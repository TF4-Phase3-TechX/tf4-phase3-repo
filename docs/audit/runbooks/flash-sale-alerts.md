# Runbook: Flash-sale SLO and resource-pressure alerts

## Scope and ownership

This runbook covers the alert rules in `techx-corp-chart/prometheus/flash-sale-alerts.yaml`.

| Owner label | Responsibility |
| --- | --- |
| `tf4-webstore` | Storefront, browse, cart, checkout and customer-facing errors |
| `tf4-platform` | Pods, nodes, scheduling, OOM and restart incidents |
| `tf4-observability` | Prometheus, Grafana, Jaeger and alert delivery |
| `tf4-performance` | Load-generator and approved performance-test windows |

The current TF4 on-call is the first responder for every critical alert. Escalate to the owner label after initial containment. Do not disable flagd/OpenFeature incident mechanisms to make an alert disappear.

## Common first response

1. Record the alert name, labels, start time, current value and active load-test window.
2. Confirm the signal directly in Prometheus or Grafana Explore over the same time range.
3. Check recent deploys and Helm revisions for both `techx-tf4` and `techx-observability`.
4. If an unapproved load test is active, stop the Locust swarm before changing application capacity.
5. Capture pod status, warning events and relevant logs before restarting or rolling back anything.
6. Prefer rollback of the triggering release over an unreviewed live edit. Do not use `kubectl set env` for persistent remediation.

## StorefrontP95High

- Threshold: storefront p95 greater than `1000 ms` for `5m`.
- Owner/severity: `tf4-webstore` / `critical`.
- Verify the same PromQL in Grafana Explore and split latency by frontend span name.
- Check frontend, product-catalog, PostgreSQL and downstream trace latency in Jaeger.
- Stop an unapproved load test. During an approved test, compare node pressure and dependency saturation.
- Roll back the most recent application change if latency increased immediately after deployment.

## CheckoutSuccessRateLow

- Threshold: success rate below `99%` for `5m`, with at least 20 checkout requests in the window.
- Owner/severity: `tf4-webstore` / `critical`.
- Inspect `POST /api/checkout` errors and the checkout `PlaceOrder` trace.
- Check cart, product-catalog, currency, shipping, payment, Kafka and PostgreSQL dependencies.
- Preserve evidence before retrying. Avoid blind retries after a payment may have succeeded.
- Stop load generation if the failure rate continues to consume the checkout error budget.

## BrowseSuccessRateLow

- Threshold: browse success below `99.5%` for `5m`, with at least 20 requests.
- Owner/severity: `tf4-webstore` / `critical`.
- Split errors by homepage, product listing, product detail and data routes.
- Check frontend, product-catalog, image-provider, recommendation and ad dependencies.
- Confirm whether errors are customer requests or expected synthetic fault-injection traffic.

## CartSuccessRateLow

- Threshold: cart success below `99.5%` for `5m`, with at least 20 requests.
- Owner/severity: `tf4-webstore` / `critical`.
- Split GET, POST and DELETE cart operations and inspect frontend-to-cart traces.
- Check the cart pod, Valkey availability, latency and recent restarts.
- Do not delete or recreate Valkey state as an initial mitigation.

## FrontendErrorRateHigh

- Threshold: customer-facing frontend error rate above `5%` for `2m`, with at least 20 requests.
- Owner/severity: `tf4-webstore` / `critical`.
- Identify the failing routes and correlate them with the SLO-specific alerts.
- Check whether a common dependency or node is shared by the failing requests.
- Stop an unapproved load test and roll back a correlated application release when safe.

## PodOOMKilled

- Threshold: at least one cAdvisor OOM event in `10m`, held for `1m`.
- Owner/severity: `tf4-platform` / `critical`.
- Run `kubectl describe pod` and inspect `lastState`, exit code `137`, limits and warning events.
- Capture pre-restart logs with `kubectl logs --previous` when available.
- Check whether the workload is leaking memory or has an unrealistically small limit.
- Do not increase limits blindly if node memory is already pressured.

## PodRestartBurst

- Threshold: more than two additional restarts in `10m`, sustained for `5m`.
- Owner/severity: `tf4-platform` / `warning`.
- Inspect termination reason, probes, previous logs and recent rollout history.
- Escalate to critical handling when the affected service is checkout, cart, frontend or observability.
- Roll back a failing rollout rather than repeatedly deleting the pod.

## NodeCPUPressure

