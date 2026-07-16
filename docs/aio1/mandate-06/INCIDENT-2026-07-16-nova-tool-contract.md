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
- Preserve token/latency usage from an already-received provider response even
  when its response contract fails or it arrives after the application
  deadline, so Prometheus cost telemetry is not falsely zero. The response is
  still rejected after the deadline.
- Emit only finite, non-content diagnostic enums: provider stop reason and
  response-contract stage. No prompt, review, response, tool input, request
  ID, or canary is emitted as a metric label or log field.

## Pre-fix audit snapshot

This is a **failed-canary baseline**, not evidence that the remediation has
passed. The snapshot was read at `2026-07-16 14:45:56 +07:00` before this
change was merged or deployed.

| Item | Recorded value |
|---|---|
| Source remediation PR | `TF4-Phase3-TechX/tf4-phase3-repo#248` |
| Remediation commit | `b46da10212e72b11ad01eaaf986440b0ac2cb74a` |
| Local verification | product-reviews suite: `26 passed` |
| GitHub checks | changed-area detection, YAML parse, Helm render and Docker smoke build: `SUCCESS` |
| Review state at snapshot | `REVIEW_REQUIRED`; no production promotion yet |
| Running Deployment | `product-reviews`, revision `20`, Ready `1/1`, zero pod restarts |
| Running image | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:c16ecbe-product-reviews` |
| Kubernetes identity | ServiceAccount `techx-tf4/product-reviews-bedrock` |
| Temporary canary route | source account `511825856493` Pod Identity association targeting approved account `589077667575` |
| Model and Guardrail | `us.amazon.nova-2-lite-v1:0`, `e2svpiawj1v5:3`, forced tool mode |

The cumulative Prometheus snapshot for the running pre-fix workload was:

- calls: `17` answered, `152` unavailable/`invalid_response`, `18`
  unavailable/`circuit_open`, and `2`
  unavailable/`connectionclosederror`;
- usage: `24,740` prompt tokens and `5,033` completion tokens;
- estimated cost: `$0.0200045` using the configured price counters; and
- rolling 10-minute aggregate p95 latency: approximately `2.0 seconds`.

These are cumulative multi-outcome counters and must not be used as the
post-fix success denominator. The post-fix record must filter by the new pod,
image/revision and controlled test window.

## Promotion and rollback control

- Merging this source PR does not itself change production. A separate image
  build and GitOps promotion are required.
- The new image must first run in a time-bounded canary with the load window,
  owner and image identifier recorded.
- The existing rollback PR changes the Guardrail back to the source account.
  It must not be merged while the Pod Identity association still contains the
  cross-account `targetRoleArn`; CDO must restore the source-only association
  first or explicitly approve continuation of the temporary canary route.
- If the post-fix application-path hard gates fail, the service must continue
  returning the canonical static unavailable response and CDO must execute the
  coordinated identity-plus-GitOps rollback. No real-to-mock fallback is
  permitted.

## Required next canary gates

1. Run a non-routing synthetic preflight using the exact application-shaped
   tool request, rather than a plain-text Bedrock ping.
2. Deploy only after either the cross-account rollback is complete or CDO has
   explicitly approved a short extension of the current temporary canary
   route.
3. Verify `tool_use` plus schema/citation validation on the application path,
   p95 latency under the existing 5-second request budget, and non-zero token
   and estimated-cost Prometheus counters.
4. Keep the failure closed if any response contract stage is unexpected.

## References

- [Amazon Nova tool-use troubleshooting](https://docs.aws.amazon.com/nova/latest/userguide/tools-troubleshooting.html)
- [Amazon Nova tool definition constraints](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-definition.html)
