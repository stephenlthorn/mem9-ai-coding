def test_init_and_write_single_repo(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(
        repo="pulumi", name="acme-prod-x", type="S3", env="production",
        summary="x bucket", developer="claude-code", depends_on=None, account_ref="prod",
    )
    rows = db.query(f"SELECT name, repo, account_ref FROM {db.tref('pulumi','infra_components')}")
    assert any(r["name"] == "acme-prod-x" and r["repo"] == "pulumi" for r in rows)


def test_edge_and_session_log_written(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(repo="pulumi", name="S3Bucket", type="Library", env="library",
                       summary="lib", developer="seed")
    db.write_component(repo="pulumi", name="acme-prod-y", type="S3", env="production",
                       summary="y", developer="claude-code", depends_on="S3Bucket")
    edges = db.query(f"SELECT relationship FROM {db.tref('pulumi','component_edges')}")
    assert any(e["relationship"] == "uses" for e in edges)
    log = db.query(f"SELECT action FROM {db.tref('pulumi','session_log')}")
    assert any(r["action"] == "created" for r in log)


def test_cross_repo_join(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(repo="lza", name="acme-lza-account-prod", type="Account", env="org",
                       summary="prod account", developer="seed", account_ref="prod")
    db.write_component(repo="pulumi", name="acme-prod-exports", type="S3", env="production",
                       summary="exports", developer="seed", account_ref="prod")
    sql = db.cross_repo_accounts_sql(db.database_for("pulumi"), db.database_for("lza"))
    rows = db.query(sql)
    assert rows and rows[0]["pulumi_component"] == "acme-prod-exports"
    assert rows[0]["lza_account"] == "acme-lza-account-prod"


def test_blast_radius_cte_single_repo(sqlite_env):
    db = sqlite_env
    db.init_db()
    db.write_component(repo="pulumi", name="S3Bucket", type="Library", env="library",
                       summary="lib", developer="seed")
    db.write_component(repo="pulumi", name="acme-prod-exports", type="S3", env="production",
                       summary="exports", developer="seed", depends_on="S3Bucket")
    out = db.cte_blast_radius("pulumi", "S3Bucket")
    assert "acme-prod-exports" in out["nodes"]
    assert "WITH RECURSIVE" in out["sql"]


def test_query_rejects_non_select(sqlite_env):
    db = sqlite_env
    db.init_db()
    import pytest
    with pytest.raises(ValueError):
        db.query("DELETE FROM acme_pulumi_kb.infra_components")


def test_backend_name_mentions_sqlite(sqlite_env):
    assert "SQLite" in sqlite_env.backend_name()
