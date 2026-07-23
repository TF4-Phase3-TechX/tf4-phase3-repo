from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IncidentStatus(str, Enum):
    OPEN = "open"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    ROLLED_BACK = "rolled_back"


class Evidence(BaseModel):
    source: str
    query: str
    window: str
    value: float | str | None = None
    reference: str | None = None


class AuditEvent(BaseModel):
    at: datetime = Field(default_factory=utcnow)
    event: str
    detail: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    incident_id: str = Field(default_factory=lambda: f"inc-{uuid4().hex[:12]}")
    incident_type: str
    status: IncidentStatus = IncidentStatus.OPEN
    severity: str
    affected_service: str
    environment: str = "production"
    tenant_id: str = "default"
    detected_at: datetime = Field(default_factory=utcnow)
    last_observed_at: datetime = Field(default_factory=utcnow)
    confidence: float
    suspected_root_cause: str
    evidence: list[Evidence] = Field(default_factory=list)
    rca_candidates: list[dict[str, Any]] = Field(default_factory=list)
    runbook_id: str
    recommended_action: str
    approval_status: str = "not_requested"
    approval_expires_at: datetime | None = None
    policy_version: str | None = None
    execution_attempts: int = 0
    mutation_blocked: bool = False
    before_snapshot: dict[str, Any] | None = None
    verification_result: dict[str, Any] | None = None
    rollback_result: dict[str, Any] | None = None
    rollback_verification_result: dict[str, Any] | None = None
    escalation_reason: str | None = None
    audit_events: list[AuditEvent] = Field(default_factory=list)

    @property
    def dedup_key(self) -> str:
        return f"{self.incident_type}:{self.affected_service}"


class Decision(BaseModel):
    anomalous: bool
    incident_type: str
    service: str
    breached: bool = False
    coverage_status: Literal["available", "warming", "unavailable"] = "available"
    severity: str = "medium"
    confidence: float = 0.0
    root_cause: str = "Insufficient evidence"
    evidence: list[Evidence] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    runbook_id: str = "observe-and-escalate"
    recommended_action: str = "Collect more evidence and notify the owning team."
