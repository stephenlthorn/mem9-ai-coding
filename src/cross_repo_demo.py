"""Scenario B - cross-repo task over ONE team connection (no separate per-cluster auth).

"Create a new AWS account in LZA, then create an S3 bucket in that account in Pulumi."
Reads/writes BOTH acme_lza_kb and acme_pulumi_kb (same team cluster), then runs a
cross-database JOIN to show the bucket mapped to its account.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db


def run(account_ref: str = "data-platform", developer: str = "claude-code") -> dict:
    account_name = f"acme-lza-account-{account_ref}"
    bucket_name = f"acme-prod-{account_ref}-exports"

    # 1. Write the new AWS account into the LZA repo database.
    db.write_component(
        repo="lza", name=account_name, type="Account", env="org",
        summary=f"AWS account (account_ref={account_ref}) created for the {account_ref} workload.",
        depends_on="AwsAccount", developer=developer, account_ref=account_ref,
        repo_path="lza/accounts.ts",
    )

    # 2. Write the S3 bucket into the Pulumi repo database, tagged to that account.
    db.write_component(
        repo="pulumi", name=bucket_name, type="S3", env="production",
        summary=f"Exports bucket deployed into AWS account {account_ref}. Composes S3Bucket.",
        depends_on="S3Bucket", developer=developer, account_ref=account_ref,
        repo_path="environments/production/storage.ts",
    )

    # 3. One cross-database JOIN proves the link, over a single team connection.
    sql = db.cross_repo_accounts_sql(db.database_for("pulumi"), db.database_for("lza"))
    joined = db.query(sql)
    return {"sql": sql, "joined": joined, "account": account_name, "bucket": bucket_name}


def main() -> None:
    out = run()
    print(f"Created {out['account']} (lza_kb) and {out['bucket']} (pulumi_kb) on {db.backend_name()}\n")
    print("Cross-database JOIN (acme_pulumi_kb x acme_lza_kb):")
    for r in out["joined"]:
        print(f"  {r['pulumi_component']:<34} -> account {r['account_ref']:<14} ({r['lza_account']})")


if __name__ == "__main__":
    main()
