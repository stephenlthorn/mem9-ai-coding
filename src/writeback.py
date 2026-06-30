"""CLI writeback: record a component to a repo's KB (instruction-driven persist).

Usage:
  python -m src.writeback --repo pulumi \\
    --name acme-staging-admin-dns --type Cloudflare --env staging \\
    --summary "Cloudflare DNS for staging admin portal" \\
    --depends-on DnsRecord --account-ref sandbox --developer claude-code
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology


def main() -> None:
    p = argparse.ArgumentParser(description="Record a component to a repo's mem9 KB")
    p.add_argument("--repo", required=True, choices=topology.repo_names())
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--env", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--depends-on", dest="depends_on")
    p.add_argument("--account-ref", dest="account_ref")
    p.add_argument("--developer", required=True)
    p.add_argument("--repo-path", dest="repo_path")
    args = p.parse_args()

    db.init_db(repos=[args.repo])
    comp_id = db.write_component(
        repo=args.repo, name=args.name, type=args.type, env=args.env, summary=args.summary,
        depends_on=args.depends_on, account_ref=args.account_ref, developer=args.developer,
        repo_path=args.repo_path,
    )
    print(f"Written to {db.database_for(args.repo)}: {args.name} (id={comp_id})")


if __name__ == "__main__":
    main()
