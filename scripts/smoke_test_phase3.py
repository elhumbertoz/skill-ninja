"""Live Phase 3 smoke test: lexical vs semantic vs hybrid over real skills.

Indexes anthropics/skills (via the GitHub adapter) into a throwaway data dir, then
runs paraphrased queries through each backend. The first semantic search downloads
the embedding model (~130 MB) and embeds the catalog. Requires the [semantic] extra.

    .venv\\Scripts\\python.exe scripts\\smoke_test_phase3.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from skill_ninja.catalog import Catalog
from skill_ninja.config import DEFAULT_SOURCES, Config, Source

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Paraphrased queries — deliberately avoid the skills' own keywords so lexical search
# is challenged and the value of embeddings shows.
QUERIES = [
    "put together a slide deck for monday's meeting",
    "crunch some numbers in a workbook",
    "turn my notes into a polished word document",
]


def _cfg(data_dir: Path, backend: str) -> Config:
    cfg = Config(
        data_dir=data_dir,
        sources=[Source(type=t, url=u) for (t, u) in DEFAULT_SOURCES],
        search_backend=backend,
    )
    cfg.ensure_dirs()
    return cfg


def _show(cat: Catalog, label: str) -> None:
    print(f"\n=== backend: {label}  (effective: {cat.effective_backend()}) ===")
    for q in QUERIES:
        hits = cat.search(q, top_k=3)
        names = ", ".join(f"{h['name']}({h['score']})" for h in hits)
        print(f"  {q!r}\n      -> {names}")


def main() -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="skill-ninja-p3-")) / "data"
    print(f"[i] scratch data dir: {data_dir}")

    # 1) Lexical baseline (also performs the one-time GitHub indexing).
    with Catalog(_cfg(data_dir, "lexical")) as cat:
        cat.ensure_indexed()
        print(f"[i] indexed {cat.db.count_skills()} skills")
        _show(cat, "lexical")

    # 2) Semantic — first search downloads the model and embeds the catalog.
    print("\n[i] loading embedding model + embedding catalog (first run downloads ~130MB)…")
    with Catalog(_cfg(data_dir, "semantic")) as cat:
        cat.search("warm up")  # triggers ensure_embedded
        print(f"[i] vectors stored: {cat.db.vector_count()}")
        _show(cat, "semantic")

    # 3) Hybrid — fuses lexical + vector.
    with Catalog(_cfg(data_dir, "hybrid")) as cat:
        _show(cat, "hybrid")

    print("\n[OK] Phase 3 live smoke test passed ✅")


if __name__ == "__main__":
    main()
