# Mandate 15 partial runtime evidence — 2026-07-23

> Canonical Jira: TF4AIO-80 / TF4AIO-77  
> Collection account: `511825856493`  
> Collection role: `TF4-AIReadOnlyOrLimitedInvoke`  
> Evidence window: 2026-07-23 14:08Z–14:23Z  
> Status: **PARTIAL — detection and safety path observed; live MTTD and real-channel receipt pending**

## Claim boundary

This record proves that the merged AIOps workload was running in the production
namespace, consumed real Prometheus data, created structured incidents and did
not mutate the cluster. It does **not** prove:

- the start time of either underlying degradation;
- live MTTD from fault injection to alert;
- labeled production precision or recall;
- Alertmanager delivery or Slack/on-call receipt;
- causal RCA; or
- Mandate 22 autonomous mitigation.

The detector timestamp-to-incident-log intervals below are publication latency,
not MTTD.

## Workload observation

Read-only inspection returned:

| Field | Observation |
|---|---|
| Namespace | `techx-tf4` |
| Deployment | `aiops` |
| Ready | `1/1` |
| Image | `66ed32b-aiops@sha256:7eff9e53c0ba609a2b421a33778b5bcf8ef98a429dd846e354c53ccf4fa6fb0d` |
| Mode | GitOps configuration keeps `REMEDIATION_MODE=dry-run` and autonomous remediation disabled |
| Stability limitation | Pod had 6 liveness-driven restarts and repeated one-second readiness/liveness timeouts over approximately 6h41m |

The process therefore is a standing in-cluster workload, not a run-once script,
but this sample must not be presented as uninterrupted reliability evidence.
The probe/event-loop contention requires a separate fix and a stable observation
window.

## Observed production incidents

### Checkout latency degradation

| Field | Value |
|---|---|
| Incident ID | `inc-4c1718b15075` |
| Detector timestamp | `2026-07-23T14:10:54.879772Z` |
| Structured incident log | `2026-07-23T14:11:03.787796Z` |
| Publication interval | approximately `8.908s` |
| Type / service | `service_latency_spike` / `checkout` |
| Severity / confidence | `medium` / `0.7469` |
| Observed p95 | `1628ms` |
| Evidence | Prometheus query, available baseline and 20 Jaeger traces |
| Decision evidence | ratio `1.2105`, z-score `1.4068`, EWMA `1.2710`, slow-drift `true` |
| Runtime state | `awaiting_approval`, `execution_attempts=0`, `mutation_blocked=false` |
| Recovery | `incident_auto_resolved` at `2026-07-23T14:15:15.818488Z` |

This is ambient-production evidence. Without a labeled fault-start timestamp it
cannot be counted as a true positive or used to calculate live MTTD.

### Checkout error-rate degradation

| Field | Value |
|---|---|
| Incident ID | `inc-1dc1af1a1ddf` |
| Detector timestamp | `2026-07-23T14:12:27.630248Z` |
| Structured incident log | `2026-07-23T14:12:32.263274Z` |
| Publication interval | approximately `4.633s` |
| Type / service | `service_error_rate_spike` / `checkout` |
| Severity / confidence | `medium` / `0.7502` |
| Observed error rate | `0.0465` |
| Evidence | Prometheus query, available baseline and 20 Jaeger traces |
| Decision evidence | ratio `24.7132`, z-score `20.1216`, slow-drift `true` |
| Runtime state | `awaiting_approval`, `execution_attempts=0` |

The gradual path may fire before the 5% absolute floor when its trend,
consistency, relative-baseline and early-warning floor checks all pass. This is
the intended slow-drift design; it still requires a labeled case to establish
whether the alert is correct.

## Safety observation

Both incidents stopped at `awaiting_approval`. Their audit trail contained
`incident_created` followed by `approval_requested`, while
`execution_attempts=0`. No rollout, patch, rollback or flagd mutation was
observed. This is evidence of the current production safety boundary, not
closed-loop remediation.

## Probe-stability follow-up — 2026-07-24

The original AIOps pod reached 12 restarts while running image
`66ed32b-aiops`. Kubelet events correlated the failures with one-second
liveness/readiness timeouts while synchronous Isolation Forest evaluation ran
on the FastAPI event loop.

