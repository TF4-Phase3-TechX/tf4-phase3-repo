# Task-4 runbook

## Goal
Run the flash-sale load test at 200 concurrent users with a 15-minute steady state and capture evidence.

## Timeline
- Ramp-up: 1 minute
- Steady-state: 15 minutes
- Ramp-down: 20 seconds
- Total runtime: 16 minutes 20 seconds

## Traffic mix
The Locust scenario is designed to exercise realistic flash-sale behavior rather than a single lightweight endpoint.

- Browse/discovery flow: product list, product detail, recommendations, reviews, ads, AI assistant, homepage
- Cart flow: view cart and add-to-cart actions
- Checkout flow: single-item and multi-item checkout

## Prerequisites
- Access to the target Kubernetes cluster
- `kubectl` configured for namespace `techx-tf4`
- The `load-generator` deployment available
- Flagd remains enabled; do not disable it for the test

## Dry-run
```bash
bash scripts/run-load-test-task4.sh dry-run
```

Then open the Locust UI at `http://localhost:8089` and verify the traffic mix and basic health.

## Full run
```bash
bash scripts/run-load-test-task4.sh full
```

## Stop conditions
Stop early if any of the following thresholds are exceeded:
- checkout-related errors exceed the configured threshold (5 errors per 100 log lines)
- CPU usage exceeds 90% for monitored pods
- memory usage exceeds 850Mi for monitored pods
- load-generator CPU exceeds 80% or memory exceeds 1200Mi
- node count grows beyond the baseline unexpectedly

## Dashboard mapping
Use Grafana in the `techx-observability` namespace and focus on the following signals for namespace `techx-tf4`:

| Acceptance Criteria | Metric | Grafana Panel | Evidence |
|---|---|---|---|
| Checkout ≥99% | Success rate | Checkout Success | Screenshot |
| Storefront p95 < 1s | HTTP p95 | Storefront Latency | Screenshot |
| Error rate thấp | 5xx rate | Error Rate | Screenshot |
| Không OOM | Container restart count | Pod Health | Screenshot |
| Không Memory Pressure | Memory working set | Container Memory | Screenshot |
| Node còn headroom | CPU/memory utilization | Node Overview | Screenshot |
| Observability hoạt động | Trace count / span count | Jaeger/OpenSearch | Screenshot |

Use these mappings as the evidence checklist when capturing screenshots and dashboards.

## Evidence checklist
Capture the following before closing the task:
- run output and timestamps from `task4-full-T0.txt` and `task4-full-T1.txt`
- Locust stats CSV and HTML report
- monitor log from `load-test-monitor-*.log`
- Grafana screenshots for latency, error rate, and request rate
- Jaeger traces for representative checkout and cart requests

## Evidence artifacts
Artifacts are written under:
- `docs/evidence/epic-03-performance-efficiency/runtime/`
