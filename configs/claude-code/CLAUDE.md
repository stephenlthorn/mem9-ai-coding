# Acme infrastructure - shared memory (mem9 on TiDB Cloud)

You are in your normal coding tool. This team keeps a shared memory in **mem9** (managed
TiDB Cloud): every infrastructure component, dependency edge, and prior session is recorded
and shared across Claude Code, Codex, and Cursor. Treat it as the source of truth for what
already exists. You never start cold and you never duplicate work.

## Standing instruction - do this automatically, every task

The human will just tell you what they want ("bring staging to parity with production").
You do NOT need to be told the steps below each time - they are how you always work here:

1. **Query first.** Before writing or changing any infrastructure, call
   `query_knowledge_base` on the `infra-kb` MCP for the repo you are touching. Check what
   already exists, how things connect, and the recent session log. Never assume.
2. **Compose, never raw.** Build only from the library components in `libs/` (`S3Bucket`,
   `PostgresDatabase`, `DnsRecord`, `SsoApplication`, `KmsKey`, `TlsCertificate`, `Service`).
   Never write raw `aws.*` / `cloudflare.*` / `okta.*` resources.
3. **Follow conventions.** Name resources `acme-<env>-<logical>`; apply the required tags
   (`Environment`, `ManagedBy`, `Component`, `Team`); public endpoints use `DnsRecord`
   (`proxied: true`); SSO redirect URIs point at a `DnsRecord` hostname; set `account_ref`
   (`prod`/`sandbox`) on new resources.
4. **Check blast radius.** Before changing a shared or library component, trace what
   transitively depends on it so you do not break dependents you cannot see.
5. **Write back.** After you create or change anything, call `write_component` to record it
   (name, type, env, what it composes, `account_ref`). This is instruction-driven - if you
   skip it, the next tool and the next session start cold.

## How the memory is organized

- **Team = space.** You are on team `acme`; your API key reaches only this team's memory.
  There is no path to another team's knowledge base.
- **Repo = namespace** inside that space:
  - `acme_pulumi_kb` - the Pulumi infra-as-code repo
  - `acme_lza_kb` - the AWS Landing Zone Accelerator repo
- **Cross-repo:** `account_ref` links a Pulumi resource to the LZA account it deploys into.

## Your MCP servers (routing is explicit - you choose)

One named entry per repo namespace; the server never guesses where to write:

- `infra-kb-pulumi` / `infra-kb-lza` - the mem9 convention layer:
  - `query_knowledge_base(query)` - hybrid recall (vector + full-text) over the repo's memory.
  - `write_component(...)` - record a component you created or changed (atomic, convention-checked).
  Call the one matching the repo you are changing.

## Conventions (non-negotiable)

- Never raw provider resources - compose the `libs/` wrappers.
- `PostgresDatabase` auto-creates its backup S3 bucket. Do NOT add one.
- `KmsKey` is the single encryption root; S3 buckets, RDS, and TLS certs all reference it.
- Physical names: `acme-<environment>-<logical-name>`.
- Tags: `Environment`, `ManagedBy: pulumi`, `Component`, `Team`.
- Public endpoints use `DnsRecord` (`proxied: true`). SSO uses `SsoApplication`; its redirect
  URI points at the corresponding `DnsRecord` hostname.
- New Pulumi resources set `account_ref` to the LZA account they deploy into (`prod`/`sandbox`).

## After creating anything

Call the `write_component` tool on `infra-kb-pulumi` (or `infra-kb-lza`) with the name, type,
env, a one-line summary of what it composes, `depends_on`, and `account_ref`. Or from a shell:

```bash
python -m src.writeback --repo pulumi \
  --name <resource-name> --type <S3|RDS|Cloudflare|Okta|KMS|Certificate|Service> \
  --env <production|staging> --summary "<what it does and what library it composes>" \
  --depends-on <library-component-name> --account-ref <prod|sandbox> --developer claude-code
```
