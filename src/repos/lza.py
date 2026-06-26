"""AWS Landing Zone Accelerator repo manifest (repo = lza -> *_lza_kb).

Models the org/account layer: an OU, AWS accounts (account_ref is the join key
to Pulumi resources), an SCP, and an IAM baseline."""
from __future__ import annotations

REPO = "lza"

COMPONENTS = [
    # ── Libraries ──
    {"name": "AwsAccount", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/aws-account.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable AWS account factory. Creates an account inside an OrganizationalUnit, "
                "applies the IAM baseline and required SCPs. Account alias acme-<account_ref>."},
    {"name": "OrganizationalUnit", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/ou.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable AWS Organizations OU. Groups accounts and is the attach point for SCPs."},
    {"name": "ScpPolicy", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/scp.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable Service Control Policy. Attached to an OU; constrains every account beneath it."},
    {"name": "IamBaseline", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/iam-baseline.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable IAM baseline (roles, password policy, CloudTrail) applied to every new account."},

    # ── Org instances ──
    {"name": "acme-lza-ou-workloads", "type": "OU", "env": "org", "repo": REPO,
     "repo_path": "lza/ous.ts", "account_ref": None, "depends_on": "OrganizationalUnit",
     "summary": "Workloads OU. Parent of the prod and sandbox accounts; SCP deny-root attached."},
    {"name": "acme-lza-scp-deny-root", "type": "SCP", "env": "org", "repo": REPO,
     "repo_path": "lza/ous.ts", "account_ref": None, "depends_on": "ScpPolicy",
     "summary": "SCP denying root-user actions, attached to the workloads OU."},
    {"name": "acme-lza-account-prod", "type": "Account", "env": "org", "repo": REPO,
     "repo_path": "lza/accounts.ts", "account_ref": "prod", "depends_on": "AwsAccount",
     "summary": "Production AWS account (account_ref=prod) in the workloads OU. Hosts acme-prod-* resources."},
    {"name": "acme-lza-account-sandbox", "type": "Account", "env": "org", "repo": REPO,
     "repo_path": "lza/accounts.ts", "account_ref": "sandbox", "depends_on": "AwsAccount",
     "summary": "Sandbox AWS account (account_ref=sandbox) in the workloads OU. Hosts acme-staging-* resources."},
    {"name": "acme-lza-iam-baseline", "type": "IAM", "env": "org", "repo": REPO,
     "repo_path": "lza/accounts.ts", "account_ref": None, "depends_on": "IamBaseline",
     "summary": "Org-wide IAM baseline applied to every account by the AwsAccount factory."},

    # ── Nested-OU chain: a 3-hop org path (account -> workloads OU -> core OU) ──
    {"name": "acme-lza-ou-core", "type": "OU", "env": "org", "repo": REPO,
     "repo_path": "lza/ous.ts", "account_ref": None, "depends_on": "OrganizationalUnit",
     "relationship": "instantiates",
     "summary": "Core (parent) OU. acme-lza-ou-workloads is nested beneath it; org-wide guardrails SCP "
                "attached here. Deepens the org chain so account -> workloads OU -> core OU -> library "
                "is a 3-hop transitive path."},
    {"name": "acme-lza-scp-guardrails", "type": "SCP", "env": "org", "repo": REPO,
     "repo_path": "lza/ous.ts", "account_ref": None, "depends_on": "ScpPolicy",
     "relationship": "instantiates",
     "summary": "Org-wide guardrails SCP (region lock, deny-leave-org) attached to the core OU. "
                "Constrains every account beneath core, including everything in the workloads OU."},
]

EDGES = [
    ("acme-lza-account-prod", "acme-lza-ou-workloads", "belongs_to", "prod account lives in the workloads OU"),
    ("acme-lza-account-sandbox", "acme-lza-ou-workloads", "belongs_to", "sandbox account lives in the workloads OU"),
    ("acme-lza-scp-deny-root", "acme-lza-ou-workloads", "attached_to", "deny-root SCP is attached to the workloads OU"),

    # ── Nested-OU + guardrails ──
    ("acme-lza-ou-workloads", "acme-lza-ou-core", "belongs_to", "workloads OU is nested beneath the core OU"),
    ("acme-lza-scp-guardrails", "acme-lza-ou-core", "attached_to", "guardrails SCP is attached to the core OU"),
    ("acme-lza-account-prod", "acme-lza-iam-baseline", "applies", "prod account applies the org IAM baseline"),
]
