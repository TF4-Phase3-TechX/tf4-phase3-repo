# Nova 2 Lite tool-contract canary finding — 2026-07-16

> **Current status at 2026-07-16 15:02 +07:00:** FAILED CANARY / ROLLBACK
> PENDING / TEMPORARY CROSS-ACCOUNT ROUTE STILL ACTIVE / PR #248 NOT MERGED OR
> DEPLOYED / ADR-006 REMAINS PROPOSED.

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

## Reproduction and supported root cause

An account-589 diagnostic sent the exact application-shaped request (system
prompt, `guardContent`, sanitized product/review context, forced tool, and
Guardrail `e2svpiawj1v5:3`) while retaining only metadata:

| `maxTokens` | `stopReason` | Output tokens | Result |
|---:|---|---:|---|
| 300 | `malformed_tool_use` | 0 | Fail-closed fallback |
| 1000 | `tool_use` | 328 | Expected one-tool response |

The answer payload can require more than 300 output tokens because it carries
exact evidence quotes. The diagnostic therefore supports output truncation as
the primary failure mechanism. It also identified an independent provider
compatibility risk: the original tool schema sent top-level
`additionalProperties`, while Nova's documented tool schema accepts only
`type`, `properties`, and `required` at the top level.

Both changes were then exercised through the proposed adapter code at PR head
`2352d96` using a synthetic application-shaped request. The direct probe ran
from `arn:aws:iam::589077667575:user/dinhdanhnam-admin` in `us-east-1`, with
model `us.amazon.nova-2-lite-v1:0`, Guardrail `e2svpiawj1v5:3`, forced tool
mode, `maxTokens=512`, the Nova-compatible top-level tool schema, and the real
application schema/citation validator. Only metadata was retained:

| Run / timestamp UTC | Stop / contract stage | Decision / citations | Tokens in/out | Latency | Result |
|---|---|---|---:|---:|---|
| 1 / `2026-07-16T08:02:28Z` | `tool_use` / `tool_input_dict` | answered / 3 | 1193 / 165 | 2375 ms | PASS |
| 2 / `2026-07-16T08:02:29Z` | `tool_use` / `tool_input_dict` | answered / 3 | 1193 / 165 | 1360 ms | PASS |
| 3 / `2026-07-16T08:02:32Z` | `tool_use` / `tool_input_dict` | answered / 3 | 1193 / 165 | 2546 ms | PASS |

The direct result rules out a blanket Guardrail/IAM/model incompatibility and
shows that the proposed bounded contract can complete. It does **not** prove
the EKS image, Pod Identity path, Storefront SLO, production success rate, or
rollback gate; those remain canary evidence requirements.

Amazon Nova's official troubleshooting guidance identifies an insufficient
maximum token count as a common cause of invalid tool output. The official
tool-schema guidance also limits top-level schema fields; the application
continues to use the validator as the final schema/citation/PII enforcement
layer.

## Remediation in this change

- Raise the bounded application `maxTokens` cap from 300 to 512. This is above
  the observed 328-token valid payload but remains bounded; billing is based on
  actual generated tokens, not the configured maximum.
- Send Nova only its supported top-level tool-schema fields (`type`,
  `properties`, `required`). Keep the full strict schema, including
  `additionalProperties: false`, in the deterministic application validator
  and in native structured-output mode.
- Preserve `temperature=0`, one provider call, no SDK retries, 4.5-second
  deadline, forced non-action tool use, pinned numeric Guardrail, and all
  deterministic output validation.
- Preserve token/latency usage from an already-received provider response even
  when its response contract fails or it arrives after the application
  deadline, so Prometheus cost telemetry is not falsely zero. The response is
  still rejected after the deadline.
- Emit only allowlisted, non-content diagnostic dimensions for provider stop
  reason and response-contract stage; unknown values collapse to
  `missing_or_unknown`. No prompt, review, response, tool input, request ID, or
  canary is emitted as a metric label or log field.

## Pre-fix audit snapshot

This is a **failed-canary baseline**, not evidence that the remediation has
passed. The Prometheus query responses were read between
`2026-07-16 14:42:14` and `14:42:16 +07:00`, before this change was merged or
deployed.

| Item | Recorded value |
|---|---|
| Source remediation PR | `TF4-Phase3-TechX/tf4-phase3-repo#248` |
| Remediation commits | `b46da10` cap/telemetry; `e56ab84` late-response usage; `d0ddd90` Nova schema; `2352d96` bounded diagnostic dimensions |
| Local verification | product-reviews suite: `28 passed` |
| GitHub checks | Must be re-run and pass on the final PR head before merge |
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
- The currently failed canary must be rolled back before a new canary is
  opened. CDO first removes the cross-account `targetRoleArn` and verifies the
  association read-back; only then may rollback PR #16 restore the source
  account Guardrail through Argo CD.
- After rollback evidence is recorded, PR #248 may be merged/built and a fresh
  time-bounded cross-account canary may be proposed. That proposal requires a
  named CDO approver, UTC start/expiry, exact target role, Guardrail, image and
  rollback trigger before any new promotion.
- If the post-fix application-path hard gates fail, the service must continue
  returning the canonical static unavailable response and CDO must execute the
  coordinated identity-plus-GitOps rollback. No real-to-mock fallback is
  permitted.

## Required next canary gates

1. Complete the source-only Pod Identity restoration and GitOps rollback #16;
   record association, Argo revision and workload read-back.
2. Merge PR #248 only after required review and final-head CI pass, then record
   the built image identifier.
3. Obtain a fresh named CDO approval and UTC window for the new image canary.
4. Run a non-routing production-shaped preflight from the built image before
   routing the canary; a plain-text Bedrock ping is insufficient.
   canary.
5. Verify `tool_use` plus schema/citation validation on the application path,
   p95 latency under the existing 5-second request budget, and non-zero token
   and estimated-cost Prometheus counters.
6. Keep the failure closed if any response contract stage is unexpected.

## References

- [Amazon Nova tool-use troubleshooting](https://docs.aws.amazon.com/nova/latest/userguide/tools-troubleshooting.html)
- [Amazon Nova tool definition constraints](https://docs.aws.amazon.com/nova/latest/userguide/tool-use-definition.html)
