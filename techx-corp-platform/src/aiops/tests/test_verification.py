from app.verification import evaluate_target_slo, target_error_rate_query


def test_target_error_rate_query_is_scoped_to_mutated_service():
    query = target_error_rate_query("product-reviews", "techx-tf4", "2m")

    assert 'service_name="product-reviews"' in query
    assert 'k8s_namespace_name="techx-tf4"' in query
    assert 'status_code="STATUS_CODE_ERROR"' in query
    assert "[2m]" in query
    assert "frontend|checkout" not in query


def test_target_slo_ignores_unrelated_service_noise_by_construction():
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=0.0,
        error_rate_threshold=0.01,
    )

    assert result["healthy"] is True
    assert result["target_service"] == "product-reviews"
    assert result["coverage_complete"] is True


def test_target_slo_fails_closed_when_target_error_coverage_is_missing():
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=None,
        error_rate_threshold=0.01,
    )

    assert result["healthy"] is False
    assert result["coverage_complete"] is False


def test_target_slo_rejects_fast_errors():
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=0.02,
        error_rate_threshold=0.01,
    )

    assert result["healthy"] is False
    assert result["coverage_complete"] is True
