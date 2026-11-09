"""认证依赖 - 从 Authorization header 提取用户身份"""

import logging

import jwt
from sqlalchemy import text
from app.config import get_settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()


def resolve_g4_employee_id(oa_loginid: str) -> str | None:
    """OA loginid -> G4PRO empno，通过 cus_fielddata 表映射。"""
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT c.field0 FROM cus_fielddata c "
            "JOIN hrmresource r ON r.id = c.id "
            "WHERE c.scope = 'HrmCustomFieldByInfoType' "
            "AND c.field0 IS NOT NULL AND TRIM(c.field0) IS NOT NULL "
            "AND r.loginid = :loginid AND ROWNUM = 1 "
        ), {"loginid": oa_loginid}).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning(f"resolve_g4_employee_id failed for {oa_loginid}: {e}")
        return None
    finally:
        db.close()


def resolve_oa_user_id(oa_loginid: str) -> str | None:
    """OA loginid (如 M03141) -> hrmresource.id (如 1395)"""
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT id FROM hrmresource WHERE loginid = :loginid"),
            {"loginid": oa_loginid},
        ).fetchone()
        return str(row[0]) if row else None
    except Exception as e:
        logger.warning(f"resolve_oa_user_id failed for {oa_loginid}: {e}")
        return None
    finally:
        db.close()


def get_user_from_auth_header(
    authorization: str | None,
    x_employee_id: str | None = None,
) -> dict:
    """从 Authorization Bearer token 解 JWT 提取用户身份。

    解析出 OA 工号后，自动映射 G4PRO 考勤工号 + OA 数字 userId。
    JWT 解码失败时回退到 X-Employee-Id header。
    """
    employee_id = ""
    name = ""

    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
            employee_id = payload.get("employee_id", "")
            name = payload.get("name", "")
        except jwt.PyJWTError:
            logger.warning("JWT decode failed, falling back to X-Employee-Id")
    if not employee_id and x_employee_id:
        employee_id = x_employee_id

    if not employee_id:
        return {}

    g4_id = resolve_g4_employee_id(employee_id)
    oa_uid = resolve_oa_user_id(employee_id)

    result = {"employee_id": employee_id, "name": name}
    if g4_id:
        result["g4_employee_id"] = g4_id
    if oa_uid:
        result["oa_user_id"] = oa_uid
    return result
