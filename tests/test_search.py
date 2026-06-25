def _seed(db):
    db.init_db()
    db.write_component(repo="pulumi", name="acme-prod-static-assets", type="S3", env="production",
                       summary="CDN static assets bucket fronted by Cloudflare", developer="seed")
    db.write_component(repo="pulumi", name="acme-prod-analytics-db", type="RDS", env="production",
                       summary="analytics postgres database", developer="seed")


def test_like_search_matches_keyword(sqlite_env):
    db = sqlite_env
    _seed(db)
    out = db.search("pulumi", "static assets", mode="keyword")
    assert out["target"] == "sqlite"
    names = [r["name"] for r in out["results"]]
    assert "acme-prod-static-assets" in names


def test_hybrid_on_sqlite_degrades_to_like(sqlite_env):
    db = sqlite_env
    _seed(db)
    out = db.search("pulumi", "analytics", mode="hybrid")
    assert "LIKE" in out["note"]
    assert any(r["name"] == "acme-prod-analytics-db" for r in out["results"])
