"""OA SSO - 通过 E9 Session 单点登录

流程: 前端传入 ecology_JSessionId -> Python 调用 Java /api/agentsession/current
      -> Java 用 HrmUserVarify 解析 OA Session -> 返回用户信息 -> Python 签发 JWT
"""

import logging

import httpx

from app.auth.models import LoginResponse, UserInfo
from app.auth.sso import _create_jwt
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OA_SESSION_COOKIE_NAME = "ecology_JSessionId"


def sso_by_session(ecology_session_id: str) -> LoginResponse:
    """通过 E9 Session ID 获取用户信息并签发 JWT。"""
    if not ecology_session_id:
        raise ValueError("session ID 不能为空")

    url = f"{settings.e9_base_url}/api/agentsession/current"
    cookies = {OA_SESSION_COOKIE_NAME: ecology_session_id}

    try:
        resp = httpx.get(url, cookies=cookies, timeout=10, verify=False)
    except Exception as e:
        logger.error("SSO: 调用 OA 会话接口失败: %s", e)
        raise ValueError("OA 会话服务不可用")

    if resp.status_code != 200:
        logger.warning("SSO: OA 返回 HTTP %s", resp.status_code)
        raise ValueError("OA 会话服务异常")

    data = resp.json()
    if data.get("code") != 200 or not data.get("data"):
        logger.warning("SSO: OA session 无效或已过期")
        raise ValueError("OA 会话已过期，请重新登录 OA")

    user_data = data["data"]
    login_id = user_data.get("loginId", "")
    name = user_data.get("name", "")

    if not login_id:
        raise ValueError("OA 返回的用户信息不完整")

    token = _create_jwt(login_id, name)
    user = UserInfo(employee_id=login_id, name=name)
    logger.info("SSO: 登录成功: %s (%s)", login_id, name)
    return LoginResponse(token=token, user=user)
