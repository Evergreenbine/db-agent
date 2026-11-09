"""run_sql - 执行只读 SELECT 查询并返回 JSON 结果"""

import json

from app.agents.tools.registry import tool
from app.agents.tools.db._query import ROW_LIMIT, TIMEOUT_MS, execute_select


@tool
def run_sql(purpose: str, sql: str, datasource: str = "") -> str:
    """执行一条只读 SELECT 查询并返回 JSON 结果。

    purpose: 【必填】用一句中文写明本次查询的目的——要查什么/为什么查，例如"查何春梅 2025-09-24 至 2025-10-23 的加班小时数合计"。仅用于向用户展示意图，不参与执行。
    何时用：已通过 resolve_form / search_schema 确认表名与字段后，用它真正取数。
    输入：一条完整的 Oracle SELECT 或 WITH 语句；不要写结尾分号；不要写 DML/DDL。
    安全：仅允许只读查询；结果行数上限 100；查询超时 30 秒；表名/字段名大小写不敏感。
    自定义表单物理表形如 formtable_main_<id>，明细表形如 formtable_main_<id>_dt<n>；
    若不确定表名请先调用 resolve_form，不要用本工具猜测。
    返回：JSON 字符串 {"columns":[...], "rows":[[...],...], "count":N, "truncated":bool}；
          失败时 {"error":"ONLY_SELECT_ALLOWED"|"QUERY_FAILED", "detail":"..."}。
    Oracle 日期比较示例：requestlog.createdate >= to_date('2025-01-01','YYYY-MM-DD')。
    datasource: 可选，目标数据源名称（如 hr）；不传则默认查 OA 库。跨库查询时必传，并注意目标库的 SQL 方言（SQL Server 用 GETDATE()/TOP，无 dual、无 to_date）。
    """
    result = execute_select(sql, limit=ROW_LIMIT, timeout_ms=TIMEOUT_MS, datasource=datasource or None)
    return json.dumps(result, ensure_ascii=False, default=str)
