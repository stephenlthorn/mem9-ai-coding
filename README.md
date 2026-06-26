# mem9-ai-coding

**Your existing Cursor (or Claude Code, or Codex) plus a memory the database holds.**

mem9 is a memory layer - backed by TiDB Cloud (mem9.ai) - that your coding tools share.
Every infrastructure component, dependency edge, and prior session lives in the database,
so tools stop duplicating work, stop breaking conventions, and never start from zero.

```
Claude Code --+
Codex        -+-- MCP (one named entry per repo) --► team cluster on mem9.ai
Cursor       --+                                       +-- acme_pulumi_kb   (Pulumi repo)
                                                       +-- acme_lza_kb      (AWS LZA repo)
```

## The model: team = cluster, repo = database

- **Team = cluster.** A team maps to its own TiDB cluster. Credentials unlock only that
  team's data - an agent on team `acme` has no path to team `globex`. (In this demo a
  single cluster simulates teams as database namespaces: `acme_*`, `globex_*`.)
- **Repo = database.** Each repo is its own database inside the team's cluster
  (`acme_pulumi_kb`, `acme_lza_kb`). Work in one, or across both with a cross-database JOIN
  over the same connection.
- **Components carry provenance** (`repo`) and a cross-repo key (`account_ref`), so a single
  query can tie a Pulumi bucket to the LZA account it lives in.

## Lifecycle: bootstrap, then query-before / persist-after

1. **Bootstrap (explicit, before any agent session).** Walk each repo's source, extract
   components + dependency edges, embed, and INSERT:
   ```bash
   python -m src.ingest --reset          # populate acme_pulumi_kb + acme_lza_kb
   ```
   On mem9.ai embeddings are generated server-side with `EMBED_TEXT`; on a local tiup
   playground they are precomputed client-side.
2. **Query first.** At session start the agent queries the KB (warm start).
3. **Persist after.** After scaffolding, the agent calls `write_component`. **Write-back is
   instruction-driven, not automatic** - it is an explicit instruction in the agent prompts.

> **Eventual consistency:** full-text / columnar (TiCI) indexes lag writes by a second or
> two. Strongly consistent read-your-write checks use point lookups by `name`.

## Targets and capabilities

The same demo runs on two targets. Full-text search is **Cloud only**; vector search works
on both; the local target degrades keyword search to `LIKE`.

| Capability | mem9.ai / Cloud Starter | Local tiup playground |
|---|---|---|
| Relational + recursive CTE | ✅ | ✅ |
| Cross-database JOIN (repo = db) | ✅ | ✅ |
| Vector search | ✅ `EMBED_TEXT` auto-embed | ✅ precomputed (`fastembed`) |
| Keyword search | ✅ full-text (`FTS_MATCH_WORD`) | ✅ `LIKE` boost |
| Hybrid (RRF) | ✅ vector + full-text | ✅ vector + `LIKE` |

(A SQLite path exists purely as an offline/test substrate: relational + `LIKE`, no vector.)

> **Full-text is region-gated.** It is Cloud Starter/Essential only **and** only served in
> some regions. A cluster can accept the `FULLTEXT INDEX` DDL yet not serve `FTS_MATCH_WORD`
> queries (e.g. `eu-central-1` does not). When full-text is unavailable, `db.search()`
> degrades hybrid to vector-only automatically, so the demo still runs - it just can't show
> the vector+full-text fusion live. To demo full hybrid, use a full-text-enabled region.

## Quick start

```bash
git clone https://github.com/stephenlthorn/mem9-ai-coding && cd mem9-ai-coding
cp .env.example .env          # paste your mem9.ai cluster creds
./setup.sh                    # bootstrap both repo DBs + generate per-tool MCP configs
```

## Scenarios

- **A. Single repo** - an agent queries/writes only `acme_pulumi_kb`. See [DEMO.md](DEMO.md).
- **B. Cross repo** - create an AWS account in LZA, then an S3 bucket in that account in
  Pulumi, over one connection: `python -m src.cross_repo_demo`.
- **C. Team isolation** - prove team `acme` cannot read team `globex`:
  `python -m src.isolation_check`.

## Connect your tools

`./setup.sh` runs `python -m src.gen_configs`, writing per-tool configs with **one named
server entry per repo database**, all scoped to one team cluster. Routing is explicit - the
agent picks `infra-kb-pulumi` vs `infra-kb-lza` (and `tidb-pulumi` vs `tidb-lza`) itself.

| Tool | Config | Project file |
|---|---|---|
| Claude Code | `.mcp.json` (generated) | copy `configs/claude-code/CLAUDE.md` to repo root |
| Codex | paste `configs/generated/codex-config.toml` | copy `configs/codex/AGENTS.md` |
| Cursor | `.cursor/mcp.json` (generated) | copy `configs/cursor/.cursorrules` |

See [docs/MCP-GUIDE.md](docs/MCP-GUIDE.md) for how routing and per-team auth work.

## Layout

| Path | Description |
|---|---|
| `src/topology.py` | team/repo registry, target detection, capability flags |
| `src/db.py` | target-aware + repo-aware KB (cloud/local/sqlite) |
| `src/embed.py` | local precomputed embeddings (cloud uses `EMBED_TEXT`) |
| `src/repos/` | per-repo component manifests (Pulumi, AWS LZA) |
| `src/ingest.py` | bootstrap/backfill each repo's KB |
| `src/seed.py` | seed team acme (both repos) + team globex (isolation) |
| `src/mcp_server.py` | repo-scoped mem9 convention MCP (`MEM9_REPO`) |
| `src/cross_repo_demo.py` | Scenario B (cross-database JOIN) |
| `src/isolation_check.py` | Scenario C (team isolation proof) |
| `configs/` | per-tool MCP + context configs |
| `docs/MCP-GUIDE.md` | MCP connect / routing / auth guide |

## Appendix: the dashboard (optional)

A FastAPI dashboard at `http://localhost:7001` (`./demo.sh`) visualizes the Pulumi repo's
graph, the recursive-CTE blast radius, and the 3-tool replay. It is an **optional, under-the-
hood view** of what the database holds - not the product. mem9 is the memory layer; the
dashboard is just a window onto it.

## License

Apache-2.0
