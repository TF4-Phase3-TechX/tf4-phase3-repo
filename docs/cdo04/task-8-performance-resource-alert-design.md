# Task 8 — Performance and resource alert design

## Objective and operating model

This design covers latency, errors, workload stability, node pressure, observability health, and unexpected synthetic traffic. Rules are stored in `techx-corp-chart/prometheus/flash-sale-alerts.yaml`, evaluated every 30 seconds, routed by Alertmanager, and shown by the provisioned Grafana alert-state dashboard.

Critical means customer flow loss, data-risking resource failure, or loss of an observability surface and requires immediate TF4 on-call triage. Warning means sustained capacity drift or unexpected test traffic and should be handled during the active support window. The `owner` label identifies the resolver; TF4 on-call remains first responder.

## Proposed rules

| Alert | Signal / metric | Firing condition | Duration | Severity | Owner |
|---|---|---|---:|---|---|
| `CheckoutLatencyP95High` | `traces_span_metrics_duration_milliseconds_bucket`, frontend server span `POST /api/checkout` | 5-minute histogram p95 > 1,000 ms | 5m | critical | `tf4-webstore` |
| `CheckoutErrorRateHigh` | `traces_span_metrics_calls_total`, frontend server span `POST /api/checkout` | 5-minute error ratio > 1% and at least 20 requests | 5m | critical | `tf4-webstore` |
| `BrowseSearchLatencyP95High` | `traces_span_metrics_duration_milliseconds_bucket`, frontend browse/product routes | 5-minute histogram p95 > 1,000 ms | 5m | critical | `tf4-webstore` |
| `PodRestartBurst` | `k8s_container_restarts` | more than 2 added restarts in 10 minutes | 5m | warning | `tf4-platform` |
| `PodOOMKilled` | `container_oom_events_total` | at least one OOM event in 10 minutes | 1m | critical | `tf4-platform` |
| `NodeCPUPressure` | `k8s_node_cpu_usage / machine_cpu_cores` | normalized node CPU > 85% | 10m | warning | `tf4-platform` |
| `NodeMemoryPressure` | `k8s_node_memory_usage_bytes / (usage + available)` | node memory usage > 85% | 10m | warning | `tf4-platform` |
| `GrafanaUnavailable` | `k8s_deployment_available` | Grafana has no available replica | 2m | critical | `tf4-observability` |
| `JaegerUnavailable` | `k8s_deployment_available` | Jaeger has no available replica | 2m | critical | `tf4-observability` |
| `LoadGeneratorTrafficOutsideTestWindow` | `traces_span_metrics_calls_total{service_name="load-generator"}` | load-generator rate > 0.1 spans/s | 10m | warning | `tf4-performance` |

Related existing rules for browse/cart success, frontend error rate, node readiness, pod scheduling, Prometheus, payment, PostgreSQL, Valkey, and Kafka remain enabled. They are not substitutes for the Task 8 rules above.

## Noise controls and clear conditions

- Latency and resource rules require a sustained `for` window; transient spikes remain pending and clear automatically when the expression becomes false.
- Checkout error rate requires 20 requests per five-minute evaluation window, preventing one low-volume error from paging the team.
- Restart and OOM alerts use increases over bounded windows instead of lifetime counters.
- CPU is normalized by node cores; memory is a ratio of used plus available bytes, so thresholds work across node sizes.
- Approved benchmark windows use a time-bounded Alertmanager silence matching only `LoadGeneratorTrafficOutsideTestWindow`. The silence must expire at the planned test end; `LOCUST_AUTOSTART=false` remains the normal baseline.
- Every alert carries `severity`, `owner`, `component`, summary, description, and a runbook URL. Alertmanager sends resolved notifications so responders can see that the condition cleared.

## Verification and evidence plan

### Repository checks

1. Run `promtool check rules techx-corp-chart/prometheus/flash-sale-alerts.yaml`.
2. Run `promtool test rules techx-corp-chart/prometheus/tests/flash-sale-alerts.test.yaml`. The suite provides deterministic firing and non-firing evidence for latency, checkout error volume gating, restart burst, node readiness, availability, and unexpected load traffic.
3. Run `helm lint techx-corp-chart -f deploy/values-observability.yaml` and render the chart. Confirm the `prometheus-flash-sale-alerts` ConfigMap and `/etc/alerts.d/*.yaml` mount exist.

Local validation on 2026-07-20 passed: Prometheus `promtool` v3.11.3 found 21 valid rules, the rule-test suite returned `SUCCESS`, Helm lint returned `1 chart(s) linted, 0 chart(s) failed`, and the rendered manifest contained both the alert ConfigMap and rule-file mount.

### Staging/EKS checks

1. Ninh deploys the chart to staging, then runs `bash scripts/verify-flash-sale-alerts.sh`; expected result is 21 healthy `flash-sale-*` rules and a reachable Alertmanager API.
2. Huy captures Prometheus `/rules`, Prometheus `/alerts`, Alertmanager, and Grafana `Flash Sale Alert State` screenshots with rule name, state, labels, start time, and value visible.
3. During an approved test window, inject one controlled signal at a time: k6 checkout latency/error, a disposable pod restart/OOM, a temporary staging-only Grafana or Jaeger scale-down, and a short load-generator run. Restore the workload immediately after evidence is captured.
4. Confirm the rule progresses inactive → pending → firing → resolved and that the correct owner receives both firing and resolved notifications. Record timestamps to verify the configured duration.
5. An reviews threshold wording against the observed staging baseline. Change a threshold only with a linked query/screenshot and rerun repository plus staging checks.

Do not deliberately create OOM, node pressure, or observability outage in production/demo. Synthetic `promtool` tests validate rule logic; staging validates metric labels, routing, UI visibility, and recovery.

## Current validation boundary / blocker

The rules are implemented in the chart, but this change does not deploy to EKS or claim live screenshots. Live firing evidence requires staging access, an approved test window, Alertmanager receiver credentials, and coordination with Ninh/Huy. `LoadGeneratorTrafficOutsideTestWindow` currently uses a time-bounded silence as the approved-window marker because Prometheus has no authoritative benchmark-schedule metric. A future pipeline can publish such a metric and remove the manual silence step.

Prometheus cannot report its own total outage. Grafana and Jaeger availability are covered here; full Prometheus black-box monitoring requires an external evaluator and remains a documented observability boundary.

## Rollback

For an invalid or noisy rule, revert only the affected rule and redeploy; do not disable all alert evaluation. If the rules ConfigMap or mount makes the observability release unhealthy, run `helm -n techx-observability history techx-observability`, roll back to the previous healthy revision, and rerun `scripts/verify-flash-sale-alerts.sh`. Remove any test-only silence after the approved window and preserve pre/post rollback evidence.
