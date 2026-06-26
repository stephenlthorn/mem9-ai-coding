"""Transitive dependency traversal (manifest-backed, offline).

The dependency graph's authoritative structure is the manifest, so traversal is
deterministic and testable without any mem9 / network access. We delete
MEM9_API_KEY so the live mem9 overlay in db._load_graph no-ops (its recall raises
and is swallowed), leaving the pure manifest backbone.
"""
import importlib

import pytest


@pytest.fixture
def db(monkeypatch):
    monkeypatch.delenv("MEM9_API_KEY", raising=False)
    monkeypatch.delenv("MEM9_NS_VERSION", raising=False)
    monkeypatch.setenv("MEM9_TEAM", "acme")
    import src.topology as topology
    import src.db as _db
    importlib.reload(topology)
    importlib.reload(_db)
    _db._GRAPH_CACHE.clear()
    return _db


def test_graph_builds_from_manifest_only(db):
    g = db._load_graph("pulumi")
    # all manifest components are present as nodes
    assert {"KmsKey", "acme-prod-portal-svc", "acme-prod-data-kms"} <= set(g["meta"])
    # composition + edge arcs are both captured
    assert ("acme-prod-portal-sso", "authenticates_via") in g["fwd"]["acme-prod-portal-svc"]
    assert ("KmsKey", "instantiates") in g["fwd"]["acme-prod-data-kms"]


def test_portal_svc_has_five_hop_dependency_chain(db):
    r = db.cte_dependencies("pulumi", "acme-prod-portal-svc")
    assert r["mode"] == "dependencies"
    # a chain of length 5 (six nodes) bottoming out at KmsKey exists
    deepest = max(r["paths"], key=len)
    assert len(deepest) - 1 >= 5
    assert deepest[0] == "acme-prod-portal-svc"
    assert deepest[-1] == "KmsKey"
    assert "acme-prod-portal-cert" in deepest


def test_kmskey_blast_radius_reaches_thirteen_across_four_depths(db):
    r = db.cte_blast_radius("pulumi", "KmsKey")
    assert r["mode"] == "blast-radius"
    assert r["count"] == 13
    assert r["max_depth"] == 4
    depths = {n["depth"] for n in r["nodes_meta"] if n["depth"] > 0}
    assert depths == {1, 2, 3, 4}
    reached = {n["name"] for n in r["nodes_meta"]}
    assert {"acme-prod-portal-svc", "acme-prod-data-kms", "acme-prod-admin-sso"} <= reached


def test_leaf_has_no_dependencies(db):
    r = db.cte_dependencies("pulumi", "KmsKey")  # KmsKey depends on nothing
    assert r["count"] == 0
    assert r["paths"] == []


def test_lza_nested_ou_three_hop_chain(db):
    r = db.cte_dependencies("lza", "acme-lza-account-prod")
    deepest = max(r["paths"], key=len)
    assert deepest[:3] == ["acme-lza-account-prod", "acme-lza-ou-workloads", "acme-lza-ou-core"]


def test_rows_carry_depth_type_and_relationship(db):
    r = db.cte_blast_radius("pulumi", "KmsKey")
    assert r["rows"], "expected directed BFS edges"
    for row in r["rows"]:
        assert {"depth", "from_name", "to_name", "relationship", "component_type"} <= set(row)
        assert row["depth"] >= 1
