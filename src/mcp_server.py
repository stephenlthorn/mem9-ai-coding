"""tidb-infra-kb MCP server (stdio transport).

Run with: python -m src.mcp_server
Connect from Claude Code, Codex, or Cursor via their MCP config.
Each session reads/writes the shared kb.db - all tools see each other's work.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import db as _db

_db.init_db()

TOOLS = [
    {
        "name": "query_knowledge_base",
        "description": (
            "Execute a read-only SELECT query against the infrastructure knowledge base. "
            "Tables: infra_components (id, name, component_type, environment, repo_path, summary, code_excerpt), "
            "component_edges (id, from_id, to_id, relationship, note), "
            "session_log (id, developer, action, detail, created_at). "
            "Always query before creating anything new."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SELECT SQL query to execute against the knowledge base."
                },
                "developer": {
                    "type": "string",
                    "description": "Tool name for logging: claude-code, codex, or cursor"
                }
            },
            "required": ["sql"],
        },
    },
    {
        "name": "write_component",
        "description": (
            "Atomically record a new infrastructure component, its dependency edge, and a session log entry. "
            "Run this after scaffolding any new Pulumi resource so the next session starts warm."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Resource name, e.g. acme-staging-admin-dns"},
                "type": {"type": "string", "enum": ["S3", "RDS", "Cloudflare", "Okta", "Library"]},
                "env": {"type": "string", "enum": ["production", "staging", "library"]},
                "summary": {"type": "string", "description": "What this resource does and what library it composes"},
                "depends_on": {"type": "string", "description": "Name of parent library component"},
                "developer": {"type": "string", "description": "claude-code | codex | cursor"},
            },
            "required": ["name", "type", "env", "summary", "developer"],
        },
    },
]


def _respond(id: int | str | None, result: dict) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": id, "result": result}), flush=True)


def _error(id: int | str | None, code: int, message: str) -> None:
    print(json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}), flush=True)


def _handle(msg: dict) -> None:
    method = msg.get("method", "")
    id_ = msg.get("id")

    if method == "initialize":
        _respond(id_, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tidb-infra-kb", "version": "1.0.0"},
        })

    elif method == "notifications/initialized":
        pass  # no response

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
                rows = _db.query(sql)
                _db.log_query(developer, f"SQL: {sql[:120]}")
                text = json.dumps(rows, indent=2, default=str)
                _respond(id_, {"content": [{"type": "text", "text": text}]})

            elif tool == "write_component":
                comp_id = _db.write_component(
                    name=args["name"],
                    type=args["type"],
                    env=args["env"],
                    summary=args["summary"],
                    depends_on=args.get("depends_on"),
                    developer=args["developer"],
                )
                _respond(id_, {"content": [{"type": "text", "text": f"Written: {args['name']} (id={comp_id})"}]})

            else:
                _error(id_, -32601, f"Unknown tool: {tool}")

        except Exception as exc:
            _error(id_, -32603, str(exc))

    else:
        _error(id_, -32601, f"Unknown method: {method}")


def main() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
            _handle(msg)
        except json.JSONDecodeError as exc:
            _error(None, -32700, f"Parse error: {exc}")
        except Exception as exc:
            _error(None, -32603, str(exc))


if __name__ == "__main__":
    main()
