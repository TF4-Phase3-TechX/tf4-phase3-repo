import json
from datetime import datetime

class IncidentSummaryGenerator:
    """
    Generates a human-readable incident summary MVP from structured detector output.
    Addresses Task TF4AIO-43.
    """
    
    def __init__(self, grafana_base_url="http://grafana.internal", loki_datasource_uid="loki"):
        self.grafana_base_url = grafana_base_url
        self.loki_datasource_uid = loki_datasource_uid

    def generate_summary(self, detector_output: dict) -> str:
        rule = detector_output.get("rule", "Unknown Rule")
        service = detector_output.get("service", "Unknown Service")
        severity = detector_output.get("severity", "unknown")
        timestamp = detector_output.get("timestamp", datetime.now().isoformat())
        evidence = detector_output.get("evidence", {})
        
        metrics_found = evidence.get("metrics_found", 0)
        logs_found = evidence.get("logs_found", 0)

        # 1. Determine Confidence
        if metrics_found > 0 and logs_found > 0:
            confidence = "High (Correlated Metrics and Logs)"
        elif metrics_found > 0 or logs_found > 0:
            confidence = "Medium (Single Signal Source)"
        else:
            confidence = "Low (No direct evidence found)"

        # 2. Build Evidence Links / Queries
        # Provide the raw LogQL / PromQL that users can paste into Grafana Explore
        prom_query = f'sum(rate(aiops_llm_calls_total{{service="{service}", status=~"error|timeout|429"}}[15m])) > 0'
        log_query = f'{{service="{service}"}} |~ "(?i)(llm|openai|anthropic).*?(timeout|429|rate limit|failed)"'
        
        grafana_log_link = f"{self.grafana_base_url}/explore?left=%5B%22now-1h%22,%22now%22,%22{self.loki_datasource_uid}%22,%7B%22expr%22:%22{log_query}%22%7D%5D"

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

**Logs (Loki):**
```logql
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
        "timestamp": "2026-07-14T15:40:00Z",
        "rule": "ai_llm_timeout_error",
        "service": "tf1-ai-triage-engine",
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
