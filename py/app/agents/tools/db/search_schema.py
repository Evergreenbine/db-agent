"""search_schema - 在数据字典里检索相关标准模块表"""

import json

from app.agents.tools.registry import tool
from app.agents.rag.schema_store import search_schema as _search_schema


@tool
def search_schema(purpose: str, query: str, module: str = "") -> str:
    """在 e-cology 数据字典里检索与关键词相关的标准模块表（不含自定义流程表单）。

    purpose: 【必填】用一句中文写明本次检索的目的，例如"找部门相关的标准表"。仅用于向用户展示意图，不参与执行。
    何时用：用户问标准业务表在哪（如“部门表”“人员信息表”“合同表”），用它找表名。
    输入：query 中文业务关键词（如“部门”“人员”“合同”“会议”）；module 可选，限定模块（如“人力资源”）。
    返回：JSON，最多 8 张表 [{table, chinese_name, module, pk, field_count, field_summary, score}]。
    拿到表名后用 get_table_detail 看完整字段，或直接 run_sql 查询。
    注意：本工具只覆盖数据字典内的标准模块表；流程表单/建模表单(如“付款单”)用 resolve_form。
    """
    return json.dumps(_search_schema(query, module=module or None, top_k=8), ensure_ascii=False, default=str)
