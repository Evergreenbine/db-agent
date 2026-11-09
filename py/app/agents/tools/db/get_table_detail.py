"""get_table_detail - 查询单张标准模块表的完整字段定义"""

import json

from app.agents.tools.registry import tool
from app.agents.rag.schema_store import get_table_detail as _get_table_detail


@tool
def get_table_detail(purpose: str, table: str, datasource: str = "") -> str:
    """查询单张标准模块表的完整字段定义（来自数据字典）。
    purpose: 【必填】用一句中文写明本次查看表结构的目的——要确认什么/为什么看，例如「确认 hrmdepartment 的部门编码字段名」。仅用于向用户展示意图，不参与执行。

    何时用：search_schema 命中表后，需要看具体字段名/类型/中文说明时。
    输入：table 表名（大小写不敏感，如 hrmdepartment）。
    返回：JSON {table, chinese_name, module, pk, description, field_count,
              fields:[{name,chinese_name,data_type,length,nullable,is_fk,is_auto,default,comment}]}。
    表不在字典中时返回 {error:"NOT_FOUND"}（自定义表单请改用 resolve_form）。
    datasource: 可选，目标数据源名称（如 hr）。非 OA 库没有数据字典缓存，传后会实时查该库的字段定义。
    """
    if datasource:
        from app.datasource import registry
        adapter = registry.get_adapter(datasource)
        if not adapter:
            return json.dumps({"error": "DATASOURCE_NOT_FOUND", "detail": f"数据源 {datasource!r} 不存在"}, ensure_ascii=False)
        cols = adapter.get_columns(table)
        return json.dumps({"table": table, "datasource": datasource, "field_count": len(cols), "fields": cols}, ensure_ascii=False, default=str)
    return json.dumps(_get_table_detail(table), ensure_ascii=False, default=str)
