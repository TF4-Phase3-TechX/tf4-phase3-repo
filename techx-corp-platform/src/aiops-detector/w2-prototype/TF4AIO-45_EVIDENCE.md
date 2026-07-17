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
`fd5cf2073c317102b6bc6957b23b3cd2b6a0649f`

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

## Dependencies Resolution
The missing `requests` dependency blocker has been fully resolved:
- Added `requests==2.32.3` to `techx-corp-platform/src/product-reviews/requirements.txt`.
- Created dedicated dependency tracker `techx-corp-platform/src/aiops-detector/requirements.txt` listing `requests` and `pytest` for local and CI environments.

## Deployment Recommendations & Risk Mitigation
To address non-blocking risks identified during PR review:
1. **Karpenter Security Group Tags**: Comments have been added to `deploy/karpenter/ec2nodeclass.yaml` highlighting that `terraform apply` must finish successfully before ArgoCD synchronization is triggered to prevent scaling issues.
2. **Bedrock Canary Secret**: Warnings and placeholder guidelines have been added to `deploy/values-aio-llm.yaml`. Detailed instructions and a secret template for non-production environments are documented in [docs/aio01/deployment_guide_TF4AIO-45.md](file:///d:/AWS/Xbrain/Phase3/docs/aio01/deployment_guide_TF4AIO-45.md).

## Conclusion
The AIOps detector successfully identifies the signal, explicit dependency on AIE telemetry (`app_llm_errors_total` and log messages) is verified, and all PR review issues (blockers and improvements) have been mitigated.
