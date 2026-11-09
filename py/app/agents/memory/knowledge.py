"""知识库统一入口 - Mem0(语义记忆) + Neo4j(表关系图)

工具:
- query_knowledge: agent 主动查知识库（语义搜索 + 图关系展开）
- save_knowledge: agent 主动沉淀知识

内部函数:
- inject_knowledge: 请求入口被动注入（关键词匹配 + 去重）
- forced_deposit_form: resolve_form 后强制沉淀表单元信息
- forced_deposit_relation: execute_write 后强制沉淀表关系
"""

import json
import logging
import re
from typing import Any

from app.agents.tools.registry import tool
from app.agents.memory.mem0_config import get_memory
from app.agents.memory.reranker import rerank_memories, is_available as reranker_available
from app.agents.memory.neo4j_store import (
    save_table_relation,
    query_table_relations,
    save_form_meta,
    query_form_meta,
)

logger = logging.getLogger("knowledge")

# 表名匹配正则（formtable_main_XXX, formtable_main_XXX_dtY, 等）
_TABLE_RE = re.compile(r"(formtable_main_\w+|hrmresource|kq_leave|workflow_base)", re.IGNORECASE)


# ===== agent 工具 =====

@tool
def query_knowledge(purpose: str, query: str, knowledge_type: str = "") -> str:
    """查业务知识库。不确定表关系/字段用途/流程编号/业务操作时先查这里。

    purpose: 【必填】为什么查（一句中文）
    query: 【必填】搜索关键词或自然语言描述，如"请假单推送后人事库有什么记录"
    knowledge_type: 可选，限定类型：table_relation|form_meta|field_usage|business_rule|unnamed_detail|execution_experience

    返回: JSON 字符串，包含语义搜索结果（Mem0）+ 表关系图（Neo4j 多跳展开）。
    """
    results: dict[str, Any] = {"purpose": purpose}

    # 1. Mem0 语义搜索
    try:
        mem = get_memory()
        # 用 employee_id 隔离？不——业务知识是全局共享的，用固定 user_id
        query_tables = _TABLE_RE.findall(query)
        resp = mem.search(query, filters={"user_id": "business_shared"}, top_k=10, threshold=0.5)
        mem_list = resp.get("results", []) if isinstance(resp, dict) else (resp or [])
        # Post-filter: filter out memories about unrelated tables
        if query_tables and mem_list:
            tbl_set = set(tb.lower() for tb in query_tables)
            filtered = []
            for m in mem_list:
                if not isinstance(m, dict): continue
                meta = m.get("metadata") or {}
                mem_tbls = meta.get("tables") or []
                if isinstance(mem_tbls, list) and mem_tbls:
                    if set(str(tb).lower() for tb in mem_tbls) & tbl_set:
                        filtered.append(m)
                else:
                    filtered.append(m)
            if filtered: mem_list = filtered
        if mem_list:
            # 副 agent（本地小模型）二次过滤不相关记忆
            semantic_items = [
                {"memory": m.get("memory", ""), "score": m.get("score", 0)}
                for m in mem_list if isinstance(m, dict)
            ]
            if reranker_available():
                semantic_items = rerank_memories(query, semantic_items)
            if semantic_items:
                results["semantic"] = semantic_items
    except Exception as e:
        logger.warning("Mem0 search failed: %s", e)
        results["semantic_error"] = str(e)

    # 2. Neo4j 图关系展开（从 query 中提取表名）
    tables = _TABLE_RE.findall(query)
    if tables:
        all_relations = []
        for tbl in set(tables):
            try:
                rels = query_table_relations(tbl, max_depth=2)
                all_relations.extend(rels)
            except Exception as e:
                logger.warning("Neo4j query failed for %s: %s", tbl, e)

        if all_relations:
            results["table_relations"] = all_relations

        # 查表单元信息
        for tbl in set(tables):
            try:
                meta = query_form_meta(tbl)
                if meta:
                    results.setdefault("form_meta", []).append({"table": tbl.upper(), **meta})
            except Exception:
                pass

    if not results.get("semantic") and not results.get("table_relations") and not results.get("form_meta"):
        results["empty"] = True
        results["message"] = "知识库中未找到相关知识。如果是新的表关系或业务规则，可以用 save_knowledge 沉淀。"

    return json.dumps(results, ensure_ascii=False, default=str)


