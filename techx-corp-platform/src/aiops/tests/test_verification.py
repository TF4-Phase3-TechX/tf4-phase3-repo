from app.verification import (
    evaluate_target_slo,
    target_error_rate_query,
    target_request_count_query,
)


def test_target_error_rate_query_is_scoped_to_mutated_service():
    query = target_error_rate_query("product-reviews", "techx-tf4", "2m")

    assert 'service_name="product-reviews"' in query
    assert 'k8s_namespace_name="techx-tf4"' in query
    assert 'span_name="oteldemo.ProductReviewService/GetProductReviews"' in query
    assert "grpc.health.v1.Health/Check" not in query
    assert 'status_code="STATUS_CODE_ERROR"' in query
    assert "or vector(0)" in query
    assert "clamp_min(" in query
    assert "[2m]" in query
    assert "frontend|checkout" not in query


def test_zero_error_series_does_not_bypass_the_request_volume_guard():
    query = target_error_rate_query("product-reviews", "techx-tf4", "2m")

    assert "or vector(0)" in query
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=0.0,
        error_rate_threshold=0.01,
        request_count=0,
        minimum_request_count=5,
    )

    assert result["healthy"] is False
    assert result["volume_sufficient"] is False


def test_target_request_count_query_is_scoped_to_mutated_service():
    query = target_request_count_query("product-reviews", "techx-tf4", "2m")

    assert 'service_name="product-reviews"' in query
    assert 'span_name="oteldemo.ProductReviewService/GetProductReviews"' in query
    assert "grpc.health.v1.Health/Check" not in query
    assert "increase(" in query
    assert "[2m]" in query


def test_target_slo_ignores_unrelated_service_noise_by_construction():
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=0.0,
        error_rate_threshold=0.01,
        request_count=20,
        minimum_request_count=5,
    )

    assert result["healthy"] is True
    assert result["target_service"] == "product-reviews"
    assert result["coverage_complete"] is True
    assert result["volume_sufficient"] is True


def test_target_slo_fails_closed_when_target_error_coverage_is_missing():
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=None,
        error_rate_threshold=0.01,
        request_count=20,
        minimum_request_count=5,
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
        request_count=20,
        minimum_request_count=5,
    )

    assert result["healthy"] is False
    assert result["coverage_complete"] is True


def test_target_slo_fails_closed_on_insufficient_request_volume():
    result = evaluate_target_slo(
        service="product-reviews",
        p95_latency_ms=1.9,
        latency_threshold_ms=1000.0,
        target_error_rate=0.0,
        error_rate_threshold=0.01,
        request_count=1,
        minimum_request_count=5,
    )

    assert result["healthy"] is False
    assert result["volume_sufficient"] is False
    assert result["coverage_complete"] is True
