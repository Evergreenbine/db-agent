"""本地 Embedding 模型封装 - 使用 BAAI/bge-small-zh-v1.5 (512维)

模型已缓存在 ~/.cache/huggingface/，启动时从本地加载。
首次下载需代理，可手动设置: HF_ENDPOINT=https://hf-mirror.com HTTPS_PROXY=http://127.0.0.1:7892
"""

import os

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    return _model


def embed(text: str) -> list[float]:
    """将文本转为向量"""
    return _get_model().encode(text).tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """批量向量化"""
    return _get_model().encode(texts).tolist()
