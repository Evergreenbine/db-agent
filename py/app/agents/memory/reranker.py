"""副 agent - 本地小模型重排序模块

用 Ollama 本地运行的 Qwen2.5-1.5b 对 Mem0 召回的记忆做二次过滤，
剔除向量相似但不语义相关的结果，只保留真正相关的记忆。

架构：主 agent（API 大模型）负责推理，副 agent（本地小模型）负责过滤。
"""

import json
import logging
import os
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger("reranker")

_OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
_RERANKER_MODEL = os.environ.get("RERANKER_MODEL", "qwen2.5:3b")
_TIMEOUT = 30  # 秒，小模型做分类任务应该很快


def _call_ollama(messages: list[dict], timeout: int = _TIMEOUT) -> str | None:
    """调用 Ollama chat API，返回模型生成的文本。失败返回 None。"""
    payload = json.dumps({
        "model": _RERANKER_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 200},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{_OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        logger.warning("Ollama 不可用（%s），跳过重排序", e)
        return None
    except Exception as e:
        logger.warning("重排序调用失败: %s", e)
        return None


def _parse_indices(text: str, count: int) -> list[int]:
    """从模型输出中解析相关记忆的编号（1-based）。"""
    if not text:
        return []

    text = text.strip()

    # 处理"无"或"none"等否定回答
    low = text.lower()
    if low in ("无", "none", "n/a", "空", ""):
        return []

    indices: list[int] = []
    # 尝试提取所有数字
    for token in text.replace("，", ",").replace("、", ",").split(","):
        token = token.strip()
        # 去掉常见前缀如"记忆"、"编号"等
        digits = ""
        for ch in token:
            if ch.isdigit():
                digits += ch
        if digits:
            idx = int(digits)
            if 1 <= idx <= count:
                indices.append(idx)

    return indices


def rerank_memories(
    query: str,
    memories: list[dict[str, Any]],
    keep_all_on_fail: bool = True,
) -> list[dict[str, Any]]:
    """用本地小模型对 Mem0 召回的记忆做二次过滤。

    Args:
        query: 用户的查询/问题
        memories: Mem0 返回的记忆列表，每条至少有 "memory" 和 "score" 字段
        keep_all_on_fail: Ollama 不可用时是否保留全部结果（True=降级为不过滤）

    Returns:
        过滤后的记忆列表（按模型判断的相关性排序，不相关的被剔除）
    """
    if not memories:
        return []

    if len(memories) == 1:
        return memories

    # 构建提示词
    lines = []
    for i, m in enumerate(memories, 1):
        text = str(m.get("memory", ""))[:300]  # 截断过长的记忆
        lines.append(f"记忆{i}：{text}")

    memories_text = "\n".join(lines)

    system_prompt = (
        "你是记忆过滤助手。判断每条记忆是否与用户问题直接相关。\n"
        "\n"
        "规则：\n"
        "- 相关：记忆直接回答用户问题，或讨论同一张表/同一个业务\n"
        "- 无关：记忆讨论的是不同的表、不同的业务、不同的话题\n"
        "\n"
        "示例1：\n"
        "问题：加班单的加班类型字段在哪\n"
        "记忆1：加班申请formtable_main_171的加班类型classno推送到kq_overtime\n"
        "记忆2：请假申请单formtable_main_238推送kq_leave\n"
        "记忆3：检测委托单cbzx来源表UF_CBZXNBDDH\n"
        "答案：1\n"
        "\n"
        "示例2：\n"
        "问题：请假单审批后推送到哪个表\n"
        "记忆1：请假申请单formtable_main_238 djzt=2时推送kq_leave\n"
        "记忆2：kq_leave通过requestid关联workflow_request\n"
        "记忆3：出差外勤表报销金额bxje关联报账表\n"
        "答案：1,2\n"
        "\n"
        "只返回相关记忆编号，逗号分隔。都不相关回复无。不要解释。"
    )

    user_prompt = f"用户问题：{query}\n\n{memories_text}\n\n相关记忆编号："

    result = _call_ollama([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    if result is None:
        # Ollama 不可用，降级
        logger.info("Ollama 不可用，降级为不过滤（返回全部 %d 条）", len(memories))
        return memories if keep_all_on_fail else []

    indices = _parse_indices(result, len(memories))

    if not indices:
        logger.info("重排序结果：全部 %d 条被认为不相关", len(memories))
        return memories if keep_all_on_fail else []

    # 按模型判断的相关性排序（相关的在前，保持原顺序）
    filtered = []
    remaining = []
    for i, m in enumerate(memories, 1):
        if i in indices:
            filtered.append(m)
        else:
            remaining.append(m)

    logger.info(
        "重排序完成：%d 条 -> %d 条（模型输出: %s）",
        len(memories), len(filtered), result[:80],
    )

    return filtered


def is_available() -> bool:
    """检查 Ollama 服务和重排序模型是否可用。"""
    try:
        req = urllib.request.Request(
            f"{_OLLAMA_URL}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(_RERANKER_MODEL in name for name in models)
    except Exception:
        return False
