# TF4AIO-45 Validation Evidence

**Task**: [W3][AIOPS] Validate LLM timeout/error signal
**Assignee**: huynh xuan hau

## Validation Context
This document proves that the AIOps detector can recognize AI-path timeout/errors using simulated LLM failure signals as required by TF4AIO-45.

## Test Implementation
A validation script (`tests/test_validate_tf4aio45.py`) was implemented as a pytest case to mock both Prometheus and OpenSearch responses, simulating a high-severity incident where both metric thresholds are exceeded and error logs are present. This ensures CI enforcement.

## Validation Output
When executing the validation test, the detector successfully correlates the signals and asserts a `high` severity.

**Command:**
```bash
python -m pytest techx-corp-platform/src/aiops-detector/tests/test_validate_tf4aio45.py -s
```

**Commit SHA:**
`800360354ad04d55e8f158e001fb95fa068a7439` (Note: Pending commit will update this hash on PR).

**Output:**
```json
{
  "timestamp": "2026-07-17T01:49:32.417004+00:00",
  "rule": "ai_llm_timeout_error",
  "service": "product-reviews",
  "environment": "production",
  "tenant_id": "default",
  "severity": "high",
  "evidence": {
    "metric_query": "sum(rate(app_llm_errors_total[15m])) > 0",
    "log_query": "resource.service.name:\"product-reviews\" AND resource.k8s.namespace.name:\"production\" AND (message:*timeout* OR message:*rate_limited* OR message:*429*) AND (message:*llm* OR message:*openai* OR message:*bedrock*)",
    "log_index": "otel-logs-*",
    "metrics_available": true,
    "logs_available": true,
    "metrics_found": 1,
    "logs_found": 1,
    "metric_details": [
      {
        "metric": {
          "__name__": "app_llm_errors_total"
        },
        "value": [
          1600000000,
          "1.5"
        ]
      }
    ],
    "log_details": [
      {
        "_source": {
          "message": "LLM connection timeout after 5000ms"
        }
      }
    ]
  }
}
```

## Conclusion
The AIOps detector successfully identifies the signal and explicit dependency on AIE telemetry (`app_llm_errors_total` and log messages) is verified.
