# Demo Recording Runbook + Narration Script

Three AI coding tools sharing one TiDB Cloud brain. Step 2 ("Codex") is powered by the **MiniMax CLI** (model MiniMax-M3) because the OpenAI/Codex path is unavailable - it talks to the same `tidb-infra-kb` MCP server and the same TiDB database, and writes the feed as `developer='codex'`, so on screen it stays "Codex."

---

## A. One-time pre-flight (run once before recording)

```bash
cd ~/GitHub/mem9-ai-coding

# 1. MiniMax CLI present + pointed at M3
which minimax && minimax --version
cat ~/.minimax/user-settings.json   # apiKey + baseURL https://api.minimax.io/v1 + model MiniMax-M3

# 2. The other two CLIs present
which claude cursor-agent

# 3. TiDB reachable + MCP server healthy
set -a; source .env; set +a
.venv/bin/python -c "from src import db; print('backend:', db.backend_name())"

# 4. Bootstrap both repo databases (explicit setup before recording)
.venv/bin/python -m src.ingest --reset
```

Expected: `minimax` resolves, `claude` + `cursor-agent` resolve, backend prints `mem9.ai (TiDB Cloud)`.

---

## B. Start the dashboard (Terminal 0 - leave running)

```bash
cd ~/GitHub/mem9-ai-coding
set -a; source .env; set +a
.venv/bin/uvicorn dashboard.server:app --host 0.0.0.0 --port 7001
```

Open **http://localhost:7001** in the browser. Hard-refresh with **Cmd+Shift+R** if it looks stale.

If the port is stuck: `lsof -ti :7001 | xargs kill -9` then re-run.

---

## C. Reset to a clean baseline (before every take)

Either click **Reset KB** on the dashboard, or:

```bash
cd ~/GitHub/mem9-ai-coding
set -a; source .env; set +a
.venv/bin/python -m src.seed --reset
```

Baseline = **library 4 / production 6 / staging 2** → parity strip shows **4 missing**.

---

## D. The three panes (open three terminals, all in the repo)

| Pane | Label on screen | Launch command |
|------|-----------------|----------------|
| 1 | **Claude Code** | `cd ~/GitHub/mem9-ai-coding && claude` |
| 2 | **Codex** (runs MiniMax M3) | `cd ~/GitHub/mem9-ai-coding && minimax -m MiniMax-M3` |
| 3 | **Cursor** | `cd ~/GitHub/mem9-ai-coding && cursor-agent` |

Paste-prompts for each step (also on the dashboard's Live tab, with Copy buttons):

**Pane 1 - Claude Code:**
```
Use infra-kb-pulumi. Query the knowledge base: what components exist in staging vs production in acme_pulumi_kb, and what is staging missing? Then scaffold the missing staging static-assets bucket and its Cloudflare DNS record, composing the S3Bucket and DnsRecord libraries - never raw aws.* resources. Follow the acme-<env>-<name> naming and required tags. Set account_ref='sandbox'. Record each new component with write_component. Pass developer='claude-code' on every infra-kb-pulumi call so the activity feed attributes the work.
```

**Pane 2 - "Codex" (MiniMax):**
```
Use infra-kb-pulumi. Read the recent session_log in acme_pulumi_kb - what did the previous session just create? Continue the staging build: add the admin-portal DNS record (acme-staging-admin-dns) matching the production pattern, composing DnsRecord. Set account_ref='sandbox'. Record it with write_component. Pass developer='codex' on every infra-kb-pulumi call so the activity feed attributes the work.
```

**Pane 3 - Cursor:**
```
Use tidb-pulumi (db_query) to run a recursive CTE: what does the production acme_pulumi_kb's acme-prod-admin-sso transitively depend on? Confirm an SSO app must redirect to a DnsRecord. Then scaffold acme-staging-admin-sso composing SsoApplication, with the redirect URI pointing at acme-staging-admin-dns, account_ref='sandbox'. Record it with write_component (developer='cursor') so the activity feed attributes the work.
```

After each paste, watch the dashboard: QUERY rows then WRITE rows appear, and the parity strip drops 4 → 2 → 1 → 0.

---

## E. Narration script (talk over the video)

### 0. Open (~20s) - dashboard on screen, nothing running yet
> "This is a live window onto a mem9.ai memory layer (TiDB Cloud). Every row you see is a real query.
> On the right is a shared memory the database holds of an infrastructure codebase - a Pulumi monorepo.
> Production is complete. Staging has drifted: it's missing its DNS records and its SSO app - four components.
> The job: bring staging to parity. And I'm going to do it with three *different* AI coding tools - Claude Code, Codex, and Cursor - that have never talked to each other. Their only shared memory is TiDB."

### 1. Claude Code (~60s) - paste into Pane 1
> "First, Claude Code. Notice what it does *before* it writes anything - it queries TiDB. What exists in staging, what exists in production, what's the gap?
> No grepping the codebase, no guessing - a database query returns the exact answer.
> It finds the two missing pieces, builds them by composing the approved library components - never raw AWS resources - and writes them back to TiDB.
> Watch the feed: query rows, then write rows. Parity just went from four missing to two."

### 2. "Codex" / MiniMax (~60s) - paste into Pane 2
> "Now a second tool - a completely different vendor, a fresh session, zero context of what just happened.
> The first thing it does is read the shared session log. It sees - 'the previous session just created the static-assets bucket and its DNS record.'
> Nobody briefed it. No Slack message, no handoff meeting. It just reads the shared memory in TiDB and picks up exactly where the last tool left off.
> It adds the admin-portal DNS record and writes it back. Two missing, now one.
> *(This pane is the MiniMax model driving the exact same MCP tools - that's the point: any tool, same brain.)*"

### 3. Cursor (~60s) - paste into Pane 3
> "Last tool - Cursor. Before it builds, it does something a vector database simply cannot do.
> It runs a recursive query against TiDB - what does the production SSO app transitively depend on? TiDB walks the dependency graph to any depth and answers: an SSO app must redirect to a DNS record.
> That's graph reachability - plain SQL on TiDB. You can't grep for it, and embeddings can't compute it.
> Now Cursor knows the exact pattern, builds the staging SSO app correctly, pointing at the DNS record the previous tool just created. Parity strip - all green. Done."

### 3b. Cross-repo + isolation (optional, ~30s)
> "Two repos, two databases - `acme_pulumi_kb` and `acme_lza_kb` - connected with a single cross-database JOIN over one team connection. No second login, no second cluster.
> And if you try to read another team's KB? Access denied. Team = cluster; credentials bound the blast radius.
> Run `python -m src.cross_repo_demo` for the JOIN, `python -m src.isolation_check` for the proof."

### 4. Close (~15s)
> "Three AI coding tools, three different vendors, one TiDB brain. They queried before they built, followed the conventions, saw the blast radius of a change, and handed off warm to each other.
> That's mem9 - the memory the database holds - for agentic engineering."

---

## F. Recovery during recording

- **Dashboard not loading:** check it's up - `lsof -nP -i :7001 | grep LISTEN`; restart with section B; hard-refresh browser.
- **A tool writes the wrong feed label:** the prompts pin `developer=...`; if you edited a prompt, keep that clause.
- **Need to re-shoot a step:** run the reset in section C, refresh the dashboard, start over from Pane 1.
- **MiniMax shows `<think>...` text:** that's the model reasoning out loud - normal; it still calls the tool and writes. You can scroll past it.
