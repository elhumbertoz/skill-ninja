"""MCP server — registers the skill-ninja tools (FastMCP).

Runs over **stdio** by default; **HTTP** transports (``streamable-http`` or ``sse``)
are available via ``--transport`` / ``SKILL_NINJA_TRANSPORT`` for remote/shared use.

Startup is instant: creating the server only opens the local SQLite index and an
HTTP client (no network, no model downloads). The configured sources are indexed
*lazily* on the first ``search_skills`` call.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .catalog import Catalog, CatalogError
from .sources import SourceError

mcp = FastMCP("skill-ninja")
# FastMCP has no `version` constructor arg yet; set it on the low-level server so
# the MCP `initialize` handshake advertises our version (not the SDK's).
mcp._mcp_server.version = __version__

_catalog: Catalog | None = None


def get_catalog() -> Catalog:
    global _catalog
    if _catalog is None:
        _catalog = Catalog()
    return _catalog


def _safe(fn, *args, **kwargs) -> Any:
    """Run a catalog call, turning known failures into a structured error dict."""
    try:
        return fn(*args, **kwargs)
    except (CatalogError, SourceError) as exc:
        return {"error": str(exc)}


@mcp.tool()
def search_skills(
    query: str,
    top_k: int = 10,
    category: str | None = None,
    source: str | None = None,
    license: str | None = None,
) -> dict:
    """Search the skill catalog for skills relevant to a task.

    Call this the moment you need specialized, battle-tested expertise you don't
    already have — e.g. editing an .xlsx, building a PDF, web-app testing. Use a
    short, keyword-rich English query describing the task or file type (e.g. "xlsx
    spreadsheet", "pdf form fill", "web app testing").

    Returns a ranked list of candidate skills with their ``skill_id`` and metadata
    (name, description, license, source, whether already downloaded). Follow up with
    ``get_skill(skill_id)`` to pull the chosen skill's instructions into context.

    Optional filters: ``category``, ``source`` (e.g. "github"), ``license``.
    """
    cat = get_catalog()
    results = _safe(
        cat.search,
        query,
        top_k=top_k,
        category=category,
        source_type=source,
        license=license,
    )
    if isinstance(results, dict):  # error
        return results
    out = {
        "query": query,
        "count": len(results),
        "results": results,
        "backend": cat.effective_backend(),
    }
    downgraded = cat.config.search_backend != "lexical" and out["backend"] == "lexical"
    if downgraded and cat.embedder_error:
        out["note"] = f"semantic backend unavailable; used lexical. {cat.embedder_error}"
    return out


@mcp.tool()
def get_skill(skill_id: str) -> dict:
    """Fetch a skill's full SKILL.md instructions plus its bundle file list.

    Use this after ``search_skills`` to bring the chosen skill into context. The
    returned ``content`` is the SKILL.md body (the actual instructions/expertise);
    ``files`` lists bundled resources you can pull individually with
    ``read_skill_file``. Reads from the local store if the skill was downloaded,
    otherwise fetches from origin. This does NOT persist the bundle — use
    ``download_skill`` for that.
    """
    return _safe(get_catalog().get_skill, skill_id)


@mcp.tool()
def read_skill_file(skill_id: str, path: str) -> dict:
    """Read one bundled resource of a skill (e.g. ``references/REFERENCE.md``).

    ``path`` is relative to the skill root. Use the paths listed in ``get_skill``'s
    ``files``. Text files are returned in ``content``; binary files are reported as
    such instead of being inlined.
    """
    return _safe(get_catalog().read_skill_file, skill_id, path)


@mcp.tool()
def download_skill(skill_id: str, dest: str | None = None) -> dict:
    """Download a skill's full bundle into the local store and pin its version.

    Fetches every file (SKILL.md + scripts/ + references/ + assets/) from origin,
    writes them under ``dest`` (defaults to the managed local store), records the
    pinned commit SHA, and returns the local path + file manifest. Point ``dest`` at
    your agent's skills folder (e.g. ``.claude/skills`` or ``.agents/skills``) to make
    the skill natively available there.
    """
    return _safe(get_catalog().download_skill, skill_id, dest)


@mcp.tool()
def list_local_skills() -> dict:
    """List skills already downloaded into the local store."""
    skills = get_catalog().list_local()
    return {"count": len(skills), "skills": skills}


@mcp.tool()
def list_sources() -> dict:
    """List the registered catalog sources, their index status and skill counts."""
    sources = get_catalog().list_sources()
    return {"count": len(sources), "sources": sources}


@mcp.tool()
def add_source(url: str, source_type: str | None = None) -> dict:
    """Register a new source to discover skills from.

    ``url`` may be a GitHub repo (``https://github.com/owner/repo``), any git URL
    (``…​.git``), or a local folder path. ``source_type`` (github | git | local) is
    inferred when omitted. The new source is indexed lazily on the next search, or
    immediately via ``refresh_catalog``.
    """
    return _safe(get_catalog().add_source, url, source_type)


@mcp.tool()
def remove_source(url: str, purge: bool = False) -> dict:
    """Deregister a source so it's no longer refreshed.

    By default already-indexed skills from it are left in place; set ``purge=true`` to
    also drop them from the index (downloaded files on disk are never deleted).
    """
    return _safe(get_catalog().remove_source, url, purge)


@mcp.tool()
def refresh_catalog(source: str | None = None, force: bool = False) -> dict:
    """Re-index the catalog from its sources (all, or one source URL).

    Normally unnecessary — sources are auto-indexed on first search. Incremental:
    sources whose version is unchanged are skipped unless ``force=true``.
    """
    return _safe(get_catalog().refresh, source, force=force)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skill-ninja",
        description="MCP server that exposes Agent Skills to any agent via search.",
    )
    p.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("SKILL_NINJA_TRANSPORT", "stdio"),
        help="MCP transport (default: stdio). HTTP transports are for remote/shared use.",
    )
    p.add_argument(
        "--host",
        default=os.environ.get("SKILL_NINJA_HOST", "127.0.0.1"),
        help="Bind host for HTTP transports (default: 127.0.0.1).",
    )
    p.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SKILL_NINJA_PORT", "8000")),
        help="Bind port for HTTP transports (default: 8000).",
    )
    p.add_argument("--version", action="version", version=f"skill-ninja {__version__}")
    return p


def main(argv: list[str] | None = None) -> None:
    """Console entry point. Runs over stdio by default; HTTP transports optional."""
    args = _build_arg_parser().parse_args(argv)
    if args.transport != "stdio":
        mcp.settings.host = args.host
        mcp.settings.port = args.port
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
