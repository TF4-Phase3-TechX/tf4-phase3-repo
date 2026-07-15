# Bedrock readiness and cutover guide

This document is the consolidated successor to the OpenAI-compatible/mock readiness plan introduced by PR #131. The canonical architecture and current evidence are in [`docs/aio1/mandate-06`](../aio1/mandate-06/README.md).

## Current decision

- Provider: Amazon Bedrock Runtime `Converse`.
- Evaluated winner: `us.amazon.nova-2-lite-v1:0`.
- Output contract: forced non-action tool plus application schema/exact-review-quote validation.
- Guardrail: `e2svpiawj1v5`, pinned version `3` for the evaluated canary configuration.
- Production authentication: EKS Pod Identity using ServiceAccount `product-reviews-bedrock`; no provider API key.
- Runtime failure behavior: canonical static unavailable response. The service never silently switches model or falls back to the mock.
- Operational rollback: CDO reverts the reviewed image/configuration through GitOps/Helm. `flagd` is not changed.

## Readiness gates

### Identity and configuration

- [ ] CDO confirms `eks-pod-identity-agent` is healthy.
- [ ] Role `tf4-product-reviews-bedrock` uses the reviewed Nova-only runtime policy.
- [ ] Namespace `techx-tf4` and ServiceAccount `product-reviews-bedrock` are associated with the role.
- [ ] Canary values pin Nova, Guardrail version 3, tool output mode and the current price snapshot.
- [ ] The leak-detection marker is provisioned outside Git and absent from logs.

### Reliability and safety

- [x] SDK online retries are zero.
- [x] Bedrock deadline is 4.5 seconds inside the five-second application budget.
- [x] Circuit breaker opens after five consecutive provider failures in 30 seconds and cools down for 60 seconds.
- [x] Existing `llmRateLimitError` and `llmInaccurateResponse` incident flags remain observable; they now produce safe unavailable/insufficient outcomes and never switch to mock.
- [x] Timeout, malformed output and provider error return a static safe response.
- [x] Direct action/system-prompt attacks are blocked before provider invocation.
- [x] Review instructions are quarantined and PII is redacted before provider invocation.
- [x] Displayed answers require an existing review ID and exact evidence substring.
- [ ] CDO/mentor repeats the adversarial cases through the deployed storefront path.

### Evaluation and observability

- [x] Three models ran 30 cases × 3 repetitions; the report contains 270 metadata-only records.
- [x] Nova passed supported ≥90%, unsupported 100%, injection quarantine 100% and zero PII/canary leakage.
- [x] Metric contract from PR #131 is retained: `app_llm_prompt_tokens_total`, `app_llm_completion_tokens_total`, `app_llm_estimated_cost_usd_total`, `app_llm_latency_seconds`, `app_llm_errors_total`, and `app_llm_calls_total`.
- [x] `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` is set.
- [ ] Deployed Prometheus series names and Grafana queries are verified.
- [ ] Storefront SLO before/after and canary logs/traces are attached.

## Controlled cutover

```text
reviewed image + values + Pod Identity
  -> CDO internal/isolated canary
  -> warm output schema/tool path
  -> mentor adversarial tests
  -> compare latency, errors, cost and Storefront SLO
  -> approve wider rollout | revert previous image/config
```

Abort the canary on any leakage, hard-gate regression, missing Guardrail, content-bearing telemetry, application request over five seconds, or Storefront SLO regression.

## Rollback

1. Record current and previous image digests and GitOps revisions.
2. CDO reverts the canary image/configuration to the previous reviewed revision.
3. Wait for rollout readiness and verify the original product/review page.
4. Confirm latency/error recovery and record UTC start/end plus recovery time.
5. Attach sanitized telemetry and the GitHub revision to the evidence package.

Rollback does not select the deterministic mock as a hidden runtime fallback. If a future mock configuration is intentionally deployed, it needs an explicit reviewed rollout and must be visible to operators.
