"""Generate MCP configs for Claude Code, Codex, and Cursor.

Routing is EXPLICIT: one named server entry per repo namespace, all scoped to a
single mem9 space (API key). For team 'acme' with repos pulumi + lza this emits:

  infra-kb-pulumi  mem9 convention MCP, MEM9_REPO=pulumi  (hybrid search + write)
  infra-kb-lza     mem9 convention MCP, MEM9_REPO=lza

The same API key is used for every repo namespace - appId isolation is handled
server-side by mem9. Generated files contain secrets and are gitignored.
Run: python -m src.gen_configs
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
    key = os.environ.get("MEM9_API_KEY", "").strip()
    if not key:
        sys.exit("ERROR: MEM9_API_KEY not set. Copy .env.example to .env and paste your mem9 space key.")
    return {
        "MEM9_API_KEY": key,
        "MEM9_BASE_URL": os.environ.get("MEM9_BASE_URL", "https://api.mem9.ai"),
        "TEAM": topology.team(),
    }


def _kb_server(env: dict, repo: str) -> dict:
    return {
        "command": str(VENV_PY),
        "args": ["-m", "src.mcp_server"],
        "cwd": str(ROOT),
        "env": {
            "MEM9_REPO": repo,
            "MEM9_TEAM": env["TEAM"],
            "MEM9_API_KEY": env["MEM9_API_KEY"],
            "MEM9_BASE_URL": env["MEM9_BASE_URL"],
        },
    }


def _servers(env: dict) -> dict:
    return {f"infra-kb-{repo}": _kb_server(env, repo) for repo in topology.repo_names()}


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
        lines += [
            f"[mcp_servers.infra-kb-{repo}]",
            f'command = "{VENV_PY}"',
            'args = ["-m", "src.mcp_server"]',
            f'cwd = "{ROOT}"',
            f"[mcp_servers.infra-kb-{repo}.env]",
            f'MEM9_REPO = "{repo}"',
            f'MEM9_TEAM = "{env["TEAM"]}"',
            f'MEM9_API_KEY = "{env["MEM9_API_KEY"]}"',
            f'MEM9_BASE_URL = "{env["MEM9_BASE_URL"]}"',
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
    print("\nNamed entries per repo: " + ", ".join(f"infra-kb-{r}" for r in topology.repo_names()))


if __name__ == "__main__":
    main()
