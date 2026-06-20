"""Generic git source adapter — shallow-clone any git URL and index its skills.

Discovery walks a shallow clone for ``SKILL.md`` files. The current version is read
cheaply with ``git ls-remote`` (no clone) for incremental refresh. Requires the
``git`` CLI on PATH.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ..config import Source
from ..index.parser import SkillParseError, parse_skill_md
from ..index.validation import validate
from ..models import SkillRecord
from .base import (
    BundleFile,
    BundleManifest,
    DiscoverResult,
    SourceAdapter,
    SourceError,
    write_bundle_manifest,
)

_SLUG_STRIP = re.compile(r"^(https?://|git@|ssh://git@)")
_SLUG_SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(url: str) -> str:
    """A readable, stable identifier for a git URL (host/path, no scheme/.git)."""
    s = _SLUG_STRIP.sub("", url.strip()).replace(":", "/")
    if s.endswith(".git"):
        s = s[:-4]
    return s.strip("/")


def _dir_slug(url: str) -> str:
    return _SLUG_SANITIZE.sub("_", _slug(url)) or "repo"


class GitAdapter(SourceAdapter):
    source_type = "git"

    def __init__(self, cache_dir: Path):
        self._cache_dir = Path(cache_dir)

    # -- git plumbing -----------------------------------------------------
    def _git(self, *args: str, cwd: Path | None = None) -> str:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError as exc:
            raise SourceError(
                "git CLI not found on PATH; the generic-git source requires git."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise SourceError(f"git {args[0]} timed out") from exc
        if proc.returncode != 0:
            raise SourceError(f"git {args[0]} failed: {proc.stderr.strip()[:200]}")
        return proc.stdout

    def _clone_dir(self, source: Source) -> Path:
        return self._cache_dir / _dir_slug(source.url)

    def _ensure_clone(self, source: Source) -> tuple[Path, str]:
        """Clone (shallow) or update the cached clone to the remote default HEAD."""
        repo_dir = self._clone_dir(source)
        if (repo_dir / ".git").is_dir():
            self._git("fetch", "--depth", "1", "origin", "HEAD", cwd=repo_dir)
            self._git("reset", "--hard", "FETCH_HEAD", cwd=repo_dir)
        else:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            if repo_dir.exists():
                shutil.rmtree(repo_dir, ignore_errors=True)
            self._git("clone", "--depth", "1", source.url, str(repo_dir))
        head = self._git("rev-parse", "HEAD", cwd=repo_dir).strip()
        return repo_dir, head

    # -- adapter API ------------------------------------------------------
    def latest_version(self, source: Source) -> str:
        out = self._git("ls-remote", source.url, "HEAD")
        line = out.strip().splitlines()[0] if out.strip() else ""
        sha = line.split("\t", 1)[0] if line else ""
        if not sha:
            raise SourceError(f"could not resolve HEAD for {source.url}")
        return sha

    def discover(self, source: Source, version: str | None = None) -> DiscoverResult:
        repo_dir, head = self._ensure_clone(source)
        sha = version or head
        slug = _slug(source.url)

        records: list[SkillRecord] = []
        warnings: list[str] = []
        for md in sorted(repo_dir.rglob("SKILL.md")):
            if ".git" in md.parts:
                continue
            skill_dir = md.parent
            repo_path = skill_dir.relative_to(repo_dir).as_posix()
            dir_name = skill_dir.name
            category = (
                skill_dir.parent.relative_to(repo_dir).as_posix()
                if skill_dir.parent != repo_dir
                else ""
            )
            if repo_path.split("/", 1)[0] == "template":
                warnings.append(f"skipped {repo_path}: repo template scaffold")
                continue
            try:
                parsed = parse_skill_md(md.read_text(encoding="utf-8"))
            except (SkillParseError, UnicodeDecodeError) as exc:
                warnings.append(f"skipped {repo_path}: {exc}")
                continue
            result = validate(parsed, dir_name=dir_name)
            warnings.extend(f"{repo_path}: {w}" for w in result.warnings)
            if not parsed.description:
                warnings.append(f"skipped {repo_path}: missing description")
                continue
            records.append(
                SkillRecord(
                    id=f"git/{slug}/{repo_path}",
                    name=parsed.name or dir_name,
                    description=parsed.description,
                    category=category,
                    source_type="git",
                    source_url=source.url,
                    repo_path=repo_path,
                    version=sha,
                    license=parsed.license,
                    validated=result.valid,
                )
            )
        return DiscoverResult(version=sha, records=records, warnings=warnings)

    def _skill_dir(self, record: SkillRecord) -> Path:
        repo_dir, _ = self._ensure_clone(Source(type="git", url=record.source_url))
        return repo_dir / record.repo_path

    def get_skill_md(self, record: SkillRecord) -> str:
        return (self._skill_dir(record) / "SKILL.md").read_text(encoding="utf-8")

    def list_files(self, record: SkillRecord) -> list[BundleFile]:
        base = self._skill_dir(record)
        files = [
            BundleFile(path=p.relative_to(base).as_posix(), size=p.stat().st_size)
            for p in base.rglob("*")
            if p.is_file()
        ]
        files.sort(key=lambda f: f.path)
        return files

    def read_file(self, record: SkillRecord, rel_path: str) -> bytes:
        target = self._skill_dir(record) / rel_path.lstrip("/")
        if not target.is_file():
            raise SourceError(f"file not found: {rel_path!r}")
        return target.read_bytes()

    def download(self, record: SkillRecord, dest: Path) -> BundleManifest:
        base = self._skill_dir(record)
        bundle_dir = dest / record.name
        bundle_dir.mkdir(parents=True, exist_ok=True)
        written: list[BundleFile] = []
        for f in self.list_files(record):
            data = (base / f.path).read_bytes()
            target = bundle_dir / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(BundleFile(path=f.path, size=len(data)))
        return write_bundle_manifest(bundle_dir, record, written)
