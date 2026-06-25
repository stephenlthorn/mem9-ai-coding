# Acme infrastructure - mem9 memory (Codex)

Your coding tool, plus a memory the database holds (mem9): components, edges, and prior
sessions live in TiDB and are shared across Claude Code, Codex, and Cursor.

## Organization
- **Team = cluster** (you are on team `acme`; creds unlock only this team).
- **Repo = database**: `acme_pulumi_kb` (Pulumi), `acme_lza_kb` (AWS LZA).

## MCP servers (explicit routing - you pick the named entry)
- `infra-kb-pulumi` / `infra-kb-lza`: `query_knowledge_base`, `write_component`.
- `tidb-pulumi` / `tidb-lza`: official TiDB MCP `db_query` (raw SQL, recursive CTEs,
  vector search). Cross-database JOINs work because both DBs share the team creds.

## Lifecycle: query before acting; persist after acting
- Query the KB before writing code (what exists, conventions, recent session_log).
- After scaffolding, **call `write_component`** - persist is instruction-driven, not automatic.
- Eventual consistency: full-text/columnar indexes lag writes by ~seconds; use a point
  lookup by `name` for read-your-write checks.

## Query first
```sql
SELECT name, component_type, environment FROM acme_pulumi_kb.infra_components WHERE environment='staging';
SELECT developer, action, detail FROM acme_pulumi_kb.session_log ORDER BY created_at DESC LIMIT 5;
```

## Rules
- Never raw provider resources - compose libraries in `libs/`.
- Names `acme-<env>-<logical>`; tags Environment/ManagedBy/Component/Team.
- Public endpoints use `DnsRecord` (proxied: true); SSO redirect URI points at a `DnsRecord`.
- `PostgresDatabase` makes its own backup bucket - don't add one.
- Set `account_ref` (prod/sandbox) on new Pulumi resources.

## After creating
```bash
python -m src.writeback --repo pulumi --name <name> --type <type> --env <env> \
  --summary "<summary>" --depends-on <library> --account-ref <prod|sandbox> --developer codex
```
