from app.config import Settings
from app.detection import (
    Detector,
    adaptive_breach,
    anomaly_scores,
    error_rate_query,
    latency_query,
    llm_error_query,
    signal_gate,
    torai_lite_score,
)


def settings(**overrides):
    values = Settings().__dict__ | overrides
    return Settings(**values)


def test_statistical_scores_detect_latest_spike():
    scores = anomaly_scores([100, 102, 98, 101, 99, 103, 100, 2500])
    assert scores["ratio"] > 20
    assert scores["zscore"] > 3
    assert scores["isolation"] > 0


def test_acute_confirmation_does_not_refit_confidence_only_isolation_forest(
    monkeypatch,
):
    import app.detection as detection

    original = detection.anomaly_scores
    isolation_flags = []

    def recording_scores(points, settings=None, *, include_isolation=True):
        isolation_flags.append(include_isolation)
        return original(points, settings, include_isolation=include_isolation)

    monkeypatch.setattr(detection, "anomaly_scores", recording_scores)

    signal_gate([100, 101, 99, 100, 102, 130, 150, 180], 120)

    assert isolation_flags == [True, False, False, False]


def test_latency_requires_sustained_polls():
    detector = Detector(settings(sustained_polls=2, latency_threshold_ms=1000))
    series = [{"values": [[i, str(v)] for i, v in enumerate([100] * 7 + [1750, 1800])]}]
    assert detector.latency("checkout", series, "q").anomalous is False
    assert detector.latency("checkout", series, "q").anomalous is True


def test_single_latency_spike_resets_when_signal_recovers():
    detector = Detector(settings(sustained_polls=2))
    bad = [{"values": [[i, str(v)] for i, v in enumerate([100] * 8 + [1800])]}]
    good = [{"values": [[i, "100"] for i in range(9)]}]
    detector.latency("frontend", bad, "q")
    assert detector.latency("frontend", good, "q").anomalous is False


def test_error_rate_uses_per_service_span_metrics_and_requires_sustained_polls():
    detector = Detector(settings(sustained_polls=2, error_rate_threshold=0.05))
    series = [{"values": [[i, str(v)] for i, v in enumerate([0.005] * 7 + [0.11, 0.12])]}]
    query = error_rate_query("checkout")
    assert 'service_name="checkout"' in query
    assert 'span_kind="SPAN_KIND_SERVER"' in query
    assert 'span_name="oteldemo.CheckoutService/PlaceOrder"' in query
    assert "increase(" in query
    assert ">= 20" in query
    assert detector.error_rate("checkout", series, query).anomalous is False
    assert detector.error_rate("checkout", series, query).anomalous is True


def test_frontend_latency_query_reuses_user_visible_slo_routes():
    query = latency_query("frontend")
    assert 'span_kind="SPAN_KIND_SERVER"' in query
    assert 'span_name=~"GET /|GET /product.*' in query
    assert "POST /api/checkout" not in query


def test_frontend_error_query_uses_canonical_all_server_span_boundary():
    query = error_rate_query("frontend")
    assert 'span_kind="SPAN_KIND_SERVER"' in query
    assert "span_name" not in query


def test_runtime_queries_can_be_scoped_to_the_application_namespace():
    namespace = 'k8s_namespace_name="techx-tf4"'
    assert namespace in latency_query("frontend", "techx-tf4")
    assert namespace in error_rate_query("checkout", namespace="techx-tf4")
    assert namespace in llm_error_query("", namespace="techx-tf4")


def test_empty_latency_series_is_unavailable_not_healthy():
    detector = Detector(settings(sustained_polls=1))
    decision = detector.latency("frontend", [], "q")
    assert decision.coverage_status == "unavailable"
    assert decision.breached is False
    assert decision.anomalous is False
    assert decision.evidence[0].value == "unavailable"


def test_thin_latency_series_above_floor_can_fire_while_warming():
    detector = Detector(settings(sustained_polls=1, latency_threshold_ms=1000))
    decision = detector.latency("checkout", [{"values": [[0, "5000"]]}], "q")
    assert decision.coverage_status == "warming"
    assert decision.breached is True
    assert decision.anomalous is True


def test_llm_query_uses_instrumented_app_metric_family():
    query = llm_error_query("")
    assert "app_llm_errors_total" in query
    assert "app_llm_calls_total" in query
    assert "app_llm_requests_total" not in query
    assert "sum by (service_name)" in query
    assert "on(service_name)" in query
    assert ">= 5" in query


