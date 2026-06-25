"""Shared pytest fixtures. All tests run on the SQLite offline substrate
(no network, no creds) unless a test explicitly opts into a live target."""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest


@pytest.fixture
def sqlite_env(tmp_path, monkeypatch):
    """Force the SQLite target with an isolated per-test data dir, and reload
    the topology + db modules so module-level state is re-evaluated."""
    monkeypatch.delenv("TIDB_HOST", raising=False)
    monkeypatch.delenv("MEM9_TARGET", raising=False)
    monkeypatch.setenv("MEM9_TEAM", "acme")
    monkeypatch.setenv("MEM9_DATA_DIR", str(tmp_path))

    import src.topology as topology
    import src.db as db
    importlib.reload(topology)
    importlib.reload(db)
    return db
