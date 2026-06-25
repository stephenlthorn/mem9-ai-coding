import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _rpc(proc, msg):
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def test_server_identifies_its_repo_and_writes_scoped(tmp_path, monkeypatch):
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env.update({"MEM9_DATA_DIR": str(tmp_path), "MEM9_REPO": "pulumi", "MEM9_TEAM": "acme"})
    env.pop("TIDB_HOST", None)

    proc = subprocess.Popen(
        [sys.executable, "-m", "src.mcp_server"],
        cwd=str(ROOT), env=env, text=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert "pulumi" in json.dumps(init["result"]).lower()

        listed = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in listed["result"]["tools"]}
        assert {"query_knowledge_base", "write_component"} <= names

        wrote = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "write_component",
            "arguments": {"name": "acme-staging-admin-dns", "type": "Cloudflare",
                          "env": "staging", "summary": "staging admin dns", "developer": "codex"}}})
        assert "acme-staging-admin-dns" in json.dumps(wrote["result"])

        read = _rpc(proc, {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "query_knowledge_base",
            "arguments": {"sql": "SELECT name FROM acme_pulumi_kb.infra_components WHERE name='acme-staging-admin-dns'",
                          "developer": "codex"}}})
        assert "acme-staging-admin-dns" in json.dumps(read["result"])
    finally:
        proc.terminate()
