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

from .config import Config, Source, load_config
from .models import SkillRecord
from .sources import GitAdapter, GitHubAdapter, LocalAdapter, SourceAdapter, SourceError
from .storage import Database


class CatalogError(RuntimeError):
    pass


class Catalog:
    def __init__(self, config: Config | None = None, *, embedder=None):
        self.config = config or load_config()
        self.db = Database(self.config.db_path)
        self._client = self._build_client()
        self._adapters: dict[str, SourceAdapter] = {
            "github": GitHubAdapter(self._client),
            "git": GitAdapter(self.config.data_dir / "clones"),
            "local": LocalAdapter(),
        }
        # Seed default sources into the registry (idempotent).
        self.db.seed_sources([(s.id, s.type, s.url) for s in self.config.sources])

        # Optional semantic backend (lazy). `embedder` may be injected (tests).
        self._injected_embedder = embedder
        self._embedder = embedder
        self._embedder_resolved = embedder is not None
        self.embedder_error: str | None = None

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
    def _registered_sources(self) -> list[Source]:
        return [Source(type=r["type"], url=r["url"]) for r in self.db.list_sources()]

    def _index_source(self, src: Source, *, force: bool) -> dict:
        """Index one source, skipping the walk if its version is unchanged."""
        adapter = self._adapter_for(src.type)
        version = adapter.latest_version(src)
        if not force and self.db.source_refreshed(src.id):
            current = self.db.get_source(src.id)
            if current is not None and current["version"] == version:
                return {
                    "source": src.url,
                    "version": version,
                    "skills": self.db.count_skills_for_source(src.type, src.url),
                    "skipped": True,
                }
        result = adapter.discover(src, version)
        self.db.upsert_skills(result.records)
        self.db.record_source_refresh(src.id, src.type, src.url, result.version)
        return {
            "source": src.url,
            "version": result.version,
            "skills": len(result.records),
            "skipped": False,
            "warnings": result.warnings,
        }

    def refresh(self, source_url: str | None = None, *, force: bool = False) -> dict:
        """(Re)index one registered source (by url) or all of them.

        Incremental: a source whose version is unchanged since last refresh is
        skipped unless ``force`` is set.
        """
        sources = self._registered_sources()
        if source_url:
            sources = [s for s in sources if s.url == source_url]
            if not sources:
                raise CatalogError(f"source not registered: {source_url!r}")

        per_source, indexed, warnings = [], 0, []
        for src in sources:
            info = self._index_source(src, force=force)
            warnings.extend(info.pop("warnings", []))
            per_source.append(info)
            if not info["skipped"]:
                indexed += info["skills"]
        return {"indexed": indexed, "sources": per_source, "warnings": warnings}

    def ensure_indexed(self) -> None:
        """Lazy auto-index: index any registered source not yet refreshed."""
        for src in self._registered_sources():
            if not self.db.source_refreshed(src.id):
                self._index_source(src, force=False)

    # -- Semantic backend (optional, lazy) -------------------------------
    def _get_embedder(self):
        """Resolve the embedder once. Returns it, or None if unavailable."""
        if self._embedder_resolved:
            return self._embedder
        self._embedder_resolved = True
        if self.config.search_backend == "lexical":
            self._embedder = None
            return None
        try:
            from .search import semantic

            self._embedder = semantic.load_embedder(self.config.embed_model)
        except Exception as exc:  # SemanticUnavailable or import error → fall back
            self._embedder = None
            self.embedder_error = str(exc)
        return self._embedder

    def effective_backend(self) -> str:
        """The backend actually in use (configured one, downgraded if unavailable)."""
        if self.config.search_backend == "lexical":
            return "lexical"
        return self.config.search_backend if self._get_embedder() else "lexical"

    def ensure_embedded(self) -> None:
        """Embed any indexed skill that lacks a current vector."""
        embedder = self._get_embedder()
        if embedder is None:
            return
        from .search import semantic

        pending = self.db.skills_needing_embedding()
        if not pending:
            return
        texts = [f"{r.name}. {r.description}" for r in pending]
        vectors = embedder.embed(texts)
        for record, vec in zip(pending, vectors, strict=True):
            blob = semantic.normalize_to_blob(vec)
            self.db.upsert_vector(record.id, record.version, len(vec), blob)

    @staticmethod
    def _passes_filters(record, category, source_type, license) -> bool:
        if category and record.category != category:
            return False
        if source_type and record.source_type != source_type:
            return False
        if license and (not record.license or license.lower() not in record.license.lower()):
            return False
        return True

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
        if self.effective_backend() == "lexical":
            return self._lexical_search(
                query, top_k, category=category, source_type=source_type, license=license
            )
        return self._vector_search(
            query, top_k, category=category, source_type=source_type, license=license
        )

    def _lexical_search(self, query, top_k, *, category, source_type, license) -> list[dict]:
        hits = self.db.search(
            query, top_k=top_k, category=category, source_type=source_type, license=license
        )
        results = []
        for record, rank in hits:
            item = record.summary()
            item["score"] = round(-rank, 4)  # bm25: lower is better → negate for intuition
            results.append(item)
        return results

    def _vector_search(self, query, top_k, *, category, source_type, license) -> list[dict]:
        from .search import semantic
        from .search.hybrid import rrf_fuse

        self.ensure_embedded()
        embedder = self._get_embedder()
        qvec = embedder.embed([query])[0]
        # Retrieve a generous candidate pool, then fuse/filter down to top_k.
        pool = max(top_k * 5, 50)
        vec_hits = semantic.cosine_topk(qvec, self.db.all_vectors(), pool)
        vec_ids = [sid for sid, _ in vec_hits]

        if self.config.search_backend == "hybrid":
            lex = self.db.search(query, top_k=pool)
            lex_ids = [rec.id for rec, _ in lex]
            ordered, scores = rrf_fuse(lex_ids, vec_ids)
        else:  # semantic
            ordered = vec_ids
            scores = dict(vec_hits)

        results = []
        for sid in ordered:
            record = self.db.get_skill(sid)
            if record is None or not self._passes_filters(
                record, category, source_type, license
            ):
                continue
            item = record.summary()
            item["score"] = round(scores.get(sid, 0.0), 4)
            results.append(item)
            if len(results) >= top_k:
                break
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
        out = []
        for r in self.db.list_sources():
            out.append(
                {
                    "type": r["type"],
                    "url": r["url"],
                    "indexed": r["version"] is not None,
                    "version": r["version"],
                    "last_refreshed": r["last_refreshed"],
                    "skills": self.db.count_skills_for_source(r["type"], r["url"]),
                }
            )
        return out

    # -- Source management (Phase 2) -------------------------------------
    @staticmethod
    def _infer_type(url: str) -> str:
        u = url.strip()
        if u.startswith(("http://github.com/", "https://github.com/", "git@github.com:")):
            return "github"
        if u.endswith(".git") or u.startswith(("git@", "ssh://", "git://")):
            return "git"
        if Path(u).expanduser().is_dir():
            return "local"
        if u.startswith(("http://", "https://")):
            return "git"  # a generic remote git repo served over http(s)
        raise CatalogError(
            f"cannot infer source type from {url!r}; pass source_type explicitly "
            "(github | git | local)"
        )

    def add_source(self, url: str, source_type: str | None = None) -> dict:
        stype = source_type or self._infer_type(url)
        if stype not in self._adapters:
            raise CatalogError(
                f"unsupported source type {stype!r}; supported: {sorted(self._adapters)}"
            )
        norm_url = url
        if stype == "local":
            path = Path(url).expanduser()
            if not path.is_dir():
                raise CatalogError(f"local path is not a directory: {url!r}")
            norm_url = str(path.resolve())
        src = Source(type=stype, url=norm_url)
        added = self.db.register_source(src.id, src.type, src.url)
        return {"added": added, "already_present": not added, "type": src.type, "url": src.url}

    def remove_source(self, url: str, purge: bool = False) -> dict:
        match = next(
            (r for r in self.db.list_sources() if url in (r["url"], r["id"])), None
        )
        if match is None:
            raise CatalogError(f"source not registered: {url!r}")
        self.db.remove_source(match["id"])
        purged = (
            self.db.delete_skills_for_source(match["type"], match["url"]) if purge else 0
        )
        return {
            "removed": True,
            "type": match["type"],
            "url": match["url"],
            "purged_skills": purged,
        }

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
