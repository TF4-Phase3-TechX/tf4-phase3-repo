# C0G-17 — Baseline EKS without automatic Locust traffic

**Jira:** [C0G-17](https://ngonguyentruongan2907.atlassian.net/browse/C0G-17)  
**Scope:** `techx-tf4` EKS application baseline  
**Owner:** Nguyễn Thành Vinh  
**Support:** Huy (Grafana/Jaeger verification)  
**Status:** Pending CI/deployment evidence

## Purpose

The baseline EKS application must keep the `load-generator` available for approved tests without automatically starting a Locust swarm after a rollout. Automatic traffic contaminates request rate, latency, error rate, trace volume, and cost/performance measurements.

The baseline setting is the named `LOCUST_AUTOSTART: "false"` override in `deploy/values-app-stamp.yaml`. This document does not change local Docker Compose behavior and does not remove or scale down the load-generator as the baseline state.

## Preconditions

- The pull request containing C0G-17 changes is approved and merged to `main`.
- The GitHub Actions `helm-render` job and its `rendered-manifests` artifact are available.
- The GitHub Actions deployment workflow has completed. Begin observations only after its smoke HTTP requests finish.
- `kubectl`, `helm`, and AWS EKS access target cluster `techx-tf4-cluster`, namespace `techx-tf4`.
- Access is available to Grafana and Jaeger, directly or through the frontend-proxy routes.

## Deployment configuration proof

Record the following before observing traffic:

| Field | Evidence |
| --- | --- |
| PR / commit | `<link>` |
| CI run / rendered-manifests artifact | `<link>` |
| Deployment workflow / deploy-evidence artifact | `<link>` |
| Helm revision | `<value>` |
| Image tag | `<value>` |
| UTC deploy completion | `<timestamp>` |

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

Port-forward the service if the ingress route is unavailable:

```bash
kubectl -n techx-tf4 port-forward svc/load-generator 8089:8089
```

Capture a screenshot of `http://127.0.0.1:8089` (or `/loadgen/`) that shows zero active users and no active swarm. This prevents a manually started test from being misclassified as an autostart regression.

- Screenshot / URL: `<link>`
- Captured UTC: `<timestamp>`

### 2. Grafana request-rate evidence

In Grafana Explore, select the Prometheus datasource used by the spanmetrics dashboard. Capture the query, selected time range, timestamp, and result for each observation window:

```promql
sum(rate(traces_span_metrics_calls_total{service_name="load-generator"}[5m])) or vector(0)
```

```promql
sum(increase(traces_span_metrics_calls_total{service_name="load-generator"}[10m])) or vector(0)
```

Expected result: both queries are `0` for each bounded window. Also capture the existing spanmetrics/service-throughput dashboard filtered to `load-generator`.

| Window | Five-minute rate | Ten-minute increment | Screenshot / query link |
| --- | ---: | ---: | --- |
| 1 | `<0>` | `<0>` | `<link>` |
| 2 | `<0>` | `<0>` | `<link>` |

Capture total application or `frontend-proxy` traffic separately as context only. It does **not** have to be zero: public requests, health checks, and the deployment workflow’s smoke requests can create legitimate non-Locust traces.

### 3. Jaeger trace-volume evidence

Search Jaeger for service `load-generator`, with the start and end times set to the same bounded observation window. Capture the zero-result page.

If the compatibility query API is available, collect a machine-readable count through a local port-forward as a supplement:

```bash
kubectl -n techx-observability port-forward svc/jaeger 16686:16686

curl -sG http://127.0.0.1:16686/api/traces \
  --data-urlencode 'service=load-generator' \
  --data-urlencode "start=${START_US}" \
  --data-urlencode "end=${END_US}" \
  --data-urlencode 'limit=1000' |
  jq '{trace_count: (.data | length), span_count: ([.data[].spans | length] | add // 0)}'
```

Expected result: zero new `load-generator` traces and spans in the bounded window. If the API is unavailable or differs on the deployed Jaeger version, retain the UI search as authoritative evidence and record the API response; do not guess a replacement endpoint.

| Window | Jaeger result | UI screenshot | API output, if supported |
| --- | --- | --- | --- |
| 1 | `0 traces / 0 spans` | `<link>` | `<link>` |
| 2 | `0 traces / 0 spans` | `<link>` | `<link>` |

## Rollback

If `LOCUST_AUTOSTART=false` causes an unexpected operational issue, revert the approved overlay commit through the normal PR and GitHub Actions deployment path. Do not use `kubectl set env`, as it creates Helm drift. Re-enabling autostart is not the normal test-start mechanism; use the Locust UI for approved, time-bounded test runs.

## Jira completion comment

> C0G-17 complete for EKS baseline. `LOCUST_AUTOSTART=false` is applied through `deploy/values-app-stamp.yaml`; the load-generator remains deployed and is manually operable. The rendered manifest CI assertion and the live Deployment evidence each confirm one `LOCUST_AUTOSTART=false` value. In the bounded post-deploy observation windows, Grafana recorded zero load-generator spanmetric request rate/increment and Jaeger recorded zero new load-generator traces. Any total application traffic was captured separately and was not classified as synthetic traffic.
>
> Evidence: PR `<link>` · CI/rendered manifest `<link>` · deployment/runtime artifact `<link>` · Grafana `<link>` · Jaeger `<link>` · evidence document `<link>`.
