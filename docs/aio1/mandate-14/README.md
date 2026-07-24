# Mandate 14 evidence index

Current status: two-surface harness implemented; clean-SHA live evidence and
named ADR approval remain before closure.

| Requirement | Artifact | Status |
|---|---|---|
| Open scoring logic | `tests/eval_mandate14/scorer.py` | Implemented |
| External runtime input | `tests/eval_mandate14/run_harness.py --dataset ...` | JSONL path and stdin implemented with pre-call schema validation |
| Both surfaces | `tests/eval_mandate14/adapters/` | Review retrieval-boundary adapter and Copilot gRPC/cart-state adapter implemented |
| Public labeled cases | `tests/eval_mandate14/public-cases-v1.jsonl` | 16 frozen cases across both surfaces and required sensitive families |
| ≥10 human labels / agreement | `tests/eval_mandate14/labeled-observations-v2.jsonl` | 18 synthetic calibration labels; agreement, confusion matrix and Cohen's kappa reported |
| Per-case and aggregate metrics | generated package from `tests/eval_mandate14/runtime-repro.sh` | Runtime observations, scored per-case JSONL, aggregate JSON and Markdown implemented |
| Baseline/candidate latency, tokens, cost | report `variants` and `before_after` | Schema and calibration implemented; live measurements pending |
| Hard bars | report `hard_bars` | Separate PII, prompt and unauthorized-write counts; certification also rejects any supplied-case failure |
| One-command repro | `tests/eval_mandate14/runtime-repro.sh` | Implemented for public and externally supplied hidden JSONL |
| Signed ADR | `ADR-014-standard-ai-evaluation.md` | Proposed; named approvals pending |
| Organizer hidden cases | `schemas/runtime-case.schema.json` | Same runner accepts the unchanged BTC file; grading-day capture pending |

Synthetic fixture results must not be represented as production evidence.
