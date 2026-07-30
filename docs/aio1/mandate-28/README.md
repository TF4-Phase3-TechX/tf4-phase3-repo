# Mandate 28 — frozen-baseline incident lifecycle

Status: **implemented and replay-verified at evidence level 3**.

## One-command replay

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.mandate28_replay \
  --output-dir ../../../docs/aio1/mandate-28/evidence \
  --force
```

The command simulates `T-30..T179` without sleeping and writes:

- `alert-stream.jsonl` — one alert-state record per service per minute;
- `incidents.json` — durable final incident records;
- `summary.json` — machine-readable acceptance counters and conditions;
- `reviewer-verdict.json` — PASS/FAIL plus the claim boundary.

## Implementation

- `app/lifecycle.py` contains the composite-key lifecycle engine, frozen raw
  baseline, three-poll recovery, coverage holds, bounded CAS retry, deterministic
  memory store and atomic Valkey adapter.
- `benchmark/mandate28_replay.py` runs the 210-minute scenario, restart,
  telemetry gaps, insufficient traffic, enrichment loss, recovery flap and
  two-worker conflict.
- `tests/test_m28_lifecycle.py` and `tests/test_m28_replay.py` cover lifecycle,
  persistence, CAS, replay artifacts and overwrite safety.

The memory store is permitted only for deterministic tests and replay. It is
not a production fallback.

## Production activation gates

Production runtime wiring remains disabled until all of these are reviewed:

1. a dedicated AIOps Valkey endpoint, never `valkey-cart`;
2. `maxmemory-policy=noeviction` and operator evidence for AOF/RDB persistence;
3. secret-managed TLS/auth URL and NetworkPolicy/RBAC ownership;
4. retention calibrated from runtime incident duration rather than the replay
   seed of 3600 seconds;
5. controlled restart/concurrency observation against real Prometheus signals;
6. a named Jira ticket and deployment-owner approval.

Passing this replay must not be represented as production persistence or live
no-silent-gap evidence.
