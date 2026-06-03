"""Infrastructure knowledge base.

Backend is chosen at runtime:
  - TiDB Cloud Serverless (MySQL protocol, TLS) when TIDB_HOST is configured
  - SQLite fallback otherwise, so the dashboard still runs with no network

Every recursive-CTE traversal is ANSI SQL that runs unchanged on both engines.
On TiDB the same query benefits from the distributed SQL engine and can join
against VEC_COSINE_DISTANCE for hybrid graph + vector retrieval.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=False)
except Exception:
    pass

DB_PATH = Path(__file__).parent.parent / "kb.db"
_TIDB_DISABLED_REASON: str | None = None


def using_tidb() -> bool:
    return bool(os.environ.get("TIDB_HOST")) and _TIDB_DISABLED_REASON is None


def backend_name() -> str:
    if using_tidb():
        return "TiDB Cloud Serverless"
    if _TIDB_DISABLED_REASON:
        return f"SQLite (local fallback; TiDB unavailable: {_TIDB_DISABLED_REASON})"
    return "SQLite (local fallback)"


# ── Schema (per dialect) ─────────────────────────────────────────────────────

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS infra_components (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT UNIQUE NOT NULL,
    component_type TEXT NOT NULL,
    environment    TEXT NOT NULL,
    repo_path      TEXT,
    summary        TEXT,
    code_excerpt   TEXT,
    created_by     TEXT DEFAULT 'seed',
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS component_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL, to_id INTEGER NOT NULL,
    relationship TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS session_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    developer TEXT NOT NULL, action TEXT NOT NULL, detail TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# TiDB: add a VECTOR column so the official TiDB MCP can demo VEC_COSINE_DISTANCE.
_TIDB_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS infra_components (
        id             BIGINT PRIMARY KEY AUTO_INCREMENT,
        name           VARCHAR(191) UNIQUE NOT NULL,
        component_type VARCHAR(32) NOT NULL,
        environment    VARCHAR(32) NOT NULL,
        repo_path      VARCHAR(255),
        summary        TEXT,
        code_excerpt   TEXT,
        created_by     VARCHAR(64) DEFAULT 'seed',
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS component_edges (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        from_id BIGINT NOT NULL, to_id BIGINT NOT NULL,
        relationship VARCHAR(32) NOT NULL, note VARCHAR(255)
    )""",
    """CREATE TABLE IF NOT EXISTS session_log (
        id BIGINT PRIMARY KEY AUTO_INCREMENT,
        developer VARCHAR(64) NOT NULL, action VARCHAR(32) NOT NULL, detail TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]


# ── Connection ───────────────────────────────────────────────────────────────

@contextmanager
def _tidb_conn():
    import pymysql
    con = pymysql.connect(
        host=os.environ["TIDB_HOST"],
        port=int(os.environ.get("TIDB_PORT", "4000")),
        user=os.environ["TIDB_USERNAME"],
        password=os.environ.get("TIDB_PASSWORD", ""),
        database=os.environ.get("TIDB_DATABASE", "test"),
        ssl_verify_cert=True,
        ssl_verify_identity=True,
        ssl={"ca": os.environ.get("TIDB_CA_PATH") or _default_ca()},
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
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


def _disable_tidb(exc: Exception) -> None:
    global _TIDB_DISABLED_REASON
    if _TIDB_DISABLED_REASON is None:
        _TIDB_DISABLED_REASON = str(exc)


@contextmanager
def _sqlite_conn():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _ph(sql: str) -> str:
    """SQLite uses ? placeholders; pymysql uses %s. Author with ? and translate."""
    return sql if not using_tidb() else sql.replace("?", "%s")


def _run(con, sql: str, params: tuple = ()):
    if using_tidb():
        cur = con.cursor()
        # Only pass args when present; otherwise pymysql still runs `sql % args`
        # and any literal % in the SQL would raise a format error.
        if params:
            cur.execute(_ph(sql), params)
        else:
            cur.execute(sql)
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


def _lastrowid(con, cur) -> int:
    return cur.lastrowid


# ── Lifecycle ────────────────────────────────────────────────────────────────

def init_db() -> None:
    if using_tidb():
        try:
            with _tidb_conn() as con:
                cur = con.cursor()
                for stmt in _TIDB_SCHEMA:
                    cur.execute(stmt)
            return
        except Exception as exc:
            _disable_tidb(exc)

    with _sqlite_conn() as con:
        con.executescript(_SQLITE_SCHEMA)


def reset_db() -> None:
    if using_tidb():
        try:
            with _tidb_conn() as con:
                cur = con.cursor()
                for t in ("component_edges", "session_log", "infra_components"):
                    cur.execute(f"DROP TABLE IF EXISTS {t}")
                for stmt in _TIDB_SCHEMA:
                    cur.execute(stmt)
            return
        except Exception as exc:
            _disable_tidb(exc)

    with _sqlite_conn() as con:
        con.executescript(
            "DROP TABLE IF EXISTS component_edges;"
            "DROP TABLE IF EXISTS session_log;"
            "DROP TABLE IF EXISTS infra_components;" + _SQLITE_SCHEMA
        )


@contextmanager
def _conn():
    if using_tidb():
        with _tidb_conn() as c:
            yield c
    else:
        with _sqlite_conn() as c:
            yield c


# ── Reads ────────────────────────────────────────────────────────────────────

def query(sql: str) -> list[dict]:
    """Execute a read-only SELECT/WITH and return rows as dicts."""
    meaningful = [ln for ln in sql.strip().splitlines()
                  if ln.strip() and not ln.strip().startswith("--")]
    head = meaningful[0].upper() if meaningful else ""
    if not head.startswith("SELECT") and not head.startswith("WITH"):
        raise ValueError("Only SELECT / WITH queries are allowed via query()")
    with _conn() as con:
        return _rows(_run(con, sql))


# ── Writes ───────────────────────────────────────────────────────────────────

def write_component(
    *, name: str, type: str, env: str, summary: str,
    depends_on: str | None = None, relationship: str = "uses",
    developer: str, repo_path: str | None = None, code_excerpt: str | None = None,
) -> int:
    with _conn() as con:
        if using_tidb():
            cur = _run(con,
                "INSERT INTO infra_components"
                " (name, component_type, environment, repo_path, summary, code_excerpt, created_by)"
                " VALUES (?,?,?,?,?,?,?)"
                " ON DUPLICATE KEY UPDATE component_type=VALUES(component_type),"
                " environment=VALUES(environment), repo_path=VALUES(repo_path),"
                " summary=VALUES(summary), code_excerpt=VALUES(code_excerpt),"
                " created_by=VALUES(created_by)",
                (name, type, env, repo_path, summary, code_excerpt, developer))
            row = _rows(_run(con, "SELECT id FROM infra_components WHERE name=?", (name,)))
            comp_id = row[0]["id"] if row else cur.lastrowid
        else:
            cur = _run(con,
                "INSERT OR REPLACE INTO infra_components"
                " (name, component_type, environment, repo_path, summary, code_excerpt, created_by)"
                " VALUES (?,?,?,?,?,?,?)",
                (name, type, env, repo_path, summary, code_excerpt, developer))
            comp_id = cur.lastrowid

        if depends_on:
            dep = _rows(_run(con, "SELECT id FROM infra_components WHERE name=?", (depends_on,)))
            if dep:
                _run(con,
                    "INSERT INTO component_edges (from_id, to_id, relationship, note) VALUES (?,?,?,?)",
                    (comp_id, dep[0]["id"], relationship, f"{name} {relationship} {depends_on}"))

        _run(con, "INSERT INTO session_log (developer, action, detail) VALUES (?,?,?)",
             (developer, "created", f"Created {type} component '{name}' in {env}"))
        return comp_id


def write_edge(from_name: str, to_name: str, relationship: str, note: str = "") -> None:
    with _conn() as con:
        f = _rows(_run(con, "SELECT id FROM infra_components WHERE name=?", (from_name,)))
        t = _rows(_run(con, "SELECT id FROM infra_components WHERE name=?", (to_name,)))
        if f and t:
            _run(con, "INSERT INTO component_edges (from_id, to_id, relationship, note) VALUES (?,?,?,?)",
                 (f[0]["id"], t[0]["id"], relationship, note))


def log(developer: str, action: str, detail: str) -> None:
    with _conn() as con:
        _run(con, "INSERT INTO session_log (developer, action, detail) VALUES (?,?,?)",
             (developer, action, detail))


def log_query(developer: str, detail: str) -> None:
    log(developer, "queried", detail)


# ── Recursive CTE traversals (identical SQL on SQLite + TiDB) ─────────────────

CTE_DEPENDENCIES_SQL = """\
-- What does '{name}' transitively depend on? (downstream traversal)
WITH RECURSIVE deps(from_id, to_id, relationship, depth) AS (
    SELECT e.from_id, e.to_id, e.relationship, 1
    FROM component_edges e
    JOIN infra_components c ON e.from_id = c.id
    WHERE c.name = '{name}'
  UNION ALL
    SELECT e.from_id, e.to_id, e.relationship, d.depth + 1
    FROM component_edges e
    JOIN deps d ON e.from_id = d.to_id
    WHERE d.depth < 10
)
SELECT DISTINCT d.depth, cf.name AS from_name,
       d.relationship, ct.name AS to_name,
       ct.component_type, ct.environment
