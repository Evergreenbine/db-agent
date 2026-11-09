"""Mem0 long-term memory config - DeepSeek LLM + HuggingFace embedder + Qdrant vector store"""

import logging
import os
from functools import lru_cache

from mem0 import Memory

from app.config import get_settings

logger = logging.getLogger('mem0_config')
settings = get_settings()


@lru_cache(maxsize=1)
def get_memory() -> Memory:
    """Get Mem0 Memory singleton."""
    mem0_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.mem0_data')
    mem0_dir = os.path.abspath(mem0_dir)
    os.makedirs(mem0_dir, exist_ok=True)
    # Offline mode: use locally cached HuggingFace model, no network checks
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

    config = {
        'vector_store': {
            'provider': 'qdrant',
            'config': {
                'collection_name': 'business_knowledge',
                'path': mem0_dir,
                'embedding_model_dims': 512,
            },
        },
        'llm': {
            'provider': 'deepseek',
            'config': {
                'model': settings.deepseek_model,
                'api_key': settings.deepseek_api_key,
                'deepseek_base_url': settings.deepseek_base_url,
                'temperature': 0.1,
                'max_tokens': 2000,
            },
        },
        'embedder': {
            'provider': 'huggingface',
            'config': {
                'model': 'BAAI/bge-small-zh-v1.5',
            },
        },
        'history_db_path': os.path.join(mem0_dir, 'history.db'),
        'custom_instructions': 'You are the memory manager for a database assistant. Extract worth-keeping business knowledge from conversations: table relationships (which fields link tables), field Chinese meanings and common usage, form workflow IDs, business operation patterns (e.g. push leave form -> check kq_leave -> update status), unnamed detail table purposes. Do NOT store: temporary query results, one-off data values. Always preserve original English table/field names.',
    }

    try:
        mem = Memory.from_config(config)
        logger.info('Mem0 initialized: Qdrant=%s, LLM=%s', mem0_dir, settings.deepseek_model)
        return mem
    except Exception as e:
        logger.error('Mem0 init failed: %s', e)
        raise
