from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM: "auto" tries Ollama, then Claude (if a key is set), then the rules-only fallback.
    llm_provider: str = "auto"  # auto | ollama | anthropic | none
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_num_ctx: int = 8192
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"
    llm_concurrency: int = 3

    # News sources
    finnhub_api_key: str = ""
    sec_user_agent: str = "StockCompass personal-research contact@example.com"
    news_lookback_days: int = 4
    max_articles_per_symbol: int = 6
    max_articles_per_topic: int = 8
    min_source_trust: float = 0.4


@lru_cache
def get_settings() -> Settings:
    return Settings()
