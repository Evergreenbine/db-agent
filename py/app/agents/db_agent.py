"""DB-Agent Runner - 提供 run / run_streamed 入口

已接入工具(5): run_sql / resolve_form / search_schema / get_table_detail / list_modules
"""

import asyncio

from agents import Agent, Runner, ModelSettings
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent

import app.agents.base  # noqa: F401  触发 DeepSeek 客户端配置
from app.agents.base import inject_user_context
from app.agents.rag.store import get_tool_title
from app.agents.memory.knowledge import inject_knowledge
from app.agents.tools.registry import get_all_tools
from app.config import get_settings

settings = get_settings()

_INSTRUCTIONS = """你是 e-cology 数据库助手（DB-Agent）。

职责：帮用户用自然语言查询或变更 e-cology 数据库（OA 库，Oracle）。

解题流程：
1. 判断用户问的是「自定义表单」还是「标准模块表」：
   - 自定义表单（“付款单”“报销单”等业务名）：用 resolve_form 解析物理表与字段。
   - 标准模块表（部门、人员、合同、会议等）：先用 search_schema 按中文关键词检索表名；
     不确定有哪些模块时先 list_modules 看模块清单并按 module 缩小范围。
2. 命中表后，用 get_table_detail 看完整字段名/类型/中文说明，或对自定义表单直接读 resolve_form 返回的字段。
3. 用 run_sql 编写并执行只读 SELECT 取数。
4. 用自然语言回答，并附所用 SQL 与关键表名。

5. 遇到新业务场景（当前对话中首次涉及的表单/表/业务操作）时，先调用 query_knowledge 查语义记忆库，看是否有已沉淀的表关系、字段用途、业务规则或执行经验可直接复用，避免重复摸索。如果当前请求是沿着上文同一业务对象继续追问（如表名、操作类型已在之前消息中出现），则无需重复查询，直接沿用上下文。发现新的表关系或字段用途时，用 save_knowledge 沉淀。
6. 用户说「帮我记住」「记住」「记一下」时，立即调用 save_knowledge 沉淀。根据内容判断 knowledge_type：
   - 表A.字段关联表B.字段 → table_relation
   - 表单名/物理表/流程编号/明细表 → form_meta
   - 字段中文含义或用途 → field_usage
   - 业务操作流程或规则 → business_rule
   - 无名明细表的用途 → unnamed_detail
   存完后告诉用户「已记住」，不要重复存已有内容（先 query_knowledge 查一下）。
7. 用户要求变更数据（增/改/删）时：用 execute_write 生成预览（DELETE/UPDATE 必须带 WHERE），收到 requires_confirm 即停，等用户在卡片确认执行。

工具说明：
- list_modules(purpose)：列出数据字典全部模块及表数。purpose 必填，用一句中文写明本次列出目的。
- search_schema(purpose, query, module?)：在数据字典里向量检索相关标准表（不含自定义表单）。purpose 必填，用一句中文写明本次检索目的。返回表名/中文名/模块/主键/字段摘要/分数。
- get_table_detail(purpose, table, datasource?)：单张标准表的完整字段定义（OA 库来自数据字典）。purpose 必填。datasource 可选：查非 OA 库时传数据源名，会实时返回该库字段定义（无中文说明）。
- resolve_form(purpose, business_name)：按业务名解析自定义流程表单的物理表(formtable_main_<id>)与字段+中文名。purpose 必填，用一句中文写明本次解析目的。自定义表单不在字典里，只能靠它。
- run_sql(purpose, sql, datasource?)：只读 SELECT，行数上限 100，超时 30 秒；不要写结尾分号，不要写 DML/DDL。purpose 必填。datasource 可选：查非 OA 库时传数据源名；注意目标库 SQL 方言（SQL Server 用 GETDATE()/TOP n、无 dual、无 to_date、分页用 OFFSET FETCH）。
- query_knowledge(purpose, query, knowledge_type?)：查业务知识库（表关系/字段用途/流程编号/业务规则）。不确定时先查。purpose 必填。
- save_knowledge(purpose, knowledge_type, title, content, keywords?, source_tables?)：沉淀业务知识。发现新表关系/字段用途时调用。table_relation 的 content 格式：源表.字段 -> 目标表.字段 (关系类型)。
- execute_write(purpose, steps)：数据变更组合预览（DELETE/UPDATE/INSERT/MERGE，支持多条）。steps 必传数组，每步是结构化对象：
  {sql, preview_sql, table, columns?, datasource?, description?}
  sql=最终执行的 DML；preview_sql=预览受影响数据的 SELECT（DELETE/UPDATE 必填，WHERE 与 sql 一致）；table=目标物理表名；table_label=表中文名（如"检测委托单明细1"，显示在步骤头让用户看懂）；columns=受影响列名（预览高亮），多表 JOIN 预览时用 [{"name":"col","table":"TABLE_A"}] 标注每列归属表名；datasource=跨库时传数据源名；column_labels=列名→中文名映射（如 {"sybz":"审批意见"}）；column_meta=列元数据数组（如 [{"name":"sylx2","table":"FORMTABLE_MAIN_238","label":"试验类型","affected":true},{"name":"sylx1","table":"FORMTABLE_MAIN_238_DT1","label":"试验类型"}]），affected=true 标记被更新的列，跨表列标注来源表让预览分色显示；description=本步说明。
  一步能做完的 SQL 不要拆分——含 MERGE INTO、连表 UPDATE、子查询 SET 等复杂语句直接写一条完整 DML。
  只预览、不执行：DELETE/UPDATE 必须带 WHERE，用户在组合卡片一次「确定执行」；多步按序执行、失败即停（跨库无原子回滚）。purpose 必填，用一句中文写明本次变更目的。

工具调用纪律：
- resolve_form 无匹配时，可用 run_sql 直接查 workflow_base.workflowname 找流程，或查 all_tables / user_tables 找表。
- 取数前若不确定列名，先 get_table_detail 或 resolve_form 确认，避免写错列名。
- 调用 run_sql / resolve_form / search_schema / get_table_detail / list_modules 时，purpose 必填：用一句中文写明"这次是为了查什么/为什么"，让用户在看工具调用时就能知道你的意图；不要写空、不要写英文、不要照抄 SQL。

- 用户要求新增/修改/删除数据时用 execute_write 生成预览；收到 requires_confirm=true 后立即停止工具调用，用一句话说明预览了多少行、请在确认卡片点「确定执行」，然后结束回答。严禁重复调用 execute_write，严禁用 run_sql 执行 DML（run_sql 只读）。
- 收到以「[执行确认]」开头的消息时：这是用户在确认卡片点「确定执行」后系统自动回传的执行结果（含已执行 SQL、影响行数、执行后回查行数与验证查询）。请用 run_sql 执行消息中提供的验证查询，确认数据已正确变更（幂等性检查），然后告知用户执行结果与验证结论。不要重复执行写操作（execute_write），run_sql 只读可以放心调用。
- 收到以「[执行取消]」开头的消息时：用户已取消本次变更，不执行。用一句话确认取消即可，不要调用任何工具。

回答规范：
- 先给结论，再附 SQL 代码块与关键表名。
- 日期比较用 to_date('YYYY-MM-DD','YYYY-MM-DD')。
- 金额/日期字段需说明含义。"""


