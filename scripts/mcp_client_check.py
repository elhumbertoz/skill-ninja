"""Launch the real MCP server over stdio and drive it like a client would.

Validates the MCP wiring end to end: initialize -> list_tools -> call_tool. Uses a
throwaway data dir (via SKILL_NINJA_DATA_DIR) so it never touches the real catalog.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def payload(result) -> dict:
    """Extract a tool's dict payload (structured output, else parse JSON text)."""
    if result.structuredContent:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="skill-ninja-mcp-"))
    env = {**os.environ, "SKILL_NINJA_DATA_DIR": str(tmp), "PYTHONUTF8": "1"}
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "skill_ninja"],
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"[i] connected to MCP server: {init.serverInfo.name} v{init.serverInfo.version}")

            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            print(f"[1] list_tools -> {names}")
            assert "search_skills" in names and "download_skill" in names

            print("\n[2] call_tool search_skills(query='web app testing', top_k=3)")
            res = await session.call_tool("search_skills", {"query": "web app testing", "top_k": 3})
            data = payload(res)
            for r in data["results"]:
                print(f"    - {r['name']:<22} score={r['score']}")
            assert data["count"] >= 1

            top_id = data["results"][0]["skill_id"]
            print(f"\n[3] call_tool get_skill('{top_id}')")
            res = await session.call_tool("get_skill", {"skill_id": top_id})
            skill = payload(res)
            print(
                f"    name={skill['name']}  SKILL.md={len(skill['content'])} chars  "
                f"files={len(skill['files'])}"
            )
            assert skill["content"]

    print("\n[OK] MCP server stdio round-trip passed ✅")


if __name__ == "__main__":
    asyncio.run(main())
