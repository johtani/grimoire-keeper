"""Configuration settings."""

import logging
import os
import sys

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

    # Database
    DATABASE_PATH: str = "./grimoire.db"

    # Weaviate
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_PAGE_COLLECTION_NAME: str = "GrimoirePage"
    WEAVIATE_CHUNK_COLLECTION_NAME: str = "GrimoireContentChunk"
    WEAVIATE_STARTUP_RETRY_ATTEMPTS: int = 12
    WEAVIATE_STARTUP_RETRY_INTERVAL: float = 5.0
    WEAVIATE_STARTUP_TIMEOUT: float = 60.0
    WEAVIATE_CONNECT_TIMEOUT: float = 5.0
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

    def missing_required_vars(self) -> list[str]:
        """未設定または現在の構成では無効な必須環境変数を返す."""
        required_vars = {
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

    def validate_required_vars(self) -> None:
        """必須環境変数の検証.

        Raises:
            SystemExit: 必須環境変数が設定されていない場合
        """
        missing_vars = self.missing_required_vars()

        if missing_vars:
            error_msg = (
                "\n" + "=" * 70 + "\n"
                "ERROR: 必須環境変数が設定されていません\n"
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
