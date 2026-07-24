from __future__ import annotations

from collections import defaultdict
from statistics import mean, median, pstdev
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from .availability import AvailabilitySnapshot
from .config import Settings
from .models import Decision, Evidence


# Pure-function fallback used by unit tests and offline callers. The runtime
# Detector supplies the equivalent environment/Helm-backed Settings values.
TORAI_LITE_WEIGHTS = {
    "metric": 0.35,
    "trace": 0.25,
    "log": 0.20,
    "deploy": 0.10,
    "ai": 0.10,
}

# These route selectors reuse the production user-visible SLO definitions.
# Services without a route selector still require a server span, avoiding
# client/internal-span double counting while retaining generic coverage.
LATENCY_SPAN_NAMES = {
    "frontend": r"GET /|GET /product.*|GET /api/products.*|GET /api/data.*",
    "checkout": "oteldemo.CheckoutService/PlaceOrder",
}


def values(series: dict[str, Any]) -> list[float]:
    return [
        float(point[1])
        for point in series.get("values", [])
        if point[1] not in {"NaN", None}
    ]


def instant_value(series: list[dict[str, Any]]) -> float | None:
    """Extract one Prometheus instant-vector value without treating gaps as zero."""

    if not series:
        return None
    value = series[0].get("value", [None, None])[1]
    if value in {"NaN", None}:
        return None
    return float(value)


def robust_baseline(
    points: list[float], settings: Settings | None = None
) -> list[float]:
    """Discard isolated historical spikes before scoring the latest point.

    A single noisy sample must not inflate the mean/std enough to mask a
    separate incident. The 50% relative band keeps ordinary high-load
    variation in the service's own baseline while the MAD term accommodates
    naturally noisy services.
    """

    settings = settings or Settings()
    baseline = points[:-1]
    if len(baseline) < 4:
        return baseline
    center = median(baseline)
    mad = median(abs(point - center) for point in baseline)
    tolerance = max(
        settings.baseline_mad_multiplier * mad,
        abs(center) * settings.baseline_relative_band,
        1e-9,
    )
    cleaned = [point for point in baseline if abs(point - center) <= tolerance]
    return cleaned if len(cleaned) >= 3 else baseline


def anomaly_scores(
    points: list[float],
    settings: Settings | None = None,
    *,
    include_isolation: bool = True,
) -> dict[str, float]:
    settings = settings or Settings()
    if len(points) < 4:
        return {
            "ratio": 0.0,
            "zscore": 0.0,
            "ewma": 0.0,
            "isolation": 0.0,
            "trend": 0.0,
            "trend_consistency": 0.0,
            "slow_drift": 0.0,
        }
    baseline, current = robust_baseline(points, settings), points[-1]
    baseline_mean = mean(baseline)
    std = pstdev(baseline) if len(baseline) > 1 else 0.0
    # A perfectly flat baseline still has a meaningful relative deviation.
    # Use a 5% baseline band instead of turning that signal into z-score zero.
    zscore = abs(current - baseline_mean) / max(
        std, abs(baseline_mean) * settings.zscore_noise_floor, 1e-9
    )
    expected = baseline[0]
    residuals: list[float] = []
    for point in baseline[1:]:
        residuals.append(abs(point - expected))
        expected = settings.ewma_alpha * point + (1 - settings.ewma_alpha) * expected
    spread = (
        pstdev(residuals) if len(residuals) > 1 else max(mean(residuals or [0.0]), 1.0)
    )
    ewma = abs(current - expected) / max(
        settings.ewma_spread_multiplier * spread,
        abs(expected) * settings.ewma_relative_floor,
        1.0,
    )

    # A short-vs-long trend catches gradual degradation that never presents as
    # one large spike. The score is the fitted rise across the recent window,
    # normalized by the robust long-window level. Consistency prevents a
    # saw-tooth/noisy sequence from being treated as a sustained drain.
    recent = points[-max(settings.trend_window, 3) :]
    x_center = (len(recent) - 1) / 2
    denominator = sum((index - x_center) ** 2 for index in range(len(recent)))
    slope = (
        sum(
            (index - x_center) * (point - mean(recent))
            for index, point in enumerate(recent)
        )
        / denominator
        if denominator
        else 0.0
    )
    trend = max(slope * (len(recent) - 1), 0.0) / max(abs(baseline_mean), 1e-9)
    deltas = [right - left for left, right in zip(recent, recent[1:])]
    trend_consistency = (
        sum(delta > 0 for delta in deltas) / len(deltas) if deltas else 0.0
    )
    current_ratio = current / max(abs(baseline_mean), 1e-9)
    slow_drift = float(
        trend >= settings.trend_min_relative_change
        and trend_consistency >= settings.trend_min_consistency
        and current_ratio >= settings.trend_min_current_ratio
    )
    isolation = 0.0
    isolation_points = [*baseline, current]
    if include_isolation and len(isolation_points) >= 8 and len(set(isolation_points)) >= 3:
        data = np.array(isolation_points).reshape(-1, 1)
        model = IsolationForest(
            contamination=settings.isolation_contamination, random_state=7
        ).fit(data)
        if model.predict(data[-1:])[0] == -1:
            isolation = min(-float(model.score_samples(data[-1:])[0]), 1.0)
    return {
        "ratio": current / max(abs(baseline_mean), 1e-9),
        "zscore": zscore,
        "ewma": ewma,
        "isolation": isolation,
        "trend": trend,
        "trend_consistency": trend_consistency,
        "slow_drift": slow_drift,
    }


