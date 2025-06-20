"""Configuration settings."""

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

    class Config:
        env_file = ".env"


settings = Settings()
