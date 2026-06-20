"""GitHub source adapter.

Discovery strategy (CLAUDE.md §9): 2 REST calls per repo refresh —
  1. latest commit on the default branch (pins a reproducible SHA), and
  2. the Git Trees API with ``?recursive=1`` (whole tree in one call).
Per-file content is then read from ``raw.githubusercontent.com``, which does **not**
count against the REST rate limit — so discovery stays well under the unauthenticated
budget even for a monorepo with many skills.
"""

from __future__ import annotations

from pathlib import Path

import httpx

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

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"


def _owner_repo(url: str) -> tuple[str, str]:
    """Parse ``owner`` and ``repo`` from a GitHub URL or ``owner/repo`` string."""
    s = url.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    if s.endswith(".git"):
        s = s[:-4]
    parts = [p for p in s.split("/") if p]
    if len(parts) < 2:
        raise SourceError(f"cannot parse owner/repo from GitHub source {url!r}")
    return parts[0], parts[1]


class GitHubAdapter(SourceAdapter):
    source_type = "github"

    def __init__(self, client: httpx.Client):
        self._client = client

    # -- REST helpers -----------------------------------------------------
    def _get_json(self, url: str) -> dict | list:
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            raise SourceError(f"GitHub request failed: {exc}") from exc
        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            raise SourceError(
                "GitHub API rate limit hit. Set GITHUB_TOKEN (or "
                "SKILL_NINJA_GITHUB_TOKEN) to raise the limit."
            )
        if resp.status_code >= 400:
            raise SourceError(f"GitHub API {resp.status_code} for {url}: {resp.text[:200]}")
        return resp.json()

    def _latest_commit(self, owner: str, repo: str) -> str:
        data = self._get_json(f"{API}/repos/{owner}/{repo}/commits?per_page=1")
        if not isinstance(data, list) or not data:
            raise SourceError(f"no commits found for {owner}/{repo}")
        return data[0]["sha"]

    def _tree(self, owner: str, repo: str, sha: str) -> list[dict]:
        data = self._get_json(f"{API}/repos/{owner}/{repo}/git/trees/{sha}?recursive=1")
        if not isinstance(data, dict):
            raise SourceError("unexpected tree response")
        if data.get("truncated"):
            # Rare for skill repos; surfaced so the caller knows the tree was capped.
            raise SourceError(
                f"tree for {owner}/{repo} was truncated by GitHub; "
                "repo too large for single-call discovery"
            )
        return data.get("tree", [])

    def _raw_bytes(self, owner: str, repo: str, sha: str, path: str) -> bytes:
        url = f"{RAW}/{owner}/{repo}/{sha}/{path}"
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            raise SourceError(f"raw fetch failed for {path}: {exc}") from exc
        if resp.status_code >= 400:
            raise SourceError(f"raw fetch {resp.status_code} for {url}")
        return resp.content

    # -- adapter API ------------------------------------------------------
    def latest_version(self, source: Source) -> str:
        owner, repo = _owner_repo(source.url)
        return self._latest_commit(owner, repo)

    def discover(self, source: Source, version: str | None = None) -> DiscoverResult:
        owner, repo = _owner_repo(source.url)
        sha = version or self._latest_commit(owner, repo)
        tree = self._tree(owner, repo, sha)

        skill_paths = [
            e["path"]
            for e in tree
            if e.get("type") == "blob" and e["path"].endswith("/SKILL.md")
        ]

        records: list[SkillRecord] = []
        warnings: list[str] = []
        for path in skill_paths:
            repo_path = path[: -len("/SKILL.md")]  # the skill directory
            dir_name = repo_path.rsplit("/", 1)[-1]
            category = repo_path.rsplit("/", 1)[0] if "/" in repo_path else ""

            # Skip a repo-root `template/` scaffold — it's a placeholder, not a skill.
            if repo_path.split("/", 1)[0] == "template":
                warnings.append(f"skipped {path}: repo template scaffold")
                continue
            try:
                text = self._raw_bytes(owner, repo, sha, path).decode("utf-8")
                parsed = parse_skill_md(text)
            except (SkillParseError, UnicodeDecodeError) as exc:
                warnings.append(f"skipped {path}: {exc}")
                continue

            result = validate(parsed, dir_name=dir_name)
            warnings.extend(f"{path}: {w}" for w in result.warnings)
            name = parsed.name or dir_name
            description = parsed.description or ""
            if not description:
                warnings.append(f"skipped {path}: missing description")
                continue

            records.append(
                SkillRecord(
                    id=f"github/{owner}/{repo}/{repo_path}",
                    name=name,
                    description=description,
                    category=category,
                    source_type="github",
                    source_url=f"https://github.com/{owner}/{repo}",
                    repo_path=repo_path,
                    version=sha,
                    license=parsed.license,
                    validated=result.valid,
                )
            )

        return DiscoverResult(version=sha, records=records, warnings=warnings)

    def get_skill_md(self, record: SkillRecord) -> str:
        owner, repo = _owner_repo(record.source_url)
        data = self._raw_bytes(owner, repo, record.version, f"{record.repo_path}/SKILL.md")
        return data.decode("utf-8")

    def list_files(self, record: SkillRecord) -> list[BundleFile]:
        owner, repo = _owner_repo(record.source_url)
        tree = self._tree(owner, repo, record.version)
        prefix = record.repo_path + "/"
        files: list[BundleFile] = []
        for e in tree:
            if e.get("type") == "blob" and e["path"].startswith(prefix):
                files.append(BundleFile(path=e["path"][len(prefix):], size=e.get("size")))
        files.sort(key=lambda f: f.path)
        return files

    def read_file(self, record: SkillRecord, rel_path: str) -> bytes:
        owner, repo = _owner_repo(record.source_url)
        rel = rel_path.lstrip("/")
        return self._raw_bytes(owner, repo, record.version, f"{record.repo_path}/{rel}")

    def download(self, record: SkillRecord, dest: Path) -> BundleManifest:
        owner, repo = _owner_repo(record.source_url)
        files = self.list_files(record)
        bundle_dir = dest / record.name
        bundle_dir.mkdir(parents=True, exist_ok=True)

        written: list[BundleFile] = []
        for f in files:
            content = self._raw_bytes(owner, repo, record.version, f"{record.repo_path}/{f.path}")
            target = bundle_dir / f.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written.append(BundleFile(path=f.path, size=len(content)))

        return write_bundle_manifest(bundle_dir, record, written)
