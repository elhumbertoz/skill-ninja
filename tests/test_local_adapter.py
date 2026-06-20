from pathlib import Path

from skill_ninja.config import Source
from skill_ninja.sources.local import LocalAdapter


def _make_skill(root: Path, name: str, desc: str, extra: str | None = None) -> None:
    d = root / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\nbody\n", encoding="utf-8"
    )
    if extra is not None:
        (d / "references").mkdir()
        (d / "references" / "notes.md").write_text(extra, encoding="utf-8")


def test_local_discover_and_fetch(tmp_path):
    _make_skill(tmp_path, "alpha", "Alpha skill for spreadsheets", extra="ref notes")
    _make_skill(tmp_path, "beta", "Beta skill for pdfs")
    adapter = LocalAdapter()
    src = Source(type="local", url=str(tmp_path))

    res = adapter.discover(src)
    assert sorted(r.name for r in res.records) == ["alpha", "beta"]

    alpha = next(r for r in res.records if r.name == "alpha")
    assert alpha.repo_path == "skills/alpha"
    assert alpha.category == "skills"
    assert alpha.source_type == "local"
    assert "name: alpha" in adapter.get_skill_md(alpha)

    files = [f.path for f in adapter.list_files(alpha)]
    assert "SKILL.md" in files
    assert "references/notes.md" in files
    assert adapter.read_file(alpha, "references/notes.md") == b"ref notes"

    manifest = adapter.download(alpha, tmp_path / "store")
    assert (Path(manifest.dest) / "SKILL.md").is_file()
    assert (Path(manifest.dest) / "references" / "notes.md").is_file()
    assert (Path(manifest.dest) / ".skill-ninja.json").is_file()


def test_local_version_changes_when_content_changes(tmp_path):
    _make_skill(tmp_path, "alpha", "Alpha")
    adapter = LocalAdapter()
    src = Source(type="local", url=str(tmp_path))
    v1 = adapter.latest_version(src)
    _make_skill(tmp_path, "beta", "Beta")
    v2 = adapter.latest_version(src)
    assert v1 != v2


def test_local_missing_dir_errors():
    from skill_ninja.sources.base import SourceError

    adapter = LocalAdapter()
    src = Source(type="local", url="C:/definitely/not/a/real/dir/xyz")
    try:
        adapter.discover(src)
    except SourceError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected SourceError for missing dir")
