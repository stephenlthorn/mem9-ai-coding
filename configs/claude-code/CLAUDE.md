# Acme Infrastructure Knowledge Base

You are assisting the Acme infrastructure team. This is a Pulumi TypeScript monorepo with reusable component libraries and environment-specific implementations across AWS, Cloudflare, and Okta.

## Your persistent memory (two MCP servers, one TiDB database)

You have two MCP servers, both backed by the same TiDB Cloud Serverless database
that every tool on the team (Codex, Cursor) shares:

- **`tidb`** - PingCAP's official TiDB MCP. Use `db_query` for any read-only SQL
  (including recursive CTEs and `VEC_COSINE_DISTANCE` vector search) and `db_execute`
  for raw writes. This is the full power of TiDB.
- **`tidb-infra-kb`** - our convention layer. `query_knowledge_base` for guided reads
  and `write_component` for atomic, convention-checked writes (component + edge +
  session-log entry in one transaction). Prefer this for creating components.

**Before writing any new infrastructure code, always query the knowledge base first.**

## Key queries

```sql
-- What exists in staging right now?
SELECT name, component_type, summary FROM infra_components WHERE environment = 'staging';

-- What does the production environment look like for reference?
SELECT name, component_type, summary FROM infra_components WHERE environment = 'production' ORDER BY component_type;

-- What are the available library components?
SELECT name, component_type, repo_path, summary FROM infra_components WHERE environment = 'library';

-- What has been created in recent sessions?
SELECT developer, action, detail, created_at FROM session_log ORDER BY created_at DESC LIMIT 10;

-- What does PostgresDatabase depend on?
SELECT c2.name, e.relationship, e.note
FROM component_edges e
JOIN infra_components c1 ON e.from_id = c1.id
JOIN infra_components c2 ON e.to_id = c2.id
WHERE c1.name = 'PostgresDatabase';
```

## Blast radius before refactoring a library (recursive CTE)

Before changing any `libs/` component, compute its full transitive blast radius -
this catches dependents that are two or more hops away (e.g. RDS instances whose
backup buckets compose S3Bucket):

```sql
WITH RECURSIVE blast(from_id, to_id, relationship, depth) AS (
    SELECT e.from_id, e.to_id, e.relationship, 1
    FROM component_edges e JOIN infra_components c ON e.to_id = c.id
    WHERE c.name = 'S3Bucket'
  UNION ALL
    SELECT e.from_id, e.to_id, e.relationship, b.depth + 1
    FROM component_edges e JOIN blast b ON e.to_id = b.from_id
    WHERE b.depth < 10
)
SELECT depth, from_id, relationship, to_id FROM blast ORDER BY depth;
```

## Conventions (non-negotiable)

- **Never use raw provider resources** (`aws.rds.Instance`, `aws.s3.BucketV2`, etc). Always compose through library components in `libs/`.
- `PostgresDatabase` auto-creates a backup S3 bucket. Do NOT create one manually.
- Physical names: `acme-<environment>-<logical-name>`
- All resources need tags: `Environment`, `ManagedBy: pulumi`, `Component`, `Team: infra`
- New public endpoints must use `DnsRecord` (proxied: true always)
- Internal services needing SSO use `SsoApplication`, redirect URI points at the `DnsRecord` hostname

## After creating anything

Always write back to the knowledge base:

```bash
python -m src.writeback \
  --name <resource-name> \
  --type <S3|RDS|Cloudflare|Okta> \
  --env <production|staging> \
  --summary "<what it does and what library it composes>" \
  --depends-on <library-component-name> \
  --developer claude-code
```

Or use the `write_component` MCP tool directly.