def _build_mentions_block(user_context: dict | None) -> str:
    """把用户 @ 引用的表单/标准表注入为指令块，避免 LLM 再调 resolve_form/search_schema。

    header 仅传 ASCII 的 {table,type,id}，中文 label 由后端从 DB 权威解析，规避 header 中文编码问题。
    """
    mentions = (user_context or {}).get("mentions") or []
    if not mentions:
        return ""
    from app.agents.rag.schema_store import get_table_detail
    from app.agents.tools.db.resolve_form import get_form_detail_by_id

    lines = ["【用户已 @ 引用的表单】以下表单已由用户明确选定，物理表名与字段已为你准备好，可直接据此写 SQL："]
    for m in mentions:
        mtype = m.get("type")
        table = (m.get("table") or "").lower()
        given_label = m.get("label")
        try:
            ds_name = (m.get("datasource") or "").strip()
            if ds_name:
                from app.datasource import registry
                adapter = registry.get_adapter(ds_name)
                if not adapter:
                    lines.append(f"【{given_label or table}】物理表 {table}（数据源 {ds_name}，不存在）")
                    continue
                cols = adapter.get_columns(table)
                if not cols:
                    lines.append(f"【{given_label or table}】物理表 {table}（数据源 {ds_name}，表不存在或无字段）")
                    continue
                flds = ", ".join(f"{c.get('name')}:{c.get('data_type')}" for c in cols[:40])
                lines.append(
                    f"【{given_label or table}】物理表 {table}（数据源 {ds_name}，{adapter.config.db_type}）字段: {flds}。"
                    f"查询时 run_sql / get_table_detail 必须带 datasource=\"{ds_name}\"。"
                )
                continue
            if mtype == "builtin":
                d = get_table_detail(table)
                if d.get("error"):
                    label = given_label or table
                    lines.append(f"【{label}】物理表 {table.upper()}（系统内置表，解析失败：{d.get('detail', '')}）")
                else:
                    label = d.get("chinese_name") or given_label or table
                    fields = d.get("fields") or []
                    flds = ", ".join(f"{f.get('name')}={f.get('chinese_name') or ''}" for f in fields[:20])
                    lines.append(f"【{label}】物理表 {table.upper()}（系统内置表）字段: {flds}")
            else:
                fid = m.get("id")
                if fid is None:
                    label = given_label or table
                    lines.append(f"【{label}】物理表 {table.upper()}（{mtype}，缺少 form_id）")
                    continue
                dt_name = (m.get("detail_table") or "").strip()
                if dt_name:
                    from app.agents.tools.db.resolve_form import get_detail_table_fields
                    dd = get_detail_table_fields(int(fid), dt_name)
                    if dd.get("fields"):
                        flds = ", ".join(f"{f.get('field')}={f.get('label') or ''}" for f in dd["fields"])
                        lines.append(f"【{given_label or dt_name}】物理表 {dt_name.upper()}（{mtype}明细表，form_id={fid}）字段: {flds}")
                    else:
                        lines.append(f"【{given_label or dt_name}】物理表 {dt_name.upper()}（{mtype}明细表，form_id={fid}，无字段）")
                    continue
                d = get_form_detail_by_id(int(fid))
                if d.get("error"):
                    label = given_label or table
                    lines.append(f"【{label}】物理表 {table.upper()}（{mtype}，form_id={fid}，解析失败）")
                else:
                    label = d.get("label") or given_label or table
                    main = d.get("main_fields") or []
                    flds = ", ".join(f"{f.get('field')}={f.get('label') or ''}" for f in main)
                    extras = [f"{dt.get('detail_table')}({dt.get('field_count')}字段)" for dt in (d.get("detail_tables") or [])]
                    extra = "; 明细表: " + ", ".join(extras) if extras else ""
                    lines.append(f"【{label}】物理表 {table.upper()}（{mtype}，form_id={fid}）字段: {flds}{extra}")
        except Exception as e:
            label = given_label or table
            lines.append(f"【{label}】物理表 {table.upper()}（解析异常：{type(e).__name__}: {e}）")
    return "\n".join(lines)


