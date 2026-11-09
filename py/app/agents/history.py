"""SQLite 持久化历史对话存储。

与 Redis 并行：
- Redis 存活跃 session（24h TTL，快），供 Agents SDK 上下文加载。
- SQLite 存永久历史（不过期），可查询/导出/回溯。

每次 session.add_items 时自动同步写入 SQLite。
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parents[2] / "data"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "history.db"

_lock = threading.Lock()
_initialized = False


def _get_conn():
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init():
    global _initialized
    if _initialized:
        return
    with _lock:
        if _initialized:
            return
        conn = _get_conn()
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id   TEXT PRIMARY KEY,
                    user_id      TEXT DEFAULT '',
                    user_name    TEXT DEFAULT '',
                    title        TEXT DEFAULT '',
                    msg_count    INTEGER DEFAULT 0,
                    created_at   TEXT DEFAULT (datetime('now','localtime')),
                    updated_at   TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT NOT NULL,
                    seq         INTEGER DEFAULT 0,
                    role        TEXT DEFAULT '',
                    msg_type    TEXT DEFAULT '',
                    content     TEXT DEFAULT '',
                    raw_json    TEXT DEFAULT '',
                    created_at  TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
                CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
                """
            )
            conn.commit()
            _initialized = True
            logger.info("SQLite history DB ready: %s", _DB_PATH)
        except Exception as e:
            logger.error("SQLite init failed: %s", e)
            raise
        finally:
            conn.close()


def _extract(item):
    """从 SDK session item 提取 (role, msg_type, content) 摘要文本。"""
    itype = item.get("type", "message")
    role = item.get("role", "")
    content = ""
    if itype == "message":
        role = role or "unknown"
        c = item.get("content")
        if isinstance(c, str):
            content = c
        elif isinstance(c, list):
            parts = []
            for p in c:
                if isinstance(p, dict):
                    parts.append(p.get("text", "") or p.get("content", "") or "")
                else:
                    parts.append(str(p))
            content = " ".join(parts)
        else:
            content = str(c) if c else ""
    elif itype == "function_call":
        role = "tool"
        name = item.get("name", "")
        args = item.get("arguments", "")
        content = name + "(" + str(args)[:300] + ")"
    elif itype == "function_call_output":
        role = "tool"
        out = item.get("output", "")
        content = str(out)[:500]
    elif itype == "reasoning":
        role = "reasoning"
        summary = item.get("summary", [])
        if isinstance(summary, list):
            content = " ".join(
                s.get("text", "") if isinstance(s, dict) else str(s)
                for s in summary
            )
        else:
            content = str(summary)
    else:
        role = role or itype
        content = json.dumps(item, ensure_ascii=False, default=str)[:300]
    return role, itype, content


def _conversation_title(content):
    text = content or ""
    if text.startswith("【用户已 @ 引用的表单】"):
        parts = text.split("\n\n")
        if len(parts) > 1:
            return parts[-1].strip()
    return text.strip()


