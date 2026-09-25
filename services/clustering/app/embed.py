"""Text embedders. Vectors are L2-normalised so dot product = cosine similarity."""
from __future__ import annotations

import logging
from typing import Protocol

import httpx
import numpy as np

from .config import get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    device: str

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


class OllamaEmbedder:
    """Runs on the Mac's GPU via the native Ollama app (Docker on macOS cannot reach MPS directly)."""

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.name = f"ollama:{model}"
        self.device = "apple-gpu (metal, via ollama)"

    def embed(self, texts: list[str]) -> np.ndarray:
        # nomic-embed-text is trained with task prefixes; "clustering:" is the right one here.
        prefix = "clustering: " if "nomic" in self.model else ""
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            r = httpx.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": [prefix + t for t in texts[i : i + 64]]}, timeout=300)
            r.raise_for_status()
            out += r.json()["embeddings"]
        return _normalise(np.asarray(out, dtype=np.float32))


class SentenceTransformerEmbedder:
    """PyTorch on MPS (Apple Silicon), CUDA or CPU - for running this service natively."""

    def __init__(self, model: str, device: str = "auto"):
        import torch
        from sentence_transformers import SentenceTransformer

        if device == "auto":
            device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.name = f"st:{model}"
        self.model = SentenceTransformer(model, device=device)

    def embed(self, texts: list[str]) -> np.ndarray:
        return _normalise(np.asarray(self.model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32))


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        s = get_settings()
        if s.embed_backend == "sentence-transformers":
            _embedder = SentenceTransformerEmbedder(s.st_model, s.st_device)
        else:
            _embedder = OllamaEmbedder(s.ollama_base_url, s.ollama_embed_model)
        log.info("embedder %s on %s", _embedder.name, _embedder.device)
    return _embedder


def article_text(title: str, summary: str | None) -> str:
    return f"{title}. {(summary or '')[:600]}".strip()
