# PERF-04: Runtime Performance Evidence After Deployment

Capture time: 2026-07-09 13:47 +07:00

## Scope

This folder stores runtime evidence collected after the TechX application was deployed on EKS.

Namespace under test:

- Application namespace: `techx-tf4`
- Observability namespace: `techx-observability`
- Public ALB host: `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com`

## Subtask status

| Subtask | Owner | Status | Evidence |
|---|---|---|---|
| PERF-04.1: Capture pod status and node placement | Tuấn | Done | `kubectl/pods-wide-2026-07-09.md`, `kubectl/nodes-zones-2026-07-09.md` |
| PERF-04.2: Capture CPU/memory usage | Huy | Blocked | `kubectl/top-metrics-blocker-2026-07-09.md` |
| PERF-04.3: Capture Grafana dashboard screenshot | Ninh | Partially done | `grafana/http-check-2026-07-09.md`; screenshots still need browser capture |
| PERF-04.4: Capture Jaeger trace if available | Huy | Partially done | `jaeger/http-check-2026-07-09.md`; trace screenshots still need browser capture |
| PERF-04.5: Summarize runtime performance evidence | Huy | Done | This summary |

## Findings

1. All 22 application deployments in `techx-tf4` are currently `READY 1/1`.
2. All application pods are currently `Running` and `READY 1/1`.
3. The application is spread across two EKS worker nodes in two Availability Zones:
   - `ip-10-0-10-231.ec2.internal` in `us-east-1a`
   - `ip-10-0-11-40.ec2.internal` in `us-east-1b`
4. Webstore public endpoint returns `HTTP 200 OK`.
5. Grafana public route `/grafana/` returns `HTTP 200 OK`.
6. Jaeger public route `/jaeger/ui/` returns `HTTP 200 OK`.
7. CPU/memory evidence could not be collected because the Kubernetes Metrics API is not installed or unavailable:
   - `kubectl top pods` returns `error: Metrics API not available`
   - `kubectl top nodes` returns `error: Metrics API not available`
   - `v1beta1.metrics.k8s.io` APIService is not found
8. Runtime warning events should be watched:
   - `accounting` pod has repeated restarts and current BackOff warning.
   - Grafana had a previous readiness probe failure but is currently `4/4 Running`.

## Screenshot status

Screenshot capture is still pending for:

- Grafana latency dashboard
- Grafana error rate dashboard
- Grafana request rate dashboard
- Jaeger checkout trace
- Jaeger product flow trace

The public UI routes are reachable, so screenshot collection is now unblocked from an application availability perspective. A team member with browser access should capture screenshots into:

- `runtime/grafana/screenshots/`
- `runtime/jaeger/screenshots/`

## Jira evidence comment

PERF-04 runtime evidence collection has been started after deployment.

Completed:

- Captured pod status and node placement for namespace `techx-tf4`.
- Captured EKS node zone placement across `us-east-1a` and `us-east-1b`.
- Verified all application deployments are currently `1/1` available.
- Verified Webstore, Grafana and Jaeger public routes return `HTTP 200 OK`.
- Recorded CPU/memory blocker: Metrics API is not available, so `kubectl top pods` and `kubectl top nodes` cannot currently produce usage data.

Key runtime risks:

- `accounting` pod shows repeated restarts and BackOff warning.
- Metrics-server / Metrics API is missing, blocking CPU and memory evidence required for performance right-sizing.

Evidence folder:

`docs/evidence/epic-03-performance-efficiency/runtime/`

