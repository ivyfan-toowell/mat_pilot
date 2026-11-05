"""统一加载本地配置与服务密钥，为各模块提供经过校验的设置。"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_TENANT_ID = "local"
TENANT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
AuthMode = Literal["off", "api_key"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    mp_api_key: SecretStr | None = None
    dashscope_api_key: SecretStr | None = None
    openalex_api_key: SecretStr | None = None
    openalex_timeout_seconds: int = Field(default=20, ge=1, le=60)
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-plus"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = Field(default=10, ge=1, le=10)
    rerank_model: str = "qwen3-rerank"
    rerank_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
    sparse_corpus_limit: int = Field(default=10000, ge=100, le=50000)
    database_url: SecretStr | None = None
    data_dir: Path = PROJECT_ROOT / "data"
    auth_mode: AuthMode = "off"
    auth_api_keys: str = ""
    job_workers: int = Field(default=2, ge=1, le=8)
    # 0 disables rate limiting (local/tests). Production example: 120 / 30.
    rate_limit_per_minute: int = Field(default=0, ge=0, le=10000)
    rate_limit_costly_per_minute: int = Field(default=30, ge=1, le=1000)
    log_json: bool = False
    schema_auto_apply: bool = True
    vector_hnsw: bool = False
    log_level: str = "INFO"
    mp_timeout_seconds: int = Field(default=30, ge=1, le=120)
    backend_url: str = "http://127.0.0.1:8000"

    @field_validator("data_dir")
    @classmethod
    def resolve_data_dir(cls, value: Path) -> Path:
        return value if value.is_absolute() else PROJECT_ROOT / value

    @field_validator("embedding_dimensions")
    @classmethod
    def validate_dimension(cls, value: int) -> int:
        if value not in {64, 128, 256, 512, 768, 1024, 1536, 2048}:
            raise ValueError("unsupported text-embedding-v4 dimension")
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("invalid log level")
        return value


def tenant_data_dir(settings: Settings, tenant_id: str) -> Path:
    """Return the filesystem root for one tenant. Never interpolate untrusted paths."""
    if not TENANT_ID_PATTERN.fullmatch(tenant_id):
        raise ValueError(f"invalid tenant_id: {tenant_id}")
    return settings.data_dir / "tenants" / tenant_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
