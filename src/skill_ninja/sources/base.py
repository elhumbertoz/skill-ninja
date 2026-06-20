"""Source adapter interface.

An adapter knows how to (a) *discover* the lightweight metadata for every skill in
a source, and (b) *fetch* a specific skill's SKILL.md, list its bundle files, read
one of them, or download the whole bundle. Each origin (GitHub, generic git,
agentskills.io, local FS) implements this interface; the catalog is origin-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

from ..config import Source
from ..models import SkillRecord


class SourceError(RuntimeError):
    """Raised when a source cannot be reached or returns unexpected data."""


@dataclass(slots=True)
class DiscoverResult:
    version: str
    """The pinned version (commit SHA) the metadata was read at."""

    records: list[SkillRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BundleFile:
    path: str  # relative to the skill root
    size: int | None = None


@dataclass(slots=True)
class BundleManifest:
    skill_id: str
    version: str
    dest: str
    files: list[BundleFile] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "version": self.version,
            "dest": self.dest,
            "files": [{"path": f.path, "size": f.size} for f in self.files],
        }


class SourceAdapter(ABC):
    source_type: str

    @abstractmethod
    def discover(self, source: Source) -> DiscoverResult:
        """Walk the source and return metadata records (no full bundles)."""

    @abstractmethod
    def get_skill_md(self, record: SkillRecord) -> str:
        """Return the text of the skill's SKILL.md at its pinned version."""

    @abstractmethod
    def list_files(self, record: SkillRecord) -> list[BundleFile]:
        """List the bundle files (relative paths) at the pinned version."""

    @abstractmethod
    def read_file(self, record: SkillRecord, rel_path: str) -> bytes:
        """Return the bytes of one bundled resource."""

    @abstractmethod
    def download(self, record: SkillRecord, dest: Path) -> BundleManifest:
        """Download the full bundle into ``dest`` and return its manifest."""
