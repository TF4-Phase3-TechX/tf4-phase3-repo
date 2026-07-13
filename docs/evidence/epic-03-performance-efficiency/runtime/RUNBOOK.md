# Task-4 runbook

## Goal
Run the flash-sale load test at 200 concurrent users with a 15-minute steady state and capture evidence.

## Prerequisites
- Access to the target Kubernetes cluster
- `kubectl` configured for namespace `techx-tf4`
- The `load-generator` deployment available

## Dry-run
```bash
bash scripts/run-load-test-task4.sh dry-run
```

Then open the Locust UI at `http://localhost:8089` and verify the traffic mix and basic health.

## Full run
```bash
bash scripts/run-load-test-task4.sh full
```

## Evidence
Artifacts are written under:
- `docs/evidence/epic-03-performance-efficiency/runtime/`

## Stop conditions
Stop early if:
- checkout-related errors exceed the configured threshold
- CPU or memory guardrails trigger
- the monitor script indicates abnormal growth
