# Task-4 evidence checklist

## Acceptance evidence package

Use this checklist before marking Task-4 as evidence-ready.

### Scenario definition
- [ ] Confirm the target is 200 concurrent users.
- [ ] Confirm the steady-state window is 15 minutes.
- [ ] Confirm the timeline is documented as ramp-up 1 minute, steady-state 15 minutes, ramp-down 20 seconds.

### Traffic mix
- [ ] Confirm the Locust scenario includes browse/discovery traffic.
- [ ] Confirm the scenario includes cart operations.
- [ ] Confirm the scenario includes checkout operations.
- [ ] Confirm the scenario does not rely only on a single lightweight endpoint.

### Execution controls
- [ ] Confirm flagd remains enabled during the run.
- [ ] Confirm dry-run was executed before the full run.
- [ ] Confirm the run script output captured the start and end timestamps.

### Guardrails and stop conditions
- [ ] Confirm the monitor script captured CPU/memory/error guardrail data.
- [ ] Confirm the run was stopped early if thresholds were exceeded.

### Dashboard / observability evidence
- [ ] Capture Grafana latency evidence for the storefront and checkout flows.
- [ ] Capture Grafana error-rate evidence.
- [ ] Capture Grafana request-rate evidence.
- [ ] Capture pod resource evidence if there were resource concerns.

### Output artifacts
- [ ] Save Locust stats CSV as `task4-full-stats.csv`.
- [ ] Save Locust HTML report as `task4-full-report.html`.
- [ ] Save the monitor log.
- [ ] Save the run timestamps as `task4-full-T0.txt` and `task4-full-T1.txt`.
- [ ] Save Grafana/Prometheus dashboard screenshots covering the exact full-run window.
- [ ] Save the cost-efficiency evidence summary as `task4-cost-efficiency.md`.
- [ ] Confirm full-run SLO validation passed in the run script.
