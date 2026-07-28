from __future__ import annotations

from typing import Any


def target_error_rate_query(service: str, namespace: str, window: str) -> str:
    """Build the post-action error-rate guard for the mutated service.

    Verification is intentionally scoped to the action target. A cross-service
    or end-to-end guard must be declared by an action policy with an explicit
    dependency mapping; it must not be silently applied to every remediation.
    """

    matchers = (
        f'service_name="{service}",'
        'span_kind="SPAN_KIND_SERVER",'
        f'k8s_namespace_name="{namespace}"'
    )
    return (
        f'sum(rate(traces_span_metrics_calls_total{{{matchers},'
        f'status_code="STATUS_CODE_ERROR"}}[{window}])) '
        f'/ clamp_min(sum(rate(traces_span_metrics_calls_total{{{matchers}}}'
        f'[{window}])), 0.000001)'
    )


def target_request_count_query(service: str, namespace: str, window: str) -> str:
    """Request volume for the mutated service over the verification window."""

    matchers = (
        f'service_name="{service}",'
        'span_kind="SPAN_KIND_SERVER",'
        f'k8s_namespace_name="{namespace}"'
    )
    return (
        f"sum(increase(traces_span_metrics_calls_total{{{matchers}}}[{window}]))"
    )


def evaluate_target_slo(
    *,
    service: str,
    p95_latency_ms: float | None,
    latency_threshold_ms: float,
    target_error_rate: float | None,
    error_rate_threshold: float,
    request_count: float | None = None,
    minimum_request_count: float = 0,
) -> dict[str, Any]:
    """Evaluate only telemetry attributable to the mutated target.

    Missing latency or error-rate coverage fails closed. Insufficient request
    volume also fails closed so a near-empty series cannot claim recovery.
    """

    latency_healthy = (
        p95_latency_ms is not None and p95_latency_ms < latency_threshold_ms
    )
    error_rate_healthy = (
        target_error_rate is not None
        and target_error_rate < error_rate_threshold
    )
    volume_required = max(minimum_request_count, 0)
    volume_healthy = (
        True
        if volume_required <= 0
        else request_count is not None and request_count >= volume_required
    )
    coverage_complete = (
        p95_latency_ms is not None
        and target_error_rate is not None
        and (volume_required <= 0 or request_count is not None)
    )
    return {
        "healthy": (
            coverage_complete
            and latency_healthy
            and error_rate_healthy
            and volume_healthy
        ),
        "target_service": service,
        "p95_latency_ms": p95_latency_ms,
        "threshold_ms": latency_threshold_ms,
        "target_error_rate": target_error_rate,
        "target_error_rate_threshold": error_rate_threshold,
        "request_count": request_count,
        "minimum_request_count": volume_required,
        "volume_sufficient": volume_healthy,
        "coverage_complete": coverage_complete,
    }
