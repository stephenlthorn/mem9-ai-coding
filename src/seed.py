"""Seed the mem9 knowledge base.

Team `acme` (the demo team) gets both repos fully populated: pulumi_kb + lza_kb.
Team `globex` gets a minimal pulumi_kb so the team-isolation demo (Scenario C) has
a real second team whose data Team A must NOT be able to read.

Usage:
  python -m src.seed --reset           # reseed acme (both repos) + globex (minimal)
  python -m src.seed --reset --repo lza # reseed only acme's lza_kb
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, ingest, topology


def seed(reset: bool = False, repo: str | None = None) -> None:
    if repo:
        n = ingest.bootstrap(repo, reset=reset)
        print(f"Seeded {repo} -> {db.database_for(repo)} ({n} components) on {db.backend_name()}")
        return

    counts = ingest.bootstrap_all(reset=reset)
    _seed_second_team(reset=reset)
    print(f"Seeded knowledge base on {db.backend_name()}:")
    print(f"  team acme: pulumi_kb ({counts['pulumi']}) + lza_kb ({counts['lza']})")
    print("  team globex: pulumi_kb (2) - for the team-isolation demo")
    print("  staging is missing its DNS + SSO layer (the live-demo task)")


def _seed_second_team(reset: bool) -> None:
    team = "globex"
    if reset:
        db.reset_db(team, ["pulumi"])
    else:
        db.init_db(team, ["pulumi"])
    db.write_component(repo="pulumi", team_name=team, name="globex-prod-ledger-db", type="RDS",
                       env="production", summary="Globex production ledger database (private to Globex).",
                       developer="seed", account_ref="prod")
    db.write_component(repo="pulumi", team_name=team, name="globex-prod-secrets", type="S3",
                       env="production", summary="Globex production secrets bucket (private to Globex).",
                       developer="seed", account_ref="prod")


if __name__ == "__main__":
    reset = "--reset" in sys.argv or "--reseed" in sys.argv
    repo = None
    for i, a in enumerate(sys.argv):
        if a == "--repo" and i + 1 < len(sys.argv):
            repo = sys.argv[i + 1]
    seed(reset=reset, repo=repo)
