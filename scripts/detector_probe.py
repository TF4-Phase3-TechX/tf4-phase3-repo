"""Helpers for classifying detector Prometheus probe outcomes.

These helpers are used by deterministic tests/fixtures so the output-channel
contract can be validated without depending on a live cluster.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal


PROMETHEUS_RULE_ID = "prometheus-up-probe-v1"
PROMETHEUS_DEFAULT_URL = (
    "http://prometheus.techx-observability.svc.cluster.local:9090/"
    "api/v1/query?query=up%20%3D%3D%201"
)
DEFAULT_RUNBOOK_URL = (
    "https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/"
    "docs/audit/runbooks/detector-prometheus-probe.md"
)


Outcome = Literal["prometheus_probe_ok", "prometheus_probe_empty", "prometheus_probe_error"]


@dataclass(frozen=True)
class ProbeClassification:
    outcome: Outcome
    severity: Literal["info", "warning", "critical"]
    summary: str
    observed_value: str


def classify_prometheus_response(response_text: str) -> ProbeClassification:
    """Classify a Prometheus HTTP response into the detector's outcome types."""

    if not response_text or not response_text.strip():
        return ProbeClassification(
            outcome="prometheus_probe_error",
            severity="critical",
            summary="Prometheus probe failed",
            observed_value="n/a",
        )

    try:
        response = json.loads(response_text)
    except json.JSONDecodeError:
        return ProbeClassification(
            outcome="prometheus_probe_error",
            severity="critical",
            summary="Prometheus probe failed",
            observed_value="parse_error",
        )

    if response.get("status") != "success":
        return ProbeClassification(
            outcome="prometheus_probe_error",
            severity="critical",
            summary="Prometheus probe failed",
            observed_value=str(response.get("status", "error")),
        )

    results = response.get("data", {}).get("result", [])
    up_samples = 0
    for result in results:
        value = result.get("value")
        if isinstance(value, list) and len(value) >= 2 and str(value[1]) == "1":
            up_samples += 1

    if up_samples >= 1:
        return ProbeClassification(
            outcome="prometheus_probe_ok",
            severity="info",
            summary="Prometheus probe succeeded with up==1",
            observed_value=str(up_samples),
        )

    return ProbeClassification(
        outcome="prometheus_probe_empty",
        severity="warning",
        summary="Prometheus probe returned no up==1 samples",
        observed_value="0",
    )


def build_payload(
    classification: ProbeClassification,
    *,
    timestamp: str,
    detection_id: str,
    service: str,
    environment: str,
    channel: str = "stdout-jsonl",
    schema_version: str = "1.0",
    threshold: str = "at_least_one_up_target",
    runbook_url: str = DEFAULT_RUNBOOK_URL,
    prometheus_url: str = PROMETHEUS_DEFAULT_URL,
    owner: str = "AIOps-oncall",
    owner_response_path: str = "open-runbook-then-create-incident-ticket",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "detection_id": detection_id,
        "detector": "aioops-detector",
        "service": service,
        "environment": environment,
        "channel": channel,
        "schema_version": schema_version,
        "incident_type": classification.outcome,
        "severity": classification.severity,
        "summary": classification.summary,
        "observed_value": classification.observed_value,
        "threshold": threshold,
        "runbook_url": runbook_url,
        "evidence": {"prometheus_url": prometheus_url},
        "owner": owner,
        "owner_response_path": owner_response_path,
    }