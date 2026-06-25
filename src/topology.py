"""Team / repo / target topology for the mem9 knowledge base.

Model:
  team  -> a TiDB cluster in production; a database-name namespace in this demo.
  repo  -> a database inside the team's cluster (pulumi -> *_pulumi_kb, lza -> *_lza_kb).

Targets (capabilities differ; see capability matrix in README):
  cloud  - mem9.ai / TiDB Cloud Starter: EMBED_TEXT auto-embed + FULLTEXT + hybrid.
  local  - self-hosted tiup playground: vector (precomputed) + LIKE, no full-text.
  sqlite - offline/test substrate: relational + LIKE only, no vector.
"""
from __future__ import annotations

import os
from pathlib import Path

# Skip .env loading when running under pytest so monkeypatch controls env cleanly.
if not os.environ.get("PYTEST_CURRENT_TEST"):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env", override=False)
    except Exception:
        pass

# repo registry: logical repo -> (database stem, source dir, manifest module)
REPOS: dict[str, dict] = {
    "pulumi": {"db_stem": "pulumi_kb", "source": "environments", "manifest": "src.repos.pulumi"},
    "lza": {"db_stem": "lza_kb", "source": "lza", "manifest": "src.repos.lza"},
}


def team() -> str:
    return os.environ.get("MEM9_TEAM", "acme").strip().lower()


def repo_names() -> list[str]:
    return list(REPOS.keys())


def target() -> str:
    host = os.environ.get("TIDB_HOST", "").strip()
    if not host:
        return "sqlite"
    explicit = os.environ.get("MEM9_TARGET", "").strip().lower()
    if explicit in ("cloud", "local"):
        return explicit
    if "tidbcloud.com" in host or host.endswith(".mem9.ai"):
        return "cloud"
    return "local"


def has_vector() -> bool:
    return target() in ("cloud", "local")


def has_fulltext() -> bool:
    return target() == "cloud"


def has_auto_embed() -> bool:
    return target() == "cloud"


def database_for(repo: str, team: str | None = None) -> str:
    if repo not in REPOS:
        raise KeyError(f"unknown repo: {repo!r} (known: {list(REPOS)})")
    team_name = (team or _current_team()).strip().lower()
    return f"{team_name}_{REPOS[repo]['db_stem']}"


def _current_team() -> str:
    return os.environ.get("MEM9_TEAM", "acme").strip().lower()
