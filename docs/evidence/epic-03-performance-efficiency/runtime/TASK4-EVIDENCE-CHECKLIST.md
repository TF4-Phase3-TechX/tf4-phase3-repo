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
- [ ] Save Locust stats CSV.
- [ ] Save Locust HTML report.
- [ ] Save the monitor log.
- [ ] Save the run timestamps in the evidence folder.
- [ ] Save screenshots or exports for Grafana/Jaeger as needed.
