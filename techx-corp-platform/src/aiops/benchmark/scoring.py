from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .rcaeval import MetricWindow


@dataclass(frozen=True)
class MetricScore:
    service: str
    metric: str
    score: float
    robust_shift: float
    peak_shift: float
    persistence: float
    relative_change: float


@dataclass(frozen=True)
class ServiceScore:
    service: str
    score: float
    top_metrics: tuple[MetricScore, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "service": self.service,
            "score": self.score,
            "top_metrics": [asdict(metric) for metric in self.top_metrics],
        }


def baro_lite(window: MetricWindow) -> MetricScore:
    """Research-inspired baseline-vs-incident scorer, not a full BARO reproduction."""

    baseline = np.asarray(window.baseline, dtype=float)
    incident = np.asarray(window.incident, dtype=float)
    baseline_median = float(np.median(baseline))
    incident_median = float(np.median(incident))
    mad = float(np.median(np.abs(baseline - baseline_median))) * 1.4826
    standard_deviation = float(np.std(baseline))
    scale_floor = max(abs(baseline_median) * 0.01, 1e-9)
    scale = max(mad, standard_deviation * 0.25, scale_floor)
    robust_shift = abs(incident_median - baseline_median) / scale
    peak_shift = float(np.quantile(np.abs(incident - baseline_median), 0.95)) / scale
    persistence = float(np.mean(np.abs(incident - baseline_median) >= 3 * scale))
    relative_change = abs(incident_median - baseline_median) / max(abs(baseline_median), scale_floor)
    raw_score = (
        math.log1p(robust_shift)
        + 0.35 * math.log1p(peak_shift)
        + 1.5 * persistence
        + 0.2 * math.log1p(relative_change)
    )
    return MetricScore(
        service=window.service,
        metric=window.metric,
        score=round(raw_score, 6),
        robust_shift=round(robust_shift, 6),
        peak_shift=round(peak_shift, 6),
        persistence=round(persistence, 6),
        relative_change=round(relative_change, 6),
    )


def rank_services(windows: list[MetricWindow]) -> list[ServiceScore]:
    """Aggregate BARO-lite metric evidence into deterministic RCA candidates."""

    by_service: dict[str, list[MetricScore]] = {}
    for window in windows:
        metric = baro_lite(window)
        by_service.setdefault(metric.service, []).append(metric)
    rankings: list[ServiceScore] = []
    weights = (0.65, 0.25, 0.10)
    for service, metrics in by_service.items():
        metrics.sort(key=lambda item: (-item.score, item.metric))
        top = tuple(metrics[:3])
        score = sum(weight * metric.score for weight, metric in zip(weights, top))
        rankings.append(ServiceScore(service, round(score, 6), top))
    rankings.sort(key=lambda item: (-item.score, item.service))
    return rankings
