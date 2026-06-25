"""Pulumi infra-as-code repo manifest (repo = pulumi -> *_pulumi_kb).

Mirrors the original Acme scenario: 4 libraries, full production, staging missing
its DNS + SSO layer (the live-demo task). account_ref maps each resource to an LZA
account so cross-repo JOINs work (prod -> 'prod', staging -> 'sandbox')."""
from __future__ import annotations

REPO = "pulumi"

COMPONENTS = [
    # ── Libraries ──
    {"name": "S3Bucket", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/s3-bucket/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable S3 bucket component. Enforces versioning, encryption at rest, "
                "lifecycle rules, required tags. Physical name acme-<env>-<logical>.",
     "code_excerpt": "export class S3Bucket extends pulumi.ComponentResource { /* tags, encryption */ }"},
    {"name": "PostgresDatabase", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/postgres-db/index.ts", "account_ref": None,
     "depends_on": "S3Bucket", "relationship": "instantiates",
     "summary": "Reusable RDS Postgres component. Automatically instantiates an S3Bucket for "
                "backups - do NOT create a backup bucket manually. Multi-AZ in prod, single-AZ staging.",
     "code_excerpt": "this.backupBucket = new S3Bucket(`${name}-backup`, ...);"},
    {"name": "DnsRecord", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/dns-record/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable Cloudflare DNS record. Always proxied (orange cloud). All new public "
                "endpoints must use this component.",
     "code_excerpt": "// proxied: true always - never set proxied: false"},
    {"name": "SsoApplication", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/sso-app/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable Okta SSO application. Redirect URIs must point at the corresponding "
                "DnsRecord hostname. Used for all internal services requiring SSO.",
     "code_excerpt": "// redirectUris must point at a DnsRecord hostname"},

    # ── Production (account_ref = prod) ──
    {"name": "acme-prod-analytics-db", "type": "RDS", "env": "production", "repo": REPO,
     "repo_path": "environments/production/analytics.ts", "account_ref": "prod",
     "depends_on": "PostgresDatabase",
     "summary": "Production analytics Postgres (multi-AZ). Composes PostgresDatabase; backup bucket auto-created."},
    {"name": "acme-prod-data-exports", "type": "S3", "env": "production", "repo": REPO,
     "repo_path": "environments/production/storage.ts", "account_ref": "prod",
     "depends_on": "S3Bucket", "summary": "Production data exports bucket. Composes S3Bucket."},
    {"name": "acme-prod-static-assets", "type": "S3", "env": "production", "repo": REPO,
     "repo_path": "environments/production/storage.ts", "account_ref": "prod",
     "depends_on": "S3Bucket", "summary": "Production static assets bucket. Fronted by acme-prod-assets-dns (CDN)."},
    {"name": "acme-prod-assets-dns", "type": "Cloudflare", "env": "production", "repo": REPO,
     "repo_path": "environments/production/dns.ts", "account_ref": "prod",
     "depends_on": "DnsRecord", "summary": "Cloudflare DNS fronting acme-prod-static-assets. Proxied: true."},
    {"name": "acme-prod-admin-dns", "type": "Cloudflare", "env": "production", "repo": REPO,
     "repo_path": "environments/production/dns.ts", "account_ref": "prod",
     "depends_on": "DnsRecord", "summary": "Cloudflare DNS for the admin portal. acme-prod-admin-sso redirects here."},
    {"name": "acme-prod-admin-sso", "type": "Okta", "env": "production", "repo": REPO,
     "repo_path": "environments/production/sso.ts", "account_ref": "prod",
     "depends_on": "SsoApplication", "summary": "Okta SSO for admin portal. Redirect URI points at acme-prod-admin-dns."},

    # ── Staging (account_ref = sandbox) - DNS + SSO intentionally missing ──
    {"name": "acme-staging-analytics-db", "type": "RDS", "env": "staging", "repo": REPO,
     "repo_path": "environments/staging/analytics.ts", "account_ref": "sandbox",
     "depends_on": "PostgresDatabase", "summary": "Staging analytics Postgres (single-AZ). Composes PostgresDatabase."},
    {"name": "acme-staging-data-exports", "type": "S3", "env": "staging", "repo": REPO,
     "repo_path": "environments/staging/storage.ts", "account_ref": "sandbox",
     "depends_on": "S3Bucket", "summary": "Staging data exports bucket. Composes S3Bucket."},
]

# Extra composition edges (beyond depends_on) applied after all components exist.
EDGES = [
    ("acme-prod-assets-dns", "acme-prod-static-assets", "fronts",
     "CDN DNS record proxies to the static assets bucket"),
    ("acme-prod-admin-sso", "acme-prod-admin-dns", "redirects_to",
     "Okta redirect URI points at the admin DNS hostname"),
]
