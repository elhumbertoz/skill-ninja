from skill_ninja.models import SkillRecord
from skill_ninja.search.fts import build_match_query
from skill_ninja.storage.db import Database


def _rec(name, description, **kw) -> SkillRecord:
    return SkillRecord(
        id=kw.get("id", f"github/test/repo/skills/{name}"),
        name=name,
        description=description,
        category=kw.get("category", "skills"),
        source_type="github",
        source_url="https://github.com/test/repo",
        repo_path=f"skills/{name}",
        version="abc123",
        license=kw.get("license"),
        validated=True,
    )


def test_build_match_query_sanitizes():
    assert build_match_query('edit "my.xlsx" file!') == "edit* OR my* OR xlsx* OR file*"
    assert build_match_query("---") == ""
    assert build_match_query("  ") == ""


def test_search_ranks_relevant_skill_first(tmp_path):
    db = Database(tmp_path / "catalog.db")
    db.upsert_skills([
        _rec("xlsx", "Edit spreadsheets, xlsx, csv, tabular data."),
        _rec("pdf", "Extract text and fill forms in PDF documents."),
        _rec("webapp-testing", "Test web applications in a browser."),
    ])
    assert db.count_skills() == 3

    hits = db.search("spreadsheet xlsx", top_k=5)
    assert hits, "expected at least one hit"
    assert hits[0][0].name == "xlsx"


def test_search_filters_by_category(tmp_path):
    db = Database(tmp_path / "catalog.db")
    db.upsert_skills([
        _rec("xlsx", "spreadsheet editing", category="document"),
        _rec("pdf", "pdf spreadsheet-like tables", category="other"),
    ])
    hits = db.search("spreadsheet", category="document")
    assert [h[0].name for h in hits] == ["xlsx"]


def test_upsert_is_idempotent(tmp_path):
    db = Database(tmp_path / "catalog.db")
    rec = _rec("xlsx", "v1 spreadsheet")
    db.upsert_skills([rec])
    rec.description = "v2 spreadsheet updated"
    db.upsert_skills([rec])
    assert db.count_skills() == 1
    assert db.get_skill(rec.id).description == "v2 spreadsheet updated"
    # FTS stays in sync (no duplicate rows)
    hits = db.search("spreadsheet")
    assert len(hits) == 1