def _build_datasources_block() -> str:
    """列出已配置数据源，提示 LLM 可通过 datasource 参数跨库查询。"""
    try:
        from app.datasource import registry
        ds_list = registry.list_all()
    except Exception:
        ds_list = []
    if not ds_list:
        return ""
    lines = ["【已配置数据源】run_sql / get_table_detail 可用 datasource 参数指定目标库；不传默认查 OA 库："]
    for d in ds_list:
        lines.append(f'- datasource="{d["name"]}"：{d["db_type"]}，{d.get("description","")}（{d["host"]}:{d["port"]}/{d["database_name"]}）')
    lines.append("跨库时务必带上对应 datasource 名称，并使用该库的 SQL 方言。")
    return "\n".join(lines)


def _build_agent(user_context: dict | None = None, user_input: str = "") -> Agent:
    instructions = inject_user_context(_INSTRUCTIONS, user_context)
    ds_block = _build_datasources_block()
    if ds_block:
        instructions += "\n\n" + ds_block
    mentions_block = _build_mentions_block(user_context)
    if mentions_block:
        instructions += "\n\n" + mentions_block
    knowledge_block = inject_knowledge(user_input, session_id=(user_context or {}).get("session_id", ""))
    if knowledge_block:
        instructions += "\n\n" + knowledge_block
    return Agent(
        name="DB-Agent",
        instructions=instructions,
        tools=get_all_tools(),
        model=settings.deepseek_model,
        model_settings=ModelSettings(),
    )


def _build_session(session_id, user_context=None):
    if not session_id:
        return None
    from app.agents.session import get_session
    uid = (user_context or {}).get("employee_id", "")
    uname = (user_context or {}).get("name", "")
    return get_session(session_id, user_id=uid, user_name=uname)


async def run_agent(user_input, session_id=None, user_context=None) -> str:
    agent = await asyncio.to_thread(_build_agent, user_context, user_input)
    session = _build_session(session_id, user_context)
    final_input = user_input
    result = await Runner.run(agent, final_input, session=session)
    return result.final_output


async def run_agent_streamed(user_input, session_id=None, user_context=None):
    agent = await asyncio.to_thread(_build_agent, user_context, user_input)
    session = _build_session(session_id, user_context)
    final_input = user_input
    result = Runner.run_streamed(agent, final_input, session=session)
    async for event in result.stream_events():
        if isinstance(event, RawResponsesStreamEvent):
            data = event.data
            if data.type == "response.output_text.delta":
                yield {"type": "text", "content": data.delta}
            elif data.type in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
                yield {"type": "reasoning", "content": data.delta}
        elif isinstance(event, RunItemStreamEvent):
            if event.name == "tool_called":
                item = event.item
                tool_name = getattr(item, "tool_name", "") or ""
                raw = getattr(item, "raw_item", None)
                tool_args = getattr(raw, "arguments", "") or "" if raw else ""
                call_id = str(getattr(item, "call_id", "") or "")
                print(f"[TOOL] called: name={tool_name} call_id={call_id}", flush=True)
                yield {"type": "tool_call", "tool_call_id": call_id, "name": tool_name, "title": get_tool_title(tool_name), "args": tool_args}
            elif event.name == "tool_output":
                item = event.item
                call_id = str(getattr(item, "call_id", "") or "")
                output = str(getattr(item, "output", ""))
                print(f"[TOOL] output: call_id={call_id} output_len={len(output)}", flush=True)
                yield {"type": "tool_result", "tool_call_id": call_id, "output": output}
