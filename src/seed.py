"""Seed the Acme infrastructure knowledge base."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import init_db, reset_db, write_component, write_edge


def seed(reset: bool = False) -> None:
    if reset:
        reset_db()
    else:
        init_db()

    # ── Library components ──────────────────────────────────────────────────
    write_component(
        name="S3Bucket",
        type="Library",
        env="library",
        repo_path="libs/s3-bucket/index.ts",
        summary=(
            "Reusable S3 bucket component. Enforces versioning, encryption at rest, "
            "lifecycle rules, and required tags (Environment, ManagedBy, Component, Team). "
            "Physical name follows acme-<env>-<logical> convention."
        ),
        code_excerpt=(
            "export class S3Bucket extends pulumi.ComponentResource {\n"
            "  constructor(name: string, args: S3BucketArgs, opts?: pulumi.ComponentResourceOptions) {\n"
            "    // enforces acme-<env>-<name> naming, required tags, encryption\n"
            "  }\n}"
        ),
        developer="seed",
    )

    write_component(
        name="PostgresDatabase",
        type="Library",
        env="library",
        repo_path="libs/postgres-db/index.ts",
        summary=(
            "Reusable RDS Postgres component. Automatically instantiates an S3Bucket "
            "for backups - do NOT create a separate backup bucket manually. "
            "Multi-AZ in production, single-AZ in staging."
        ),
        code_excerpt=(
            "export class PostgresDatabase extends pulumi.ComponentResource {\n"
            "  public readonly backupBucket: S3Bucket;  // auto-created\n"
            "  constructor(name: string, args: PostgresDatabaseArgs, opts?) {\n"
            "    this.backupBucket = new S3Bucket(`${name}-backup`, ...);\n"
            "  }\n}"
        ),
        developer="seed",
        depends_on="S3Bucket",
        relationship="instantiates",
    )

    write_component(
        name="DnsRecord",
        type="Library",
        env="library",
        repo_path="libs/dns-record/index.ts",
        summary=(
            "Reusable Cloudflare DNS record component. Always enables Cloudflare proxy "
            "(orange cloud). All new public endpoints must use this component."
        ),
        code_excerpt=(
            "export class DnsRecord extends pulumi.ComponentResource {\n"
            "  public readonly hostname: pulumi.Output<string>;\n"
            "  // proxied: true always - never set proxied: false\n}"
        ),
        developer="seed",
    )

    write_component(
        name="SsoApplication",
        type="Library",
        env="library",
        repo_path="libs/sso-app/index.ts",
        summary=(
            "Reusable Okta SSO application component. "
            "Redirect URIs must point at the corresponding DnsRecord hostname. "
            "Used for all internal services requiring SSO."
        ),
        code_excerpt=(
            "export class SsoApplication extends pulumi.ComponentResource {\n"
            "  constructor(name: string, args: SsoApplicationArgs, opts?) {\n"
            "    // redirectUris must point at a DnsRecord hostname\n"
            "  }\n}"
        ),
        developer="seed",
    )

    # ── Production resources (full reference set) ─────────────────────────────
    write_component(
        name="acme-prod-analytics-db", type="RDS", env="production",
        repo_path="environments/production/analytics.ts",
        summary=("Production analytics Postgres database (multi-AZ). Composes PostgresDatabase. "
                 "Backup bucket acme-prod-analytics-db-backup auto-created by the library."),
        developer="seed", depends_on="PostgresDatabase",
    )
    write_component(
        name="acme-prod-data-exports", type="S3", env="production",
        repo_path="environments/production/storage.ts",
        summary="Production data exports bucket. Composes S3Bucket library.",
        developer="seed", depends_on="S3Bucket",
    )
    write_component(
        name="acme-prod-static-assets", type="S3", env="production",
        repo_path="environments/production/storage.ts",
        summary="Production static assets bucket. Fronted by acme-prod-assets-dns (Cloudflare CDN).",
        developer="seed", depends_on="S3Bucket",
    )
    write_component(
        name="acme-prod-assets-dns", type="Cloudflare", env="production",
        repo_path="environments/production/dns.ts",
        summary="Cloudflare DNS record fronting acme-prod-static-assets. Proxied: true.",
        developer="seed", depends_on="DnsRecord",
    )
    write_component(
        name="acme-prod-admin-dns", type="Cloudflare", env="production",
        repo_path="environments/production/dns.ts",
        summary="Cloudflare DNS record for the admin portal. acme-prod-admin-sso redirects here.",
        developer="seed", depends_on="DnsRecord",
    )
    write_component(
        name="acme-prod-admin-sso", type="Okta", env="production",
        repo_path="environments/production/sso.ts",
        summary="Okta SSO application for admin portal. Redirect URI points at acme-prod-admin-dns.",
        developer="seed", depends_on="SsoApplication",
    )

    # ── Staging resources (data layer only - DNS + SSO missing) ──────────────
    write_component(
        name="acme-staging-analytics-db", type="RDS", env="staging",
        repo_path="environments/staging/analytics.ts",
        summary="Staging analytics Postgres database (single-AZ). Composes PostgresDatabase.",
        developer="seed", depends_on="PostgresDatabase",
    )
    write_component(
        name="acme-staging-data-exports", type="S3", env="staging",
        repo_path="environments/staging/storage.ts",
        summary="Staging data exports bucket. Composes S3Bucket library.",
        developer="seed", depends_on="S3Bucket",
    )

    # ── Composition edges beyond simple depends_on ───────────────────────────
    write_edge("acme-prod-assets-dns", "acme-prod-static-assets", "fronts",
               "CDN DNS record proxies requests to the static assets bucket")
    write_edge("acme-prod-admin-sso", "acme-prod-admin-dns", "redirects_to",
               "Okta redirect URI points at the admin DNS hostname")

    print("Seeded knowledge base:")
    print("  4 library components (S3Bucket, PostgresDatabase, DnsRecord, SsoApplication)")
    print("  6 production resources (full set)")
    print("  2 staging resources (data layer only - DNS + SSO missing)")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv or "--reseed" in sys.argv)
