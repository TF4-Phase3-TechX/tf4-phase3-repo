# Mandate 14 evidence index

Current status: clean-SHA public evidence captured; Jira publication, hidden
grading evidence and named ADR approval remain before mandate closure.

| Requirement | Artifact | Status |
|---|---|---|
| Final evidence index | `MANDATE-14-EVIDENCE-INDEX.md` | Public candidate, preserved failure, before/after and Jira-ready comment recorded |
| Open scoring logic | `tests/eval_mandate14/scorer.py` | Implemented |
| External runtime input | `tests/eval_mandate14/run_harness.py --dataset ...` | JSONL path and stdin implemented with pre-call schema validation |
| Both surfaces | `tests/eval_mandate14/adapters/` | Review retrieval-boundary adapter and Copilot gRPC/cart-state adapter implemented |
| Public labeled cases | `tests/eval_mandate14/public-cases-v1.jsonl` | 16 frozen cases across both surfaces and required sensitive families |
| ≥10 human labels / agreement | `tests/eval_mandate14/labeled-observations-v2.jsonl` | 18 synthetic calibration labels; agreement, confusion matrix and Cohen's kappa reported |
| Per-case and aggregate metrics | generated package from `tests/eval_mandate14/runtime-repro.sh` | Runtime observations, scored per-case JSONL, aggregate JSON and Markdown implemented |
| Baseline/candidate latency, tokens, cost | `evidence/public/before-after.json` | Same 16 cases and model/guardrail; live before/after recorded |
| Hard bars | candidate `aggregate.json` | PII=0, prompt=0 and unauthorized-write=0; 16/16 supplied cases passed |
| One-command repro | `tests/eval_mandate14/runtime-repro.sh` | Implemented for public and externally supplied hidden JSONL |
| Signed ADR | `ADR-014-standard-ai-evaluation.md` | Proposed; named approvals pending |
| Organizer hidden cases | `schemas/runtime-case.schema.json` | Same runner accepts the unchanged BTC file; grading-day capture pending |

The calibration fixture remains synthetic and is not production-quality
evidence. The public runtime package is a local real-model run and is labeled as
such in its manifest.
