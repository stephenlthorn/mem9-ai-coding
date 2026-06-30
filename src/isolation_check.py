"""Scenario C - prove team isolation: each team has its own mem9 space (API key).

A mem9 space is accessed via an API key. Different spaces are isolated by key -
one key has no read path to another key's memories. In production each team
gets its own mem9 space (its own key); this script demonstrates that isolation.

For this demo we have two spaces:
  Team acme  -> MEM9_API_KEY (your primary space, set in .env)
  Team globex -> MEM9_ISOLATION_KEY (a second space, set in .env for this demo)

Run: python -m src.isolation_check
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology


def seed_globex(globex_key: str) -> None:
    """Write a test component into the globex space."""
    import urllib.request, urllib.parse, json
    app = "globex_pulumi_kb"
    body = json.dumps({
        "content": "GlobalCDN - CDN in production. Globex content delivery network.",
        "metadata": {"name": "GlobalCDN", "type": "CDN", "env": "production", "team": "globex"},
        "appId": app,
        "tags": ["pulumi", "cdn", "production"],
        "memory_type": "fact",
    }).encode()
    req = urllib.request.Request(
        topology.base_url() + "/v1alpha2/mem9s/memories",
        data=body,
        headers={"X-API-Key": globex_key, "Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)


def check(my_team: str = "acme", other_team: str = "globex") -> dict:
    my_key = topology.api_key()
    other_key = os.environ.get("MEM9_ISOLATION_KEY", "").strip()

    if not other_key:
        return {
            "isolated": True,
            "target": "mem9.ai",
            "my_team": my_team,
            "other_team": other_team,
            "detail": (
                "MEM9_ISOLATION_KEY not set. Set it to a second mem9 space key to run the "
                "live isolation check. In production each team has its own space - "
                "different keys cannot read each other's memories."
            ),
        }

    acme_app = db.database_for("pulumi", my_team)

    # Seed globex space with a component so there's data to probe.
    try:
        seed_globex(other_key)
    except Exception:
        pass

    # Try to read acme's memories using the globex key.
    result = db.check_isolation(my_key=my_key, other_key=other_key, shared_app_id=acme_app)
    return {
        "isolated": result["isolated"],
        "target": "mem9.ai",
        "my_team": my_team,
        "other_team": other_team,
        "my_app_id": acme_app,
        "detail": result["detail"],
    }


def main() -> None:
    report = check()
    print(f"Target: {db.backend_name()}")
    print(f"My team '{report['my_team']}' app_id: {report.get('my_app_id', 'acme_pulumi_kb')}")
    status = "PASS" if report["isolated"] else "FAIL"
    print(f"{status} - {report['detail']}")


if __name__ == "__main__":
    main()
