# AIO1 endpoint, evaluation, and reproduction package

Tracking issue: `TF4AIO-49`

Accountable owner: Nam

Reproduction support: Thông

## Purpose and claim boundary

This page gives a reviewer one starting point for the AIO1 endpoints, deterministic
evaluation, committed evidence, and known limitations. Commands below are relative
to the repository root unless they contain an explicit `cd`.

The evidence levels in this package are deliberately separate:

1. designed/documented;
2. implemented;
3. tested offline or in CI;
4. deployed;
5. observed in runtime;
6. accepted/sign-off.

Committed reports and passing local tests prove at most level 3. They do not prove
that the same revision is deployed, healthy in the cluster, or accepted. Before
using this page as final submission evidence, record the exact merged commit and
rerun every applicable command from a clean checkout of that commit.

## Reviewer entry points

The AIOps service exposes:

| Method | Path | Purpose | Mutation |
|---|---|---|---|
| `GET` | `/healthz` | Process liveness | No |
| `GET` | `/readyz` | Dependency readiness | No |
| `GET` | `/metrics` | Prometheus metrics | No |
| `GET` | `/v1/telemetry/status` | Input telemetry status | No |
| `GET` | `/v1/incidents` | List incidents | No |
| `GET` | `/v1/incidents/{incident_id}` | Inspect one incident | No |
| `GET` | `/v1/incidents/{incident_id}/summary` | Human-readable evidence summary | No |
| `POST` | `/v1/incidents/{incident_id}/approve` | Authorize a gated action | Yes; token required |
| `POST` | `/v1/incidents/{incident_id}/reject` | Reject a gated action | Yes; token required |

Source of truth: `techx-corp-platform/src/aiops/app/main.py`.
Do not exercise the mutation endpoints against a shared environment without an
approved owner and change window.

## Mandate 15 deterministic replay

Run:

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.replay \
  ../../../docs/aio1/mandate-15/labeled-scenarios-v1.jsonl \
  --output mandate-15-replay-local.json
```

Expected acceptance signal:

- exit code `0`;
- `Passed: 5 / 5`;
- matrix `TP=3, FP=0, FN=0, TN=3`;
- average offline MTTD `45s`.

The reviewed, committed reference output is
`docs/aio1/mandate-15/replay-report-v1.json`. The design and scoring boundary are
documented in `docs/aio1/mandate-15/ADR-015-aiops-detection.md`.

This is deterministic offline evidence. Live continuous-pod MTTD and real on-call
timestamps remain pending and must not be inferred from the replay.

## Paid-AI-safe load regression

Baseline Locust traffic must not call the Bedrock-backed AI Assistant endpoint.
The paid scenario is an explicit opt-in with an accountable owner, unique run ID,
request cap, time window, minimum pacing, and one synthetic user.

Run the no-provider-call regression:

```bash
cd techx-corp-platform/src/load-generator
python -m unittest -v test_paid_ai_control.py
```

The tests prove offline that:

- paid AI is disabled by default;
- enabling it without attribution and bounds fails closed;
- hard request and time ceilings are enforced;
- `WebsiteUser` contains no paid-AI route;
- `PaidAIUser` exists only under the enabled gate and has `fixed_count = 1`.

For an explicitly authorized paid run, configure all of:

```text
LOCUST_PAID_AI_ENABLED=true
LOCUST_PAID_AI_OWNER=<accountable-person>
LOCUST_PAID_AI_RUN_ID=<unique-run-id>
LOCUST_PAID_AI_MAX_REQUESTS=<1..500>
LOCUST_PAID_AI_WINDOW_MINUTES=<1..60>
LOCUST_PAID_AI_WAIT_SECONDS=<at-least-1>
```

The request budget is process-local. It is not safe for distributed Locust workers
without a shared budget. A passing unit test does not prove a production success
path or a Bedrock invocation.

## Delivery dependency ledger

These pull requests are related delivery inputs, not evidence that their features
are merged or deployed:

| Area | Accountable owner | Pull request | Dependency / claim boundary |
|---|---|---|---|
| Mandate 22 closed loop | Hòa | `#669` | Source/CI evidence until merged; precedes the durable-saga change |
| Mandate 22 durable saga | Hòa | `#711` | Rebase on the final `#669` revision and rerun its evidence |
| Mandate 23 memory/cache | Huy Vũ | `#692` | Source/CI evidence until merged; foundational product-review change |
| Mandate 24 LLM observability | Thông | `#707` | Rebase on the final foundational product-review revision and rerun its evidence |
| Mandate 25 resilience | Tất Văn | `#710` | Rebase after the preceding product-review changes and rerun its evidence |
| TF4AIO-88 adversarial review | Thành Tâm | `#701` | Review artifact, not implementation or runtime evidence |

Recommended merge order for the conflicting product-review work is `#692`, then
rebased `#707`, then rewritten/rebased `#710`. For the remediation work, merge
`#669` before rebasing `#711`.

## Known limitations and final submission gate

- No command on this page proves that the relevant revision is deployed.
- No paid AI success path is executed by the offline regression.
- The Locust cap is not shared across distributed workers.
- Mandate 15 live MTTD and real notification timestamps are pending.
- Open pull requests in the ledger may change; their final merged SHAs and evidence
  must replace the review-time state above.

`TF4AIO-49` is ready to close only when another reviewer can start from a clean
checkout, run the commands, locate the output, and record:

```text
Merged commit:
Reviewer:
UTC timestamp:
Mandate 15 replay result:
Load safety regression result:
Deployment revision (if claiming deployed):
Runtime evidence link (if claiming observed):
Acceptance/sign-off link (if claiming accepted):
```
