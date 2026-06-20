"""Validate SKILL.md frontmatter against the Agent Skills standard.

Rules mirror agent-skills-reference.md §4.2 (the ``skills-ref`` reference rules):

- ``name``: required, 1-64 chars, lowercase ``a-z``/``0-9``/``-`` only, no leading
  or trailing hyphen, no consecutive hyphens, must match the parent directory name.
- ``description``: required, 1-1024 chars, non-empty.
- ``compatibility`` (optional): 1-500 chars.
- ``license`` (optional): free-form string.
- ``metadata`` (optional): mapping of string -> string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .parser import ParsedSkill

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate(parsed: ParsedSkill, *, dir_name: str | None = None) -> ValidationResult:
    fm = parsed.frontmatter
    errors: list[str] = []
    warnings: list[str] = []

    # name -----------------------------------------------------------------
    name = fm.get("name")
    if not name or not isinstance(name, str):
        errors.append("`name` is required and must be a string")
    else:
        if len(name) > NAME_MAX:
            errors.append(f"`name` must be at most {NAME_MAX} characters (got {len(name)})")
        if not NAME_RE.match(name):
            errors.append(
                "`name` must be lowercase a-z/0-9 and single hyphens only, "
                "with no leading, trailing, or consecutive hyphens"
            )
        if dir_name is not None and name != dir_name:
            # A warning, not an error: monorepos occasionally diverge and we still
            # want the record indexable. The standard recommends they match.
            warnings.append(f"`name` ({name!r}) does not match directory ({dir_name!r})")

    # description ----------------------------------------------------------
    description = fm.get("description")
    if not description or not isinstance(description, str) or not description.strip():
        errors.append("`description` is required and must be a non-empty string")
    elif len(description) > DESCRIPTION_MAX:
        errors.append(
            f"`description` must be at most {DESCRIPTION_MAX} characters (got {len(description)})"
        )

    # compatibility (optional) --------------------------------------------
    compatibility = fm.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str):
            errors.append("`compatibility` must be a string")
        elif len(compatibility) > COMPATIBILITY_MAX:
            errors.append(
                f"`compatibility` must be at most {COMPATIBILITY_MAX} characters "
                f"(got {len(compatibility)})"
            )

    # metadata (optional) --------------------------------------------------
    metadata = fm.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        errors.append("`metadata` must be a mapping")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)
