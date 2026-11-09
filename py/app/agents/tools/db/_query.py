"""只读查询执行器 - run_sql / resolve_form 共用的底层执行层

安全模型: 仅允许 SELECT / WITH 开头的只读查询；行数上限与超时由调用方控制。
Oracle 经 oracledb 无法在一条 execute 中执行多语句（; 会抛 ORA-00911），
故顶层关键字为 SELECT/WITH 即可保证只读。
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal

from app.database import engine

logger = logging.getLogger(__name__)

ROW_LIMIT = 100
TIMEOUT_MS = 30_000
LABEL_LANG_CN = 7  # e-cology htmllabelinfo 中文 languageid

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_FOR_UPDATE = re.compile(r"\bfor\s+update\b", re.IGNORECASE)


def _strip_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    return sql


def _normalize(sql: str) -> str:
    return " ".join(_strip_comments(sql).split())


def is_read_only(sql: str) -> tuple[bool, str]:
    """校验是否为只读 SELECT/WITH。返回 (ok, reason)"""
    s = _normalize(sql).strip(";").strip()
    if not s:
        return False, "空 SQL"
    first = s.split(None, 1)[0].strip('`"[]').lower()
    if first not in ("select", "with"):
        return False, f"仅允许 SELECT/WITH 开头，检测到 '{first}'"
    if _FOR_UPDATE.search(s):
        return False, "禁止 FOR UPDATE（只读模式不允许加锁）"
    return True, "ok"


def _convert(value):
    """把 oracledb 返回值转为 JSON 可序列化的 Python 对象"""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return value.hex() if isinstance(value, (bytes, bytearray)) else str(value)
    if hasattr(value, "read"):  # CLOB/BLOB
        try:
            return value.read()
        except Exception:
            return str(value)
    return value


def execute_select(
    sql: str,
    params: dict | None = None,
    limit: int = ROW_LIMIT,
    timeout_ms: int = TIMEOUT_MS,
    datasource: str | None = None,
) -> dict:
    """执行只读 SELECT，返回 {columns, rows, count, truncated} 或 {error, detail}。

    params 采用 oracledb 命名绑定（:name）。
    """
    ok, reason = is_read_only(sql)
    if not ok:
        return {"error": "ONLY_SELECT_ALLOWED", "detail": reason}

    if datasource:
        from app.datasource import registry
        adapter = registry.get_adapter(datasource)
        if not adapter:
            return {"error": "DATASOURCE_NOT_FOUND", "detail": f"数据源 {datasource!r} 不存在"}
        return adapter.execute_readonly(sql, limit=limit, timeout_ms=timeout_ms)

    conn = engine.raw_connection()
    try:
        try:
            conn.call_timeout = timeout_ms  # oracledb thick 模式超时（毫秒）
        except Exception:
            pass
        cur = conn.cursor()
        try:
            cur.execute(sql, params or {})
            cols = [d[0].lower() for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(limit)
            rows = [[_convert(v) for v in r] for r in fetched]
            truncated = False
            if len(fetched) == limit:
                truncated = cur.fetchone() is not None
            return {
                "columns": cols,
                "rows": rows,
                "count": len(rows),
                "truncated": truncated,
            }
        finally:
            cur.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("execute_select 失败: %s: %s", type(e).__name__, e)
        return {"error": "QUERY_FAILED", "detail": f"{type(e).__name__}: {e}"}
    finally:
        conn.close()  # 归还连接池


def resolve_labels(indexids: list[int]) -> dict[int, str]:
    """批量解析标签 indexid -> 中文 labelname（languageid=7）"""
    ids = [i for i in dict.fromkeys(indexids) if i is not None]
    if not ids:
        return {}
    in_list = ",".join(str(int(i)) for i in ids)  # indexid 为整数，可安全内联
    res = execute_select(
        "select indexid, labelname from htmllabelinfo "
        f"where indexid in ({in_list}) and languageid={LABEL_LANG_CN}",
        limit=max(1000, len(ids)),
    )
    if res.get("error"):
        return {}
    out: dict[int, str] = {}
    cols = res["columns"]
    ii = cols.index("indexid") if "indexid" in cols else 0
    li = cols.index("labelname") if "labelname" in cols else 1
    for row in res["rows"]:
        try:
            out[int(row[ii])] = row[li]
        except (TypeError, ValueError, IndexError):
            continue
    return out
