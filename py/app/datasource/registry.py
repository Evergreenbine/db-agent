"""数据源注册表 - SQLite 持久化 + 适配器工厂。

启动时自动从 .env 种子 OA 数据源（如果表为空）。
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from app.datasource.adapter import (
    DataSourceConfig,
    DataSourceAdapter,
    create_adapter,
)

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parents[2] / "data"
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "datasources.db"

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
                CREATE TABLE IF NOT EXISTS datasources (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    name          TEXT UNIQUE NOT NULL,
                    db_type       TEXT NOT NULL,
                    host          TEXT NOT NULL,
                    port          INTEGER NOT NULL,
                    database_name TEXT NOT NULL,
                    username      TEXT NOT NULL,
                    password      TEXT NOT NULL,
                    description   TEXT DEFAULT '',
                    is_active     INTEGER DEFAULT 1,
                    created_at    TEXT DEFAULT (datetime('now','localtime'))
                );
                """
            )
            conn.commit()
            _seed_if_empty(conn)
            _initialized = True
            logger.info("DataSource registry ready: %s", _DB_PATH)
        finally:
            conn.close()


def _seed_if_empty(conn):
    """表空时从 .env 种子 OA 数据源。"""
    count = conn.execute("SELECT COUNT(*) FROM datasources").fetchone()[0]
    if count > 0:
        return
    try:
        from app.config import get_settings
        s = get_settings()
        conn.execute(
            "INSERT INTO datasources (name, db_type, host, port, database_name, username, password, description) "
            "VALUES (?, 'oracle', ?, ?, ?, ?, ?, ?)",
            (
                "oa",
                s.db_host,
                s.db_port,
                s.db_sid,
                s.db_user,
                s.db_password,
                "e-cology OA 系统（默认）",
            ),
        )
        conn.commit()
        logger.info("Seeded OA datasource from .env")
    except Exception as e:
        logger.warning("Seed OA datasource failed: %s", e)


def _row_to_config(row: sqlite3.Row) -> DataSourceConfig:
    return DataSourceConfig(
        id=row["id"],
        name=row["name"],
        db_type=row["db_type"],
        host=row["host"],
        port=row["port"],
        database_name=row["database_name"],
        username=row["username"],
        password=row["password"],
        description=row["description"] or "",
        is_active=bool(row["is_active"]),
        created_at=row["created_at"] or "",
    )


def list_all() -> list[dict]:
    _init()
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM datasources ORDER BY id").fetchall()
        return [_row_to_config(r).to_dict() for r in rows]
    finally:
        conn.close()


def get_config(name: str) -> Optional[DataSourceConfig]:
    _init()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM datasources WHERE name=?", (name,)).fetchone()
        return _row_to_config(row) if row else None
    finally:
        conn.close()


def get_config_by_id(ds_id: int) -> Optional[DataSourceConfig]:
    _init()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM datasources WHERE id=?", (ds_id,)).fetchone()
        return _row_to_config(row) if row else None
    finally:
        conn.close()


def create(data: dict) -> dict:
    _init()
    conn = _get_conn()
    try:
        with _lock:
            cur = conn.execute(
                "INSERT INTO datasources (name, db_type, host, port, database_name, username, password, description, is_active) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    data["name"],
                    data["db_type"],
                    data["host"],
                    int(data.get("port", 0)),
                    data["database_name"],
                    data["username"],
                    data["password"],
                    data.get("description", ""),
                ),
            )
            conn.commit()
            ds_id = cur.lastrowid
        cfg = get_config_by_id(ds_id)
        return cfg.to_dict() if cfg else {"error": "创建后读取失败"}
    except sqlite3.IntegrityError:
        return {"error": "NAME_EXISTS", "detail": f"数据源名称 '{data['name']}' 已存在"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


def delete(ds_id: int) -> bool:
    _init()
    conn = _get_conn()
    try:
        with _lock:
            cur = conn.execute("DELETE FROM datasources WHERE id=?", (ds_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def get_adapter(name: str) -> Optional[DataSourceAdapter]:
    cfg = get_config(name)
    if not cfg:
        return None
    return create_adapter(cfg)


def get_adapter_by_id(ds_id: int) -> Optional[DataSourceAdapter]:
    cfg = get_config_by_id(ds_id)
    if not cfg:
        return None
    return create_adapter(cfg)
