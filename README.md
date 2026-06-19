# 🥷 skill-ninja

**A federated index of Agent Skills + a local download manager, exposed over MCP to any AI agent.**

> **Status:** design / early development. No code is published yet — see [the roadmap](#roadmap). This README describes the project's goals and the v1 design.

skill-ninja is an open-source [MCP](https://modelcontextprotocol.io) server that keeps a local catalog of [Agent Skills](https://agentskills.io) and lets **any MCP client** — Claude Code, Cursor, VS Code, OpenCode, Antigravity, Gemini CLI, Codex, and others — search it in natural language and download skills on demand.

---

## Why

Agent Skills are spread across many repos and registries (`anthropics/skills`, generic git repos, agentskills.io, local folders). Finding the right one and wiring it into your agent is manual. skill-ninja turns that into one MCP tool call:

> *"search for a skill that helps with CSS design"* → ranked candidates → *"download it"* → it lands in your skills folder.

**Design principles:** open source · trivial to install · usable from any IDE. Concretely: zero-install launch, instant first startup, no mandatory API keys, no external infrastructure.

---

## How it works

skill-ninja keeps **two layers**, which is what makes it cheap and fast:

| Layer | What | Cost |
|-------|------|------|
| **Metadata index** | `name` + `description` + source for every discovered skill, *without* downloading the bundle | light — search runs here |
| **Local store** | full bundles (`SKILL.md` + `scripts/` + `references/` + `assets/`) you actually download | heavy — materialized on demand |

Search hits the lightweight index; download materializes the full skill. By default, search is **lexical (SQLite FTS5)** — no model downloads, no API keys, works offline. A semantic/embedding backend is an **opt-in extra** for those who want it.

skill-ninja is a **fetcher, not a mirror**: it always downloads from the original source and caches locally for you (like a package manager). It never re-hosts skills, and surfaces each skill's `license` so you decide.

---

## Quick start

> ⚠️ Not yet published. The commands below show the intended usage once v1 ships.

skill-ninja runs as a zero-install MCP server via [`uv`](https://docs.astral.sh/uv/):

```bash
uvx skill-ninja
```

That's the whole install. No model download, no database to set up — it starts instantly.

### Register it in your MCP client

Most clients accept a standard stdio MCP server entry. Examples:

**Claude Code**

```bash
claude mcp add skill-ninja -- uvx skill-ninja
```

**Cursor / VS Code / Antigravity / OpenCode** (any client using the standard `mcpServers` JSON):

```jsonc
{
  "mcpServers": {
    "skill-ninja": {
      "command": "uvx",
      "args": ["skill-ninja"]
    }
  }
}
```

> Each client stores its config in a different place (a settings file, a `.mcp.json`, or a UI). Check your client's MCP docs for where to paste this. Per-client snippets will live in the docs as they're verified.

### Use it

Once registered, just ask your agent in natural language:

- *"Find a skill for working with PDFs and download it."*
- *"Search skills about web-app testing."*
- *"List the skills I've already downloaded."*

The agent calls the tools below under the hood.

---

## MCP tools

| Tool | Input | Output |
|------|-------|--------|
| `search_skills` | `query`, `top_k?`, `filters?` (category/source/license) | ranked skills with `skill_id` + metadata |
| `get_skill` | `skill_id` | `SKILL.md` content + bundle file list |
| `read_skill_file` | `skill_id`, `path` | content of a bundled resource |
| `download_skill` | `skill_id`, `dest?` | local path + manifest |
| `list_local_skills` | — | already-downloaded skills |
| `list_sources` / `add_source` / `remove_source` | `url?`, `type?` | source state |
| `refresh_catalog` | `source?` | re-index summary |

Tools return structured JSON so the agent can chain actions: **search → download → read**.

---

## Sources

skill-ninja aggregates skills from pluggable adapters:

- **GitHub** — discovers `SKILL.md` files across a repo (monorepo-aware via the Git Trees API). Reference: [`anthropics/skills`](https://github.com/anthropics/skills).
- **Generic git** — shallow clone of any git URL.
- **agentskills.io** — the community catalog/showcase as a discovery source.
- **Local filesystem** — index your own skill folders.

Add or remove sources at runtime via the `*_source` tools.

---

## Roadmap

- **Phase 1 — MVP:** stdio server + GitHub adapter + `SKILL.md` parsing/validation + FTS5 search + `search_skills` / `download_skill` over `anthropics/skills`. Runnable via `uvx`.
- **Phase 2 — Multi-source:** generic git, agentskills.io, and local FS adapters; source management; incremental refresh.
- **Phase 3 — Search quality:** optional semantic backend, hybrid (lexical + vector) search, filters, auto-categorization.
- **Phase 4 — DX/distribution:** HTTP/SSE transport, packaging, and verified per-client setup docs.

---

## Tech stack

Python 3.12+ · [`uv`](https://docs.astral.sh/uv/) · [FastMCP](https://github.com/modelcontextprotocol/python-sdk) · SQLite + FTS5 (search) · `httpx` + GitHub REST. Optional semantic search via `fastembed` + `sqlite-vec` (`skill-ninja[semantic]`).

A TypeScript/Node implementation is a viable alternative if `npx` distribution is preferred.

---

## Contributing

Contributions are welcome — new source adapters and per-client setup docs are especially valuable. (Contribution guidelines will land alongside the first code drop.)

The Agent Skills format itself is documented in [agent-skills-reference.md](agent-skills-reference.md), and the full project design in [CLAUDE.md](CLAUDE.md).

---

## License

[Apache-2.0](LICENSE) — aligned with the Agent Skills ecosystem.

> skill-ninja indexes and downloads third-party skills but does not redistribute them; each skill keeps its own license, which skill-ninja surfaces in search results.
