"""Per-repo component manifests: the extractor's output for each synthetic repo.

In production, `src/ingest.py` would walk the repo source (TypeScript) and emit
these dicts. For the demo the extracted result is checked in as data so bootstrap
is deterministic and reviewable.
"""
from __future__ import annotations

import importlib

from src import topology


def load_manifest(repo: str) -> list[dict]:
    module = importlib.import_module(topology.REPOS[repo]["manifest"])
    return module.COMPONENTS
