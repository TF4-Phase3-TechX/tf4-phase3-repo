# AIO1 proof-of-knowledge and defense index

- Accountable team: AIO1
- Audited base: `main@fd1c7f3445812d6058e3b97c4ecc903bb70dfe6e`
- Evidence rule: code or synthetic replay is not presented as live production
  proof; open PRs are labelled as candidates until merged.

## Defense map

| Mandate | What the owner must be able to explain | Canonical evidence and replay | Current boundary |
|---|---|---|---|
| 06 — trust and safety | Why Nova was selected, how Guardrail and application validation compose, why exact canaries are not a general PII detector, and how rollback works | [`mandate-06/README.md`](mandate-06/README.md), [`ADR-006`](mandate-06/ADR-006-bedrock-model-and-safety.md), `python docs/aio1/mandate-06/eval/run_bakeoff.py` | Bounded production acceptance exists; historical observations are not claimed to be exactly re-measurable later |
| 07a/07b/15 — detection | Which signals fire decisions, why IsolationForest is capped confidence/audit evidence, how masking and burn-rate escalation work, and how false positives are bounded | [`MANDATE-07B-EVIDENCE-INDEX.md`](mandate-07b/MANDATE-07B-EVIDENCE-INDEX.md), [`MANDATE-15-EVIDENCE-INDEX.md`](mandate-15/MANDATE-15-EVIDENCE-INDEX.md), [`ADR-015`](mandate-15/ADR-015-aiops-detection.md) | Availability was observed live; anomaly/masking plus high-burn live drill remains an operator-window gate |
| 14 — AI evaluation | Difference between lexical overlap and semantic entailment, scorer calibration, human agreement, negative controls, dataset revision/hash, and truncation policy | [`MANDATE-14-EVIDENCE-INDEX.md`](mandate-14/MANDATE-14-EVIDENCE-INDEX.md), candidate [PR #781](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/781) | Semantic calibration candidate is CI-green but remains unmerged until named reviewer approval |
| 22 — closed loop | Why remediation is GitOps-native, the policy gates before mutation, idempotency/durable saga behavior, compensation, quarantine and ambiguous-outcome handling | [`FINAL-EVIDENCE-2026-07-25.md`](mandate-22/FINAL-EVIDENCE-2026-07-25.md), [`ADR-022`](mandate-22/ADR-022-safe-closed-loop-mitigation.md) | Kind/Argo sandbox evidence is not production GitHub App/CDO acceptance |
| 23 — GenAI cache/memory | Cache key and invalidation, consent/identity binding, single-flight behavior, deletion, and why Valkey cart is isolated from AI state | [`mandate-23/README.md`](mandate-23/README.md), [`ADR-023`](mandate-23/ADR-023-genai-caching-and-memory.md), `bash tests/eval_mandate23/repro.sh` | Deterministic and runtime evidence is bounded to the documented identities and flows |
| 24 — observability | Black-box span/metric contract, redaction, runtime cost/latency overhead method, why matched alternating arms matter, and rollback | [`MANDATE-24-EVIDENCE-INDEX.md`](mandate-24/MANDATE-24-EVIDENCE-INDEX.md), candidate [PR #777](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/777) | Matched production packet is in an open PR and is not canonical on `main` yet |
| 25 — resilience | Retry budget, breaker state machine, provider suppression, safe response semantics, fault-control TTL and cleanup | [`runtime production report`](mandate-25/evidence/runtime-production-20260729/RUNTIME-EVIDENCE-REPORT.md), [`ADR-025`](mandate-25/ADR-25-ai-resilience-fallback.md) | Production drill passed; do not rerun without an approved bounded operator window |
| 26 — RCA | Evidence graph construction, cross-service ordering, candidate ranking, Root@1/MRR/noise metrics, and externally supplied replay | [`MANDATE-26-EVIDENCE-INDEX.md`](mandate-26/MANDATE-26-EVIDENCE-INDEX.md), merged [PR #716](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/716) | Evidence level 3; mentor/Jira acceptance is distinct from merge |
| 27 — model-quality drift | Capability-bound baseline, semantic score source, statistical thresholds, elapsed persistence, version binding, traffic weighting and rolling-baseline limitation | Merged [PR #780](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/780), [`POK-DEFENSE.md`](mandate-27/POK-DEFENSE.md) | Evidence level 3 is merged; no live production drift incident is claimed |
| 28 — sustained incidents | Frozen baseline lifecycle, stacked incident identity, continuity during telemetry gaps/load shifts, CAS/restart behavior, bounded evidence and external oracle | Merged [PR #778](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/778) | Evidence level 3 is merged; production Valkey/runtime wiring remains a deployment gate |

## Eight mentor questions every owner must answer

1. What user or operator failure does this mandate prevent?
2. Which exact code path makes the decision?
3. Which input contract is accepted, and what fails closed?
4. What is the threshold or invariant, and why was it chosen?
5. Which counterexample previously broke the claim, and which regression test
   now prevents recurrence?
6. Which command reproduces the result from a clean checkout?
7. Which immutable revision, dataset, runtime image or checksum binds the
   evidence?
8. What remains unproven, and which owner/window/approval is required to prove
   it?

## Closure rule

A mandate is technically ready only when the owner can point to all of:

- purpose and accountable owner;
- design plus rejected alternative or trade-off;
- code/replay path and regression tests;
- immutable artifact or runtime identity;
- one-command reproduction where the evidence is deterministic;
- explicit claim boundary;
- merged revision and required independent acceptance.

An open PR, local branch, self-generated verdict or stale runtime number cannot
alone satisfy the final two bullets.
