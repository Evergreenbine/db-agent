"""list_modules - 列出数据字典所有模块及表数量"""

import json

from app.agents.tools.registry import tool
from app.agents.rag.schema_store import list_modules as _list_modules


@tool
def list_modules(purpose: str) -> str:
    """列出 e-cology 数据字典中所有模块及其表数量。
    purpose: 【必填】用一句中文写明本次列出模块的目的——要浏览什么/为什么列，例如「确认有哪些模块以缩小 search_schema 范围」。仅用于向用户展示意图，不参与执行。

    何时用：用户想按模块浏览，或在 search_schema 前确认模块名以缩小范围。
    返回：JSON [{module, table_count}, ...]，按表数降序。
    """
    return json.dumps(_list_modules(), ensure_ascii=False, default=str)
