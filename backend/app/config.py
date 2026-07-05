"""Application settings from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:5500"

    groq_api_key: str = ""
    gemini_api_key: str = ""
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_fallback_model: str = ""
    llm_max_tokens: int = 1024
    llm_timeout: int = 90
    llm_retry_max: int = 2
    llm_retry_delay: float = 2.0

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