@tool
def save_knowledge(
    purpose: str,
    knowledge_type: str,
    title: str,
    content: str,
    keywords: str = "",
    source_tables: str = "",
) -> str:
    """沉淀业务知识到知识库。发现新的表关系/字段用途/业务模式时调用。

    purpose: 【必填】为什么沉淀（一句中文）
    knowledge_type: 【必填】类型：table_relation|form_meta|field_usage|business_rule|unnamed_detail|execution_experience
    title: 【必填】标题，如"请假单与kq_leave的关联关系"
    content: 【必填】详细内容（markdown）。如果是 table_relation，格式为"源表.字段 -> 目标表.字段 (关系类型)"
    keywords: 可选，逗号分隔的关键词，用于被动注入匹配（如"请假单,kq_leave,formtable_main_238"）
    source_tables: 可选，涉及的表名，逗号分隔（如"formtable_main_238,kq_leave"）

    返回: JSON 字符串，保存结果。
    """
    result: dict[str, Any] = {"purpose": purpose, "type": knowledge_type, "title": title}

    # 1. 存 Mem0（所有类型都存语义记忆）
    try:
        mem = get_memory()
        messages = [
            {"role": "user", "content": f"请记住以下业务知识:\n标题: {title}\n类型: {knowledge_type}\n内容: {content}\n关键词: {keywords}"},
            {"role": "assistant", "content": f"已记录: {title}"},
        ]
        metadata = {"type": knowledge_type, "title": title}
        if source_tables:
            metadata["tables"] = [t.strip() for t in source_tables.split(",")]
        if keywords:
            metadata["keywords"] = keywords

        mem.add(messages, user_id="business_shared", metadata=metadata)
        result["mem0_saved"] = True
    except Exception as e:
        logger.warning("Mem0 save failed: %s", e)
        result["mem0_error"] = str(e)

    # 2. 如果是 table_relation，同时存 Neo4j 图
    if knowledge_type == "table_relation":
        try:
            # 解析 content: "源表.字段 -> 目标表.字段 (关系类型)"
            m = re.match(
                r"(\w+)\.(\w+)\s*->\s*(\w+)\.(\w+)\s*(?:\(([^)]+)\))?",
                content.strip(),
            )
            if m:
                save_table_relation(
                    source_table=m.group(1),
                    source_field=m.group(2),
                    target_table=m.group(3),
                    target_field=m.group(4),
                    relation_type=m.group(5) or "join",
                    description=title,
                    source="agent",
                )
                result["neo4j_saved"] = True
            else:
                result["neo4j_error"] = "content 格式不符合 '源表.字段 -> 目标表.字段 (关系类型)'"
        except Exception as e:
            logger.warning("Neo4j save failed: %s", e)
            result["neo4j_error"] = str(e)

    # 3. 如果是 form_meta，同时存 Neo4j
    if knowledge_type == "form_meta":
        try:
            tables = [t.strip() for t in source_tables.split(",") if t.strip()]
            main_table = tables[0] if tables else ""
            detail_tables = tables[1:] if len(tables) > 1 else []
            workflow_id = ""
            wf_match = re.search(r"workflow[_ ]?id[=: ]+(\w+)", content, re.IGNORECASE)
            if wf_match:
                workflow_id = wf_match.group(1)
            save_form_meta(title, main_table, workflow_id, detail_tables)
            result["neo4j_saved"] = True
        except Exception as e:
            logger.warning("Neo4j form_meta save failed: %s", e)
            result["neo4j_error"] = str(e)

    result["saved"] = result.get("mem0_saved") or result.get("neo4j_saved", False)
    return json.dumps(result, ensure_ascii=False, default=str)


# ===== 被动注入（请求入口调用）=====

