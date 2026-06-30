# Live demo runbook - your tools + a memory the database holds (mem9)

Claude Code, Codex, and Cursor share one team's memory on mem9.ai (TiDB Cloud). Each
starts cold; each reads the shared memory and continues where the last left off. The team
has two repos, each its own database: `acme_pulumi_kb` and `acme_lza_kb`.

## One-time setup (bootstrap)

```bash
cd mem9-ai-coding
cp .env.example .env          # paste your mem9.ai creds (Connect -> General)
./setup.sh                    # bootstraps BOTH repo DBs + generates MCP configs
```

`setup.sh` runs `python -m src.ingest --reset` (the explicit bootstrap that populates each
repo's KB from source) and `python -m src.gen_configs` (per-tool configs, one named server
entry per repo database). Confirm the target:

```bash
.venv/bin/python -c "from src import db; print('target:', db.backend_name())"
```

Open the optional dashboard (appendix view of the Pulumi repo): `./demo.sh` -> http://localhost:7001

## The named MCP servers (routing is explicit)

Each tool loads four entries, scoped to the team `acme` cluster:
- `infra-kb-pulumi` / `infra-kb-lza` - mem9 convention layer (`query_knowledge_base`, `write_component`)
- `tidb-pulumi` / `tidb-lza` - official TiDB MCP (`db_query`, recursive CTEs, vector search)

The agent picks the entry for the repo it is changing - the server never guesses.

## iTerm: open 3 panes (Cmd+D to split), each `cd`'d into the repo

| Pane | Launch | Tool |
|---|---|---|
| 1 | `claude` | Claude Code |
| 2 | `codex` | Codex |
| 3 | `cursor-agent` | Cursor |

---

## Scenario A - single repo (bring staging to parity in Pulumi)

### Pane 1 - Claude Code: inspect + scaffold the asset layer
> Use `infra-kb-pulumi`. Query the KB: what exists in staging vs production in
> `acme_pulumi_kb`, and what is staging missing? Then scaffold the missing staging
> static-assets bucket and its Cloudflare DNS record, composing `S3Bucket` and `DnsRecord` -
> never raw `aws.*`. Set account_ref='sandbox'. Record each with `write_component`
> (developer='claude-code').

### Pane 2 - Codex: pick up warm, continue
> Use `infra-kb-pulumi`. Read the recent `session_log` in `acme_pulumi_kb` - what did the
> last session create? Continue: add `acme-staging-admin-dns` (compose `DnsRecord`,
> account_ref='sandbox'). Record it with `write_component` (developer='codex').

### Pane 3 - Cursor: prove a dependency (recursive CTE), then finish
> Use `tidb-pulumi` (`db_query`) to run a recursive CTE: what does
> `acme_pulumi_kb`'s `acme-prod-admin-sso` transitively depend on? Confirm SSO must redirect
> to a `DnsRecord`. Then scaffold `acme-staging-admin-sso` composing `SsoApplication`,
> redirect URI -> `acme-staging-admin-dns`, account_ref='sandbox'. Record with
> `write_component` (developer='cursor').

---

## Scenario B - cross repo (LZA account, then Pulumi bucket in it)

> Use `infra-kb-lza` to create a new AWS account `acme-lza-account-data-platform`
> (account_ref='data-platform', compose `AwsAccount`). Then use `infra-kb-pulumi` to create
> `acme-prod-data-platform-exports` (compose `S3Bucket`, account_ref='data-platform').
> Finally use `tidb-pulumi` to run a cross-database JOIN proving the bucket maps to the new
> account:
> ```sql
> SELECT p.name, p.account_ref, a.name AS lza_account
> FROM acme_pulumi_kb.infra_components p
> JOIN acme_lza_kb.infra_components a ON a.account_ref = p.account_ref AND a.component_type='Account'
> WHERE p.account_ref = 'data-platform';
> ```

Both writes and the JOIN use the **same team credentials** - no separate per-cluster auth.
Scripted equivalent: `python -m src.cross_repo_demo`.

**Talking point:** one team cluster, two repo databases, joined in a single query. Vector
search finds related-looking code; only the database can JOIN the bucket to its account.

---

## Scenario C - team isolation (cross-team read fails by design)

```bash
python -m src.isolation_check
```
Expected: `PASS - acme has no query path to globex_pulumi_kb ... Isolation holds by design.`

On mem9.ai, prove it with a scoped user (run once as an admin connection):
```sql
CREATE USER 'acme_agent'@'%' IDENTIFIED BY '<pw>';
GRANT SELECT, INSERT, UPDATE ON `acme\_%`.* TO 'acme_agent'@'%';
-- Now connect as acme_agent and try to read globex:
SELECT COUNT(*) FROM globex_pulumi_kb.infra_components;   -- ERROR 1142: access denied
```

**Talking point:** team = cluster. Credentials unlock one team's data only; another team's
KB is unreachable by design.

---

## Headline moments (any pane)

**Blast radius (graph reachability a vector store can't do):**
> Use `tidb-pulumi`. Recursive CTE for the blast radius of `S3Bucket` in `acme_pulumi_kb` -
> every component that transitively depends on it (reaches the RDS instances two hops away).

**Convention catch (the duplicate it didn't build):**
> Use `infra-kb-pulumi`. Before adding a backup bucket for `acme-staging-analytics-db`,
> query: does `PostgresDatabase` already create one? (It does - write nothing.)

## Reset between runs

- Dashboard **Reset KB**, or `python -m src.seed --reset`.

## Appendix - the dashboard

The dashboard is an optional window onto the Pulumi repo database (graph, CTE, replay). It
is not the product; mem9 is the memory layer, the dashboard just visualizes it.
