# Mandate 27 proof of knowledge

- Owner: AIO1
- Scope: model-output quality drift for `review_summary` and `copilot`
- Source of truth: version-bound external JSONL replay
- Operational companion: content-free Prometheus outcome counters

## What we built

The external detector builds a reviewed baseline per surface and metric, binds
it to model, guardrail and scorer versions, and emits a signal containing the
surface, metric, detection time, baseline/current values and persistence
evidence. It retains no prompt, response, identity or source text.

Fallback and abstention use a minimum adverse delta plus a one-sided 99% Wilson
interval. Faithfulness uses the declared mean-drop threshold; JSD describes the
distribution but cannot hide a regression inside a coarse bin. A signal needs
30 temporally distributed samples and two breached windows at least 10 minutes
apart.

The online path emits bounded outcome plus model/guardrail/scorer labels.
Prometheus computes traffic-weighted seven-day baselines and requires traffic,
history and 30-minute persistence. It is advisory because a rolling window can
eventually absorb persistent drift; the frozen external replay remains the
closure authority.

## Reviewer counterexamples and defenses

| Counterexample | Defense | Test/evidence |
|---|---|---|
| Missing surface or metric reported healthy | Baseline capabilities are required; absence returns `baseline_insufficient` | `test_missing_expected_*` |
| Semantic and lexical faithfulness disagree | Semantic adapter reads only `semantic_faithfulness`; lexical-only input fails closed | `test_mandate14_adapter_*` |
| Mean drops >0.10 inside one histogram bin | Mean threshold independently breaches | `test_material_mean_drop_*` |
| Same-timestamp burst satisfies persistence | Window span and elapsed persistence gates | `test_same_timestamp_burst_*` |
| Runtime `degraded` is ignored | Canonical outcome maps it to `fallback` | `test_quality_outcome_has_bounded_cardinality` |
| Traffic mix biases online average | Baseline is unfavorable events divided by total requests | Prometheus recording rules |
| Version change contaminates comparison | Version labels partition online series; missing identity alerts | metric and alert rules |
| Windows checkout breaks evidence hashes | LF policy plus byte-level verifier in CI | `verify_evidence.py` |

## Reproduction

```bash
python -m pytest -q tests/eval_mandate27/tests
python -m pytest -q techx-corp-platform/src/product-reviews/tests/test_metrics.py
python -m tests.eval_mandate27.verify_evidence \
  docs/aio1/mandate-27/evidence/public-20260730
docker run --rm --entrypoint /bin/promtool -v "$PWD:/work:ro" -w /work \
  prom/prometheus:v3.11.3 check rules \
  techx-corp-chart/prometheus/model-drift-recording-rules.yaml \
  techx-corp-chart/prometheus/model-drift-alerts.yaml
```

## Claim boundary

Synthetic shifted fixtures prove detector behavior, not production quality.
The online companion detects bounded proxy changes, not semantic causality.
Mitigation still requires correlation with the Mandate 14 suite, provider
health and the immutable runtime revision.
