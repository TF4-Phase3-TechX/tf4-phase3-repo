# Mandate 27 — model-quality drift detection

Status: implementation and hermetic replay evidence complete; production
rollout evidence pending deployment.

The implementation provides:

- a versioned, compatibility-bound baseline;
- deterministic output-quality drift detection;
- stable, transient, seasonal and shifted replay controls;
- exact surface/metric/timestamp signals;
- content-free runtime outcome telemetry;
- Prometheus recording rules, alerts and Grafana panels;
- a human-controlled investigation/recovery runbook.

Start with the
[harness README](../../../tests/eval_mandate27/README.md), then run the command
in [the evidence index](./MANDATE-27-EVIDENCE-INDEX.md).

The committed code does not disable or modify flagd, add model calls, retain
request/response content or automatically take remediation action.

