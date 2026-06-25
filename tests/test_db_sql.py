from src import db


def test_schema_cloud_has_vector_and_fulltext():
    stmts = db.schema_statements("cloud", "acme_pulumi_kb", dims=1024)
    joined = "\n".join(stmts)
    assert "acme_pulumi_kb.infra_components" in joined
    assert "VECTOR(1024)" in joined
    assert "FULLTEXT INDEX" in joined
    assert "repo" in joined and "account_ref" in joined


def test_schema_local_has_vector_no_fulltext():
    joined = "\n".join(db.schema_statements("local", "acme_pulumi_kb", dims=384))
    assert "VECTOR(384)" in joined
    assert "FULLTEXT" not in joined


def test_schema_sqlite_has_no_vector_no_fulltext():
    joined = "\n".join(db.schema_statements("sqlite", "acme_pulumi_kb", dims=384))
    assert "VECTOR" not in joined
    assert "FULLTEXT" not in joined
    assert "repo" in joined and "account_ref" in joined


def test_insert_component_sql_cloud_uses_embed_text():
    sql = db.insert_component_sql("cloud", "acme_pulumi_kb")
    assert "EMBED_TEXT(" in sql
    assert "acme_pulumi_kb.infra_components" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


def test_insert_component_sql_local_takes_vector_literal_param():
    sql = db.insert_component_sql("local", "acme_pulumi_kb")
    assert "EMBED_TEXT" not in sql
    assert "embedding" in sql
    assert "ON DUPLICATE KEY UPDATE" in sql


def test_insert_component_sql_sqlite_no_embedding():
    sql = db.insert_component_sql("sqlite", "acme_pulumi_kb")
    assert "embedding" not in sql
    assert "INSERT OR REPLACE" in sql


def test_keyword_search_sql_cloud_is_fulltext():
    sql = db.keyword_search_sql("cloud", "acme_pulumi_kb")
    assert "FTS_MATCH_WORD" in sql


def test_keyword_search_sql_local_is_like():
    sql = db.keyword_search_sql("local", "acme_pulumi_kb")
    assert "LIKE" in sql
    assert "FTS_MATCH_WORD" not in sql


def test_cross_repo_sql_joins_two_databases():
    sql = db.cross_repo_accounts_sql("acme_pulumi_kb", "acme_lza_kb")
    assert "acme_pulumi_kb.infra_components" in sql
    assert "acme_lza_kb.infra_components" in sql
    assert "account_ref" in sql
