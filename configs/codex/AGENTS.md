# Acme Infrastructure Knowledge Base

You are assisting the Acme infrastructure team on a Pulumi TypeScript monorepo.

## Shared memory (two MCP servers, one TiDB database)

Both MCP servers hit the same TiDB Cloud Serverless DB that Claude Code and Cursor also use:
- **`tidb`** - official TiDB MCP: `db_query` (raw SQL, recursive CTEs, vector search), `db_execute`.
- **`tidb-infra-kb`** - convention layer: `query_knowledge_base`, `write_component` (atomic, checked).

Query before doing anything.

## Before creating any resource

```sql
SELECT name, component_type, summary FROM infra_components WHERE environment = 'staging';
SELECT name, component_type, summary FROM infra_components WHERE environment = 'library';
SELECT developer, action, detail FROM session_log ORDER BY created_at DESC LIMIT 5;
```

## Rules

- Never raw provider resources - always use library components in `libs/`
- Names: `acme-<env>-<logical-name>`
- Tags required: `Environment`, `ManagedBy: pulumi`, `Component`, `Team: infra`
- Public endpoints: must use `DnsRecord` (proxied: true)
- SSO: use `SsoApplication`, redirect URI points at `DnsRecord` hostname
- `PostgresDatabase` creates its own backup bucket - do not add one

## After creating anything

```bash
python -m src.writeback --name <name> --type <type> --env <env> \
  --summary "<summary>" --depends-on <library> --developer codex
```
