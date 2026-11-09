"""智能体路由"""

import json

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.db_agent import run_agent, run_agent_streamed
from app.agents.tools.db._write import execute_dml, execute_dml_routed, execute_dml_batch, classify
from app.agents.tools.db._query import execute_select
from app.auth.deps import get_user_from_auth_header
from app.agents.history import list_conversations, get_history, delete_conversation, patch_tool_result, patch_latest_tool_result

router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    prompt: str = Field(default="你好", description="用户输入")
    session_id: str | None = Field(default=None, description="会话 ID（多轮对话记忆）")


class AgentResponse(BaseModel):
    prompt: str
    response: str


@router.post("/test", response_model=AgentResponse)
async def test_agent(
    req: AgentRequest,
    authorization: str | None = Header(None),
    x_employee_id: str | None = Header(None, alias="X-Employee-Id"),
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
    x_sqr: str | None = Header(None, alias="X-SQR"),
    x_mentions: str | None = Header(None, alias="X-Mentions"),
):
    """测试智能体 - 调用 DeepSeek 模型（带会话记忆 + 用户身份 + 单据上下文）"""
    user_context = get_user_from_auth_header(authorization, x_employee_id)
    if x_request_id:
        user_context["request_id"] = x_request_id
    if x_sqr:
        user_context["sqr"] = x_sqr
    if x_mentions:
        try:
            user_context["mentions"] = json.loads(x_mentions)
        except (json.JSONDecodeError, TypeError):
            user_context["mentions"] = []
    result = await run_agent(
        req.prompt, session_id=req.session_id, user_context=user_context
    )
    return AgentResponse(prompt=req.prompt, response=result)


