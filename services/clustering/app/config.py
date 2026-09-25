from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Its own database (a separate Postgres with pgvector), not the main app database.
    social_database_url: str = "postgresql+psycopg://social:social@localhost:5433/social"
    backend_url: str = "http://localhost:8000"

    # Embeddings. "ollama" runs natively on the Mac GPU (Metal) and is reachable from Docker;
    # "sentence-transformers" uses PyTorch directly (MPS on Apple Silicon) when this service runs natively.
    embed_backend: str = "ollama"  # ollama | sentence-transformers
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_embed_model: str = "nomic-embed-text"
    st_model: str = "BAAI/bge-base-en-v1.5"
    st_device: str = "auto"  # auto -> mps / cuda / cpu

    # Cluster headlines & summaries (only for new or changed clusters).
    llm_provider: str = "auto"  # auto | ollama | anthropic | none
    ollama_model: str = "qwen2.5:7b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5"

    # Algorithm
    window_days: int = 14
    min_cluster_size: int = 3
    min_samples: int = 2
    umap_neighbors: int = 12
    umap_cluster_dims: int = 5
    merge_similarity: float = 0.92  # merge clusters whose centroids are this similar (same story)
    random_state: int = 42
    platform: str = "News"  # later: Twitter / LinkedIn / Reddit connectors


@lru_cache
def get_settings() -> Settings:
    return Settings()
