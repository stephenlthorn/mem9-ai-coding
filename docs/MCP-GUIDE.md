# mem9 MCP user guide

How your coding tool talks to the team's database-held memory (mem9), how routing is
deterministic, and how per-team auth bounds what you can reach.

## What you connect to

mem9 is a memory layer backed by TiDB Cloud (mem9.ai). Your tool reaches it over MCP -
the same protocol Claude Code, Codex, and Cursor already speak. Two server kinds:

| Server | Purpose | Tools |
|---|---|---|
| `tidb-<repo>` | Official TiDB MCP - raw SQL | `db_query`, `db_execute` |
| `infra-kb-<repo>` | mem9 convention layer | `query_knowledge_base`, `write_component` |

## Routing is explicit (one named entry per repo database)

There is **one named server entry per repo database**, and you choose which to call. The
server never infers the destination from your prompt.

- Working in the Pulumi repo? Call `infra-kb-pulumi` (writes land in `acme_pulumi_kb`) or
  `tidb-pulumi` for raw SQL.
- Working in the LZA repo? Call `infra-kb-lza` / `tidb-lza` (`acme_lza_kb`).

```
Cursor -- infra-kb-pulumi -+
       -- infra-kb-lza    -+
       -- tidb-pulumi     -+--► team acme cluster (mem9.ai)
       -- tidb-lza        -+     +-- acme_pulumi_kb
                                 +-- acme_lza_kb
```

## How the agent communicates

1. The agent sends a `tools/call` to the named server you targeted.
2. `infra-kb-*` validates and writes atomically (component + edge + session-log) into its
   bound repo database, or runs your read-only SELECT.
3. `tidb-*` runs raw SQL. Because every server shares the same team credentials, a query on
   `tidb-pulumi` can cross-database JOIN into `acme_lza_kb` - no second login.

## Per-team auth (isolation)

Credentials are scoped to **one team cluster**. In production each team is its own TiDB
cluster; in this demo we simulate teams as database namespaces (`acme_*`, `globex_*`) and
GRANT each team's user access to only its own databases. Either way: an agent authenticated
to team `acme` has **no query path** to `globex_*`. Verify it:

```bash
python -m src.isolation_check       # prints PASS - cross-team read has no path
```

## Cross-repo work, one connection (Scenario B)

"Create an AWS account in LZA, then an S3 bucket in that account in Pulumi" touches both
databases over the same team connection:

```bash
python -m src.cross_repo_demo       # writes both repos, prints the cross-db JOIN
```

## Connect your tool

1. `cp .env.example .env` and paste your mem9.ai cluster creds.
2. `./setup.sh` - bootstraps both repo databases and generates per-tool MCP configs.
3. Claude Code reads `.mcp.json`; Cursor reads `.cursor/mcp.json`; Codex: paste
   `configs/generated/codex-config.toml` into `~/.codex/config.toml`.
4. Launch your tool from the repo directory. The named servers appear; pick the one for
   the repo you are changing.

## Gotchas

- **Persist is instruction-driven.** The agent must call `write_component`; nothing writes
  back automatically.
- **Eventual consistency.** Full-text and columnar indexes lag writes by ~seconds. For a
  read-your-write check use a point lookup by `name`.
- **Full-text is Cloud-only and early-access.** On a local tiup playground, keyword search
  degrades to `LIKE`; vector search still works (with precomputed embeddings). On Cloud, full-text
  is Starter/Essential only, limited to specific AWS regions, and enabled per cluster - so a
  cluster can accept the `FULLTEXT INDEX` DDL yet hang on `FTS_MATCH_WORD` because its index builder
  never advances. `db.search()` handles this with bounded timeouts and degrades hybrid to
  vector-only, so search never hangs. For live full-text, provision the cluster in a currently
  supported region with full-text enabled and point `.env` at it.
