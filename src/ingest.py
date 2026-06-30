"""Bootstrap / backfill: populate a repo's KB from its source BEFORE any agent session.

This is the EXPLICIT setup step (not automatic). On cloud (mem9.ai) embeddings are
generated server-side via EMBED_TEXT on insert; on local tiup they are precomputed
client-side; SQLite stores no embedding. Re-running is idempotent (upsert by name).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology
from src.repos import load_manifest
import importlib


def bootstrap(repo: str, reset: bool = False, team_name: str | None = None) -> int:
    team_name = team_name or topology.team()
    if reset:
        db.reset_db(team_name, [repo])
    else:
        db.init_db(team_name, [repo])

    components = load_manifest(repo)
    for c in components:
        db.write_component(
            repo=repo, name=c["name"], type=c["type"], env=c["env"], summary=c["summary"],
            depends_on=c.get("depends_on"), relationship=c.get("relationship", "uses"),
            developer="seed", repo_path=c.get("repo_path"), code_excerpt=c.get("code_excerpt"),
            account_ref=c.get("account_ref"), team_name=team_name,
        )

    manifest_mod = importlib.import_module(topology.REPOS[repo]["manifest"])
    for edge in getattr(manifest_mod, "EDGES", []):
        db.write_edge(repo, *edge, team_name=team_name)

    return len(components)


def bootstrap_all(reset: bool = False, team_name: str | None = None) -> dict[str, int]:
    return {r: bootstrap(r, reset=reset, team_name=team_name) for r in topology.repo_names()}


def main() -> None:
    reset = "--reset" in sys.argv or "--reseed" in sys.argv
    repo = None
    for i, a in enumerate(sys.argv):
        if a == "--repo" and i + 1 < len(sys.argv):
            repo = sys.argv[i + 1]
    target = db.backend_name()
    if repo:
        n = bootstrap(repo, reset=reset)
        print(f"Bootstrapped {repo} -> {db.database_for(repo)} ({n} components) on {target}")
    else:
        counts = bootstrap_all(reset=reset)
        for r, n in counts.items():
            print(f"Bootstrapped {r} -> {db.database_for(r)} ({n} components) on {target}")


if __name__ == "__main__":
    main()
