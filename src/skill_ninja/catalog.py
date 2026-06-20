"""Catalog service — orchestrates config, storage, search and source adapters.

This is the single entry point the MCP layer talks to. It implements the three
main flows from CLAUDE.md §6:

* **Search** (Flow A) over the local FTS5 index, with *lazy auto-indexing* of the
  configured sources on first use (so the very first ``search_skills`` works with
  zero prior setup).
* **On-demand retrieval / download** (Flow B) of a specific skill's bundle.
* **Index / refresh** (Flow C) of one or all sources.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from .config import Config, load_config
from .models import SkillRecord
from .sources import GitHubAdapter, SourceAdapter, SourceError
from .storage import Database


class CatalogError(RuntimeError):
    pass


class Catalog:
    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self.db = Database(self.config.db_path)
        self._client = self._build_client()
        self._adapters: dict[str, SourceAdapter] = {
            "github": GitHubAdapter(self._client),
        }

    def _build_client(self) -> httpx.Client:
        headers = {
            "User-Agent": self.config.user_agent,
            "Accept": "application/vnd.github+json",
        }
        if self.config.github_token:
            headers["Authorization"] = f"Bearer {self.config.github_token}"
        return httpx.Client(headers=headers, timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()
        self.db.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _adapter_for(self, source_type: str) -> SourceAdapter:
        adapter = self._adapters.get(source_type)
        if adapter is None:
            raise CatalogError(f"no adapter registered for source type {source_type!r}")
        return adapter

    # -- Flow C: index / refresh -----------------------------------------
    def refresh(self, source_url: str | None = None) -> dict:
        """(Re)index one source (by url) or all configured sources."""
        if source_url:
            sources = [s for s in self.config.sources if s.url == source_url]
            if not sources:
                raise CatalogError(f"source not configured: {source_url!r}")
        else:
            sources = list(self.config.sources)

        per_source = []
        total = 0
        warnings: list[str] = []
        for src in sources:
            adapter = self._adapter_for(src.type)
            result = adapter.discover(src)
            self.db.upsert_skills(result.records)
            self.db.record_source_refresh(src.id, src.type, src.url, result.version)
            total += len(result.records)
            warnings.extend(result.warnings)
            per_source.append(
                {"source": src.url, "version": result.version, "skills": len(result.records)}
            )
        return {"indexed": total, "sources": per_source, "warnings": warnings}

    def ensure_indexed(self) -> None:
        """Lazy auto-index: index any configured source not yet in the catalog."""
        pending = [s for s in self.config.sources if not self.db.is_source_indexed(s.id)]
        for src in pending:
            adapter = self._adapter_for(src.type)
            result = adapter.discover(src)
            self.db.upsert_skills(result.records)
            self.db.record_source_refresh(src.id, src.type, src.url, result.version)

    # -- Flow A: search ---------------------------------------------------
    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        category: str | None = None,
        source_type: str | None = None,
        license: str | None = None,
    ) -> list[dict]:
        self.ensure_indexed()
        hits = self.db.search(
            query,
            top_k=top_k,
            category=category,
            source_type=source_type,
            license=license,
        )
        results = []
        for record, rank in hits:
            item = record.summary()
            item["score"] = round(-rank, 4)  # bm25: lower is better → negate for intuition
            results.append(item)
        return results

    # -- Flow B: retrieval / download ------------------------------------
    def _require(self, skill_id: str) -> SkillRecord:
        record = self.db.get_skill(skill_id)
        if record is None:
            raise CatalogError(f"unknown skill_id: {skill_id!r}")
        return record

    def get_skill(self, skill_id: str) -> dict:
        record = self._require(skill_id)
        adapter = self._adapter_for(record.source_type)

        local_md = self._local_skill_md_path(record)
        if local_md is not None:
            content = local_md.read_text(encoding="utf-8")
            files = self._local_files(record)
        else:
            content = adapter.get_skill_md(record)
            files = [f.path for f in adapter.list_files(record)]

        summary = record.summary()
        summary.update({"content": content, "files": files})
        return summary

    def read_skill_file(self, skill_id: str, path: str) -> dict:
        record = self._require(skill_id)
        adapter = self._adapter_for(record.source_type)
        rel = path.lstrip("/")

        if record.local_path:
            target = Path(record.local_path) / rel
            if not target.is_file():
                raise CatalogError(f"file not found in local bundle: {rel!r}")
            raw = target.read_bytes()
        else:
            raw = adapter.read_file(record, rel)

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return {
                "skill_id": skill_id,
                "path": rel,
                "binary": True,
                "size": len(raw),
                "note": "binary file — not returned as text",
            }
        return {"skill_id": skill_id, "path": rel, "binary": False, "content": text}

    def download_skill(self, skill_id: str, dest: str | None = None) -> dict:
        record = self._require(skill_id)
        adapter = self._adapter_for(record.source_type)
        dest_dir = Path(dest) if dest else self.config.store_dir
        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            manifest = adapter.download(record, dest_dir)
        except SourceError as exc:
            raise CatalogError(f"download failed: {exc}") from exc

        self.db.set_local_path(record.id, manifest.dest)
        out = manifest.to_dict()
        out.update({"name": record.name, "license": record.license})
        return out

    def list_local(self) -> list[dict]:
        return [
            {**r.summary(downloaded=True), "local_path": r.local_path}
            for r in self.db.list_local()
        ]

    def list_sources(self) -> list[dict]:
        indexed = {row["id"]: row for row in self.db.list_sources()}
        out = []
        for src in self.config.sources:
            row = indexed.get(src.id)
            out.append(
                {
                    "type": src.type,
                    "url": src.url,
                    "indexed": row is not None,
                    "version": row["version"] if row else None,
                    "last_refreshed": row["last_refreshed"] if row else None,
                }
            )
        return out

    # -- local-store helpers ---------------------------------------------
    def _local_skill_md_path(self, record: SkillRecord) -> Path | None:
        if not record.local_path:
            return None
        candidate = Path(record.local_path) / "SKILL.md"
        return candidate if candidate.is_file() else None

    def _local_files(self, record: SkillRecord) -> list[str]:
        base = Path(record.local_path) if record.local_path else None
        if not base or not base.is_dir():
            return []
        return sorted(
            str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*")
            if p.is_file()
        )