FROM deps d
JOIN infra_components cf ON d.from_id = cf.id
JOIN infra_components ct ON d.to_id = ct.id
ORDER BY d.depth, to_name;"""

CTE_BLAST_RADIUS_SQL = """\
-- What breaks if '{name}' changes? (upstream blast-radius traversal)
WITH RECURSIVE blast(from_id, to_id, relationship, depth) AS (
    SELECT e.from_id, e.to_id, e.relationship, 1
    FROM component_edges e
    JOIN infra_components c ON e.to_id = c.id
    WHERE c.name = '{name}'
  UNION ALL
    SELECT e.from_id, e.to_id, e.relationship, b.depth + 1
    FROM component_edges e
    JOIN blast b ON e.to_id = b.from_id
    WHERE b.depth < 10
)
SELECT DISTINCT b.depth, cf.name AS from_name,
       b.relationship, ct.name AS to_name,
       cf.component_type, cf.environment
FROM blast b
JOIN infra_components cf ON b.from_id = cf.id
JOIN infra_components ct ON b.to_id = ct.id
ORDER BY b.depth, from_name;"""


def _resolve(name: str) -> str:
    return name.replace("'", "").strip()


def cte_dependencies(name: str) -> dict:
    safe = _resolve(name)
    sql = CTE_DEPENDENCIES_SQL.format(name=safe)
    rows = query(sql)
    return {"sql": sql, "rows": rows, "nodes": _nodes_in(rows, safe)}


def cte_blast_radius(name: str) -> dict:
    safe = _resolve(name)
    sql = CTE_BLAST_RADIUS_SQL.format(name=safe)
    rows = query(sql)
    return {"sql": sql, "rows": rows, "nodes": _nodes_in(rows, safe)}


def _nodes_in(rows: list[dict], root: str) -> list[str]:
    names = {root}
    for r in rows:
        names.add(r["from_name"]); names.add(r["to_name"])
    return sorted(names)
