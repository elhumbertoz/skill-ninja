"""Parse a SKILL.md file into frontmatter + body.

A SKILL.md is YAML frontmatter delimited by ``---`` fences, followed by Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

_FENCE = "---"


@dataclass(slots=True)
class ParsedSkill:
    frontmatter: dict
    body: str

    @property
    def name(self) -> str | None:
        v = self.frontmatter.get("name")
        return v if isinstance(v, str) else None

    @property
    def description(self) -> str | None:
        v = self.frontmatter.get("description")
        return v if isinstance(v, str) else None

    @property
    def license(self) -> str | None:
        v = self.frontmatter.get("license")
        return v if isinstance(v, str) else None


class SkillParseError(ValueError):
    """Raised when a SKILL.md cannot be parsed (missing/invalid frontmatter)."""


def parse_skill_md(text: str) -> ParsedSkill:
    """Split frontmatter and body. Raises SkillParseError if no frontmatter."""
    stripped = text.lstrip("﻿")  # tolerate a BOM
    if not stripped.lstrip().startswith(_FENCE):
        raise SkillParseError("SKILL.md must start with a '---' YAML frontmatter fence")

    # Find the opening fence, then the closing fence on its own line.
    lines = stripped.splitlines()
    # Locate first fence line
    start = next((i for i, ln in enumerate(lines) if ln.strip() == _FENCE), None)
    if start is None:
        raise SkillParseError("missing opening frontmatter fence")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].strip() == _FENCE),
        None,
    )
    if end is None:
        raise SkillParseError("missing closing frontmatter fence")

    fm_text = "\n".join(lines[start + 1 : end])
    body = "\n".join(lines[end + 1 :]).lstrip("\n")

    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        raise SkillParseError(f"invalid YAML frontmatter: {exc}") from exc

    if not isinstance(data, dict):
        raise SkillParseError("frontmatter must be a YAML mapping")

    return ParsedSkill(frontmatter=data, body=body)
