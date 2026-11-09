"""数据字典 RAG - 解析 e-cology 数据字典 HTML -> Qdrant(db_schema) + SQLite 缓存

提供: build_schema_index / search_schema / get_table_detail / list_modules
供 @tool 包装与 db_agent 调用。自定义表单(流程表单)不在此字典内，用 resolve_form 解析。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from pathlib import Path

from bs4 import BeautifulSoup

from app.agents.rag.embeddings import embed, embed_batch
from app.agents.rag.store import get_client

logger = logging.getLogger(__name__)

SCHEMA_COLLECTION = "db_schema"
VECTOR_SIZE = 512  # bge-small-zh-v1.5
_EMBED_CHUNK = 64

SQLITE_PATH = Path(__file__).resolve().parent / "db_schema.sqlite"
DICT_DEFAULT = os.environ.get("ECOLOGY_DICT_DIR", r"D:\doc\ecology\数据库完整包 (1)")

# 字段表列序
_FIELD_COLS = ["序号", "数据库列名", "中文名称", "数据类型", "长度",
               "是否允许空值", "是否为外键", "是否自增长", "默认值", "说明"]


def _parse_html(path: Path) -> dict | None:
    try:
        html = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        logger.debug("读取失败 %s: %s", path, e)
        return None
    soup = BeautifulSoup(html, "lxml")
    cells = [td.get_text(strip=True) for td in soup.find_all("td")]

    def _val(label: str) -> str:
        try:
            i = cells.index(label)
        except ValueError:
            return ""
        for c in cells[i + 1: i + 4]:
            if c and c not in _FIELD_COLS:
                return c
        return ""

    table = _val("数据库表名").lower()
    chinese = _val("中文名称")
    module = _val("所属模块")
    pk = _val("主键")
    desc = _val("说明")

    # 文件名兜底: fileclean(附件清理表).html
    if not table or not chinese:
        stem = path.stem
        if "(" in stem and stem.endswith(")"):
            left, _, right = stem.partition("(")
            if not table:
                table = left.strip().lower()
            if not chinese:
                chinese = right.rstrip(")").strip()
    if not module:
        module = path.parent.name

    # 字段: 数据行 = 含 td.contentTd.td 且首列为序号
    fields: list[dict] = []
    for tr in soup.select("tr"):
        tds = tr.select("td.contentTd.td")
        if len(tds) < 3:
            continue
        vals = [td.get_text(strip=True) for td in tds]
        if not (vals[0] and vals[0].isdigit()):
            continue
        def _g(i):
            return vals[i] if i < len(vals) else ""
        fields.append({
            "name": _g(1),
            "chinese_name": _g(2),
            "data_type": _g(3),
            "length": _g(4),
            "nullable": _g(5),
            "is_fk": _g(6),
            "is_auto": _g(7),
            "default": _g(8),
            "comment": _g(9),
        })

    if not table:
        return None
    field_summary = " ".join(
        f.get("chinese_name") or f.get("name") or ""
        for f in fields if f.get("chinese_name") or f.get("name")
    )
    return {
        "table": table,
        "chinese_name": chinese,
        "module": module,
        "pk": pk,
        "description": desc,
        "fields": fields,
        "field_summary": field_summary,
    }


def _embed_text(d: dict) -> str:
    return " ".join(filter(None, [
        d.get("chinese_name", ""), d.get("module", ""), d.get("table", ""),
        d.get("description", ""), "字段:", d.get("field_summary", ""),
    ]))


def _ensure_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tables (
            table_name TEXT PRIMARY KEY,
            chinese_name TEXT,
            module TEXT,
            pk TEXT,
            description TEXT,
            field_count INTEGER,
            field_summary TEXT,
            fields_json TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_module ON tables(module)")
    conn.commit()
    return conn


def build_schema_index(dict_dir: str | None = None, force: bool = False) -> dict:
    """全量解析数据字典 -> 写 SQLite + Qdrant(若空或 force)"""
    base = Path(dict_dir or DICT_DEFAULT)
    html_files = sorted(base.rglob("*.html"))
    if not html_files:
        return {"tables": 0, "modules": 0, "errors": 1, "detail": f"未找到 HTML: {base}"}

    docs: dict[str, dict] = {}
    errors = 0
    for i, fp in enumerate(html_files, 1):
        d = _parse_html(fp)
        if d is None or not d.get("table"):
            errors += 1
            continue
        if d["table"] in docs:  # 去重(同名表保留首现)
            continue
        docs[d["table"]] = d
        if i % 500 == 0:
            logger.info("已解析 %d/%d", i, len(html_files))

    # --- SQLite ---
    conn = _ensure_sqlite()
    conn.execute("DELETE FROM tables")
    rows = []
    for d in docs.values():
        rows.append((
            d["table"], d["chinese_name"], d["module"], d["pk"], d["description"],
            len(d["fields"]), d["field_summary"], json.dumps(d["fields"], ensure_ascii=False),
        ))
    conn.executemany(
        "INSERT OR REPLACE INTO tables VALUES (?,?,?,?,?,?,?,?)", rows
    )
    conn.commit()

    modules = {}
    for d in docs.values():
        modules[d["module"]] = modules.get(d["module"], 0) + 1

    # --- Qdrant ---
    upserted = _ensure_qdrant(list(docs.values()), force=force)

    conn.close()
    return {
        "tables": len(docs),
        "modules": len(modules),
        "errors": errors,
        "qdrant_upserted": upserted,
    }


def _ensure_qdrant(docs: list[dict], force: bool = False) -> int:
    client = get_client()
    names = [c.name for c in client.get_collections().collections]
    if SCHEMA_COLLECTION not in names:
        from qdrant_client.models import VectorParams, Distance
        client.create_collection(
            collection_name=SCHEMA_COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )

    existing = client.count(collection_name=SCHEMA_COLLECTION, exact=True).count
    if existing and existing >= len(docs) and not force:
        return 0  # 已索引，跳过

    from qdrant_client.models import PointStruct
    texts = [_embed_text(d) for d in docs]
    total = 0
    for i in range(0, len(texts), _EMBED_CHUNK):
        chunk = texts[i: i + _EMBED_CHUNK]
        embs = embed_batch(chunk)
        points = []
        for d, emb in zip(docs[i: i + _EMBED_CHUNK], embs):
            points.append(PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, d["table"])),
                vector=emb,
                payload={
                    "table": d["table"],
                    "chinese_name": d["chinese_name"],
                    "module": d["module"],
                    "pk": d["pk"],
                    "description": d["description"],
                    "field_count": len(d["fields"]),
                    "field_summary": d["field_summary"][:2000],
                },
            ))
        client.upsert(collection_name=SCHEMA_COLLECTION, points=points)
        total += len(points)
        logger.info("Qdrant upsert %d/%d", total, len(docs))
    return total


def ensure_schema_index() -> None:
    """启动时调用: SQLite 缺失则建; Qdrant 空则建。幂等。"""
    if not SQLITE_PATH.exists() or _sqlite_row_count() == 0:
        build_schema_index()
    else:
        # SQLite 已有，仅确保 Qdrant collection 存在(空则补)
        _ensure_qdrant([], force=False)


def _sqlite_row_count() -> int:
    conn = _ensure_sqlite()
    n = conn.execute("SELECT count(*) FROM tables").fetchone()[0]
    conn.close()
    return n


def search_schema(query: str, module: str | None = None, top_k: int = 8) -> list[dict]:
    """向量检索相关表; module 过滤; 返回表名/中文名/模块/主键/字段摘要/分数"""
    client = get_client()
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    qf = None
    if module:
        qf = Filter(must=[FieldCondition(key="module", match=MatchValue(value=module))])
    try:
        res = client.query_points(
            collection_name=SCHEMA_COLLECTION,
            query=embed(query),
            limit=top_k,
            query_filter=qf,
        ).points
    except Exception as e:  # noqa: BLE001
        return [{"error": "SEARCH_FAILED", "detail": f"{type(e).__name__}: {e}"}]
    out = []
    for r in res:
        p = r.payload or {}
        out.append({
            "table": p.get("table"),
            "chinese_name": p.get("chinese_name"),
            "module": p.get("module"),
            "pk": p.get("pk"),
            "field_count": p.get("field_count"),
            "field_summary": p.get("field_summary"),
            "score": round(float(r.score), 4) if r.score is not None else None,
        })
    return out


def get_table_detail(table: str) -> dict:
    """从 SQLite 缓存取单表完整字段"""
    conn = _ensure_sqlite()
    row = conn.execute(
        "SELECT table_name, chinese_name, module, pk, description, field_count, field_summary, fields_json "
        "FROM tables WHERE table_name = ?", (table.lower().strip(),)
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "NOT_FOUND", "detail": f"字典中无此表: {table}", "table": table}
    fields = []
    try:
        fields = json.loads(row[7] or "[]")
    except json.JSONDecodeError:
        fields = []
    return {
        "table": row[0],
        "chinese_name": row[1],
        "module": row[2],
        "pk": row[3],
        "description": row[4],
        "field_count": row[5],
        "field_summary": row[6],
        "fields": fields,
    }


def list_modules() -> list[dict]:
    """列出所有模块及表数"""
    conn = _ensure_sqlite()
    rows = conn.execute(
        "SELECT module, count(*) c FROM tables GROUP BY module ORDER BY c DESC, module"
    ).fetchall()
    conn.close()
    return [{"module": m, "table_count": c} for m, c in rows]


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        r = build_schema_index(force="--force" in sys.argv)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif cmd == "search":
        q = sys.argv[2] if len(sys.argv) > 2 else "部门"
        print(json.dumps(search_schema(q), ensure_ascii=False, indent=2))
    elif cmd == "modules":
        print(json.dumps(list_modules(), ensure_ascii=False, indent=2))
    elif cmd == "detail":
        t = sys.argv[2] if len(sys.argv) > 2 else "hrmdepartment"
        print(json.dumps(get_table_detail(t), ensure_ascii=False, indent=2))
    else:
        print("usage: python -m app.agents.rag.schema_store [build|search q|modules|detail t]")
