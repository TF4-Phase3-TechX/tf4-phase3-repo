from __future__ import annotations

from collections import defaultdict
from statistics import mean, median, pstdev
from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

from .config import Settings
from .models import Decision, Evidence


TORAI_LITE_WEIGHTS = {
    "metric": 0.35,
    "trace": 0.25,
    "log": 0.20,
    "deploy": 0.10,
    "ai": 0.10,
}


def values(series: dict[str, Any]) -> list[float]:
    return [float(point[1]) for point in series.get("values", []) if point[1] not in {"NaN", None}]


def robust_baseline(points: list[float]) -> list[float]:
    """Discard isolated historical spikes before scoring the latest point.

    A single noisy sample must not inflate the mean/std enough to mask a
    separate incident. The 50% relative band keeps ordinary high-load
    variation in the service's own baseline while the MAD term accommodates
    naturally noisy services.
    """

    baseline = points[:-1]
    if len(baseline) < 4:
        return baseline
    center = median(baseline)
    mad = median(abs(point - center) for point in baseline)
    tolerance = max(6 * mad, abs(center) * 0.5, 1e-9)
    cleaned = [point for point in baseline if abs(point - center) <= tolerance]
    return cleaned if len(cleaned) >= 3 else baseline


def anomaly_scores(points: list[float]) -> dict[str, float]:
    if len(points) < 4:
        return {"ratio": 0.0, "zscore": 0.0, "ewma": 0.0, "isolation": 0.0}
    baseline, current = robust_baseline(points), points[-1]
    baseline_mean = mean(baseline)
    std = pstdev(baseline) if len(baseline) > 1 else 0.0
    # A perfectly flat baseline still has a meaningful relative deviation.
    # Use a 5% baseline band instead of turning that signal into z-score zero.
    zscore = abs(current - baseline_mean) / max(std, abs(baseline_mean) * 0.05, 1e-9)
    expected = baseline[0]
    residuals: list[float] = []
    for point in baseline[1:]:
        residuals.append(abs(point - expected))
        expected = 0.35 * point + 0.65 * expected
    spread = pstdev(residuals) if len(residuals) > 1 else max(mean(residuals or [0.0]), 1.0)
    ewma = abs(current - expected) / max(3 * spread, abs(expected) * 0.25, 1.0)
    isolation = 0.0
    isolation_points = [*baseline, current]
    if len(isolation_points) >= 8 and len(set(isolation_points)) >= 3:
        data = np.array(isolation_points).reshape(-1, 1)
        model = IsolationForest(contamination=0.15, random_state=7).fit(data)
        if model.predict(data[-1:])[0] == -1:
            isolation = min(-float(model.score_samples(data[-1:])[0]), 1.0)
    return {
        "ratio": current / max(abs(baseline_mean), 1e-9),
        "zscore": zscore,
        "ewma": ewma,
        "isolation": isolation,
    }


def adaptive_breach(scores: dict[str, float]) -> bool:
    """Require a meaningful relative shift, not a z-score-only busy signal."""

    return scores["ratio"] >= 1.5 or (scores["zscore"] >= 3 and scores["ewma"] >= 1)


def torai_lite_score(**signals: float | None) -> dict[str, Any]:
    """Normalize available evidence into an auditable multi-source score.

    This preserves the research-inspired TORAI-lite weighting documented by
    the team, but deliberately omits the paper's clustering/causal ranker and
    therefore is not represented as a full TORAI implementation.
    """

    available = {
        name: min(max(float(value), 0.0), 1.0)
        for name, value in signals.items()
        if name in TORAI_LITE_WEIGHTS and value is not None
    }
    denominator = sum(TORAI_LITE_WEIGHTS[name] for name in available)
    score = (
        sum(TORAI_LITE_WEIGHTS[name] * value for name, value in available.items()) / denominator
        if denominator
        else 0.0
    )
    return {
        "score": round(score, 4),
        "components": {name: round(value, 4) for name, value in available.items()},
        "missing_sources": sorted(set(TORAI_LITE_WEIGHTS) - set(available)),
    }


