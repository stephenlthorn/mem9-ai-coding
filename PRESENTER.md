# Presenter's guide - the 5-minute walkthrough

> Read this top to bottom. It tells you what to say, what to click, what the
> audience sees, and why each moment matters.

---

## 0. The idea in one sentence

> "Your existing coding tools - Claude Code, Codex, Cursor - plus a memory the database holds (mem9). What components exist, how they connect, and the rules for building them live in TiDB Cloud (mem9.ai) as a shared memory every tool reads and writes - organized as team = cluster, repo = database."

## The problem you're solving (say this first)

Acme runs a Pulumi TypeScript monorepo. Developers now use AI coding tools
- Claude Code, Codex, Cursor - to write infrastructure. But each tool works
**blind and alone**:

- It can't see that a component **already exists** → it builds a duplicate.
- It can't see the team's **conventions** → it writes a raw `aws.s3.Bucket`
  instead of the approved library wrapper.
- It can't see how components **connect** → it changes a shared library and
  breaks things two hops away in production.
- The next tool/session starts **cold** → re-derives everything, re-makes mistakes.

**The fix:** put the knowledge in TiDB, connect every tool to it over MCP.

```
   Claude Code ─┐
   Codex       ─┼──►  MCP  ──►  mem9.ai (TiDB Cloud)  ◄── the memory the database holds
   Cursor      ─┘                 (team = cluster · repo = database)
                                        │
                                  Dashboard  ◄── what you narrate
```

---

## 1. Before you start (pre-flight, 1 min)

- [ ] `./demo.sh` running → dashboard open at **http://localhost:7001**
- [ ] Header says **"mem9.ai (TiDB Cloud)"**
- [ ] Dashboard on the **Live** tab, showing the staging gap
- [ ] 3 iTerm panes open side by side, each `cd`'d into the repo:
      `claude` · `codex` · `cursor-agent`
- [ ] Reset to a clean slate: click **Reset KB** (top-right) once
- [ ] Bootstrap has been run (`./setup.sh` -> `python -m src.ingest --reset`) so both `acme_pulumi_kb` and `acme_lza_kb` are populated.

Arrange the screen: **iTerm panes on top/left, dashboard visible** so the audience
sees the tools AND the brain at the same time.

---

## 2. Orient the audience (45 sec) - the dashboard

Point at the dashboard, left to right:

- **Left - "3 tools → 1 TiDB":** "This is a live feed of every query and write the
  three coding tools make. Right now it just shows the seed data."
- **Right - the graph:** "This is the knowledge graph. Green = reusable libraries
  (`S3Bucket`, `PostgresDatabase`, `DnsRecord`, `SsoApplication`). The rings show
  environment - green ring = production, yellow = staging."
- **The yellow banner / parity strip:** "Production is complete. **Staging is
  missing its DNS and SSO layer.** That's the job. Watch three different AI tools
  finish it - sharing one brain."

---

## 3. The walkthrough - three tools, one task (3 min)

> Paste each prompt into the matching iTerm pane. After each, point at the
> dashboard feed lighting up.

### Pane 1 - Claude Code (inspect + build the asset layer)

**Paste:**
> Use `infra-kb-pulumi`. Query the knowledge base: what components exist in
> `staging` vs `production` in `acme_pulumi_kb`, and what is staging missing? Then scaffold the missing
> staging static-assets bucket and its Cloudflare DNS record, composing the
> `S3Bucket` and `DnsRecord` libraries - never raw `aws.*` resources. Follow the
> `acme-<env>-<name>` naming and required tags. Record each new component with
> `write_component`.

**Say:** "Notice it **queries first** - it doesn't assume. It composes the existing
libraries, not raw cloud resources. And it **writes its work back** to TiDB."

**Audience sees:** QUERY rows then WRITE rows appear in the left feed under
`claude-code`; two new nodes pop into the graph; the parity strip flips two ✗ to ✓.

### Pane 2 - Codex (pick up warm - the shared-memory moment)

**Paste:**
> Use `infra-kb-pulumi`. Read the recent `session_log` in `acme_pulumi_kb` - what did the previous
> session just create? Continue the staging build: add the admin-portal DNS record
> (`acme-staging-admin-dns`) matching the production pattern, composing `DnsRecord`.
> Record it with `write_component`.

**Say (the key line):** "Codex just opened. It has **zero local memory** of what
Claude Code did. But it reads the **shared TiDB session log** and instantly knows
where to continue. No copy-pasting context between tools. This is the part teams
feel every day."

