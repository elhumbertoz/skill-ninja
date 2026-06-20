"""Search engine. Lexical (SQLite FTS5) by default; vectors are a Phase 3 add-on."""

from .fts import BM25_WEIGHTS, build_match_query

__all__ = ["BM25_WEIGHTS", "build_match_query"]
