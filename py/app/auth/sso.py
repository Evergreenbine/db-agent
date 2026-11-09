"""认证服务 - Oracle 数据库验证 + JWT 签发"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import text
from app.config import get_settings
from app.database import get_db
from app.auth.models import LoginRequest, LoginResponse, UserInfo

logger = logging.getLogger(__name__)
settings = get_settings()


def _md5_upper(password: str) -> str:
    """E9 密码存储格式: MD5 大写"""
    return hashlib.md5(password.encode()).hexdigest().upper()


def _create_jwt(employee_id: str, name: str) -> str:
    """签发 JWT token"""
    payload = {
        "employee_id": employee_id,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _query_user(employee_id: str):
    """查 hrmresource + 部门，返回 (loginid, lastname, departmentname) 或 None"""
    db = next(get_db())
    try:
        sql = text("""
            SELECT r.loginid, r.lastname, d.departmentname
            FROM hrmresource r
            LEFT JOIN hrmdepartment d ON r.departmentid = d.id
            WHERE r.loginid = :loginid
        """)
        return db.execute(sql, {"loginid": employee_id}).fetchone()
    finally:
        db.close()


def login(req: LoginRequest) -> LoginResponse:
    """工号 + 密码 验证 -> JWT"""
    db = next(get_db())
    try:
        sql = text("""
            SELECT r.loginid, r.password, r.lastname, d.departmentname
            FROM hrmresource r
            LEFT JOIN hrmdepartment d ON r.departmentid = d.id
            WHERE r.loginid = :loginid
        """)
        row = db.execute(sql, {"loginid": req.employee_id}).fetchone()

        if row is None:
            logger.warning(f"Auth: employee not found: {req.employee_id}")
            raise ValueError(f"工号 {req.employee_id} 不存在")

        loginid, db_pwd, name, dept = row
        if _md5_upper(req.password) != db_pwd:
            logger.warning(f"Auth: wrong password: {req.employee_id}")
            raise ValueError("密码错误")

        user = UserInfo(
            employee_id=loginid,
            name=name or "",
            department=dept or "",
        )
        token = _create_jwt(loginid, name or "")
        logger.info(f"Auth: login success: {loginid} ({name})")
        return LoginResponse(token=token, user=user)
    finally:
        db.close()


def login_by_id(employee_id: str) -> LoginResponse:
    """工号直接换 JWT（简化版，无密码验证，仅供内网 iframe 嵌套使用）"""
    row = _query_user(employee_id)
    if row is None:
        logger.warning(f"Auth: employee not found: {employee_id}")
        raise ValueError(f"工号 {employee_id} 不存在")

    loginid, name, dept = row
    user = UserInfo(
        employee_id=loginid,
        name=name or "",
        department=dept or "",
    )
    token = _create_jwt(loginid, name or "")
    logger.info(f"Auth: login_by_id success: {loginid} ({name})")
    return LoginResponse(token=token, user=user)
