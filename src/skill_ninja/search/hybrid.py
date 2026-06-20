"""Hybrid ranking — Reciprocal Rank Fusion (RRF) of multiple ranked id lists.

RRF combines rankings without needing to normalize disparate score scales (bm25 vs
cosine): each list contributes ``1 / (k + rank)`` to a document's score. Robust,
parameter-light, and the standard choice for lexical+vector fusion. Pure Python — no
heavy deps, so it's always importable.
"""

from __future__ import annotations

RRF_K = 60


def rrf_fuse(*ranked_lists: list[str], k: int = RRF_K) -> tuple[list[str], dict[str, float]]:
    """Fuse ranked id lists. Returns (ordered_ids, scores)."""
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, doc_id in enumerate(lst):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    ordered = sorted(scores, key=lambda d: scores[d], reverse=True)
    return ordered, scores
