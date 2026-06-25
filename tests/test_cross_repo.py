def test_cross_repo_create_account_then_bucket(sqlite_env):
    db = sqlite_env
    from src import ingest, cross_repo_demo
    ingest.bootstrap_all(reset=True)
    result = cross_repo_demo.run(account_ref="data-platform", developer="claude-code")
    # The new LZA account and the new Pulumi bucket both exist...
    lza = db.query(f"SELECT name FROM {db.tref('lza','infra_components')} WHERE account_ref='data-platform'")
    pul = db.query(f"SELECT name FROM {db.tref('pulumi','infra_components')} WHERE account_ref='data-platform'")
    assert lza and pul
    # ...and the cross-database JOIN ties them together.
    joined = [r for r in result["joined"] if r["account_ref"] == "data-platform"]
    assert joined and joined[0]["lza_account"].startswith("acme-lza-account-")
