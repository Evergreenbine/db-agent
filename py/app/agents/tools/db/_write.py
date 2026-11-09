"""DML 写操作支持 - 校验 / 预览 / 执行（仅 confirm-write 接口调用执行）

安全模型: execute_write 工具只做预览（运行模型提供的 preview_sql），
真正执行 DML 只能由 /api/agent/confirm-write 接口经 execute_dml 完成。
DELETE/UPDATE 必须带 WHERE；影响行数超 PREVIEW_LIMIT 即拒绝执行。

架构变更: 不再用正则解析 SQL。模型通过结构化 step 提供 sql/preview_sql/table/columns，
后端只执行 preview_sql 取预览数据，执行 sql 做 DML，零解析。
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

from app.database import engine
from app.agents.tools.db._query import _normalize, execute_select

logger = logging.getLogger("db_write")

PREVIEW_LIMIT = 1000
WRITE_TIMEOUT_MS = 60_000

_HAS_WHERE_RE = re.compile(r"\bwhere\b", re.IGNORECASE)

# ---- 审计日志（JSONL，append）----
_LOG_DIR = Path(__file__).resolve().parents[4] / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "writes.jsonl"


def _audit(employee_id, action, table, sql, rows_affected, status):
    rec = {
        "ts": datetime.now().isoformat(),
        "user": employee_id or "",
        "action": action,
        "table": table,
        "sql": sql,
        "rows": rows_affected,
        "status": status,
    }
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        logger.warning("审计日志写入失败: %s", e)


def classify(sql):
    """返回 (action, reason)。action in delete|update|insert|merge|None"""
    s = _normalize(sql).strip(";").strip()
    if not s:
        return None, "空 SQL"
    first = s.split(None, 1)[0].strip('`"[]').lower()
    if first == "delete":
        return "delete", "ok"
    if first == "update":
        return "update", "ok"
    if first == "insert":
        return "insert", "ok"
    if first == "merge":
        return "merge", "ok"
    return None, "非 DML 语句，检测到 '%s'（仅允许 DELETE/UPDATE/INSERT/MERGE）" % first


def _has_where(sql):
    """简单检查 SQL 是否含 WHERE 关键字（安全校验，非精确解析）。"""
    return bool(_HAS_WHERE_RE.search(sql))


# ---- 预览（不执行 DML）----

def build_preview_from_step(step):
    """根据模型提供的结构化 step 生成预览（不执行 DML）。

    step 是 dict，由模型通过 execute_write 工具的 steps 参数提供：
      sql        : 必填，最终执行的 DML（UPDATE/DELETE/INSERT/MERGE）
      preview_sql: DELETE/UPDATE 必填，预览受影响数据的 SELECT 语句
      table      : 必填，目标表名（显示 + 审计）
      columns    : 可选，受影响的列名列表（预览高亮）
      datasource : 可选，数据源名；空/oa 默认 OA 库
      description: 可选，本步变更说明
    """
    sql = (step.get("sql") or "").strip()
    preview_sql = (step.get("preview_sql") or "").strip()
    table = (step.get("table") or "").strip()
    columns = step.get("columns") or []
    datasource = (step.get("datasource") or "").strip()
    table_label = step.get("table_label") or ""
    column_meta = step.get("column_meta") or []
    description = (step.get("description") or "").strip()

    if not sql:
        return {"error": "EMPTY_SQL", "detail": "step.sql 为空"}

    action, reason = classify(sql)
    if not action:
        return {"error": "NOT_DML", "detail": reason}

    if action in ("delete", "update") and not _has_where(sql):
        return {
            "error": "WHERE_REQUIRED",
            "detail": "%s 必须带 WHERE 条件，拒绝无条件全表写操作" % action.upper(),
            "action": action,
            "table": table,
        }

    column_labels = step.get("column_labels") or {}
    result = {
        "requires_confirm": True,
        "action": action,
        "table": table,
        "table_label": table_label,
        "sql": sql,
        "columns": columns,
        "column_labels": column_labels,
        "column_meta": column_meta,
        "description": description,
    }
    if datasource:
        result["datasource"] = datasource

    # INSERT / MERGE 不需要预览查询数据
    if action in ("insert", "merge"):
        return result

    # DELETE / UPDATE: 执行 preview_sql 取受影响数据
    if not preview_sql:
        result["error"] = "NO_PREVIEW_SQL"
        result["detail"] = "模型未提供 preview_sql，无法生成预览"
        return result

    res = execute_select(
        preview_sql,
        limit=PREVIEW_LIMIT,
        timeout_ms=WRITE_TIMEOUT_MS,
        datasource=datasource or None,
    )
    result["preview_sql"] = preview_sql
    if res.get("error"):
        result["preview"] = res
    else:
        result["preview"] = {
            "columns": res.get("columns"),
            "rows": res.get("rows"),
            "count": res.get("count"),
            "truncated": res.get("truncated"),
        }
    return result


def build_combined_preview(steps):
    """结构化 step 组合预览。steps: list[dict]，每个 dict 含 sql/preview_sql/table/columns/datasource/description。"""
    if not steps:
        return {"error": "EMPTY_STATEMENTS", "detail": "steps 为空"}

    results = []
    has_error = False
    for step in steps:
        st = build_preview_from_step(step)
        if st.get("error"):
            has_error = True
        results.append(st)

    out = {
        "requires_confirm": not has_error,
        "step_count": len(results),
        "steps": results,
    }
    if has_error:
        out["error"] = "STEP_PREVIEW_FAILED"
        out["detail"] = "部分语句预览失败，见 steps[].error"
    return out


# ---- 执行 DML（仅 confirm-write 接口调用）----

def execute_dml_routed(sql, datasource="", employee_id="", timeout_ms=WRITE_TIMEOUT_MS, table=""):
    """执行 DML 并按数据源路由：空/oa 走全局 Oracle 引擎，其余走适配器。含安全校验与审计。"""
    action, reason = classify(sql)
    if not action:
        return {"error": "NOT_DML", "detail": reason}

    if action in ("delete", "update") and not _has_where(sql):
        _audit(employee_id, action, table, sql, 0, "REJECTED_NO_WHERE")
        return {"error": "WHERE_REQUIRED", "detail": "%s 必须带 WHERE" % action.upper()}

    ds = (datasource or "").strip()
    if ds and ds != "oa":
        from app.datasource import registry
        adapter = registry.get_adapter(ds)
        if not adapter:
            return {"error": "DATASOURCE_NOT_FOUND", "detail": "数据源 %r 不存在" % ds}
        r = adapter.execute_dml(sql, timeout_ms=timeout_ms)
        status = "OK" if r.get("executed") else "FAILED"
        _audit(employee_id, action, table, sql, r.get("rows_affected", 0), status)
        r.update({"action": action, "table": table, "datasource": ds})
        return r

    return execute_dml(sql, employee_id=employee_id, timeout_ms=timeout_ms, table=table)


def execute_dml(sql, employee_id="", timeout_ms=WRITE_TIMEOUT_MS, table=""):
    """真正执行 DML（仅 confirm-write 接口调用）。二次校验 + 审计。"""
    action, reason = classify(sql)
    if not action:
        return {"error": "NOT_DML", "detail": reason}

    if action in ("delete", "update") and not _has_where(sql):
        _audit(employee_id, action, table, sql, 0, "REJECTED_NO_WHERE")
        return {"error": "WHERE_REQUIRED", "detail": "%s 必须带 WHERE" % action.upper()}

    conn = engine.raw_connection()
    try:
        try:
            conn.call_timeout = timeout_ms
        except Exception:
            pass
        cur = conn.cursor()
        try:
            cur.execute(sql)
            conn.commit()
            affected = cur.rowcount
            _audit(employee_id, action, table, sql, affected, "OK")
            return {"executed": True, "action": action, "table": table, "rows_affected": affected}
        except Exception as e:  # noqa: BLE001
            try:
                conn.rollback()
            except Exception:
                pass
            _audit(employee_id, action, table or "", sql, 0, "FAILED:%s" % type(e).__name__)
            logger.warning("execute_dml 失败: %s: %s", type(e).__name__, e)
            return {"error": "WRITE_FAILED", "detail": "%s: %s" % (type(e).__name__, e)}
        finally:
            cur.close()
    finally:
        conn.close()


def execute_dml_batch(steps, employee_id="", datasource="", timeout_ms=WRITE_TIMEOUT_MS):
    """Execute multiple DMLs in a single transaction (all-or-nothing).
    steps: list of (sql, table) tuples. Must share same datasource.
    Returns {executed, step_count, ok_count, results, partial_failure, transactional}.
    """
    if not steps:
        return {"executed": False, "error": "EMPTY", "results": [],
                "step_count": 0, "ok_count": 0, "partial_failure": False}

    classified = []
    for sql, table in steps:
        action, reason = classify(sql)
        if not action:
            return {"executed": False, "error": "NOT_DML", "detail": reason,
                    "results": [], "step_count": len(steps), "ok_count": 0, "partial_failure": False}
        if action in ("delete", "update") and not _has_where(sql):
            _audit(employee_id, action, table, sql, 0, "REJECTED_NO_WHERE")
            return {"executed": False, "error": "WHERE_REQUIRED",
                    "detail": "%s must have WHERE" % action.upper(),
                    "results": [], "step_count": len(steps), "ok_count": 0, "partial_failure": False}
        classified.append((action, sql, table))

    ds = (datasource or "").strip()

    if ds and ds != "oa":
        from app.datasource import registry
        adapter = registry.get_adapter(ds)
        if not adapter:
            return {"executed": False, "error": "DATASOURCE_NOT_FOUND",
                    "detail": "datasource %r not found" % ds,
                    "results": [], "step_count": len(steps), "ok_count": 0, "partial_failure": False}
        if hasattr(adapter, "execute_dml_batch"):
            return adapter.execute_dml_batch(classified, timeout_ms=timeout_ms, employee_id=employee_id)
        results = []
        for action, sql, table in classified:
            r = adapter.execute_dml(sql, timeout_ms=timeout_ms)
            r["action"] = action
            r["table"] = table
            _audit(employee_id, action, table, sql, r.get("rows_affected", 0),
                   "OK" if r.get("executed") else "FAILED")
            results.append(r)
            if r.get("error"):
                break
        ok = sum(1 for r in results if r.get("executed"))
        return {"executed": ok == len(classified), "step_count": len(classified),
                "ok_count": ok, "results": results,
                "partial_failure": 0 < ok < len(classified)}

    conn = engine.raw_connection()
    results = []
    all_ok = True
    try:
        try:
            conn.call_timeout = timeout_ms
        except Exception:
            pass
        cur = conn.cursor()
        try:
            for action, sql, table in classified:
                try:
                    cur.execute(sql)
                    results.append({"executed": True, "action": action,
                                    "table": table, "rows_affected": cur.rowcount})
                except Exception as e:
                    results.append({"executed": False, "error": "WRITE_FAILED",
                                    "detail": "%s: %s" % (type(e).__name__, e),
                                    "action": action, "table": table, "rows_affected": 0})
                    all_ok = False
                    break
            if all_ok:
                conn.commit()
            else:
                conn.rollback()
            for idx, (action, sql, table) in enumerate(classified):
                r = results[idx] if idx < len(results) else {"executed": False}
                status = "OK" if r.get("executed") else ("ROLLED_BACK" if not all_ok else "FAILED")
                _audit(employee_id, action, table, sql, r.get("rows_affected", 0), status)
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning("execute_dml_batch failed: %s: %s", type(e).__name__, e)
            return {"executed": False, "error": "BATCH_FAILED",
                    "detail": "%s: %s" % (type(e).__name__, e),
                    "results": results, "step_count": len(classified),
                    "ok_count": sum(1 for r in results if r.get("executed")),
                    "partial_failure": False}
        finally:
            cur.close()
    finally:
        conn.close()
    return {"executed": all_ok, "step_count": len(classified),
            "ok_count": sum(1 for r in results if r.get("executed")),
            "results": results, "partial_failure": False, "transactional": True}