**Audience sees:** a `codex` QUERY reading the log, then a `codex` WRITE; another node appears.

### Pane 3 - Cursor (prove a dependency with a recursive CTE, then finish)

**Paste:**
> Use `tidb-pulumi` (`db_query`) to run a recursive CTE: what does the production
> `acme_pulumi_kb`'s `acme-prod-admin-sso` transitively depend on? Confirm an SSO app must redirect to a
> `DnsRecord`. Then scaffold `acme-staging-admin-sso` composing `SsoApplication`, with
> the redirect URI pointing at `acme-staging-admin-dns`. Record it with `write_component`.

**Say:** "Cursor uses the **official TiDB MCP** to run a recursive query over the
graph - it proves the dependency chain before writing a line of code. Then it
finishes the job."

**Audience sees:** the last node appears; **parity strip goes all ✓ - "at parity"**.
"Three different tools. One TiDB brain. Staging is now a faithful copy of production,
built to convention, with full history of who did what."

### Cross-repo + isolation (the new money moments)

**Cross-repo (B):** run `python -m src.cross_repo_demo` (or the prompts in DEMO.md). One
team connection writes acme_lza_kb AND acme_pulumi_kb, then a cross-database JOIN ties the
bucket to its LZA account. Say: "Two repos, two databases, one query - no second login."

**Isolation (C):** run `python -m src.isolation_check`. Say: "Team = cluster. An agent on
team acme has no path to team globex. Credentials bound the blast radius."

---

## 4. The three money moments (pick what fits your audience)

### A. Recursive CTE - "the query a vector database can't answer"
Click the **Dependency graph (CTE)** tab. Component = `S3Bucket`, mode =
**Blast radius**, click **Run**.

**Say:** "What breaks if I change the `S3Bucket` library? The graph traverses every
dependency to any depth. Look - it reaches the **RDS databases two hops away**,
because their backup buckets compose `S3Bucket`. A vector search finds *similar-
looking* code. It **cannot compute this** - this is graph reachability, and it's
plain SQL on TiDB." (Point at the SQL on the right - same SQL the CLIs run.)

### B. The convention guardrail - "the duplicate it didn't build"
In any iTerm pane, paste:
> I'm about to add a backup S3 bucket for `acme-staging-analytics-db`. First query the
> KB: does `PostgresDatabase` already create one?

**Say:** "It checks first, sees `PostgresDatabase` **already instantiates** a backup
bucket, and writes **nothing**. The graph just prevented a duplicate, untagged,
drift-causing resource - the #1 thing that goes wrong with AI-written infra."

### C. It's real TiDB
Point at the header: **"mem9.ai - TiDB Cloud."** "Everything you saw - the graph,
the recursive CTE, the writes from three tools - ran on a real TiDB Cloud
cluster over MySQL protocol. Same database that scales to your production workload."

---

## 5. Close (15 sec)

> "Three AI coding tools, the exact ones your team uses, all sharing one TiDB brain.
> They query before they build, follow your conventions, see the blast radius of a
> change, and hand off warm to the next tool. That's mem9 - the memory the database holds - for agentic engineering."

---

## FAQ / objection handling

**"Why not a vector database / RAG?"** Vector search finds semantically similar
text. It can't traverse a dependency graph or compute a transitive blast radius.
This demo's headline query (recursive CTE) is graph reachability - relational, not
similarity. TiDB also *has* vector search, so you get both in one engine.

**"Is this just for Pulumi?"** No - the pattern is "shared, queryable engineering
memory across tools." Pulumi infra is the example; it works for any codebase graph.

**"How do the tools connect?"** Standard MCP. Each tool loads two MCP servers: the
official PingCAP `tidb` server (raw SQL + vector) and a thin `tidb-infra-kb` server
that enforces conventions. Configs are generated per tool from your `.env`.

**"Does it scale?"** It's TiDB Cloud - the same distributed SQL engine
behind large production workloads. The demo cluster and a production cluster are the
same product.

---

## If something breaks mid-demo

- Dashboard blank / errors → `./demo.sh` again; check `.env` has TiDB creds.
- A CLI can't see the tools → confirm it launched from the repo dir; re-run
  `python -m src.gen_configs`.
- Want a clean slate → **Reset KB** button (or `python -m src.seed --reset`).
- TiDB unreachable (wifi) → unset `TIDB_HOST` and it falls back to local SQLite;
  the whole demo still runs, header will say "SQLite (local fallback)".
