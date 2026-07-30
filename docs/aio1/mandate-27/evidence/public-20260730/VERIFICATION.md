# Mandate 27 verification record

Implementation commit:
`de247172c298ce9a2aa94993c1a64adaa71b51d7`

## Hermetic replay

```text
45 passed
stable_false_flags=0
shifted_series_detected=2
copilot/fallback_rate detected after the injected shift
review_summary/faithfulness detected after the injected shift
```

## Regression

```text
268 passed
```

Scope: all `product-reviews` tests plus the Mandate 27 suite.

## Prometheus

Validated with Prometheus `v3.11.3`, matching the vendored chart app version.

```text
model-drift-recording-rules.yaml: SUCCESS, 7 rules
model-drift-alerts.yaml: SUCCESS, 3 rules
model-drift-recording-rules.test.yaml: SUCCESS
model-drift-alerts.test.yaml: SUCCESS
```

## Helm and dashboard

```text
helm lint: 1 chart linted, 0 failed
observability ConfigMap render: success
Grafana dashboard JSON parse: success
```

This pack is hermetic replay evidence, not a claim that the new metric/rules
have already been deployed to production.
