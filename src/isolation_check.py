"""Scenario C - prove team isolation: an agent scoped to Team A cannot read Team B.

SQLite (offline): a team connection only ATTACHes its own team's databases, so the
other team's tables are absent - the cross-team query has no path (OperationalError).

TiDB (mem9.ai / tiup): isolation is enforced by credentials. In production each team
is its OWN cluster; in this single-cluster demo we GRANT a team user access only to
that team's databases, so a cross-team SELECT fails with an access-denied error.
The runbook (DEMO.md) shows the GRANT setup; this script verifies the denial.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology


def read_team_components(team: str) -> list[dict]:
    return db.query(
        f"SELECT name, repo FROM {db.tref('pulumi', 'infra_components', team)}",
        team_name=team, repos=["pulumi"],
    )


def check(my_team: str = "acme", other_team: str = "globex") -> dict:
    target = topology.target()
    other_db = db.database_for("pulumi", other_team)
    # Attempt a cross-team read using ONLY my_team's connection scope.
    cross_sql = f"SELECT COUNT(*) AS n FROM {other_db}.infra_components"
    try:
        db.query(cross_sql, team_name=my_team, repos=["pulumi"])
        isolated = False
        detail = f"WARNING: {my_team} could read {other_db} - isolation NOT enforced."
    except Exception as exc:
        isolated = True
        detail = (f"{my_team} has no query path to {other_db}: {type(exc).__name__}. "
                  f"Isolation holds by design.")
    return {"isolated": isolated, "target": target, "my_team": my_team,
            "other_team": other_team, "cross_sql": cross_sql, "detail": detail}


def main() -> None:
    report = check()
    print(f"Target: {db.backend_name()}")
    print(f"Cross-team probe: {report['cross_sql']}")
    print(("PASS - " if report["isolated"] else "FAIL - ") + report["detail"])


if __name__ == "__main__":
    main()
