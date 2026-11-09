"""FastAPI 主入口 - DB-Agent 后端"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api import health, agent, auth, forms, datasource, knowledge

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[DB-Agent] 启动中... 模型: {settings.deepseek_model}")
    print(f"[DB-Agent] 数据库: {settings.db_host}:{settings.db_port}/{settings.db_sid}")
    import app.agents.tools  # noqa: F401  触发工具注册
    import app.agents.base   # noqa: F401  触发 DeepSeek 客户端配置
    from app.agents.rag.schema_store import ensure_schema_index
    ensure_schema_index()  # SQLite 缺失才建; Qdrant 空才补(首次约 1-2 分钟, 之后秒级)
    from app.datasource import registry as _ds_reg
    _ds_reg._init()  # 数据源注册表初始化 + 种子 OA
    yield
    print("[DB-Agent] 已关闭")


app = FastAPI(
    title="DB-Agent API",
    description="e-cology 数据库智能体后端服务",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(agent.router)
app.include_router(auth.router)
app.include_router(forms.router)
app.include_router(datasource.router)
app.include_router(knowledge.router)


@app.get("/")
async def root():
    return {
        "service": "DB-Agent API",
        "docs": "/docs",
        "endpoints": {
            "health": "/health",
            "db_health": "/health/db",
            "agent_chat": "/api/agent/chat",
            "auth_login": "/api/auth/login",
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
