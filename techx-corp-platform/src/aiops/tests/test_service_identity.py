from app.service_identity import normalize_service_name, normalize_many


def test_known_aliases():
    assert normalize_service_name("frontend-web").canonical_service == "frontend"
    assert normalize_service_name("ProductCatalog").canonical_service == "product-catalog"
    assert normalize_service_name("llm").canonical_service == "external-llm-provider"


def test_preserve_unknown_names():
    result = normalize_service_name("billing-core")
    assert result.canonical_service == "billing-core"
    assert result.original_service == "billing-core"
    assert "alias" not in result.normalization_reason


def test_per_scenario_alias_isolation():
    global_like = normalize_service_name("edge-portal")
    assert global_like.canonical_service == "edge-portal"
    overridden = normalize_service_name(
        "edge-portal", aliases={"edge-portal": "frontend"}
    )
    assert overridden.canonical_service == "frontend"
    # Global default unchanged
    assert normalize_service_name("edge-portal").canonical_service == "edge-portal"


def test_no_accidental_merge_of_similar_names():
    a = normalize_service_name("payment")
    b = normalize_service_name("payments")
    assert a.canonical_service != b.canonical_service


def test_empty_and_whitespace():
    empty = normalize_service_name("")
    assert empty.canonical_service == "unknown"
    assert empty.normalization_reason == "empty_or_missing"
    trimmed = normalize_service_name("  checkout  ")
    assert trimmed.canonical_service == "checkout"


def test_normalize_many():
    results = normalize_many(["frontend-web", "checkoutservice"])
    assert [r.canonical_service for r in results] == ["frontend", "checkout"]