def save_items(session_id, items, user_id="", user_name=""):
    """持久化一批 session items 到 SQLite（线程安全）。"""
    if not items:
        return
    _init()
    conn = _get_conn()
    try:
        with _lock:
            conn.execute(
                """
                INSERT INTO conversations (session_id, user_id, user_name, updated_at)
                VALUES (?, ?, ?, datetime('now','localtime'))
                ON CONFLICT(session_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    user_name=excluded.user_name,
                    updated_at=datetime('now','localtime')
                """,
                (session_id, user_id, user_name),
            )
            row = conn.execute(
                "SELECT COALESCE(MAX(seq),0) FROM messages WHERE session_id=?",
                (session_id,),
            ).fetchone()
            seq = (row[0] if row else 0) + 1
            for item in items:
                role, mtype, content = _extract(item)
                conn.execute(
                    """
                    INSERT INTO messages (session_id, seq, role, msg_type, content, raw_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        seq,
                        role,
                        mtype,
                        content[:2000],
                        json.dumps(item, ensure_ascii=False, default=str),
                    ),
                )
                seq += 1
            conn.execute(
                "UPDATE conversations SET msg_count=(SELECT COUNT(*) FROM messages WHERE session_id=?), updated_at=datetime('now','localtime') WHERE session_id=?",
                (session_id, session_id),
            )
            cur_title = conn.execute(
                "SELECT title FROM conversations WHERE session_id=?", (session_id,)
            ).fetchone()
            if cur_title and not cur_title["title"]:
                first = conn.execute(
                    "SELECT content FROM messages WHERE session_id=? AND role='user' ORDER BY seq LIMIT 1",
                    (session_id,),
                ).fetchone()
                if first and first["content"]:
                    conn.execute(
                        "UPDATE conversations SET title=? WHERE session_id=?",
                        (_conversation_title(first["content"])[:60], session_id),
                    )
            conn.commit()
    except Exception as e:
        logger.warning("SQLite save_items failed: %s", e)
    finally:
        conn.close()


def get_history(session_id):
    """获取某 session 的全部消息（按时间序）。"""
    _init()
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, seq, role, msg_type, content, raw_json, created_at FROM messages WHERE session_id=? ORDER BY seq",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()



def patch_latest_tool_result(session_id, tool_name, patch_data):
    """Patch the most recent function_call_output whose function_call name matches tool_name."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, seq, raw_json FROM messages WHERE session_id=? AND msg_type='function_call_output' ORDER BY seq DESC",
            (session_id,),
        ).fetchall()
        for row_id, seq, raw_json in rows:
            try:
                item = json.loads(raw_json) if raw_json else {}
            except (json.JSONDecodeError, TypeError):
                continue
            call_id = str(item.get("call_id", ""))
            # Find the corresponding function_call to check tool name
            fc_row = conn.execute(
                "SELECT raw_json FROM messages WHERE session_id=? AND msg_type='function_call' AND raw_json LIKE ? ORDER BY seq DESC LIMIT 1",
                (session_id, f'%{call_id}%'),
            ).fetchone()
            if fc_row:
                try:
                    fc = json.loads(fc_row["raw_json"] or "{}")
                    if fc.get("name") != tool_name:
                        continue
                except (json.JSONDecodeError, TypeError):
                    continue
            else:
                continue
            output = item.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    output = {"_raw": output}
            if not isinstance(output, dict):
                output = {}
            output.update(patch_data)
            item["output"] = json.dumps(output, ensure_ascii=False)
            conn.execute(
                "UPDATE messages SET raw_json=? WHERE id=?",
                (json.dumps(item, ensure_ascii=False), row_id),
            )
            conn.commit()
            logger.info("patch_latest_tool_result: patched row %s for %s", row_id, tool_name)
            return True
        logger.warning("patch_latest_tool_result: no matching %s output found", tool_name)
        return False
    except Exception as e:
        logger.warning("patch_latest_tool_result failed: %s", e)
        return False
    finally:
        conn.close()

def list_conversations(user_id=None, limit=50):
    """列出历史会话（最新的在前）。"""
    _init()
    conn = _get_conn()
    try:
        if user_id:
            rows = conn.execute(
                "SELECT session_id, user_id, user_name, title, msg_count, created_at, updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT session_id, user_id, user_name, title, msg_count, created_at, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conversations = []
        for row in rows:
            item = dict(row)
            title = item.get("title") or ""
            if not title or title.startswith("【用户已 @ 引用的表单】"):
                first = conn.execute(
                    "SELECT content FROM messages WHERE session_id=? AND role='user' ORDER BY seq LIMIT 1",
                    (item["session_id"],),
                ).fetchone()
                if first and first["content"]:
                    title = _conversation_title(first["content"])[:60]
            item["title"] = title
            conversations.append(item)
        return conversations
    finally:
        conn.close()


def delete_conversation(session_id):
    """删除某个会话的全部记录。"""
    _init()
    conn = _get_conn()
    try:
        with _lock:
            conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
            conn.commit()
    finally:
        conn.close()


def patch_tool_result(session_id, tool_call_id, patch_data):
    """Patch a tool result's raw_json in SQLite (merge exec_result/executed/cancelled)."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, raw_json FROM messages WHERE session_id=? AND msg_type='function_call_output' ORDER BY seq",
            (session_id,),
        ).fetchall()
        for row_id, raw_json in rows:
            try:
                item = json.loads(raw_json) if raw_json else {}
            except (json.JSONDecodeError, TypeError):
                continue
            if str(item.get("call_id", "")) != tool_call_id:
                continue
            output = item.get("output")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except (json.JSONDecodeError, TypeError):
                    output = {"_raw": output}
            if not isinstance(output, dict):
                output = {}
            output.update(patch_data)
            item["output"] = json.dumps(output, ensure_ascii=False)
            conn.execute(
                "UPDATE messages SET raw_json=? WHERE id=?",
                (json.dumps(item, ensure_ascii=False), row_id),
            )
            conn.commit()
            return True
        return False
    except Exception as e:
        logger.warning("patch_tool_result failed: %s", e)
        return False
    finally:
        conn.close()
