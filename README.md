# 🥷 skill-ninja

### Give your AI agent just-in-time skills. One MCP server. Any IDE.

[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![MCP](https://img.shields.io/badge/Model_Context_Protocol-compatible-7C3AED.svg)](https://modelcontextprotocol.io)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776AB.svg)](#tech-stack)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

**skill-ninja lets your AI agent find and pull the exact [Agent Skill](https://agentskills.io) it needs — the moment it needs it** — from across GitHub, agentskills.io, and your own folders. No pre-installing. No context bloat. Works in **any MCP client**: Claude Code, Cursor, VS Code, OpenCode, Antigravity, Gemini CLI, Codex…

---

## ⚡ Install in one sentence

Just tell your agent:

> **"Install the MCP server at https://github.com/elhumbertoz/skill-ninja"**

It reads this README, runs the command below, and you're done. Or do it yourself in one line:

```bash
# Claude Code
claude mcp add skill-ninja -- uvx skill-ninja
```

```bash
# Just run it (zero-install via uv)
uvx skill-ninja
```

That's the **whole** install. No model download. No database to set up. No API key. It starts instantly. 🚀

<sub>⭐ Find it handy? **Star the repo** — it helps other devs discover it.</sub>

---

## The problem it kills

You ask your agent to **edit an `.xlsx` file**. It doesn't know the right approach, so it guesses — wrong library, broken formatting, an afternoon lost.

A skill that teaches it *exactly* how to do this already exists. But skills are scattered across dozens of repos and registries, and wiring them in is manual. Pre-installing them all? That bloats your context with stuff you don't need 99% of the time.

**skill-ninja flips it:**

| Without skill-ninja | With skill-ninja |
|---|---|
| Hunt GitHub for the right skill | Agent calls `search_skills("xlsx")` |
| Copy files into your skills folder | Agent pulls the proven skill into context |
| Hope it's current and correct | It's fetched from origin, version-pinned |
| Repeat for every task | One tool. Every task. Any IDE. |

Your agent gains **expertise on demand** — it carries one cheap search tool and brings in only the *specific* skill it needs, *when* it needs it.

---

## Use it

Once registered, just talk to your agent in plain language:

- 💬 *"Find a skill for editing xlsx files and use it."*
- 💬 *"Search skills about web-app testing and download the best one."*
- 💬 *"What skills have I already downloaded?"*

Under the hood it chains the MCP tools below: **search → download → read.**

---

## How it works

Two layers — that's the trick that keeps it **cheap, fast, and offline-first**:

| Layer | What | Cost |
|-------|------|------|
| **🔍 Metadata index** | `name` + `description` + source for every discovered skill, *without* downloading the bundle | light — search runs here |
| **📦 Local store** | full bundles (`SKILL.md` + `scripts/` + `references/` + `assets/`) you actually download | heavy — fetched on demand |

Search hits the lightweight index; download materializes the full skill. Search is **lexical (SQLite FTS5)** by default — **no model downloads, no API keys, works offline.** A semantic/embedding backend is an **opt-in extra** for whoever wants it.

> **Fetcher, not mirror.** skill-ninja always downloads from the original source and caches locally for you — like a package manager (`apt`/`npm`). It never re-hosts skills, and surfaces each skill's `license` so *you* decide.

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

Everything returns structured JSON so the agent can decide the next move.

---

## Works in your IDE

**Claude Code** — one line:

```bash
claude mcp add skill-ninja -- uvx skill-ninja
```

**Cursor · VS Code · Antigravity · OpenCode · Gemini CLI · Codex** — any client using the standard `mcpServers` JSON:

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

> Each client stores this config in a different place (a settings file, a `.mcp.json`, or a UI). Check your client's MCP docs for where it goes.

Prefer the bleeding edge? Install straight from source:

```bash
uvx --from git+https://github.com/elhumbertoz/skill-ninja skill-ninja
```

---

## Sources

Pluggable adapters — mix and match:

- **GitHub** — discovers `SKILL.md` across a repo, monorepo-aware via the Git Trees API. Reference: [`anthropics/skills`](https://github.com/anthropics/skills).
- **Generic git** — shallow clone of any git URL.
- **agentskills.io** — the community catalog/showcase as a discovery source.
- **Local filesystem** — index your own skill folders.

Add or remove sources at runtime with the `*_source` tools.

---

## Roadmap

A solid core, growing outward:

- **Core:** stdio MCP server + GitHub adapter + `SKILL.md` parsing/validation + FTS5 search + `search_skills` / `download_skill` over `anthropics/skills`, runnable via `uvx`.
- **Multi-source:** generic git, agentskills.io, and local FS adapters; source management; incremental refresh.
- **Search quality:** optional semantic backend, hybrid (lexical + vector) search, filters, auto-categorization.
- **DX & distribution:** HTTP/SSE transport, packaging, verified per-client setup docs.

PRs toward any of these are welcome.

---

## Tech stack

Python 3.12+ · [`uv`](https://docs.astral.sh/uv/) · [FastMCP](https://github.com/modelcontextprotocol/python-sdk) · SQLite + FTS5 (search) · `httpx` + GitHub REST. Optional semantic search via `fastembed` + `sqlite-vec` (`skill-ninja[semantic]`). A TypeScript/Node port is a viable alternative if `npx` distribution is preferred.

---

## Contributing

Contributions are welcome — **new source adapters** and **verified per-client setup docs** are especially valuable. Open an issue to discuss, or send a PR.

Format background: [agent-skills-reference.md](agent-skills-reference.md) · full design: [CLAUDE.md](CLAUDE.md).

---

## License

[Apache-2.0](LICENSE) — aligned with the Agent Skills ecosystem.

> skill-ninja indexes and downloads third-party skills but does not redistribute them; each skill keeps its own license, which skill-ninja surfaces in search results.
