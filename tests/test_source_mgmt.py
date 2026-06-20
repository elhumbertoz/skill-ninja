from pathlib import Path

from skill_ninja.catalog import Catalog
from skill_ninja.config import Config


def _make_skill(root: Path, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n", encoding="utf-8"
    )


def _catalog(tmp_path: Path) -> Catalog:
    # No default sources → no network; everything stays local and offline.
    cfg = Config(data_dir=tmp_path / "data", sources=[])
    cfg.ensure_dirs()
    return Catalog(cfg)


def test_add_local_source_then_search(tmp_path):
    skills = tmp_path / "myskills"
    _make_skill(skills, "alpha", "Alpha skill for spreadsheets and tabular data")
    _make_skill(skills, "beta", "Beta skill for pdf forms")

    cat = _catalog(tmp_path)
    try:
        added = cat.add_source(str(skills))
        assert added["type"] == "local"
        assert added["added"] is True
        # idempotent
        assert cat.add_source(str(skills))["already_present"] is True

        # search triggers lazy auto-index of the registered local source
        results = cat.search("spreadsheet")
        assert any(r["name"] == "alpha" for r in results)

        # list_sources reflects the registered + indexed source with a skill count
        srcs = cat.list_sources()
        assert len(srcs) == 1
        assert srcs[0]["type"] == "local"
        assert srcs[0]["indexed"] is True
        assert srcs[0]["skills"] == 2
    finally:
        cat.close()


def test_incremental_refresh_skips_unchanged(tmp_path):
    skills = tmp_path / "myskills"
    _make_skill(skills, "alpha", "Alpha skill")
    cat = _catalog(tmp_path)
    try:
        cat.add_source(str(skills))
        cat.ensure_indexed()  # first index
        out = cat.refresh()  # nothing changed
        assert out["sources"][0]["skipped"] is True
        # force re-indexes
        forced = cat.refresh(force=True)
        assert forced["sources"][0]["skipped"] is False
    finally:
        cat.close()


def test_remove_source_with_purge(tmp_path):
    skills = tmp_path / "myskills"
    _make_skill(skills, "alpha", "Alpha skill for spreadsheets")
    cat = _catalog(tmp_path)
    try:
        added = cat.add_source(str(skills))
        assert cat.search("spreadsheet")  # indexes
        rem = cat.remove_source(added["url"], purge=True)
        assert rem["purged_skills"] >= 1
        assert cat.list_sources() == []
        assert cat.search("spreadsheet") == []
    finally:
        cat.close()


def test_infer_type_for_github_and_git():
    assert Catalog._infer_type("https://github.com/anthropics/skills") == "github"
    assert Catalog._infer_type("https://gitlab.com/foo/bar.git") == "git"
    assert Catalog._infer_type("git@example.com:foo/bar.git") == "git"
