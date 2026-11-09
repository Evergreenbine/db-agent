"""认证路由 - 工号密码登录 + OA SSO + 工号直接登录"""

from fastapi import APIRouter, HTTPException

from app.auth.models import LoginRequest, LoginResponse, SSORequest, UserIdRequest
from app.auth.sso import login, login_by_id
from app.auth.oa_sso import sso_by_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login_endpoint(req: LoginRequest):
    """工号 + 密码 -> JWT token + 用户信息"""
    try:
        return login(req)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/sso", response_model=LoginResponse)
async def sso_endpoint(req: SSORequest):
    """OA Session SSO -> JWT token + 用户信息

    iframe 嵌套场景: 前端从 OA 页面获取 ecology_JSessionId，
    传入本接口，后端调用 Java /api/agentsession/current 验证会话并签发 JWT。
    """
    try:
        return sso_by_session(req.ecology_session_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/by-id", response_model=LoginResponse)
async def login_by_id_endpoint(req: UserIdRequest):
    """工号直接换 JWT（简化版，无密码验证，仅供内网 iframe 嵌套使用）"""
    try:
        return login_by_id(req.employee_id)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