def acute_breach(scores: dict[str, float], settings: Settings | None = None) -> bool:
    """Detect a sudden shift while rejecting z-score-only busy noise."""

    settings = settings or Settings()
    return scores["ratio"] >= settings.ratio_threshold or (
        scores["zscore"] >= settings.zscore_threshold
        and scores["ewma"] >= settings.ewma_threshold
    )


def slow_drift_breach(scores: dict[str, float]) -> bool:
    return scores.get("slow_drift", 0.0) >= 1.0


def acute_window_breach(
    points: list[float], floor: float, settings: Settings | None = None
) -> bool:
    """Require persistence inside the current range-query window.

    The worker may still open an incident on its first poll, but one isolated
    scrape sample cannot page.  Every candidate is compared with the same
    earlier robust history so preceding incident samples do not inflate the
    baseline and mask the next one.  The latest sample must still be breached;
    this prevents paging after the signal has already recovered.
    """

    settings = settings or Settings()
    window = max(settings.acute_confirmation_window, 1)
    required = min(max(settings.acute_min_breach_points, 1), window)
    if len(points) < window + 3:
        scores = anomaly_scores(points, settings)
        return points[-1] >= floor and acute_breach(scores, settings)

    reference = points[:-window]
    recent = points[-window:]
    breaches = []
    for candidate in recent:
        # Isolation Forest contributes only to operator confidence and cannot
        # fire the acute gate. Re-fitting it for every confirmation candidate
        # adds CPU cost without changing the breach decision.
        candidate_scores = anomaly_scores(
            [*reference, candidate], settings, include_isolation=False
        )
        breaches.append(
            candidate >= floor and acute_breach(candidate_scores, settings)
        )
    return breaches[-1] and sum(breaches) >= required


def adaptive_breach(scores: dict[str, float], settings: Settings | None = None) -> bool:
    """Accept either an acute shift or a consistent multi-window drift."""

    return acute_breach(scores, settings) or slow_drift_breach(scores)


def signal_gate(
    points: list[float],
    floor: float,
    settings: Settings | None = None,
    *,
    include_isolation: bool = True,
) -> tuple[bool, str, dict[str, float]]:
    """Return raw breach, coverage state and adaptive scores.

    Empty telemetry is unavailable, not healthy. A thin baseline is explicitly
    warming and uses a conservative floor-only gate so a severe first-window
    spike is not silently discarded.
    """

    settings = settings or Settings()
    scores = anomaly_scores(points, settings, include_isolation=include_isolation)
    if not points:
        return False, "unavailable", scores
    if len(points) < 4:
        return points[-1] >= floor, "warming", scores
    # Acute anomalies must also violate the absolute safety floor. A gradual,
    # consistent drift is allowed to fire before the floor so memory-drain or
    # queue-growth symptoms are not hidden until the final spike.
    breached = acute_window_breach(points, floor, settings) or (
        slow_drift_breach(scores)
        and points[-1] >= floor * settings.trend_min_floor_ratio
    )
    return breached, "available", scores


