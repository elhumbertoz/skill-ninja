"""Optional semantic backend — embeddings via fastembed + brute-force cosine.

This module is import-safe even when the ``skill-ninja[semantic]`` extra is absent:
heavy deps (``fastembed``, ``numpy``) are imported lazily inside functions and any
``ImportError`` is surfaced as :class:`SemanticUnavailable`, so the catalog can fall
back to lexical search cleanly.

Vector store: we keep one normalized float32 embedding per skill as a SQLite BLOB and
score queries with brute-force cosine. At this catalog's scale (hundreds of skills)
that is effectively instant and avoids the loadable-extension requirement of
``sqlite-vec`` — keeping the install portable (the project's north star).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

_INSTALL_HINT = (
    "semantic search needs the optional extra — install with "
    "`uvx --from 'skill-ninja[semantic]' skill-ninja` (or `pip install "
    "'skill-ninja[semantic]'`), or set SKILL_NINJA_SEARCH=lexical."
)


class SemanticUnavailable(RuntimeError):
    """Raised when semantic deps (fastembed/numpy) or a model are unavailable."""


@runtime_checkable
class Embedder(Protocol):
    model_name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SemanticUnavailable(_INSTALL_HINT) from exc
    return np


class FastEmbedEmbedder:
    """Wraps fastembed's ONNX TextEmbedding (no PyTorch). Lazy-loads the model."""

    def __init__(self, model_name: str):
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise SemanticUnavailable(_INSTALL_HINT) from exc
        self.model_name = model_name
        try:
            self._model = TextEmbedding(model_name=model_name)
        except Exception as exc:  # bad model name, download/network failure, etc.
            raise SemanticUnavailable(
                f"could not load embedding model {model_name!r}: {exc}"
            ) from exc
        self.dim = len(self._embed_one("probe"))

    def _embed_one(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._model.embed([text])))]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(x) for x in v] for v in self._model.embed(list(texts))]


def load_embedder(model_name: str) -> Embedder:
    """Construct the default (fastembed) embedder, or raise SemanticUnavailable."""
    return FastEmbedEmbedder(model_name)


def normalize_to_blob(vec: list[float]) -> bytes:
    """L2-normalize a vector and pack it as float32 bytes for storage."""
    np = _numpy()
    a = np.asarray(vec, dtype="float32")
    norm = float(np.linalg.norm(a))
    if norm > 0:
        a = a / norm
    return a.astype("float32").tobytes()


def cosine_topk(
    query_vec: list[float], stored: list[tuple[str, bytes]], top_k: int
) -> list[tuple[str, float]]:
    """Rank stored (already-normalized) vectors by cosine similarity to the query."""
    np = _numpy()
    if not stored:
        return []
    q = np.asarray(query_vec, dtype="float32")
    qn = float(np.linalg.norm(q))
    if qn > 0:
        q = q / qn
    ids = [sid for sid, _ in stored]
    matrix = np.vstack([np.frombuffer(blob, dtype="float32") for _, blob in stored])
    sims = matrix @ q  # both sides unit-normalized → cosine
    order = np.argsort(-sims)[:top_k]
    return [(ids[i], float(sims[i])) for i in order]
