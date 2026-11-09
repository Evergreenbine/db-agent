"""数据源适配器 - 统一接口，支持 Oracle / SQL Server。

每个适配器封装连接创建、表枚举、列查询，上层（registry / API / 工具）不关心底层差异。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DataSourceConfig:
    id: int | None = None
    name: str = ""
    db_type: str = "oracle"       # oracle / sqlserver / mysql
    host: str = ""
    port: int = 1521
    database_name: str = ""       # Oracle: SID; SQLServer: db name
    username: str = ""
    password: str = ""
    description: str = ""
    is_active: bool = True
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("password", None)   # 不回传密码
        return d


class DataSourceAdapter:
    """数据源适配器基类。"""

    def __init__(self, config: DataSourceConfig):
        self.config = config

    def test_connection(self) -> dict:
        """返回 {ok, message, tables_count}"""
        raise NotImplementedError

    def execute_dml_batch(self, classified, timeout_ms=60000, employee_id=""):
        """Default: loop execute_dml without transaction (override for real batch)."""
        results = []
        for action, sql, table in classified:
            r = self.execute_dml(sql, timeout_ms=timeout_ms)
            r["action"] = action
            r["table"] = table
            results.append(r)
            if r.get("error"):
                break
        ok = sum(1 for r in results if r.get("executed"))
        return {"executed": ok == len(classified), "step_count": len(classified),
                "ok_count": ok, "results": results,
                "partial_failure": 0 < ok < len(classified)}

    def list_tables(self, include_backups: bool = False) -> list[dict]:
        """返回 [{name, schema, row_count, table_type, is_backup}]"""
        raise NotImplementedError

    def get_columns(self, table_name: str) -> list[dict]:
        """返回 [{name, data_type, max_length, is_nullable}]"""
        raise NotImplementedError

    def execute_query(self, sql: str, limit: int = 100) -> dict:
        """执行查询，返回 {columns, rows, count} 或 {error}"""
        raise NotImplementedError

    def execute_readonly(self, sql: str, limit: int = 100, timeout_ms: int = 30000) -> dict:
        """只读 SELECT 执行（只读已由上层校验），返回 {columns, rows, count, truncated} 或 {error, detail}。"""
        raise NotImplementedError

    def execute_dml(
        self, sql: str, params: Any | None = None, timeout_ms: int = 60000
    ) -> dict:
        """执行 DML（commit/rollback），返回 {executed, rows_affected} 或 {error, detail}。"""
        raise NotImplementedError


# ---- 备份表识别 ----
import re

_BACKUP_PAT = re.compile(
    r"(_bk$|_bak|_copy|_202d|before|backup|_old$|_tmp$|^temp)", re.I
)


def _is_backup_table(name: str) -> bool:
    return bool(_BACKUP_PAT.search(name))


def convert_value(value):
    """把数据库返回值转为 JSON 可序列化对象（Oracle / SQL Server 通用）。"""
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return value.hex() if isinstance(value, (bytes, bytearray)) else str(value)
    if hasattr(value, "read"):
        try:
            return value.read()
        except Exception:
            return str(value)
    return value


# ==================== Oracle ====================

class OracleAdapter(DataSourceAdapter):

    def _connect(self):
        import oracledb
        return oracledb.connect(
            user=self.config.username,
            password=self.config.password,
            host=self.config.host,
            port=self.config.port,
            sid=self.config.database_name,
        )

    def test_connection(self) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM user_tables")
            n = cur.fetchone()[0]
            conn.close()
            return {"ok": True, "message": f"连接成功，{n} 张表", "tables_count": n}
        except Exception as e:
            logger.warning("Oracle test failed [%s]: %s", self.config.name, e)
            return {"ok": False, "message": str(e), "tables_count": 0}

    def list_tables(self, include_backups: bool = False) -> list[dict]:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT table_name, NVL(num_rows, 0) FROM user_tables "
                "ORDER BY NVL(num_rows, 0) DESC"
            )
            tables = []
            for tn, rc in cur.fetchall():
                is_bak = _is_backup_table(tn)
                if not include_backups and is_bak:
                    continue
                tables.append({
                    "name": tn,
                    "schema": self.config.username.upper(),
                    "row_count": int(rc) if rc else 0,
                    "table_type": "BASE TABLE",
                    "is_backup": is_bak,
                })
            conn.close()
            return tables
        except Exception as e:
            logger.warning("Oracle list_tables failed: %s", e)
            return []

    def get_columns(self, table_name: str) -> list[dict]:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT column_name, data_type, data_length, nullable "
                "FROM all_tab_columns WHERE table_name = :t "
                "ORDER BY column_id",
                {"t": table_name.upper()},
            )
            cols = []
            for cn, dt, ml, nl in cur.fetchall():
                cols.append({
                    "name": cn,
                    "data_type": dt,
                    "max_length": int(ml) if ml else 0,
                    "is_nullable": nl == "Y",
                })
            conn.close()
            return cols
        except Exception as e:
            logger.warning("Oracle get_columns failed: %s", e)
            return []

    def execute_query(self, sql: str, limit: int = 100) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(limit)
            conn.close()
            return {"columns": columns, "rows": [list(r) for r in rows], "count": len(rows)}
        except Exception as e:
            return {"error": str(e)}

    def execute_readonly(self, sql: str, limit: int = 100, timeout_ms: int = 30000) -> dict:
        try:
            conn = self._connect()
            try:
                try:
                    conn.call_timeout = timeout_ms
                except Exception:
                    pass
                cur = conn.cursor()
                try:
                    cur.execute(sql)
                    cols = [d[0].lower() for d in cur.description] if cur.description else []
                    fetched = cur.fetchmany(limit)
                    rows = [[convert_value(v) for v in r] for r in fetched]
                    truncated = len(fetched) == limit and cur.fetchone() is not None
                    return {"columns": cols, "rows": rows, "count": len(rows), "truncated": truncated}
                finally:
                    cur.close()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Oracle execute_readonly failed: %s: %s", type(e).__name__, e)
            return {"error": "QUERY_FAILED", "detail": f"{type(e).__name__}: {e}"}

    def execute_dml(
        self, sql: str, params: Any | None = None, timeout_ms: int = 60000
    ) -> dict:
        try:
            conn = self._connect()
            try:
                try:
                    conn.call_timeout = timeout_ms
                except Exception:
                    pass
                cur = conn.cursor()
                try:
                    cur.execute(sql, params or {})
                    conn.commit()
                    return {"executed": True, "rows_affected": cur.rowcount}
                except Exception:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    raise
                finally:
                    cur.close()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Oracle execute_dml failed: %s: %s", type(e).__name__, e)
            return {"error": "WRITE_FAILED", "detail": f"{type(e).__name__}: {e}"}

    def execute_dml_batch(self, classified, timeout_ms=60000, employee_id=""):
        """Execute multiple DMLs in a single transaction (all-or-nothing)."""
        results = []
        all_ok = True
        try:
            conn = self._connect()
            try:
                try:
                    conn.call_timeout = timeout_ms
                except Exception:
                    pass
                cur = conn.cursor()
                try:
                    for action, sql, table in classified:
                        try:
                            cur.execute(sql)
                            results.append({"executed": True, "action": action,
                                            "table": table, "rows_affected": cur.rowcount})
                        except Exception as e:
                            results.append({"executed": False, "error": "WRITE_FAILED",
                                            "detail": f"{type(e).__name__}: {e}",
                                            "action": action, "table": table, "rows_affected": 0})
                            all_ok = False
                            break
                    if all_ok:
                        conn.commit()
                    else:
                        conn.rollback()
                finally:
                    cur.close()
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Oracle execute_dml_batch failed: %s: %s", type(e).__name__, e)
            return {"executed": False, "error": "BATCH_FAILED",
                    "detail": f"{type(e).__name__}: {e}", "results": results,
                    "step_count": len(classified),
                    "ok_count": sum(1 for r in results if r.get("executed")),
                    "partial_failure": False}
        return {"executed": all_ok, "step_count": len(classified),
                "ok_count": sum(1 for r in results if r.get("executed")),
                "results": results, "partial_failure": False, "transactional": True}


# ==================== SQL Server ====================

class SqlServerAdapter(DataSourceAdapter):

    def _conn_str(self) -> str:
        return (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={self.config.host},{self.config.port};"
            f"DATABASE={self.config.database_name};"
            f"UID={self.config.username};"
            f"PWD={self.config.password};"
        )

    def _connect(self):
        import pyodbc
        return pyodbc.connect(self._conn_str(), timeout=15)

    def test_connection(self) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sys.tables")
            n = cur.fetchone()[0]
            conn.close()
            return {"ok": True, "message": f"连接成功，{n} 张表", "tables_count": n}
        except Exception as e:
            logger.warning("SQLServer test failed [%s]: %s", self.config.name, e)
            return {"ok": False, "message": str(e), "tables_count": 0}

    def list_tables(self, include_backups: bool = False) -> list[dict]:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT t.name, ISNULL(p.rows, 0) "
                "FROM sys.tables t "
                "LEFT JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1) "
                "ORDER BY ISNULL(p.rows, 0) DESC"
            )
            tables = []
            for tn, rc in cur.fetchall():
                is_bak = _is_backup_table(tn)
                if not include_backups and is_bak:
                    continue
                tables.append({
                    "name": tn,
                    "schema": "dbo",
                    "row_count": int(rc) if rc else 0,
                    "table_type": "BASE TABLE",
                    "is_backup": is_bak,
                })
            conn.close()
            return tables
        except Exception as e:
            logger.warning("SQLServer list_tables failed: %s", e)
            return []

    def get_columns(self, table_name: str) -> list[dict]:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(
                "SELECT c.name, ty.name, c.max_length, c.is_nullable "
                "FROM sys.columns c "
                "JOIN sys.types ty ON c.user_type_id = ty.user_type_id "
                "WHERE c.object_id = OBJECT_ID(?) "
                "ORDER BY c.column_id",
                f"dbo.{table_name}",
            )
            cols = []
            for cn, dt, ml, nl in cur.fetchall():
                cols.append({
                    "name": cn,
                    "data_type": dt,
                    "max_length": int(ml) if ml else 0,
                    "is_nullable": bool(nl),
                })
            conn.close()
            return cols
        except Exception as e:
            logger.warning("SQLServer get_columns failed: %s", e)
            return []

    def execute_query(self, sql: str, limit: int = 100) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            if params is None:
                cur.execute(sql)
            else:
                cur.execute(sql, params)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(limit)
            conn.close()
            return {"columns": columns, "rows": [list(r) for r in rows], "count": len(rows)}
        except Exception as e:
            return {"error": str(e)}

    def execute_readonly(self, sql: str, limit: int = 100, timeout_ms: int = 30000) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(limit)
            rows = [[convert_value(v) for v in r] for r in fetched]
            truncated = len(fetched) == limit and cur.fetchone() is not None
            conn.close()
            return {"columns": cols, "rows": rows, "count": len(rows), "truncated": truncated}
        except Exception as e:
            logger.warning("SQLServer execute_readonly failed: %s: %s", type(e).__name__, e)
            return {"error": "QUERY_FAILED", "detail": f"{type(e).__name__}: {e}"}

    def execute_dml(
        self, sql: str, params: Any | None = None, timeout_ms: int = 60000
    ) -> dict:
        try:
            conn = self._connect()
            cur = conn.cursor()
            try:
                if params is None:
                    cur.execute(sql)
                else:
                    cur.execute(sql, params)
                conn.commit()
                return {"executed": True, "rows_affected": cur.rowcount}
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                cur.close()
        except Exception as e:
            logger.warning("SQLServer execute_dml failed: %s: %s", type(e).__name__, e)
            return {"error": "WRITE_FAILED", "detail": f"{type(e).__name__}: {e}"}
        finally:
            conn.close()

    def execute_dml_batch(self, classified, timeout_ms=60000, employee_id=""):
        """Execute multiple DMLs in a single transaction (all-or-nothing)."""
        results = []
        all_ok = True
        try:
            conn = self._connect()
            cur = conn.cursor()
            try:
                for action, sql, table in classified:
                    try:
                        cur.execute(sql)
                        results.append({"executed": True, "action": action,
                                        "table": table, "rows_affected": cur.rowcount})
                    except Exception as e:
                        results.append({"executed": False, "error": "WRITE_FAILED",
                                        "detail": f"{type(e).__name__}: {e}",
                                        "action": action, "table": table, "rows_affected": 0})
                        all_ok = False
                        break
                if all_ok:
                    conn.commit()
                else:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            finally:
                cur.close()
        except Exception as e:
            logger.warning("SQLServer execute_dml_batch failed: %s: %s", type(e).__name__, e)
            return {"executed": False, "error": "BATCH_FAILED",
                    "detail": f"{type(e).__name__}: {e}", "results": results,
                    "step_count": len(classified),
                    "ok_count": sum(1 for r in results if r.get("executed")),
                    "partial_failure": False}
        finally:
            conn.close()
        return {"executed": all_ok, "step_count": len(classified),
                "ok_count": sum(1 for r in results if r.get("executed")),
                "results": results, "partial_failure": False, "transactional": True}


# ==================== 工厂 ====================

_ADAPTERS = {
    "oracle": OracleAdapter,
    "sqlserver": SqlServerAdapter,
}


def create_adapter(config: DataSourceConfig) -> DataSourceAdapter:
    cls = _ADAPTERS.get(config.db_type)
    if not cls:
        raise ValueError(f"不支持的数据源类型: {config.db_type}")
    return cls(config)


def supported_types() -> list[dict]:
    return [
        {"value": "oracle", "label": "Oracle", "default_port": 1521, "db_label": "SID"},
        {"value": "sqlserver", "label": "SQL Server", "default_port": 1433, "db_label": "数据库名"},
        {"value": "mysql", "label": "MySQL", "default_port": 3306, "db_label": "数据库名"},
    ]
