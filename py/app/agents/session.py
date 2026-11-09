import json, time, logging, asyncio
import redis as redis_lib
from app.config import get_settings
from app.agents.history import save_items as _save_history

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis key prefixes
_PREFIX = "oa:agent:chat:"
_META_PREFIX = "oa:agent:meta:"
_TTL = 86400  # 24h

_pool = None

def _get_redis():
    global _pool
    if _pool is None:
        _pool = redis_lib.ConnectionPool(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
        )
    return redis_lib.Redis(connection_pool=_pool)

_MAX_SESSION_BYTES = 300_000  # 300KB cap to avoid model context overflow

def _rget_items(session_id, limit=None):
    r = _get_redis()
    key = _PREFIX + session_id
    if limit:
        items_raw = r.lrange(key, -limit, -1)
    else:
        items_raw = r.lrange(key, 0, -1)
    result = []
    total_bytes = 0
    for raw in items_raw:
        total_bytes += len(raw)
        if total_bytes > _MAX_SESSION_BYTES and result:
            break
        try:
            result.append(json.loads(raw))
        except Exception:
            pass
    return result

def _radd_items(session_id, items):
    r = _get_redis()
    key = _PREFIX + session_id
    pipe = r.pipeline()
    for item in items:
        pipe.rpush(key, json.dumps(item, ensure_ascii=False, default=str))
    pipe.expire(key, _TTL)
    pipe.execute()

def _rpop_item(session_id):
    r = _get_redis()
    key = _PREFIX + session_id
    raw = r.rpop(key)
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            return None
    return None

def _rclear_session(session_id):
    r = _get_redis()
    r.delete(_PREFIX + session_id)
    r.delete(_META_PREFIX + session_id)

def _rensure_session(session_id, user_id, user_name):
    r = _get_redis()
    meta_key = _META_PREFIX + session_id
    if not r.exists(meta_key):
        r.hset(meta_key, mapping={
            "user_id": user_id,
            "user_name": user_name,
            "created_at": str(int(time.time())),
        })
        r.expire(meta_key, _TTL)
        logger.info("Redis session created: %s (user=%s)", session_id, user_id)

class RedisSession:
    def __init__(self, session_id, user_id="", user_name=""):
        self.session_id = session_id
        self.user_id = user_id
        self.user_name = user_name

    async def get_items(self, limit=60):
        try:
            return await asyncio.to_thread(_rget_items, self.session_id, limit)
        except Exception as e:
            logger.warning("Redis get_items failed: %s", e)
            return []

    async def add_items(self, items):
        try:
            await asyncio.to_thread(_radd_items, self.session_id, items)
        except Exception as e:
            logger.warning("Redis add_items failed: %s", e)
        try:
            await asyncio.to_thread(_save_history, self.session_id, items, self.user_id, self.user_name)
        except Exception as e:
            logger.warning("SQLite history save failed: %s", e)

    async def pop_item(self):
        try:
            return await asyncio.to_thread(_rpop_item, self.session_id)
        except Exception as e:
            logger.warning("Redis pop_item failed: %s", e)
            return None

    async def clear_session(self):
        try:
            await asyncio.to_thread(_rclear_session, self.session_id)
        except Exception as e:
            logger.warning("Redis clear_session failed: %s", e)

def get_session(session_id, user_id="", user_name=""):
    _rensure_session(session_id, user_id, user_name)
    return RedisSession(session_id, user_id, user_name)

def clear_session(session_id):
    _rclear_session(session_id)
