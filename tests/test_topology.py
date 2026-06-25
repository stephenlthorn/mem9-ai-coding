import importlib

import pytest


def reload_topology(monkeypatch, **env):
    for k in ("TIDB_HOST", "MEM9_TARGET", "MEM9_TEAM"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import src.topology as topology
    importlib.reload(topology)
    return topology


def test_no_host_is_sqlite(monkeypatch):
    t = reload_topology(monkeypatch)
    assert t.target() == "sqlite"
    assert t.has_vector() is False
    assert t.has_fulltext() is False
    assert t.has_auto_embed() is False


def test_tidbcloud_host_is_cloud(monkeypatch):
    t = reload_topology(monkeypatch, TIDB_HOST="gateway01.eu-central-1.prod.aws.tidbcloud.com")
    assert t.target() == "cloud"
    assert t.has_vector() and t.has_fulltext() and t.has_auto_embed()


def test_localhost_host_is_local_tiup(monkeypatch):
    t = reload_topology(monkeypatch, TIDB_HOST="127.0.0.1")
    assert t.target() == "local"
    assert t.has_vector() is True
    assert t.has_fulltext() is False
    assert t.has_auto_embed() is False


def test_explicit_target_overrides_inference(monkeypatch):
    t = reload_topology(monkeypatch, TIDB_HOST="gateway01.prod.aws.tidbcloud.com", MEM9_TARGET="local")
    assert t.target() == "local"


def test_database_for_namespaces_by_team(monkeypatch):
    t = reload_topology(monkeypatch, MEM9_TEAM="acme")
    assert t.database_for("pulumi") == "acme_pulumi_kb"
    assert t.database_for("lza") == "acme_lza_kb"
    assert t.database_for("pulumi", team="globex") == "globex_pulumi_kb"


def test_unknown_repo_raises(monkeypatch):
    t = reload_topology(monkeypatch)
    with pytest.raises(KeyError):
        t.database_for("nope")


def test_repos_and_team_defaults(monkeypatch):
    t = reload_topology(monkeypatch)
    assert t.team() == "acme"
    assert set(t.repo_names()) == {"pulumi", "lza"}
