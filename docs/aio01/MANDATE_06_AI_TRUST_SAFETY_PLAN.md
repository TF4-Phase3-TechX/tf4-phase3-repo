# AIO1 Mandate 06 implementation plan

- Effective date: 2026-07-14
- Deadline: 2026-07-18
- Status: implementation complete locally; real-model/CDO evidence pending
- Canonical decision: [`docs/aio1/mandate-06/ADR-006-bedrock-model-and-safety.md`](../aio1/mandate-06/ADR-006-bedrock-model-and-safety.md)
- Evidence checklist: [`docs/aio1/mandate-06/evidence-checklist.md`](../aio1/mandate-06/evidence-checklist.md)

## Outcome and dependency chain

Demonstrate on the real product-review application path that a Bedrock model is grounded in exact review evidence, resists direct and stored prompt injection, does not leak PII/system markers, degrades to a static safe response, stays inside latency/cost/SLO limits, and can be re-evaluated from committed data/scripts.

```text
pinned Bedrock + Guardrail + Pod Identity
  -> non-bypassable application filters and validators
  -> unit/integration fault tests
  -> 30-case × 3-run Haiku/Qwen/Nova bake-off through AWS SSO
  -> select winner and update Proposed ADR
  -> CDO canary + telemetry/SLO + rollback drill
  -> mentor adversarial application-path test
  -> named signatures and ADR Accepted
```

No long-lived provider key is used. No model can query the DB or execute shopping tools. Provider failure never silently falls back to a mock. The ADR remains `Proposed` until the real evidence chain is complete.

## Ownership

| Owner | Deliverable |
|---|---|
| Nam | Architecture, integration review, final model decision and ADR |
| Văn | Bedrock adapter, static fallback, 4.5-second deadline and circuit breaker |
| Vũ | Versioned 30-case dataset, runner, scorecard and real bake-off |
| Hậu | Stored/direct injection, PII/canary red team and Guardrail |
| Hòa | Token, latency, price snapshot, cost and sanitized observability |
| Tâm | Canary, provider-failure drill and GitOps rollback with CDO |
| Thông | Pod Identity/IAM coordination, GitHub evidence links and sign-off tracking |

## Schedule

- 14/07: proposed catalogue/ADR, CDO access request, Guardrail design.
- 15/07: provider adapter, application guards, sanitized telemetry and unit tests.
- 16/07: real three-model bake-off; select winner only if gates pass.
- 17/07: CDO internal canary, schema warm-up, SLO comparison and rollback drill.
- 18/07: mentor adversarial test, named signatures, ADR acceptance and mandate close.

Stop the rollout on any leakage, hard-gate failure, missing pinned Guardrail, content-bearing telemetry, AI path over five seconds, or Storefront SLO regression.
