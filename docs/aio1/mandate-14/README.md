# Mandate 14 evidence index

Current status: implementation in progress; this index is not closure evidence.

| Requirement | Artifact | Status |
|---|---|---|
| Open scoring logic | `tests/eval_mandate14/scorer.py` | Implemented |
| External observation input | `tests/eval_mandate14/run_eval.py --input ...` | Implemented |
| Both surfaces | `surface=review_summary\|copilot` schema | Implemented in scorer; runtime adapter pending TF4AIO-81 |
| ≥10 human labels / agreement | `labeled-observations-v1.jsonl`, `sample-report.json` | 12 synthetic calibration labels; 100% scorer agreement |
| Per-case and aggregate metrics | `sample-report.json` | Implemented for calibration |
| Baseline/candidate latency, tokens, cost | report `variants` and `before_after` | Schema and calibration implemented; live measurements pending |
| Hard bars | report `hard_bars_pass` | Candidate fixture passes; live evidence pending |
| One-command repro | `tests/eval_mandate14/README.md` | Implemented for scorer |
| Signed ADR | `ADR-014-standard-ai-evaluation.md` | Proposed; named approvals pending |
| Organizer hidden cases | same JSONL contract | Grading-day capture pending |

Synthetic fixture results must not be represented as production evidence.
