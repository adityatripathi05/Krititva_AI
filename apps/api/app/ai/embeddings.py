"""Embedding client abstraction (FR-4.5.5, NFR-5.1.5).

The pipeline talks to embedders through the :class:`EmbeddingClient` protocol so
tests can substitute :class:`FakeEmbeddingClient` — real Ollama is only invoked
in the tagged-release smoke suite, never in unit/PR CI (§CLAUDE.md §5).

The default runtime client routes through the LiteLLM gateway (OpenAI-compatible
``/v1/embeddings``), which fronts a local Ollama running ``nomic-embed-text``
(768-dim). No embedding call happens unless a user action triggers generation —
consistent with the zero-phone-home default (§CLAUDE.md §1.6).
"""

from __future__ import annotations

import hashlib
import struct
from typing import Protocol

import httpx

from app.config import get_settings

# nomic-embed-text v1.5 — the default local embedder (768-dim). Project-level
# model selection via llm_config lands with the config wiring; until then the
# pipeline uses this default.
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
PRIMARY_EMBEDDING_DIM = 768


class EmbeddingError(RuntimeError):
    """Raised when the embedding backend fails or returns malformed output."""


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Return one vector per input text, in order."""
        ...


class LiteLLMEmbeddingClient:
    """Calls the LiteLLM gateway's OpenAI-compatible embeddings endpoint."""

    def __init__(self, base_url: str | None = None, timeout: float = 60.0) -> None:
        self._base_url = (base_url or get_settings().litellm_url).rstrip("/")
        self._timeout = timeout

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        payload = {"model": model, "input": texts}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/v1/embeddings", json=payload)
                resp.raise_for_status()
                body = resp.json()
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"embedding request failed: {exc}") from exc
        data = body.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingError("embedding response shape mismatch")
        return [row["embedding"] for row in data]


class FakeEmbeddingClient:
    """Deterministic, offline embeddings for tests.

    The vector is derived from a hash of the text, so identical text yields an
    identical vector (useful for asserting write-back) without any network call
    or semantic model. Not meaningful for similarity ranking.
    """

    def __init__(self, dim: int = PRIMARY_EMBEDDING_DIM) -> None:
        self._dim = dim

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        out: list[float] = []
        counter = 0
        while len(out) < self._dim:
            digest = hashlib.sha256(f"{text}:{counter}".encode()).digest()
            # 8 float32s per 32-byte digest.
            for i in range(0, 32, 4):
                if len(out) >= self._dim:
                    break
                (raw,) = struct.unpack("<I", digest[i : i + 4])
                out.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
            counter += 1
        return out