- Threshold: node CPU usage above `85%` for `10m`.
- Owner/severity: `tf4-platform` / `warning`.
- Find the highest CPU pods and check throttling, request/limit configuration and load-generator traffic.
- Confirm whether traffic is approved before considering capacity changes.
- Stop the test at the agreed safety threshold; do not expand the node group without cost approval.

## NodeMemoryPressure

- Threshold: node memory usage above `85%` for `10m`.
- Owner/severity: `tf4-platform` / `warning`.
- Find the highest working-set pods and correlate with OOM/restart alerts.
- Check whether observability ingestion or synthetic traffic is driving the increase.
- Stop the load test before the node begins evicting customer-facing workloads.

## NodeNotReady

- Threshold: node Ready condition differs from `1` for `2m`.
- Owner/severity: `tf4-platform` / `critical`.
- Inspect node conditions, kubelet status, networking and EKS node-group health.
- Check whether workloads were rescheduled and whether cart/stateful components were affected.
- Follow the managed node-group recovery path; do not force-delete the node before capturing events.

## PodPendingOrNotRunning

- Threshold: pod phase equals `1` (Pending), `4` (Failed) or `5` (Unknown) for `5m`.
- Owner/severity: `tf4-platform` / `warning`.
- Run `kubectl describe pod` and inspect `FailedScheduling` events.
- Check resource requests, ResourceQuota, node capacity, taints, selectors, affinity and PVC status.
- For rollout pods, pause or roll back the rollout if the previous version is still serving traffic.

## GrafanaUnavailable

- Threshold: Grafana deployment availability below one for `2m`.
- Owner/severity: `tf4-observability` / `critical`.
- Check Grafana pod status, sidecars, memory, mounted provisioning ConfigMaps and recent Helm changes.
- Use Prometheus `/alerts` directly while Grafana is unavailable.
- Roll back the observability Helm revision if the outage follows a deployment.

## PrometheusUnavailable

- Threshold: Prometheus deployment availability below one for `2m`.
- Owner/severity: `tf4-observability` / `critical`.
- Check pod status, OOM, storage, configuration reload logs and `/\-/ready` when reachable.
- Prometheus cannot reliably notify on its own total failure. Confirm this condition through Grafana query errors, Kubernetes monitoring or an external uptime check.
- Restore Prometheus before trusting SLO/resource alert state or historical evidence.

## JaegerUnavailable

- Threshold: Jaeger deployment availability below one for `2m`.
- Owner/severity: `tf4-observability` / `critical`.
- Check Jaeger pod status, OOM/restarts, memory limits and collector export errors.
- Continue incident triage with Prometheus and application logs until tracing is restored.
- Roll back the observability release if availability dropped after a Helm upgrade.

## LoadGeneratorTrafficOutsideTestWindow

- Threshold: load-generator telemetry above `0.1 spans/s` for `10m`.
- Owner/severity: `tf4-performance` / `warning`.
- Confirm the approved test owner, UTC start/end, target users and stop conditions.
- If no approved window exists, stop the Locust swarm and verify `user_count=0` plus zero new load-generator spans.
- For an approved test, create a silence matching only this alert and set its expiry to the documented end time. Never create an open-ended silence.
- Keep `LOCUST_AUTOSTART=false`; starting a test is a manual, time-bounded operation.

## Verification and evidence

After deployment:

```bash
kubectl -n techx-observability get pods
kubectl -n techx-observability get configmap prometheus-flash-sale-alerts
kubectl -n techx-observability logs deployment/prometheus -c prometheus-server --since=10m
```

Use Prometheus `/rules` or `/api/v1/rules` to confirm all four groups are loaded, and Prometheus `/alerts` to capture active alert state. Save screenshots and API output with UTC timestamps in the Task-3 evidence document.

> **Note:** Alertmanager is currently disabled. Alert notification delivery (Slack/email/webhook) is deferred until a receiver configuration is approved.

The offline firing test is defined in `techx-corp-chart/prometheus/tests/flash-sale-alerts.test.yaml`. It proves that sustained load-generator traffic transitions the real production rule to firing after its ten-minute wait.

## Disable and rollback

To disable one bad rule, remove or correct only that rule in `flash-sale-alerts.yaml`, merge through the normal workflow and redeploy observability. Do not disable the whole alerting stack for a single malformed expression.

For immediate rollback of the observability release:

```bash
helm -n techx-observability history techx-observability
helm -n techx-observability rollback techx-observability <previous-revision> --wait --timeout 10m
```

After rollback, confirm Prometheus readiness, rule count and Grafana datasource health.
