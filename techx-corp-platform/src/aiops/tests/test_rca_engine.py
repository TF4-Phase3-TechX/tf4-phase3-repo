from datetime import datetime, timedelta, timezone

from app.dependency_graph import DependencyGraph
from app.rca_engine import RCAEngine, RCAEngineInput, observations_from_decisions
from app.rca_models import RCAObservation, SignalObservation
from app.trace_graph import parse_normalized_spans


def _obs(service: str, t0: datetime, confidence: float = 0.9, anomalous: bool = True):
    return RCAObservation(
        service=service,
        signals=[
            SignalObservation(
                signal="error",
                anomalous=anomalous,
                breached=anomalous,
                confidence=confidence,
                observed_at=t0,
                first_anomalous_at=t0 if anomalous else None,
                first_breached_at=t0 if anomalous else None,
            )
        ],
        first_anomalous_at=t0 if anomalous else None,
        first_breached_at=t0 if anomalous else None,
    )


def test_standard_cascade_root_ranks_first():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    observations = [
        _obs("payment", t0, 0.92),
        _obs("checkout", t0 + timedelta(seconds=10), 0.88),
        _obs("frontend", t0 + timedelta(seconds=20), 0.8),
    ]
    result = RCAEngine().analyze(RCAEngineInput(observations=observations))
    assert result.suspected_root_service == "payment"
    assert result.candidates[0].service == "payment"


def test_multiple_signals_one_service_count_once():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    obs = RCAObservation(
        service="checkout",
        signals=[
            SignalObservation(
                signal="latency",
                anomalous=True,
                confidence=0.7,
                observed_at=t0,
                first_anomalous_at=t0,
            ),
            SignalObservation(
                signal="error",
                anomalous=True,
                confidence=0.9,
                observed_at=t0,
                first_anomalous_at=t0,
            ),
        ],
        first_anomalous_at=t0,
    )
    result = RCAEngine().analyze(
        RCAEngineInput(observations=[obs, _obs("payment", t0 - timedelta(seconds=5))])
    )
    checkout_entries = [c for c in result.candidates if c.service == "checkout"]
    assert len(checkout_entries) == 1


def test_disconnected_noise_not_selected():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    spans = [
        {
            "trace_id": "t",
            "span_id": "1",
            "service": "checkout",
            "kind": "client",
            "peer_service": "payment",
            "error": True,
            "start_us": 100,
            "duration_us": 50,
            "parent_span_ids": [],
        },
        {
            "trace_id": "t",
            "span_id": "2",
            "service": "payment",
            "kind": "server",
            "error": True,
            "start_us": 110,
            "duration_us": 30,
            "parent_span_ids": ["1"],
        },
    ]
    observations = [
        _obs("payment", t0, 0.9),
        _obs("checkout", t0 + timedelta(seconds=5), 0.85),
        _obs("frontend", t0 + timedelta(seconds=10), 0.8),
        _obs("ad", t0, 0.91),
    ]
    result = RCAEngine().analyze(
        RCAEngineInput(
            observations=observations,
            traces=parse_normalized_spans(spans),
            graph=DependencyGraph.from_static(),
        )
    )
    assert result.suspected_root_service == "payment"
    ad = next(c for c in result.candidates if c.service == "ad")
    assert ad.classification == "unexplained_parallel_anomaly"


def test_trace_only_root_without_local_anomaly():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    spans = [
        {
            "trace_id": "t",
            "span_id": "1",
            "service": "checkout",
            "kind": "client",
            "peer_service": "payment",
            "error": True,
            "start_us": 100,
            "duration_us": 50,
            "parent_span_ids": [],
        },
        {
            "trace_id": "t",
            "span_id": "2",
            "service": "payment",
            "kind": "server",
            "error": True,
            "start_us": 110,
            "duration_us": 30,
            "parent_span_ids": ["1"],
        },
    ]
    observations = [
        _obs("checkout", t0 + timedelta(seconds=5), 0.85),
        _obs("frontend", t0 + timedelta(seconds=10), 0.8),
    ]
    result = RCAEngine().analyze(
        RCAEngineInput(
            observations=observations,
            traces=parse_normalized_spans(spans),
        )
    )
    assert result.suspected_root_service == "payment"
    payment = next(c for c in result.candidates if c.service == "payment")
    assert payment.contributions["local_anomaly_support"].raw_value == 0.0


def test_missing_trace_unavailable_not_zero_support():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    result = RCAEngine().analyze(
        RCAEngineInput(
            observations=[
                _obs("payment", t0, 0.9),
                _obs("checkout", t0 + timedelta(seconds=10), 0.8),
            ],
            unavailable_signals=["trace"],
        )
    )
    for cand in result.candidates:
        contrib = cand.contributions["trace_origin_support"]
        assert contrib.available is False
        assert contrib.raw_value is None
    assert result.suspected_root_service == "payment"


def test_input_order_invariance():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    a = [_obs("frontend", t0 + timedelta(seconds=20)), _obs("payment", t0), _obs("checkout", t0 + timedelta(seconds=10))]
    b = list(reversed(a))
    engine = RCAEngine()
    r1 = engine.analyze(RCAEngineInput(observations=a))
    r2 = engine.analyze(RCAEngineInput(observations=b))
    assert [c.service for c in r1.candidates] == [c.service for c in r2.candidates]
    assert r1.suspected_root_service == r2.suspected_root_service


def test_adding_noise_does_not_change_root():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    base = [
        _obs("payment", t0, 0.92),
        _obs("checkout", t0 + timedelta(seconds=10), 0.88),
        _obs("frontend", t0 + timedelta(seconds=20), 0.8),
    ]
    with_noise = base + [_obs("ad", t0, 0.95)]
    engine = RCAEngine()
    r1 = engine.analyze(RCAEngineInput(observations=base))
    r2 = engine.analyze(RCAEngineInput(observations=with_noise))
    assert r1.suspected_root_service == r2.suspected_root_service == "payment"


def test_multiple_independent_clusters_status():
    t0 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    graph = DependencyGraph.from_edges(
        [("checkout", "payment"), ("ad", "currency")],
        base=None,
    )
    result = RCAEngine().analyze(
        RCAEngineInput(
            observations=[
                _obs("payment", t0),
                _obs("checkout", t0 + timedelta(seconds=5)),
                _obs("ad", t0),
            ],
            graph=graph,
        )
    )
    assert result.attribution_status == "multiple_independent_clusters"
    assert result.suspected_root_service is None


def test_observations_from_decisions_aggregate_by_service():
    class D:
        def __init__(self, service, incident_type, conf):
            self.service = service
            self.incident_type = incident_type
            self.anomalous = True
            self.breached = True
            self.coverage_status = "available"
            self.confidence = conf
            self.severity = "high"
            self.evidence = []

    obs = observations_from_decisions(
        [D("checkout", "latency", 0.7), D("checkout", "error", 0.9)]
    )
    assert len(obs) == 1
    assert obs[0].service == "checkout"
    assert len(obs[0].signals) == 2
