"""SQLite-backed metadata index with FTS5 full-text search.

Single file, no server, stdlib-only. The ``skills`` table holds the records; a
companion FTS5 virtual table (``skills_fts``) provides ranked lexical search. The
two are kept in sync on every upsert (delete-then-insert into FTS) — simple and
plenty fast at the scale of this catalog (hundreds of records).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from ..models import SkillRecord
from ..search.fts import BM25_WEIGHTS, build_match_query

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id             TEXT PRIMARY KEY,
    type           TEXT NOT NULL,
    url            TEXT NOT NULL,
    version        TEXT,
    last_refreshed REAL
);

CREATE TABLE IF NOT EXISTS skills (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    description  TEXT NOT NULL,
    category     TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '[]',
    source_type  TEXT NOT NULL,
    source_url   TEXT NOT NULL,
    repo_path    TEXT NOT NULL DEFAULT '',
    version      TEXT NOT NULL DEFAULT '',
    license      TEXT,
    local_path   TEXT,
    validated    INTEGER NOT NULL DEFAULT 0,
    last_indexed REAL NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
    skill_id UNINDEXED,
    name,
    description,
    category,
    tokenize = 'porter unicode61'
);
"""

def _row_to_record(row: sqlite3.Row) -> SkillRecord:
    return SkillRecord(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        category=row["category"],
        tags=json.loads(row["tags"] or "[]"),
        source_type=row["source_type"],
        source_url=row["source_url"],
        repo_path=row["repo_path"],
        version=row["version"],
        license=row["license"],
        local_path=row["local_path"],
        validated=bool(row["validated"]),
        last_indexed=row["last_indexed"],
    )


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_fts5()
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _ensure_fts5(self) -> None:
        try:
            self.conn.execute("CREATE VIRTUAL TABLE temp.__fts5_probe USING fts5(x)")
            self.conn.execute("DROP TABLE temp.__fts5_probe")
        except sqlite3.OperationalError as exc:  # pragma: no cover - env dependent
            raise RuntimeError(
                "This SQLite build lacks the FTS5 extension, which skill-ninja "
                "requires for search. Use a Python with FTS5-enabled sqlite3."
            ) from exc

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- skills -----------------------------------------------------------
    def upsert_skills(self, records: list[SkillRecord]) -> int:
        cur = self.conn.cursor()
        for rec in records:
            cur.execute(
                """
                INSERT INTO skills (id, name, description, category, tags,
                    source_type, source_url, repo_path, version, license,
                    local_path, validated, last_indexed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    category=excluded.category,
                    tags=excluded.tags,
                    source_type=excluded.source_type,
                    source_url=excluded.source_url,
                    repo_path=excluded.repo_path,
                    version=excluded.version,
                    license=excluded.license,
                    validated=excluded.validated,
                    last_indexed=excluded.last_indexed
                """,
                (
                    rec.id, rec.name, rec.description, rec.category,
                    json.dumps(rec.tags), rec.source_type, rec.source_url,
                    rec.repo_path, rec.version, rec.license, rec.local_path,
                    int(rec.validated), rec.last_indexed,
                ),
            )
            # Keep FTS in sync: delete-then-insert for this skill.
            cur.execute("DELETE FROM skills_fts WHERE skill_id = ?", (rec.id,))
            cur.execute(
                "INSERT INTO skills_fts (skill_id, name, description, category) "
                "VALUES (?, ?, ?, ?)",
                (rec.id, rec.name, rec.description, rec.category),
            )
        self.conn.commit()
        return len(records)

    def get_skill(self, skill_id: str) -> SkillRecord | None:
        row = self.conn.execute(
            "SELECT * FROM skills WHERE id = ?", (skill_id,)
        ).fetchone()
        return _row_to_record(row) if row else None

    def count_skills(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]

    def set_local_path(self, skill_id: str, local_path: str | None) -> None:
        self.conn.execute(
            "UPDATE skills SET local_path = ? WHERE id = ?", (local_path, skill_id)
        )
        self.conn.commit()

    def list_local(self) -> list[SkillRecord]:
        rows = self.conn.execute(
            "SELECT * FROM skills WHERE local_path IS NOT NULL ORDER BY name"
        ).fetchall()
        return [_row_to_record(r) for r in rows]

    def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        category: str | None = None,
        source_type: str | None = None,
        license: str | None = None,
    ) -> list[tuple[SkillRecord, float]]:
        match = build_match_query(query)
        if not match:
            return []

        sql = [
            "SELECT s.*, bm25(skills_fts, ?, ?, ?, ?) AS rank",
            "FROM skills_fts",
            "JOIN skills s ON s.id = skills_fts.skill_id",
            "WHERE skills_fts MATCH ?",
        ]
        params: list = [*BM25_WEIGHTS, match]
        if category:
            sql.append("AND s.category = ?")
            params.append(category)
        if source_type:
            sql.append("AND s.source_type = ?")
            params.append(source_type)
        if license:
            sql.append("AND s.license LIKE ?")
            params.append(f"%{license}%")
        sql.append("ORDER BY rank LIMIT ?")
        params.append(top_k)

        rows = self.conn.execute("\n".join(sql), params).fetchall()
        return [(_row_to_record(r), r["rank"]) for r in rows]

    # -- sources (the `sources` table is the registry of where to discover) --
    def register_source(self, source_id: str, source_type: str, url: str) -> bool:
        """Add a source to the registry. Returns True if newly added (else exists)."""
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO sources (id, type, url) VALUES (?, ?, ?)",
            (source_id, source_type, url),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def seed_sources(self, sources: list[tuple[str, str, str]]) -> None:
        """Ensure default sources exist (id, type, url), without resetting state."""
        for source_id, source_type, url in sources:
            self.register_source(source_id, source_type, url)

    def remove_source(self, source_id: str) -> bool:
        """Deregister a source. Returns True if it existed. Skills are left intact
        unless purged separately."""
        cur = self.conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def delete_skills_for_source(self, source_type: str, url: str) -> int:
        """Purge indexed skill records originating from a source (FTS kept in sync).

        Does not touch already-downloaded files on disk — only the index.
        """
        rows = self.conn.execute(
            "SELECT id FROM skills WHERE source_type = ? AND source_url = ?",
            (source_type, url),
        ).fetchall()
        ids = [r["id"] for r in rows]
        for skill_id in ids:
            self.conn.execute("DELETE FROM skills_fts WHERE skill_id = ?", (skill_id,))
        self.conn.execute(
            "DELETE FROM skills WHERE source_type = ? AND source_url = ?",
            (source_type, url),
        )
        self.conn.commit()
        return len(ids)

    def record_source_refresh(
        self, source_id: str, source_type: str, url: str, version: str | None
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO sources (id, type, url, version, last_refreshed)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                version=excluded.version,
                last_refreshed=excluded.last_refreshed
            """,
            (source_id, source_type, url, version, time.time()),
        )
        self.conn.commit()

    def get_source(self, source_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM sources WHERE id = ?", (source_id,)
        ).fetchone()

    def source_refreshed(self, source_id: str) -> bool:
        """True if the source has been indexed at least once (has a pinned version)."""
        row = self.get_source(source_id)
        return row is not None and row["version"] is not None

    def count_skills_for_source(self, source_type: str, url: str) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM skills WHERE source_type = ? AND source_url = ?",
            (source_type, url),
        ).fetchone()[0]

    def list_sources(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
