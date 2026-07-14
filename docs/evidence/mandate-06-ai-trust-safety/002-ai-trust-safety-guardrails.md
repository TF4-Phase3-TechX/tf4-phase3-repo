# Mandate 06 evidence index: Bedrock trust and safety

- Status: local implementation verified; real runtime evidence pending
- Team: AIO1 with CDO deployment and CDO-07 audit review
- Deadline: 2026-07-18
- Proposed ADR: [`docs/aio1/mandate-06/ADR-006-bedrock-model-and-safety.md`](../../../aio1/mandate-06/ADR-006-bedrock-model-and-safety.md)

## Committed evidence

| Requirement | Artifact | State |
|---|---|---|
| Non-bypassable grounded path | `src/product-reviews/{ai_assistant,bedrock_adapter,safety}.py` | Implemented |
| Failure bounds | zero SDK retries, 4.5-second deadline, 5/30s breaker, 60s cooldown, static fallback | Unit tested |
| Injection/PII/citation controls | deterministic filters and exact-quote validator | Unit tested |
| Reproducible eval | `docs/aio1/mandate-06/eval/dataset-v1.jsonl` + `run_bakeoff.py` | 30 cases committed; SSO run pending |
| Model decision | catalogue and frozen scorecard | ADR remains Proposed |
| Guardrail/IAM | create request and least-privilege policy templates | CDO version/association pending |
| Deployment | dedicated ServiceAccount, Bedrock env, content capture disabled, hardened canary values | CDO canary pending |
| Runtime proof | bake-off, telemetry/SLO, rollback, mentor record | Pending |

## Verification

```sh
python -m pytest techx-corp-platform/src/product-reviews/tests -q
python docs/aio1/mandate-06/eval/run_bakeoff.py \
  --guardrail-id "$BEDROCK_GUARDRAIL_ID" \
  --guardrail-version "$BEDROCK_GUARDRAIL_VERSION"
```

The second command requires temporary AWS SSO credentials and CDO-granted access to all three shortlisted models. It writes a sanitized report containing case IDs, outcomes, latency, tokens, cost and error classes—never prompt, review, response or PII content.

## Evidence hygiene and completion

Jira must link a GitHub commit/PR or deployed dashboard evidence. It must not contain a workstation path, credentials, raw model content, PII, or Guardrail trace. Follow the canonical [runtime evidence checklist](../../../aio1/mandate-06/evidence-checklist.md) for the canary, SLO comparison, rollback drill, mentor tests and signatures. Unit/mock evidence alone cannot move the ADR to `Accepted`.
