# Mandate 25: AI resilience and controlled fallback

**Jira:** TF4AIO-86

**Owner:** Tất Văn

**Evidence status:** implemented and tested offline; runtime proof pending

## What is implemented

- explicit two-attempt application retry with bounded backoff and deadline;
- normalized timeout, throttling, and provider-5xx errors;
- circuit open, fast-fail, cooldown, and recovery;
- honest unavailable/insufficient responses;
- malformed tool-shaped model output rejected before any action;
- token-protected, TTL-bounded external gRPC fault control;
- content-free resilience status used by `/api/copilot-health`;
- no flagd mutation.

## External drill

Provision the approved runtime secret:

```text
Secret: product-reviews-mandate25-control
Key: token
Environment: MANDATE25_FAULT_TOKEN
```

Port-forward the deployed Product Reviews service and export the same token:

```bash
kubectl -n techx-tf4 port-forward svc/product-reviews 3551:3551
export MANDATE25_TARGET=127.0.0.1:3551
export MANDATE25_FAULT_TOKEN='<runtime secret>'
```

Run one bounded fault window around an external replay command:

```bash
./scripts/inject_mandate25_faults.sh throttling -- \
  python -m tests.eval_mandate25.replay \
  tests/eval_mandate25/cases.example.jsonl \
  --target 127.0.0.1:3551 \
  --repeat 6 \
  --output /tmp/m25-throttling.jsonl
```

Supported modes are `timeout`, `throttling`, `provider_5xx`, and
`malformed_output`. The script:

1. sets a fault with a maximum 120-second TTL;
2. reads back effective fault and circuit state;
3. runs the supplied command;
4. restores `off` and reads back the restored state on every exit path.

Status-only and emergency restore commands:

```bash
./scripts/inject_mandate25_faults.sh status
./scripts/inject_mandate25_faults.sh recover
```

## Required runtime evidence

Record the exact deployed image/Argo revision and sanitized outputs for:

1. single timeout, throttling, and 5xx fallback without 500/hang;
2. exact attempt count and bounded latency;
3. sustained failures causing `circuit_state=open`;
4. fast-fail with no provider attempt;
5. cooldown plus a successful real-provider recovery;
6. malformed output returning an honest insufficient response with no action;
7. final effective readback showing `fault.mode=off`;
8. named ADR acceptance.

Do not call the mandate Done from unit tests or the control script alone.
