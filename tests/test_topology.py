"""Topology: team -> mem9 space, repo -> appId namespace within it."""
import importlib

import pytest


def reload_topology(monkeypatch, **env):
    for k in ("MEM9_TEAM", "MEM9_NS_VERSION"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.topology as topology
    importlib.reload(topology)
    return topology


def test_repos_and_team_defaults(monkeypatch):
    t = reload_topology(monkeypatch)
    assert t.team() == "acme"
    assert set(t.repo_names()) == {"pulumi", "lza"}


def test_app_id_namespaces_by_team_and_repo(monkeypatch):
    t = reload_topology(monkeypatch, MEM9_TEAM="acme")
    assert t.app_id("pulumi") == "acme_pulumi_kb"
    assert t.app_id("lza") == "acme_lza_kb"
    assert t.app_id("pulumi", team_name="globex") == "globex_pulumi_kb"


def test_ns_version_suffix_when_set(monkeypatch):
    t = reload_topology(monkeypatch, MEM9_TEAM="acme", MEM9_NS_VERSION="demo")
    assert t.ns_version() == "demo"
    assert t.app_id("pulumi") == "acme_pulumi_kb_demo"
    assert t.app_id("lza", team_name="globex") == "globex_lza_kb_demo"


def test_ns_version_empty_by_default(monkeypatch):
    t = reload_topology(monkeypatch)
    assert t.ns_version() == ""
    assert t.app_id("pulumi") == "acme_pulumi_kb"


def test_unknown_repo_raises(monkeypatch):
    t = reload_topology(monkeypatch)
    with pytest.raises(KeyError):
        t.app_id("nope")
