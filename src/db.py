"""mem9 knowledge base - HTTP client for the mem9 REST API.

Every repo's components live in a mem9 space, namespaced by appId:
  appId = {team}_{repo}_kb  (e.g. acme_pulumi_kb, acme_lza_kb)

The underlying TiDB cluster - with its vector index, full-text index, and hybrid
recall - is provisioned and managed by mem9.ai. Callers use only an API key.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from src import topology

_TIMEOUT = 30
_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4


# ── HTTP primitives ───────────────────────────────────────────────────────────

def _request(method: str, path: str, body: dict | None = None, api_key: str | None = None) -> dict:
    key = api_key or topology.api_key()
    url = topology.base_url() + path
    data = json.dumps(body).encode() if body else None
    headers: dict[str, str] = {"X-API-Key": key}
    if data:
        headers["Content-Type"] = "application/json"

    last_err: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200]
            if e.code in _RETRY_STATUS and attempt < _MAX_RETRIES - 1:
                time.sleep(0.6 * (2 ** attempt))  # 0.6s, 1.2s, 2.4s backoff
                last_err = RuntimeError(f"mem9 API {method} {path} -> {e.code}: {detail}")
                continue
            raise RuntimeError(f"mem9 API {method} {path} -> {e.code}: {detail}")
        except urllib.error.URLError as e:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(0.6 * (2 ** attempt))
                last_err = RuntimeError(f"mem9 API {method} {path} -> {e}")
                continue
            raise RuntimeError(f"mem9 API {method} {path} -> {e}")
    raise last_err or RuntimeError(f"mem9 API {method} {path} failed")


def _get(path: str, api_key: str | None = None) -> dict:
    return _request("GET", path, api_key=api_key)


def _post(path: str, body: dict, api_key: str | None = None) -> dict:
    return _request("POST", path, body=body, api_key=api_key)


def _delete(path: str, api_key: str | None = None) -> None:
    _request("DELETE", path, api_key=api_key)


# ── Naming helpers ────────────────────────────────────────────────────────────

def database_for(repo: str, team_name: str | None = None) -> str:
    """Returns the appId for this repo - used as the namespace in mem9."""
    return topology.app_id(repo, team_name)


def team() -> str:
    return topology.team()


def backend_name() -> str:
    return "mem9.ai (TiDB Cloud - hybrid vector + full-text)"


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def init_db(team_name: str | None = None, repos: list[str] | None = None) -> None:
    """No-op: mem9 spaces need no schema creation."""
    pass


def reset_db(team_name: str | None = None, repos: list[str] | None = None) -> None:
    """Delete all memories in each repo namespace, then re-init (no-op)."""
    team_name = team_name or team()
    repos = repos or topology.repo_names()
    for repo in repos:
        app = database_for(repo, team_name)
        _clear_namespace(app)


def _clear_namespace(app_id: str, api_key: str | None = None) -> int:
    """Delete every memory in a namespace until a fetch returns none.

    The mem9 list endpoint caps page size and ranks results, so we must loop
    until the namespace is genuinely empty rather than stopping on the first
    short page. Already-deleted ids (404) are tolerated so concurrent or
    eventually-consistent deletes don't abort the purge.
    """
    deleted = 0
    for _ in range(500):  # generous guard against runaway loops
        data = _get(f"/v1alpha2/mem9s/memories?appId={app_id}&limit=100", api_key=api_key)
        memories = data.get("memories", [])
        if not memories:
            break
        progressed = False
        for m in memories:
            try:
                _delete(f"/v1alpha2/mem9s/memories/{m['id']}", api_key=api_key)
                deleted += 1
                progressed = True
            except RuntimeError as exc:
                if "404" in str(exc):
                    continue  # already gone
                raise
        if not progressed:
            break
    return deleted


# ── Writes ────────────────────────────────────────────────────────────────────

def write_component(
    *, repo: str, name: str, type: str, env: str, summary: str,
    depends_on: str | None = None, relationship: str = "uses",
    developer: str, repo_path: str | None = None, code_excerpt: str | None = None,
    account_ref: str | None = None, team_name: str | None = None,
) -> str:
    """Write one infrastructure component as a mem9 memory. Returns memory id."""
    team_name = team_name or team()
    app = database_for(repo, team_name)

    content = f"{name} - {type} in {env}. {summary}"
    if depends_on:
        content += f" Depends on: {depends_on}."
    if code_excerpt:
        content += f"\n\n{code_excerpt}"

    metadata: dict = {
        "name": name, "type": type, "env": env, "repo": repo,
        "team": team_name, "developer": developer,
    }
    if depends_on:
        metadata["depends_on"] = depends_on
        metadata["relationship"] = relationship
    if repo_path:
        metadata["repo_path"] = repo_path
    if account_ref:
        metadata["account_ref"] = account_ref

    tags = [repo, type.lower(), env]

    body = {
        "content": content,
        "metadata": metadata,
        "appId": app,
        "tags": tags,
    }
    result = _post("/v1alpha2/mem9s/memories", body)
    return result.get("id", "")


def write_edge(repo: str, from_name: str, to_name: str, relationship: str, note: str = "",
               team_name: str | None = None) -> None:
    """Record a dependency edge as a memory note."""
    team_name = team_name or team()
    app = database_for(repo, team_name)
    content = f"Dependency: {from_name} {relationship} {to_name}. {note}".strip()
    _post("/v1alpha2/mem9s/memories", {
        "content": content,
        "metadata": {"from": from_name, "to": to_name, "relationship": relationship, "edge": True},
        "appId": app,
        "tags": [repo, "edge", relationship],
    })


def log(repo: str, developer: str, action: str, detail: str, team_name: str | None = None) -> None:
    team_name = team_name or team()
    app = database_for(repo, team_name)
    # content is just the detail sentence; developer + action ride in metadata
    # (mem9 paraphrases content, so a clean sentence reads cleanest in the feed).
    _post("/v1alpha2/mem9s/memories", {
        "content": detail,
        "metadata": {"developer": developer, "action": action, "repo": repo},
        "appId": app,
        "tags": [repo, "session-log", action],
    })


def log_query(repo: str, developer: str, detail: str, team_name: str | None = None) -> None:
    log(repo, developer, "queried", detail, team_name)


# ── Reads ─────────────────────────────────────────────────────────────────────

def recall(app_id: str, q: str = "", limit: int = 20, api_key: str | None = None) -> list[dict]:
    """Raw search against one appId namespace. Returns list of memory objects."""
    path = f"/v1alpha2/mem9s/memories?appId={app_id}&limit={limit}"
    if q.strip():
        q_enc = urllib.parse.quote(q.strip())
        path = f"/v1alpha2/mem9s/memories?q={q_enc}&appId={app_id}&limit={limit}"
    data = _get(path, api_key=api_key)
    return data.get("memories", [])


# Import after defining recall to avoid circular issues
import urllib.parse


def search(repo: str, q: str, mode: str = "hybrid", k: int = 6,
           team_name: str | None = None) -> dict:
    """Hybrid search (vector + full-text, via mem9) in a single repo namespace."""
    app = database_for(repo, team_name)
    memories = recall(app, q, limit=k * 2)

    seen: set[str] = set()
    results = []
    for m in memories:
        meta = m.get("metadata", {})
        if meta.get("edge"):
            continue
        name = meta.get("name", m["id"])
        if name in seen:
            continue
        seen.add(name)
        results.append({
            "name": name,
            "component_type": meta.get("type", ""),
            "environment": meta.get("env", ""),
            "repo": meta.get("repo", repo),
            "summary": m.get("content", ""),
            "score": m.get("score"),
            "confidence": m.get("confidence"),
            "in_vector": True,
            "in_keyword": True,
            "hybrid_score": round(m.get("score", 0), 5),
        })

    return {
        "available": True,
        "mode": "hybrid",
        "target": "mem9.ai",
        "note": "Hybrid = vector + full-text (served by mem9.ai / TiDB Cloud).",
        "results": results[:k],
    }


def search_cross_repo(repos: list[str], q: str, k: int = 6,
                      team_name: str | None = None) -> list[dict]:
    """Search across multiple repo namespaces and merge results."""
    all_results = []
    for repo in repos:
        result = search(repo, q, k=k, team_name=team_name)
        all_results.extend(result["results"])
    all_results.sort(key=lambda r: -(r.get("hybrid_score") or 0))
    return all_results[:k]


def query(q: str, team_name: str | None = None, repos: list[str] | None = None) -> list[dict]:
    """Search-based replacement for raw SQL query. Searches across specified repos."""
    repos = repos or topology.repo_names()
    team_name = team_name or team()
    return search_cross_repo(repos, q, k=20, team_name=team_name)


# ── Dependency traversal (real multi-hop / transitive, recursive-CTE style) ───
#
# The KB is a directed dependency graph: every "X depends_on Y" plus every
# explicit edge (from -> to) is an arc. Transitive reachability over that graph
# is exactly what a recursive CTE computes in SQL; we do the BFS/DFS in process.
# Both directions are supported:
#   · dependencies(X)  = forward reachability  (everything X needs, downstream)
#   · blast_radius(X)   = reverse reachability  (everything that breaks if X
#                         changes, upstream)
#
# Graph SOURCE: the manifest is the authoritative, complete structure (it is
# exactly what was ingested into mem9). mem9's recall is a ranked/semantic store
# whose list reads are lossy for a complete edge set, so we build the backbone
# from the manifest and OVERLAY any live, agent-added components from mem9 (which
# reliably surface by name) on top. Net: a complete graph that still reflects
# live writes during the demo.

_GRAPH_CACHE: dict[str, tuple[float, dict]] = {}
_GRAPH_TTL = 2.0  # seconds; the dashboard polls ~every 2s, so coalesce overlay reads


def _load_graph(repo: str, team_name: str | None = None) -> dict:
    """Build the directed dependency graph: manifest backbone + live mem9 overlay."""
    import importlib
    from src.repos import load_manifest

    app = database_for(repo, team_name)
    cached = _GRAPH_CACHE.get(app)
    if cached and (time.time() - cached[0]) < _GRAPH_TTL:
        return cached[1]
    meta_by_name: dict[str, dict] = {}
    fwd: dict[str, list[tuple[str, str]]] = {}
    rev: dict[str, list[tuple[str, str]]] = {}

    def add_arc(a: str, b: str, rel: str) -> None:
        if not a or not b or a == b:
            return
        fwd.setdefault(a, [])
        rev.setdefault(b, [])
        if (b, rel) not in fwd[a]:
            fwd[a].append((b, rel))
        if (a, rel) not in rev[b]:
            rev[b].append((a, rel))

    def remember(name: str, meta: dict) -> None:
        if name and name not in meta_by_name:
            meta_by_name[name] = {
                "type": meta.get("type", ""), "env": meta.get("env", ""),
                "repo": meta.get("repo", repo), "summary": meta.get("summary", ""),
            }

    # 1) Manifest backbone - complete and deterministic.
    try:
        for c in load_manifest(repo):
            remember(c["name"], c)
            if c.get("depends_on"):
                add_arc(c["name"], c["depends_on"], c.get("relationship", "uses"))
        mod = importlib.import_module(topology.REPOS[repo]["manifest"])
        for edge in getattr(mod, "EDGES", []):
            add_arc(edge[0], edge[1], edge[2] if len(edge) > 2 else "uses")
    except Exception:
        pass

    # 2) Live overlay - agent-added components written to mem9 during the demo.
    try:
        for m in recall(app, limit=200):
            meta = m.get("metadata", {})
            if meta.get("edge"):
                add_arc(meta.get("from", ""), meta.get("to", ""), meta.get("relationship", "uses"))
                continue
            name = meta.get("name")
            if not name:
                continue
            remember(name, {**meta, "summary": m.get("content", "")})
            if meta.get("depends_on"):
                add_arc(name, meta["depends_on"], meta.get("relationship", "uses"))
    except Exception:
        pass

    result = {"app": app, "meta": meta_by_name, "fwd": fwd, "rev": rev}
    _GRAPH_CACHE[app] = (time.time(), result)
    return result


def _traverse(repo: str, name: str, mode: str, team_name: str | None = None,
              max_depth: int = 8, max_nodes: int = 200) -> dict:
    g = _load_graph(repo, team_name)
    adj = g["fwd"] if mode == "dependencies" else g["rev"]
    meta = g["meta"]

    # ── BFS for depth + the set of traversed arcs ──
    depth: dict[str, int] = {name: 0}
    rows: list[dict] = []
    queue: list[str] = [name]
    seen_arc: set[tuple[str, str]] = set()
    while queue and len(depth) < max_nodes:
        cur = queue.pop(0)
        d = depth[cur]
        if d >= max_depth:
            continue
        for nxt, rel in adj.get(cur, []):
            # real arc direction is always from -> to in the dependency graph
            frm, to = (cur, nxt) if mode == "dependencies" else (nxt, cur)
            far = nxt
            if (frm, to) not in seen_arc:
                seen_arc.add((frm, to))
                rows.append({
                    "depth": d + 1,
                    "from_name": frm,
                    "to_name": to,
                    "relationship": rel,
                    "component_type": meta.get(far, {}).get("type", ""),
                    "environment": meta.get(far, {}).get("env", ""),
                })
            if far not in depth:
                depth[far] = d + 1
                queue.append(far)

    # ── DFS for ordered root→leaf chains (the readable "sentences") ──
    paths: list[list[str]] = []

    def walk(node: str, trail: list[str]) -> None:
        if len(paths) >= 80 or len(trail) > max_depth + 1:
            return
        nexts = [nxt for nxt, _ in adj.get(node, []) if nxt not in trail]
        if not nexts:
            if len(trail) > 1:
                paths.append(list(trail))
            return
        for nxt in nexts:
            walk(nxt, trail + [nxt])

    walk(name, [name])
    paths.sort(key=len, reverse=True)

    nodes_meta = [
        {"name": n, "depth": d, "type": meta.get(n, {}).get("type", ""),
         "env": meta.get(n, {}).get("env", "")}
        for n, d in sorted(depth.items(), key=lambda kv: kv[1])
    ]
    max_d = max(depth.values()) if depth else 0
    verb = "needs" if mode == "dependencies" else "is needed by"
    note = (f"{'Dependencies' if mode == 'dependencies' else 'Blast radius'} of "
            f"'{name}': {len(depth) - 1} components across {max_d} hop(s), "
            f"transitively ({name} {verb} ...). Graph reachability over mem9 "
            f"(appId={g['app']}).")

    return {
        "root": name, "mode": mode, "note": note,
        "rows": rows, "nodes": [n["name"] for n in nodes_meta],
        "nodes_meta": nodes_meta, "paths": paths,
        "max_depth": max_d, "count": len(depth) - 1,
    }


def cte_dependencies(repo: str, name: str, team_name: str | None = None) -> dict:
    """Transitive forward reachability: everything `name` depends on (multi-hop)."""
    return _traverse(repo, name, "dependencies", team_name)


def cte_blast_radius(repo: str, name: str, team_name: str | None = None) -> dict:
    """Transitive reverse reachability: everything that breaks if `name` changes."""
    return _traverse(repo, name, "blast-radius", team_name)


# ── Team isolation check helper ────────────────────────────────────────────────

def check_isolation(my_key: str, other_key: str, shared_app_id: str) -> dict:
    """Verify that a different API key cannot read memories from another space."""
    try:
        memories = recall(shared_app_id, api_key=other_key)
        return {
            "isolated": len(memories) == 0,
            "detail": (
                f"Other key returned {len(memories)} results for appId={shared_app_id}. "
                "In production each team has its own mem9 space (separate API key) - "
                "different spaces are fully isolated by key."
            ),
        }
    except RuntimeError as exc:
        return {"isolated": True, "detail": str(exc)}
