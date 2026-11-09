"""单据目录路由 - 供前端 @ mention 三类单据(系统内置表 / 流程表单 / 建模表单)"""

import re
import time

import jieba

# 预热 jieba 词典（首次调用较慢）
jieba.initialize()

from fastapi import APIRouter, Query

from app.agents.rag.schema_store import _ensure_sqlite
from app.agents.tools.db._query import execute_select
from app.agents.tools.db.resolve_form import get_form_detail_by_id
from app.agents.rag.schema_store import get_table_detail as _get_table_detail

router = APIRouter(prefix="/api/forms", tags=["forms"])

_cache: dict = {"ts": 0.0, "data": None}
_TTL = 600  # 10 分钟内存缓存


def _builtin_tables() -> list[dict]:
    """系统内置表 - 来自数据字典 SQLite"""
    conn = _ensure_sqlite()
    rows = conn.execute(
        "SELECT table_name, chinese_name, module FROM tables ORDER BY module, chinese_name"
    ).fetchall()
    conn.close()
    out = []
    for t, c, m in rows:
        if re.match(r"^[a-z][a-z0-9_]*$", t or ""):
            out.append({"table": t, "chinese_name": c, "module": m})
    return out


def _custom_forms(workflow: bool) -> list[dict]:
    """流程表单(workflow=True)或建模表单(workflow=False) - 来自 Oracle workflow_bill"""
    cond = ("exists (select 1 from workflow_base w where w.formid = b.id)"
            if workflow else
            "not exists (select 1 from workflow_base w where w.formid = b.id)")
    sql = (
        "select b.id, b.tablename, l.labelname "
        "from workflow_bill b "
        "left join htmllabelinfo l on b.namelabel = l.indexid and l.languageid = 7 "
        f"where {cond} order by l.labelname"
    )
    res = execute_select(sql, limit=3000)
    if res.get("error"):
        return []
    cols = res["columns"]

    def g(c):
        return cols.index(c) if c in cols else None

    out = []
    for r in res["rows"]:
        out.append({
            "id": r[g("id")] if g("id") is not None else None,
            "table": r[g("tablename")] if g("tablename") is not None else None,
            "chinese_name": r[g("labelname")] if g("labelname") is not None else None,
        })
    return out


def _datasource_tables() -> list[dict]:
    """非 OA 数据源的表清单（供 @ mention 选择器按数据源分组展示）。"""
    from app.datasource import registry
    try:
        ds_list = registry.list_all()
    except Exception:
        ds_list = []
    out = []
    for d in ds_list:
        name = d.get("name", "")
        if name == "oa":
            continue  # OA 已由三类表单覆盖
        adapter = registry.get_adapter(name)
        if not adapter:
            continue
        try:
            tables = adapter.list_tables(include_backups=False)
        except Exception:
            tables = []
        out.append({
            "name": name,
            "label": d.get("description") or name,
            "db_type": d.get("db_type", ""),
            "tables": [
                {"table": t["name"], "chinese_name": None, "datasource": name, "row_count": t.get("row_count", 0)}
                for t in tables
            ],
        })
    return out



def _ensure_ref_table(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS form_refs ("
        "table_name TEXT PRIMARY KEY, ref_count INTEGER DEFAULT 0)"
    )


def _get_ref_counts() -> dict:
    try:
        conn = _ensure_sqlite()
        _ensure_ref_table(conn)
        rows = conn.execute("SELECT table_name, ref_count FROM form_refs").fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}


def _track_form_ref(table_name: str):
    try:
        conn = _ensure_sqlite()
        _ensure_ref_table(conn)
        conn.execute(
            "INSERT INTO form_refs (table_name, ref_count) VALUES (?, 1) "
            "ON CONFLICT(table_name) DO UPDATE SET ref_count = ref_count + 1",
            (table_name,),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _sort_by_ref(items: list[dict], refs: dict) -> list[dict]:
    for it in items:
        it["ref_count"] = refs.get(it.get("table", ""), 0)
    items.sort(key=lambda x: -x["ref_count"])
    return items


@router.get("/detail")
async def form_detail(
    form_type: str = Query(..., alias="type"),
    table: str = Query(""),
    id: int | None = Query(None),
    detail_table: str = Query(""),
    datasource: str = Query(""),
):
    """单表/明细表详情 - 供前端 @ 引用 chip 悬浮卡片展示字段（复用注入逻辑）"""
    from app.agents.tools.db.resolve_form import get_detail_table_fields
    t = (form_type or "").strip().lower()
    dt = (detail_table or "").strip()
    if datasource:
        from app.datasource import registry
        adapter = registry.get_adapter(datasource)
        if not adapter:
            return {"error": "DATASOURCE_NOT_FOUND", "detail": f"数据源 {datasource!r} 不存在"}
        cols = adapter.get_columns(table)
        if not cols:
            return {"error": "NOT_FOUND", "detail": f"表 {table!r} 在数据源 {datasource!r} 中不存在或无字段"}
        return {
            "table": table,
            "datasource": datasource,
            "db_type": adapter.config.db_type,
            "fields": [
                {
                    "name": c.get("name"),
                    "chinese_name": None,
                    "data_type": c.get("data_type"),
                    "length": c.get("max_length"),
                    "nullable": c.get("is_nullable"),
                }
                for c in cols
            ],
        }
    if t == "builtin":
        return _get_table_detail(table)
    if t in ("workflow", "modeled") and id is not None:
        if dt:
            return get_detail_table_fields(int(id), dt)
        return get_form_detail_by_id(int(id))
    return {"error": "BAD_REQUEST", "detail": "需要 type=builtin&table= 或 type=workflow|modeled&id="}



@router.post("/track")
async def track_form(table: str = Query(..., description="table name to track")):
    """Increment reference count for a form (called when user selects a form in @ mention)."""
    _track_form_ref(table.strip())
    _cache["ts"] = 0.0
    return {"tracked": True, "table": table}


def _add_segments(items: list[dict]) -> list[dict]:
    """用 jieba 分词，给每条表单加上 segments 字段（长度>=2的词）。"""
    for it in items:
        name = it.get("chinese_name") or ""
        if name:
            it["segments"] = [w for w in jieba.lcut(name) if len(w) >= 2]
        else:
            it["segments"] = []
    return items


@router.get("/")

async def list_forms():
    """返回三类单据: builtin(系统内置表) / workflow(流程表单) / modeled(建模表单)"""
    now = time.time()
    if _cache["data"] is None or now - _cache["ts"] > _TTL:
        refs = _get_ref_counts()
        ds_list = _datasource_tables()
        for ds in ds_list:
            _sort_by_ref(ds["tables"], refs)
        _cache["data"] = {
            "builtin": _add_segments(_sort_by_ref(_builtin_tables(), refs)),
            "workflow": _add_segments(_sort_by_ref(_custom_forms(workflow=True), refs)),
            "modeled": _add_segments(_sort_by_ref(_custom_forms(workflow=False), refs)),
            "datasources": ds_list,
        }
        _cache["ts"] = now
    return _cache["data"]
