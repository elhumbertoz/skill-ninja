"""FTS5 query construction and ranking weights — the default lexical backend.

Kept separate from storage so the *search semantics* (how a free-text query maps
to an FTS5 expression, how columns are weighted) live in one place and an
alternative backend (e.g. vectors, Phase 3) can be slotted in beside it.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# bm25 weights, one per FTS5 column in declared order:
#   (skill_id [UNINDEXED, ignored], name, description, category)
# name dominates triggering; description is keyword-rich and matters a lot.
BM25_WEIGHTS: tuple[float, float, float, float] = (0.0, 5.0, 3.0, 2.0)


def build_match_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    Tokens are lowercased and reduced to ``[a-z0-9]`` runs, so no FTS5
    metacharacter (``"``, ``*``, ``(``, ``:``, ``-`` …) can survive to break the
    parser or be interpreted as an operator. Each token becomes a prefix term and
    they are OR-combined for recall; bm25 then ranks by match quality. Returns an
    empty string when the query has no usable tokens (caller should short-circuit).
    """
    tokens = [t for t in _TOKEN_RE.findall(query.lower()) if len(t) >= 2]
    if not tokens:
        return ""
    return " OR ".join(f"{t}*" for t in tokens)
