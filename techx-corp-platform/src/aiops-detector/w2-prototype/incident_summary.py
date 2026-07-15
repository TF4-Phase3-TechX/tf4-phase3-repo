import json
from datetime import datetime, timezone
from urllib.parse import urlencode, quote

class IncidentSummaryGenerator:
    """
    Generates a human-readable incident summary from structured detector output.
    Addresses Task TF4AIO-43.

    Design:
    - Reads verification queries directly from detector evidence metadata
      (no hard-coded queries).
    - Preserves service, environment, and tenant_id scope from detector output.
    - URL-encodes all Grafana Explore links.
    """

    def __init__(
        self,
        grafana_base_url: str = "http://grafana.internal",
        opensearch_datasource_uid: str = "opensearch",
    ):
        self.grafana_base_url = grafana_base_url.rstrip("/")
        self.opensearch_datasource_uid = opensearch_datasource_uid

    def _build_grafana_explore_url(self, query: str) -> str:
        """Builds a properly URL-encoded Grafana Explore link for OpenSearch."""
        explore_params = {
            "left": json.dumps(
                [
                    "now-1h",
                    "now",
                    self.opensearch_datasource_uid,
                    {"query": query},
                ]
            )
        }
        return f"{self.grafana_base_url}/explore?{urlencode(explore_params)}"

    def generate_summary(self, detector_output: dict) -> str:
        """
        Generate a Markdown incident summary.

        Reads query metadata, scope labels, and score breakdown directly from
        detector_output — no reconstruction or hard-coding.
        """
        # --- Core scope labels (must be preserved from detector) ---
        service = detector_output.get("service", "unknown-service")
        environment = detector_output.get("environment", "unknown-env")
        tenant_id = detector_output.get("tenant_id", "unknown-tenant")
        timestamp = detector_output.get("timestamp", datetime.now(timezone.utc).isoformat())
        severity = detector_output.get("severity", "unknown").upper()

        # --- Evidence metadata from detector (Task 38 / Task 41 output) ---
        evidence = detector_output.get("evidence", {})

        # For Task 38 (RCA engine) output
        metric_query = evidence.get("metric_query", "N/A")
        log_query = evidence.get("log_query", "N/A")
        ai_query = evidence.get("ai_query", "N/A")
        sources_unavailable = evidence.get("sources_unavailable", 0)

        # For Task 41 (LLM detector) output
        metrics_found = evidence.get("metrics_found", 0)
        logs_found = evidence.get("logs_found", 0)
        metrics_available = evidence.get("metrics_available", True)
        logs_available = evidence.get("logs_available", True)

        # --- RCA scoring (from Task 38 output) ---
        metric_score = detector_output.get("metric_anomaly_score")
        trace_score = detector_output.get("trace_error_score")
        log_score = detector_output.get("log_anomaly_score")
        ai_score = detector_output.get("ai_telemetry_score")
        total_score = detector_output.get("total_service_score", 0.0)
        confidence = detector_output.get("confidence", "unknown")

        def fmt_score(s):
            return f"{s:.2f}" if s is not None else "N/A (source unavailable)"

        # --- Confidence label ---
        if confidence == "high" and total_score >= 0.8:
            confidence_label = f"High — score {total_score:.2f}, all sources available"
        elif confidence == "partial":
            confidence_label = f"Partial — score {total_score:.2f}, {sources_unavailable} source(s) unavailable"
        elif confidence == "unknown":
            confidence_label = "Unknown — all telemetry sources were unavailable during evaluation"
        else:
            confidence_label = f"Low — score {total_score:.2f}"

        # --- Grafana link (URL-encoded) ---
        grafana_log_link = self._build_grafana_explore_url(log_query)

        summary = f"""# 🚨 AIOps Incident Summary

**Service:** `{service}`
**Environment:** `{environment}`
**Tenant:** `{tenant_id}`
**Severity:** `{severity}`
**Detected At:** {timestamp}
**Confidence:** {confidence_label}

---

## 📊 RCA Score Breakdown

| Signal | Score | Weight |
|---|---|---|
| Metric Anomaly (HTTP 5xx / app errors) | {fmt_score(metric_score)} | 0.35 |
| Trace Errors (Jaeger) | {fmt_score(trace_score)} | 0.25 |
| Log Anomaly (OpenSearch) | {fmt_score(log_score)} | 0.20 |
| AI Telemetry (app_llm_* errors) | {fmt_score(ai_score)} | 0.20 |
| **Total Service Score** | **{total_score:.2f}** | — |

---

## 🔍 Verification Queries
Paste these into your observability stack to reproduce the detector signal.

**Metrics (Prometheus):**
```promql
{metric_query}
```

**AI Telemetry (Prometheus):**
```promql
{ai_query}
```

**Logs (OpenSearch / Lucene):**
```lucene
{log_query}
```
[🔗 View Logs in Grafana (URL-encoded)]({grafana_log_link})

---

## ⚠️ Limitations & Signal Gaps
- **Source availability:** {sources_unavailable} telemetry source(s) were unavailable during this evaluation; unavailable sources are excluded from score re-normalisation.
- **Trace Context:** OTel span status may not reflect LLM errors if the SDK handles failures gracefully without calling `span.set_status(StatusCode.ERROR)`.
- **Rate Limits vs. Crashes:** A `429 rate_limited` event scores the same as a hard error. Check provider billing dashboard if `ai_score` is the primary driver.
"""
        return summary


if __name__ == "__main__":
    # Simulate Task 38 (RCA Engine) output — no hard-coded queries
    mock_rca_output = {
        "service": "product-reviews",
        "environment": "production",
        "tenant_id": "default",
        "timestamp": "2026-07-15T09:40:00Z",
        "metric_anomaly_score": 0.9,
        "trace_error_score": None,           # Jaeger unavailable
        "log_anomaly_score": 0.6,
        "ai_telemetry_score": 1.0,
        "total_service_score": 0.83,
        "confidence": "partial",
        "is_incident": True,
        "evidence": {
            "metric_query": 'sum(rate(http_server_requests_total{service="product-reviews", status=~"5.."}[5m])) / sum(rate(http_server_requests_total{service="product-reviews"}[5m]))',
            "log_query": 'kubernetes.labels.app:"product-reviews" AND level:"ERROR"',
            "ai_query": 'sum(rate(app_llm_requests_total{service="product-reviews", status=~"error|timeout|rate_limited"}[5m]))',
            "sources_unavailable": 1,
        },
    }

    generator = IncidentSummaryGenerator()
    report = generator.generate_summary(mock_rca_output)
    with open("incident_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Report saved to incident_report.md")
    print(report)
