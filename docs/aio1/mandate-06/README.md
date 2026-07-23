# Mandate 06 submission package

Status: **original production closure is complete; Standard-tier hardening has passing evaluation evidence and awaits CDO production promotion/signatures**.

For a single mentor-facing overview matching the cross-team submission format,
see [MANDATE-06 Mentor Brief](../../evidence/mandate-06-ai-trust-safety/MANDATE-06-Mentor-Brief-AI-Trust-Safety.md).

## Decision and implementation evidence

- [ADR-006](ADR-006-bedrock-model-and-safety.md): Nova 2 Lite selection, safety boundary, alternatives and acceptance record.
- [Model-selection scorecard](model-selection-scorecard.md): frozen gates, ranking and 2026-07-14 result.
- [Dataset](eval/dataset-v1.jsonl), [runner](eval/run_bakeoff.py), [report](eval/bakeoff-report.json) and [report schema](eval/bakeoff-report.schema.json).
- [Metadata-only human review](eval/human-review-2026-07-17.md): disposition of every deterministic failure and unstable case without re-grading unretained content.
- [Guardrail configuration](guardrail/create-guardrail.json) and [version evidence](guardrail/evaluation-guardrail-evidence.json).
- [Nova runtime IAM policy](iam/runtime-policy-nova.json), validated with AWS Access Analyzer.
- [CDO production handoff runbook](CDO-HANDOFF.md): account, Guardrail, IAM, Pod Identity, deployment, verification and rollback contract.
- [Standard-tier Guardrail hardening runbook](STANDARD-GUARDRAIL-HARDENING-RUNBOOK.md): isolated Standard/cross-Region candidate, two-version IAM transition, GitOps promotion, sanitized evidence and rollback contract.
- [Guardrail hardening corpus and runners](eval/guardrail_hardening/): deterministic 100-case `ApplyGuardrail` suite plus 10-case production-path Converse suite, with frozen schemas and metadata-only reports.
- [Standard v3 evaluation evidence](guardrail/evaluation-standard-v3-evidence.json): immutable Guardrail readback, config/dataset/report hashes, failed calibration history and passing measured result.
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

The original closure approvals remain the record for version 1; the hardening
promotion requires a new explicit CDO owner, AIO witness, security reviewer and
rollback owner. The custom LLM latency histogram bucket granularity remains a
non-blocking observability follow-up; acceptance uses the finer span-metrics
histogram and does not hide any error or timeout.

## Guardrail hardening evaluation

The evaluation account now has immutable Standard Guardrail
`h2za64pyoh1i:3` with `us.guardrail.v1:0` and one measured semantic
prompt-boundary topic. The final fixed corpus produced:

- 15/15 curated attacks blocked;
- 58/60 generated variants blocked (96.67%);
- 0/25 benign controls blocked in the final immutable report;
- zero provider/protocol errors and 100/100 guarded-character coverage;
- 5/5 EN/VI/FR/ES/ID regex-bypass attacks blocked on the real
  `GroundedAssistant` → `BedrockAdapter.converse` path;
- 5/5 benign Converse cases safe, zero canary leakage, exact payload match,
  and p95/max end-to-end latency 1.837 seconds.

This is scoped evidence for the committed corpus/config/version, not a claim
of universal prompt-injection resistance. Production remains on
`wckqh9dms6qa:1` until CDO applies the reviewed DRAFT, publishes the next
numeric version, completes IAM/GitOps promotion, reruns regression probes and
records all four named signatures.

The compatibility runbook from PR #131 is consolidated in [`docs/aio01/real_llm_readiness_checklist.md`](../../aio01/real_llm_readiness_checklist.md). The silent-attack review is linked as negative observability evidence; large Week 1 UI exports are intentionally not duplicated.
