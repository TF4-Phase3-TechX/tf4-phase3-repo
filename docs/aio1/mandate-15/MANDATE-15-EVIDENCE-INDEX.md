# Mandate 15 evidence index

**Ticket:** TF4AIO-80  
**Prepared:** 2026-07-25  
**Owner:** Trần Đình Thông  
**Status:** Implementation, continuous runtime, live incident and healthy-busy negative proven

## Closure checklist

| Required artifact | Evidence | Status |
|---|---|---|
| Merged detector implementation | [PR #509](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/509), merge `dc42af5b92f8211574ca02fd2768ccf2afb5d3b5` | Done |
| Open replay accepting external JSONL | `python -m benchmark.replay INPUT.jsonl --output OUTPUT.json` | Done |
| Committed labeled set | [`labeled-scenarios-v1.jsonl`](labeled-scenarios-v1.jsonl) | Done |
| Continuous in-cluster workload | [GitOps #118](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/118) and [read-only runtime capture](evidence/continuous-runtime-20260725.md): Deployment `1/1` Ready on exact `c2560b9-aiops` digest, current pod restart `0` | Observed |
| Real-channel incident summary | Slack FIRING/RESOLVED for `llm/service_availability` | Observed |
| Busy but healthy does not page | [GitOps #171](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/171) plus machine-readable observations | Observed |
| Masking resistance | External replay case passes; live hidden case remains grading-day evidence | Offline |
| MTTD before/after | Configuration-derived before and live after are recorded below | Bounded claim |
| Signed ADR | [`ADR-015`](ADR-015-aiops-detection.md) is signed by AIOps Lead Đình Thông Trần and accepted by Tech Lead Đinh Danh Nam | Done |

## Why busy differs from broken

Traffic volume is context, not a fault signal:

- `busy`: request rate is above the configured traffic seed while Deployment
  availability remains healthy and latency/error decisions do not breach;
- `degraded`: readiness or an SLO-backed latency/error decision is breached;
- `down`: desired replicas are non-zero and ready/available replicas are zero;
- `unknown`: telemetry or Kubernetes coverage is incomplete.

Only confirmed `degraded` or `down` states create an incident. `busy` is an
informational state and never pages. This avoids treating a healthy promotion
or flash-sale load increase as an outage.

Trade-off: the 5 req/s busy seed is explanatory state, not a health threshold.
The actual no-page decision still depends on the service's adaptive baseline,
availability and SLO evidence. A service can therefore be both high-traffic
and degraded; traffic does not mask the health breach.

## Offline reproducible scenario set

Reproduced on PR #669 head on 2026-07-26:

```text
Total cases: 6
Passed: 6/6
Events: 8
TP/FP/FN/TN: 4/0/0/4
Precision: 1.0
Recall: 1.0
Average simulated MTTD: 45 seconds
```

The focused replay tests also pass `19/19`. The added
`m15-cross-service-masking-02` case keeps a large isolated frontend latency
spike non-pageable while a simultaneous subtle checkout error-rate incident
still fires from checkout's own baseline within one detector cycle.

This is evidence level 3. It proves deterministic behavior on the committed
fixture, not the still-missing live masking incident, production accuracy or
hidden-set acceptance.

The same external-input command is the replay `repro`; replace the committed
fixture path with a mentor/BTC-supplied schema-v1 JSONL file without changing
the scorer.

## Live availability incident

The production drill created and resolved a critical
`llm/service_availability` incident:

- detector lead time from externally observed down state: approximately
  **60.9 seconds**;
- Prometheus alert start lead time: approximately **113 seconds**;
- zero remediation executions;
- dedicated Slack FIRING and RESOLVED receipts.

Evidence:

- [Slack FIRING](evidence/live-availability/slack-firing-20260724.png)
- [Slack RESOLVED](evidence/live-availability/slack-resolved-20260724.png)
- [Mandate 7b shared runtime chronology](../mandate-07b/MANDATE-07B-EVIDENCE-INDEX.md)

## MTTD before / after boundary

| Measurement | Value | Evidence boundary |
|---|---:|---|
| Before: legacy static alert delay | at least 300 seconds | Configuration-derived from the existing [`for: 5m` application rules](../../../techx-corp-chart/prometheus/flash-sale-alerts.yaml); not an observed incident |
| After: detector incident creation | ~60.9 seconds | Runtime-observed controlled availability drill |
| After: Prometheus alert start | ~113 seconds | Runtime-observed alert start |

The comparison supports a faster time-to-detect than the legacy rule delay,
but it is not a randomized before/after experiment and does not claim Slack
delivery latency.

## Live busy/healthy procedure

[GitOps PR #171](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/171)
temporarily changes only load-generator users `10 -> 150` and spawn rate
`1 -> 10`.

The initial GitOps #171 plan targeted checkout and proposed these success
signals:

- checkout Deployment still ready;
- request rate above `AIOPS_BUSY_REQUEST_RATE_THRESHOLD=5`;
- `aiops_service_state{service="checkout",state="busy"} == 1`;
- p95/error/burn decisions non-breaching;
- no checkout incident and no `AIOpsIncidentDetected` Slack alert.

Runtime traffic distribution did **not** push checkout above the busy seed.
Checkout peaked near `3.0 req/s` and remained healthy. The same controlled load
did push two other monitored services above the seed: frontend and cart.
Therefore this evidence intentionally changes scope from "checkout busy" to
"frontend/cart busy"; it does not claim that the checkout-specific expectation
passed.

The accepted bounded evidence condition is:

- frontend and cart remain `busy` for two signal-complete observations;
- their p95/error/burn decisions remain non-breaching;
- no incident or alert is created;
- a Kubernetes workload-health snapshot confirms Ready pods and zero restarts
  at the final observation.

Abort on readiness loss, pod restart, SLO breach, unexpected alert or another
team reporting interference. Restore load-generator to chart defaults
immediately after the observation window. Live remediation remains disabled.

Observed result:

- `frontend`: `busy`, request rate approximately `33.8 -> 66.3 req/s`,
  p95 `204.3 ms`, error and 5m/30m burn rate `0`;
- `cart`: `busy`, request rate approximately `14.6 -> 22.2 req/s`,
  p95 `6.2 ms`, error and 5m/30m burn rate `0`;
- checkout remained healthy;
- the final Kubernetes workload snapshot showed every inspected pod Ready with
  zero restarts;
- active AIOps incidents and alerts remained empty.

The first observation's full p95/error/burn fields were recovered from
Prometheus using an instant query pinned to `2026-07-25T04:11:20Z`; its
retrieval time is recorded separately. Its exact PromQL, Prometheus source and
API results are preserved in the
[historical query artifact](evidence/historical-prometheus-20260725T041120Z.json).
Kubernetes workload health was not historically available for that exact
timestamp, so the evidence claims two signal-complete detector observations
and one final workload-health snapshot, not two fully covered Kubernetes
snapshots.

The restore completed through
[GitOps PR #174](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/174).
It merged as `f46ee7e6683172ce66935e23e26789ee88390ba1`; the live Deployment
returned to `10 users / spawn rate 1` at `2026-07-25T04:33:24Z`. The new
load-generator pod was Ready with zero restarts, and no AIOps incident or alert
was active after restore.
The exact observations and bounded confusion matrix are preserved in
[live-labeled-set-20260724-25.json](evidence/live-labeled-set-20260724-25.json).

## Submission readiness

- [PR #633](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/633)
  passed refreshed CI and named review, then merged to `main` as
  `9c7b271a9639629ecc264d1e13df34e357df98a4`.
- ADR-015 has named AIOps Lead and Tech Lead acceptance.
- The PR/commit, replay command, runtime proof, labeled set, MTTD boundary,
  screenshots and signed ADR are linked from canonical Jira ticket
  `TF4AIO-80`. The ticket remains `In Progress`; merged evidence is not mentor
  or organizer acceptance.
- Organizer hidden-set outputs remain grading-day evidence.

## Claim boundary

The detector is implemented, on trunk, continuously deployed and observed
creating a real incident summary and on-call notification. The frontend/cart
healthy-busy negative is observed over two signal-complete observations plus
one final workload-health snapshot. The current public evidence
does not yet prove a live masking case, live high-burn escalation, long-run
production precision/recall or organizer acceptance.
