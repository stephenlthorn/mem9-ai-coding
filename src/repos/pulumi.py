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

    # ── Deep chain: KMS foundation + TLS + customer-portal service stack ──
    # Gives the recursive-traversal demo real 4-5 hop transitive chains and a
    # foundation node (acme-prod-data-kms / KmsKey) whose blast radius spans the
    # entire prod estate.
    {"name": "KmsKey", "type": "KMS", "env": "library", "repo": REPO,
     "repo_path": "libs/kms-key/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable AWS KMS customer-managed key. Single source of encryption for S3 buckets, "
                "RDS instances, and TLS private key material. Rotation enabled; key policy grants only "
                "the owning account. Every encrypted resource references one KmsKey - rotating or "
                "deleting it has org-wide blast radius.",
     "code_excerpt": "export class KmsKey extends pulumi.ComponentResource { /* rotation, key policy */ }"},
    {"name": "TlsCertificate", "type": "Certificate", "env": "library", "repo": REPO,
     "repo_path": "libs/tls-cert/index.ts", "account_ref": None,
     "depends_on": "KmsKey", "relationship": "encrypted_by",
     "summary": "Reusable ACM/Cloudflare TLS certificate. Private key material is encrypted_by a KmsKey. "
                "Used to secure public DnsRecord hostnames (HTTPS). All proxied DNS endpoints "
                "terminating TLS must reference a TlsCertificate."},
    {"name": "Service", "type": "Service", "env": "library", "repo": REPO,
     "repo_path": "libs/service/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable application service (ECS/Fargate task + ALB). Authenticates end users via an "
                "SsoApplication and is fronted by a DnsRecord hostname. Internal services must wire "
                "authenticates_via -> SSO and fronted_by -> DNS."},

    {"name": "acme-prod-data-kms", "type": "KMS", "env": "production", "repo": REPO, "prod_only": True,
     "repo_path": "environments/production/security.ts", "account_ref": "prod",
     "depends_on": "KmsKey", "relationship": "instantiates",
     "summary": "FOUNDATION NODE. Production data-encryption KMS key. Composes KmsKey. Encrypts "
                "acme-prod-analytics-db, acme-prod-data-exports, acme-prod-static-assets and the TLS "
                "cert key material. Rotating/deleting it transitively impacts every prod data + portal resource."},
    {"name": "acme-prod-portal-cert", "type": "Certificate", "env": "production", "repo": REPO, "prod_only": True,
     "repo_path": "environments/production/security.ts", "account_ref": "prod",
     "depends_on": "TlsCertificate", "relationship": "instantiates",
     "summary": "Production TLS certificate for the customer portal + admin domains. Composes "
                "TlsCertificate; private key encrypted_by acme-prod-data-kms. Secures acme-prod-portal-dns "
                "and acme-prod-admin-dns."},
    {"name": "acme-prod-portal-dns", "type": "Cloudflare", "env": "production", "repo": REPO, "prod_only": True,
     "repo_path": "environments/production/dns.ts", "account_ref": "prod",
     "depends_on": "DnsRecord", "relationship": "instantiates",
     "summary": "Cloudflare DNS for the customer portal (portal.acme.com). Composes DnsRecord "
                "(proxied: true); secured_by acme-prod-portal-cert. SSO redirect target and the front "
                "door for acme-prod-portal-svc."},
    {"name": "acme-prod-portal-sso", "type": "Okta", "env": "production", "repo": REPO, "prod_only": True,
     "repo_path": "environments/production/sso.ts", "account_ref": "prod",
     "depends_on": "SsoApplication", "relationship": "instantiates",
     "summary": "Okta SSO application for the customer portal. Composes SsoApplication; redirect URI "
                "points at acme-prod-portal-dns. acme-prod-portal-svc and acme-prod-reporting-svc "
                "authenticate through it."},
    {"name": "acme-prod-portal-svc", "type": "Service", "env": "production", "repo": REPO, "prod_only": True,
     "repo_path": "environments/production/portal.ts", "account_ref": "prod",
     "depends_on": "Service", "relationship": "instantiates",
     "summary": "Production customer portal service. Composes Service; authenticates_via "
                "acme-prod-portal-sso and fronted_by acme-prod-portal-dns. Top of the deepest prod "
                "dependency chain (5 hops down to KmsKey)."},
    {"name": "acme-prod-reporting-svc", "type": "Service", "env": "production", "repo": REPO, "prod_only": True,
     "repo_path": "environments/production/reporting.ts", "account_ref": "prod",
     "depends_on": "Service", "relationship": "instantiates",
     "summary": "Production reporting service. Composes Service; reads_from acme-prod-analytics-db and "
                "authenticates_via acme-prod-portal-sso. Transitively depends on acme-prod-data-kms via "
                "two distinct paths (DB encryption + SSO/DNS/TLS)."},
]

# Extra composition edges (beyond depends_on) applied after all components exist.
EDGES = [
    ("acme-prod-assets-dns", "acme-prod-static-assets", "fronts",
     "CDN DNS record proxies to the static assets bucket"),
    ("acme-prod-admin-sso", "acme-prod-admin-dns", "redirects_to",
     "Okta redirect URI points at the admin DNS hostname"),

    # ── Deep-chain edges (KMS foundation + portal stack) ──
    ("acme-prod-analytics-db", "acme-prod-data-kms", "encrypted_by",
     "RDS storage + automated backups encrypted with the prod data KMS key"),
    ("acme-prod-data-exports", "acme-prod-data-kms", "encrypted_by",
     "data-exports bucket encrypted with the prod data KMS key"),
    ("acme-prod-static-assets", "acme-prod-data-kms", "encrypted_by",
     "static-assets bucket encrypted with the prod data KMS key"),
    ("acme-prod-portal-cert", "acme-prod-data-kms", "encrypted_by",
     "TLS private key material wrapped by the prod data KMS key"),
    ("acme-prod-portal-dns", "acme-prod-portal-cert", "secured_by",
     "portal DNS terminates HTTPS with the portal TLS certificate"),
    ("acme-prod-admin-dns", "acme-prod-portal-cert", "secured_by",
     "admin DNS shares the portal/admin TLS certificate"),
    ("acme-prod-portal-sso", "acme-prod-portal-dns", "redirects_to",
     "Okta redirect URI points at the portal DNS hostname"),
    ("acme-prod-portal-svc", "acme-prod-portal-sso", "authenticates_via",
     "portal service authenticates end users through the portal SSO app"),
    ("acme-prod-portal-svc", "acme-prod-portal-dns", "fronted_by",
     "portal service is served behind the portal DNS hostname"),
    ("acme-prod-reporting-svc", "acme-prod-analytics-db", "reads_from",
     "reporting service reads from the production analytics database"),
    ("acme-prod-reporting-svc", "acme-prod-portal-sso", "authenticates_via",
     "reporting service authenticates end users through the portal SSO app"),
]
