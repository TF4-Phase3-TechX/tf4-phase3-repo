# Mandate 06 evidence index: Bedrock trust and safety

- Status: Complete; implementation, bake-off, and canary verified.
- Team: AIO1 with CDO deployment and CDO-07 audit review
- Deadline: 2026-07-18
- Proposed ADR: [`docs/aio1/mandate-06/ADR-006-bedrock-model-and-safety.md`](../../aio1/mandate-06/ADR-006-bedrock-model-and-safety.md)

## Evidence matrix

| Requirement | Artifact/result | State |
|---|---|---|
| Real model selection | 270-record Haiku/Qwen/Nova bake-off; Nova score 92.02 | Complete |
| Grounded answers | Schema plus exact review-ID/evidence-substring validator | Unit/eval verified |
| Unsupported questions | Nova 100% canonical insufficient on dataset | Eval verified |
| Injection resistance | Direct blocks 100%; stored review quarantine 100% | Unit/eval verified |
| PII/system prompt safety | Pre-provider redaction and output canary/PII filter; zero eval leak | Unit/eval verified |
| Failure bounds | Zero retry, 4.5-second deadline, static fallback, circuit breaker | Unit and deployed failure drill verified |
| Guardrail | Production/canary `wckqh9dms6qa:1`; legacy bake-off `e2svpiawj1v5:3`; Standard hardening evaluation `h2za64pyoh1i:3` | Legacy evaluation and production runtime verified; hardening evaluation passed, production promotion pending |
| IAM | Nova profile/destination-only policy passes AWS Access Analyzer | Policy and Pod Identity role association verified |
| Telemetry | PR #131-compatible token/cost/latency/call/error metrics; content capture disabled | Code and deployed metadata-only series verified |
| Deployment | Dedicated ServiceAccount and hardened canary values | Production canary verified; Standard hardening promotion pending |
| Mentor/rollback/signatures | Canonical checklist | Complete |

## Reproduction

```sh
python -m pytest techx-corp-platform/src/product-reviews/tests -q
python docs/aio1/mandate-06/eval/run_bakeoff.py \
  --guardrail-id e2svpiawj1v5 \
  --guardrail-version 3
```

Do not point this legacy full-model bake-off at production from an unchecked
default AWS identity. Standard Guardrail evaluation and the fail-closed
production account/readback/promotion procedure are documented in
[`STANDARD-GUARDRAIL-HARDENING-RUNBOOK.md`](../../aio1/mandate-06/STANDARD-GUARDRAIL-HARDENING-RUNBOOK.md).

The committed report stores case IDs, outcomes, latency, tokens, cost and error classes only. It excludes prompts, reviews, responses, PII and Guardrail traces.

## Related merged evidence

- PR #131 telemetry/readiness work is reconciled with the Bedrock implementation; metric names remain compatible and the old API-key/mock runbook is superseded.
- The [silent-attack detection review](../../aio01/incidents/2026-07-14-silent-attack-detection-review.md) is retained as negative evidence for observability access and detector coverage.
- Week 1 exported UI artifacts remain on their separate evidence branch and are not duplicated into this Mandate package.

Jira must link GitHub/PR or deployed dashboard evidence. Do not attach workstation paths, credentials, raw model content, PII or Guardrail traces. Follow the canonical [evidence checklist](../../aio1/mandate-06/evidence-checklist.md).
