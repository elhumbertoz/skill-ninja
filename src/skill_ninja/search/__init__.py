"""Search engine. Lexical (SQLite FTS5) by default; semantic/hybrid are opt-in.

Only the lexical pieces are imported here — the semantic module (``semantic.py``)
pulls optional heavy deps and is imported lazily by the catalog so this package
stays import-safe without the ``[semantic]`` extra.
"""

from .fts import BM25_WEIGHTS, build_match_query
from .hybrid import rrf_fuse

__all__ = ["BM25_WEIGHTS", "build_match_query", "rrf_fuse"]
