"""Runtime configuration: storage paths, registered sources, optional API keys.

Defaults follow the design north star — works with no API keys, stores everything
under the per-user data directory (overridable via ``SKILL_NINJA_DATA_DIR``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "skill-ninja"

# The default source seeded on first run. Lazy auto-indexed on the first search.
DEFAULT_SOURCES: tuple[Source, ...] = (
    # owner/repo form is enough; the GitHub adapter resolves the default branch.
    # url kept as the canonical https form for display/identification.
    ("github", "https://github.com/anthropics/skills"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """A registered origin to discover skills from."""

    type: str  # "github" | "git" | "agentskills" | "local"
    url: str

    @property
    def id(self) -> str:
        return f"{self.type}:{self.url}"


@dataclass(slots=True)
class Config:
    data_dir: Path
    sources: list[Source]
    github_token: str | None = None
    user_agent: str = f"{APP_NAME}/0.1 (+https://github.com/elhumbertoz/skill-ninja)"

    # Derived paths -------------------------------------------------------
    @property
    def db_path(self) -> Path:
        return self.data_dir / "catalog.db"

    @property
    def store_dir(self) -> Path:
        """Default destination for downloaded skill bundles (layer 2)."""
        return self.data_dir / "skills"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.store_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Build a Config from environment + defaults."""
    data_dir_env = os.environ.get("SKILL_NINJA_DATA_DIR")
    data_dir = Path(data_dir_env) if data_dir_env else Path(user_data_dir(APP_NAME))

    token = (
        os.environ.get("SKILL_NINJA_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or None
    )

    sources = [Source(type=t, url=u) for (t, u) in DEFAULT_SOURCES]

    cfg = Config(data_dir=data_dir, sources=sources, github_token=token)
    cfg.ensure_dirs()
    return cfg
