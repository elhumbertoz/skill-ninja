"""Semantic/hybrid backend tests using a deterministic fake embedder (no model)."""

from pathlib import Path

import pytest

from skill_ninja.catalog import Catalog
from skill_ninja.config import Config
from skill_ninja.search.hybrid import rrf_fuse

# Fixed vocabulary → bag-of-words vectors. Texts sharing words point the same way,
# so cosine ranks them together — enough to exercise the vector pipeline.
VOCAB = ["spreadsheet", "xlsx", "csv", "pdf", "form", "web", "test", "sql", "lint", "report"]


class FakeEmbedder:
    model_name = "fake-bow"
    dim = len(VOCAB)

    def embed(self, texts):
        out = []
        for text in texts:
            low = text.lower()
            out.append([float(low.count(word)) for word in VOCAB])
        return out


def _make_skill(root: Path, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n", encoding="utf-8"
    )


def _catalog(tmp_path: Path, backend: str, embedder=None) -> Catalog:
    cfg = Config(data_dir=tmp_path / "data", sources=[], search_backend=backend)
    cfg.ensure_dirs()
    return Catalog(cfg, embedder=embedder)


# -- pure pieces ----------------------------------------------------------
def test_rrf_fuse_rewards_agreement():
    lexical = ["a", "b", "c"]
    vector = ["b", "a", "d"]
    ordered, scores = rrf_fuse(lexical, vector)
    # 'a' (ranks 0 & 1) and 'b' (ranks 1 & 0) appear in both → outrank single-list ids
    assert set(ordered[:2]) == {"a", "b"}
    assert scores["a"] > scores["c"]
    assert scores["b"] > scores["d"]


def test_cosine_topk_ranks_similar_first():
    semantic = pytest.importorskip("skill_ninja.search.semantic")
    a = semantic.normalize_to_blob([1.0, 0.0, 0.0])
    b = semantic.normalize_to_blob([0.0, 1.0, 0.0])
    c = semantic.normalize_to_blob([0.9, 0.1, 0.0])
    hits = semantic.cosine_topk([1.0, 0.0, 0.0], [("a", a), ("b", b), ("c", c)], 3)
    assert hits[0][0] == "a"
    assert hits[1][0] == "c"  # closer to the query than the orthogonal 'b'


# -- catalog with the fake embedder --------------------------------------
def test_semantic_search_ranks_by_embedding(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "sql-linter", "Lint and format SQL queries")
    _make_skill(skills, "pdf-tool", "Fill PDF form fields")
    cat = _catalog(tmp_path, "semantic", embedder=FakeEmbedder())
    try:
        cat.add_source(str(skills))
        results = cat.search("sql lint")
        assert cat.effective_backend() == "semantic"
        assert results[0]["name"] == "sql-linter"
        assert cat.db.vector_count() == 2
    finally:
        cat.close()


def test_hybrid_search_combines_signals(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "sql-linter", "Lint and format SQL queries")
    _make_skill(skills, "pdf-tool", "Fill PDF form fields")
    cat = _catalog(tmp_path, "hybrid", embedder=FakeEmbedder())
    try:
        cat.add_source(str(skills))
        results = cat.search("pdf form")
        assert cat.effective_backend() == "hybrid"
        assert results[0]["name"] == "pdf-tool"
    finally:
        cat.close()


def test_reembeds_when_skill_version_changes(tmp_path):
    skills = tmp_path / "skills"
    _make_skill(skills, "sql-linter", "Lint and format SQL queries")
    cat = _catalog(tmp_path, "semantic", embedder=FakeEmbedder())
    try:
        cat.add_source(str(skills))
        cat.search("sql")
        assert not cat.db.skills_needing_embedding()  # all embedded
        # change content → version (file hash) changes → needs re-embed
        (skills / "sql-linter" / "SKILL.md").write_text(
            "---\nname: sql-linter\ndescription: Lint SQL and CSV spreadsheet data\n---\n",
            encoding="utf-8",
        )
        cat.refresh(force=True)
        assert cat.db.skills_needing_embedding()  # stale vector detected
        cat.ensure_embedded()
        assert not cat.db.skills_needing_embedding()
    finally:
        cat.close()


def test_falls_back_to_lexical_when_unavailable(tmp_path, monkeypatch):
    from skill_ninja.search import semantic

    def boom(model):
        raise semantic.SemanticUnavailable("extra not installed")

    monkeypatch.setattr(semantic, "load_embedder", boom)

    skills = tmp_path / "skills"
    _make_skill(skills, "xlsx", "Edit spreadsheet and csv data")
    cat = _catalog(tmp_path, "semantic")  # no injected embedder → resolves via load_embedder
    try:
        cat.add_source(str(skills))
        results = cat.search("spreadsheet")
        assert cat.effective_backend() == "lexical"
        assert cat.embedder_error
        assert any(r["name"] == "xlsx" for r in results)
    finally:
        cat.close()