def inject_knowledge(user_input: str, session_id: str = "", employee_id: str = "") -> str:
    """从用户输入中提取关键词，查知识库，返回注入到 system prompt 的知识块。

    同一 session 内去重（避免反复注入）。
    """
    if not user_input:
        return ""

    # 提取表名
    tables = _TABLE_RE.findall(user_input)
    if not tables:
        return ""

    lines: list[str] = []
    injected_keys: set[str] = set()

    # 1. 查 Neo4j 表关系
    for tbl in set(tables):
        try:
            rels = query_table_relations(tbl, max_depth=2)
            if rels:
                lines.append(f"【已知表关系 - {tbl.upper()}】")
                for r in rels[:5]:  # 最多 5 条
                    key = f"rel:{r['source_table']}.{r['source_field']}->{r['target_table']}.{r['target_field']}"
                    if key not in injected_keys:
                        injected_keys.add(key)
                        lines.append(
                            f"  {r['source_table']}.{r['source_field']} -> "
                            f"{r['target_table']}.{r['target_field']} ({r['relation_type']})"
                            + (f" [{r['description']}]" if r.get("description") else "")
                        )

            # 查表单元信息
            meta = query_form_meta(tbl)
            if meta:
                lines.append(f"【表单元信息 - {tbl.upper()}】")
                lines.append(f"  中文名: {meta['form_name']}")
                if meta.get("workflow_id"):
                    lines.append(f"  流程编号: {meta['workflow_id']}")
                if meta.get("detail_tables"):
                    lines.append(f"  明细表: {', '.join(meta['detail_tables'])}")
        except Exception as e:
            logger.debug("Neo4j inject failed for %s: %s", tbl, e)

    # 2. 查 Mem0 语义记忆（用用户原文搜索）
    try:
        mem = get_memory()
        resp = mem.search(user_input, filters={"user_id": "business_shared"}, top_k=5, threshold=0.5)
        mem_list = resp.get("results", []) if isinstance(resp, dict) else (resp or [])
        # 副 agent 二次过滤
        if mem_list and reranker_available():
            mem_list = rerank_memories(user_input, [
                {"memory": m.get("memory", ""), "score": m.get("score", 0)}
                for m in mem_list if isinstance(m, dict)
            ])
        if mem_list:
            lines.append("【业务知识】")
            for m in mem_list:
                if not isinstance(m, dict):
                    continue
                text = m.get("memory", "")
                key = f"mem0:{text[:50]}"
                if key not in injected_keys:
                    injected_keys.add(key)
                    lines.append(f"  - {text}")
    except Exception as e:
        logger.debug("Mem0 inject failed: %s", e)

    if not lines:
        return ""

    return "\n".join(lines)


# ===== 强制沉淀 hooks =====

def forced_deposit_form(form_name: str, table_name: str, workflow_id: str = "",
                         detail_tables: list[dict] | None = None):
    """resolve_form 返回后调用，强制沉淀表单元信息。"""
    try:
        dt_names = []
        for dt in (detail_tables or []):
            if isinstance(dt, dict):
                dt_names.append(dt.get("detail_table") or dt.get("name") or "")
            elif isinstance(dt, str):
                dt_names.append(dt)
        dt_names = [d for d in dt_names if d]

        save_form_meta(form_name, table_name, workflow_id, dt_names)
        logger.info("Forced deposit form_meta: %s -> %s", form_name, table_name)
    except Exception as e:
        logger.warning("Forced deposit form failed: %s", e)


def forced_deposit_relation(source_table: str, source_field: str,
                             target_table: str, target_field: str,
                             relation_type: str = "join", description: str = ""):
    """execute_write 跨表 SQL 后调用，强制沉淀表关系。"""
    try:
        save_table_relation(
            source_table=source_table,
            source_field=source_field,
            target_table=target_table,
            target_field=target_field,
            relation_type=relation_type,
            description=description,
            source="system_forced",
        )
        logger.info("Forced deposit relation: %s.%s -> %s.%s",
                     source_table, source_field, target_table, target_field)
    except Exception as e:
        logger.warning("Forced deposit relation failed: %s", e)