Application PR
[`#587`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/587)
kept detector evaluations sequential but moved their CPU-bound work to worker
threads. It also stopped re-fitting Isolation Forest for acute-window
confirmation candidates because that score enriches confidence but cannot
change the acute gate. Offline verification reached 71 passing AIOps tests;
the representative nine-call detector path fell from approximately `3.93s` to
`1.23s`.

GitOps PR
[`#151`](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/151)
promoted the exact release:

```text
d9b18fa-aiops
sha256:c032171352869b91e2683826aefed9124ea2e35e78cd5095d51ca278b64d30c1
```

Argo reconciled Deployment generation 4 and created pod
`aiops-7d87f8b68b-r5tgr` at `2026-07-24T01:12:47Z`. In the first observation
window of more than four minutes, covering approximately five 45-second worker
polls, the pod remained Ready with:

| Observation | Result |
|---|---:|
| Container restarts | `0` |
| Prometheus HTTP 200 responses | `45` |
| OpenSearch HTTP 200 responses | `5` |
| Unexpected polling failures | `0` |
| `telemetry_degraded` events | `0` |

The only probe warnings were `connection refused` during initial container
startup before Uvicorn listened; they did not terminate the container. This is
short-window runtime evidence that the probe-starvation failure did not recur
across several polls. It is not a long-duration availability or reliability
claim.

## Coverage and observability limitations

The same worker window repeatedly emitted unavailable coverage for:

- latency and error-rate signals for `llm`;
- product-reviews error-rate coverage; and
- product-reviews LLM error coverage.

The node-local OpenTelemetry Collector was Ready, and NetworkPolicy allowed
OTLP ports 4317/4318. Collector logs nevertheless reported:

```text
memorylimiter: Memory usage is above soft limit. Refusing data.
otlp/jaeger: data refused due to high memory usage
spanmetrics: Failed ConsumeMetrics — data refused due to high memory usage
```

The DaemonSet has a `200Mi` memory limit with the memory limiter configured at
80%, and the same collector continuously attempts to scrape the obsolete
`kafka:9092` endpoint, which returns DNS failures. This is an observability
capacity/configuration dependency that can drop traces and derived span
metrics; it must be fixed before using a later window for trustworthy live
precision/recall.

## Real-channel evidence status

The source path exists:

```text
aiops_incidents_created_total
  -> AIOpsIncidentDetected PrometheusRule
  -> Alertmanager combined receiver
  -> #tf4-alerts
```

GitOps PR
[`#118`](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/118)
merged the continuous dry-run detector configuration. During this collection,
the read-only role could list Prometheus and Alertmanager workloads but service
proxy calls timed out, `pods/exec` was forbidden and Slack was not available to
the collector. Therefore no delivery timestamp is claimed.

## Reproduction commands

Use a valid read-only profile and kubeconfig:

```powershell
kubectl -n techx-tf4 get deploy,pod,svc -o wide |
  Select-String "aiops|product-reviews"

kubectl -n techx-tf4 describe pod -l app.kubernetes.io/component=aiops

kubectl -n techx-tf4 logs deploy/aiops --since=8h --timestamps |
  Select-String "incident_created|incident_auto_resolved|signal_coverage_degraded"

kubectl -n techx-observability logs daemonset/otel-collector-agent `
  --since=10m --timestamps |
  Select-String "memory usage|Failed ConsumeMetrics|data refused"
```

## Required closure run

1. Continue the probe/event-loop observation over the agreed reliability
   window. The first five post-fix polls completed with zero restarts, but the
   long-duration window remains open.
2. Remove or correct the stale `kafka:9092` receiver and size/shape the
   collector so it does not refuse telemetry during the labeled window.
3. Record a controlled scenario start timestamp without touching/disabling
   flagd.
4. Correlate scenario start, detector decision, incident creation, Prometheus
   alert firing, Alertmanager notification and Slack/on-call receipt.
5. Calculate live lead time and MTTD; retain the per-case label and output.
6. Attach the hidden-set outputs on grading day and obtain the Tech Lead ADR
   signature.
