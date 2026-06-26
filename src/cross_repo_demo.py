"""Scenario B - cross-repo task over ONE mem9 space (no separate per-key auth).

"Create a new AWS account in LZA, then create an S3 bucket in that account in Pulumi."
Writes to both acme_lza_kb and acme_pulumi_kb (same API key, different appId namespaces),
then searches across both repos and joins client-side to show the bucket mapped to its account.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db


def run(account_ref: str = "data-platform", developer: str = "claude-code") -> dict:
    account_name = f"acme-lza-account-{account_ref}"
    bucket_name = f"acme-prod-{account_ref}-exports"

    # 1. Write the new AWS account into the LZA repo namespace.
    db.write_component(
        repo="lza", name=account_name, type="Account", env="org",
        summary=f"AWS account (account_ref={account_ref}) created for the {account_ref} workload.",
        depends_on="AwsAccount", developer=developer, account_ref=account_ref,
        repo_path="lza/accounts.ts",
    )

    # 2. Write the S3 bucket into the Pulumi repo namespace, tagged to that account.
    db.write_component(
        repo="pulumi", name=bucket_name, type="S3", env="production",
        summary=f"Exports bucket deployed into AWS account {account_ref}. Composes S3Bucket.",
        depends_on="S3Bucket", developer=developer, account_ref=account_ref,
        repo_path="environments/production/storage.ts",
    )

    # 3. Search both namespaces and join client-side on account_ref.
    import time; time.sleep(2)  # allow mem9 to index before recall
    lza_hits = db.recall(db.database_for("lza"), account_ref, limit=10)
    pulumi_hits = db.recall(db.database_for("pulumi"), account_ref, limit=10)

    # Build a join: Pulumi resources <-> LZA accounts sharing account_ref
    lza_accounts = {
        m["metadata"].get("account_ref"): m["metadata"].get("name")
        for m in lza_hits
        if m.get("metadata", {}).get("type") == "Account"
    }
    joined = []
    for m in pulumi_hits:
        meta = m.get("metadata", {})
        ref = meta.get("account_ref")
        if ref and ref in lza_accounts:
            joined.append({
                "pulumi_component": meta.get("name"),
                "pulumi_type": meta.get("type"),
                "account_ref": ref,
                "lza_account": lza_accounts[ref],
            })

    return {
        "account": account_name,
        "bucket": bucket_name,
        "joined": joined,
        "lza_app_id": db.database_for("lza"),
        "pulumi_app_id": db.database_for("pulumi"),
    }


def main() -> None:
    out = run()
    print(f"Created {out['account']} ({out['lza_app_id']}) "
          f"and {out['bucket']} ({out['pulumi_app_id']}) on {db.backend_name()}\n")
    print(f"Cross-repo join ({out['pulumi_app_id']} x {out['lza_app_id']}):")
    for r in out["joined"]:
        print(f"  {r['pulumi_component']:<34} -> account {r['account_ref']:<14} ({r['lza_account']})")
    if not out["joined"]:
        print("  (no cross-repo links found yet - index may still be warming up)")


if __name__ == "__main__":
    main()