class Detector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._streaks: dict[str, int] = defaultdict(int)

    def latency(self, service: str, series: list[dict[str, Any]], query: str) -> Decision:
        points = values(series[0]) if series else []
        current = points[-1] if points else 0.0
        scores = anomaly_scores(points)
        breached = current >= self.settings.latency_threshold_ms and adaptive_breach(scores)
        key = f"service_latency_spike:{service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = self._streaks[key] >= self.settings.sustained_polls
        confidence = min(0.45 + 0.1 * min(scores["zscore"], 3) + 0.15 * min(scores["ewma"], 1), 0.95)
        return Decision(
            anomalous=anomalous,
            incident_type="service_latency_spike",
            service=service,
            severity="high" if current >= self.settings.latency_threshold_ms * 2 else "medium",
            confidence=confidence,
            root_cause=f"Sustained p95 latency degradation on {service}; dependency or recent deployment correlation requires confirmation.",
            evidence=[Evidence(source="prometheus", query=query, window=f"{self.settings.lookback_minutes}m", value=round(current, 2))],
            candidates=[{"service": service, "score": round(confidence, 3), "signals": scores}],
            runbook_id="deployment-latency-rollback",
            recommended_action="Review recent deployment and, after approval, roll back to the previous known-good ReplicaSet.",
        )

    def error_rate(self, service: str, series: list[dict[str, Any]], query: str) -> Decision:
        points = values(series[0]) if series else []
        current = points[-1] if points else 0.0
        scores = anomaly_scores(points)
        breached = current >= self.settings.error_rate_threshold and adaptive_breach(scores)
        key = f"service_error_rate_spike:{service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = self._streaks[key] >= self.settings.sustained_polls
        confidence = min(
            0.5
            + 0.1 * min(scores["zscore"], 3)
            + 0.15 * min(scores["ewma"], 1),
            0.95,
        )
        return Decision(
            anomalous=anomalous,
            incident_type="service_error_rate_spike",
            service=service,
            severity="high" if current >= self.settings.error_rate_threshold * 2 else "medium",
            confidence=confidence,
            root_cause=(
                f"Sustained error-rate degradation on {service}; logs, traces and recent deployment "
                "evidence are required before assigning a root cause."
            ),
            evidence=[
                Evidence(
                    source="prometheus",
                    query=query,
                    window=f"{self.settings.lookback_minutes}m",
                    value=round(current, 4),
                )
            ],
            candidates=[{"service": service, "score": round(confidence, 3), "signals": scores}],
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
        scores = anomaly_scores(points)
        # Logs enrich confidence/evidence but never fire an incident without a
        # metric breach. This avoids static log-count and duplicate-log noise.
        breached = current >= self.settings.llm_error_threshold and adaptive_breach(scores)
        key = f"llm_timeout_error:{service}"
        self._streaks[key] = self._streaks[key] + 1 if breached else 0
        anomalous = self._streaks[key] >= self.settings.sustained_polls
        torai = torai_lite_score(
            metric=min(max(scores["ratio"] - 1, 0) / 0.5, 1.0),
            log=None if log_count is None else min(log_count / 3, 1.0),
            ai=min(current / max(self.settings.llm_error_threshold, 1e-9), 1.0),
        )
        confidence = min(0.45 + 0.5 * torai["score"], 0.95)
        evidence = [Evidence(source="prometheus", query=query, window=f"{self.settings.lookback_minutes}m", value=round(current, 4))]
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
            evidence.append(Evidence(source="opensearch", query="timeout OR rate_limit OR error", window=f"{self.settings.lookback_minutes}m", value=log_count))
        return Decision(
            anomalous=anomalous,
            incident_type="llm_timeout_error",
            service=service,
            severity="high" if current >= 0.25 else "medium",
            confidence=confidence,
            root_cause="LLM calls show sustained timeout/error or provider rate-limit evidence.",
            evidence=evidence,
            candidates=[
                {"service": service, "score": round(confidence, 3), "signals": {**torai, "anomaly": scores}},
            ],
            runbook_id="llm-timeout-escalation",
            recommended_action="Confirm provider/configuration and fallback health; escalate because no bounded automatic mutation is approved.",
        )


def latency_query(service: str) -> str:
    return (
        "histogram_quantile(0.95, sum by (le) "
        f"(rate(traces_span_metrics_duration_milliseconds_bucket{{service_name=\"{service}\"}}[5m])))"
    )


def llm_error_query(service: str, minimum_calls: int = 5) -> str:
    # app_llm_* is emitted by product-reviews without a service label. The
    # caller-provided service remains part of the incident scope/output.
    del service
    return (
        "(sum(rate(app_llm_errors_total[5m])) "
        "/ clamp_min(sum(rate(app_llm_calls_total[5m])), 0.000001)) "
        f"and on() (sum(increase(app_llm_calls_total[5m])) >= {minimum_calls})"
    )


def error_rate_query(service: str, minimum_requests: int = 20) -> str:
    return (
        "(sum(rate(traces_span_metrics_calls_total{"
        f"service_name=\"{service}\",status_code=\"STATUS_CODE_ERROR\"}}[5m])) "
        f"/ clamp_min(sum(rate(traces_span_metrics_calls_total{{service_name=\"{service}\"}}[5m])), 0.000001)) "
        "and on() (sum(increase(traces_span_metrics_calls_total{"
        f"service_name=\"{service}\"}}[5m])) >= {minimum_requests})"
    )
