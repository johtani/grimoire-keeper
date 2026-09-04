"""Configuration settings."""

import logging
import os
import sys
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings."""

    # API Keys
    JINA_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # LLM
    LLM_MODEL: str = "openai/qwen3-35b"
    LLM_API_BASE: str = ""  # 空の場合はLiteLLMのデフォルトルーティングを使用 (Gemini等)
    LLM_API_KEY: str = "dummy"
    LLM_CONTEXT_WINDOW: int = 32768
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    LLM_SUMMARY_CONCURRENCY: int = 3
    LLM_TIMEOUT: float = Field(default=60.0, gt=0)
    LLM_RETRY_ATTEMPTS: int = Field(default=3, ge=1)
    LLM_RETRY_BACKOFF_BASE: float = Field(default=1.0, ge=0)
    LLM_RETRY_BACKOFF_MAX: float = Field(default=10.0, ge=0)
    LLM_RETRY_JITTER: float = Field(default=0.5, ge=0)
    LLM_RETRY_AFTER_MAX: float = Field(default=30.0, ge=0)

    # Jina Reader
    JINA_CONNECT_TIMEOUT: float = Field(default=5.0, gt=0)
    JINA_READ_TIMEOUT: float = Field(default=60.0, gt=0)
    JINA_WRITE_TIMEOUT: float = Field(default=10.0, gt=0)
    JINA_POOL_TIMEOUT: float = Field(default=5.0, gt=0)
    JINA_RETRY_ATTEMPTS: int = Field(default=3, ge=1)
    JINA_RETRY_BACKOFF_BASE: float = Field(default=1.0, ge=0)
    JINA_RETRY_BACKOFF_MAX: float = Field(default=10.0, ge=0)
    JINA_RETRY_JITTER: float = Field(default=0.5, ge=0)
    JINA_RETRY_AFTER_MAX: float = Field(default=30.0, ge=0)

    # Database
    DATABASE_PATH: str = "./grimoire.db"

    # Weaviate
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_PAGE_COLLECTION_NAME: str = "GrimoirePage"
    WEAVIATE_CHUNK_COLLECTION_NAME: str = "GrimoireContentChunk"
    WEAVIATE_EMBEDDING_PROVIDER: Literal["text2vec-openai"] = "text2vec-openai"
    WEAVIATE_EMBEDDING_MODEL: Literal[
        "text-embedding-ada-002",
        "text-embedding-3-small",
        "text-embedding-3-large",
    ] = "text-embedding-ada-002"
    WEAVIATE_EMBEDDING_DIMENSIONS: int = Field(default=1536, gt=0)
    WEAVIATE_STARTUP_RETRY_ATTEMPTS: int = 12
    WEAVIATE_STARTUP_RETRY_INTERVAL: float = 5.0
    WEAVIATE_STARTUP_TIMEOUT: float = 60.0
    WEAVIATE_CONNECT_TIMEOUT: float = 5.0
    WEAVIATE_QUERY_TIMEOUT: float = Field(default=30.0, gt=0)
    WEAVIATE_INSERT_TIMEOUT: float = Field(default=90.0, gt=0)
    WEAVIATE_RETRY_ATTEMPTS: int = Field(default=3, ge=1)
    WEAVIATE_RETRY_BACKOFF_BASE: float = Field(default=0.5, ge=0)
    WEAVIATE_RETRY_BACKOFF_MAX: float = Field(default=5.0, ge=0)
    WEAVIATE_RETRY_JITTER: float = Field(default=0.25, ge=0)
    WEAVIATE_RETRY_AFTER_MAX: float = Field(default=10.0, ge=0)
    WEAVIATE_DELETE_POLL_ATTEMPTS: int = Field(default=10, ge=1)
    WEAVIATE_DELETE_POLL_INTERVAL: float = Field(default=0.1, ge=0)
    WEAVIATE_MONITOR_INTERVAL: float = 5.0
    WEAVIATE_WORKER_STOP_TIMEOUT: float = 10.0

    # File Storage
    JSON_STORAGE_PATH: str = "./data/json"
    REPAIR_REPORT_PATH: str = "./data/migration/repair-pending.json"

    # Build Info
    GIT_COMMIT: str = "unknown"
    BUILD_DATE: str = "unknown"

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"),
        extra="ignore",  # 余分な環境変数を無視
    )

    @model_validator(mode="after")
    def validate_embedding_dimensions(self) -> "Settings":
        """Validate dimensions supported by the configured OpenAI model."""
        maximum_dimensions = {
            "text-embedding-ada-002": 1536,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
        }
        maximum = maximum_dimensions[self.WEAVIATE_EMBEDDING_MODEL]
        if self.WEAVIATE_EMBEDDING_MODEL == "text-embedding-ada-002":
            if self.WEAVIATE_EMBEDDING_DIMENSIONS != maximum:
                raise ValueError("text-embedding-ada-002 requires 1536 dimensions")
        elif self.WEAVIATE_EMBEDDING_DIMENSIONS > maximum:
            raise ValueError(
                f"{self.WEAVIATE_EMBEDDING_MODEL} supports at most {maximum} dimensions"
            )
        return self

    @model_validator(mode="after")
    def validate_retry_backoff_limits(self) -> "Settings":
        """Reject retry policies whose cap is below their initial delay."""
        for service in ("JINA", "LLM", "WEAVIATE"):
            base = getattr(self, f"{service}_RETRY_BACKOFF_BASE")
            maximum = getattr(self, f"{service}_RETRY_BACKOFF_MAX")
            if maximum < base:
                raise ValueError(
                    f"{service}_RETRY_BACKOFF_MAX must be greater than or equal to "
                    f"{service}_RETRY_BACKOFF_BASE"
                )
        return self

    def missing_api_required_vars(self) -> list[str]:
        """Return missing settings required by the SQLite-backed API process."""
        return ["DATABASE_PATH"] if not self.DATABASE_PATH.strip() else []

    def missing_worker_required_vars(self) -> list[str]:
        """Return missing settings required by the processing worker."""
        required_vars = {
            "DATABASE_PATH": self.DATABASE_PATH,
            "JINA_API_KEY": self.JINA_API_KEY,
            "OPENAI_API_KEY": self.OPENAI_API_KEY,
        }
        missing_vars = [
            name for name, value in required_vars.items() if not value.strip()
        ]

        llm_api_key = self.LLM_API_KEY.strip()
        uses_cloud_llm = not self.LLM_API_BASE.strip()
        if not llm_api_key or (uses_cloud_llm and llm_api_key.lower() == "dummy"):
            missing_vars.append("LLM_API_KEY")

        return missing_vars

    def validate_api_required_vars(self) -> None:
        """Validate settings required by the API process."""
        self._validate_required_vars(self.missing_api_required_vars(), "API")

    def validate_worker_required_vars(self) -> None:
        """Validate settings required by the worker process."""
        self._validate_required_vars(self.missing_worker_required_vars(), "Worker")

    def _validate_required_vars(self, missing_vars: list[str], process: str) -> None:
        """Exit with a useful message when process-specific settings are missing.

        Raises:
            SystemExit: 必須環境変数が設定されていない場合
        """
        if missing_vars:
            error_msg = (
                "\n" + "=" * 70 + "\n"
                f"ERROR: {process} の必須環境変数が設定されていません\n"
                "=" * 70 + "\n\n"
                "以下の環境変数を設定してください:\n\n"
            )
            for var in missing_vars:
                error_msg += f"  - {var}\n"
            error_msg += (
                "\n設定方法:\n"
                "  1. Bitwarden Secrets Managerにシークレットを登録\n"
                "     (GRIMOIRE_KEEPER_プレフィックス付きで登録)\n"
                "  2. BWS_ACCESS_TOKENを.envに設定\n"
                "  3. bash scripts/dev.sh でAPIを起動 (bws runがシークレットを注入)\n\n"
                "LLM_API_BASEが空のクラウドLLM構成では、LLM_API_KEYにdummy以外の"
                "実キーが必要です。\n"
                "詳細は docs/development.md を参照してください。\n"
                "=" * 70
            )
            logger.error(error_msg)
            sys.exit(1)


settings = Settings()
