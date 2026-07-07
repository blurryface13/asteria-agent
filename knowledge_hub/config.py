"""Env-driven configuration, following the same .env conventions as the
rest of asteria-agent (DATABASE_URL, OLLAMA_BASE_URL, DEEPSEEK_API_KEY)."""
import os
from dataclasses import dataclass, field


def _env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return value


@dataclass
class KHConfig:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    ollama_base_url: str = field(default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434"))
    embedding_model: str = field(default_factory=lambda: _env("KH_EMBEDDING_MODEL", "bge-m3"))
    embedding_dim: int = 1024
    # chunking
    chunk_size: int = int(os.environ.get("KH_CHUNK_SIZE", "1000"))
    chunk_overlap: int = int(os.environ.get("KH_CHUNK_OVERLAP", "150"))
    # retrieval
    default_collection: str = "watermark"
    rrf_k: int = int(os.environ.get("KH_RRF_K", "60"))
    # rerank (LLM-based via DeepSeek; falls back to no-op if key missing)
    deepseek_api_key: str | None = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY"))
    rerank_model: str = "deepseek-chat"
