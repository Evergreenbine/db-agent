"""数据库引擎与会话管理 - SQLAlchemy 2.0 + oracledb (thick 模式)"""

from collections.abc import Generator
import oracledb
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from app.config import get_settings

settings = get_settings()

# 初始化 Oracle Instant Client (thick mode, 支持 Oracle 11g)
if settings.oracle_client_dir:
    oracledb.init_oracle_client(lib_dir=settings.oracle_client_dir)


def _create_connection():
    """使用 oracledb 直接创建连接 (支持 SID 模式)"""
    return oracledb.connect(
        user=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        sid=settings.db_sid,
    )


# Oracle (Ecology E9) 引擎
engine = create_engine(
    "oracle+oracledb://",
    creator=_create_connection,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.app_debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """ORM 模型基类"""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖注入: 获取 Oracle 数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
