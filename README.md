# mem9-ai-coding

A shared, TiDB-backed **infrastructure knowledge graph** that Claude Code, Codex, and Cursor all read from and write to through one MCP server. Every coding tool sees the same memory of every Pulumi component, dependency edge, and prior session.

```
Claude Code ──┐
Codex        ─┼── tidb-infra-kb (MCP) ── kb.db  (SQLite locally · TiDB Cloud in prod)
Cursor       ──┘                              │
                                    Dashboard (localhost:7001)
                          graph · 3-CLI replay · before/after memory · recursive-CTE · scenarios
```

## Quick start

```bash
git clone https://github.com/stephenlthorn/mem9-ai-coding && cd mem9-ai-coding
./demo.sh
```

Opens the dashboard at <http://localhost:7001> seeded with a Acme-style Pulumi scenario:
4 library components, a full production environment, and an **incomplete staging environment** (the demo task).

## The dashboard (5 views)

| Tab | What it shows |
|---|---|
| **Overview** | Force-directed component graph (typed nodes, env rings, relationship edges) + component table + live session log. The yellow banner shows what staging is missing vs production. |
| **3 CLIs, live** | A triptych of Claude Code / Codex / Cursor terminals. Press **Play** and the three tools collaborate - querying and writing the *same* database - to bring staging to parity. Each `✓ write_component` is a real KB mutation. |
| **Before / After memory** | The mem9 memory store at seed time vs after the agents collaborated. New memories - written by whichever tool created them - are highlighted. |
| **Dependency graph (CTE)** | Pick any component and run a **recursive CTE**: *blast radius* (what breaks if this changes, traversing upstream) or *dependencies* (what it transitively needs). The transitive closure is highlighted on the graph, colored by depth, with the exact SQL shown. |
| **Pulumi scenarios** | Two headline scenarios - the duplicate backup bucket and blast-radius-before-a-refactor - showing what the graph prevents that a flat repo or vector store can't. |

## Why a graph (and recursive CTEs)?

The two things that bite a Pulumi monorepo are *composition* and *blast radius*:

- **Composition:** `PostgresDatabase` already instantiates an `S3Bucket` for backups. A dev who can't see that relationship hand-rolls a duplicate (often as a raw `aws.s3.BucketV2`, breaking the no-raw-resources rule). The graph makes the relationship a first-class, queryable edge.
- **Blast radius:** changing the `S3Bucket` library ripples - via `PostgresDatabase` - all the way to every RDS instance, two hops away. A recursive CTE computes that transitive closure in one query. Vector similarity finds *related-looking* code; it cannot compute graph reachability.

```sql
-- What breaks if S3Bucket changes? (runs unchanged on SQLite and TiDB)
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

## Connect the three tools

All three use the same MCP server command - update the `cwd` path to this repo:

```json
{
  "mcpServers": {
    "tidb-infra-kb": {
      "command": "python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/mem9-ai-coding"
    }
  }
}
```

| Tool | Config | Project file |
|---|---|---|
| Claude Code | merge `configs/claude-code/mcp.json` into `.mcp.json` | copy `configs/claude-code/CLAUDE.md` to project root |
| Codex | same MCP JSON | copy `configs/codex/AGENTS.md` to project root |
| Cursor | `configs/cursor/mcp.json` → `.cursor/mcp.json` | copy `configs/cursor/.cursorrules` to project root |

### MCP tools exposed to every coding tool

| Tool | Description |
|---|---|
| `query_knowledge_base` | Run a SELECT (incl. recursive CTEs) over `infra_components`, `component_edges`, `session_log` |
| `write_component` | Atomic write: component + dependency edge + session-log entry |

## Demo flow

1. **Overview** - point out the staging gap (yellow banner).
2. **3 CLIs, live** - press Play. Claude Code scaffolds two components, Codex picks up the warm session log and continues, Cursor runs a dependency CTE then finishes the SSO app. Staging reaches parity, built by three tools sharing one memory.
3. **Before / After** - the four new memories are now in the store, tagged by the tool that wrote them.
4. **Dependency graph (CTE)** - run blast radius on `S3Bucket` to show the transitive closure reaching the RDS instances.
5. **Scenarios** - the concrete Pulumi pain points and how the graph solves them.

Reset any time with the **Reset KB** button (top right) or `python -m src.seed --reset`.

## Writeback CLI

```bash
python -m src.writeback \
  --name acme-staging-admin-dns --type Cloudflare --env staging \
  --summary "Cloudflare DNS for the staging admin portal" \
  --depends-on DnsRecord --developer claude-code
```

## Layout

| Path | Description |
|---|---|
| `src/db.py` | KB: schema, atomic writes, recursive-CTE traversals (SQLite + TiDB compatible) |
| `src/seed.py` | Seeds 4 libs, 6 prod, 2 staging components + composition edges |
| `src/mcp_server.py` | `tidb-infra-kb` MCP server (stdio) - `query_knowledge_base` + `write_component` |
| `src/writeback.py` | CLI writeback used by agents after scaffolding |
| `dashboard/server.py` | FastAPI API + static dashboard host |
| `dashboard/static/` | Tabbed single-page dashboard (graph, terminals, memory, CTE, scenarios) |
| `configs/` | Per-tool MCP + rules configs for Claude Code, Codex, Cursor |

## TiDB Cloud (full demo)

The schema and every recursive CTE run unchanged on TiDB. Point `src/db.py` at a TiDB DSN to use the distributed engine and add `VEC_COSINE_DISTANCE` for hybrid graph + vector retrieval over component embeddings.

## License

Apache-2.0
