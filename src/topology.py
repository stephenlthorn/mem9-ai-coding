"""Team / repo topology for the mem9 knowledge base.

Model:
  team  -> a mem9 space (API key scopes access to one team's memories).
  repo  -> a namespace within the team's space, expressed as appId: {team}_{repo}_kb.

The underlying TiDB cluster is provisioned and managed by mem9.ai - callers never
handle raw database credentials.
"""
from __future__ import annotations

import os
from pathlib import Path

if not os.environ.get("PYTEST_CURRENT_TEST"):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env", override=False)
    except Exception:
        pass

# repo registry: logical repo -> source dir + manifest module
REPOS: dict[str, dict] = {
    "pulumi": {"source": "environments", "manifest": "src.repos.pulumi"},
    "lza":    {"source": "lza",          "manifest": "src.repos.lza"},
}


def team() -> str:
    return os.environ.get("MEM9_TEAM", "acme").strip().lower()


def repo_names() -> list[str]:
    return list(REPOS.keys())


def api_key() -> str:
    key = os.environ.get("MEM9_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "MEM9_API_KEY not set. Copy .env.example to .env and paste your mem9 space key."
        )
    return key


def base_url() -> str:
    return os.environ.get("MEM9_BASE_URL", "https://api.mem9.ai").rstrip("/")


def ns_version() -> str:
    """Optional namespace version suffix (e.g. 'v2') for a pristine appId.

    mem9 spaces accumulate history and list reads are eventually consistent /
    capped; bumping MEM9_NS_VERSION gives a clean namespace without changing the
    team/repo model. Empty (default) keeps the canonical {team}_{repo}_kb form.
    """
    return os.environ.get("MEM9_NS_VERSION", "").strip().lower()


def app_id(repo: str, team_name: str | None = None) -> str:
    """appId used for per-repo namespace isolation inside a mem9 space."""
    if repo not in REPOS:
        raise KeyError(f"unknown repo: {repo!r} (known: {list(REPOS)})")
    base = f"{(team_name or team()).strip().lower()}_{repo}_kb"
    ver = ns_version()
    return f"{base}_{ver}" if ver else base
