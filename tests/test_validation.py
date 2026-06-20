from skill_ninja.index.parser import ParsedSkill
from skill_ninja.index.validation import DESCRIPTION_MAX, validate


def _parsed(**fm) -> ParsedSkill:
    return ParsedSkill(frontmatter=fm, body="")


def test_valid_skill():
    parsed = _parsed(name="pdf-processing", description="Handle PDFs.")
    res = validate(parsed, dir_name="pdf-processing")
    assert res.valid
    assert not res.errors


def test_name_must_be_lowercase_kebab():
    assert not validate(_parsed(name="PDF", description="x")).valid
    assert not validate(_parsed(name="-pdf", description="x")).valid
    assert not validate(_parsed(name="pdf--x", description="x")).valid


def test_missing_required_fields():
    assert not validate(_parsed(description="x")).valid
    assert not validate(_parsed(name="ok")).valid
    assert not validate(_parsed(name="ok", description="   ")).valid


def test_description_length_limit():
    res = validate(_parsed(name="ok", description="a" * (DESCRIPTION_MAX + 1)))
    assert not res.valid


def test_dir_name_mismatch_is_warning_not_error():
    res = validate(_parsed(name="xlsx", description="ok"), dir_name="spreadsheet")
    assert res.valid
    assert res.warnings
