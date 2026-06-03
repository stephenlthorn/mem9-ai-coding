"""CLI writeback tool: record a new component to the knowledge base.

Usage:
  python -m src.writeback \\
    --name acme-staging-admin-dns \\
    --type Cloudflare \\
    --env staging \\
    --summary "Cloudflare DNS record for staging admin portal" \\
    --depends-on DnsRecord \\
    --developer claude-code
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import init_db, write_component


def main() -> None:
    p = argparse.ArgumentParser(description="Record a component to the infra knowledge base")
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True, choices=["S3", "RDS", "Cloudflare", "Okta", "Library"])
    p.add_argument("--env", required=True, choices=["production", "staging", "library"])
    p.add_argument("--summary", required=True)
    p.add_argument("--depends-on", dest="depends_on")
    p.add_argument("--developer", required=True)
    p.add_argument("--repo-path", dest="repo_path")
    args = p.parse_args()

    init_db()
    comp_id = write_component(
        name=args.name,
        type=args.type,
        env=args.env,
        summary=args.summary,
        depends_on=args.depends_on,
        developer=args.developer,
        repo_path=args.repo_path,
    )
    print(f"Written: {args.name} (id={comp_id})")


if __name__ == "__main__":
    main()
