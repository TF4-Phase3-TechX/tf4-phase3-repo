# C0G-17 — Baseline EKS without automatic Locust traffic

**Jira:** [C0G-17](https://ngonguyentruongan2907.atlassian.net/browse/C0G-17)  
**Scope:** `techx-tf4` EKS application baseline  
**Owner:** Nguyễn Thành Vinh  
**Support:** Huy (Grafana/Jaeger verification)  
**Status:** Runtime verification passed — 2026-07-12

## Purpose

The baseline EKS application must keep the `load-generator` available for approved tests without automatically starting a Locust swarm after a rollout. Automatic traffic contaminates request rate, latency, error rate, trace volume, and cost/performance measurements.

The baseline setting is the named `LOCUST_AUTOSTART: "false"` override in `deploy/values-app-stamp.yaml`. This document does not change local Docker Compose behavior and does not remove or scale down the load-generator as the baseline state.

## Preconditions

- The pull request containing C0G-17 changes is approved and merged to `main`.
- The GitHub Actions `helm-render` job and its `rendered-manifests` artifact are available.
- The GitHub Actions deployment workflow has completed. Begin observations after rollout completion.
- `kubectl`, `helm`, and AWS EKS access target cluster `techx-tf4-cluster`, namespace `techx-tf4`.
- Access is available to Grafana and Jaeger, directly or through the frontend-proxy routes.

## Deployment configuration proof

Record the following before observing traffic:

| Field | Evidence |
| --- | --- |
| PR / commit | Pending commit / PR creation |
| CI run / rendered-manifests artifact | Run for image `06c7031` — artifact `deploy-evidence-06c7031` |
| Deployment workflow / deploy-evidence artifact | [committed artifact](deploy-evidence-06c7031/) |
| Helm revision | `14` |
| Image tag | `06c7031` (`06c7031-load-generator`) |
| UTC deploy completion | `2026-07-12T17:30:14Z` |

The deployment artifact recorded `generation=7`, `observedGeneration=7`, `readyReplicas=1`, `availableReplicas=1`, and `locustAutostart="false"` for the live `load-generator` Deployment.

The CI rendered-manifests artifact must show the app release was rendered with both deployment overlays. Verify the effective setting from that artifact or reproduce the render locally:

```bash
helm dependency build ./techx-corp-chart

helm template techx-corp ./techx-corp-chart \
  --namespace techx-tf4 \
  --set default.image.repository="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}" \
  --set default.image.tag=preview \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  > /tmp/techx-corp-app.yaml

grep -A1 'name: LOCUST_AUTOSTART' /tmp/techx-corp-app.yaml
```

Expected output: one `LOCUST_AUTOSTART` value, `"false"`.

After GitHub Actions deploys, retain its `load-generator-runtime-config.json` artifact and independently confirm the rollout:

```bash
kubectl -n techx-tf4 rollout status deployment/load-generator --timeout=180s
kubectl -n techx-tf4 get deployment/load-generator -o json |
  jq '[
    .spec.template.spec.containers[]
    | select(.name == "load-generator")
    | .env[]?
    | select(.name == "LOCUST_AUTOSTART")
    | .value
  ]'
```

Expected output: one value, `"false"`.

## Bounded no-synthetic-traffic observation

Record a UTC start and end timestamp. Use a minimum ten-minute window after a two-to-three-minute settling period. Do not use historical traces as proof because retained Jaeger data can include earlier test runs.

| Field | Window 1 | Window 2 |
| --- | --- | --- |
| Start UTC | `<timestamp>` | `<timestamp>` |
| End UTC | `<timestamp>` | `<timestamp>` |
| Observer | `<name>` | `<name>` |
| Locust UI URL | `<url>` | `<url>` |

### 1. Locust UI state

Use the ALB route `/loadgen/` and capture the state that shows zero active users and no active swarm. This prevents a manually started test from being misclassified as an autostart regression.

- URL: `http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/loadgen/`
- Captured state: `ready`, `user_count=0` before and after the recorded window.

### 2. Grafana request-rate evidence

In Grafana Explore, select the Prometheus datasource used by the spanmetrics dashboard. Capture the query, selected time range, timestamp, and result for each observation window:

```promql
sum(rate(traces_span_metrics_calls_total{service_name="load-generator"}[5m])) or vector(0)
```

```promql
sum(increase(traces_span_metrics_calls_total{service_name="load-generator"}[10m])) or vector(0)
```

Expected result: both queries are `0` for each bounded window. Also capture the existing spanmetrics/service-throughput dashboard filtered to `load-generator`.

| Window | Five-minute rate | Ten-minute increment | Query route |
| --- | ---: | ---: | --- |
| 2026-07-12T18:19:31Z → 18:29:32Z | `0` at start/end | `0` at start/end | Grafana Prometheus datasource proxy |

Capture total application or `frontend-proxy` traffic separately as context only. It does **not** have to be zero: public requests, health checks, and the deployment workflow’s smoke requests can create legitimate non-Locust traces.

### 3. Jaeger trace-volume evidence

Search Jaeger for service `load-generator`, with the start and end times set to the same bounded observation window. Capture the zero-result page.

Use the ALB-routed Jaeger API with the same UTC window converted to microseconds:

```bash
curl -sG 'http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/jaeger/ui/api/traces' \
  --data-urlencode 'service=load-generator' \
  --data-urlencode "start=${START_US}" \
  --data-urlencode "end=${END_US}" \
  --data-urlencode 'limit=1000'
```

Expected result: zero new `load-generator` traces and spans in the bounded window.

| Window | Jaeger result | API route |
| --- | --- | --- |
| 2026-07-12T18:19:31Z → 18:29:32Z | `0 traces / 0 spans` | `/jaeger/ui/api/traces` |

## Recorded runtime result — 2026-07-12

Evidence was collected through the public ALB `http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com`; no port-forward was used. The Locust UI check was intentionally performed before a 660-second settling period so its own UI-render telemetry could not appear in the bounded evidence window.

| Check | Result |
| --- | --- |
| Live deployment | `LOCUST_AUTOSTART=false`; generation `7` observed as `7`; one ready/available replica |
| Locust pre-window state | `ready`, `user_count=0`, configured host `http://frontend-proxy:8080` |
| Locust post-window state | `ready`, `user_count=0` |
| Evidence window | `2026-07-12T18:19:31Z` to `2026-07-12T18:29:32Z` (UTC) |
| Grafana five-minute rate at start/end | `0` / `0` |
| Grafana ten-minute increment at start/end | `0` / `0` |
| Jaeger `load-generator` traces in bounded window | `0` traces, `0` spans |

Queries were sent through Grafana's Prometheus datasource proxy (`/grafana/api/datasources/uid/webstore-metrics/resources/api/v1/query`) and Jaeger was queried at `/jaeger/ui/api/traces` with the same start/end microsecond timestamps. This proves that the deployed Locust server was idle and did not auto-generate synthetic traffic during the observation window.

## Rollback

If `LOCUST_AUTOSTART=false` causes an unexpected operational issue, revert the approved overlay commit through the normal PR and GitHub Actions deployment path. Do not use `kubectl set env`, as it creates Helm drift. Re-enabling autostart is not the normal test-start mechanism; use the Locust UI for approved, time-bounded test runs.

## Jira completion comment

> C0G-17 complete for EKS baseline. `LOCUST_AUTOSTART=false` is applied through `deploy/values-app-stamp.yaml`; the load-generator remains deployed and is manually operable. The rendered manifest CI assertion and the live Deployment evidence each confirm one `LOCUST_AUTOSTART=false` value. In the bounded post-deploy observation windows, Grafana recorded zero load-generator spanmetric request rate/increment and Jaeger recorded zero new load-generator traces. Any total application traffic was captured separately and was not classified as synthetic traffic.
>
> Evidence: PR `<link>` · CI/rendered manifest `<link>` · deployment/runtime artifact `<link>` · Grafana `<link>` · Jaeger `<link>` · evidence document `<link>`.
