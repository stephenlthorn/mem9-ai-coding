from src.repos import pulumi, lza, load_manifest


def test_pulumi_has_libraries_and_staging_gap():
    names = {c["name"] for c in pulumi.COMPONENTS}
    assert {"S3Bucket", "PostgresDatabase", "DnsRecord", "SsoApplication"} <= names
    staging = {c["name"] for c in pulumi.COMPONENTS if c["env"] == "staging"}
    assert "acme-staging-data-exports" in staging
    assert "acme-staging-admin-sso" not in staging  # the demo gap


def test_lza_has_accounts_with_account_ref():
    accounts = [c for c in lza.COMPONENTS if c["type"] == "Account"]
    refs = {c["account_ref"] for c in accounts}
    assert {"prod", "sandbox"} <= refs


def test_load_manifest_by_name():
    assert load_manifest("pulumi") is pulumi.COMPONENTS
    assert load_manifest("lza") is lza.COMPONENTS


def test_every_component_has_required_keys():
    for mod in (pulumi, lza):
        for c in mod.COMPONENTS:
            assert {"name", "type", "env", "summary", "repo"} <= set(c)
            assert c["repo"] == mod.REPO
