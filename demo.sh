#!/usr/bin/env bash
# Serve the dashboard (live mission control over the shared TiDB KB).
# Run ./setup.sh first to create schema, seed, and generate MCP configs.
set -euo pipefail
cd "$(dirname "$0")"

PORT="${DASHBOARD_PORT:-7001}"
python3 -m venv .venv 2>/dev/null || true
. .venv/bin/activate
pip install -q -r requirements.txt >/dev/null 2>&1 || true

case "${1:-run}" in
  --reseed) python3 -m src.seed --reset; echo "reseeded"; exit 0 ;;
esac

echo "==> Backend: $(python3 -c 'from src import db; print(db.backend_name())')"
echo "==> Starting dashboard"
lsof -ti :"$PORT" | xargs kill -9 2>/dev/null || true
.venv/bin/uvicorn dashboard.server:app --host 0.0.0.0 --port "$PORT" &
for i in $(seq 1 20); do
  curl -sf "http://localhost:$PORT/healthz" >/dev/null && break
  [ "$i" -eq 20 ] && { echo "ERROR: dashboard failed to start" >&2; exit 1; }
  sleep 1
done

echo ""
echo "Dashboard: http://localhost:$PORT"
echo "Open 3 iTerm panes in this repo and launch:  claude · codex · cursor-agent"
echo "Prompts: see DEMO.md"
echo ""
(command -v open >/dev/null && open "http://localhost:$PORT") || true
wait
