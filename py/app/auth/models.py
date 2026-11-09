"""认证模块数据模型"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求 (前端契约)"""
    employee_id: str = Field(description="工号")
    password: str = Field(description="密码")


class UserInfo(BaseModel):
    """用户信息"""
    employee_id: str = Field(description="工号")
    name: str = Field(description="姓名")
    department: str = Field(default="", description="部门名称")


class LoginResponse(BaseModel):
    """登录响应 (前端契约)"""
    token: str = Field(description="JWT token")
    user: UserInfo = Field(description="用户信息")


class SSORequest(BaseModel):
    """SSO 登录请求 (前端契约) - iframe 嵌套场景，前端传入 OA 会话 ID"""
    ecology_session_id: str = Field(description="E9 OA 会话 ID (ecology_JSessionId cookie 值)")


class UserIdRequest(BaseModel):
    """工号登录请求 (前端契约) - 简化版，传工号直接换 JWT"""
    employee_id: str = Field(description="工号")
