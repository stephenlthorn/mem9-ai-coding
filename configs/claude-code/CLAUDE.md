# Acme infrastructure - mem9 memory

You are working in your normal coding tool. The only thing different here is that
this team has a **memory the database holds (mem9)**: every infrastructure component,
dependency edge, and prior session is recorded in TiDB and shared across Claude Code,
Codex, and Cursor. Use it so you never start cold or duplicate work.

## How the memory is organized

- **Team = cluster.** You are connected to one team's TiDB cluster (this team: `acme`).
  Your credentials unlock only this team's databases. You have no path to another team's KB.
- **Repo = database.** Each repo is its own database in this cluster:
  - `acme_pulumi_kb` - the Pulumi infra-as-code repo
  - `acme_lza_kb` - the AWS Landing Zone Accelerator repo
- Work in one repo, or across both with a cross-database JOIN over the same connection.

## Your MCP servers (routing is explicit - you choose)

Named entries, one per repo database. The server does NOT guess where to write:

- `infra-kb-pulumi` / `infra-kb-lza` - mem9 convention layer: `query_knowledge_base`,
  `write_component`. Call the one matching the repo you are changing.
- `tidb-pulumi` / `tidb-lza` - the official TiDB MCP for raw SQL (`db_query`, recursive
  CTEs, vector search). Same team creds, so you can cross-database JOIN, e.g.
  `acme_lza_kb.infra_components` from the `tidb-pulumi` connection.

## Lifecycle: query before acting; persist after acting

1. **Bootstrap (done before your session).** The team runs `python -m src.ingest --reset`
   to populate each repo's KB from source. You start warm.
2. **Query first.** Before writing any code, query the KB for what exists, the conventions,
   and the recent session log.
3. **Persist after.** After you scaffold a resource, **call `write_component` to record it.**
   This is instruction-driven, NOT automatic - if you skip it, the next tool starts cold.

> Eventual consistency: full-text/columnar indexes lag writes by a second or two. For a
> read-your-write check, use a point lookup by `name` (primary/unique key), not full-text.

## Key queries

```sql
-- What exists in staging vs production? (Pulumi repo)
SELECT name, component_type, environment FROM acme_pulumi_kb.infra_components
WHERE environment IN ('staging','production') ORDER BY environment;

-- Recent shared sessions (who did what)
SELECT developer, action, detail, created_at FROM acme_pulumi_kb.session_log
ORDER BY created_at DESC LIMIT 10;

-- Cross-repo: which Pulumi resources live in which LZA account?
SELECT p.name, p.account_ref, a.name AS lza_account
FROM acme_pulumi_kb.infra_components p
JOIN acme_lza_kb.infra_components a ON a.account_ref = p.account_ref AND a.component_type='Account';
```

## Blast radius before changing a library (recursive CTE, single repo)

```sql
WITH RECURSIVE blast(from_id, to_id, relationship, depth) AS (
    SELECT e.from_id, e.to_id, e.relationship, 1
    FROM acme_pulumi_kb.component_edges e
    JOIN acme_pulumi_kb.infra_components c ON e.to_id = c.id WHERE c.name = 'S3Bucket'
  UNION ALL
    SELECT e.from_id, e.to_id, e.relationship, b.depth + 1
    FROM acme_pulumi_kb.component_edges e
    JOIN blast b ON e.to_id = b.from_id WHERE b.depth < 10
)
SELECT depth, from_id, relationship, to_id FROM blast ORDER BY depth;
```

## Conventions (non-negotiable)

- Never use raw provider resources (`aws.s3.BucketV2`, etc). Compose library components.
- `PostgresDatabase` auto-creates its backup S3 bucket. Do NOT add one.
- Physical names: `acme-<environment>-<logical-name>`.
- Tags: `Environment`, `ManagedBy: pulumi`, `Component`, `Team`.
- Public endpoints use `DnsRecord` (proxied: true). SSO uses `SsoApplication`, redirect URI
  points at the `DnsRecord` hostname.
- New Pulumi resources set `account_ref` to the LZA account they deploy into (`prod`/`sandbox`).

## After creating anything

```bash
python -m src.writeback --repo pulumi \
  --name <resource-name> --type <S3|RDS|Cloudflare|Okta> --env <production|staging> \
  --summary "<what it does and what library it composes>" \
  --depends-on <library-component-name> --account-ref <prod|sandbox> --developer claude-code
```

Or call the `write_component` tool on `infra-kb-pulumi` (or `infra-kb-lza`) directly.