def test_llm_query_can_filter_one_instrumented_caller_without_losing_owner_label():
    query = llm_error_query("shopping-copilot", minimum_calls=10)
    assert 'service_name="shopping-copilot"' in query
    assert "sum by (service_name)" in query
    assert ">= 10" in query


def test_llm_error_requires_adaptive_metric_breach_and_treats_logs_as_evidence_only():
    detector = Detector(settings(sustained_polls=1, llm_error_threshold=0.05))
    healthy = [{"values": [[i, str(v)] for i, v in enumerate([0.01] * 8 + [0.01])]}]
    assert (
        detector.llm_error("product-reviews", healthy, "q", log_count=99).anomalous
        is False
    )

    degraded = [{"values": [[i, str(v)] for i, v in enumerate([0.01] * 7 + [0.075, 0.08])]}]
    decision = detector.llm_error("product-reviews", degraded, "q", log_count=1)
    assert decision.anomalous is True
    assert decision.service == "product-reviews"
    assert [candidate["service"] for candidate in decision.candidates] == [
        "product-reviews"
    ]


def test_robust_baseline_prevents_noise_spike_from_masking_a_separate_incident():
    scores = anomaly_scores([100, 101, 99, 100, 5000, 102, 98, 101, 160])
    assert scores["ratio"] >= 1.5
    assert adaptive_breach(scores) is True


def test_high_but_stable_service_load_does_not_fire_on_small_shift():
    detector = Detector(settings(sustained_polls=1, latency_threshold_ms=900))
    busy_healthy = [
        {
            "values": [
                [i, str(v)]
                for i, v in enumerate(
                    [990, 1000, 1010, 995, 1005, 1000, 990, 1010, 1100]
                )
            ]
        }
    ]
    assert detector.latency("checkout", busy_healthy, "q").anomalous is False


def test_gradual_degradation_fires_before_absolute_floor():
    detector = Detector(
        settings(
            sustained_polls=1,
            latency_threshold_ms=1000,
            trend_window=6,
            trend_min_relative_change=0.25,
            trend_min_current_ratio=1.2,
            trend_min_consistency=0.75,
        )
    )
    gradual = [400] * 8 + [450, 510, 570, 630, 690, 750]
    decision = detector.latency(
        "checkout",
        [{"values": [[i, str(v)] for i, v in enumerate(gradual)]}],
        "q",
    )

    assert max(gradual) < 1000
    assert decision.breached is True
    assert decision.anomalous is True
    assert decision.candidates[0]["signals"]["slow_drift"] == 1.0


def test_slow_drift_far_below_slo_is_audit_evidence_not_a_page():
    detector = Detector(settings(sustained_polls=1, latency_threshold_ms=1000))
    ramp_up = [50] * 8 + [55, 65, 75, 85, 95, 105]

    decision = detector.latency(
        "frontend",
        [{"values": [[i, str(v)] for i, v in enumerate(ramp_up)]}],
        "q",
    )

    assert decision.candidates[0]["signals"]["slow_drift"] == 1.0
    assert decision.breached is False
    assert decision.anomalous is False


def test_isolation_forest_is_configurable_confidence_evidence_not_a_gate():
    series = [
        {
            "values": [
                [i, str(v)]
                for i, v in enumerate([100, 101, 99, 102, 98, 100, 101, 1750, 1800])
            ]
        }
    ]
    without_if = Detector(
        settings(sustained_polls=1, isolation_confidence_weight=0.0)
    ).latency("checkout", series, "q")
    with_if = Detector(
        settings(sustained_polls=1, isolation_confidence_weight=0.10)
    ).latency("checkout", series, "q")

    assert without_if.anomalous is True
    assert with_if.anomalous is True
    assert with_if.confidence > without_if.confidence


def test_torai_lite_renormalizes_available_sources_and_records_missing_sources():
    result = torai_lite_score(metric=1.0, trace=None, log=0.5, ai=1.0)
    assert 0.0 < result["score"] <= 1.0
    assert result["components"] == {"metric": 1.0, "log": 0.5, "ai": 1.0}
    assert result["missing_sources"] == ["deploy", "trace"]


def test_torai_lite_weights_are_explicit_and_configurable():
    metric_first = torai_lite_score(
        weights={"metric": 0.9, "log": 0.1}, metric=1.0, log=0.0
    )
    log_first = torai_lite_score(
        weights={"metric": 0.1, "log": 0.9}, metric=1.0, log=0.0
    )

    assert metric_first["score"] > log_first["score"]
