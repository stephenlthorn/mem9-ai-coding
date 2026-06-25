def test_cross_team_read_has_no_path_sqlite(sqlite_env):
    db = sqlite_env
    from src import seed, isolation_check
    seed.seed(reset=True)  # seeds team acme + team globex
    report = isolation_check.check(my_team="acme", other_team="globex")
    assert report["isolated"] is True
    assert report["target"] == "sqlite"
    assert "no query path" in report["detail"].lower()


def test_same_team_read_succeeds(sqlite_env):
    db = sqlite_env
    from src import seed, isolation_check
    seed.seed(reset=True)
    rows = isolation_check.read_team_components("acme")
    assert any(r["name"] == "acme-prod-static-assets" for r in rows)
