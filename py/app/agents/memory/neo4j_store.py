"""Neo4j 表关系图存储 - 结构化管理表与表的关联关系"""

import logging
from datetime import datetime
from functools import lru_cache
from typing import Any
import os


logger = logging.getLogger("neo4j_store")

_NEO4J_URI = "bolt://localhost:7687"
_NEO4J_USER = "neo4j"
_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")


@lru_cache(maxsize=1)
def get_driver():
    """获取 Neo4j driver（单例）"""
    driver = GraphDatabase.driver(_NEO4J_URI, auth=(_NEO4J_USER, _NEO4J_PASSWORD))
    try:
        driver.verify_connectivity()
        logger.info("Neo4j connected: %s", _NEO4J_URI)
    except Exception as e:
        logger.error("Neo4j connection failed: %s", e)
        raise
    return driver


def save_table_relation(
    source_table: str,
    source_field: str,
    target_table: str,
    target_field: str,
    relation_type: str = "join",
    description: str = "",
    source: str = "agent",
):
    """保存表关系（upsert）。如果关系已存在，confidence+1。"""
    driver = get_driver()
    query = """
    MERGE (a:Table {name: $src_table})
    MERGE (b:Table {name: $tgt_table})
    MERGE (a)-[r:RELATES_TO {
        source_field: $src_field,
        target_field: $tgt_field,
        relation_type: $rel_type
    }]->(b)
    ON CREATE SET r.confidence = 1, r.description = $desc, r.source = $source, r.created_at = $ts
    ON MATCH SET r.confidence = r.confidence + 1, r.updated_at = $ts
    RETURN r.confidence AS confidence
    """
    with driver.session() as session:
        result = session.run(query, {
            "src_table": source_table.upper(),
            "src_field": source_field.lower(),
            "tgt_table": target_table.upper(),
            "tgt_field": target_field.lower(),
            "rel_type": relation_type,
            "desc": description,
            "source": source,
            "ts": datetime.now().isoformat(),
        })
        record = result.single()
        conf = record["confidence"] if record else 0
        logger.info("Table relation saved: %s.%s -> %s.%s (%s, conf=%d)",
                     source_table, source_field, target_table, target_field, relation_type, conf)
        return {"saved": True, "confidence": conf}


def query_table_relations(table_name: str, max_depth: int = 2) -> list[dict[str, Any]]:
    """查询与某张表关联的所有表关系（多跳展开）。"""
    driver = get_driver()
    query = """
    MATCH path = (a:Table {name: $table})-[:RELATES_TO*1..%d]-(b:Table)
    WITH path, relationships(path) AS rels, nodes(path) AS tables
    UNWIND range(0, size(rels)-1) AS idx
    RETURN
      tables[idx].name AS source_table,
      rels[idx].source_field AS source_field,
      tables[idx+1].name AS target_table,
      rels[idx].target_field AS target_field,
      rels[idx].relation_type AS relation_type,
      rels[idx].description AS description,
      rels[idx].confidence AS confidence,
      idx+1 AS depth
    ORDER BY depth, confidence DESC
    """ % max_depth

    with driver.session() as session:
        result = session.run(query, {"table": table_name.upper()})
        relations = []
        seen = set()
        for record in result:
            key = f"{record['source_table']}.{record['source_field']}->{record['target_table']}.{record['target_field']}"
            if key not in seen:
                seen.add(key)
                relations.append({
                    "source_table": record["source_table"],
                    "source_field": record["source_field"],
                    "target_table": record["target_table"],
                    "target_field": record["target_field"],
                    "relation_type": record["relation_type"],
                    "description": record["description"],
                    "confidence": record["confidence"],
                    "depth": record["depth"],
                })
        return relations


def save_form_meta(form_name: str, table_name: str, workflow_id: str = "",
                   detail_tables: list[str] | None = None):
    """保存表单元信息（表单名 -> 主表 -> 流程编号 -> 明细表）"""
    driver = get_driver()
    with driver.session() as session:
        session.run("""
            MERGE (t:Table {name: $table})
            SET t.form_name = $form_name, t.workflow_id = $wid, t.is_form_main = true,
                t.updated_at = $ts
        """, {
            "table": table_name.upper(),
            "form_name": form_name,
            "wid": workflow_id,
            "ts": datetime.now().isoformat(),
        })
        for dt in (detail_tables or []):
            session.run("""
                MERGE (main:Table {name: $main_table})
                MERGE (dt:Table {name: $dt_table})
                SET dt.is_form_detail = true
                MERGE (main)-[r:HAS_DETAIL]->(dt)
                ON CREATE SET r.confidence = 1, r.created_at = $ts
                ON MATCH SET r.confidence = r.confidence + 1
            """, {
                "main_table": table_name.upper(),
                "dt_table": dt.upper(),
                "ts": datetime.now().isoformat(),
            })
    logger.info("Form meta saved: %s -> %s (workflow=%s, details=%s)",
                form_name, table_name, workflow_id, detail_tables)



def increment_form_search(table_name: str):
    """Increment search_count on a Table node (track retrieval frequency)."""
    driver = get_driver()
    with driver.session() as session:
        session.run("""
            MERGE (t:Table {name: $table})
            ON CREATE SET t.search_count = 1
            ON MATCH SET t.search_count = coalesce(t.search_count, 0) + 1
            SET t.last_searched = $ts
        """, {
            "table": table_name.upper(),
            "ts": datetime.now().isoformat(),
        })
    logger.info("Form search count incremented: %s", table_name)


def get_form_search_counts(table_names: list[str]) -> dict[str, int]:
    """Get search counts for multiple tables. Returns {TABLE_NAME: count}."""
    if not table_names:
        return {}
    driver = get_driver()
    upper_names = [t.upper() for t in table_names]
    with driver.session() as session:
        result = session.run("""
            MATCH (t:Table) WHERE t.name IN $names
            RETURN t.name AS name, coalesce(t.search_count, 0) AS cnt
        """, {"names": upper_names})
        return {record["name"]: record["cnt"] for record in result}


def query_form_meta(table_name: str) -> dict[str, Any] | None:
    """查询表单元信息"""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""
            MATCH (t:Table {name: $table})
            OPTIONAL MATCH (t)-[:HAS_DETAIL]->(dt:Table)
            RETURN t.form_name AS form_name,
                   t.workflow_id AS workflow_id,
                   t.is_form_main AS is_main,
                   collect(dt.name) AS detail_tables
        """, {"table": table_name.upper()})
        record = result.single()
        if record and record["form_name"]:
            return {
                "form_name": record["form_name"],
                "workflow_id": record["workflow_id"],
                "detail_tables": [d for d in record["detail_tables"] if d],
            }
        return None

