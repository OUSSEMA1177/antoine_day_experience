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
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_fallback_model: str = ""
    llm_max_tokens: int = 512
    llm_timeout: int = 90
    llm_retry_max: int = 1
    llm_retry_delay: float = 2.0
    llm_history_limit: int = 8
    llm_catalog_inject_limit: int = 4
    llm_compact_prompt: bool = True
    llm_log_usage: bool = True
    llm_nlu_extract: bool = True
    support_email: str = "support@day-experience-demo.com"

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
