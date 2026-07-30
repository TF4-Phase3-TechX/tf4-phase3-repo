# Mandate 14 evidence index

Current status: clean-SHA public evidence captured, ADR-014 accepted through
named approvals, and PR #658 merged to `main` as
`9bf9d9b`. The semantic amendment is implemented and calibrated offline; its
new PR review/merge, TF4-domain labels, and organizer hidden grading evidence
remain.

| Requirement | Artifact | Status |
|---|---|---|
| Final evidence index | `MANDATE-14-EVIDENCE-INDEX.md` | Public candidate, preserved failure, before/after and Jira-ready comment recorded |
| Open scoring logic | `tests/eval_mandate14/scorer.py`, `tests/eval_mandate14/semantic_faithfulness.py` | Pinned HHEM semantic support plus deterministic citation/safety/agency gates implemented |
| External runtime input | `tests/eval_mandate14/run_harness.py --dataset ...` | JSONL path and stdin implemented with pre-call schema validation |
| Both surfaces | `tests/eval_mandate14/adapters/` | Review retrieval-boundary adapter and Copilot gRPC/cart-state adapter implemented |
| Public labeled cases | `tests/eval_mandate14/public-cases-v1.jsonl` | 16 frozen cases across both surfaces and required sensitive families |
| At least 10 human labels / agreement | `tests/eval_mandate14/external-human-labels-summeval-v1.jsonl` | 100 external SummEval summary rows (50 pass/50 fail; 65 documents), pinned revision and hashes; failed generic NLI baseline 0.50/kappa 0.00 retained; exact HHEM runtime paths: structured claims 0.74/kappa 0.48, response assertions 0.71/kappa 0.42 |
| Per-case and aggregate metrics | generated package from `tests/eval_mandate14/runtime-repro.sh` | Runtime observations, scored per-case JSONL, aggregate JSON and Markdown implemented |
| Baseline/candidate latency, tokens, cost | `evidence/public/before-after.json` | Same 16 cases and model/guardrail; live before/after recorded |
| Hard bars | candidate `aggregate.json` | PII=0, prompt=0 and unauthorized-write=0; 16/16 supplied cases passed |
| One-command repro | `tests/eval_mandate14/runtime-repro.sh` | Implemented for public and externally supplied hidden JSONL |
| Signed ADR | `ADR-014-standard-ai-evaluation.md` | Accepted by the decision owner and three independent reviewers in PR #658 |

The separate 18-row `labeled-observations-v2.jsonl` remains a synthetic scorer
regression fixture. Its κ=1.0 must not be presented as human agreement. The
external human-label comparison is documented in
`tests/eval_mandate14/EXTERNAL-HUMAN-LABELS.md`. The generic NLI model remains
rejected at kappa 0.00. The pinned HHEM candidate passes the recorded gate on
both deployed paths: structured claims 0.74/kappa 0.48 and response assertions
0.71/kappa 0.42, with 3/3 contradiction controls and 0 truncations.
| Organizer hidden cases | `schemas/runtime-case.schema.json` | Same runner accepts the unchanged BTC file; grading-day capture pending |

The calibration fixture remains synthetic and is not production-quality
evidence. The public runtime package is a local real-model run and is labeled as
such in its manifest.
