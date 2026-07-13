# Task-3 — Flash-sale SLO and resource-pressure alerting evidence

**Implementation owner:** Tín Văn Phú (Văn Phú Tín)  
**Date:** 2026-07-13  
**Runtime namespaces:** `techx-tf4`, `techx-observability`

## Implemented scope

The production rule file contains 15 Prometheus alerts across four groups:

- `flash-sale-slo`: storefront latency, checkout success, browse success, cart success and frontend errors.
- `flash-sale-kubernetes-pressure`: OOM, restart burst, node CPU/memory, node readiness and pod scheduling/phase.
- `flash-sale-observability`: Grafana, Prometheus and Jaeger deployment availability.
- `flash-sale-test-window`: sustained load-generator traffic outside an approved window.

Every rule has a non-zero `for` duration, `severity`, `owner`, summary, description and runbook URL. Alertmanager is enabled and Prometheus loads the standalone rules from `/etc/alerts.d/*.yaml`.

## Repository verification

Commands executed locally:

```powershell
helm lint techx-corp-chart -f deploy/values-observability.yaml
helm template techx-observability techx-corp-chart `
  -n techx-observability `
  -f deploy/values-observability.yaml
```

Result:

```text
1 chart(s) linted, 0 chart(s) failed
```

Rendered-manifest checks confirmed:

- ConfigMap `prometheus-flash-sale-alerts` contains `flash-sale-alerts.yaml`.
- Prometheus mounts the ConfigMap at `/etc/alerts.d`.
- Prometheus `rule_files` contains `/etc/alerts.d/*.yaml`.
- Alertmanager Service, ConfigMap and StatefulSet are rendered.
- Grafana dashboard `Flash Sale Alert State` is provisioned with active count, pending/firing instances and state-over-time panels.

## Promtool validation and firing evidence

The rules were checked using the same Prometheus version deployed by the chart, `v3.11.3`:

```text
Checking techx-corp-chart/prometheus/flash-sale-alerts.yaml
  SUCCESS: 15 rules found

  SUCCESS
```

The second `SUCCESS` is the result of:

```text
promtool test rules techx-corp-chart/prometheus/tests/flash-sale-alerts.test.yaml
```

The firing test feeds sustained load-generator traffic into the production `LoadGeneratorTrafficOutsideTestWindow` rule and verifies:

- It is not firing at five minutes.
- It is firing at fifteen minutes after satisfying the configured ten-minute wait.
- The firing alert contains `severity=warning`, `owner=tf4-performance` and `component=load-generator`.

CI repeats both `promtool check rules` and `promtool test rules` for every chart/deploy change.

## Live metric discovery performed before implementation

The live Prometheus datasource was queried before selecting the expressions. It confirmed the following metric families and labels exist:

- `traces_span_metrics_calls_total` and `traces_span_metrics_duration_milliseconds_bucket` with frontend, checkout, cart and load-generator series.
- `container_oom_events_total`.
- `k8s_container_restarts`, `k8s_pod_phase`, `k8s_node_condition_ready` and `k8s_deployment_available`.
- `k8s_node_cpu_usage`, `k8s_node_memory_usage_bytes` and `k8s_node_memory_available_bytes`.

At discovery time, the proposed SLI expressions returned:

| Signal | Observed value |
| --- | ---: |
| Storefront p95 | approximately `8.58 ms` |
| Checkout success | `1.0` |
| Browse success | `1.0` |
| Cart success | `1.0` |
| Frontend error rate | `0` |
| Maximum raw node CPU usage | approximately `0.175 CPU cores` before normalization by `machine_cpu_cores` |
| Maximum node memory ratio | approximately `0.620` |

The load-generator was not idle during one discovery check: Locust reported `user_count=1`, `current_rps` around `0.2`, and Prometheus reported around `0.4` load-generator spans per second. This runtime observation was not stopped or modified as part of the read-only discovery.

## Post-deployment runtime evidence

The deployment workflow automatically saves:

- `prometheus-flash-sale-alerts-configmap.yaml`
- `prometheus-rule-state.json`
- `alertmanager-alert-state.json`
- Helm status and observability resource state

After deployment, run:

```bash
bash scripts/verify-flash-sale-alerts.sh
```

Expected result:

```text
Flash-sale alert verification passed: 15 healthy rules; Alertmanager API reachable.
```

Attach or link the deploy-evidence artifact and capture these UI states:

| Evidence | Required state |
| --- | --- |
| Prometheus `/rules` | Four `flash-sale-*` groups, 15 healthy rules |
| Prometheus `/alerts` | Inactive, pending or firing state visible |
| Alertmanager | API/UI reachable; firing alerts visible when present |
| Grafana `Flash Sale Alert State` dashboard | Active count and pending/firing state panels load from `webstore-metrics` |

## Operational handling

The complete owner mapping, first response, alert-specific diagnosis and mitigation steps are in `docs/runbooks/flash-sale-alerts.md`.

Approved load tests must use a time-bounded Alertmanager silence matching only `LoadGeneratorTrafficOutsideTestWindow`. The silence must expire at the documented test end; `LOCUST_AUTOSTART=false` remains the baseline.

## Rollback and disable

Rollback the observability Helm release when a bad rule or mount prevents a healthy rollout:

```bash
helm -n techx-observability history techx-observability
helm -n techx-observability rollback techx-observability <previous-revision> --wait --timeout 10m
```

For one noisy or invalid rule, correct/remove only that rule and redeploy. Do not disable all alert evaluation. Validate the rollback with the verification script and preserve both pre- and post-rollback rule-state evidence.

## Known monitoring boundary

Prometheus evaluates the observability availability rules and can alert when Grafana or Jaeger loses availability. A completely stopped Prometheus cannot evaluate its own `PrometheusUnavailable` rule. Total Prometheus failure therefore requires Grafana datasource-error monitoring, Kubernetes/external uptime monitoring, or another Prometheus evaluator. The rule and runbook explicitly document this self-monitoring boundary rather than claiming impossible in-process coverage.
