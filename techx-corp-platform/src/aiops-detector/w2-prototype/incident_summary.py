import json
from datetime import datetime

class IncidentSummaryGenerator:
    """
    Generates a human-readable incident summary MVP from structured detector output.
    Addresses Task TF4AIO-43 and integrates with Task TF4AIO-38 (RCA Engine).
    """
    
    def __init__(self, grafana_base_url="http://grafana.internal", opensearch_datasource_uid="opensearch"):
        self.grafana_base_url = grafana_base_url
        self.opensearch_datasource_uid = opensearch_datasource_uid

    def generate_summary(self, detector_output: dict) -> str:
        # If output comes from Task 38's RCARuleEngine
        service = detector_output.get("service", "product-reviews")
        timestamp = detector_output.get("timestamp", datetime.now().isoformat())
        
        # Read pre-calculated scores from Task 38
        metric_score = detector_output.get("metric_anomaly_score", 0.0)
        trace_score = detector_output.get("trace_error_score", 0.0)
        log_score = detector_output.get("log_anomaly_score", 0.0)
        ai_score = detector_output.get("ai_telemetry_score", 0.0)
        total_score = detector_output.get("total_service_score", 0.0)

        # 1. Determine Confidence & RCA Scoring (Phase 3 Requirement)
        if total_score >= 0.8:
            confidence = f"High (Service Score: {total_score:.2f})"
            severity = "HIGH"
        elif total_score >= 0.4:
            confidence = f"Medium (Service Score: {total_score:.2f})"
            severity = "MEDIUM"
        else:
            confidence = f"Low (Service Score: {total_score:.2f})"
            severity = "LOW"

        # 2. Build Evidence Links / Queries
        prom_query = f'sum(rate(aiops_llm_calls_total{{service="{service}", status=~"error|timeout|429"}}[5m])) / sum(rate(aiops_llm_calls_total{{service="{service}"}}[5m])) > 0.05'
        log_query = f'kubernetes.labels.app:"{service}" AND (message:*timeout* OR message:*429* OR message:*rate limit*) AND message:(*llm* OR *openai* OR *bedrock*)'
        
        grafana_log_link = f"{self.grafana_base_url}/explore?left=%5B%22now-1h%22,%22now%22,%22{self.opensearch_datasource_uid}%22,%7B%22query%22:%22{log_query}%22%7D%5D"

        # 3. Format the Markdown Summary
        summary = f"""# 🚨 AIOps Incident Summary: RCA_THRESHOLD_BREACH

**Service:** `{service}`
**Severity:** `{severity}`
**Detected At:** {timestamp}

## 📊 Overview
The AIOps detector identified a potential issue crossing the RCA threshold.
- **Metric Anomaly Score:** {metric_score:.2f}
- **Log Anomaly Score:** {log_score:.2f}
- **Trace Error Score:** {trace_score:.2f}
- **AI Telemetry Score:** {ai_score:.2f}
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
    # Mock output exactly as produced by Task 38 RCARuleEngine
    mock_incident = {
        "service": "product-reviews",
        "timestamp": "2026-07-15T15:40:00Z",
        "metric_anomaly_score": 1.0,
        "trace_error_score": 0.0,
        "log_anomaly_score": 1.0,
        "ai_telemetry_score": 1.0,
        "total_service_score": 0.75,
        "is_incident": True
    }

    generator = IncidentSummaryGenerator()
    report = generator.generate_summary(mock_incident)
    with open("incident_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("Report saved to incident_report.md")
