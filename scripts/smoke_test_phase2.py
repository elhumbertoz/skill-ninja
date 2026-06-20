"""Live Phase 2 smoke test: multi-source (generic git + local FS) + source management.

Exercises add_source / refresh (incremental) / search / get_skill / remove_source
against a real git repo and a local folder, in a throwaway data dir. Requires `git`
on PATH and network access for the git source. Run:

    .venv\\Scripts\\python.exe scripts\\smoke_test_phase2.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from skill_ninja.catalog import Catalog
from skill_ninja.config import Config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# A small public repo that hosts skills under SKILL.md folders.
GIT_SOURCE = "https://github.com/anthropics/skills.git"


def _make_local_skill(root: Path, name: str, desc: str) -> None:
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n# {name}\n", encoding="utf-8"
    )


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="skill-ninja-p2-"))
    cfg = Config(data_dir=tmp / "data", sources=[])  # no default github source
    cfg.ensure_dirs()
    print(f"[i] scratch data dir: {cfg.data_dir}")

    local_dir = tmp / "my-local-skills"
    _make_local_skill(local_dir, "report-styler", "Format internal status reports, house style")
    _make_local_skill(local_dir, "sql-linter", "Lint and format SQL queries to team conventions")

    with Catalog(cfg) as cat:
        print("\n[1] add_source(local folder) + add_source(git, forcing the clone adapter)")
        print("    local:", cat.add_source(str(local_dir)))
        # Force source_type='git' so a github.com URL routes through the generic git
        # (shallow-clone) adapter rather than the REST GitHub adapter.
        print("    git:  ", cat.add_source(GIT_SOURCE, source_type="git"))

        print("\n[2] list_sources (before indexing)")
        for s in cat.list_sources():
            print(f"    {s['type']:<7} indexed={s['indexed']}  {s['url']}")

        print("\n[3] refresh() — clones the git repo + hashes the local folder")
        out = cat.refresh()
        for s in out["sources"]:
            print(f"    {s['source']}  skills={s['skills']}  skipped={s['skipped']}")
        print(f"    total indexed: {out['indexed']}")

        print("\n[4] search('lint sql') — should surface the LOCAL skill")
        for r in cat.search("lint sql", top_k=3):
            print(f"    - {r['name']:<16} [{r['source_type']}] score={r['score']}")

        print("\n[5] search('pdf form') — should surface a GIT (anthropics) skill")
        git_hit = None
        for r in cat.search("pdf form", top_k=3):
            print(f"    - {r['name']:<16} [{r['source_type']}] score={r['score']}")
            if r["source_type"] == "git" and git_hit is None:
                git_hit = r["skill_id"]

        if git_hit:
            print(f"\n[6] get_skill('{git_hit}') from the git clone")
            skill = cat.get_skill(git_hit)
            md_len, n_files = len(skill["content"]), len(skill["files"])
            print(f"    name={skill['name']}  SKILL.md={md_len} chars  files={n_files}")

        print("\n[7] refresh() again — incremental, both sources should SKIP")
        out2 = cat.refresh()
        for s in out2["sources"]:
            print(f"    {s['source']}  skipped={s['skipped']}")
        assert all(s["skipped"] for s in out2["sources"]), "expected all sources skipped"

        print("\n[8] remove_source(local, purge=True)")
        print("   ", cat.remove_source(str(local_dir.resolve()), purge=True))
        print(f"    sources left: {[s['type'] for s in cat.list_sources()]}")

    print("\n[OK] Phase 2 live smoke test passed ✅")


if __name__ == "__main__":
    main()
