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
| PERF-04.2: Capture CPU/memory usage | Huy | Done | PromQL queries via Prometheus/Grafana Explore. Screenshots: `grafana-pods-cpu.png`, `grafana-pods-memory.png` |
| PERF-04.3: Capture Grafana dashboard screenshot | Ninh | Done | Screenshots: `grafana-latency.png`, `grafana-error-rate.png`, `grafana-request-rate.png` |
| PERF-04.4: Capture Jaeger trace if available | Huy | Done | Trace screenshots in `screenshots/` directory, Services dropdown: `jaeger-services-dropdown.png` |
| PERF-04.5: Summarize runtime performance evidence | Huy | Done | This summary and `04-runtime-performance-evidence.md` |
| C0G-29: Finalize Flash Sale Verification Dashboard | CDO-04 | Done | `c0g-29/flash-sale-dashboard-design.md`, `techx-corp-chart/grafana/provisioning/dashboards/flash-sale-verification-dashboard.json` |

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

## Screenshot status

All screenshots have been successfully captured and saved in `/screenshots/` directory:
- `grafana-pods-cpu.png` (Pod CPU usage PromQL)
- `grafana-pods-memory.png` (Pod Memory usage PromQL)
- `grafana-latency.png` (Grafana latency dashboard)
- `grafana-error-rate.png` (Grafana error rate dashboard)
- `grafana-request-rate.png` (Grafana request rate dashboard)
- `jaeger-services-dropdown.png` (Jaeger services dropdown)
- Jaeger waterfall traces for critical flows

All public UI routes are reachable and verified.

## Jira evidence comment

PERF-04 runtime evidence collection has been started after deployment.

Completed:

- Captured pod status and node placement for namespace `techx-tf4`.
- Captured EKS node zone placement across `us-east-1a` and `us-east-1b`.
- Verified all application deployments are currently `1/1` available.
- Verified Webstore, Grafana and Jaeger public routes return `HTTP 200 OK`.
- Captured CPU/memory evidence via Prometheus/Grafana PromQL queries and Grafana screenshots.

Key runtime risks:

- `accounting` pod shows repeated restarts and BackOff warning.
- CPU/memory trend still needs the planned 48-72 hour evidence window before performance right-sizing.

Evidence folder:

`docs/evidence/epic-03-performance-efficiency/runtime/`

