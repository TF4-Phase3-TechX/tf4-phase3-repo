# Mandate 06 submission package

Status: **implementation, real-model bake-off and production canary gates complete; ADR acceptance awaits named closure-PR approvals**.

## Decision and implementation evidence

- [ADR-006](ADR-006-bedrock-model-and-safety.md): Nova 2 Lite selection, safety boundary, alternatives and acceptance record.
- [Model-selection scorecard](model-selection-scorecard.md): frozen gates, ranking and 2026-07-14 result.
- [Dataset](eval/dataset-v1.jsonl), [runner](eval/run_bakeoff.py), [report](eval/bakeoff-report.json) and [report schema](eval/bakeoff-report.schema.json).
- [Metadata-only human review](eval/human-review-2026-07-17.md): disposition of every deterministic failure and unstable case without re-grading unretained content.
- [Guardrail configuration](guardrail/create-guardrail.json) and [version evidence](guardrail/evaluation-guardrail-evidence.json).
- [Nova runtime IAM policy](iam/runtime-policy-nova.json), validated with AWS Access Analyzer.
- [CDO production handoff runbook](CDO-HANDOFF.md): account, Guardrail, IAM, Pod Identity, deployment, verification and rollback contract.
- [Runtime evidence checklist](evidence-checklist.md).
- [2026-07-17 runtime acceptance record](runtime-acceptance-2026-07-17.md): exact release, application/safety paths, provider failures, Prometheus/SLO and actual rollback evidence.

## Verified result

Nova was the sole eligible model: supported quality 96.67%, unsupported 100%, stored injection quarantine 100%, direct attacks 100%, PII/canary leakage zero, p95 1.328 seconds, estimated $0.4541 per 1,000 successful evaluation requests. The report contains exactly 270 metadata-only records.

PR #131 telemetry names and the existing `llmRateLimitError`/`llmInaccurateResponse` incident flags are retained. The flags exercise static safe degradation/output blocking; they do not route production traffic to a mock.

## Runtime acceptance result

The 2026-07-17 canary passed exact-image preflight, real gRPC application-path
tests, prompt/action/PII safety cases, provider timeout/error/circuit behavior,
Prometheus token/cost visibility, a 2026-07-17 pricing re-snapshot, Storefront
and Bedrock latency/error gates, and the real GitOps rollback drill. Temporary probe Jobs were removed and the
`load-generator` replica used during quota recovery was restored.

Only named closure-PR approvals/signatures remain before the accepted ADR is
effective. The custom LLM latency histogram bucket granularity is tracked as a
non-blocking observability follow-up; acceptance uses the finer span-metrics
histogram and does not hide any error or timeout.

The compatibility runbook from PR #131 is consolidated in [`docs/aio01/real_llm_readiness_checklist.md`](../../aio01/real_llm_readiness_checklist.md). The silent-attack review is linked as negative observability evidence; large Week 1 UI exports are intentionally not duplicated.
