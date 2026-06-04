# Live demo runbook - 3 real CLIs, one TiDB brain

Three coding tools (Claude Code, Codex, Cursor) connect to the **same TiDB Cloud
TiDB Cloud** database through MCP and collaborate on the Acme Pulumi monorepo.
Each starts cold; each reads the shared memory and continues where the last left off.

## One-time setup

```bash
cd mem9-ai-coding
cp .env.example .env          # paste your TiDB Cloud creds (Connect → General)
./setup.sh                    # installs deps, creates schema + seeds on TiDB, generates MCP configs
```

`setup.sh` runs `python -m src.gen_configs`, which writes (with your creds, gitignored):
- `.mcp.json` - auto-loaded by **Claude Code**
- `.cursor/mcp.json` - auto-loaded by **Cursor**
- `configs/generated/codex-config.toml` - paste the blocks into `~/.codex/config.toml`

Each wires **two** MCP servers:
- `tidb` - PingCAP's official TiDB MCP (`db_query`, `db_execute`, vector search)
- `tidb-infra-kb` - our convention layer (`query_knowledge_base`, `write_component`)

Open the dashboard (live mission control) in a browser:
```bash
./demo.sh                     # http://localhost:7001
```

## iTerm: open 3 panes (Cmd+D to split)

In **every** pane: `cd /path/to/mem9-ai-coding`

| Pane | Launch | Tool |
|---|---|---|
| 1 | `claude` | Claude Code |
| 2 | `codex` | Codex |
| 3 | `cursor-agent` | Cursor |

---

## The script (copy-paste prompts)

### Pane 1 - Claude Code: inspect + scaffold the asset layer

> Use the tidb-infra-kb MCP. Query the knowledge base: what components exist in
> `staging` vs `production`, and what is staging missing? Then scaffold the missing
> staging **static-assets bucket** and its **Cloudflare DNS record**, composing the
> `S3Bucket` and `DnsRecord` libraries - never raw `aws.*` resources. Follow the
> `acme-<env>-<name>` naming and required tags. Record each new component with
> `write_component`.

*Talking point:* it queries first (no duplication), composes the libs (conventions),
writes back (the next tool will see it). Watch the dashboard session log light up.

### Pane 2 - Codex: pick up warm, continue

> Use the tidb-infra-kb MCP. Read the recent `session_log` - what did the previous
> session just create? Continue the staging build: add the **admin-portal DNS record**
> (`acme-staging-admin-dns`) matching the production pattern, composing `DnsRecord`.
> Record it with `write_component`.

*Talking point:* Codex opened cold. It has zero local memory of Claude Code's work -
but the shared TiDB session log briefs it instantly. No re-explaining.

### Pane 3 - Cursor: verify dependencies with a recursive CTE, then finish

> Use the **tidb** MCP (`db_query`) to run a recursive CTE: what does the production
> `acme-prod-admin-sso` transitively depend on? Confirm an SSO app must redirect to a
> `DnsRecord`. Then scaffold `acme-staging-admin-sso` composing `SsoApplication`, with
> the redirect URI pointing at `acme-staging-admin-dns`. Record it with `write_component`.

*Talking point:* the recursive CTE - graph reachability a vector store can't do -
proves the dependency before writing code. Staging is now at parity, built by three
tools sharing one brain.

---

## Headline moments (run any time, any pane)

**Blast radius (the "what breaks if I change this" query):**
> Use the tidb MCP. Run a recursive CTE for the blast radius of `S3Bucket` - every
> component that transitively depends on it. Should reach the RDS instances two hops
> away via their backup buckets.

**Convention catch (the duplicate-bucket trap):**
> I'm about to add a backup S3 bucket for `acme-staging-analytics-db`. First query the
> KB: does `PostgresDatabase` already create one?

It does (`instantiates` edge) - so the right move is to write nothing. The graph
prevented a duplicate, untagged, raw-resource bucket.

**Vector search (TiDB for AI):**
> Use the tidb MCP. Find components semantically similar to "CDN for user-facing
> static files" using VEC_COSINE_DISTANCE over the summary embeddings.

---

## Reset between runs

- Dashboard **Reset KB** button, or
- `python -m src.seed --reset`
