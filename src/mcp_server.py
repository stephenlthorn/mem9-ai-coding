"""mem9 convention MCP server - ONE process per repo namespace (stdio transport).

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
APP_ID = _db.database_for(REPO, TEAM)

TOOLS = [
    {
        "name": "query_knowledge_base",
        "description": (
            f"Search the '{REPO}' repo knowledge base (namespace {APP_ID}) for team '{TEAM}'. "
            "Uses hybrid recall (vector + full-text) powered by mem9.ai / TiDB Cloud. "
            "Always query before creating anything - the KB holds every component this team "
            "has already scaffolded so you don't duplicate work."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language description of what you're looking for.",
                },
                "developer": {"type": "string", "description": "claude-code | codex | cursor"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "write_component",
        "description": (
            f"Record a component into the '{REPO}' repo knowledge base (namespace {APP_ID}) "
            f"for team '{TEAM}'. Write-back is INSTRUCTION-DRIVEN: call this after you scaffold "
            "a resource so the next session starts warm. "
            "Set account_ref to the LZA account the resource belongs to (enables cross-repo joins)."
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
            "serverInfo": {"name": f"mem9-infra-kb-{REPO}", "version": "3.0.0",
                           "repo": REPO, "team": TEAM, "app_id": APP_ID},
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
                q = args.get("query", "").strip()
                developer = args.get("developer", "unknown")
                result = _db.search(REPO, q, team_name=TEAM)
                _db.log_query(REPO, developer, f"searched: {q[:120]}", team_name=TEAM)
                _respond(id_, {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]})
            elif tool == "write_component":
                mem_id = _db.write_component(
                    repo=REPO, team_name=TEAM, name=args["name"], type=args["type"],
                    env=args["env"], summary=args["summary"], depends_on=args.get("depends_on"),
                    account_ref=args.get("account_ref"), developer=args["developer"],
                )
                _respond(id_, {"content": [{"type": "text",
                          "text": f"Written to {APP_ID}: {args['name']} (id={mem_id})"}]})
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
