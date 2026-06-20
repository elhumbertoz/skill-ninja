"""Data model for skill records (see CLAUDE.md §8).

A ``SkillRecord`` is a row in the lightweight metadata index (layer 1). The full
bundle (layer 2) is materialized on demand by the cache manager; ``local_path`` is
set once a skill has been downloaded.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

SourceType = str  # "github" | "git" | "agentskills" | "local"


@dataclass(slots=True)
class SkillRecord:
    """A single skill as it appears in the metadata index."""

    id: str
    """Stable identifier: ``<source_type>/<owner>/<repo>/<skill-path>``."""

    name: str
    """``name`` from the SKILL.md frontmatter."""

    description: str
    """``description`` from the frontmatter — the primary text searched."""

    source_type: SourceType
    source_url: str
    """Origin URL/path of the source the skill was discovered in."""

    repo_path: str
    """Path of the skill directory inside the repo (for monorepos)."""

    version: str
    """Pinned commit SHA (or tag) the metadata/bundle was indexed at."""

    category: str = ""
    """Derived from repo structure (parent folder) — never model-classified."""

    tags: list[str] = field(default_factory=list)
    license: str | None = None
    local_path: str | None = None
    """Filesystem path if the bundle has been downloaded (layer 2)."""

    validated: bool = False
    """Whether the SKILL.md passed validation against the standard."""

    last_indexed: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self, *, downloaded: bool | None = None) -> dict:
        """Compact view returned in search results / tool output."""
        data = {
            "skill_id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "license": self.license,
            "version": self.version,
            "validated": self.validated,
            "downloaded": (self.local_path is not None) if downloaded is None else downloaded,
        }
        return data
