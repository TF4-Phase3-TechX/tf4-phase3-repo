# Mandate 28 — frozen-baseline incident lifecycle

Status: **candidate replay passed at evidence level 3; independent review pending**.

## One-command replay

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.mandate28_replay \
  --scenario ../../../docs/aio1/mandate-28/scenario.jsonl \
  --oracle ../../../docs/aio1/mandate-28/oracle.json \
  --protected-manifest ../../../docs/aio1/mandate-28/protected-inputs.json \
  --repository-root ../../.. \
  --output-dir ../../../docs/aio1/mandate-28/evidence \
  --force
```

The generator, detector and oracle are separate. The strict external scenario
contains raw JSONL observations and no expected breach labels. The oracle is read
only after processing. The command writes:

- `alert-stream.jsonl` — at least one record per service per minute;
- `incidents.json` — durable final incident records;
- `summary.json` — machine-readable conditions and protected-input hashes;
- `candidate-verdict.json` — candidate result with independent review pending.

## Implementation

- `app/lifecycle.py` contains the composite-key lifecycle engine, true
  Median/MAD filtering, fitted-slope drift, timestamp high-water marks, bounded
  hashed evidence, serialization support and atomic Valkey CAS adapter.
- `benchmark/generate_mandate28_scenario.py` generates the reference raw input.
- `benchmark/mandate28_replay.py` validates and runs any conforming scenario.
- `.github/workflows/ci.yaml` runs the complete AIOps suite for AIOps changes.

The memory store is permitted only for deterministic tests and replay. It is
not a production fallback.

## Production activation gates

1. A dedicated AIOps Valkey endpoint, never `valkey-cart`.
2. `maxmemory-policy=noeviction` and operator evidence for AOF/RDB persistence.
3. Secret-managed TLS/auth URL and NetworkPolicy/RBAC ownership.
4. Retention calibrated from runtime incident duration.
5. Controlled restart/concurrency observation against real Prometheus signals.
6. A named Jira ticket and deployment-owner approval.
7. A named independent reviewer verdict tied to the reviewed commit SHA.

Passing this replay is not production durability or live no-silent-gap proof.
