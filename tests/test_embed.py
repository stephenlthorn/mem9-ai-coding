from src import embed


def test_fallback_is_deterministic_and_right_length():
    a = embed.encode_one("acme-prod-static-assets S3 bucket")
    b = embed.encode_one("acme-prod-static-assets S3 bucket")
    assert a == b
    assert len(a) == embed.LOCAL_DIMS
    assert all(-1.0 <= x <= 1.0 for x in a)


def test_distinct_text_distinct_vector():
    assert embed.encode_one("alpha") != embed.encode_one("beta")


def test_to_literal_format():
    lit = embed.to_literal([0.5, -0.25, 0.0])
    assert lit == "[0.500000,-0.250000,0.000000]"


def test_dims_by_target():
    assert embed.dims("cloud") == embed.CLOUD_DIMS
    assert embed.dims("local") == embed.LOCAL_DIMS
