from __future__ import annotations

import json
from urllib.parse import urlencode

from .models import Incident


class IncidentSummaryGenerator:
    """Render an operator-facing summary from the stored evidence contract.

    This folds the team's PR #208 incident-summary prototype into the unified
    runtime. Queries are copied from evidence; they are never reconstructed or
    silently broadened here.
    """

    def __init__(self, grafana_base_url: str, opensearch_datasource_uid: str):
        self.grafana_base_url = grafana_base_url.rstrip("/")
        self.opensearch_datasource_uid = opensearch_datasource_uid

    def grafana_explore_url(self, query: str) -> str:
        left = json.dumps(
            [
                "now-1h",
                "now",
                self.opensearch_datasource_uid,
                {"query": query},
            ],
            separators=(",", ":"),
        )
        return f"{self.grafana_base_url}/explore?{urlencode({'left': left})}"

    def generate(self, incident: Incident) -> str:
        evidence_rows: list[str] = []
        log_links: list[str] = []
        for item in incident.evidence:
            reference = f" [reference]({item.reference})" if item.reference else ""
            evidence_rows.append(
                f"| {item.source} | `{item.query}` | {item.window} | `{item.value}`{reference} |"
            )
            if item.source == "opensearch" and item.query:
                log_links.append(
                    f"- [Open the exact log query in Grafana Explore]({self.grafana_explore_url(item.query)})"
                )

        candidates = "\n".join(
            f"- `{candidate.get('service', 'unknown')}`: score "
            f"`{candidate.get('score', 'n/a')}`; signals "
            f"`{json.dumps(candidate.get('signals', {}), sort_keys=True, separators=(',', ':'))}`"
            for candidate in incident.rca_candidates
        ) or "- No ranked candidate is available."
        impact = (
            json.dumps(incident.impact, sort_keys=True, indent=2)
            if incident.impact
            else '{"level": "not_assessed"}'
        )

        return f"""# AIOps Incident {incident.incident_id}

- **Service:** `{incident.affected_service}`
- **Environment:** `{incident.environment}`
- **Tenant:** `{incident.tenant_id}`
- **Type:** `{incident.incident_type}`
- **Severity:** `{incident.severity}`
- **Status:** `{incident.status.value}`
- **Detected:** `{incident.detected_at.isoformat()}`
- **Confidence:** `{incident.confidence:.2f}`

## Suspected cause

{incident.suspected_root_cause}

Correlation is not proof of causality. Confirm the evidence before approving an action.

## Customer/SLO impact

```json
{impact}
```

For error-rate incidents, `critical_budget_burn` requires both configured
short and long windows to exceed the critical threshold. Missing telemetry is
reported as unavailable, never as a healthy zero.

## Evidence

| Source | Exact query | Window | Observed value |
|---|---|---|---|
{chr(10).join(evidence_rows) or '| none | `n/a` | n/a | `n/a` |'}

{chr(10).join(log_links)}

## RCA candidates

{candidates}

## Response

- **Runbook:** `{incident.runbook_id}`
- **Recommended action:** {incident.recommended_action}
- **Approval:** `{incident.approval_status}`
- **Escalation reason:** {incident.escalation_reason or 'Not set'}
"""
