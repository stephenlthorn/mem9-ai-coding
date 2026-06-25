# mem9 Team/Repo Memory Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the `mem9-ai-coding` demo so the shared knowledge base is organized as **team = cluster / repo = database**, adds a second **AWS LZA** repo alongside Pulumi, supports an explicit **bootstrap-then-persist** lifecycle, exposes **one named MCP server entry per repo database**, and repositions everything around "your existing Cursor plus a memory the database holds (mem9)" - all while keeping the existing single-repo flow working end-to-end on **mem9.ai (TiDB Cloud)**.

**Architecture:** A team maps to a TiDB cluster (production) or a database-name namespace within one cluster (this demo + local dev). Each repo maps to its own database in that cluster (`acme_pulumi_kb`, `acme_lza_kb`). The Python KB layer becomes **target-aware** (cloud = `EMBED_TEXT` auto-embedding + `FULLTEXT` + hybrid RRF; local tiup = precomputed embeddings + `LIKE` keyword boost; SQLite = relational + `LIKE`, offline/test only) and **repo-aware** (every read/write is scoped to a repo's database; cross-repo work uses cross-database JOINs over one team connection). MCP configs get one named server per repo database, credentials scoped to a single team cluster. The recursive-CTE dashboard moves to an optional appendix.

**Tech Stack:** Python 3.11, PyMySQL (TiDB over MySQL protocol, TLS), TiDB Cloud vector (`VECTOR`, `VEC_COSINE_DISTANCE`, server-side `EMBED_TEXT`) + full-text (`FULLTEXT`, `FTS_MATCH_WORD`), `fastembed` (local precomputed embeddings, optional), SQLite (offline/test substrate, `ATTACH DATABASE` for cross-repo), FastAPI (dashboard), stdio JSON-RPC MCP server, pytest.

---

## Hard constraints (must not be violated)

1. **Full-text search is Cloud only.** Hybrid (vector + full-text) paths are gated to the cloud target. The local/SQLite targets degrade to vector + `LIKE` (local) or `LIKE` only (SQLite). Never claim full-text off-cloud.
2. **Vector works on cloud + local tiup (v8.4.0+), not SQLite.** Cloud embeds server-side with `EMBED_TEXT`; local precomputes embeddings client-side and inserts a vector literal. SQLite has no vector column.
3. **MCP routing is explicit, never inferred.** One named server entry per repo database, credentials scoped to a single team cluster. No copy or code may imply the MCP "figures out" the destination.

## Capability matrix (becomes a README table)

| Capability | mem9.ai / Cloud Starter | Local tiup playground | SQLite (offline/test) |
|---|---|---|---|
| Relational + recursive CTE | ✅ | ✅ | ✅ |
| Cross-database JOIN (repo = db) | ✅ | ✅ | ✅ (via `ATTACH`) |
| Vector search | ✅ `EMBED_TEXT` auto-embed | ✅ precomputed (`fastembed`) | ❌ |
| Keyword search | ✅ full-text (`FTS_MATCH_WORD`) | ✅ `LIKE` boost | ✅ `LIKE` |
| Hybrid (RRF) | ✅ vector + full-text | ✅ vector + `LIKE` | ❌ (`LIKE` only) |

## Scenarios this plan must demonstrate

- **A. Single-repo:** an agent queries/writes only `acme_pulumi_kb`.
- **B. Cross-repo:** create an AWS account in LZA (`acme_lza_kb`), then an S3 bucket in that account in Pulumi (`acme_pulumi_kb`), reading/writing **both** databases over **one team connection** via a cross-database JOIN - no separate per-cluster auth.
- **C. Team isolation:** an agent authenticated to Team A's cluster has no query path to Team B's KB. A runnable script/runbook proves a cross-team read fails by design.

---

## File Structure

**New files**
- `src/topology.py` - team/repo registry, target detection (`cloud`/`local`/`sqlite`), capability flags, `database_for(repo, team)`.
- `src/embed.py` - local precomputed embeddings (`fastembed`) with a deterministic offline fallback; vector-literal formatting; per-target dims.
- `src/repos/__init__.py`, `src/repos/pulumi.py`, `src/repos/lza.py` - per-repo component manifests (the extractor's output for each synthetic repo).
- `src/ingest.py` - bootstrap/backfill: walk a repo manifest, chunk+embed, INSERT components + edges + log into the repo's database.
- `src/cross_repo_demo.py` - Scenario B: write LZA account + Pulumi bucket, run the cross-database JOIN.
- `src/isolation_check.py` - Scenario C: prove a cross-team read fails by design.
- `docs/MCP-GUIDE.md` - how to connect, deterministic per-repo routing, per-team auth.
- `requirements-local.txt` - heavy local-only deps (`fastembed`).
- `tests/` - pytest suite (`test_topology.py`, `test_embed.py`, `test_db_sql.py`, `test_db_sqlite.py`, `test_search.py`, `test_repos.py`, `test_ingest.py`, `test_cross_repo.py`, `test_isolation.py`, `test_mcp_server.py`, `conftest.py`).
- `lza/` - small synthetic LZA Pulumi source (`accounts.ts`, `ous.ts`) for realism; gitignored like `environments/`.

**Rewritten files**
- `src/db.py` - target-aware + repo-aware KB; pure SQL builders separated from execution.
- `src/seed.py` - seed two repos for team `acme` (full) + team `globex` (minimal, for isolation).
- `src/mcp_server.py` - repo-scoped server (`MEM9_REPO` env), cross-database reads, explicit per-repo identity in tool descriptions.
- `src/gen_configs.py` - one named server entry per repo database, creds scoped to one team cluster.
- `src/writeback.py` - add `--repo`.
- `dashboard/server.py` - repo-aware reads (defaults to the Pulumi repo; appendix view).
- `configs/claude-code/CLAUDE.md`, `configs/codex/AGENTS.md`, `configs/cursor/.cursorrules` - mem9 framing, lifecycle, explicit routing, eventual-consistency caveat.
- `configs/claude-code/mcp.json`, `configs/cursor/mcp.json`, `configs/codex/config.toml` - per-repo named server templates.
- `README.md`, `DEMO.md`, `PRESENTER.md`, `RECORDING.md`, `REHEARSE.md` - mem9 framing, model, lifecycle, scenarios A/B/C, dashboard → appendix.
- `.env.example`, `setup.sh`, `demo.sh`, `.gitignore`, `requirements.txt`, `pyproject.toml`.

**Design rules locked in**
- Every table reference is **fully qualified**: `{db}.infra_components` where `db = database_for(repo, team)` (e.g. `acme_pulumi_kb`). True on TiDB (`db.table` syntax) and SQLite (`ATTACH ... AS acme_pulumi_kb`).
- `infra_components` gains two columns: `repo` (provenance) and `account_ref` (cross-repo JOIN key).
- Recursive CTEs stay **within a single repo database**. Cross-repo relationships are expressed via the `account_ref` cross-database JOIN, not via cross-database recursion.
- Embedding dims are target-dependent: cloud `1024` (Titan), local `384` (bge-small). SQLite has no embedding.

---

## Task 0: Test harness, dependencies, gitignore

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-local.txt`
- Modify: `pyproject.toml`
- Modify: `.gitignore`
- Create: `tests/conftest.py`
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Add pytest to dev deps and pin runtime deps**

Replace the entire contents of `requirements.txt`:

```text
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
PyMySQL>=1.1.0
cryptography>=42.0.0
certifi>=2024.2.2
python-dotenv>=1.0.1
pytest>=8.0.0
```

- [ ] **Step 2: Create the local-only requirements file**

Create `requirements-local.txt` (only needed for the local tiup target's precomputed embeddings):

```text
# Local tiup-playground target only: client-side embeddings for vector search.
# Cloud (mem9.ai) embeds server-side with EMBED_TEXT and does NOT need this.
fastembed>=0.3.0
```

- [ ] **Step 3: Configure pytest pythonpath**

Replace the entire contents of `pyproject.toml`:

```toml
[project]
name = "mem9-ai-coding"
version = "0.3.0"
description = "mem9 - a database-held memory layer that Claude Code, Codex, and Cursor share across repos and teams"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "PyMySQL>=1.1.0",
    "python-dotenv>=1.0.1",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 4: Gitignore data dir and LZA source, keep secrets ignored**

Replace the entire contents of `.gitignore`:

```text
.venv/
node_modules/
__pycache__/
*.py[cod]
.env
kb.db
data/
.DS_Store

# generated MCP configs (contain TiDB secrets)
/.mcp.json
/.cursor/mcp.json
/configs/generated/
.fastembed_cache/
package.json
package-lock.json
environments/
lza/
.minimax/
```

- [ ] **Step 5: Create the test fixtures**

Create `tests/__init__.py` as an empty file.

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures. All tests run on the SQLite offline substrate
(no network, no creds) unless a test explicitly opts into a live target."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_env(tmp_path, monkeypatch):
    """Force the SQLite target with an isolated per-test data dir, and reload
    the topology + db modules so module-level state is re-evaluated."""
    monkeypatch.delenv("TIDB_HOST", raising=False)
    monkeypatch.delenv("MEM9_TARGET", raising=False)
    monkeypatch.setenv("MEM9_TEAM", "acme")
    monkeypatch.setenv("MEM9_DATA_DIR", str(tmp_path))

    import src.topology as topology
    import src.db as db
    importlib.reload(topology)
    importlib.reload(db)
    return db
```

- [ ] **Step 6: Run pytest to confirm the harness collects (zero tests yet)**

Run: `cd /Users/stephen/GitHub/mem9-ai-coding && .venv/bin/python -m pytest -q`
Expected: `no tests ran` (exit code 5) - harness is wired, no tests collected yet. (If `.venv` deps are stale, run `.venv/bin/pip install -r requirements.txt` first.)

- [ ] **Step 7: Commit**

```bash
git checkout -b mem9-team-repo-refactor
git add requirements.txt requirements-local.txt pyproject.toml .gitignore tests/
git commit -m "chore: add pytest harness, local-embed deps, data-dir gitignore"
```

---

## Task 1: Topology - team / repo / target / capabilities

**Files:**
- Create: `src/topology.py`
- Test: `tests/test_topology.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_topology.py`:

```python
import importlib

import pytest


def reload_topology(monkeypatch, **env):
    for k in ("TIDB_HOST", "MEM9_TARGET", "MEM9_TEAM"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.topology as topology
    importlib.reload(topology)
    return topology


def test_no_host_is_sqlite(monkeypatch):
    t = reload_topology(monkeypatch)
    assert t.target() == "sqlite"
    assert t.has_vector() is False
    assert t.has_fulltext() is False
    assert t.has_auto_embed() is False


def test_tidbcloud_host_is_cloud(monkeypatch):
    t = reload_topology(monkeypatch, TIDB_HOST="gateway01.eu-central-1.prod.aws.tidbcloud.com")
    assert t.target() == "cloud"
    assert t.has_vector() and t.has_fulltext() and t.has_auto_embed()


def test_localhost_host_is_local_tiup(monkeypatch):
    t = reload_topology(monkeypatch, TIDB_HOST="127.0.0.1")
    assert t.target() == "local"
    assert t.has_vector() is True
    assert t.has_fulltext() is False
    assert t.has_auto_embed() is False


def test_explicit_target_overrides_inference(monkeypatch):
    t = reload_topology(monkeypatch, TIDB_HOST="gateway01.prod.aws.tidbcloud.com", MEM9_TARGET="local")
    assert t.target() == "local"


def test_database_for_namespaces_by_team(monkeypatch):
    t = reload_topology(monkeypatch, MEM9_TEAM="acme")
    assert t.database_for("pulumi") == "acme_pulumi_kb"
    assert t.database_for("lza") == "acme_lza_kb"
    assert t.database_for("pulumi", team="globex") == "globex_pulumi_kb"


def test_unknown_repo_raises(monkeypatch):
    t = reload_topology(monkeypatch)
    with pytest.raises(KeyError):
        t.database_for("nope")


def test_repos_and_team_defaults(monkeypatch):
    t = reload_topology(monkeypatch)
    assert t.team() == "acme"
    assert set(t.repo_names()) == {"pulumi", "lza"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_topology.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.topology'`.

- [ ] **Step 3: Write the implementation**

Create `src/topology.py`:

```python
"""Team / repo / target topology for the mem9 knowledge base.

Model:
  team  -> a TiDB cluster in production; a database-name namespace in this demo.
  repo  -> a database inside the team's cluster (pulumi -> *_pulumi_kb, lza -> *_lza_kb).

Targets (capabilities differ; see capability matrix in README):
  cloud  - mem9.ai / TiDB Cloud Starter: EMBED_TEXT auto-embed + FULLTEXT + hybrid.
  local  - self-hosted tiup playground: vector (precomputed) + LIKE, no full-text.
  sqlite - offline/test substrate: relational + LIKE only, no vector.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=False)
except Exception:
    pass

# repo registry: logical repo -> (database stem, source dir, manifest module)
REPOS: dict[str, dict] = {
    "pulumi": {"db_stem": "pulumi_kb", "source": "environments", "manifest": "src.repos.pulumi"},
    "lza": {"db_stem": "lza_kb", "source": "lza", "manifest": "src.repos.lza"},
}


def team() -> str:
    return os.environ.get("MEM9_TEAM", "acme").strip().lower()


def repo_names() -> list[str]:
    return list(REPOS.keys())


def target() -> str:
    host = os.environ.get("TIDB_HOST", "").strip()
    if not host:
        return "sqlite"
    explicit = os.environ.get("MEM9_TARGET", "").strip().lower()
    if explicit in ("cloud", "local"):
        return explicit
    if "tidbcloud.com" in host or host.endswith(".mem9.ai"):
        return "cloud"
    return "local"


def has_vector() -> bool:
    return target() in ("cloud", "local")


def has_fulltext() -> bool:
    return target() == "cloud"


def has_auto_embed() -> bool:
    return target() == "cloud"


def database_for(repo: str, team_name: str | None = None) -> str:
    if repo not in REPOS:
        raise KeyError(f"unknown repo: {repo!r} (known: {list(REPOS)})")
    t = (team_name or team()).strip().lower()
    return f"{t}_{REPOS[repo]['db_stem']}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_topology.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/topology.py tests/test_topology.py
git commit -m "feat: add team/repo/target topology module"
```

---

## Task 2: Embeddings - precomputed local with deterministic offline fallback

**Files:**
- Create: `src/embed.py`
- Test: `tests/test_embed.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_embed.py`:

```python
from src import embed


def test_fallback_is_deterministic_and_right_length():
    a = embed.encode_one("acme-prod-static-assets S3 bucket")
    b = embed.encode_one("acme-prod-static-assets S3 bucket")
    assert a == b
    assert len(a) == embed.LOCAL_DIMS
    assert all(-1.0 <= x <= 1.0 for x in a)


def test_distinct_text_distinct_vector():
    assert embed.encode_one("alpha") != embed.encode_one("beta")


def test_to_literal_format():
    lit = embed.to_literal([0.5, -0.25, 0.0])
    assert lit == "[0.500000,-0.250000,0.000000]"


def test_dims_by_target():
    assert embed.dims("cloud") == embed.CLOUD_DIMS
    assert embed.dims("local") == embed.LOCAL_DIMS
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_embed.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.embed'`.

- [ ] **Step 3: Write the implementation**

Create `src/embed.py`:

```python
"""Client-side embeddings for the local tiup target.

Cloud (mem9.ai) embeds server-side with EMBED_TEXT and never calls this module.
Local uses fastembed when installed; otherwise a deterministic hash-based fallback
keeps the demo and the test suite runnable with no heavy dependency.
"""
from __future__ import annotations

import hashlib
import os

CLOUD_MODEL = "tidbcloud_free/amazon/titan-embed-text-v2"
CLOUD_DIMS = 1024

LOCAL_MODEL = os.environ.get("MEM9_LOCAL_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
LOCAL_DIMS = 384

_model = None


def dims(target: str) -> int:
    return CLOUD_DIMS if target == "cloud" else LOCAL_DIMS


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding(model_name=LOCAL_MODEL)
    return _model


def encode_one(text: str) -> list[float]:
    """Return a LOCAL_DIMS embedding for `text`. Uses fastembed if available,
    else a deterministic pseudo-embedding (offline/test safe)."""
    try:
        import fastembed  # noqa: F401
        vec = next(iter(_get_model().embed([text])))
        return [float(x) for x in vec]
    except Exception:
        return _fallback(text, LOCAL_DIMS)


def _fallback(text: str, n: int) -> list[float]:
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    counter = 0
    while len(out) < n:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for i in range(0, len(block), 4):
            if len(out) >= n:
                break
            raw = int.from_bytes(block[i:i + 4], "big") / 2**32
            out.append(round(raw * 2.0 - 1.0, 6))
        counter += 1
    return out


def to_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_embed.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/embed.py tests/test_embed.py
git commit -m "feat: add precomputed embeddings with deterministic offline fallback"
```

---

## Task 3: db.py - pure SQL builders (schema, insert, search, cross-repo)

This task introduces the **pure, target-aware SQL builders** into `src/db.py` so the cloud/local/sqlite differences are unit-testable with no database. Task 4 wires execution around them.

**Files:**
- Modify: `src/db.py` (add builder functions; existing execution stays for now)
- Test: `tests/test_db_sql.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_sql.py`:

```python
from src import db


def test_schema_cloud_has_vector_and_fulltext():
    stmts = db.schema_statements("cloud", "acme_pulumi_kb", dims=1024)
    joined = "\n".join(stmts)
    assert "acme_pulumi_kb.infra_components" in joined
    assert "VECTOR(1024)" in joined
    assert "FULLTEXT INDEX" in joined
    assert "repo" in joined and "account_ref" in joined


def test_schema_local_has_vector_no_fulltext():
    joined = "\n".join(db.schema_statements("local", "acme_pulumi_kb", dims=384))
    assert "VECTOR(384)" in joined
    assert "FULLTEXT" not in joined


def test_schema_sqlite_has_no_vector_no_fulltext():
    joined = "\n".join(db.schema_statements("sqlite", "acme_pulumi_kb", dims=384))
    assert "VECTOR" not in joined
    assert "FULLTEXT" not in joined
    assert "repo" in joined and "account_ref" in joined


def test_insert_component_sql_cloud_uses_embed_text():
    sql = db.insert_component_sql("cloud", "acme_pulumi_kb")
    assert "EMBED_TEXT(" in sql
    assert "acme_pulumi_kb.infra_components" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


def test_insert_component_sql_local_takes_vector_literal_param():
    sql = db.insert_component_sql("local", "acme_pulumi_kb")
    assert "EMBED_TEXT" not in sql
    assert "embedding" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


def test_insert_component_sql_sqlite_no_embedding():
    sql = db.insert_component_sql("sqlite", "acme_pulumi_kb")
    assert "embedding" not in sql
    assert "INSERT OR REPLACE" in sql


def test_keyword_search_sql_cloud_is_fulltext():
    sql = db.keyword_search_sql("cloud", "acme_pulumi_kb")
    assert "FTS_MATCH_WORD" in sql


def test_keyword_search_sql_local_is_like():
    sql = db.keyword_search_sql("local", "acme_pulumi_kb")
    assert "LIKE" in sql
    assert "FTS_MATCH_WORD" not in sql


def test_cross_repo_sql_joins_two_databases():
    sql = db.cross_repo_accounts_sql("acme_pulumi_kb", "acme_lza_kb")
    assert "acme_pulumi_kb.infra_components" in sql
    assert "acme_lza_kb.infra_components" in sql
    assert "account_ref" in sql
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db_sql.py -q`
Expected: FAIL - `AttributeError: module 'src.db' has no attribute 'schema_statements'`.

- [ ] **Step 3: Add the builder functions to `src/db.py`**

Open `src/db.py`. Replace the schema block (the `_SQLITE_SCHEMA`, `EMBED_MODEL`, `EMBED_DIMS`, and `_TIDB_SCHEMA` definitions, original lines 40-97) with this builder-based block:

```python
# ── Schema + SQL builders (pure, target-aware, fully qualified) ───────────────
#
# Every table reference is qualified with the repo's database name so the same
# query text runs on TiDB (db.table) and SQLite (ATTACH ... AS db).

from src import embed as _embed

EMBED_MODEL = _embed.CLOUD_MODEL


def _columns_common() -> str:
    return (
        "name VARCHAR(191) UNIQUE NOT NULL, "
        "component_type VARCHAR(48) NOT NULL, "
        "environment VARCHAR(48) NOT NULL, "
        "repo VARCHAR(32) NOT NULL, "
        "account_ref VARCHAR(64), "
        "repo_path VARCHAR(255), "
        "summary TEXT, "
        "code_excerpt TEXT, "
        "created_by VARCHAR(64) DEFAULT 'seed', "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
    )


def schema_statements(target: str, db_name: str, dims: int) -> list[str]:
    """DDL for one repo database on the given target."""
    if target == "sqlite":
        return [
            f"CREATE TABLE IF NOT EXISTS {db_name}.infra_components ("
            f"id INTEGER PRIMARY KEY AUTOINCREMENT, {_columns_common()})",
            f"CREATE TABLE IF NOT EXISTS {db_name}.component_edges ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, from_id INTEGER NOT NULL, "
            "to_id INTEGER NOT NULL, relationship TEXT NOT NULL, note TEXT)",
            f"CREATE TABLE IF NOT EXISTS {db_name}.session_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, developer TEXT NOT NULL, "
            "action TEXT NOT NULL, detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
        ]

    extras = [
        f"id BIGINT PRIMARY KEY AUTO_INCREMENT, {_columns_common()}, "
        f"embedding VECTOR({dims}), "
        "VECTOR INDEX ((VEC_COSINE_DISTANCE(embedding)))",
    ]
    if target == "cloud":
        extras.append("FULLTEXT INDEX (summary) WITH PARSER MULTILINGUAL")
    comp = f"CREATE TABLE IF NOT EXISTS {db_name}.infra_components ({', '.join(extras)})"
    return [
        comp,
        f"CREATE TABLE IF NOT EXISTS {db_name}.component_edges ("
        "id BIGINT PRIMARY KEY AUTO_INCREMENT, from_id BIGINT NOT NULL, "
        "to_id BIGINT NOT NULL, relationship VARCHAR(48) NOT NULL, note VARCHAR(255))",
        f"CREATE TABLE IF NOT EXISTS {db_name}.session_log ("
        "id BIGINT PRIMARY KEY AUTO_INCREMENT, developer VARCHAR(64) NOT NULL, "
        "action VARCHAR(48) NOT NULL, detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)",
    ]


_INSERT_COLS = "name, component_type, environment, repo, account_ref, repo_path, summary, code_excerpt, created_by"


def insert_component_sql(target: str, db_name: str) -> str:
    """Insert/upsert one component. Placeholders authored with ? (translated for TiDB)."""
    table = f"{db_name}.infra_components"
    if target == "cloud":
        return (
            f"INSERT INTO {table} ({_INSERT_COLS}, embedding) "
            "VALUES (?,?,?,?,?,?,?,?,?, EMBED_TEXT(?, ?)) "
            "ON DUPLICATE KEY UPDATE component_type=VALUES(component_type), "
            "environment=VALUES(environment), repo=VALUES(repo), account_ref=VALUES(account_ref), "
            "repo_path=VALUES(repo_path), summary=VALUES(summary), code_excerpt=VALUES(code_excerpt), "
            "created_by=VALUES(created_by), embedding=VALUES(embedding)"
        )
    if target == "local":
        return (
            f"INSERT INTO {table} ({_INSERT_COLS}, embedding) "
            "VALUES (?,?,?,?,?,?,?,?,?, ?) "
            "ON DUPLICATE KEY UPDATE component_type=VALUES(component_type), "
            "environment=VALUES(environment), repo=VALUES(repo), account_ref=VALUES(account_ref), "
            "repo_path=VALUES(repo_path), summary=VALUES(summary), code_excerpt=VALUES(code_excerpt), "
            "created_by=VALUES(created_by), embedding=VALUES(embedding)"
        )
    return (
        f"INSERT OR REPLACE INTO {table} ({_INSERT_COLS}) "
        "VALUES (?,?,?,?,?,?,?,?,?)"
    )


def keyword_search_sql(target: str, db_name: str) -> str:
    table = f"{db_name}.infra_components"
    if target == "cloud":
        return (
            f"SELECT name, component_type, environment, repo, summary "
            f"FROM {table} WHERE FTS_MATCH_WORD(?, summary) "
            "ORDER BY FTS_MATCH_WORD(?, summary) DESC LIMIT ?"
        )
    return (
        f"SELECT name, component_type, environment, repo, summary "
        f"FROM {table} WHERE LOWER(summary) LIKE ? OR LOWER(name) LIKE ? "
        "LIMIT ?"
    )


def cross_repo_accounts_sql(pulumi_db: str, lza_db: str) -> str:
    """Scenario B: which Pulumi resources live in which LZA account (one cross-db JOIN)."""
    return (
        "SELECT p.name AS pulumi_component, p.component_type AS pulumi_type, "
        "p.account_ref, a.name AS lza_account, a.summary AS account_summary "
        f"FROM {pulumi_db}.infra_components p "
        f"JOIN {lza_db}.infra_components a "
        "  ON a.account_ref = p.account_ref AND a.component_type = 'Account' "
        "WHERE p.account_ref IS NOT NULL "
        "ORDER BY p.account_ref, p.name"
    )
```

Then delete the now-unused `EMBED_DIMS` references and the old `_default_ca`/connection code only if they reference removed names - they do not, so leave the rest of the file for Task 4.

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db_sql.py -q`
Expected: PASS (9 passed). (Other db tests may fail until Task 4 - that is expected; run only this file.)

- [ ] **Step 5: Commit**

```bash
git add src/db.py tests/test_db_sql.py
git commit -m "feat: add target-aware SQL builders to db.py"
```

---

## Task 4: db.py - repo-aware execution (connections, init/reset, query, write)

Rewrites the execution half of `src/db.py` around the Task 3 builders. SQLite uses an in-memory main connection with one ATTACHed file per team repo, so every query is fully qualified exactly like TiDB.

**Files:**
- Modify: `src/db.py` (connection + lifecycle + reads + writes + CTEs)
- Test: `tests/test_db_sqlite.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_db_sqlite.py`:

```python
def test_init_and_write_single_repo(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(
        repo="pulumi", name="acme-prod-x", type="S3", env="production",
        summary="x bucket", developer="claude-code", depends_on=None, account_ref="prod",
    )
    rows = db.query(f"SELECT name, repo, account_ref FROM {db.tref('pulumi','infra_components')}")
    assert any(r["name"] == "acme-prod-x" and r["repo"] == "pulumi" for r in rows)


def test_edge_and_session_log_written(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(repo="pulumi", name="S3Bucket", type="Library", env="library",
                       summary="lib", developer="seed")
    db.write_component(repo="pulumi", name="acme-prod-y", type="S3", env="production",
                       summary="y", developer="claude-code", depends_on="S3Bucket")
    edges = db.query(f"SELECT relationship FROM {db.tref('pulumi','component_edges')}")
    assert any(e["relationship"] == "uses" for e in edges)
    log = db.query(f"SELECT action FROM {db.tref('pulumi','session_log')}")
    assert any(r["action"] == "created" for r in log)


def test_cross_repo_join(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(repo="lza", name="acme-lza-account-prod", type="Account", env="org",
                       summary="prod account", developer="seed", account_ref="prod")
    db.write_component(repo="pulumi", name="acme-prod-exports", type="S3", env="production",
                       summary="exports", developer="seed", account_ref="prod")
    sql = db.cross_repo_accounts_sql(db.database_for("pulumi"), db.database_for("lza"))
    rows = db.query(sql)
    assert rows and rows[0]["pulumi_component"] == "acme-prod-exports"
    assert rows[0]["lza_account"] == "acme-lza-account-prod"


def test_blast_radius_cte_single_repo(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(repo="pulumi", name="S3Bucket", type="Library", env="library",
                       summary="lib", developer="seed")
    db.write_component(repo="pulumi", name="acme-prod-exports", type="S3", env="production",
                       summary="exports", developer="seed", depends_on="S3Bucket")
    out = db.cte_blast_radius("pulumi", "S3Bucket")
    assert "acme-prod-exports" in out["nodes"]
    assert "WITH RECURSIVE" in out["sql"]


def test_query_rejects_non_select(sqlite_env):
    db = sqlite_env
    db.init_db()
    import pytest
    with pytest.raises(ValueError):
        db.query("DELETE FROM acme_pulumi_kb.infra_components")


def test_backend_name_mentions_sqlite(sqlite_env):
    assert "SQLite" in sqlite_env.backend_name()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db_sqlite.py -q`
Expected: FAIL - `write_component()` got an unexpected keyword `repo` / `tref` missing.

- [ ] **Step 3: Rewrite the execution half of `src/db.py`**

Replace everything in `src/db.py` **from the module docstring through the end of the `log_query` function** (original lines 1-305, i.e. the top of file down to just before `# ── Recursive CTE traversals`) with the following. Keep the Task-3 builders (`schema_statements`, `insert_component_sql`, `keyword_search_sql`, `cross_repo_accounts_sql`, `_columns_common`, `_INSERT_COLS`, `EMBED_MODEL`, `_embed` import) - they live in the middle of the file; re-paste them where indicated.

```python
"""mem9 knowledge base - target-aware, repo-aware.

Targets (see src/topology.py): cloud (mem9.ai), local (tiup), sqlite (offline/test).
Every table reference is fully qualified `{db}.table` where db = topology.database_for(repo).
On TiDB this is native cross-database syntax; on SQLite we ATTACH one file per repo
under the same logical name, so identical SQL runs on both.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src import embed as _embed
from src import topology

EMBED_MODEL = _embed.CLOUD_MODEL


def _data_dir() -> Path:
    d = Path(os.environ.get("MEM9_DATA_DIR", str(Path(__file__).parent.parent / "data")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def target() -> str:
    return topology.target()


def team() -> str:
    return topology.team()


def database_for(repo: str, team_name: str | None = None) -> str:
    return topology.database_for(repo, team_name)


def tref(repo: str, table: str, team_name: str | None = None) -> str:
    return f"{database_for(repo, team_name)}.{table}"


def backend_name() -> str:
    t = target()
    if t == "cloud":
        return "mem9.ai (TiDB Cloud)"
    if t == "local":
        return "TiDB (self-hosted tiup playground)"
    return "SQLite (offline / test substrate)"


def using_tidb() -> bool:
    return target() in ("cloud", "local")
```

Now **re-paste the Task-3 builder block here** (the `_columns_common`, `schema_statements`, `_INSERT_COLS`, `insert_component_sql`, `keyword_search_sql`, `cross_repo_accounts_sql` functions exactly as written in Task 3 Step 3, minus the duplicate `from src import embed as _embed` / `EMBED_MODEL` lines which are now above).

Then continue with the connection + lifecycle + reads + writes:

```python
# ── Connections ───────────────────────────────────────────────────────────────

def _sqlite_paths(team_name: str, repos: list[str]) -> dict[str, Path]:
    return {database_for(r, team_name): _data_dir() / f"{database_for(r, team_name)}.db" for r in repos}


@contextmanager
def _sqlite_conn(team_name: str, repos: list[str]):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    for dbname, path in _sqlite_paths(team_name, repos).items():
        con.execute("ATTACH DATABASE ? AS " + dbname, (str(path),))
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _default_ca() -> str | None:
    try:
        import certifi
        return certifi.where()
    except Exception:
        for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
            if Path(p).exists():
                return p
    return None


@contextmanager
def _tidb_conn(team_name: str, repos: list[str]):
    import pymysql
    con = pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.environ.get("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USERNAME"],
        password=os.environ.get("TIDB_PASSWORD", ""),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        ssl={"ca": os.environ.get("TIDB_CA_PATH") or _default_ca()},
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        cur = con.cursor()
        for r in repos:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS {database_for(r, team_name)}")
        yield con
        con.commit()
    finally:
        con.close()


@contextmanager
def _conn(repos: list[str] | None = None, team_name: str | None = None):
    team_name = team_name or team()
    repos = repos or topology.repo_names()
    if using_tidb():
        with _tidb_conn(team_name, repos) as c:
            yield c
    else:
        with _sqlite_conn(team_name, repos) as c:
            yield c


def _ph(sql: str) -> str:
    return sql if not using_tidb() else sql.replace("?", "%s")


def _run(con, sql: str, params: tuple = ()):
    if using_tidb():
        cur = con.cursor()
        cur.execute(_ph(sql), params) if params else cur.execute(sql)
        return cur
    return con.execute(sql, params) if params else con.execute(sql)


def _rows(cur) -> list[dict]:
    import datetime as _dt
    rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        for k, v in row.items():
            if isinstance(v, (_dt.datetime, _dt.date)):
                row[k] = v.isoformat(sep=" ")
    return rows


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def init_db(team_name: str | None = None, repos: list[str] | None = None) -> None:
    team_name = team_name or team()
    repos = repos or topology.repo_names()
    dims = _embed.dims(target())
    with _conn(repos, team_name) as con:
        for r in repos:
            for stmt in schema_statements(target(), database_for(r, team_name), dims):
                _run(con, stmt)


def reset_db(team_name: str | None = None, repos: list[str] | None = None) -> None:
    team_name = team_name or team()
    repos = repos or topology.repo_names()
    if using_tidb():
        with _conn(repos, team_name) as con:
            for r in repos:
                db_name = database_for(r, team_name)
                for t in ("component_edges", "session_log", "infra_components"):
                    _run(con, f"DROP TABLE IF EXISTS {db_name}.{t}")
    else:
        for path in _sqlite_paths(team_name, repos).values():
            if path.exists():
                path.unlink()
    init_db(team_name, repos)


# ── Reads ───────────────────────────────────────────────────────────────────

def query(sql: str, team_name: str | None = None, repos: list[str] | None = None) -> list[dict]:
    meaningful = [ln for ln in sql.strip().splitlines()
                  if ln.strip() and not ln.strip().startswith("--")]
    head = meaningful[0].upper() if meaningful else ""
    if not head.startswith("SELECT") and not head.startswith("WITH"):
        raise ValueError("Only SELECT / WITH queries are allowed via query()")
    with _conn(repos, team_name) as con:
        return _rows(_run(con, sql))


# ── Writes ───────────────────────────────────────────────────────────────────

def write_component(
    *, repo: str, name: str, type: str, env: str, summary: str,
    depends_on: str | None = None, relationship: str = "uses",
    developer: str, repo_path: str | None = None, code_excerpt: str | None = None,
    account_ref: str | None = None, team_name: str | None = None,
) -> int:
    team_name = team_name or team()
    db_name = database_for(repo, team_name)
    comp_table = f"{db_name}.infra_components"
    with _conn([repo], team_name) as con:
        sql = insert_component_sql(target(), db_name)
        base = (name, type, env, repo, account_ref, repo_path, summary, code_excerpt, developer)
        if target() == "cloud":
            embed_text = f"{name} - {type} in {env}. {summary}"
            cur = _run(con, sql, base + (EMBED_MODEL, embed_text))
        elif target() == "local":
            embed_text = f"{name} - {type} in {env}. {summary}"
            literal = _embed.to_literal(_embed.encode_one(embed_text))
            cur = _run(con, sql, base + (literal,))
        else:
            cur = _run(con, sql, base)

        row = _rows(_run(con, f"SELECT id FROM {comp_table} WHERE name=?", (name,)))
        comp_id = row[0]["id"] if row else cur.lastrowid

        if depends_on:
            dep = _rows(_run(con, f"SELECT id FROM {comp_table} WHERE name=?", (depends_on,)))
            if dep:
                _run(con, f"INSERT INTO {db_name}.component_edges (from_id, to_id, relationship, note) VALUES (?,?,?,?)",
                     (comp_id, dep[0]["id"], relationship, f"{name} {relationship} {depends_on}"))

        _run(con, f"INSERT INTO {db_name}.session_log (developer, action, detail) VALUES (?,?,?)",
             (developer, "created", f"Created {type} component '{name}' in {env}"))
        return comp_id


def write_edge(repo: str, from_name: str, to_name: str, relationship: str, note: str = "",
               team_name: str | None = None) -> None:
    team_name = team_name or team()
    db_name = database_for(repo, team_name)
    comp_table = f"{db_name}.infra_components"
    with _conn([repo], team_name) as con:
        f = _rows(_run(con, f"SELECT id FROM {comp_table} WHERE name=?", (from_name,)))
        t = _rows(_run(con, f"SELECT id FROM {comp_table} WHERE name=?", (to_name,)))
        if f and t:
            _run(con, f"INSERT INTO {db_name}.component_edges (from_id, to_id, relationship, note) VALUES (?,?,?,?)",
                 (f[0]["id"], t[0]["id"], relationship, note))


def log(repo: str, developer: str, action: str, detail: str, team_name: str | None = None) -> None:
    team_name = team_name or team()
    db_name = database_for(repo, team_name)
    with _conn([repo], team_name) as con:
        _run(con, f"INSERT INTO {db_name}.session_log (developer, action, detail) VALUES (?,?,?)",
             (developer, action, detail))


def log_query(repo: str, developer: str, detail: str, team_name: str | None = None) -> None:
    log(repo, developer, "queried", detail, team_name)
```

- [ ] **Step 4: Replace the recursive-CTE traversal section to be repo-scoped**

In `src/db.py`, replace the existing `# ── Recursive CTE traversals` section (the `CTE_DEPENDENCIES_SQL`, `CTE_BLAST_RADIUS_SQL` constants and `_resolve`, `cte_dependencies`, `cte_blast_radius`, `_nodes_in` functions) with this repo-scoped version:

```python
# ── Recursive CTE traversals (single-repo; identical SQL on TiDB + SQLite) ────

def _cte_dependencies_sql(db_name: str, name: str) -> str:
    c = f"{db_name}.infra_components"
    e = f"{db_name}.component_edges"
    return (
        f"-- What does '{name}' transitively depend on? (repo: {db_name})\n"
        "WITH RECURSIVE deps(from_id, to_id, relationship, depth) AS (\n"
        f"    SELECT e.from_id, e.to_id, e.relationship, 1 FROM {e} e\n"
        f"    JOIN {c} c ON e.from_id = c.id WHERE c.name = '{name}'\n"
        "  UNION ALL\n"
        f"    SELECT e.from_id, e.to_id, e.relationship, d.depth + 1 FROM {e} e\n"
        "    JOIN deps d ON e.from_id = d.to_id WHERE d.depth < 10\n"
        ")\n"
        "SELECT DISTINCT d.depth, cf.name AS from_name, d.relationship, ct.name AS to_name,\n"
        "       ct.component_type, ct.environment\n"
        f"FROM deps d JOIN {c} cf ON d.from_id = cf.id JOIN {c} ct ON d.to_id = ct.id\n"
        "ORDER BY d.depth, to_name;"
    )


def _cte_blast_radius_sql(db_name: str, name: str) -> str:
    c = f"{db_name}.infra_components"
    e = f"{db_name}.component_edges"
    return (
        f"-- What breaks if '{name}' changes? (repo: {db_name})\n"
        "WITH RECURSIVE blast(from_id, to_id, relationship, depth) AS (\n"
        f"    SELECT e.from_id, e.to_id, e.relationship, 1 FROM {e} e\n"
        f"    JOIN {c} c ON e.to_id = c.id WHERE c.name = '{name}'\n"
        "  UNION ALL\n"
        f"    SELECT e.from_id, e.to_id, e.relationship, b.depth + 1 FROM {e} e\n"
        "    JOIN blast b ON e.to_id = b.from_id WHERE b.depth < 10\n"
        ")\n"
        "SELECT DISTINCT b.depth, cf.name AS from_name, b.relationship, ct.name AS to_name,\n"
        "       cf.component_type, cf.environment\n"
        f"FROM blast b JOIN {c} cf ON b.from_id = cf.id JOIN {c} ct ON b.to_id = ct.id\n"
        "ORDER BY b.depth, from_name;"
    )


def _resolve(name: str) -> str:
    return name.replace("'", "").strip()


def cte_dependencies(repo: str, name: str, team_name: str | None = None) -> dict:
    safe = _resolve(name)
    sql = _cte_dependencies_sql(database_for(repo, team_name), safe)
    rows = query(sql, team_name, [repo])
    return {"sql": sql, "rows": rows, "nodes": _nodes_in(rows, safe)}


def cte_blast_radius(repo: str, name: str, team_name: str | None = None) -> dict:
    safe = _resolve(name)
    sql = _cte_blast_radius_sql(database_for(repo, team_name), safe)
    rows = query(sql, team_name, [repo])
    return {"sql": sql, "rows": rows, "nodes": _nodes_in(rows, safe)}


def _nodes_in(rows: list[dict], root: str) -> list[str]:
    names = {root}
    for r in rows:
        names.add(r["from_name"]); names.add(r["to_name"])
    return sorted(names)
```

- [ ] **Step 5: Replace the search section to be repo-scoped and target-aware**

In `src/db.py`, replace the entire `# ── Vector + full-text + hybrid search` section (from `def search_available` through the end of `def search`) with:

```python
# ── Search: cloud = vector + full-text + RRF; local = vector + LIKE + RRF; sqlite = LIKE ─

def search_available() -> bool:
    return True


def _vector_search(con, db_name: str, q: str, k: int) -> list[dict]:
    table = f"{db_name}.infra_components"
    if target() == "cloud":
        cur = _run(con,
            f"SELECT name, component_type, environment, repo, summary, "
            f"VEC_COSINE_DISTANCE(embedding, EMBED_TEXT(?, ?)) AS distance "
            f"FROM {table} WHERE embedding IS NOT NULL ORDER BY distance LIMIT ?",
            (EMBED_MODEL, q, k))
        return _rows(cur)
    literal = _embed.to_literal(_embed.encode_one(q))
    cur = _run(con,
        f"SELECT name, component_type, environment, repo, summary, "
        f"VEC_COSINE_DISTANCE(embedding, ?) AS distance "
        f"FROM {table} WHERE embedding IS NOT NULL ORDER BY distance LIMIT ?",
        (literal, k))
    return _rows(cur)


def _keyword_search(con, db_name: str, q: str, k: int) -> list[dict]:
    sql = keyword_search_sql(target(), db_name)
    if target() == "cloud":
        return _rows(_run(con, sql, (q, q, k)))
    like = f"%{q.lower()}%"
    return _rows(_run(con, sql, (like, like, k)))


def search(repo: str, q: str, mode: str = "hybrid", k: int = 6, team_name: str | None = None) -> dict:
    db_name = database_for(repo, team_name)
    qsafe = q.replace("'", "")
    note = ("Hybrid = vector + full-text (RRF)." if target() == "cloud"
            else "Vector + LIKE keyword boost (RRF)." if target() == "local"
            else "LIKE keyword search only (no vector on SQLite).")
    pool = 10
    with _conn([repo], team_name) as con:
        kw = _keyword_search(con, db_name, qsafe, pool)
        vec = _vector_search(con, db_name, qsafe, pool) if topology.has_vector() else []

    kw_rank = {r["name"]: i for i, r in enumerate(kw)}
    vec_rank = {r["name"]: i for i, r in enumerate(vec)}
    by_name = {r["name"]: r for r in vec}
    for r in kw:
        by_name.setdefault(r["name"], r)

    C = 60
    rows = []
    for name, base in by_name.items():
        vr, kr = vec_rank.get(name), kw_rank.get(name)
        rrf = (1.0 / (C + vr) if vr is not None else 0.0) + (1.0 / (C + kr) if kr is not None else 0.0)
        rows.append({
            "name": name, "component_type": base["component_type"],
            "environment": base["environment"], "repo": base.get("repo", repo),
            "summary": base.get("summary", ""),
            "distance": next((v["distance"] for v in vec if v["name"] == name), None),
            "in_vector": vr is not None, "in_keyword": kr is not None,
            "hybrid_score": round(rrf, 5),
        })

    if mode == "vector" and topology.has_vector():
        rows = [r for r in rows if r["in_vector"]]
        rows.sort(key=lambda r: (r["distance"] if r["distance"] is not None else 9))
    elif mode in ("fts", "keyword") or (mode == "vector" and not topology.has_vector()):
        rows = [r for r in rows if r["in_keyword"]]
        rows.sort(key=lambda r: kw_rank.get(r["name"], 999))
    else:
        rows.sort(key=lambda r: -r["hybrid_score"])

    return {"available": True, "mode": mode, "target": target(), "note": note, "results": rows[:k]}
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db_sqlite.py tests/test_db_sql.py -q`
Expected: PASS (all). If `ATTACH DATABASE ? AS name` errors on the running SQLite, confirm Python's sqlite3 supports parameterized ATTACH (it does on 3.11+); the schema name is interpolated, the path is bound.

- [ ] **Step 7: Commit**

```bash
git add src/db.py tests/test_db_sqlite.py
git commit -m "feat: repo-aware, target-aware db execution (team=cluster, repo=database)"
```

---

## Task 5: Search behavior tests (SQLite LIKE path)

**Files:**
- Test: `tests/test_search.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_search.py`:

```python
def _seed(db):
    db.init_db()
    db.write_component(repo="pulumi", name="acme-prod-static-assets", type="S3", env="production",
                       summary="CDN static assets bucket fronted by Cloudflare", developer="seed")
    db.write_component(repo="pulumi", name="acme-prod-analytics-db", type="RDS", env="production",
                       summary="analytics postgres database", developer="seed")


def test_like_search_matches_keyword(sqlite_env):
    db = sqlite_env
    _seed(db)
    out = db.search("pulumi", "static assets", mode="keyword")
    assert out["target"] == "sqlite"
    names = [r["name"] for r in out["results"]]
    assert "acme-prod-static-assets" in names


def test_hybrid_on_sqlite_degrades_to_like(sqlite_env):
    db = sqlite_env
    _seed(db)
    out = db.search("pulumi", "analytics", mode="hybrid")
    assert "LIKE" in out["note"]
    assert any(r["name"] == "acme-prod-analytics-db" for r in out["results"])
```

- [ ] **Step 2: Run the test to verify it fails, then passes**

Run: `.venv/bin/python -m pytest tests/test_search.py -q`
Expected: PASS already (Task 4 implemented `search`). If it fails on the `note` string, align with the strings in `search()`. This task exists to lock search behavior; if green on first run, proceed to commit.

- [ ] **Step 3: Commit**

```bash
git add tests/test_search.py
git commit -m "test: lock SQLite LIKE search + hybrid degradation behavior"
```

---

## Task 6: Per-repo component manifests (the extractor output)

**Files:**
- Create: `src/repos/__init__.py`
- Create: `src/repos/pulumi.py`
- Create: `src/repos/lza.py`
- Test: `tests/test_repos.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_repos.py`:

```python
from src.repos import pulumi, lza, load_manifest


def test_pulumi_has_libraries_and_staging_gap():
    names = {c["name"] for c in pulumi.COMPONENTS}
    assert {"S3Bucket", "PostgresDatabase", "DnsRecord", "SsoApplication"} <= names
    staging = {c["name"] for c in pulumi.COMPONENTS if c["env"] == "staging"}
    assert "acme-staging-data-exports" in staging
    assert "acme-staging-admin-sso" not in staging  # the demo gap


def test_lza_has_accounts_with_account_ref():
    accounts = [c for c in lza.COMPONENTS if c["type"] == "Account"]
    refs = {c["account_ref"] for c in accounts}
    assert {"prod", "sandbox"} <= refs


def test_load_manifest_by_name():
    assert load_manifest("pulumi") is pulumi.COMPONENTS
    assert load_manifest("lza") is lza.COMPONENTS


def test_every_component_has_required_keys():
    for mod in (pulumi, lza):
        for c in mod.COMPONENTS:
            assert {"name", "type", "env", "summary", "repo"} <= set(c)
            assert c["repo"] == mod.REPO
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_repos.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.repos'`.

- [ ] **Step 3: Create the package loader**

Create `src/repos/__init__.py`:

```python
"""Per-repo component manifests: the extractor's output for each synthetic repo.

In production, `src/ingest.py` would walk the repo source (TypeScript) and emit
these dicts. For the demo the extracted result is checked in as data so bootstrap
is deterministic and reviewable.
"""
from __future__ import annotations

import importlib

from src import topology


def load_manifest(repo: str) -> list[dict]:
    module = importlib.import_module(topology.REPOS[repo]["manifest"])
    return module.COMPONENTS
```

- [ ] **Step 4: Create the Pulumi manifest**

Create `src/repos/pulumi.py`:

```python
"""Pulumi infra-as-code repo manifest (repo = pulumi -> *_pulumi_kb).

Mirrors the original Acme scenario: 4 libraries, full production, staging missing
its DNS + SSO layer (the live-demo task). account_ref maps each resource to an LZA
account so cross-repo JOINs work (prod -> 'prod', staging -> 'sandbox')."""
from __future__ import annotations

REPO = "pulumi"

COMPONENTS = [
    # ── Libraries ──
    {"name": "S3Bucket", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/s3-bucket/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable S3 bucket component. Enforces versioning, encryption at rest, "
                "lifecycle rules, required tags. Physical name acme-<env>-<logical>.",
     "code_excerpt": "export class S3Bucket extends pulumi.ComponentResource { /* tags, encryption */ }"},
    {"name": "PostgresDatabase", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/postgres-db/index.ts", "account_ref": None,
     "depends_on": "S3Bucket", "relationship": "instantiates",
     "summary": "Reusable RDS Postgres component. Automatically instantiates an S3Bucket for "
                "backups - do NOT create a backup bucket manually. Multi-AZ in prod, single-AZ staging.",
     "code_excerpt": "this.backupBucket = new S3Bucket(`${name}-backup`, ...);"},
    {"name": "DnsRecord", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/dns-record/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable Cloudflare DNS record. Always proxied (orange cloud). All new public "
                "endpoints must use this component.",
     "code_excerpt": "// proxied: true always - never set proxied: false"},
    {"name": "SsoApplication", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "libs/sso-app/index.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable Okta SSO application. Redirect URIs must point at the corresponding "
                "DnsRecord hostname. Used for all internal services requiring SSO.",
     "code_excerpt": "// redirectUris must point at a DnsRecord hostname"},

    # ── Production (account_ref = prod) ──
    {"name": "acme-prod-analytics-db", "type": "RDS", "env": "production", "repo": REPO,
     "repo_path": "environments/production/analytics.ts", "account_ref": "prod",
     "depends_on": "PostgresDatabase",
     "summary": "Production analytics Postgres (multi-AZ). Composes PostgresDatabase; backup bucket auto-created."},
    {"name": "acme-prod-data-exports", "type": "S3", "env": "production", "repo": REPO,
     "repo_path": "environments/production/storage.ts", "account_ref": "prod",
     "depends_on": "S3Bucket", "summary": "Production data exports bucket. Composes S3Bucket."},
    {"name": "acme-prod-static-assets", "type": "S3", "env": "production", "repo": REPO,
     "repo_path": "environments/production/storage.ts", "account_ref": "prod",
     "depends_on": "S3Bucket", "summary": "Production static assets bucket. Fronted by acme-prod-assets-dns (CDN)."},
    {"name": "acme-prod-assets-dns", "type": "Cloudflare", "env": "production", "repo": REPO,
     "repo_path": "environments/production/dns.ts", "account_ref": "prod",
     "depends_on": "DnsRecord", "summary": "Cloudflare DNS fronting acme-prod-static-assets. Proxied: true."},
    {"name": "acme-prod-admin-dns", "type": "Cloudflare", "env": "production", "repo": REPO,
     "repo_path": "environments/production/dns.ts", "account_ref": "prod",
     "depends_on": "DnsRecord", "summary": "Cloudflare DNS for the admin portal. acme-prod-admin-sso redirects here."},
    {"name": "acme-prod-admin-sso", "type": "Okta", "env": "production", "repo": REPO,
     "repo_path": "environments/production/sso.ts", "account_ref": "prod",
     "depends_on": "SsoApplication", "summary": "Okta SSO for admin portal. Redirect URI points at acme-prod-admin-dns."},

    # ── Staging (account_ref = sandbox) - DNS + SSO intentionally missing ──
    {"name": "acme-staging-analytics-db", "type": "RDS", "env": "staging", "repo": REPO,
     "repo_path": "environments/staging/analytics.ts", "account_ref": "sandbox",
     "depends_on": "PostgresDatabase", "summary": "Staging analytics Postgres (single-AZ). Composes PostgresDatabase."},
    {"name": "acme-staging-data-exports", "type": "S3", "env": "staging", "repo": REPO,
     "repo_path": "environments/staging/storage.ts", "account_ref": "sandbox",
     "depends_on": "S3Bucket", "summary": "Staging data exports bucket. Composes S3Bucket."},
]

# Extra composition edges (beyond depends_on) applied after all components exist.
EDGES = [
    ("acme-prod-assets-dns", "acme-prod-static-assets", "fronts",
     "CDN DNS record proxies to the static assets bucket"),
    ("acme-prod-admin-sso", "acme-prod-admin-dns", "redirects_to",
     "Okta redirect URI points at the admin DNS hostname"),
]
```

- [ ] **Step 5: Create the LZA manifest**

Create `src/repos/lza.py`:

```python
"""AWS Landing Zone Accelerator repo manifest (repo = lza -> *_lza_kb).

Models the org/account layer: an OU, AWS accounts (account_ref is the join key
to Pulumi resources), an SCP, and an IAM baseline."""
from __future__ import annotations

REPO = "lza"

COMPONENTS = [
    # ── Libraries ──
    {"name": "AwsAccount", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/aws-account.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable AWS account factory. Creates an account inside an OrganizationalUnit, "
                "applies the IAM baseline and required SCPs. Account alias acme-<account_ref>."},
    {"name": "OrganizationalUnit", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/ou.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable AWS Organizations OU. Groups accounts and is the attach point for SCPs."},
    {"name": "ScpPolicy", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/scp.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable Service Control Policy. Attached to an OU; constrains every account beneath it."},
    {"name": "IamBaseline", "type": "Library", "env": "library", "repo": REPO,
     "repo_path": "lza/libs/iam-baseline.ts", "account_ref": None, "depends_on": None,
     "summary": "Reusable IAM baseline (roles, password policy, CloudTrail) applied to every new account."},

    # ── Org instances ──
    {"name": "acme-lza-ou-workloads", "type": "OU", "env": "org", "repo": REPO,
     "repo_path": "lza/ous.ts", "account_ref": None, "depends_on": "OrganizationalUnit",
     "summary": "Workloads OU. Parent of the prod and sandbox accounts; SCP deny-root attached."},
    {"name": "acme-lza-scp-deny-root", "type": "SCP", "env": "org", "repo": REPO,
     "repo_path": "lza/ous.ts", "account_ref": None, "depends_on": "ScpPolicy",
     "summary": "SCP denying root-user actions, attached to the workloads OU."},
    {"name": "acme-lza-account-prod", "type": "Account", "env": "org", "repo": REPO,
     "repo_path": "lza/accounts.ts", "account_ref": "prod", "depends_on": "AwsAccount",
     "summary": "Production AWS account (account_ref=prod) in the workloads OU. Hosts acme-prod-* resources."},
    {"name": "acme-lza-account-sandbox", "type": "Account", "env": "org", "repo": REPO,
     "repo_path": "lza/accounts.ts", "account_ref": "sandbox", "depends_on": "AwsAccount",
     "summary": "Sandbox AWS account (account_ref=sandbox) in the workloads OU. Hosts acme-staging-* resources."},
    {"name": "acme-lza-iam-baseline", "type": "IAM", "env": "org", "repo": REPO,
     "repo_path": "lza/accounts.ts", "account_ref": None, "depends_on": "IamBaseline",
     "summary": "Org-wide IAM baseline applied to every account by the AwsAccount factory."},
]

EDGES = [
    ("acme-lza-account-prod", "acme-lza-ou-workloads", "belongs_to", "prod account lives in the workloads OU"),
    ("acme-lza-account-sandbox", "acme-lza-ou-workloads", "belongs_to", "sandbox account lives in the workloads OU"),
    ("acme-lza-scp-deny-root", "acme-lza-ou-workloads", "attached_to", "deny-root SCP is attached to the workloads OU"),
]
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_repos.py -q`
Expected: PASS (4 passed).

- [ ] **Step 7: Commit**

```bash
git add src/repos/ tests/test_repos.py
git commit -m "feat: per-repo component manifests (pulumi + new AWS LZA repo)"
```

---

## Task 7: Bootstrap/backfill ingestion

**Files:**
- Create: `src/ingest.py`
- Test: `tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ingest.py`:

```python
def test_bootstrap_pulumi_populates_components_and_edges(sqlite_env):
    db = sqlite_env
    from src import ingest
    ingest.bootstrap("pulumi", reset=True)
    comps = db.query(f"SELECT name FROM {db.tref('pulumi','infra_components')}")
    names = {c["name"] for c in comps}
    assert "acme-prod-admin-sso" in names
    edges = db.query(f"SELECT relationship FROM {db.tref('pulumi','component_edges')}")
    rels = {e["relationship"] for e in edges}
    assert "instantiates" in rels and "fronts" in rels and "redirects_to" in rels


def test_bootstrap_lza_sets_account_ref(sqlite_env):
    db = sqlite_env
    from src import ingest
    ingest.bootstrap("lza", reset=True)
    rows = db.query(
        f"SELECT name, account_ref FROM {db.tref('lza','infra_components')} "
        "WHERE component_type='Account'")
    refs = {r["account_ref"] for r in rows}
    assert {"prod", "sandbox"} <= refs


def test_bootstrap_all_is_idempotent(sqlite_env):
    db = sqlite_env
    from src import ingest
    ingest.bootstrap_all(reset=True)
    ingest.bootstrap_all(reset=False)  # second run must not duplicate
    comps = db.query(f"SELECT COUNT(*) AS n FROM {db.tref('pulumi','infra_components')}")
    assert comps[0]["n"] == 12  # 4 libs + 6 prod + 2 staging
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.ingest'`.

- [ ] **Step 3: Write the implementation**

Create `src/ingest.py`:

```python
"""Bootstrap / backfill: populate a repo's KB from its source BEFORE any agent session.

This is the EXPLICIT setup step (not automatic). On cloud (mem9.ai) embeddings are
generated server-side via EMBED_TEXT on insert; on local tiup they are precomputed
client-side; SQLite stores no embedding. Re-running is idempotent (upsert by name).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology
from src.repos import load_manifest
import importlib


def bootstrap(repo: str, reset: bool = False, team_name: str | None = None) -> int:
    team_name = team_name or topology.team()
    if reset:
        db.reset_db(team_name, [repo])
    else:
        db.init_db(team_name, [repo])

    components = load_manifest(repo)
    for c in components:
        db.write_component(
            repo=repo, name=c["name"], type=c["type"], env=c["env"], summary=c["summary"],
            depends_on=c.get("depends_on"), relationship=c.get("relationship", "uses"),
            developer="seed", repo_path=c.get("repo_path"), code_excerpt=c.get("code_excerpt"),
            account_ref=c.get("account_ref"), team_name=team_name,
        )

    manifest_mod = importlib.import_module(topology.REPOS[repo]["manifest"])
    for edge in getattr(manifest_mod, "EDGES", []):
        db.write_edge(repo, *edge, team_name=team_name)

    return len(components)


def bootstrap_all(reset: bool = False, team_name: str | None = None) -> dict[str, int]:
    return {r: bootstrap(r, reset=reset, team_name=team_name) for r in topology.repo_names()}


def main() -> None:
    reset = "--reset" in sys.argv or "--reseed" in sys.argv
    repo = None
    for i, a in enumerate(sys.argv):
        if a == "--repo" and i + 1 < len(sys.argv):
            repo = sys.argv[i + 1]
    target = db.backend_name()
    if repo:
        n = bootstrap(repo, reset=reset)
        print(f"Bootstrapped {repo} -> {db.database_for(repo)} ({n} components) on {target}")
    else:
        counts = bootstrap_all(reset=reset)
        for r, n in counts.items():
            print(f"Bootstrapped {r} -> {db.database_for(r)} ({n} components) on {target}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_ingest.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/ingest.py tests/test_ingest.py
git commit -m "feat: explicit bootstrap/backfill ingestion per repo"
```

---

## Task 8: Seed two repos + second team for isolation

**Files:**
- Modify: `src/seed.py` (full rewrite to delegate to ingest + add team `globex`)

- [ ] **Step 1: Rewrite `src/seed.py`**

Replace the entire contents of `src/seed.py`:

```python
"""Seed the mem9 knowledge base.

Team `acme` (the demo team) gets both repos fully populated: pulumi_kb + lza_kb.
Team `globex` gets a minimal pulumi_kb so the team-isolation demo (Scenario C) has
a real second team whose data Team A must NOT be able to read.

Usage:
  python -m src.seed --reset           # reseed acme (both repos) + globex (minimal)
  python -m src.seed --reset --repo lza # reseed only acme's lza_kb
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, ingest, topology


def seed(reset: bool = False, repo: str | None = None) -> None:
    if repo:
        n = ingest.bootstrap(repo, reset=reset)
        print(f"Seeded {repo} -> {db.database_for(repo)} ({n} components) on {db.backend_name()}")
        return

    counts = ingest.bootstrap_all(reset=reset)
    _seed_second_team(reset=reset)
    print(f"Seeded knowledge base on {db.backend_name()}:")
    print(f"  team acme: pulumi_kb ({counts['pulumi']}) + lza_kb ({counts['lza']})")
    print("  team globex: pulumi_kb (2) - for the team-isolation demo")
    print("  staging is missing its DNS + SSO layer (the live-demo task)")


def _seed_second_team(reset: bool) -> None:
    team = "globex"
    if reset:
        db.reset_db(team, ["pulumi"])
    else:
        db.init_db(team, ["pulumi"])
    db.write_component(repo="pulumi", team_name=team, name="globex-prod-ledger-db", type="RDS",
                       env="production", summary="Globex production ledger database (private to Globex).",
                       developer="seed", account_ref="prod")
    db.write_component(repo="pulumi", team_name=team, name="globex-prod-secrets", type="S3",
                       env="production", summary="Globex production secrets bucket (private to Globex).",
                       developer="seed", account_ref="prod")


if __name__ == "__main__":
    reset = "--reset" in sys.argv or "--reseed" in sys.argv
    repo = None
    for i, a in enumerate(sys.argv):
        if a == "--repo" and i + 1 < len(sys.argv):
            repo = sys.argv[i + 1]
    seed(reset=reset, repo=repo)
```

- [ ] **Step 2: Verify seed runs on the SQLite substrate**

Run:
```bash
MEM9_DATA_DIR=/tmp/mem9-seedtest .venv/bin/python -m src.seed --reset
```
Expected output includes: `Seeded knowledge base on SQLite (offline / test substrate):`, `team acme: pulumi_kb (12) + lza_kb (9)`, `team globex: pulumi_kb (2)`.

- [ ] **Step 3: Commit**

```bash
git add src/seed.py
git commit -m "feat: seed two repos for team acme + minimal globex for isolation demo"
```

---

## Task 9: Cross-repo Scenario B script

**Files:**
- Create: `src/cross_repo_demo.py`
- Test: `tests/test_cross_repo.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_cross_repo.py`:

```python
def test_cross_repo_create_account_then_bucket(sqlite_env):
    db = sqlite_env
    from src import ingest, cross_repo_demo
    ingest.bootstrap_all(reset=True)
    result = cross_repo_demo.run(account_ref="data-platform", developer="claude-code")
    # The new LZA account and the new Pulumi bucket both exist...
    lza = db.query(f"SELECT name FROM {db.tref('lza','infra_components')} WHERE account_ref='data-platform'")
    pul = db.query(f"SELECT name FROM {db.tref('pulumi','infra_components')} WHERE account_ref='data-platform'")
    assert lza and pul
    # ...and the cross-database JOIN ties them together.
    joined = [r for r in result["joined"] if r["account_ref"] == "data-platform"]
    assert joined and joined[0]["lza_account"].startswith("acme-lza-account-")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_cross_repo.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.cross_repo_demo'`.

- [ ] **Step 3: Write the implementation**

Create `src/cross_repo_demo.py`:

```python
"""Scenario B - cross-repo task over ONE team connection (no separate per-cluster auth).

"Create a new AWS account in LZA, then create an S3 bucket in that account in Pulumi."
Reads/writes BOTH acme_lza_kb and acme_pulumi_kb (same team cluster), then runs a
cross-database JOIN to show the bucket mapped to its account.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db


def run(account_ref: str = "data-platform", developer: str = "claude-code") -> dict:
    account_name = f"acme-lza-account-{account_ref}"
    bucket_name = f"acme-prod-{account_ref}-exports"

    # 1. Write the new AWS account into the LZA repo database.
    db.write_component(
        repo="lza", name=account_name, type="Account", env="org",
        summary=f"AWS account (account_ref={account_ref}) created for the {account_ref} workload.",
        depends_on="AwsAccount", developer=developer, account_ref=account_ref,
        repo_path="lza/accounts.ts",
    )

    # 2. Write the S3 bucket into the Pulumi repo database, tagged to that account.
    db.write_component(
        repo="pulumi", name=bucket_name, type="S3", env="production",
        summary=f"Exports bucket deployed into AWS account {account_ref}. Composes S3Bucket.",
        depends_on="S3Bucket", developer=developer, account_ref=account_ref,
        repo_path="environments/production/storage.ts",
    )

    # 3. One cross-database JOIN proves the link, over a single team connection.
    sql = db.cross_repo_accounts_sql(db.database_for("pulumi"), db.database_for("lza"))
    joined = db.query(sql)
    return {"sql": sql, "joined": joined, "account": account_name, "bucket": bucket_name}


def main() -> None:
    out = run()
    print(f"Created {out['account']} (lza_kb) and {out['bucket']} (pulumi_kb) on {db.backend_name()}\n")
    print("Cross-database JOIN (acme_pulumi_kb x acme_lza_kb):")
    for r in out["joined"]:
        print(f"  {r['pulumi_component']:<34} -> account {r['account_ref']:<14} ({r['lza_account']})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_cross_repo.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add src/cross_repo_demo.py tests/test_cross_repo.py
git commit -m "feat: cross-repo scenario B (LZA account + Pulumi bucket, one cross-db JOIN)"
```

---

## Task 10: Team-isolation Scenario C script

The proof differs by target. On SQLite a team-scoped connection only ATTACHes its own team's files, so another team's database is simply not present (no query path). On TiDB the proof is a GRANT-scoped user; that path is documented and runs live on mem9.ai. The script reports PASS when a cross-team read has no path.

**Files:**
- Create: `src/isolation_check.py`
- Test: `tests/test_isolation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_isolation.py`:

```python
def test_cross_team_read_has_no_path_sqlite(sqlite_env):
    db = sqlite_env
    from src import seed, isolation_check
    seed.seed(reset=True)  # seeds team acme + team globex
    report = isolation_check.check(my_team="acme", other_team="globex")
    assert report["isolated"] is True
    assert report["target"] == "sqlite"
    assert "no query path" in report["detail"].lower()


def test_same_team_read_succeeds(sqlite_env):
    db = sqlite_env
    from src import seed, isolation_check
    seed.seed(reset=True)
    rows = isolation_check.read_team_components("acme")
    assert any(r["name"] == "acme-prod-static-assets" for r in rows)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_isolation.py -q`
Expected: FAIL - `ModuleNotFoundError: No module named 'src.isolation_check'`.

- [ ] **Step 3: Write the implementation**

Create `src/isolation_check.py`:

```python
"""Scenario C - prove team isolation: an agent scoped to Team A cannot read Team B.

SQLite (offline): a team connection only ATTACHes its own team's databases, so the
other team's tables are absent - the cross-team query has no path (OperationalError).

TiDB (mem9.ai / tiup): isolation is enforced by credentials. In production each team
is its OWN cluster; in this single-cluster demo we GRANT a team user access only to
that team's databases, so a cross-team SELECT fails with an access-denied error.
The runbook (DEMO.md) shows the GRANT setup; this script verifies the denial.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology


def read_team_components(team: str) -> list[dict]:
    return db.query(
        f"SELECT name, repo FROM {db.tref('pulumi', 'infra_components', team)}",
        team_name=team, repos=["pulumi"],
    )


def check(my_team: str = "acme", other_team: str = "globex") -> dict:
    target = topology.target()
    other_db = db.database_for("pulumi", other_team)
    # Attempt a cross-team read using ONLY my_team's connection scope.
    cross_sql = f"SELECT COUNT(*) AS n FROM {other_db}.infra_components"
    try:
        db.query(cross_sql, team_name=my_team, repos=["pulumi"])
        isolated = False
        detail = f"WARNING: {my_team} could read {other_db} - isolation NOT enforced."
    except Exception as exc:
        isolated = True
        detail = (f"{my_team} has no query path to {other_db}: {type(exc).__name__}. "
                  f"Isolation holds by design.")
    return {"isolated": isolated, "target": target, "my_team": my_team,
            "other_team": other_team, "cross_sql": cross_sql, "detail": detail}


def main() -> None:
    report = check()
    print(f"Target: {db.backend_name()}")
    print(f"Cross-team probe: {report['cross_sql']}")
    print(("PASS - " if report["isolated"] else "FAIL - ") + report["detail"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_isolation.py -q`
Expected: PASS (2 passed). The cross-team `query()` raises `sqlite3.OperationalError: no such table` because `globex_pulumi_kb` is not attached to an `acme`-scoped connection.

- [ ] **Step 5: Commit**

```bash
git add src/isolation_check.py tests/test_isolation.py
git commit -m "feat: team-isolation scenario C proof (cross-team read fails by design)"
```

---

## Task 11: MCP server - repo-scoped, explicit per-repo identity

The convention MCP becomes one process per repo, selected by `MEM9_REPO`. Its tool descriptions name the repo explicitly. Reads may use cross-database SQL (the team connection reaches all the team's repos); writes default to this server's repo.

**Files:**
- Modify: `src/mcp_server.py` (full rewrite)
- Test: `tests/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_server.py`:

```python
import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _rpc(proc, msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def test_server_identifies_its_repo_and_writes_scoped(tmp_path, monkeypatch):
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env.update({"MEM9_DATA_DIR": str(tmp_path), "MEM9_REPO": "pulumi", "MEM9_TEAM": "acme"})
    env.pop("TIDB_HOST", None)

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.mcp_server"],
        cwd=str(ROOT), env=env, text=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert "pulumi" in json.dumps(init["result"]).lower()

        listed = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in listed["result"]["tools"]}
        assert {"query_knowledge_base", "write_component"} <= names

        wrote = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "write_component",
            "arguments": {"name": "acme-staging-admin-dns", "type": "Cloudflare",
                          "env": "staging", "summary": "staging admin dns", "developer": "codex"}}})
        assert "acme-staging-admin-dns" in json.dumps(wrote["result"])

        read = _rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "query_knowledge_base",
            "arguments": {"sql": "SELECT name FROM acme_pulumi_kb.infra_components WHERE name='acme-staging-admin-dns'",
                          "developer": "codex"}}})
        assert "acme-staging-admin-dns" in json.dumps(read["result"])
    finally:
        proc.terminate()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: FAIL - the current server has no repo identity and `write_component` signature lacks `repo`.

- [ ] **Step 3: Rewrite `src/mcp_server.py`**

Replace the entire contents of `src/mcp_server.py`:

```python
"""mem9 convention MCP server - ONE process per repo database (stdio transport).

Routing is explicit, never inferred: which repo this server writes to is fixed by
the MEM9_REPO environment variable set in the named MCP config entry (e.g. the
"infra-kb-pulumi" entry sets MEM9_REPO=pulumi). The agent chooses the destination
by calling the matching named server - the server does not guess.

Run with:  MEM9_REPO=pulumi MEM9_TEAM=acme python -m src.mcp_server
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db as _db

REPO = os.environ.get("MEM9_REPO", "pulumi")
TEAM = os.environ.get("MEM9_TEAM", "acme")
DB_NAME = _db.database_for(REPO, TEAM)

_db.init_db(TEAM, [REPO])

TOOLS = [
    {
        "name": "query_knowledge_base",
        "description": (
            f"Run a read-only SELECT against team '{TEAM}'. This server is bound to the "
            f"'{REPO}' repo (database {DB_NAME}). You may also cross-database JOIN to other "
            f"repos in the SAME team cluster using fully-qualified names (e.g. "
            f"{_db.database_for('lza', TEAM)}.infra_components). Tables per repo: "
            "infra_components(id,name,component_type,environment,repo,account_ref,repo_path,summary,code_excerpt), "
            "component_edges(id,from_id,to_id,relationship,note), session_log(id,developer,action,detail,created_at). "
            "Always query before creating anything."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A SELECT/WITH query. Qualify tables as <db>.<table>."},
                "developer": {"type": "string", "description": "claude-code | codex | cursor"},
            },
            "required": ["sql"],
        },
    },
    {
        "name": "write_component",
        "description": (
            f"Atomically record a component + dependency edge + session-log entry into the "
            f"'{REPO}' repo (database {DB_NAME}) for team '{TEAM}'. Write-back is INSTRUCTION-"
            "DRIVEN: call this after you scaffold a resource so the next session starts warm. "
            "Set account_ref to the LZA account the resource belongs to (enables cross-repo JOINs)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "type": {"type": "string", "description": "Component type, e.g. S3/RDS/Cloudflare/Okta/Account/OU/SCP/Library"},
                "env": {"type": "string", "description": "production | staging | library | org"},
                "summary": {"type": "string"},
                "depends_on": {"type": "string", "description": "Name of the library/parent component it composes"},
                "account_ref": {"type": "string", "description": "LZA account key, e.g. prod | sandbox"},
                "developer": {"type": "string", "description": "claude-code | codex | cursor"},
            },
            "required": ["name", "type", "env", "summary", "developer"],
        },
    },
]


def _respond(id, result):
    print(json.dumps({"jsonrpc": "2.0", "id": id, "result": result}), flush=True)


def _error(id, code, message):
    print(json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}), flush=True)


def _handle(msg):
    method = msg.get("method", "")
    id_ = msg.get("id")

    if method == "initialize":
        _respond(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": f"mem9-infra-kb-{REPO}", "version": "2.0.0",
                           "repo": REPO, "team": TEAM, "database": DB_NAME},
        })
    elif method == "notifications/initialized":
        pass
    elif method == "tools/list":
        _respond(id_, {"tools": TOOLS})
    elif method == "tools/call":
        params = msg.get("params", {})
        tool = params.get("name")
        args = params.get("arguments", {})
        try:
            if tool == "query_knowledge_base":
                sql = args.get("sql", "").strip()
                developer = args.get("developer", "unknown")
                rows = _db.query(sql, team_name=TEAM)
                _db.log_query(REPO, developer, f"SQL: {sql[:120]}", team_name=TEAM)
                _respond(id_, {"content": [{"type": "text", "text": json.dumps(rows, indent=2, default=str)}]})
            elif tool == "write_component":
                comp_id = _db.write_component(
                    repo=REPO, team_name=TEAM, name=args["name"], type=args["type"],
                    env=args["env"], summary=args["summary"], depends_on=args.get("depends_on"),
                    account_ref=args.get("account_ref"), developer=args["developer"],
                )
                _respond(id_, {"content": [{"type": "text",
                          "text": f"Written to {DB_NAME}: {args['name']} (id={comp_id})"}]})
            else:
                _error(id_, -32601, f"Unknown tool: {tool}")
        except Exception as exc:
            _error(id_, -32603, str(exc))
    else:
        _error(id_, -32601, f"Unknown method: {method}")


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            _handle(json.loads(raw))
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"Parse error: {exc}")
        except Exception as exc:
            _error(None, -32603, str(exc))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_mcp_server.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (all tests across all files).

- [ ] **Step 6: Commit**

```bash
git add src/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: repo-scoped MCP server with explicit per-repo identity + cross-db reads"
```

---

## Task 12: Writeback CLI - add `--repo`

**Files:**
- Modify: `src/writeback.py`

- [ ] **Step 1: Rewrite `src/writeback.py`**

Replace the entire contents of `src/writeback.py`:

```python
"""CLI writeback: record a component to a repo's KB (instruction-driven persist).

Usage:
  python -m src.writeback --repo pulumi \\
    --name acme-staging-admin-dns --type Cloudflare --env staging \\
    --summary "Cloudflare DNS for staging admin portal" \\
    --depends-on DnsRecord --account-ref sandbox --developer claude-code
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db, topology


def main() -> None:
    p = argparse.ArgumentParser(description="Record a component to a repo's mem9 KB")
    p.add_argument("--repo", required=True, choices=topology.repo_names())
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--env", required=True)
    p.add_argument("--summary", required=True)
    p.add_argument("--depends-on", dest="depends_on")
    p.add_argument("--account-ref", dest="account_ref")
    p.add_argument("--developer", required=True)
    p.add_argument("--repo-path", dest="repo_path")
    args = p.parse_args()

    db.init_db(repos=[args.repo])
    comp_id = db.write_component(
        repo=args.repo, name=args.name, type=args.type, env=args.env, summary=args.summary,
        depends_on=args.depends_on, account_ref=args.account_ref, developer=args.developer,
        repo_path=args.repo_path,
    )
    print(f"Written to {db.database_for(args.repo)}: {args.name} (id={comp_id})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify on the SQLite substrate**

Run:
```bash
MEM9_DATA_DIR=/tmp/mem9-wb .venv/bin/python -m src.seed --reset >/dev/null
MEM9_DATA_DIR=/tmp/mem9-wb .venv/bin/python -m src.writeback --repo pulumi \
  --name acme-staging-admin-dns --type Cloudflare --env staging \
  --summary "Cloudflare DNS for staging admin portal" \
  --depends-on DnsRecord --account-ref sandbox --developer claude-code
```
Expected: `Written to acme_pulumi_kb: acme-staging-admin-dns (id=...)`.

- [ ] **Step 3: Commit**

```bash
git add src/writeback.py
git commit -m "feat: writeback CLI takes --repo and --account-ref"
```

---

## Task 13: gen_configs - one named server entry per repo database

**Files:**
- Modify: `src/gen_configs.py` (full rewrite)
- Modify: `configs/claude-code/mcp.json`
- Modify: `configs/cursor/mcp.json`
- Modify: `configs/codex/config.toml`

- [ ] **Step 1: Rewrite `src/gen_configs.py`**

Replace the entire contents of `src/gen_configs.py`:

```python
"""Generate MCP configs for Claude Code, Codex, and Cursor.

Routing is EXPLICIT: one named server entry per repo database, all scoped to a
single team cluster. For team 'acme' with repos pulumi + lza this emits:

  tidb-pulumi      official TiDB MCP, TIDB_DATABASE=acme_pulumi_kb  (raw SQL/vector)
  tidb-lza         official TiDB MCP, TIDB_DATABASE=acme_lza_kb
  infra-kb-pulumi  mem9 convention MCP, MEM9_REPO=pulumi
  infra-kb-lza     mem9 convention MCP, MEM9_REPO=lza

Same team credentials unlock every database in that team's cluster, so a cross-repo
JOIN works from any entry - but the agent always picks the destination explicitly.
Generated files contain secrets and are gitignored. Run: python -m src.gen_configs
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import topology

ROOT = Path(__file__).parent.parent
VENV_PY = ROOT / ".venv" / "bin" / "python"


def _env() -> dict:
    if load_dotenv:
        load_dotenv(ROOT / ".env", override=False)
    needed = ["TIDB_HOST", "TIDB_PORT", "TIDB_USERNAME", "TIDB_PASSWORD"]
    env = {k: os.environ.get(k, "") for k in needed}
    if not env["TIDB_HOST"]:
        sys.exit("ERROR: TIDB_HOST not set. Copy .env.example to .env and fill in your mem9.ai creds.")
    env["TEAM"] = topology.team()
    return env


def _tidb_server(env: dict, repo: str) -> dict:
    cursor_dir = ROOT / ".cursor"
    return {
        "command": "uvx",
        "args": ["--from", "pytidb[mcp]", "tidb-mcp-server"],
        "env": {
            "TIDB_HOST": env["TIDB_HOST"],
            "TIDB_PORT": str(env["TIDB_PORT"] or "4000"),
            "TIDB_USERNAME": env["TIDB_USERNAME"],
            "TIDB_PASSWORD": env["TIDB_PASSWORD"],
            "TIDB_DATABASE": topology.database_for(repo, env["TEAM"]),
            "UV_CACHE_DIR": str(cursor_dir / "uv-cache"),
            "XDG_CACHE_HOME": str(cursor_dir / "xdg-cache"),
            "XDG_DATA_HOME": str(cursor_dir / "xdg-data"),
        },
    }


def _kb_server(env: dict, repo: str) -> dict:
    return {
        "command": str(VENV_PY),
        "args": ["-m", "src.mcp_server"],
        "cwd": str(ROOT),
        "env": {"MEM9_REPO": repo, "MEM9_TEAM": env["TEAM"]},
    }


def _servers(env: dict) -> dict:
    servers = {}
    for repo in topology.repo_names():
        servers[f"tidb-{repo}"] = _tidb_server(env, repo)
        servers[f"infra-kb-{repo}"] = _kb_server(env, repo)
    return servers


def write_claude_code(env: dict) -> Path:
    out = ROOT / ".mcp.json"
    out.write_text(json.dumps({"mcpServers": _servers(env)}, indent=2) + "\n")
    return out


def write_cursor(env: dict) -> Path:
    out = ROOT / ".cursor" / "mcp.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"mcpServers": _servers(env)}, indent=2) + "\n")
    return out


def write_codex(env: dict) -> Path:
    lines = ["# ── Add these blocks to ~/.codex/config.toml ──────────────────────────────"]
    for repo in topology.repo_names():
        t = _tidb_server(env, repo)
        lines += [
            f"[mcp_servers.tidb-{repo}]",
            'command = "uvx"',
            'args = ["--from", "pytidb[mcp]", "tidb-mcp-server"]',
            f"[mcp_servers.tidb-{repo}.env]",
            f'TIDB_HOST = "{t["env"]["TIDB_HOST"]}"',
            f'TIDB_PORT = "{t["env"]["TIDB_PORT"]}"',
            f'TIDB_USERNAME = "{t["env"]["TIDB_USERNAME"]}"',
            f'TIDB_PASSWORD = "{t["env"]["TIDB_PASSWORD"]}"',
            f'TIDB_DATABASE = "{t["env"]["TIDB_DATABASE"]}"',
            "",
            f"[mcp_servers.infra-kb-{repo}]",
            f'command = "{VENV_PY}"',
            'args = ["-m", "src.mcp_server"]',
            f'cwd = "{ROOT}"',
            f"[mcp_servers.infra-kb-{repo}.env]",
            f'MEM9_REPO = "{repo}"',
            f'MEM9_TEAM = "{env["TEAM"]}"',
            "",
        ]
    out = ROOT / "configs" / "generated" / "codex-config.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    return out


def main() -> None:
    env = _env()
    paths = [write_claude_code(env), write_cursor(env), write_codex(env)]
    print(f"Generated MCP configs for team '{env['TEAM']}' (gitignored, contain secrets):")
    print(f"  Claude Code : {paths[0]}")
    print(f"  Cursor      : {paths[1]}")
    print(f"  Codex       : paste blocks from {paths[2]} into ~/.codex/config.toml")
    print("\nNamed entries per repo: " + ", ".join(
        f"tidb-{r}/infra-kb-{r}" for r in topology.repo_names()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update the Claude Code template** `configs/claude-code/mcp.json`

Replace the entire contents:

```json
{
  "_comment": "TEMPLATE. Run `python -m src.gen_configs` to write the real .mcp.json (with your mem9.ai creds). One named entry per repo database; all scoped to one team cluster. The agent picks the destination explicitly - routing is never inferred.",
  "mcpServers": {
    "tidb-pulumi": {
      "command": "uvx",
      "args": ["--from", "pytidb[mcp]", "tidb-mcp-server"],
      "env": {
        "TIDB_HOST": "${TIDB_HOST}", "TIDB_PORT": "${TIDB_PORT}",
        "TIDB_USERNAME": "${TIDB_USERNAME}", "TIDB_PASSWORD": "${TIDB_PASSWORD}",
        "TIDB_DATABASE": "acme_pulumi_kb"
      }
    },
    "tidb-lza": {
      "command": "uvx",
      "args": ["--from", "pytidb[mcp]", "tidb-mcp-server"],
      "env": {
        "TIDB_HOST": "${TIDB_HOST}", "TIDB_PORT": "${TIDB_PORT}",
        "TIDB_USERNAME": "${TIDB_USERNAME}", "TIDB_PASSWORD": "${TIDB_PASSWORD}",
        "TIDB_DATABASE": "acme_lza_kb"
      }
    },
    "infra-kb-pulumi": {
      "command": "/path/to/mem9-ai-coding/.venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/mem9-ai-coding",
      "env": {"MEM9_REPO": "pulumi", "MEM9_TEAM": "acme"}
    },
    "infra-kb-lza": {
      "command": "/path/to/mem9-ai-coding/.venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/mem9-ai-coding",
      "env": {"MEM9_REPO": "lza", "MEM9_TEAM": "acme"}
    }
  }
}
```

- [ ] **Step 3: Update the Cursor template** `configs/cursor/mcp.json`

Replace the entire contents with the same JSON as Step 2, but change the leading `_comment` to mention Cursor and the `UV_CACHE_DIR` pinning:

```json
{
  "_comment": "TEMPLATE. Run `python -m src.gen_configs` to write the real .cursor/mcp.json. One named entry per repo database, scoped to one team cluster. The generated config pins UV_CACHE_DIR into the repo to avoid Cursor reconnect loops. Routing is explicit - the agent chooses tidb-pulumi vs tidb-lza vs infra-kb-* itself.",
  "mcpServers": {
    "tidb-pulumi": {
      "command": "uvx",
      "args": ["--from", "pytidb[mcp]", "tidb-mcp-server"],
      "env": {
        "TIDB_HOST": "${TIDB_HOST}", "TIDB_PORT": "${TIDB_PORT}",
        "TIDB_USERNAME": "${TIDB_USERNAME}", "TIDB_PASSWORD": "${TIDB_PASSWORD}",
        "TIDB_DATABASE": "acme_pulumi_kb"
      }
    },
    "tidb-lza": {
      "command": "uvx",
      "args": ["--from", "pytidb[mcp]", "tidb-mcp-server"],
      "env": {
        "TIDB_HOST": "${TIDB_HOST}", "TIDB_PORT": "${TIDB_PORT}",
        "TIDB_USERNAME": "${TIDB_USERNAME}", "TIDB_PASSWORD": "${TIDB_PASSWORD}",
        "TIDB_DATABASE": "acme_lza_kb"
      }
    },
    "infra-kb-pulumi": {
      "command": "/path/to/mem9-ai-coding/.venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/mem9-ai-coding",
      "env": {"MEM9_REPO": "pulumi", "MEM9_TEAM": "acme"}
    },
    "infra-kb-lza": {
      "command": "/path/to/mem9-ai-coding/.venv/bin/python",
      "args": ["-m", "src.mcp_server"],
      "cwd": "/path/to/mem9-ai-coding",
      "env": {"MEM9_REPO": "lza", "MEM9_TEAM": "acme"}
    }
  }
}
```

- [ ] **Step 4: Update the Codex template** `configs/codex/config.toml`

Replace the entire contents:

```toml
# TEMPLATE for ~/.codex/config.toml
# Run `python -m src.gen_configs` to produce configs/generated/codex-config.toml
# with your real mem9.ai creds, then paste these blocks into ~/.codex/config.toml.
# One named MCP entry per repo database; all scoped to one team cluster.
# Routing is explicit: the agent calls tidb-pulumi vs tidb-lza vs infra-kb-* itself.

[mcp_servers.tidb-pulumi]
command = "uvx"
args = ["--from", "pytidb[mcp]", "tidb-mcp-server"]
[mcp_servers.tidb-pulumi.env]
TIDB_HOST = "${TIDB_HOST}"
TIDB_PORT = "${TIDB_PORT}"
TIDB_USERNAME = "${TIDB_USERNAME}"
TIDB_PASSWORD = "${TIDB_PASSWORD}"
TIDB_DATABASE = "acme_pulumi_kb"

[mcp_servers.tidb-lza]
command = "uvx"
args = ["--from", "pytidb[mcp]", "tidb-mcp-server"]
[mcp_servers.tidb-lza.env]
TIDB_HOST = "${TIDB_HOST}"
TIDB_PORT = "${TIDB_PORT}"
TIDB_USERNAME = "${TIDB_USERNAME}"
TIDB_PASSWORD = "${TIDB_PASSWORD}"
TIDB_DATABASE = "acme_lza_kb"

[mcp_servers.infra-kb-pulumi]
command = "/path/to/mem9-ai-coding/.venv/bin/python"
args = ["-m", "src.mcp_server"]
cwd = "/path/to/mem9-ai-coding"
[mcp_servers.infra-kb-pulumi.env]
MEM9_REPO = "pulumi"
MEM9_TEAM = "acme"

[mcp_servers.infra-kb-lza]
command = "/path/to/mem9-ai-coding/.venv/bin/python"
args = ["-m", "src.mcp_server"]
cwd = "/path/to/mem9-ai-coding"
[mcp_servers.infra-kb-lza.env]
MEM9_REPO = "lza"
MEM9_TEAM = "acme"
```

- [ ] **Step 5: Verify generated configs parse**

Run (uses the existing `.env` creds; if absent, set dummy creds first):
```bash
.venv/bin/python -m src.gen_configs
.venv/bin/python -c "import json; json.load(open('.mcp.json')); json.load(open('.cursor/mcp.json')); print('json OK')"
.venv/bin/python -c "import tomllib; tomllib.load(open('configs/generated/codex-config.toml','rb')); print('toml OK')"
```
Expected: prints the four named entries, then `json OK` and `toml OK`. Confirm `.mcp.json` contains `tidb-pulumi`, `tidb-lza`, `infra-kb-pulumi`, `infra-kb-lza`.

- [ ] **Step 6: Commit**

```bash
git add src/gen_configs.py configs/claude-code/mcp.json configs/cursor/mcp.json configs/codex/config.toml
git commit -m "feat: one named MCP entry per repo database, scoped to one team cluster"
```

---

## Task 14: Dashboard - repo-aware (Pulumi appendix view)

The dashboard is repositioned as an optional appendix; it points at the Pulumi repo database. Endpoints stay the same so the front-end is unchanged.

**Files:**
- Modify: `dashboard/server.py`

- [ ] **Step 1: Make dashboard reads repo-qualified**

In `dashboard/server.py`, after `from src import seed as seeder` add:

```python
REPO = "pulumi"
C = db.tref(REPO, "infra_components")
E = db.tref(REPO, "component_edges")
L = db.tref(REPO, "session_log")
```

Change `db.init_db()` to `db.init_db(repos=[REPO])`.

- [ ] **Step 2: Update each endpoint's SQL to use the qualified names**

In `dashboard/server.py`, replace the bare table names in every query with the qualified module constants:
- `/api/components`: `FROM infra_components` → `FROM {C}` (f-string the query).
- `/api/edges`: `FROM component_edges e JOIN infra_components c1 ...` → use `{E}`, `{C}`.
- `/api/session-log`: `FROM session_log` → `FROM {L}`.
- `/api/missing`: both `FROM infra_components` → `FROM {C}`.
- `/api/memory`: `FROM infra_components` → `FROM {C}`.

For example, the components endpoint becomes:

```python
@app.get("/api/components")
def components():
    return JSONResponse(db.query(
        f"SELECT id, name, component_type, environment, repo, account_ref, repo_path, summary, "
        f"code_excerpt, created_by, created_at FROM {C} ORDER BY environment, component_type, name",
        repos=[REPO]))
```

Apply the same `repos=[REPO]` argument and `{C}/{E}/{L}` qualification to `edges()`, `session_log()`, `missing()`, and `memory()`.

- [ ] **Step 3: Update CTE/search/scenario calls to pass the repo**

- `cte_dependencies(name)` → `db.cte_dependencies(REPO, name)`.
- `cte_blast_radius(name)` → `db.cte_blast_radius(REPO, name)`.
- `search(q, mode)` → `db.search(REPO, q, mode=mode, k=6)`.
- In `SCENARIOS`, `db.CTE_BLAST_RADIUS_SQL.format(name="S3Bucket")` → `db._cte_blast_radius_sql(db.database_for(REPO), "S3Bucket")`.
- In `DEMO_STEPS`, `db.CTE_DEPENDENCIES_SQL.format(name="acme-prod-admin-sso")` → `db._cte_dependencies_sql(db.database_for(REPO), "acme-prod-admin-sso")`.
- In the `_m_*` mutation helpers, add `repo="pulumi"` to each `db.write_component(...)` call and change `db.write_edge("a","b",...)` to `db.write_edge("pulumi", "a", "b", ...)`.
- `db.log_query(step["tool"], ...)` → `db.log_query(REPO, step["tool"], ...)`.
- `/api/reset`: `seeder.seed(reset=True)` stays (reseeds everything).

- [ ] **Step 4: Verify the dashboard boots and serves on SQLite**

Run:
```bash
MEM9_DATA_DIR=/tmp/mem9-dash .venv/bin/python -m src.seed --reset >/dev/null
MEM9_DATA_DIR=/tmp/mem9-dash .venv/bin/python -c "
from fastapi.testclient import TestClient
import importlib, src.db as db; importlib.reload(db)
from dashboard import server
c = TestClient(server.app)
assert c.get('/healthz').json()['status']=='ok'
comps = c.get('/api/components').json()
assert any(x['name']=='acme-prod-static-assets' for x in comps), 'components missing'
assert c.get('/api/backend').json()['backend'].startswith('SQLite')
print('dashboard OK -', len(comps), 'components')
"
```
Expected: `dashboard OK - 12 components`. (Install `httpx` if `TestClient` errors: `.venv/bin/pip install httpx`.)

- [ ] **Step 5: Commit**

```bash
git add dashboard/server.py
git commit -m "refactor: dashboard reads the Pulumi repo database (appendix view)"
```

---

## Task 15: Agent context prompts (CLAUDE.md / AGENTS.md / .cursorrules)

Reposition around mem9 ("your existing Cursor plus a memory the database holds"), document team=cluster/repo=database, explicit per-repo routing, the bootstrap-then-persist lifecycle (with the explicit note that write-back is instruction-driven, not automatic), and the eventual-consistency caveat.

**Files:**
- Modify: `configs/claude-code/CLAUDE.md` (full rewrite)
- Modify: `configs/codex/AGENTS.md` (full rewrite)
- Modify: `configs/cursor/.cursorrules` (full rewrite)

- [ ] **Step 1: Rewrite `configs/claude-code/CLAUDE.md`**

Replace the entire contents:

```markdown
# Acme infrastructure - mem9 memory

You are working in your normal coding tool. The only thing different here is that
this team has a **memory the database holds (mem9)**: every infrastructure component,
dependency edge, and prior session is recorded in TiDB and shared across Claude Code,
Codex, and Cursor. Use it so you never start cold or duplicate work.

## How the memory is organized

- **Team = cluster.** You are connected to one team's TiDB cluster (this team: `acme`).
  Your credentials unlock only this team's databases. You have no path to another team's KB.
- **Repo = database.** Each repo is its own database in this cluster:
  - `acme_pulumi_kb` - the Pulumi infra-as-code repo
  - `acme_lza_kb` - the AWS Landing Zone Accelerator repo
- Work in one repo, or across both with a cross-database JOIN over the same connection.

## Your MCP servers (routing is explicit - you choose)

Named entries, one per repo database. The server does NOT guess where to write:

- `infra-kb-pulumi` / `infra-kb-lza` - mem9 convention layer: `query_knowledge_base`,
  `write_component`. Call the one matching the repo you are changing.
- `tidb-pulumi` / `tidb-lza` - the official TiDB MCP for raw SQL (`db_query`, recursive
  CTEs, vector search). Same team creds, so you can cross-database JOIN, e.g.
  `acme_lza_kb.infra_components` from the `tidb-pulumi` connection.

## Lifecycle: query before acting; persist after acting

1. **Bootstrap (done before your session).** The team runs `python -m src.ingest --reset`
   to populate each repo's KB from source. You start warm.
2. **Query first.** Before writing any code, query the KB for what exists, the conventions,
   and the recent session log.
3. **Persist after.** After you scaffold a resource, **call `write_component` to record it.**
   This is instruction-driven, NOT automatic - if you skip it, the next tool starts cold.

> Eventual consistency: full-text/columnar indexes lag writes by a second or two. For a
> read-your-write check, use a point lookup by `name` (primary/unique key), not full-text.

## Key queries

```sql
-- What exists in staging vs production? (Pulumi repo)
SELECT name, component_type, environment FROM acme_pulumi_kb.infra_components
WHERE environment IN ('staging','production') ORDER BY environment;

-- Recent shared sessions (who did what)
SELECT developer, action, detail, created_at FROM acme_pulumi_kb.session_log
ORDER BY created_at DESC LIMIT 10;

-- Cross-repo: which Pulumi resources live in which LZA account?
SELECT p.name, p.account_ref, a.name AS lza_account
FROM acme_pulumi_kb.infra_components p
JOIN acme_lza_kb.infra_components a ON a.account_ref = p.account_ref AND a.component_type='Account';
```

## Blast radius before changing a library (recursive CTE, single repo)

```sql
WITH RECURSIVE blast(from_id, to_id, relationship, depth) AS (
    SELECT e.from_id, e.to_id, e.relationship, 1
    FROM acme_pulumi_kb.component_edges e
    JOIN acme_pulumi_kb.infra_components c ON e.to_id = c.id WHERE c.name = 'S3Bucket'
  UNION ALL
    SELECT e.from_id, e.to_id, e.relationship, b.depth + 1
    FROM acme_pulumi_kb.component_edges e
    JOIN blast b ON e.to_id = b.from_id WHERE b.depth < 10
)
SELECT depth, from_id, relationship, to_id FROM blast ORDER BY depth;
```

## Conventions (non-negotiable)

- Never use raw provider resources (`aws.s3.BucketV2`, etc). Compose library components.
- `PostgresDatabase` auto-creates its backup S3 bucket. Do NOT add one.
- Physical names: `acme-<environment>-<logical-name>`.
- Tags: `Environment`, `ManagedBy: pulumi`, `Component`, `Team`.
- Public endpoints use `DnsRecord` (proxied: true). SSO uses `SsoApplication`, redirect URI
  points at the `DnsRecord` hostname.
- New Pulumi resources set `account_ref` to the LZA account they deploy into (`prod`/`sandbox`).

## After creating anything

```bash
python -m src.writeback --repo pulumi \
  --name <resource-name> --type <S3|RDS|Cloudflare|Okta> --env <production|staging> \
  --summary "<what it does and what library it composes>" \
  --depends-on <library-component-name> --account-ref <prod|sandbox> --developer claude-code
```

Or call the `write_component` tool on `infra-kb-pulumi` (or `infra-kb-lza`) directly.
```

- [ ] **Step 2: Rewrite `configs/codex/AGENTS.md`**

Replace the entire contents:

```markdown
# Acme infrastructure - mem9 memory (Codex)

Your coding tool, plus a memory the database holds (mem9): components, edges, and prior
sessions live in TiDB and are shared across Claude Code, Codex, and Cursor.

## Organization
- **Team = cluster** (you are on team `acme`; creds unlock only this team).
- **Repo = database**: `acme_pulumi_kb` (Pulumi), `acme_lza_kb` (AWS LZA).

## MCP servers (explicit routing - you pick the named entry)
- `infra-kb-pulumi` / `infra-kb-lza`: `query_knowledge_base`, `write_component`.
- `tidb-pulumi` / `tidb-lza`: official TiDB MCP `db_query` (raw SQL, recursive CTEs,
  vector search). Cross-database JOINs work because both DBs share the team creds.

## Lifecycle: query before acting; persist after acting
- Query the KB before writing code (what exists, conventions, recent session_log).
- After scaffolding, **call `write_component`** - persist is instruction-driven, not automatic.
- Eventual consistency: full-text/columnar indexes lag writes by ~seconds; use a point
  lookup by `name` for read-your-write checks.

## Query first
```sql
SELECT name, component_type, environment FROM acme_pulumi_kb.infra_components WHERE environment='staging';
SELECT developer, action, detail FROM acme_pulumi_kb.session_log ORDER BY created_at DESC LIMIT 5;
```

## Rules
- Never raw provider resources - compose libraries in `libs/`.
- Names `acme-<env>-<logical>`; tags Environment/ManagedBy/Component/Team.
- Public endpoints use `DnsRecord` (proxied: true); SSO redirect URI points at a `DnsRecord`.
- `PostgresDatabase` makes its own backup bucket - don't add one.
- Set `account_ref` (prod/sandbox) on new Pulumi resources.

## After creating
```bash
python -m src.writeback --repo pulumi --name <name> --type <type> --env <env> \
  --summary "<summary>" --depends-on <library> --account-ref <prod|sandbox> --developer codex
```
```

- [ ] **Step 3: Rewrite `configs/cursor/.cursorrules`**

Replace the entire contents:

```text
You are working on Acme's infrastructure with mem9 - a memory the database holds.
Components, dependency edges, and prior sessions live in TiDB and are shared across
Claude Code, Codex, and Cursor. Use it; never start cold or duplicate work.

ORGANIZATION
- Team = cluster (you are on team acme; your credentials unlock only this team's databases).
- Repo = database: acme_pulumi_kb (Pulumi infra), acme_lza_kb (AWS Landing Zone Accelerator).

MCP SERVERS (routing is explicit - YOU choose the named entry; the server never guesses)
- infra-kb-pulumi / infra-kb-lza: query_knowledge_base + write_component (atomic, checked).
- tidb-pulumi / tidb-lza: official TiDB MCP db_query for raw SQL, recursive CTEs, vector search.
  Cross-database JOINs (acme_pulumi_kb.x JOIN acme_lza_kb.y) work over one team connection.

LIFECYCLE: query before acting; persist after acting
- Query the KB before writing code (what exists, conventions, recent session_log).
- After scaffolding, CALL write_component. Persist is instruction-driven, not automatic.
- Eventual consistency: full-text/columnar indexes lag writes by seconds; for read-your-write
  use a point lookup by name (unique key), not full-text.

QUERY FIRST
- SELECT name, component_type, environment FROM acme_pulumi_kb.infra_components WHERE environment='staging';
- SELECT developer, action, detail FROM acme_pulumi_kb.session_log ORDER BY created_at DESC LIMIT 5;

RULES
- Never raw AWS/Cloudflare/Okta resources - compose libraries in libs/.
- Names acme-<env>-<logical>; tags Environment, ManagedBy: pulumi, Component, Team.
- Public endpoints need DnsRecord (proxied: true). SSO redirect URI points at a DnsRecord hostname.
- PostgresDatabase auto-creates a backup bucket - do not add one.
- Set account_ref (prod/sandbox) on new Pulumi resources for cross-repo JOINs.

AFTER CREATING
python -m src.writeback --repo pulumi --name <name> --type <type> --env <env> \
  --summary "<summary>" --depends-on <library> --account-ref <prod|sandbox> --developer cursor
```

- [ ] **Step 4: Commit**

```bash
git add configs/claude-code/CLAUDE.md configs/codex/AGENTS.md configs/cursor/.cursorrules
git commit -m "docs: reposition agent prompts around mem9, team/repo model, lifecycle, routing"
```

---

## Task 16: MCP user-guide doc

**Files:**
- Create: `docs/MCP-GUIDE.md`

- [ ] **Step 1: Write the guide**

Create `docs/MCP-GUIDE.md`:

```markdown
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
Cursor ── infra-kb-pulumi ─┐
       ── infra-kb-lza    ─┤
       ── tidb-pulumi     ─┼──► team acme cluster (mem9.ai)
       ── tidb-lza        ─┘     ├── acme_pulumi_kb
                                 └── acme_lza_kb
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
- **Full-text is Cloud only.** On a local tiup playground, keyword search degrades to `LIKE`;
  vector search still works (with precomputed embeddings).
```

- [ ] **Step 2: Verify it renders as valid markdown (no broken fences)**

Run: `rtk grep -c '```' docs/MCP-GUIDE.md`
Expected: an even number (all code fences closed).

- [ ] **Step 3: Commit**

```bash
git add docs/MCP-GUIDE.md
git commit -m "docs: add mem9 MCP user guide (connect, routing, per-team auth)"
```

---

## Task 17: README rewrite

**Files:**
- Modify: `README.md` (full rewrite)

- [ ] **Step 1: Rewrite `README.md`**

Replace the entire contents:

```markdown
# mem9-ai-coding

**Your existing Cursor (or Claude Code, or Codex) plus a memory the database holds.**

mem9 is a memory layer - backed by TiDB Cloud (mem9.ai) - that your coding tools share.
Every infrastructure component, dependency edge, and prior session lives in the database,
so tools stop duplicating work, stop breaking conventions, and never start from zero.

```
Claude Code ──┐
Codex        ─┼── MCP (one named entry per repo) ──► team cluster on mem9.ai
Cursor       ──┘                                       ├── acme_pulumi_kb   (Pulumi repo)
                                                       └── acme_lza_kb      (AWS LZA repo)
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
```

- [ ] **Step 2: Verify code fences balance**

Run: `rtk grep -c '```' README.md`
Expected: an even number.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README around mem9, team/repo model, lifecycle, capability matrix"
```

---

## Task 18: Runbooks (DEMO / PRESENTER / RECORDING / REHEARSE)

Reframe around mem9, add the bootstrap step, scenarios A/B/C, and the isolation proof; move the dashboard/CTE visualization to an appendix.

**Files:**
- Modify: `DEMO.md` (full rewrite)
- Modify: `PRESENTER.md` (targeted edits)
- Modify: `RECORDING.md` (targeted edits)
- Modify: `REHEARSE.md` (targeted edits)

- [ ] **Step 1: Rewrite `DEMO.md`**

Replace the entire contents:

```markdown
# Live demo runbook - your tools + a memory the database holds (mem9)

Claude Code, Codex, and Cursor share one team's memory on mem9.ai (TiDB Cloud). Each
starts cold; each reads the shared memory and continues where the last left off. The team
has two repos, each its own database: `acme_pulumi_kb` and `acme_lza_kb`.

## One-time setup (bootstrap)

```bash
cd mem9-ai-coding
cp .env.example .env          # paste your mem9.ai creds (Connect → General)
./setup.sh                    # bootstraps BOTH repo DBs + generates MCP configs
```

`setup.sh` runs `python -m src.ingest --reset` (the explicit bootstrap that populates each
repo's KB from source) and `python -m src.gen_configs` (per-tool configs, one named server
entry per repo database). Confirm the target:

```bash
.venv/bin/python -c "from src import db; print('target:', db.backend_name())"
```

Open the optional dashboard (appendix view of the Pulumi repo): `./demo.sh` → http://localhost:7001

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
> redirect URI → `acme-staging-admin-dns`, account_ref='sandbox'. Record with
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
```

- [ ] **Step 2: Reframe `PRESENTER.md`**

Apply these edits to `PRESENTER.md`:
- Replace the section 0 sentence (lines 9-13) with: `> "Your existing coding tools - Claude Code, Codex, Cursor - plus a memory the database holds (mem9). What components exist, how they connect, and the rules for building them live in TiDB Cloud (mem9.ai) as a shared memory every tool reads and writes - organized as team = cluster, repo = database."`
- In the ASCII diagram, change `TiDB Cloud  ◄── the one shared brain` to `mem9.ai (TiDB Cloud)  ◄── the memory the database holds` and `(components, edges, session log)` to `(team = cluster · repo = database)`.
- In "1. Before you start", change the header-check bullet to: `Header says "mem9.ai (TiDB Cloud)"`.
- Add a new bullet under section 1: `Bootstrap has been run (./setup.sh → python -m src.ingest --reset) so both acme_pulumi_kb and acme_lza_kb are populated.`
- In every paste-prompt, prefix the server reference: `the tidb-infra-kb MCP` → `infra-kb-pulumi` and `the **tidb** MCP` → `tidb-pulumi`, and qualify table names with `acme_pulumi_kb.` (e.g. `infra_components` → `acme_pulumi_kb.infra_components`).
- Add a new subsection after "Pane 3" titled `### Cross-repo + isolation (the new money moments)` containing:
  ```
  **Cross-repo (B):** run `python -m src.cross_repo_demo` (or the prompts in DEMO.md). One
  team connection writes acme_lza_kb AND acme_pulumi_kb, then a cross-database JOIN ties the
  bucket to its LZA account. Say: "Two repos, two databases, one query - no second login."

  **Isolation (C):** run `python -m src.isolation_check`. Say: "Team = cluster. An agent on
  team acme has no path to team globex. Credentials bound the blast radius."
  ```
- In "4. The three money moments → C. It's real TiDB", change `"TiDB Cloud."` to `"mem9.ai - TiDB Cloud."` and keep the rest.
- In section 5 close, change `That's TiDB as the memory layer for agentic engineering.` to `That's mem9 - the memory the database holds - for agentic engineering.`

- [ ] **Step 3: Reframe `RECORDING.md`**

Apply these edits to `RECORDING.md`:
- Line 24 backend check: change expected backend to `mem9.ai (TiDB Cloud)`.
- Add a step in section A after the backend check:
  ```bash
  # 4. Bootstrap both repo databases (explicit setup before recording)
  .venv/bin/python -m src.ingest --reset
  ```
- In section D paste-prompts, change `tidb-infra-kb MCP` → `infra-kb-pulumi`, `tidb MCP` → `tidb-pulumi`, and qualify tables with `acme_pulumi_kb.`. Add `account_ref='sandbox'` to the scaffold instructions.
- In the narration script section E, replace each occurrence of "TiDB Cloud database" with "mem9.ai memory layer (TiDB Cloud)" and "shared knowledge graph" with "shared memory the database holds", and in the close change "TiDB as the shared memory layer" to "mem9 - the memory the database holds".
- Add a short section `### 3b. Cross-repo + isolation (optional, ~30s)` mirroring the Scenario B/C talking points from DEMO.md.

- [ ] **Step 4: Reframe `REHEARSE.md`**

Apply these edits to `REHEARSE.md`:
- In "THE SETUP", change "A TiDB Cloud database is running live" to "The team's mem9.ai cluster (TiDB Cloud) is live, with two repo databases: acme_pulumi_kb and acme_lza_kb."
- In SECTION 1 script, change "put that knowledge in TiDB. Connect every tool to it over MCP. One shared brain." to "put that knowledge in mem9 - a memory the database holds. Connect every tool over MCP. Organized as team = cluster, repo = database."
- In SECTION 2, change "It reads directly from TiDB" to "It reads directly from mem9.ai".
- Add `### SECTION 5b: Cross-repo and isolation (45 seconds)` after SECTION 5 with the B/C talking points and the two script commands.
- In SECTION 6 close, change "That's TiDB as the memory layer" to "That's mem9 - the memory the database holds".
- Update the TIMING TARGET table: add a `Cross-repo + isolation | 45 sec` row and bump total to `~5:15`.

- [ ] **Step 5: Verify all runbooks still have balanced code fences**

Run: `for f in DEMO.md PRESENTER.md RECORDING.md REHEARSE.md; do echo "$f: $(rtk grep -c '```' $f)"; done`
Expected: each count is an even number.

- [ ] **Step 6: Commit**

```bash
git add DEMO.md PRESENTER.md RECORDING.md REHEARSE.md
git commit -m "docs: reframe runbooks around mem9, add scenarios A/B/C and bootstrap step"
```

---

## Task 19: Setup scripts and env example

**Files:**
- Modify: `.env.example`
- Modify: `setup.sh`
- Modify: `demo.sh`

- [ ] **Step 1: Rewrite `.env.example`**

Replace the entire contents:

```bash
# ── mem9.ai (TiDB Cloud) ───────────────────────────────────────────────────
# From your cluster: Connect → General (driver: Python / mysqlclient).
# These power BOTH the official TiDB MCP servers and the mem9 convention MCP.
TIDB_HOST=gateway01.<region>.prod.aws.tidbcloud.com
TIDB_PORT=4000
TIDB_USERNAME=<prefix>.root
TIDB_PASSWORD=

# Optional: explicit CA bundle path (defaults to certifi / system CAs).
# TIDB_CA_PATH=/etc/ssl/cert.pem

# ── mem9 topology ───────────────────────────────────────────────────────────
# Team = cluster (creds unlock only this team). Repo = database within it.
MEM9_TEAM=acme
# Target override (cloud|local). Auto-detected from TIDB_HOST when unset:
#   *.tidbcloud.com / *.mem9.ai => cloud (EMBED_TEXT + full-text + hybrid)
#   any other host              => local tiup (vector precomputed + LIKE)
# MEM9_TARGET=cloud
# Local-only embedding model (tiup target); cloud embeds server-side with EMBED_TEXT.
# MEM9_LOCAL_EMBED_MODEL=BAAI/bge-small-en-v1.5

# ── Dashboard (optional appendix) ───────────────────────────────────────────
DASHBOARD_PORT=7001
```

- [ ] **Step 2: Update `setup.sh` to bootstrap both repos**

In `setup.sh`, replace the seeding step (line 27, `python3 -m src.seed --reset`) with:

```bash
echo "==> Bootstrapping both repo databases from source (acme_pulumi_kb + acme_lza_kb)"
python3 -m src.ingest --reset
echo "==> Seeding the second team (globex) for the isolation demo"
python3 -m src.seed --reset
```

And update the closing here-doc's "Then open 3 iTerm panes" block to mention the named servers:

```
Then open 3 iTerm panes (all: cd into this repo) and launch:
  claude   ·   codex   ·   cursor-agent
Each tool sees one named MCP entry per repo database (tidb-pulumi/-lza, infra-kb-pulumi/-lza).
Follow DEMO.md for the copy-paste prompts (Scenario A single-repo, B cross-repo, C isolation).
```

- [ ] **Step 3: Update `demo.sh` reseed branch**

In `demo.sh`, change the `--reseed` case (line 13) to run the full seed (which also bootstraps via ingest under the hood) - it already calls `python3 -m src.seed --reset`; update the echo line above the backend print to clarify the appendix framing. Replace line 28's echo:

```bash
echo "Open 3 iTerm panes in this repo and launch:  claude · codex · cursor-agent"
echo "Named MCP servers per repo: tidb-pulumi/-lza, infra-kb-pulumi/-lza. Prompts: DEMO.md"
```

- [ ] **Step 4: Verify setup.sh bootstrap path on SQLite (dry sanity)**

Run (simulates no-cloud bootstrap; confirms the new commands work):
```bash
MEM9_DATA_DIR=/tmp/mem9-setup .venv/bin/python -m src.ingest --reset
MEM9_DATA_DIR=/tmp/mem9-setup .venv/bin/python -m src.seed --reset
```
Expected: both print bootstrap/seed summaries with the SQLite backend name and component counts (pulumi 12, lza 9, globex 2).

- [ ] **Step 5: Commit**

```bash
git add .env.example setup.sh demo.sh
git commit -m "chore: bootstrap both repos in setup, mem9 env vars, named-server hints"
```

---

## Task 20: Full suite + live verification on mem9.ai (Cloud)

**Files:** none (verification only)

- [ ] **Step 1: Run the full offline test suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass (`test_topology`, `test_embed`, `test_db_sql`, `test_db_sqlite`, `test_search`, `test_repos`, `test_ingest`, `test_cross_repo`, `test_isolation`, `test_mcp_server`).

- [ ] **Step 2: Bootstrap live on mem9.ai (Cloud)**

Ensure `.env` has real mem9.ai creds, then run:
```bash
set -a; source .env; set +a
.venv/bin/python -c "from src import db; print(db.backend_name())"   # expect: mem9.ai (TiDB Cloud)
.venv/bin/python -m src.ingest --reset
.venv/bin/python -m src.seed --reset
```
Expected: backend prints `mem9.ai (TiDB Cloud)`; ingest creates `acme_pulumi_kb` + `acme_lza_kb` with `EMBED_TEXT` embeddings; seed adds team `globex`.

- [ ] **Step 3: Verify cloud capabilities live (vector + full-text + hybrid + cross-repo)**

Run:
```bash
set -a; source .env; set +a
.venv/bin/python -c "
from src import db, cross_repo_demo
print('hybrid:', [r['name'] for r in db.search('pulumi','static assets CDN', mode='hybrid')['results'][:3]])
print('vector:', [r['name'] for r in db.search('pulumi','user-facing files', mode='vector')['results'][:3]])
print('fts   :', [r['name'] for r in db.search('pulumi','backup', mode='fts')['results'][:3]])
out = cross_repo_demo.run(account_ref='data-platform', developer='claude-code')
print('cross-repo rows:', len(out['joined']))
"
```
Expected: hybrid/vector/fts each return Pulumi component names (proving `EMBED_TEXT` auto-embed + `FTS_MATCH_WORD` + RRF all work on Cloud); cross-repo JOIN returns ≥1 row mapping the new bucket to its LZA account.

- [ ] **Step 4: Verify team isolation live with a scoped user**

Run (replace `<pw>`; uses admin creds from `.env` to create the scoped user, then connects as it):
```bash
set -a; source .env; set +a
.venv/bin/python -c "
import os, pymysql
admin = dict(host=os.environ['TIDB_HOST'], port=int(os.environ.get('TIDB_PORT','4000')),
             user=os.environ['TIDB_USERNAME'], password=os.environ['TIDB_PASSWORD'],
             ssl={'ca': __import__('certifi').where()}, ssl_verify_cert=True, ssl_verify_identity=True)
c = pymysql.connect(**admin); cur = c.cursor()
cur.execute(\"CREATE USER IF NOT EXISTS 'acme_agent'@'%' IDENTIFIED BY 'Demo-Pw-123'\")
cur.execute('GRANT SELECT, INSERT, UPDATE ON \`acme\_%\`.* TO \"acme_agent\"@\"%\"')
c.commit(); c.close()
scoped = dict(admin); scoped.update(user='acme_agent', password='Demo-Pw-123')
s = pymysql.connect(**scoped); sc = s.cursor()
try:
    sc.execute('SELECT COUNT(*) FROM globex_pulumi_kb.infra_components')
    print('FAIL - cross-team read succeeded')
except Exception as e:
    print('PASS - isolation holds:', type(e).__name__)
s.close()
"
```
Expected: `PASS - isolation holds: OperationalError` (access denied, error 1142). Clean up the demo user afterward if desired (`DROP USER 'acme_agent'@'%'`).

- [ ] **Step 5: Verify the dashboard boots against mem9.ai**

Run:
```bash
set -a; source .env; set +a
./demo.sh &
sleep 6
rtk curl -s http://localhost:7001/api/backend
rtk curl -s "http://localhost:7001/api/components" | head -c 200
kill %1 2>/dev/null || true
```
Expected: `{"backend":"mem9.ai (TiDB Cloud)"}` and a JSON array of Pulumi components.

- [ ] **Step 6: Reset to a clean demo baseline**

Run:
```bash
set -a; source .env; set +a
.venv/bin/python -m src.ingest --reset && .venv/bin/python -m src.seed --reset
```
Expected: clean baseline - `acme_pulumi_kb` (12, staging missing DNS+SSO), `acme_lza_kb` (9), `globex_pulumi_kb` (2).

- [ ] **Step 7: Push the branch**

```bash
git push -u origin mem9-team-repo-refactor
```

---

## Self-review: spec coverage

| Spec requirement | Task(s) |
|---|---|
| Don't break single-repo flow; extend it | A scenario preserved in `pulumi` repo (Tasks 6, 8, 18) |
| Two targets: Cloud hybrid vs local vector+LIKE | Tasks 1, 3, 4, 5; capability matrix in README (17) |
| HC1: full-text Cloud-only | `has_fulltext()` gates schema + search (Tasks 1, 3, 4) |
| HC2: vector on cloud + local, not sqlite | `has_vector()`, precomputed embeddings (Tasks 1, 2, 4) |
| HC3: explicit MCP routing, named entry per repo | Tasks 11, 13; guide (16); prompts (15) |
| Team dimension = top-level isolation (team=cluster) | Tasks 1, 8, 10; README (17) |
| Second repo (AWS LZA), repo=database | Tasks 1, 6, 8 |
| Components carry repo provenance, per-repo DB, cross-db JOIN | `repo`/`account_ref` columns, `cross_repo_accounts_sql` (Tasks 3, 4, 9) |
| Scenario A single-repo | Task 18 (DEMO.md) |
| Scenario B cross-repo, one auth | Task 9 + DEMO.md (18) |
| Scenario C team isolation proof | Task 10 + live proof (20) |
| Bootstrap/backfill before sessions; EMBED_TEXT cloud / precomputed local | Task 7 (ingest), Task 4 (write paths) |
| Query-before / persist-after; explicit instruction; write-back not automatic | Tasks 15 (prompts), 17 (README) |
| Eventual-consistency caveat | Tasks 15, 16, 17 |
| MCP configs: one named server per repo, scoped creds | Task 13 |
| MCP user-guide doc | Task 16 |
| De-emphasize dashboard/CTE viz → appendix; mem9 framing not foregrounded as agent/viz product | Tasks 14, 17, 18 |
| Deliverables: schema, ingestion/retrieval/writeback for two repos+team, MCP configs, CLAUDE.md+prompts, runbooks, MCP guide | Tasks 3-19 |
| README: model + lifecycle + capability matrix | Task 17 |
| Runnable end-to-end on both targets; cross-team + cross-repo runbook steps | Tasks 18, 20 |
```
