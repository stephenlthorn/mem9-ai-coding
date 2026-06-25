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
