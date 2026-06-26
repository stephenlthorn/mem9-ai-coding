"""mem9 knowledge base - HTTP client for the mem9 REST API.

Every repo's components live in a mem9 space, namespaced by appId:
  appId = {team}_{repo}_kb  (e.g. acme_pulumi_kb, acme_lza_kb)

The underlying TiDB cluster - with its vector index, full-text index, and hybrid
recall - is provisioned and managed by mem9.ai. Callers use only an API key.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from src import topology

_TIMEOUT = 30


# ── HTTP primitives ───────────────────────────────────────────────────────────

def _request(method: str, path: str, body: dict | None = None, api_key: str | None = None) -> dict:
    key = api_key or topology.api_key()
    url = topology.base_url() + path
    data = json.dumps(body).encode() if body else None
    headers: dict[str, str] = {"X-API-Key": key}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"mem9 API {method} {path} -> {e.code}: {e.read().decode()[:200]}")


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
    """Delete every memory in a namespace. Returns count deleted."""
    deleted = 0
    limit = 50
    while True:
        data = _get(f"/v1alpha2/mem9s/memories?appId={app_id}&limit={limit}", api_key=api_key)
        memories = data.get("memories", [])
        if not memories:
            break
        for m in memories:
            _delete(f"/v1alpha2/mem9s/memories/{m['id']}", api_key=api_key)
            deleted += 1
        if len(memories) < limit:
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
    _post("/v1alpha2/mem9s/memories", {
        "content": f"[{action}] {developer}: {detail}",
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


# ── Dependency traversal (metadata-based, not SQL CTE) ────────────────────────

def cte_dependencies(repo: str, name: str, team_name: str | None = None) -> dict:
    """Find what a component depends on via metadata search."""
    app = database_for(repo, team_name)
    memories = recall(app, f"depends_on {name}", limit=30)
    rows = []
    for m in memories:
        meta = m.get("metadata", {})
        if meta.get("name") == name and meta.get("depends_on"):
            rows.append({
                "depth": 1,
                "from_name": name,
                "relationship": meta.get("relationship", "uses"),
                "to_name": meta["depends_on"],
                "component_type": meta.get("type", ""),
                "environment": meta.get("env", ""),
            })
    note = f"Dependencies of '{name}' via mem9 metadata search (appId={app})."
    return {"note": note, "rows": rows, "nodes": list({name} | {r["to_name"] for r in rows})}


def cte_blast_radius(repo: str, name: str, team_name: str | None = None) -> dict:
    """Find what depends on a component (reverse dependency) via metadata search."""
    app = database_for(repo, team_name)
    memories = recall(app, name, limit=50)
    rows = []
    for m in memories:
        meta = m.get("metadata", {})
        dep = meta.get("depends_on", "")
        if dep and dep == name:
            comp_name = meta.get("name", "")
            if comp_name:
                rows.append({
                    "depth": 1,
                    "from_name": comp_name,
                    "relationship": meta.get("relationship", "uses"),
                    "to_name": name,
                    "component_type": meta.get("type", ""),
                    "environment": meta.get("env", ""),
                })
    note = f"Blast radius of '{name}' via mem9 metadata search (appId={app})."
    return {"note": note, "rows": rows, "nodes": list({name} | {r["from_name"] for r in rows})}


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