def span_matchers(
    service: str,
    *,
    namespace: str | None = None,
    error_only: bool = False,
    include_operation: bool = True,
) -> str:
    matchers = [f'service_name="{service}"', 'span_kind="SPAN_KIND_SERVER"']
    if namespace:
        matchers.append(f'k8s_namespace_name="{namespace}"')
    span_name = LATENCY_SPAN_NAMES.get(service) if include_operation else None
    if span_name:
        operator = "=" if service == "checkout" else "=~"
        matchers.append(f'span_name{operator}"{span_name}"')
    if error_only:
        matchers.append('status_code="STATUS_CODE_ERROR"')
    return ",".join(matchers)


def torai_lite_score(
    *, weights: dict[str, float] | None = None, **signals: float | None
) -> dict[str, Any]:
    """Normalize available evidence into an auditable multi-source score.

    This preserves the research-inspired TORAI-lite weighting documented by
    the team, but deliberately omits the paper's clustering/causal ranker and
    therefore is not represented as a full TORAI implementation.
    """

    selected_weights = weights or TORAI_LITE_WEIGHTS
    available = {
        name: min(max(float(value), 0.0), 1.0)
        for name, value in signals.items()
        if name in selected_weights and value is not None
    }
    denominator = sum(selected_weights[name] for name in available)
    score = (
        sum(selected_weights[name] * value for name, value in available.items())
        / denominator
        if denominator
        else 0.0
    )
    return {
        "score": round(score, 4),
        "components": {name: round(value, 4) for name, value in available.items()},
        "missing_sources": sorted(set(selected_weights) - set(available)),
    }


