from app.config import Settings
from app.detection import (
    Detector,
    adaptive_breach,
    anomaly_scores,
    error_rate_query,
    llm_error_query,
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


def test_latency_requires_sustained_polls():
    detector = Detector(settings(sustained_polls=2, latency_threshold_ms=1000))
    series = [{"values": [[i, str(v)] for i, v in enumerate([100] * 8 + [1800])] }]
    assert detector.latency("checkout", series, "q").anomalous is False
    assert detector.latency("checkout", series, "q").anomalous is True


def test_single_latency_spike_resets_when_signal_recovers():
    detector = Detector(settings(sustained_polls=2))
    bad = [{"values": [[i, str(v)] for i, v in enumerate([100] * 8 + [1800])] }]
    good = [{"values": [[i, "100"] for i in range(9)]}]
    detector.latency("frontend", bad, "q")
    assert detector.latency("frontend", good, "q").anomalous is False


def test_error_rate_uses_per_service_span_metrics_and_requires_sustained_polls():
    detector = Detector(settings(sustained_polls=2, error_rate_threshold=0.05))
    series = [{"values": [[i, str(v)] for i, v in enumerate([0.005] * 8 + [0.12])]}]
    query = error_rate_query("checkout")
    assert 'service_name="checkout"' in query
    assert "increase(" in query
    assert ">= 20" in query
    assert detector.error_rate("checkout", series, query).anomalous is False
    assert detector.error_rate("checkout", series, query).anomalous is True


def test_llm_query_uses_instrumented_app_metric_family():
    query = llm_error_query("product-reviews")
    assert "app_llm_errors_total" in query
    assert "app_llm_calls_total" in query
    assert "app_llm_requests_total" not in query
    assert ">= 5" in query


def test_llm_error_requires_adaptive_metric_breach_and_treats_logs_as_evidence_only():
    detector = Detector(settings(sustained_polls=1, llm_error_threshold=0.05))
    healthy = [{"values": [[i, str(v)] for i, v in enumerate([0.01] * 8 + [0.01])]}]
    assert detector.llm_error("product-reviews", healthy, "q", log_count=99).anomalous is False

    degraded = [{"values": [[i, str(v)] for i, v in enumerate([0.01] * 8 + [0.08])]}]
    decision = detector.llm_error("product-reviews", degraded, "q", log_count=1)
    assert decision.anomalous is True
    assert decision.service == "product-reviews"
    assert [candidate["service"] for candidate in decision.candidates] == ["product-reviews"]


def test_robust_baseline_prevents_noise_spike_from_masking_a_separate_incident():
    scores = anomaly_scores([100, 101, 99, 100, 5000, 102, 98, 101, 160])
    assert scores["ratio"] >= 1.5
    assert adaptive_breach(scores) is True


def test_high_but_stable_service_load_does_not_fire_on_small_shift():
    detector = Detector(settings(sustained_polls=1, latency_threshold_ms=900))
    busy_healthy = [
        {"values": [[i, str(v)] for i, v in enumerate([990, 1000, 1010, 995, 1005, 1000, 990, 1010, 1100])]}
    ]
    assert detector.latency("checkout", busy_healthy, "q").anomalous is False


def test_torai_lite_renormalizes_available_sources_and_records_missing_sources():
    result = torai_lite_score(metric=1.0, trace=None, log=0.5, ai=1.0)
    assert 0.0 < result["score"] <= 1.0
    assert result["components"] == {"metric": 1.0, "log": 0.5, "ai": 1.0}
    assert result["missing_sources"] == ["deploy", "trace"]
