"""应用配置 - 通过 .env 加载，pydantic-settings 管理类型校验"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # DeepSeek API
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Oracle Database
    db_host: str = ""
    db_port: int = 1521
    db_sid: str = "orcl"
    db_user: str = ""
    db_password: str = ""

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    # Proxy
    http_proxy: str = ""
    https_proxy: str = ""

    # E9 SSO
    e9_base_url: str = "https://10.3.10.88:8443"
    e9_sso_path: str = "/integration/simplesso"

    # Oracle Instant Client (thick mode)
    oracle_client_dir: str = ""

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    # JWT
    jwt_secret: str = "db-agent-secret-2026"
    jwt_expire_hours: int = 24

    # Qdrant (embedded 默认；设 QDRANT_HOST 则切 server)
    qdrant_host: str = ""
    qdrant_port: int = 6333
    qdrant_path: str = ".qdrant_data"

    @property
    def database_url(self) -> str:
        """SQLAlchemy Oracle 连接串 (oracledb thick 模式，需 Instant Client)"""
        return (
            f"oracle+oracledb://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
