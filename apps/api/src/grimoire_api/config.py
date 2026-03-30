"""Configuration settings."""

import os
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # API Keys
    JINA_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Database
    DATABASE_PATH: str = "./grimoire.db"

    # Weaviate
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080

    # File Storage
    JSON_STORAGE_PATH: str = "./data/json"

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
            "GOOGLE_API_KEY": self.GOOGLE_API_KEY,
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
                "  3. source scripts/load_secrets.sh を実行してシークレットを展開\n"
                "  4. アプリケーションを再起動\n\n"
                "詳細は docs/development.md を参照してください。\n"
                "=" * 70
            )
            print(error_msg, file=sys.stderr)
            sys.exit(1)


settings = Settings()
