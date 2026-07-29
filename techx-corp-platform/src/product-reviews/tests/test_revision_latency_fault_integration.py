from types import SimpleNamespace
from unittest.mock import patch

from revision_latency_fault import RevisionLatencyFault

with (
    patch.dict(
        "os.environ",
        {"DB_CONNECTION_STRING": "postgresql://test:test@localhost/test"},
    ),
    patch("psycopg2.pool.ThreadedConnectionPool"),
):
    import product_reviews_server


def test_review_rpc_is_delayed_but_health_check_is_not(monkeypatch):
    slept = []
    fault = RevisionLatencyFault(
        delay_ms=2500,
        ttl_seconds=600,
        max_requests=30,
        clock=lambda: 100.0,
        sleep=slept.append,
    )
    service = product_reviews_server.ProductReviewService(
        review_latency_fault=fault
    )
    expected = object()
    monkeypatch.setattr(
        product_reviews_server,
        "get_product_reviews",
        lambda product_id: expected,
    )

    assert (
        service.GetProductReviews(
            SimpleNamespace(product_id="test-product"), context=None
        )
        is expected
    )
    assert slept == [2.5]

    health = service.Check(request=None, context=None)

    assert health.status == 1
    assert slept == [2.5]
