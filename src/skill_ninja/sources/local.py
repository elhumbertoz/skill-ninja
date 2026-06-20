"""Local filesystem source adapter — index skills from a folder on disk.

``source.url`` is an absolute folder path. The version token is a hash of the
discovered SKILL.md files' (path, mtime, size), so an unchanged folder is skipped on
refresh. Downloading copies the bundle into the managed store like any other source.
"""

from __future__ import annotations

import hashlib
import re
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

_SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")


def _root_slug(root: Path) -> str:
    return _SANITIZE.sub("_", root.as_posix()).strip("_") or "root"


class LocalAdapter(SourceAdapter):
    source_type = "local"

    def _root(self, source: Source) -> Path:
        root = Path(source.url)
        if not root.is_dir():
            raise SourceError(f"local source is not a directory: {source.url!r}")
        return root

    def _skill_md_files(self, root: Path) -> list[Path]:
        return sorted(p for p in root.rglob("SKILL.md") if ".git" not in p.parts)

    def latest_version(self, source: Source) -> str:
        root = self._root(source)
        h = hashlib.sha256()
        for md in self._skill_md_files(root):
            st = md.stat()
            rel = md.relative_to(root).as_posix()
            h.update(f"{rel}:{st.st_mtime_ns}:{st.st_size}\n".encode())
        return h.hexdigest()[:16]

    def discover(self, source: Source, version: str | None = None) -> DiscoverResult:
        root = self._root(source)
        ver = version or self.latest_version(source)
        slug = _root_slug(root)

        records: list[SkillRecord] = []
        warnings: list[str] = []
        for md in self._skill_md_files(root):
            skill_dir = md.parent
            repo_path = skill_dir.relative_to(root).as_posix()
            dir_name = skill_dir.name
            category = (
                skill_dir.parent.relative_to(root).as_posix()
                if skill_dir.parent != root
                else ""
            )
            if repo_path == ".":  # SKILL.md sitting directly in the root folder
                repo_path = ""
                dir_name = root.name
            try:
                parsed = parse_skill_md(md.read_text(encoding="utf-8"))
            except (SkillParseError, UnicodeDecodeError) as exc:
                warnings.append(f"skipped {repo_path or '.'}: {exc}")
                continue
            result = validate(parsed, dir_name=dir_name)
            warnings.extend(f"{repo_path or '.'}: {w}" for w in result.warnings)
            if not parsed.description:
                warnings.append(f"skipped {repo_path or '.'}: missing description")
                continue
            skill_id = f"local/{slug}/{repo_path}" if repo_path else f"local/{slug}"
            records.append(
                SkillRecord(
                    id=skill_id,
                    name=parsed.name or dir_name,
                    description=parsed.description,
                    category=category,
                    source_type="local",
                    source_url=source.url,
                    repo_path=repo_path,
                    version=ver,
                    license=parsed.license,
                    validated=result.valid,
                )
            )
        return DiscoverResult(version=ver, records=records, warnings=warnings)

    def _skill_dir(self, record: SkillRecord) -> Path:
        base = Path(record.source_url)
        return base / record.repo_path if record.repo_path else base

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