class Detector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._streaks: dict[str, int] = defaultdict(int)

    def _confidence(self, base: float, scores: dict[str, float]) -> float:
        """Explainable evidence score; Isolation Forest cannot fire a gate."""

        return min(
            base
            + self.settings.zscore_confidence_weight
            * min(scores["zscore"] / max(self.settings.zscore_threshold, 1e-9), 1.0)
            + self.settings.ewma_confidence_weight
            * min(scores["ewma"] / max(self.settings.ewma_threshold, 1e-9), 1.0)
            + self.settings.isolation_confidence_weight * scores["isolation"]
            + self.settings.trend_confidence_weight * scores["slow_drift"],
            self.settings.maximum_confidence,
        )

    def availability(self, snapshot: AvailabilitySnapshot) -> Decision:
        """Classify workload availability without treating missing data as down."""

        coverage_status = (
            "unavailable" if snapshot.state == "unknown" else "available"
        )
        breached = snapshot.state in {"degraded", "down"}
        key = f"service_availability:{snapshot.service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = (
            self._streaks[key]
            >= max(self.settings.availability_sustained_polls, 1)
        )
        confidence = (
            self.settings.availability_down_confidence
            if snapshot.state == "down"
            else self.settings.availability_degraded_confidence
            if snapshot.state == "degraded"
            else 0.0
        )
        return Decision(
            anomalous=anomalous,
            breached=breached,
            coverage_status=coverage_status,
            incident_type="service_availability",
            service=snapshot.service,
            severity="high" if snapshot.state == "down" else "medium",
            confidence=confidence,
            root_cause=(
                f"Kubernetes reports {snapshot.available_replicas}/"
                f"{snapshot.desired_replicas} available replicas for "
                f"{snapshot.service}; the workload is {snapshot.state}, but "
                "events, logs and recent changes are required to assign cause."
            ),
            evidence=[
                Evidence(
                    source="kubernetes-api",
                    query=f"deployment/{snapshot.service}/status",
                    window="current",
                    value=snapshot.state,
                ),
                Evidence(
                    source="kubernetes-api",
                    query="desired/available/ready/updated replicas",
                    window="current",
                    value=(
                        f"{snapshot.desired_replicas}/"
                        f"{snapshot.available_replicas}/"
                        f"{snapshot.ready_replicas}/"
                        f"{snapshot.updated_replicas}"
                    ),
                ),
            ],
            candidates=[
                {
                    "service": snapshot.service,
                    "score": confidence,
                    "signals": {
                        "availability_state": snapshot.state,
                        "desired_replicas": snapshot.desired_replicas,
                        "available_replicas": snapshot.available_replicas,
                        "ready_replicas": snapshot.ready_replicas,
                        "updated_replicas": snapshot.updated_replicas,
                        "reason": snapshot.reason,
                    },
                }
            ],
            runbook_id="service-availability-escalation",
            recommended_action=(
                "Page the service owner, inspect Deployment/Pod events and "
                "recent rollout state, and restore availability through the "
                "approved service runbook."
            ),
        )

    def latency(
        self, service: str, series: list[dict[str, Any]], query: str
    ) -> Decision:
        points = values(series[0]) if series else []
        current = points[-1] if points else 0.0
        breached, coverage_status, scores = signal_gate(
            points, self.settings.latency_threshold_ms, self.settings
        )
        key = f"service_latency_spike:{service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = self._streaks[key] >= self.settings.sustained_polls
        confidence = self._confidence(self.settings.latency_confidence_base, scores)
        return Decision(
            anomalous=anomalous,
            breached=breached,
            coverage_status=coverage_status,
            incident_type="service_latency_spike",
            service=service,
            severity=(
                "high"
                if current
                >= self.settings.latency_threshold_ms
                * self.settings.latency_high_multiplier
                else "medium"
            ),
            confidence=confidence,
            root_cause=f"Sustained p95 latency degradation on {service}; dependency or recent deployment correlation requires confirmation.",
            evidence=[
                Evidence(
                    source="prometheus",
                    query=query,
                    window=f"{self.settings.lookback_minutes}m",
                    value="unavailable"
                    if coverage_status == "unavailable"
                    else round(current, 2),
                ),
                Evidence(
                    source="detector",
                    query="baseline_coverage",
                    window=f"{self.settings.lookback_minutes}m",
                    value=coverage_status,
                ),
            ],
            candidates=[
                {"service": service, "score": round(confidence, 3), "signals": scores}
            ],
            runbook_id="deployment-latency-rollback",
            recommended_action="Review recent deployment and, after approval, roll back to the previous known-good ReplicaSet.",
        )

    def error_rate(
        self,
        service: str,
        series: list[dict[str, Any]],
        query: str,
        *,
        burn_rates: tuple[float | None, float | None] | None = None,
    ) -> Decision:
        points = values(series[0]) if series else []
        current = points[-1] if points else 0.0
        slo_target = self.settings.service_slo_targets.get(service)
        detection_floor = self.settings.error_rate_threshold
        if slo_target is not None:
            detection_floor = min(
                detection_floor,
                (1 - slo_target) * self.settings.burn_rate_warning_threshold,
            )
        breached, coverage_status, scores = signal_gate(
            points, detection_floor, self.settings
        )
        impact: dict[str, Any]
        burn_evidence: list[Evidence] = []
        if slo_target is None:
            impact = {
                "level": "fixed_threshold_fallback",
                "basis": "no_approved_service_slo",
                "current_error_rate": round(current, 6),
                "threshold": self.settings.error_rate_threshold,
            }
            severity = (
                "high"
                if current
                >= self.settings.error_rate_threshold
                * self.settings.error_high_multiplier
                else "medium"
            )
        else:
            short_rate, long_rate = burn_rates or (None, None)
            short_window = self.settings.burn_rate_short_window_minutes
            long_window = self.settings.burn_rate_long_window_minutes
            warning = self.settings.burn_rate_warning_threshold
            critical = self.settings.burn_rate_critical_threshold
            if short_rate is None or long_rate is None:
                impact_level = "burn_rate_unavailable"
            elif short_rate >= critical and long_rate >= critical:
                impact_level = "critical_budget_burn"
            elif short_rate >= warning and long_rate >= warning:
                impact_level = "warning_budget_burn"
            else:
                impact_level = "budget_burn_below_warning"
            if impact_level in {"warning_budget_burn", "critical_budget_burn"}:
                # A sustained, request-weighted SLO burn is itself a breach
                # even when a recently degraded baseline has adapted to it.
                breached = True
                coverage_status = "available"
            impact = {
                "level": impact_level,
                "basis": "multi_window_error_budget_burn",
                "slo_target": slo_target,
                "error_budget": round(1 - slo_target, 6),
                "short_window": f"{short_window}m",
                "short_burn_rate": (
                    round(short_rate, 4) if short_rate is not None else None
                ),
                "long_window": f"{long_window}m",
                "long_burn_rate": (
                    round(long_rate, 4) if long_rate is not None else None
                ),
                "warning_threshold": warning,
                "critical_threshold": critical,
                "source": "prometheus_instant_query",
            }
            severity = "high" if impact_level == "critical_budget_burn" else "medium"
            for window, value in (
                (short_window, short_rate),
                (long_window, long_rate),
            ):
                burn_evidence.append(
                    Evidence(
                        source="prometheus",
                        query=error_budget_burn_rate_query(
                            service,
                            slo_target,
                            window,
                            self.settings.minimum_request_count,
                            self.settings.namespace,
                        ),
                        window=f"{window}m",
                        value=round(value, 4) if value is not None else "unavailable",
                    )
                )
        key = f"service_error_rate_spike:{service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = self._streaks[key] >= self.settings.sustained_polls
        confidence = self._confidence(self.settings.error_confidence_base, scores)
        return Decision(
            anomalous=anomalous,
            breached=breached,
            coverage_status=coverage_status,
            incident_type="service_error_rate_spike",
            service=service,
            severity=severity,
            confidence=confidence,
            root_cause=(
                f"Sustained error-rate degradation on {service}; logs, traces and recent deployment "
                "evidence are required before assigning a root cause."
            ),
            impact=impact,
            evidence=[
                Evidence(
                    source="prometheus",
                    query=query,
                    window=f"{self.settings.lookback_minutes}m",
                    value="unavailable"
                    if coverage_status == "unavailable"
                    else round(current, 4),
                ),
                Evidence(
                    source="detector",
                    query="baseline_coverage",
                    window=f"{self.settings.lookback_minutes}m",
                    value=coverage_status,
                ),
                *burn_evidence,
            ],
            candidates=[
                {"service": service, "score": round(confidence, 3), "signals": scores}
            ],
            runbook_id="service-error-rate-escalation",
            recommended_action="Correlate failed traces and error logs, then escalate to the service owner.",
        )

    def llm_error(
        self,
        service: str,
        series: list[dict[str, Any]],
        query: str,
        log_count: int | None = 0,
    ) -> Decision:
        points = values(series[0]) if series else []
        current = points[-1] if points else 0.0
        breached, coverage_status, scores = signal_gate(
            points, self.settings.llm_error_threshold, self.settings
        )
        # Logs enrich confidence/evidence but never fire an incident without a
        # metric breach. This avoids static log-count and duplicate-log noise.
        key = f"llm_timeout_error:{service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = self._streaks[key] >= self.settings.sustained_polls
        torai = torai_lite_score(
            weights={
                "metric": self.settings.torai_metric_weight,
                "trace": self.settings.torai_trace_weight,
                "log": self.settings.torai_log_weight,
                "deploy": self.settings.torai_deploy_weight,
                "ai": self.settings.torai_ai_weight,
            },
            metric=min(
                max(scores["ratio"] - 1, 0)
                / max(self.settings.torai_metric_relative_span, 1e-9),
                1.0,
            ),
            log=(
                None
                if log_count is None
                else min(
                    log_count / max(self.settings.torai_log_count_saturation, 1e-9),
                    1.0,
                )
            ),
            ai=min(current / max(self.settings.llm_error_threshold, 1e-9), 1.0),
        )
        confidence = min(
            self.settings.llm_confidence_base
            + self.settings.torai_confidence_weight * torai["score"]
            + self.settings.isolation_confidence_weight * scores["isolation"]
            + self.settings.trend_confidence_weight * scores["slow_drift"],
            self.settings.maximum_confidence,
        )
        evidence = [
            Evidence(
                source="prometheus",
                query=query,
                window=f"{self.settings.lookback_minutes}m",
                value="unavailable"
                if coverage_status == "unavailable"
                else round(current, 4),
            ),
            Evidence(
                source="detector",
                query="baseline_coverage",
                window=f"{self.settings.lookback_minutes}m",
                value=coverage_status,
            ),
        ]
        if log_count is None:
            evidence.append(
                Evidence(
                    source="opensearch",
                    query="timeout OR rate_limit OR error",
                    window=f"{self.settings.lookback_minutes}m",
                    value="unavailable",
                )
            )
        elif log_count:
            evidence.append(
                Evidence(
                    source="opensearch",
                    query="timeout OR rate_limit OR error",
                    window=f"{self.settings.lookback_minutes}m",
                    value=log_count,
                )
            )
        return Decision(
            anomalous=anomalous,
            breached=breached,
            coverage_status=coverage_status,
            incident_type="llm_timeout_error",
            service=service,
            severity="high"
            if current >= self.settings.llm_high_error_rate
            else "medium",
            confidence=confidence,
            root_cause="LLM calls show sustained timeout/error or provider rate-limit evidence.",
            evidence=evidence,
            candidates=[
                {
                    "service": service,
                    "score": round(confidence, 3),
                    "signals": {**torai, "anomaly": scores},
                },
            ],
            runbook_id="llm-timeout-escalation",
            recommended_action="Confirm provider/configuration and fallback health; escalate because no bounded automatic mutation is approved.",
        )


