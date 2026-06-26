"""Dashboard API: exposes the shared knowledge base for the browser UI.

Endpoints power five views:
  - Overview        : full component graph + table + session log
  - Terminals       : 3-CLI triptych, live session log or scripted replay
  - Memory          : before (seed) / after (current) memory comparison
  - Dependency      : transitive dependency traversal visualised as a subgraph
  - Scenarios       : narrated Pulumi pain points mem9's hybrid recall solves
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src import db
from src import seed as seeder

STATIC_DIR = Path(__file__).parent / "static"

REPO = "pulumi"

db.init_db(repos=[REPO])

app = FastAPI(title="mem9-infra-kb dashboard", docs_url=None, redoc_url=None)


# ── Memory helpers ────────────────────────────────────────────────────────────

def _all_memories(repo: str = REPO) -> list[dict]:
    return db.recall(db.database_for(repo), limit=200)


def _all_components(repo: str = REPO) -> list[dict]:
    rows = []
    seen: set[str] = set()
    for m in _all_memories(repo):
        meta = m.get("metadata", {})
        if meta.get("edge") or meta.get("action") or not meta.get("name"):
            continue
        name = meta["name"]
        if name in seen:
            continue
        seen.add(name)
        rows.append({
            "id": m.get("id", ""),
            "name": name,
            "component_type": meta.get("type", ""),
            "environment": meta.get("env", ""),
            "repo": meta.get("repo", repo),
            "account_ref": meta.get("account_ref", ""),
            "repo_path": meta.get("repo_path", ""),
            "summary": m.get("content", ""),
            "code_excerpt": "",
            "created_by": meta.get("developer", ""),
            "created_at": m.get("createdAt", ""),
        })
    return rows


def _all_edges(repo: str = REPO) -> list[dict]:
    rows = []
    for m in _all_memories(repo):
        meta = m.get("metadata", {})
        if not meta.get("edge"):
            continue
        rows.append({
            "id": m.get("id", ""),
            "relationship": meta.get("relationship", ""),
            "note": m.get("content", ""),
            "from_name": meta.get("from", ""),
            "to_name": meta.get("to", ""),
            "from_type": "",
            "from_env": "",
            "to_type": "",
            "to_env": "",
        })
    return rows


def _session_log_entries(repo: str = REPO) -> list[dict]:
    rows = []
    for m in _all_memories(repo):
        meta = m.get("metadata", {})
        if not meta.get("action"):
            continue
        rows.append({
            "id": m.get("id", ""),
            "developer": meta.get("developer", ""),
            "action": meta.get("action", ""),
            "detail": m.get("content", ""),
            "created_at": m.get("createdAt", ""),
        })
    return rows[-60:]


# ── Core reads ────────────────────────────────────────────────────────────────

@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/api/backend")
def backend():
    return {"backend": db.backend_name()}


@app.get("/api/components")
def components():
    return JSONResponse(_all_components())


@app.get("/api/edges")
def edges():
    return JSONResponse(_all_edges())


@app.get("/api/session-log")
def session_log():
    return JSONResponse(_session_log_entries())


@app.get("/api/missing")
def missing():
    comps = _all_components()
    prod = {c["name"].replace("acme-prod-", ""): c
            for c in comps if c["environment"] == "production"}
    staging = {c["name"].replace("acme-staging-", "")
               for c in comps if c["environment"] == "staging"}
    out = [
        {"production_name": comp["name"],
         "expected_staging_name": f"acme-staging-{key}",
         "component_type": comp["component_type"]}
        for key, comp in prod.items() if key not in staging
    ]
    return JSONResponse(out)


# ── Before / after memory ─────────────────────────────────────────────────────

@app.get("/api/memory")
def memory():
    rows = _all_components()
    before = [r for r in rows if r["created_by"] == "seed"]
    after = rows
    new = [r for r in rows if r["created_by"] != "seed"]
    return JSONResponse({"before": before, "after": after, "new": new})


# ── Dependency traversals ─────────────────────────────────────────────────────

@app.get("/api/cte/dependencies")
def cte_dependencies(name: str):
    return JSONResponse(db.cte_dependencies(REPO, name))


@app.get("/api/cte/blast-radius")
def cte_blast_radius(name: str):
    return JSONResponse(db.cte_blast_radius(REPO, name))


# ── Vector / full-text / hybrid search ───────────────────────────────────────

@app.get("/api/search")
def search(q: str, mode: str = "hybrid"):
    if mode not in ("hybrid", "vector", "fts"):
        mode = "hybrid"
    return JSONResponse(db.search(REPO, q, mode=mode, k=6))


# ── Scenarios ────────────────────────────────────────────────────────────────

SCENARIOS = [
    {
        "id": "duplicate-backup",
        "headline": True,
        "title": "The duplicate backup bucket",
        "tool": "cursor",
        "task": "Add backups for the staging analytics database.",
        "without": [
            "Dev greps the repo, finds no backup bucket for analytics.",
            "Writes a raw `new aws.s3.BucketV2('analytics-backup')`.",
            "Two bugs ship: (1) a DUPLICATE bucket - PostgresDatabase already makes one;",
            "(2) a raw provider resource, violating the no-raw-resources rule.",
            "Drift, double storage cost, and an untagged bucket nobody owns.",
        ],
        "query": (
            "mem9 hybrid search: 'PostgresDatabase instantiates'\n"
            "-> returns edge memories with from_name=PostgresDatabase"
        ),
        "result": "PostgresDatabase --instantiates--> S3Bucket  (backup bucket, automatic)",
        "with": [
            "The KB shows PostgresDatabase already instantiates an S3Bucket for backups.",
            "Dev does nothing - the backup already exists, correctly tagged and composed.",
            "No duplicate, no raw resource, no drift.",
        ],
        "why_tidb": (
            "The composition relationship lives in the graph, not buried in TypeScript. "
            "A flat repo search or a vector store of code snippets can't tell you "
            "'this library already creates that resource for you.'"
        ),
    },
    {
        "id": "blast-radius",
        "headline": True,
        "title": "Blast radius before a refactor",
        "tool": "claude-code",
        "task": "Change the naming scheme inside the S3Bucket library.",
        "without": [
            "Dev can't see everything that composes S3Bucket across environments.",
            "Ships the change, CI is green, prod static-assets + both analytics DBs break.",
            "The RDS breakage is the surprise - backups compose S3Bucket two hops away.",
        ],
        "query": (
            "mem9 hybrid search: 'depends_on S3Bucket'\n"
            "-> all components with metadata.depends_on == 'S3Bucket'\n"
            "-> client-side transitive closure over depends_on chains"
        ),
        "result": (
            "depth 1: PostgresDatabase, acme-prod-data-exports, acme-prod-static-assets, "
            "acme-staging-data-exports\n"
            "depth 2: acme-prod-analytics-db, acme-staging-analytics-db (via PostgresDatabase), "
            "acme-prod-assets-dns (fronts static-assets)"
        ),
        "with": [
            "Blast-radius search returns the full transitive closure: 7 dependents across prod + staging.",
            "Dev sees the RDS instances are in the blast radius before touching anything.",
            "Stages the change behind a flag, migrates per-environment, zero surprises.",
        ],
        "why_tidb": (
            "mem9 hybrid recall surfaces all components whose dependency chain includes S3Bucket. "
            "Vector similarity finds 'related-looking' code; metadata search + graph traversal "
            "computes the transitive closure that pure similarity can't."
        ),
    },
    {
        "id": "staging-parity",
        "headline": False,
        "title": "Staging parity, picked up warm across tools",
        "tool": "claude-code",
        "task": "Bring staging to parity with production (DNS + SSO).",
        "without": [
            "Each tool/dev re-discovers the prod pattern from scratch.",
            "Conventions drift: someone forgets proxied:true, someone hand-rolls the SSO redirect.",
        ],
        "query": (
            "mem9 recall: acme_pulumi_kb\n"
            "-> filter metadata.action present (session-log entries)\n"
            "-> reverse-chronological, limit 5"
        ),
        "result": "claude-code created acme-staging-static-assets, acme-staging-assets-dns ...",
        "with": [
            "Claude Code scaffolds static-assets + assets-dns, writes back to the KB.",
            "Codex opens cold, reads the session log, continues with admin-dns - no re-briefing.",
            "Cursor runs the dependency search, sees SSO must redirect to a DnsRecord, finishes it.",
            "Three tools, one shared memory, conventions preserved end to end.",
        ],
        "why_tidb": (
            "The session log + component graph are shared state every tool reads and writes. "
            "The next session starts warm instead of re-deriving context from the filesystem."
        ),
    },
]


@app.get("/api/scenarios")
def scenarios():
    return JSONResponse(SCENARIOS)


# ── Scripted 3-CLI replay ─────────────────────────────────────────────────────

def _m_static_assets():
    db.write_component(
        repo="pulumi", name="acme-staging-static-assets", type="S3", env="staging",
        repo_path="environments/staging/storage.ts",
        summary="Staging static assets bucket. Composes S3Bucket; fronted by acme-staging-assets-dns.",
        developer="claude-code", depends_on="S3Bucket",
    )


def _m_assets_dns():
    db.write_component(
        repo="pulumi", name="acme-staging-assets-dns", type="Cloudflare", env="staging",
        repo_path="environments/staging/dns.ts",
        summary="Cloudflare DNS fronting acme-staging-static-assets. Proxied: true.",
        developer="claude-code", depends_on="DnsRecord",
    )
    db.write_edge("pulumi", "acme-staging-assets-dns", "acme-staging-static-assets", "fronts",
                  "CDN DNS record proxies to the staging static assets bucket")


def _m_admin_dns():
    db.write_component(
        repo="pulumi", name="acme-staging-admin-dns", type="Cloudflare", env="staging",
        repo_path="environments/staging/dns.ts",
        summary="Cloudflare DNS for the staging admin portal. acme-staging-admin-sso redirects here.",
        developer="codex", depends_on="DnsRecord",
    )


def _m_admin_sso():
    db.write_component(
        repo="pulumi", name="acme-staging-admin-sso", type="Okta", env="staging",
        repo_path="environments/staging/sso.ts",
        summary="Okta SSO for staging admin portal. Redirect URI points at acme-staging-admin-dns.",
        developer="cursor", depends_on="SsoApplication",
    )
    db.write_edge("pulumi", "acme-staging-admin-sso", "acme-staging-admin-dns", "redirects_to",
                  "Okta redirect URI points at the staging admin DNS hostname")


DEMO_STEPS = [
    {
        "tool": "claude-code", "title": "Inspect the gap",
        "prompt": "What infra exists in staging vs production?",
        "sql": (
            "mem9 recall: acme_pulumi_kb (all components)\n"
            "-> filter metadata.env IN ('staging', 'production')\n"
            "-> group by environment, sort by type + name"
        ),
        "output": [
            "production: 6 components (RDS, S3 x2, Cloudflare x2, Okta)",
            "staging:    2 components (RDS, S3)",
            "-> staging is missing the DNS + SSO layer.",
        ],
        "mutate": None,
    },
    {
        "tool": "claude-code", "title": "Scaffold static-assets bucket",
        "prompt": "Create the staging static-assets bucket. Use the S3Bucket lib, never raw aws.s3.",
        "sql": None,
        "output": [
            "edit environments/staging/storage.ts",
            "  + new S3Bucket('acme-staging-static-assets', { env: 'staging' })",
            "write_component -> acme-staging-static-assets (S3, composes S3Bucket)",
        ],
        "mutate": _m_static_assets,
    },
    {
        "tool": "claude-code", "title": "Front it with Cloudflare DNS",
        "prompt": "Front the bucket with a DnsRecord (proxied), matching prod.",
        "sql": None,
        "output": [
            "edit environments/staging/dns.ts",
            "  + new DnsRecord('acme-staging-assets-dns', { proxied: true })",
            "write_component -> acme-staging-assets-dns  (fronts acme-staging-static-assets)",
        ],
        "mutate": _m_assets_dns,
    },
    {
        "tool": "codex", "title": "Pick up warm context",
        "prompt": "I'm continuing the staging work. What did the last session create?",
        "sql": (
            "mem9 recall: acme_pulumi_kb\n"
            "-> filter metadata.action present (session-log entries)\n"
            "-> reverse-chronological, limit 4"
        ),
        "output": [
            "claude-code - created - acme-staging-assets-dns",
            "claude-code - created - acme-staging-static-assets",
            "-> continuing from where Claude Code left off. No re-briefing needed.",
        ],
        "mutate": None,
    },
    {
        "tool": "codex", "title": "Scaffold admin DNS",
        "prompt": "Add the staging admin-portal DNS record, matching the prod pattern.",
        "sql": None,
        "output": [
            "edit environments/staging/dns.ts",
            "  + new DnsRecord('acme-staging-admin-dns', { proxied: true })",
            "write_component -> acme-staging-admin-dns",
        ],
        "mutate": _m_admin_dns,
    },
    {
        "tool": "cursor", "title": "Trace dependencies",
        "prompt": "Before I add the SSO app: what does prod's admin-sso depend on? Trace it.",
        "sql": (
            "mem9 hybrid search: 'acme-prod-admin-sso'\n"
            "-> metadata.depends_on chain + edge memories\n"
            "-> depth-1: SsoApplication, redirects_to acme-prod-admin-dns"
        ),
        "output": [
            "depth 1: acme-prod-admin-sso --uses--> SsoApplication",
            "depth 1: acme-prod-admin-sso --redirects_to--> acme-prod-admin-dns",
            "depth 2: acme-prod-admin-dns --uses--> DnsRecord",
            "-> the SSO redirect URI must point at the admin DnsRecord.",
        ],
        "mutate": None,
    },
    {
        "tool": "cursor", "title": "Scaffold admin SSO",
        "prompt": "Create the staging Okta SSO app, redirect URI -> acme-staging-admin-dns.",
        "sql": None,
        "output": [
            "edit environments/staging/sso.ts",
            "  + new SsoApplication('acme-staging-admin-sso', {",
            "      redirectUris: [pmStagingAdminDns.hostname] })",
            "write_component -> acme-staging-admin-sso  (redirects_to acme-staging-admin-dns)",
            "staging is now at parity with production.",
        ],
        "mutate": _m_admin_sso,
    },
]


@app.get("/api/demo/script")
def demo_script():
    return JSONResponse([
        {k: v for k, v in step.items() if k != "mutate"} | {"mutates": step["mutate"] is not None}
        for step in DEMO_STEPS
    ])


class ApplyBody(BaseModel):
    index: int


@app.post("/api/demo/apply")
def demo_apply(body: ApplyBody):
    if body.index < 0 or body.index >= len(DEMO_STEPS):
        return JSONResponse({"error": "index out of range"}, status_code=400)
    step = DEMO_STEPS[body.index]
    if step["mutate"]:
        step["mutate"]()
    elif step.get("sql"):
        db.log_query(REPO, step["tool"], step["sql"].replace("\n", " ")[:120])
    return JSONResponse({"ok": True, "applied": body.index, "mutated": step["mutate"] is not None})


@app.post("/api/reset")
def reset():
    seeder.seed(reset=True)
    return JSONResponse({"ok": True})


# ── Static ────────────────────────────────────────────────────────────────────

if STATIC_DIR.exists():
    @app.get("/")
    def root():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