async def _sse_generator(prompt: str, session_id: str | None, user_context: dict):
    """SSE 事件生成器：真流式输出 + 工具调用事件"""
    try:
        async for event in run_agent_streamed(
            prompt, session_id=session_id, user_context=user_context
        ):
            chunk = json.dumps(event, ensure_ascii=False)
            yield f"data: {chunk}\n\n"
    except Exception as e:
        import logging as _log, traceback as _tb
        _log.getLogger("db_agent").error("SSE_ERR type=%s repr=%r\n%s", type(e).__name__, e, _tb.format_exc())
        error = json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
        yield f"data: {error}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat_agent(
    req: AgentRequest,
    authorization: str | None = Header(None),
    x_employee_id: str | None = Header(None, alias="X-Employee-Id"),
    x_request_id: str | None = Header(None, alias="X-Request-Id"),
    x_sqr: str | None = Header(None, alias="X-SQR"),
    x_mentions: str | None = Header(None, alias="X-Mentions"),
):
    """流式对话接口 - SSE 格式（真流式 + 工具事件 + 用户身份 + 单据上下文）"""
    user_context = get_user_from_auth_header(authorization, x_employee_id)
    if x_request_id:
        user_context["request_id"] = x_request_id
    if x_sqr:
        user_context["sqr"] = x_sqr
    if x_mentions:
        try:
            user_context["mentions"] = json.loads(x_mentions)
            import sys as _sys2
            print(f"[MENTIONS_DEBUG] chat header={x_mentions[:300]}", file=_sys2.stderr, flush=True)
        except (json.JSONDecodeError, TypeError):
            user_context["mentions"] = []
    else:
        import sys as _sys2
        print("[MENTIONS_DEBUG] chat no X-Mentions header", file=_sys2.stderr, flush=True)
    return StreamingResponse(
        _sse_generator(req.prompt, req.session_id, user_context),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ConfirmStep(BaseModel):
    sql: str = Field(..., description="该步 DML 语句")
    datasource: str = Field(default="", description="目标数据源名称；空或 oa 走全局 Oracle，其余走适配器")
    table: str = Field(default="", description="目标表名（审计用）")
    preview_sql: str = Field(default="", description="SELECT for after-exec verification")

class ConfirmWriteRequest(BaseModel):
    steps: list[ConfirmStep] | None = Field(default=None, description="组合多步执行")
    sql: str = Field(default="", description="单条 DML（兼容旧格式）")
    datasource: str = Field(default="", description="数据源（兼容旧格式）")


@router.post("/confirm-write")
async def confirm_write(
    req: ConfirmWriteRequest,
    authorization: str | None = Header(None),
    x_employee_id: str | None = Header(None, alias="X-Employee-Id"),
):
    """用户在确认卡片点「确定执行」后调用：二次校验 + 执行 DML + 审计日志。

    安全：重新校验 DML + WHERE（不信前端）；DELETE/UPDATE 无 WHERE 直接拒；
    影响行数超上限拒绝；全部写操作落 logs/writes.jsonl 审计。
    """
    user_context = get_user_from_auth_header(authorization, x_employee_id)
    employee_id = user_context.get("employee_id", "")

    def _after_preview(r, st, ds):
        if r.get("executed") and not r.get("error") and st.preview_sql:
            try:
                after = execute_select(st.preview_sql, limit=1000, timeout_ms=60_000, datasource=ds or None)
                if after.get("error"):
                    r["after_preview"] = {"error": after["error"], "detail": after.get("detail", "")}
                else:
                    r["after_preview"] = {
                        "columns": after.get("columns"),
                        "rows": after.get("rows"),
                        "count": after.get("count"),
                        "truncated": after.get("truncated"),
                    }
            except Exception as e:
                r["after_preview"] = {"error": "AFTER_QUERY_FAILED", "detail": str(e)}
        return r

    if req.steps:
        dss = set((s.datasource or "").strip() for s in req.steps)
        if len(dss) == 1:
            ds = dss.pop()
            steps_data = [(s.sql, s.table) for s in req.steps]
            batch = execute_dml_batch(steps_data, employee_id=employee_id, datasource=ds)
            results = batch.get("results", [])
            for i, st in enumerate(req.steps):
                if i < len(results):
                    _after_preview(results[i], st, ds)
            return {
                "executed": batch.get("executed", False),
                "step_count": batch.get("step_count", len(req.steps)),
                "ok_count": batch.get("ok_count", 0),
                "results": results,
                "partial_failure": batch.get("partial_failure", False),
                "transactional": True,
            }
        def _run_step(st):
            ds = (st.datasource or "").strip()
            if ds and ds != "oa":
                r = execute_dml_routed(st.sql, datasource=ds, employee_id=employee_id, table=st.table)
            else:
                r = execute_dml(st.sql, employee_id=employee_id, table=st.table)
            return _after_preview(r, st, ds)
        results = []
        for st in req.steps:
            r = _run_step(st)
            results.append(r)
            if r.get("error"):
                break
        ok_count = sum(1 for r in results if r.get("executed"))
        return {
            "executed": ok_count == len(req.steps),
            "step_count": len(req.steps),
            "ok_count": ok_count,
            "results": results,
            "partial_failure": 0 < ok_count < len(req.steps),
        }

    if req.sql:
        ds = (req.datasource or "").strip()
        if ds and ds != "oa":
            return execute_dml_routed(req.sql, datasource=ds, employee_id=employee_id)
        return execute_dml(req.sql, employee_id=employee_id)
    return {"error": "BAD_REQUEST", "detail": "需要 steps 或 sql"}


class PatchToolResultRequest(BaseModel):
    session_id: str = Field(..., description="session ID")
    tool_call_id: str = Field(..., description="tool call ID to patch")
    patch: dict = Field(..., description="fields to merge into tool output")


@router.post("/patch-tool-result")
async def patch_tool_result_endpoint(
    req: PatchToolResultRequest,
    authorization: str | None = Header(None),
    x_employee_id: str | None = Header(None, alias="X-Employee-Id"),
):
    """Patch a stored tool result (e.g. exec_result, executed, user_decision) into history."""
    ok = patch_tool_result(req.session_id, req.tool_call_id, req.patch)
    return {"patched": ok}


class PatchExecResultRequest(BaseModel):
    session_id: str = Field(..., description="session ID")
    patch: dict = Field(..., description="fields to merge into tool output")


@router.post("/patch-exec-result")
async def patch_exec_result_endpoint(
    req: PatchExecResultRequest,
    authorization: str | None = Header(None),
    x_employee_id: str | None = Header(None, alias="X-Employee-Id"),
):
    """Patch the most recent execute_write tool output in this session."""
    ok = patch_latest_tool_result(req.session_id, "execute_write", req.patch)
    return {"patched": ok}




# ===== 历史对话 =====


@router.get("/history")
async def history_list(
    user_id: str | None = None,
    limit: int = 50,
):
    """列出历史会话（最新在前）。可选 user_id 过滤。"""
    return {"conversations": list_conversations(user_id=user_id, limit=limit)}


@router.get("/history/{session_id}")
async def history_detail(session_id: str):
    """获取某个会话的全部消息（按时间序）。"""
    return {"session_id": session_id, "messages": get_history(session_id)}


@router.delete("/history/{session_id}")
async def history_delete(session_id: str):
    """删除某个会话的全部记录。"""
    delete_conversation(session_id)
    return {"deleted": True, "session_id": session_id}
