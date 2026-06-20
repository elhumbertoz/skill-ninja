import pytest

from skill_ninja.index.parser import SkillParseError, parse_skill_md

VALID = """---
name: xlsx
description: "Use when editing spreadsheets, .xlsx, .csv files."
license: Proprietary. LICENSE.txt has complete terms
---

# Requirements

Body content here.
"""


def test_parse_extracts_frontmatter_and_body():
    parsed = parse_skill_md(VALID)
    assert parsed.name == "xlsx"
    assert parsed.description.startswith("Use when editing spreadsheets")
    assert parsed.license.startswith("Proprietary")
    assert parsed.body.startswith("# Requirements")


def test_parse_tolerates_bom():
    parsed = parse_skill_md("﻿" + VALID)
    assert parsed.name == "xlsx"


def test_parse_requires_frontmatter():
    with pytest.raises(SkillParseError):
        parse_skill_md("# no frontmatter here\n")


def test_parse_requires_closing_fence():
    with pytest.raises(SkillParseError):
        parse_skill_md("---\nname: x\ndescription: y\n")