def latency_query(service: str, namespace: str | None = None) -> str:
    return (
        "histogram_quantile(0.95, sum by (le) "
        f"(rate(traces_span_metrics_duration_milliseconds_bucket{{{span_matchers(service, namespace=namespace)}}}[5m])))"
    )


def llm_error_query(
    service: str, minimum_calls: int = 5, namespace: str | None = None
) -> str:
    """Build a per-emitter LLM error-rate query.

    ``service`` may be an exact service name or an empty string for discovery
    across every instrumented LLM caller. The resulting Prometheus series
    always retains ``service_name`` so the worker can assign the incident to
    the real emitting service instead of a configured global owner.
    """

    matchers = []
    if service:
        matchers.append(f'service_name="{service}"')
    if namespace:
        matchers.append(f'k8s_namespace_name="{namespace}"')
    selector = "{" + ",".join(matchers) + "}" if matchers else ""
    return (
        f"(sum by (service_name) (rate(app_llm_errors_total{selector}[5m])) "
        f"/ clamp_min(sum by (service_name) (rate(app_llm_calls_total{selector}[5m])), 0.000001)) "
        "and on(service_name) "
        f"(sum by (service_name) (increase(app_llm_calls_total{selector}[5m])) >= {minimum_calls})"
    )


def error_rate_query(
    service: str, minimum_requests: int = 20, namespace: str | None = None
) -> str:
    # The canonical frontend error SLI covers all normalized frontend server
    # operations. Internal service signals retain their documented operation.
    include_operation = service != "frontend"
    all_spans = span_matchers(
        service, namespace=namespace, include_operation=include_operation
    )
    error_spans = span_matchers(
        service,
        namespace=namespace,
        error_only=True,
        include_operation=include_operation,
    )
    return (
        "(sum(rate(traces_span_metrics_calls_total{"
        f"{error_spans}}}[5m])) "
        f"/ clamp_min(sum(rate(traces_span_metrics_calls_total{{{all_spans}}}[5m])), 0.000001)) "
        "and on() (sum(increase(traces_span_metrics_calls_total{"
        f"{all_spans}}}[5m])) >= {minimum_requests})"
    )


