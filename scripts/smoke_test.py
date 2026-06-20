"""Live end-to-end smoke test against the real anthropics/skills repo.

Exercises the motivating walkthrough: lazy auto-index -> search("xlsx") ->
get_skill -> read_skill_file -> download_skill. Writes to a throwaway data dir so
it never touches the user's real catalog. Run:

    .venv\\Scripts\\python.exe scripts\\smoke_test.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from skill_ninja.catalog import Catalog
from skill_ninja.config import load_config

# Windows consoles default to cp1252; skill content / output may contain non-ASCII.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="skill-ninja-smoke-"))
    cfg = load_config()
    cfg.data_dir = tmp  # redirect everything into the throwaway dir
    cfg.ensure_dirs()
    print(f"[i] scratch data dir: {tmp}")

    with Catalog(cfg) as cat:
        print("\n[1] search_skills('edit xlsx spreadsheet')  (triggers lazy auto-index)")
        results = cat.search("edit xlsx spreadsheet", top_k=5)
        print(f"    indexed catalog now holds {cat.db.count_skills()} skills")
        for r in results:
            print(f"    - {r['name']:<22} score={r['score']:<8} license={r['license']}")
        assert results, "expected search hits"
        assert results[0]["name"] == "xlsx", f"expected xlsx first, got {results[0]['name']}"

        top = results[0]
        skill_id = top["skill_id"]
        print(f"\n[2] get_skill('{skill_id}')")
        skill = cat.get_skill(skill_id)
        n_files = len(skill["files"])
        print(f"    SKILL.md is {len(skill['content'])} chars; bundle has {n_files} files")
        print(f"    first files: {skill['files'][:5]}")
        assert "name: xlsx" in skill["content"]

        # Pick a small text resource to read, if present.
        text_file = next((f for f in skill["files"] if f.endswith((".md", ".py", ".txt"))), None)
        if text_file:
            print(f"\n[3] read_skill_file('{skill_id}', '{text_file}')")
            res = cat.read_skill_file(skill_id, text_file)
            preview = res.get("content", "")[:80].replace("\n", " ")
            print(f"    binary={res['binary']} preview={preview!r}")

        print(f"\n[4] download_skill('{skill_id}')")
        manifest = cat.download_skill(skill_id)
        print(f"    wrote {len(manifest['files'])} files to {manifest['dest']}")
        print(f"    pinned version (SHA): {manifest['version']}")
        assert (Path(manifest["dest"]) / "SKILL.md").is_file()

        print("\n[5] list_local_skills()")
        local = cat.list_local()
        print(f"    {len(local)} downloaded: {[s['name'] for s in local]}")
        assert any(s["skill_id"] == skill_id for s in local)

        print("\n[6] list_sources()")
        for s in cat.list_sources():
            print(f"    {s['url']}  indexed={s['indexed']}  version={s['version']}")

    print("\n[OK] live end-to-end smoke test passed ✅")


if __name__ == "__main__":
    main()
