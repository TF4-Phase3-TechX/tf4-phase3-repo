# PERF-04: Runtime Performance Evidence After Deployment

Capture time: 2026-07-09 13:47 +07:00

## Scope

This folder stores runtime evidence collected after the TechX application was deployed on EKS.

Namespace under test:

- Application namespace: `techx-tf4`
- Observability namespace: `techx-observability`
- Public ALB host: `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com`

## Task-4 acceptance evidence package

The Task-4 flash-sale load test is prepared for use as acceptance evidence with the following documented controls:

- Traffic mix: browse/discovery, cart, and checkout flows are included; the test does not rely on one lightweight endpoint only.
- Ramp-up timeline: 1 minute ramp-up to 200 users, 15 minutes steady-state at 200 users, 20 seconds ramp-down; total runtime is 16m20s.
- Stop conditions: stop early if checkout-related error logs exceed the configured threshold, if CPU or memory guardrails trigger, or if the load-generator shows abnormal resource pressure.
- Dashboard mapping: monitor latency, error rate, request rate, and pod/resource metrics in Grafana for namespace `techx-tf4`.
- Evidence checklist: capture the run script output, Locust stats/report, monitor log, and Grafana screenshots before closing the task.

See [TASK4-EVIDENCE-CHECKLIST.md](TASK4-EVIDENCE-CHECKLIST.md) for the full evidence checklist.

## Subtask status

| Subtask | Owner | Status | Evidence |
|---|---|---|---|
| PERF-04.1: Capture pod status and node placement | Tuấn | Done | `kubectl/pods-wide-2026-07-09.md`, `kubectl/nodes-zones-2026-07-09.md` |
| PERF-04.2: Capture CPU/memory usage | Huy | Done | PromQL queries via Prometheus/Grafana Explore. Screenshots: `grafana-pods-cpu.png`, `grafana-pods-memory.png` |
| PERF-04.3: Capture Grafana dashboard screenshot | Ninh | Done | Screenshots: `grafana-latency.png`, `grafana-error-rate.png`, `grafana-request-rate.png` |
| PERF-04.4: Capture Jaeger trace if available | Huy | Done | Trace screenshots in `screenshots/` directory, Services dropdown: `jaeger-services-dropdown.png` |
| PERF-04.5: Summarize runtime performance evidence | Huy | Done | This summary and `04-runtime-performance-evidence.md` |

## Findings

1. All 22 application deployments in `techx-tf4` are currently `READY 1/1`.
2. All application pods are currently `Running` and `READY 1/1`.
3. The application is spread across two EKS worker nodes in two Availability Zones:
   - `ip-10-0-10-231.ec2.internal` in `us-east-1a`
   - `ip-10-0-11-40.ec2.internal` in `us-east-1b`
4. Webstore public endpoint returns `HTTP 200 OK`.
5. Grafana public route `/grafana/` returns `HTTP 200 OK`.
6. Jaeger public route `/jaeger/ui/` returns `HTTP 200 OK`.
7. CPU/memory evidence has been successfully collected via Prometheus/Grafana PromQL queries.
8. Runtime warning events should be watched:
   - `accounting` pod has repeated restarts and current BackOff warning.
   - Grafana had a previous readiness probe failure but is currently `4/4 Running`.

Key runtime risks:

- `accounting` pod shows repeated restarts and BackOff warning.
- CPU/memory trend still needs the planned 48-72 hour evidence window before performance right-sizing.

Evidence folder:

`docs/evidence/epic-03-performance-efficiency/runtime/`

