# Mandate 27 verification record

Implementation commit:
`a935834512b5f4e7ba05e0555a852384ffccfd41`

## Hermetic replay

```text
26 passed
stable_false_flags=0
shifted_series_detected=2
copilot/fallback_rate detected after the injected shift
review_summary/faithfulness detected after the injected shift
```

## Regression

```text
305 passed
```

Scope: all `product-reviews` tests plus Mandate 14, 24 and 27 suites. The
loopback gRPC integration test was run outside the filesystem/network sandbox.

## Prometheus

Validated with Prometheus `v3.11.3`, matching the vendored chart app version.

```text
model-drift-recording-rules.yaml: SUCCESS, 5 rules
model-drift-alerts.yaml: SUCCESS, 2 rules
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
