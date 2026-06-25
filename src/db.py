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


# ── Schema + SQL builders (pure, target-aware, fully qualified) ───────────────
#
# Every table reference is qualified with the repo's database name so the same
# query text runs on TiDB (db.table) and SQLite (ATTACH ... AS db).


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
            cur = _run(con, sql, base + (embed_text, EMBED_MODEL))
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
