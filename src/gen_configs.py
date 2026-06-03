"""Generate live MCP configs for Claude Code, Codex, and Cursor from .env.

Reads TiDB creds from .env and writes ready-to-use configs into the locations
each tool actually reads, wiring TWO MCP servers:

  - tidb           : the official PingCAP TiDB MCP server (raw SQL, vector search)
  - tidb-infra-kb  : our convention-aware MCP (query_knowledge_base, write_component)

Generated files contain secrets and are gitignored. Run:  python -m src.gen_configs
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

ROOT = Path(__file__).parent.parent
VENV_PY = ROOT / ".venv" / "bin" / "python"


def _env() -> dict:
    if load_dotenv:
        load_dotenv(ROOT / ".env", override=False)
    needed = ["TIDB_HOST", "TIDB_PORT", "TIDB_USERNAME", "TIDB_PASSWORD", "TIDB_DATABASE"]
    env = {k: os.environ.get(k, "") for k in needed}
    if not env["TIDB_HOST"]:
        sys.exit("ERROR: TIDB_HOST not set. Copy .env.example to .env and fill in your TiDB Cloud creds.")
    return env


def _tidb_server(env: dict) -> dict:
    return {
        "command": "uvx",
        "args": ["--from", "pytidb[mcp]", "tidb-mcp-server"],
        "env": {
            "TIDB_HOST": env["TIDB_HOST"],
            "TIDB_PORT": str(env["TIDB_PORT"] or "4000"),
            "TIDB_USERNAME": env["TIDB_USERNAME"],
            "TIDB_PASSWORD": env["TIDB_PASSWORD"],
            "TIDB_DATABASE": env["TIDB_DATABASE"] or "infra_kb",
        },
    }


def _kb_server() -> dict:
    return {
        "command": str(VENV_PY),
        "args": ["-m", "src.mcp_server"],
        "cwd": str(ROOT),
    }


def write_claude_code(env: dict) -> Path:
    cfg = {"mcpServers": {"tidb": _tidb_server(env), "tidb-infra-kb": _kb_server()}}
    out = ROOT / ".mcp.json"
    out.write_text(json.dumps(cfg, indent=2) + "\n")
    return out


def write_cursor(env: dict) -> Path:
    cfg = {"mcpServers": {"tidb": _tidb_server(env), "tidb-infra-kb": _kb_server()}}
    out = ROOT / ".cursor" / "mcp.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2) + "\n")
    return out


def write_codex(env: dict) -> Path:
    t = _tidb_server(env)
    toml = f"""# ── Add these blocks to ~/.codex/config.toml ──────────────────────────────
[mcp_servers.tidb]
command = "uvx"
args = ["--from", "pytidb[mcp]", "tidb-mcp-server"]
[mcp_servers.tidb.env]
TIDB_HOST = "{t['env']['TIDB_HOST']}"
TIDB_PORT = "{t['env']['TIDB_PORT']}"
TIDB_USERNAME = "{t['env']['TIDB_USERNAME']}"
TIDB_PASSWORD = "{t['env']['TIDB_PASSWORD']}"
TIDB_DATABASE = "{t['env']['TIDB_DATABASE']}"

[mcp_servers.tidb-infra-kb]
command = "{VENV_PY}"
args = ["-m", "src.mcp_server"]
cwd = "{ROOT}"
"""
    out = ROOT / "configs" / "generated" / "codex-config.toml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(toml)
    return out


def append_codex_global(codex_toml_path: Path) -> str:
    """Idempotently append the generated MCP blocks into ~/.codex/config.toml."""
    target = Path.home() / ".codex" / "config.toml"
    if not target.exists():
        return f"(~/.codex/config.toml not found - paste from {codex_toml_path})"
    existing = target.read_text()
    if "[mcp_servers.tidb]" in existing and "[mcp_servers.tidb-infra-kb]" in existing:
        return "already present in ~/.codex/config.toml - skipped"
    block = codex_toml_path.read_text()
    # strip the leading comment header lines (the '# ...' guidance)
    body = "\n".join(ln for ln in block.splitlines() if not ln.startswith("#")).strip()
    target.write_text(existing.rstrip() + "\n\n# --- mem9-ai-coding demo (auto-appended) ---\n" + body + "\n")
    return f"appended to {target}"


def main() -> None:
    env = _env()
    paths = [write_claude_code(env), write_cursor(env), write_codex(env)]
    codex_status = append_codex_global(paths[2])
    print("Generated MCP configs (gitignored, contain secrets):")
    print(f"  Claude Code : {paths[0]}   (auto-loaded from project root)")
    print(f"  Cursor      : {paths[1]}   (auto-loaded by Cursor)")
    print(f"  Codex       : {codex_status}")
    print("\nEach wires two MCP servers: 'tidb' (official) + 'tidb-infra-kb' (conventions).")


if __name__ == "__main__":
    main()
