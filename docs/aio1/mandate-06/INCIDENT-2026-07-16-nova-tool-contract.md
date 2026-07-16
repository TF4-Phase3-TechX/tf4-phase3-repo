# Nova 2 Lite tool-contract canary finding — 2026-07-16

## Scope

This note records the controlled production canary finding for the temporary
cross-account Nova 2 Lite path. It contains no prompt, review, model response,
or secret material.

## What failed

The EKS rollout wiring was correct: the new `product-reviews` pod used the
pinned Guardrail `e2svpiawj1v5:3`, the intended Nova 2 Lite model, and the
forced non-action tool contract. The application path nevertheless returned
safe `unavailable` fallbacks, recorded as `invalid_response`.

The separate JSON trace showing a missing Guardrail at version `1` is not
production evidence: its resource host was a local developer workstation
(`huyvu-Aspire-A315-57G`), not an EKS pod. It must not be used to diagnose the
production canary.

## Reproduction and root cause

An account-589 diagnostic sent the exact application-shaped request (system
prompt, `guardContent`, sanitized product/review context, forced tool, and
Guardrail `e2svpiawj1v5:3`) while retaining only metadata:

| `maxTokens` | `stopReason` | Output tokens | Result |
|---:|---|---:|---|
| 300 | `malformed_tool_use` | 0 | Fail-closed fallback |
| 1000 | `tool_use` | 328 | Expected one-tool response |

The answer payload can require more than 300 output tokens because it carries
exact evidence quotes. Therefore the 300-token cap can truncate the forced
tool payload before it is valid. This is not a missing Guardrail, IAM, model
access, or output-mode routing failure.

Amazon Nova's official troubleshooting guidance identifies an insufficient
maximum token count as a common cause of invalid tool output. The official
tool-schema guidance also limits top-level schema fields; the application
continues to use the validator as the final schema/citation/PII enforcement
layer.

## Remediation in this change

- Raise the bounded application `maxTokens` cap from 300 to 512. This is above
  the observed 328-token valid payload but remains bounded; billing is based on
  actual generated tokens, not the configured maximum.
- Preserve `temperature=0`, one provider call, no SDK retries, 4.5-second
  deadline, forced non-action tool use, pinned numeric Guardrail, and all
  deterministic output validation.
- Preserve token/latency usage from a provider response even when its response
  contract fails, so Prometheus cost telemetry is not falsely zero.
- Emit only finite, non-content diagnostic enums: provider stop reason and
  response-contract stage. No prompt, review, response, tool input, request
  ID, or canary is emitted as a metric label or log field.

## Required next canary gates

1. Run a non-routing synthetic preflight using the exact application-shaped
   tool request, rather than a plain-text Bedrock ping.
2. Deploy only after the cross-account rollback is complete and a fresh
   approval is recorded.
3. Verify `tool_use` plus schema/citation validation on the application path,
   p95 latency under the existing 5-second request budget, and non-zero token
   and estimated-cost Prometheus counters.
4. Keep the failure closed if any response contract stage is unexpected.

## References

- [Amazon Nova tool-use troubleshooting](https://docs.aws.amazon.com/nova/latest/userguide/tools-troubleshooting.html)
- [Amazon Nova tool definition constraints](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-definition.html)
