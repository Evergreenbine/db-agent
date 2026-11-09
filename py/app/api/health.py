"""健康检查路由"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health_check():
    """基础健康检查"""
    return {
        "status": "ok",
        "service": "oa-agent-backend",
        "version": "0.1.0",
    }


@router.get("/health/db")
async def db_health_check(db: Session = Depends(get_db)):
    """数据库连通性检查"""
    try:
        db.execute(text("SELECT 1 FROM DUAL"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
