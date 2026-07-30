"""Typed models for Mandate-26 cross-service RCA."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

class SignalObservation(BaseModel):
    signal: str
    anomalous: bool
    breached: bool = False
    coverage_status: Literal["available", "warming", "unavailable"] = "available"
    confidence: float = 0.0
    severity: str = "medium"
    observed_at: datetime
    first_breached_at: datetime | None = None
    first_anomalous_at: datetime | None = None
    # Kept structural to avoid coupling the pure RCA model layer back to the
    # incident model module. Worker/replay evidence remains JSON serializable.
    evidence: list[Any] = Field(default_factory=list)


class RCAObservation(BaseModel):
    service: str
    original_service_names: list[str] = Field(default_factory=list)
    signals: list[SignalObservation] = Field(default_factory=list)
    first_breached_at: datetime | None = None
    first_anomalous_at: datetime | None = None

    @property
    def is_anomalous(self) -> bool:
        return any(s.anomalous for s in self.signals)

    @property
    def max_confidence(self) -> float:
        if not self.signals:
            return 0.0
        return max(s.confidence for s in self.signals if s.anomalous) if any(
            s.anomalous for s in self.signals
        ) else max((s.confidence for s in self.signals), default=0.0)

    def onset(self) -> datetime | None:
        if self.first_breached_at is not None:
            return self.first_breached_at
        if self.first_anomalous_at is not None:
            return self.first_anomalous_at
        times = [
            s.first_breached_at or s.first_anomalous_at or s.observed_at
            for s in self.signals
            if s.anomalous or s.breached
        ]
        return min(times) if times else None


class RCAEvidenceFact(BaseModel):
    source: Literal["trace", "topology", "temporal", "anomaly"]
    fact: str
    support: float
    available: bool = True
    trace_id: str | None = None
    span_ids: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    provenance: str | None = None


class RCASignalContribution(BaseModel):
    available: bool
    raw_value: float | None
    weight: float
    weighted_value: float | None
    reason: str


class RCACandidate(BaseModel):
    service: str
    score: float
    rank: int
    classification: Literal[
        "suspected_root",
        "root_candidate",
        "explained_downstream_symptom",
        "unexplained_parallel_anomaly",
        "insufficient_evidence",
    ]
    contributions: dict[str, RCASignalContribution]
    base_score: float = 0.0
    penalties: dict[str, float] = Field(default_factory=dict)
    explained_affected_services: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    evidence: list[RCAEvidenceFact] = Field(default_factory=list)

    def legacy_dict(self) -> dict[str, Any]:
        """Projection for Incident.rca_candidates / summary renderer."""

        signals = {
            name: (
                contrib.weighted_value
                if contrib.weighted_value is not None
                else (contrib.raw_value if contrib.raw_value is not None else 0.0)
            )
            for name, contrib in self.contributions.items()
        }
        return {
            "service": self.service,
            "score": self.score,
            "rank": self.rank,
            "classification": self.classification,
            "signals": signals,
            "base_score": self.base_score,
            "penalties": dict(self.penalties),
            "explained_affected_services": list(self.explained_affected_services),
            "contradictions": list(self.contradictions),
        }


class RCAResult(BaseModel):
    schema_version: int = 1
    model_version: str
    attribution_status: Literal[
        "attributed",
        "insufficient_evidence",
        "multiple_independent_clusters",
    ]
    suspected_root_service: str | None
    confidence: float
    score_margin: float | None
    explanation: str
    candidates: list[RCACandidate]
    unavailable_signals: list[str] = Field(default_factory=list)
    topology_provenance: list[str] = Field(default_factory=list)
    analysis_started_at: datetime
    analysis_ended_at: datetime
    skipped_reason: str | None = None
    processing_ms: float | None = None
    trace_count: int = 0
    span_count: int = 0

    def legacy_candidates(self) -> list[dict[str, Any]]:
        return [c.legacy_dict() for c in self.candidates]
