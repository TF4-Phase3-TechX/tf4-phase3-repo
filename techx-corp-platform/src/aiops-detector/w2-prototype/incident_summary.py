import json
from datetime import datetime

class IncidentSummaryGenerator:
    """
    Generates a human-readable incident summary MVP from structured detector output.
    Addresses Task TF4AIO-43.
    """
    
    def __init__(self, grafana_base_url="http://grafana.internal", opensearch_datasource_uid="opensearch"):
        self.grafana_base_url = grafana_base_url
        self.opensearch_datasource_uid = opensearch_datasource_uid

    def generate_summary(self, detector_output: dict) -> str:
        rule = detector_output.get("rule", "Unknown Rule")
        service = detector_output.get("service", "Unknown Service")
        severity = detector_output.get("severity", "unknown")
        timestamp = detector_output.get("timestamp", datetime.now().isoformat())
        evidence = detector_output.get("evidence", {})
        
        metrics_found = evidence.get("metrics_found", 0)
        logs_found = evidence.get("logs_found", 0)

        # 1. Determine Confidence & RCA Scoring (Phase 3 Requirement)
        # Service Score = 0.35 * Metric Anomaly + 0.25 * Trace Error + 0.20 * Log Anomaly + 0.20 * AI Telemetry Signal
        metric_anomaly = 1 if metrics_found > 0 else 0
        log_anomaly = 1 if logs_found > 0 else 0
        # Mocking Trace Error and AI Telemetry for MVP
        trace_error = 1 if metrics_found > 0 else 0 
        ai_telemetry = 1 if logs_found > 0 else 0
        
        service_score = (0.35 * metric_anomaly) + (0.25 * trace_error) + (0.20 * log_anomaly) + (0.20 * ai_telemetry)
        
        if service_score >= 0.8:
            confidence = f"High (Service Score: {service_score:.2f})"
        elif service_score >= 0.4:
            confidence = f"Medium (Service Score: {service_score:.2f})"
        else:
            confidence = f"Low (Service Score: {service_score:.2f})"

        # 2. Build Evidence Links / Queries
        # Provide the raw OpenSearch / PromQL that users can paste into Grafana Explore
        prom_query = f'sum(rate(aiops_llm_calls_total{{service="{service}", status=~"error|timeout|429"}}[5m])) / sum(rate(aiops_llm_calls_total{{service="{service}"}}[5m])) > 0.05'
        log_query = f'kubernetes.labels.app:"{service}" AND (message:*timeout* OR message:*429* OR message:*rate limit*) AND message:(*llm* OR *openai* OR *bedrock*)'
        
        grafana_log_link = f"{self.grafana_base_url}/explore?left=%5B%22now-1h%22,%22now%22,%22{self.opensearch_datasource_uid}%22,%7B%22query%22:%22{log_query}%22%7D%5D"

        # 3. Format the Markdown Summary
        summary = f"""# 🚨 AIOps Incident Summary: {rule.upper()}

**Service:** `{service}`
**Severity:** `{severity.upper()}`
**Detected At:** {timestamp}

## 📊 Overview
The AIOps detector identified a potential issue matching the rule `{rule}`.
- **Metrics triggered:** {metrics_found}
- **Logs matched:** {logs_found}
- **Confidence Level:** {confidence}

## 🔍 Evidence & Queries
You can verify the signals using the following queries in the observability stack:

**Metrics (Prometheus):**
```promql
{prom_query}
```

**Logs (OpenSearch):**
```lucene
{log_query}
```
[🔗 View Logs in Grafana]({grafana_log_link})

## ⚠️ Limitations & Notes
- **Trace Context:** Traces might not be linked if the downstream SDK handled the error gracefully without setting the OpenTelemetry span status to ERROR.
- **Cost Impact:** Rate limits (429) might trigger this alert but do not necessarily indicate a system crash, they might just be a quota exhaustion. Check billing metrics if applicable.
"""
        return summary

if __name__ == "__main__":
    # Mock detector output (similar to the one produced by Task 41)
    mock_incident = {
        "timestamp": "2026-07-15T15:40:00Z",
        "rule": "ai_llm_timeout_error",
        "service": "product-reviews",
        "environment": "production",
        "tenant_id": "default",
        "severity": "high",
        "evidence": {
            "metrics_found": 1,
            "logs_found": 15,
            "metric_details": [],
            "log_details": []
        }
    }

    generator = IncidentSummaryGenerator()
    report = generator.generate_summary(mock_incident)
    with open("incident_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Report saved to incident_report.md")
