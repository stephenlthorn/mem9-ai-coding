def test_bootstrap_pulumi_populates_components_and_edges(sqlite_env):
    db = sqlite_env
    from src import ingest
    ingest.bootstrap("pulumi", reset=True)
    comps = db.query(f"SELECT name FROM {db.tref('pulumi','infra_components')}")
    names = {c["name"] for c in comps}
    assert "acme-prod-admin-sso" in names
    edges = db.query(f"SELECT relationship FROM {db.tref('pulumi','component_edges')}")
    rels = {e["relationship"] for e in edges}
    assert "instantiates" in rels and "fronts" in rels and "redirects_to" in rels


def test_bootstrap_lza_sets_account_ref(sqlite_env):
    db = sqlite_env
    from src import ingest
    ingest.bootstrap("lza", reset=True)
    rows = db.query(
        f"SELECT name, account_ref FROM {db.tref('lza','infra_components')} "
        "WHERE component_type='Account'")
    refs = {r["account_ref"] for r in rows}
    assert {"prod", "sandbox"} <= refs


def test_bootstrap_all_is_idempotent(sqlite_env):
    db = sqlite_env
    from src import ingest
    ingest.bootstrap_all(reset=True)
    ingest.bootstrap_all(reset=False)  # second run must not duplicate
    comps = db.query(f"SELECT COUNT(*) AS n FROM {db.tref('pulumi','infra_components')}")
    assert comps[0]["n"] == 12  # 4 libs + 6 prod + 2 staging
