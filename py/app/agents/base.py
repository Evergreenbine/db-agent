"""智能体共享基础设施 - DeepSeek 客户端 + 用户上下文注入"""

import logging
from datetime import datetime

import httpx
from openai import AsyncOpenAI, Timeout, DefaultAsyncHttpx2Client
from agents import set_default_openai_client, set_tracing_disabled, ModelSettings
from agents import set_default_openai_api

from app.config import get_settings

settings = get_settings()

set_default_openai_api("chat_completions")
set_tracing_disabled(True)
logging.getLogger("agents").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)

_deepseek_client = AsyncOpenAI(
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_base_url,
    timeout=Timeout(connect=30.0, read=600.0, write=600.0, pool=600.0),
    http_client=DefaultAsyncHttpx2Client(trust_env=False),
)
set_default_openai_client(_deepseek_client)

import app.agents.tools  # noqa: E402,F401  触发工具注册

logger = logging.getLogger(__name__)


def inject_user_context(instructions: str, user_context: dict | None) -> str:
    """在指令末尾注入当前登录用户身份 + 单据上下文"""
    if not user_context:
        return instructions
    parts = []
    oa_emp = user_context.get("employee_id", "")
    name = user_context.get("name", "")
    if oa_emp:
        parts.append(
            f"当前登录用户：OA工号 {oa_emp}"
            + (f"，姓名 {name}" if name else "")
            + "。当用户提到「我的」「我」时，指代当前登录用户。"
        )
    request_id = user_context.get("request_id", "")
    sqr = user_context.get("sqr", "")
    if request_id or sqr:
        ctx_parts = []
        if request_id:
            ctx_parts.append(f"单据ID: {request_id}")
        if sqr:
            ctx_parts.append(f"申请人工号(sqr): {sqr}")
        parts.append("当前单据上下文 — " + "，".join(ctx_parts))
    if parts:
        instructions += "\n\n" + "\n".join(parts)
    return instructions


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")
