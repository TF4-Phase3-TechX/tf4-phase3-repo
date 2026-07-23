# MANDATE-06 Mentor Brief: AI Trust, Safety and Grounded Product Review

> Tài liệu tổng hợp để mentor và các team review một lần: mandate yêu cầu gì,
> team đã làm gì, kết quả ra sao, evidence nằm ở đâu, task thuộc về ai và phần
> nào không được overclaim.

## 1. Executive Summary

| Nội dung | Kết luận hiện tại |
|---|---|
| Mandate | AI Trust, Safety and Grounded Product Review |
| Canonical Jira | [TF4AIO-70](https://aio1-xbrain.atlassian.net/browse/TF4AIO-70) |
| Application | `product-reviews` |
| Model | Amazon Nova 2 Lite through Bedrock `Converse` |
| Runtime identity | EKS Pod Identity; no long-lived AWS key in the workload |
| Original closure | Done |
| Feedback hardening | Code and evaluation complete |
| Decision record | [ADR-006](../../aio1/mandate-06/ADR-006-bedrock-model-and-safety.md) |
| Verdict | Ready for mentor re-review within the evidence boundary below |

The delivered application path combines grounded product-review evidence,
deterministic citation validation, PII/canary checks, local fast-path safety
checks, Bedrock Guardrail semantic enforcement, sanitized telemetry, controlled
canary and rollback evidence.

The Standard-tier Guardrail candidate has passing evaluation evidence but is a
separate CDO-controlled production promotion. The original Mandate 6 closure
must not be re-described as proof that this newer candidate is already the
active production version.

## 2. What Mandate 6 Required

| Requirement | Operational meaning |
|---|---|
| Real model path | The application must call an evaluated Bedrock model, not silently fall back to a mock |
| Grounded answer | Supported claims must come from product-review evidence and preserve exact citations |
| Safe refusal | Missing/insufficient evidence, provider failure and unsafe input must return canonical safe responses |
| Prompt-injection resistance | Direct and stored attacks must not override the system contract |
| PII/system-prompt protection | Sensitive input is redacted and output is checked before returning |
| Production identity | Workload uses Pod Identity and least-privilege IAM |
| Observability | Calls, errors, latency, tokens and estimated cost are visible without logging raw sensitive content |
| Reproducible evaluation | Dataset, runner, schema, report and human disposition are versioned |
| Controlled runtime proof | Canary, SLO gates and actual rollback are recorded |
| Signed decision | Model/safety trade-offs and activation boundary are accepted by named humans |

## 3. What the Team Implemented

### 3.1 Bedrock and grounding path

- Pinned Nova 2 Lite model and numeric Guardrail configuration.
- Bedrock `Converse` adapter with bounded deadline, retry policy and circuit
  breaker.
- No silent real-to-mock fallback on provider failure.
- Supported answers must pass deterministic schema and exact-review-quote
  validation.
- Unsupported or missing evidence returns a fixed insufficient-information
  response.

Key code:

- [`bedrock_adapter.py`](../../../techx-corp-platform/src/product-reviews/bedrock_adapter.py)
- [`product_reviews_server.py`](../../../techx-corp-platform/src/product-reviews/product_reviews_server.py)

### 3.2 Defense-in-depth safety

- Local deterministic filter blocks obvious low-cost cases before a provider
  call.
- Stored review content is quarantined when it contains instruction-like
  attacks.
- PII is redacted before the provider call.
- Bedrock Guardrail handles broader semantic unsafe content and attacks.
- Output passes PII, canary, schema and citation validation.
- Provider, schema or safety failures produce a static safe response.

Key code:

- [`safety.py`](../../../techx-corp-platform/src/product-reviews/safety.py)
- [`test_safety.py`](../../../techx-corp-platform/src/product-reviews/tests/test_safety.py)
- [`test_bedrock_adapter.py`](../../../techx-corp-platform/src/product-reviews/tests/test_bedrock_adapter.py)

The local regex/heuristic layer is an optimization and defense-in-depth layer,
not the semantic security boundary. The team does not claim that it blocks
every language, spacing trick or obfuscation by itself.

### 3.3 Runtime and operational controls

- EKS Pod Identity instead of embedded AWS credentials.
- Sanitized metrics for calls, outcomes, latency, token usage and estimated
  cost.
- Controlled canary with application-path checks.
- Real GitOps rollback and post-rollback verification.
- CDO handoff documents exact account, IAM, Guardrail, deployment and rollback
  responsibilities.

## 4. Evaluation and Runtime Results

### 4.1 Original model-selection result

| Metric | Nova result |
|---|---:|
| Supported-answer quality | `96.67%` |
| Unsupported/refusal behavior | `100%` |
| Stored injection quarantine | `100%` |
| Direct attack handling | `100%` |
| PII/canary leakage | `0` |
| Evaluation p95 | `1.328s` |
| Estimated cost / 1,000 successful eval requests | `$0.4541` |

The report contains 270 metadata-only records across three models and repeated
runs. Nova was selected because it was the only candidate to pass every hard
gate, not because of brand preference.

### 4.2 Feedback-driven Guardrail hardening

- Deterministic 100-case `ApplyGuardrail` policy suite.
- Ten-case `Converse` application-path suite.
- Multilingual, obfuscated, benign-control, prompt-extraction, action and PII
  cases.
- Frozen schemas and metadata-only reports.
- Standard v3 evaluation evidence records Guardrail configuration, dataset and
  report hashes.

### 4.3 Runtime acceptance

The accepted canary covered:

- exact image/config preflight;
- real gRPC application path;
- grounded, refusal, injection, PII and provider-failure cases;
- Prometheus call/error/token/cost visibility;
- Storefront and Bedrock latency/error gates;
- actual GitOps rollback and recovery verification.

## 5. Architecture Decision and Trade-offs

### Why not use only regex?

Rules are cheap and deterministic but have unbounded bypass variants across
languages and obfuscations. They remain a fast-path filter only. Semantic
Guardrail enforcement plus deterministic post-response validation provides the
actual defense-in-depth boundary.

### Why not call `ApplyGuardrail` before every `Converse` request?

That would duplicate Guardrail enforcement on the actual inference path and add
latency/cost. The selected design evaluates the real `Converse` path with the
Guardrail attached, then validates the response deterministically. Separate
`ApplyGuardrail` is used for policy calibration/evaluation rather than being
blindly added to every request.

### Why no mock fallback?

A mock is not the evaluated production model and would hide provider outages or
change behavior silently. Provider failure returns an explicit static safe
response; operational recovery uses reviewed configuration/image rollback.

## 6. Task Ownership

| Jira | Work | Owner | Evidence/output |
|---|---|---|---|
| `TF4AIO-64` | Reproducible real-LLM trust/safety evaluation | Nguyễn Trần Huy Vũ | Dataset, runner, report and hard-gate evaluation |
| `TF4AIO-65` | Mentor scenarios and signed evidence | Trần Đình Thông | Acceptance record, evidence reconciliation and signatures |
| `TF4AIO-66` | Integrate release gates and controlled deployment | Đinh Danh Nam | Canonical integration, CDO coordination and go/no-go boundary |
| `TF4AIO-67` | Prometheus/OpenSearch/Jaeger runtime evidence | Cái Xuân Hòa | Sanitized observability evidence and signal verification |
| `TF4AIO-68` | Adversarial cases and provider-failure signals | Huỳnh Xuân Hậu | Attack cases, failure-signal mapping and limitation review |
| `TF4AIO-69` | Controlled rollout, SLO, rollback and recovery | Thành Tâm | Canary/rollback acceptance and recovery evidence |
| `TF4AIO-70` | Canonical Mandate 6 closure | Đinh Danh Nam | Official Jira submission and closure |
| `TF4AIO-23/24/26/27/28/29` | Bedrock adapter, safe failure, injection/PII and reliability work | Tất Văn | Implementation contributions consolidated into the canonical path |

## 7. Mentor Evidence Map

| Evidence | Purpose |
|---|---|
| [Submission README](../../aio1/mandate-06/README.md) | Canonical package overview |
| [ADR-006](../../aio1/mandate-06/ADR-006-bedrock-model-and-safety.md) | Model/safety decision, alternatives and signatures |
| [Model scorecard](../../aio1/mandate-06/model-selection-scorecard.md) | Hard gates and candidate comparison |
| [Dataset](../../aio1/mandate-06/eval/dataset-v1.jsonl) | Versioned evaluation inputs |
| [Runner](../../aio1/mandate-06/eval/run_bakeoff.py) | Reproduction entry point |
| [Report](../../aio1/mandate-06/eval/bakeoff-report.json) | Machine-readable model result |
| [Human review](../../aio1/mandate-06/eval/human-review-2026-07-17.md) | Disposition of deterministic failures/unstable cases |
| [Runtime acceptance](../../aio1/mandate-06/runtime-acceptance-2026-07-17.md) | Application, SLO, canary and rollback evidence |
| [Evidence checklist](../../aio1/mandate-06/evidence-checklist.md) | Claim-to-artifact index |
| [Hardening corpus/runners](../../aio1/mandate-06/eval/guardrail_hardening/README.md) | Multilingual/adversarial evaluation |
| [Standard v3 evidence](../../aio1/mandate-06/guardrail/evaluation-standard-v3-evidence.json) | Config/dataset/report hashes and measured result |
| [CDO handoff](../../aio1/mandate-06/CDO-HANDOFF.md) | Production identity/deploy/rollback contract |
| [PR #280](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/280) | Original closure review |
| [PR #414](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/414) | Guardrail hardening review |
| [PR #458](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/458) | Explicit full-name signatures |
| [GitOps #22](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/22) | Accepted canary |
| [GitOps #16](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/16) | Actual rollback |

## 8. Claim Boundary

The following claims are supported:

- original Mandate 6 closure is complete;
- real Bedrock application-path and runtime evidence exist;
- Guardrail hardening evaluation passed its committed suites;
- named ADR signatures and rollback evidence exist.

The following claim is not supported without a fresh production readback:

- the newer Standard-tier Guardrail candidate is already the active production
  version.

## 9. Suggested Mentor Submission

```text
MANDATE-06 is ready for mentor re-review. The package contains the real Bedrock
application path, grounded-answer contract, defense-in-depth safety controls,
reproducible model/Guardrail evaluations, sanitized runtime evidence, named ADR
signatures, controlled canary and actual rollback. The original closure is Done.
The newer Standard-tier candidate is reported as evaluated and awaiting separate
CDO-controlled production promotion, not as already active.
```

## 10. Mentor Sign-Off

**Mentor name:** ______________________________________

**Decision:** `ACCEPT` / `RE-RUN REQUIRED`

**Date/time:** ______________________________________

**Comments:**

```text

```
