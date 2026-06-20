"""Launch skill-ninja over the streamable-HTTP transport and drive it as a client.

Validates the Phase 4 HTTP transport end to end: spawns the server subprocess with
``--transport streamable-http``, connects over HTTP, and runs initialize ->
list_tools -> call_tool. Uses a throwaway data dir and a high port.

    .venv\\Scripts\\python.exe scripts\\mcp_http_check.py
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PORT = 8765
URL = f"http://127.0.0.1:{PORT}/mcp"


def payload(result) -> dict:
    if result.structuredContent:
        return result.structuredContent
    return json.loads(result.content[0].text)


async def drive() -> None:
    # Retry until the server has bound the port and is serving.
    last_exc: Exception | None = None
    for _attempt in range(30):
        try:
            async with streamablehttp_client(URL) as (read, write, _):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    info = init.serverInfo
                    print(f"[i] connected over HTTP to {info.name} v{info.version}")

                    tools = await session.list_tools()
                    names = [t.name for t in tools.tools]
                    print(f"[1] list_tools -> {len(names)} tools")
                    assert "search_skills" in names

                    print("[2] call_tool search_skills(query='pdf', top_k=2)")
                    res = await session.call_tool("search_skills", {"query": "pdf", "top_k": 2})
                    data = payload(res)
                    for r in data["results"]:
                        print(f"    - {r['name']}  score={r['score']}")
                    assert data["count"] >= 1
                    print(f"    backend: {data.get('backend')}")
            return
        except Exception as exc:  # not ready yet, or transient
            last_exc = exc
            await asyncio.sleep(0.5)
    raise RuntimeError(f"could not reach HTTP server after retries: {last_exc!r}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="skill-ninja-http-"))
    env = {**os.environ, "SKILL_NINJA_DATA_DIR": str(tmp), "PYTHONUTF8": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "skill_ninja", "--transport", "streamable-http",
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        asyncio.run(drive())
        print("\n[OK] HTTP transport round-trip passed ✅")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


if __name__ == "__main__":
    main()
