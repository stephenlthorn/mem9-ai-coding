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
