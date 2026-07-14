# Mandate 06 submission package

Status: **implementation and real-model bake-off complete; ADR remains Proposed pending cluster evidence and signatures**.

## Decision and implementation evidence

- [ADR-006](ADR-006-bedrock-model-and-safety.md): Nova 2 Lite selection, safety boundary, alternatives and acceptance record.
- [Model-selection scorecard](model-selection-scorecard.md): frozen gates, ranking and 2026-07-14 result.
- [Dataset](eval/dataset-v1.jsonl), [runner](eval/run_bakeoff.py), [report](eval/bakeoff-report.json) and [report schema](eval/bakeoff-report.schema.json).
- [Guardrail configuration](guardrail/create-guardrail.json) and [version evidence](guardrail/evaluation-guardrail-evidence.json).
- [Nova runtime IAM policy](iam/runtime-policy-nova.json), validated with AWS Access Analyzer.
- [Runtime evidence checklist](evidence-checklist.md).

## Verified result

Nova was the sole eligible model: supported quality 96.67%, unsupported 100%, stored injection quarantine 100%, direct attacks 100%, PII/canary leakage zero, p95 1.328 seconds, estimated $0.4541 per 1,000 successful evaluation requests. The report contains exactly 270 metadata-only records.

PR #131 telemetry names and the existing `llmRateLimitError`/`llmInaccurateResponse` incident flags are retained. The flags exercise static safe degradation/output blocking; they do not route production traffic to a mock.

## Still required before acceptance

1. CDO Pod Identity role/association and canary deployment.
2. Deployed metric/log/trace inspection and Storefront SLO comparison.
3. Current Bedrock/Guardrail price snapshot.
4. Provider failure and GitOps rollback drill.
5. Mentor adversarial application-path record.
6. Named ADR signatures.

The compatibility runbook from PR #131 is consolidated in [`docs/aio01/real_llm_readiness_checklist.md`](../../aio01/real_llm_readiness_checklist.md). The silent-attack review is linked as negative observability evidence; large Week 1 UI exports are intentionally not duplicated.
