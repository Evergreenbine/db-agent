"""Knowledge management API - CRUD for Mem0 + Neo4j memories."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Header

from app.agents.memory.mem0_config import get_memory
from app.agents.memory.neo4j_store import get_driver, save_table_relation, save_form_meta

logger = logging.getLogger("knowledge_api")
router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _list_mem0() -> list[dict[str, Any]]:
    try:
        mem = get_memory()
        resp = mem.get_all(filters={"user_id": "business_shared"})
        all_mems = resp.get("results", []) if isinstance(resp, dict) else (resp or [])
        items = []
        for m in all_mems:
            if isinstance(m, dict):
                items.append({
                    "id": m.get("id", ""),
                    "store": "mem0",
                    "content": m.get("memory", ""),
                    "metadata": m.get("metadata", {}),
                    "created_at": m.get("created_at", ""),
                })
        return items
    except Exception as e:
        logger.warning("list_mem0 failed: %s", e)
        return []


def _list_neo4j_relations() -> list[dict[str, Any]]:
    try:
        driver = get_driver()
        with driver.session() as s:
            result = s.run("""
                MATCH (a:Table)-[r:RELATES_TO]->(b:Table)
                RETURN a.name AS src_table, r.source_field AS src_field,
                       b.name AS tgt_table, r.target_field AS tgt_field,
                       r.relation_type AS rel_type, r.description AS desc,
                       r.confidence AS conf, r.source AS source,
                       elementId(r) AS eid
                ORDER BY src_table, tgt_table
            """)
            items = []
            for rec in result:
                items.append({
                    "id": rec["eid"],
                    "store": "neo4j_relation",
                    "src_table": rec["src_table"],
                    "src_field": rec["src_field"],
                    "tgt_table": rec["tgt_table"],
                    "tgt_field": rec["tgt_field"],
                    "relation_type": rec["rel_type"],
                    "description": rec["desc"] or "",
                    "confidence": rec["conf"],
                    "source": rec["source"] or "",
                    "content": f"{rec['src_table']}.{rec['src_field']} -> {rec['tgt_table']}.{rec['tgt_field']} ({rec['rel_type']})",
                })
            return items
    except Exception as e:
        logger.warning("list_neo4j_relations failed: %s", e)
        return []


def _list_neo4j_forms() -> list[dict[str, Any]]:
    try:
        driver = get_driver()
        with driver.session() as s:
            result = s.run("""
                MATCH (t:Table) WHERE t.form_name IS NOT NULL
                OPTIONAL MATCH (t)-[:HAS_DETAIL]->(dt:Table)
                RETURN t.name AS table, t.form_name AS form_name,
                       t.workflow_id AS wid, collect(dt.name) AS details,
                       elementId(t) AS eid
                ORDER BY t.form_name
            """)
            items = []
            for rec in result:
                details = [d for d in rec["details"] if d]
                items.append({
                    "id": rec["eid"],
                    "store": "neo4j_form",
                    "table": rec["table"],
                    "form_name": rec["form_name"],
                    "workflow_id": rec["wid"] or "",
                    "detail_tables": details,
                    "content": f"{rec['form_name']} -> {rec['table']} (workflow={rec['wid'] or '-'}, details={', '.join(details) or '-'})",
                })
            return items
    except Exception as e:
        logger.warning("list_neo4j_forms failed: %s", e)
        return []


@router.get("")
async def list_knowledge():
    return {
        "mem0": _list_mem0(),
        "neo4j_relations": _list_neo4j_relations(),
        "neo4j_forms": _list_neo4j_forms(),
    }


@router.post("")
async def add_knowledge(body: dict[str, Any]):
    store = body.get("store", "mem0")

    if store == "mem0":
        try:
            mem = get_memory()
            content = body.get("content", "")
            messages = [
                {"role": "user", "content": f"请记住: {content}"},
                {"role": "assistant", "content": "已记录"},
            ]
            metadata = body.get("metadata", {})
            result = mem.add(messages, user_id="business_shared", metadata=metadata)
            return {"ok": True, "result": str(result)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if store == "neo4j_relation":
        try:
            r = save_table_relation(
                source_table=body.get("src_table", ""),
                source_field=body.get("src_field", ""),
                target_table=body.get("tgt_table", ""),
                target_field=body.get("tgt_field", ""),
                relation_type=body.get("relation_type", "join"),
                description=body.get("description", ""),
                source="manual",
            )
            return {"ok": True, "result": r}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if store == "neo4j_form":
        try:
            details = body.get("detail_tables", [])
            if isinstance(details, str):
                details = [d.strip() for d in details.split(",") if d.strip()]
            save_form_meta(
                form_name=body.get("form_name", ""),
                table_name=body.get("table", ""),
                workflow_id=body.get("workflow_id", ""),
                detail_tables=details,
            )
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"unknown store: {store}"}


@router.delete("")
async def delete_knowledge(body: dict[str, Any]):
    store = body.get("store", "")
    kid = body.get("id", "")

    if store == "mem0":
        try:
            mem = get_memory()
            mem.delete(kid)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if store == "neo4j_relation":
        try:
            driver = get_driver()
            with driver.session() as s:
                s.run("MATCH ()-[r]->() WHERE elementId(r) = $eid DELETE r", eid=kid)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if store == "neo4j_form":
        try:
            driver = get_driver()
            with driver.session() as s:
                s.run("MATCH (t:Table) WHERE elementId(t) = $eid REMOVE t.form_name, t.workflow_id, t.is_form_main", eid=kid)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": f"unknown store: {store}"}
