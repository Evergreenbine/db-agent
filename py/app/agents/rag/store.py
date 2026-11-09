"""Qdrant 向量库 - 从 SKILL.md 文件索引与检索工具（支持 embedded / server 模式）"""

import os
import uuid
import logging
import yaml
from pathlib import Path

from app.agents.rag.embeddings import embed, embed_batch

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)

_COLLECTION = "oa_functions"
_VECTOR_SIZE = 512  # bge-small-zh-v1.5

# 优先用 server 模式（QDRANT_HOST 设置了就用），否则 embedded
_qdrant_host = os.environ.get("QDRANT_HOST", "")
_qdrant_port = int(os.environ.get("QDRANT_PORT", "6333"))

if _qdrant_host:
    _client = QdrantClient(host=_qdrant_host, port=_qdrant_port)
    logger.info("[Qdrant] server mode: %s:%d", _qdrant_host, _qdrant_port)
else:
    _client = QdrantClient(path=os.environ.get("QDRANT_PATH", ".qdrant_data"))
    logger.info("[Qdrant] embedded mode: %s", os.environ.get("QDRANT_PATH", ".qdrant_data"))

_collections = _client.get_collections()
if _COLLECTION not in [c.name for c in _collections.collections]:
    _client.create_collection(
        collection_name=_COLLECTION,
        vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
    )

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"

_title_cache: dict[str, str] | None = None


def _tool_to_uuid(tool_name: str) -> str:
    """工具名转确定性 UUID（Qdrant 要求 UUID 或整数 ID）"""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, tool_name))


def parse_skill_md(file_path: Path) -> dict | None:
    """解析 SKILL.md：YAML frontmatter + Markdown 正文"""
    text = file_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    meta = yaml.safe_load(parts[1])
    body = parts[2].strip()
    return {
        "tool": meta.get("tool", file_path.stem),
        "title": meta.get("title", ""),
        "keywords": meta.get("keywords", ""),
        "module": meta.get("module", "default"),
        "body": body,
    }


def build_index() -> int:
    """扫描 skills/*.md，解析后索引到 Qdrant（upsert 幂等）"""
    docs = []
    for md_file in sorted(_SKILLS_DIR.glob("*.md")):
        parsed = parse_skill_md(md_file)
        if parsed is None:
            continue
        embed_text = f"{parsed['keywords']} {parsed['title']}\n{parsed['body']}"
        docs.append({
            "id": parsed["tool"],
            "text": embed_text,
            "meta": {
                "tool": parsed["tool"],
                "title": parsed["title"],
                "module": parsed["module"],
            },
        })

    if not docs:
        return 0

    embeddings = embed_batch([d["text"] for d in docs])
    points = [
        PointStruct(
            id=_tool_to_uuid(d["id"]),
            vector=emb,
            payload=d["meta"],
        )
        for d, emb in zip(docs, embeddings)
    ]
    _client.upsert(collection_name=_COLLECTION, points=points)
    return len(docs)


def retrieve(query: str, top_k: int = 5, module: str | None = None) -> list[str]:
    """检索相关工具名，可选按 module 过滤"""
    query_filter = None
    if module:
        query_filter = Filter(
            must=[FieldCondition(key="module", match=MatchValue(value=module))]
        )

    results = _client.query_points(
        collection_name=_COLLECTION,
        query=embed(query),
        limit=top_k,
        query_filter=query_filter,
    ).points
    return [r.payload["tool"] for r in results if r.payload]


def get_index_count() -> int:
    result = _client.count(collection_name=_COLLECTION)
    return result.count


_FALLBACK_TITLES = {
    "run_sql": "查询数据",
    "resolve_form": "解析表单",
    "search_schema": "检索表结构",
    "get_table_detail": "查看表详情",
    "list_modules": "列出模块",
    "execute_write": "数据变更预览",
    "query_knowledge": "查询知识库",
    "save_knowledge": "保存知识",
}


def get_tool_title(name: str) -> str:
    """工具名 -> SKILL.md 业务标题（供前端展示），缺失回退中文映射"""
    global _title_cache
    if _title_cache is None:
        _title_cache = {}
        for md_file in sorted(_SKILLS_DIR.glob("*.md")):
            parsed = parse_skill_md(md_file)
            if parsed:
                _title_cache[parsed["tool"]] = parsed["title"] or parsed["tool"]
    return _title_cache.get(name) or _FALLBACK_TITLES.get(name, name)

def get_client():
    """返回共享的 Qdrant 客户端（供 schema_store 等复用，避免多实例抢占同一 path）"""
    return _client
