# Acme infrastructure - shared memory (mem9 on TiDB Cloud) - Codex

Your normal coding tool, plus a shared memory in **mem9** (managed TiDB Cloud): components,
dependency edges, and prior sessions are recorded and shared across Claude Code, Codex, and
Cursor. It is the source of truth for what already exists - never start cold, never duplicate.

## Standing instruction - do this automatically, every task

The human just says what they want; you always work this way without being told:

1. **Query first.** Before writing or changing infrastructure, call `query_knowledge_base`
   on the `infra-kb` MCP for the repo you are touching - what exists, how it connects, the
   recent session log.
2. **Compose, never raw.** Build from `libs/` components (`S3Bucket`, `PostgresDatabase`,
   `DnsRecord`, `SsoApplication`, `KmsKey`, `TlsCertificate`, `Service`). Never raw
   `aws.*` / `cloudflare.*` / `okta.*`.
3. **Follow conventions.** `acme-<env>-<logical>` names; tags `Environment`, `ManagedBy`,
   `Component`, `Team`; `DnsRecord` (`proxied: true`) for public endpoints; SSO redirect URI
   points at a `DnsRecord`; set `account_ref` (`prod`/`sandbox`).
4. **Check blast radius.** Before changing a shared/library component, trace what
   transitively depends on it.
5. **Write back.** After creating or changing anything, call `write_component` to record it.
   Instruction-driven - skip it and the next tool starts cold.

## Organization
- **Team = space** (you are on team `acme`; your API key reaches only this team).
- **Repo = namespace**: `acme_pulumi_kb` (Pulumi), `acme_lza_kb` (AWS LZA).
- Cross-repo: `account_ref` links a Pulumi resource to its LZA account.

## MCP servers (explicit routing - you pick the named entry)
- `infra-kb-pulumi` / `infra-kb-lza`: `query_knowledge_base` (hybrid recall: vector +
  full-text) and `write_component` (atomic). Call the one matching the repo you change.

## Rules
- Never raw provider resources - compose `libs/`.
- `KmsKey` is the single encryption root (S3/RDS/TLS reference it).
- `PostgresDatabase` makes its own backup bucket - don't add one.
- Names `acme-<env>-<logical>`; tags Environment/ManagedBy/Component/Team.
- Public endpoints use `DnsRecord` (proxied: true); SSO redirect URI points at a `DnsRecord`.
- Set `account_ref` (prod/sandbox) on new Pulumi resources.

## After creating
```bash
python -m src.writeback --repo pulumi --name <name> --type <type> --env <env> \
  --summary "<summary>" --depends-on <library> --account-ref <prod|sandbox> --developer codex
```
Or call `write_component` on `infra-kb-pulumi` / `infra-kb-lza` directly.
