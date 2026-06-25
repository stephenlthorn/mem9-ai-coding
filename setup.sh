#!/usr/bin/env bash
# One-time setup: deps, TiDB schema + seed, and MCP configs for all 3 CLIs.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Installing Python deps"
python3 -m venv .venv 2>/dev/null || true
. .venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f .env ]; then
  echo "ERROR: no .env. Run: cp .env.example .env  then paste your TiDB Cloud creds." >&2
  exit 1
fi
set -a; . ./.env; set +a

if [ -z "${TIDB_HOST:-}" ]; then
  echo "WARNING: TIDB_HOST not set in .env - will seed the local SQLite fallback instead of TiDB." >&2
else
  echo "==> Target: TiDB Cloud ($TIDB_HOST)"
fi

echo "==> Verifying official TiDB MCP server is fetchable (uvx pytidb[mcp])"
command -v uvx >/dev/null || { echo "ERROR: uvx not found. Install uv: https://docs.astral.sh/uv/" >&2; exit 1; }

echo "==> Bootstrapping both repo databases from source (acme_pulumi_kb + acme_lza_kb)"
python3 -m src.ingest --reset
echo "==> Seeding the second team (globex) for the isolation demo"
python3 -m src.seed --reset

echo "==> Generating MCP configs for Claude Code / Codex / Cursor"
python3 -m src.gen_configs

cat <<'EOF'

Setup complete.

Next:
  ./demo.sh                         # dashboard at http://localhost:7001
  Codex users: paste configs/generated/codex-config.toml into ~/.codex/config.toml

Then open 3 iTerm panes (all: cd into this repo) and launch:
  claude   ·   codex   ·   cursor-agent
Each tool sees one named MCP entry per repo database (tidb-pulumi/-lza, infra-kb-pulumi/-lza).
Follow DEMO.md for the copy-paste prompts (Scenario A single-repo, B cross-repo, C isolation).
EOF