def error_budget_burn_rate_query(
    service: str,
    slo_target: float,
    window_minutes: int,
    minimum_requests: int = 20,
    namespace: str | None = None,
) -> str:
    """Return request-weighted error-budget consumption for one exact window."""

    if not 0 < slo_target < 1:
        raise ValueError("slo_target must be between 0 and 1")
    if window_minutes <= 0:
        raise ValueError("window_minutes must be positive")
    all_spans = span_matchers(
        service, namespace=namespace, include_operation=True
    )
    error_spans = span_matchers(
        service,
        namespace=namespace,
        error_only=True,
        include_operation=True,
    )
    error_budget = 1 - slo_target
    window = f"{window_minutes}m"
    return (
        "((sum(increase(traces_span_metrics_calls_total{"
        f"{error_spans}}}[{window}])) "
        f"/ clamp_min(sum(increase(traces_span_metrics_calls_total{{{all_spans}}}[{window}])), 1)) "
        f"/ {error_budget:.10g}) "
        "and on() (sum(increase(traces_span_metrics_calls_total{"
        f"{all_spans}}}[{window}])) >= {minimum_requests})"
    )


def request_rate_query(service: str, namespace: str | None = None) -> str:
    """Return server request throughput without using it as a health signal."""

    matchers = span_matchers(
        service,
        namespace=namespace,
        include_operation=False,
    )
    return (
        "sum(rate(traces_span_metrics_calls_total{"
        f"{matchers}}}[5m]))"
    )


def classify_service_state(
    availability: AvailabilitySnapshot,
    request_rate: float | None,
    *,
    latency_breached: bool,
    error_rate_breached: bool,
    busy_request_rate_threshold: float,
) -> str:
    """Combine workload availability, traffic and SLO state for operators."""

    if availability.state in {"unknown", "idle", "down"}:
        return availability.state
    if availability.state == "degraded" or latency_breached or error_rate_breached:
        return "degraded"
    if (
        request_rate is not None
        and request_rate >= max(busy_request_rate_threshold, 0.0)
    ):
        return "busy"
    return "healthy"
