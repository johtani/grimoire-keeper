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

    # Database
    DATABASE_PATH: str = "./grimoire.db"

    # Weaviate
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_COLLECTION_NAME: str = "GrimoireChunk"

    # File Storage
    JSON_STORAGE_PATH: str = "./data/json"

    # Build Info
    GIT_COMMIT: str = "unknown"
    BUILD_DATE: str = "unknown"

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"),
        extra="ignore",  # 余分な環境変数を無視
    )

    def validate_required_vars(self) -> None:
        """必須環境変数の検証.

        Raises:
            SystemExit: 必須環境変数が設定されていない場合
        """
        required_vars = {
            "JINA_API_KEY": self.JINA_API_KEY,
            "OPENAI_API_KEY": self.OPENAI_API_KEY,
        }

        missing_vars = [name for name, value in required_vars.items() if not value]

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
                "詳細は docs/development.md を参照してください。\n"
                "=" * 70
            )
            logger.error(error_msg)
            sys.exit(1)


settings = Settings()
