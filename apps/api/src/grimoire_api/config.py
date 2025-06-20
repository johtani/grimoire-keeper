"""Configuration settings."""

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # API Keys
    JINA_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Database
    DATABASE_PATH: str = "./grimoire.db"

    # Weaviate
    WEAVIATE_URL: str = "http://localhost:8080"

    # File Storage
    JSON_STORAGE_PATH: str = "./data/json"

    model_config = ConfigDict(
        env_file=".env",
        extra="ignore",  # 余分な環境変数を無視
    )


settings = Settings()
