# Mandate 7b live detection evidence index

**Ticket:** TF4AIO-72  
**Prepared:** 2026-07-25  
**Owner:** Trần Đình Thông  
**Status:** Live E2E detection and two-case controlled-set measurement complete

## Acceptance mapping

| Requirement | Evidence | Status |
|---|---|---|
| Detector fires end to end | Controlled `llm` availability fault produced an AIOps incident, Prometheus alert and Slack notification | Observed |
| Alert resolves after recovery | Restored workload produced detector auto-resolution, active gauge `1 -> 0` and a dedicated Slack `[RESOLVED]` receipt | Observed |
| Precision / recall / lead time | One controlled positive plus one healthy-busy negative; machine-readable event-level report | Observed |
| Impact-based alerting | Request-weighted 5m/30m burn-rate implementation merged in PR #616 | Implemented and CI-tested |
| Non-spam behavior | Alert lifecycle is grouped by `incident_type + service`; two fully covered busy observations produced no incident or alert | Observed on bounded drill |
| More than one service | Runtime configuration monitors `llm`, `product-reviews`, `frontend`, `cart` and `checkout`; generic signals are separated from LLM-only signals | Deployed |

## Live positive: `llm` unavailable

The controlled fault and restore were applied through reviewed GitOps changes:

- fault: [GitOps PR #164](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/164);
- restore: [GitOps PR #165](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/165);
- scoped alert lifecycle: [GitOps PR #163](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/163).

Recorded timestamps:

| Event | UTC |
|---|---:|
| Workload observed down (`desired=1`, `ready=0`, `available=0`) | 2026-07-24 06:41:07 |
| Detector incident created | 2026-07-24 06:42:07.896875 |
| Prometheus alert start | 2026-07-24 06:43:00 |
| Workload restored | 2026-07-24 06:50:53 |
| Detector auto-resolved | 2026-07-24 06:51:50.421712 |

Derived lead times:

- detector lead time: approximately **60.9 seconds** from the externally
  observed down state;
- alert-rule start lead time: approximately **113 seconds**;
- Slack delivery latency is **not claimed**, because the screenshot preserves
  the alert start time but not an independent Slack receipt timestamp.

Screenshots:

- [Slack FIRING](../mandate-15/evidence/live-availability/slack-firing-20260724.png)
- [Slack RESOLVED](../mandate-15/evidence/live-availability/slack-resolved-20260724.png)

## Impact-aware alerting

[Application PR #616](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/616)
merged as `bb30780f3aa4a02e2b129b983458f8965bd8eec3`.
For services with approved SLOs, the detector calculates request-weighted
error-budget burn over exact 5-minute and 30-minute windows:

- both windows `>= 2x`: warning budget burn;
- both windows `>= 10x`: critical budget burn;
- a short spike in only one window cannot become critical;
- missing request coverage remains unavailable rather than healthy zero.

This proves implementation and CI behavior. A live high-burn alert has not yet
been injected, so this index does not claim production threshold calibration.

## Controlled labeled set

The live set is intentionally small and reports event-level results, not
per-service accuracy:

| Case | Label | Detector outcome | Classification |
|---|---|---|---|
| `live-availability-20260724` | Incident | Fired | TP |
| `live-busy-healthy-20260725` | Normal/high load | No incident or alert | TN |

Bounded event-level result:

| TP | FP | FN | TN | Precision | Recall | Average detector lead time |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 0 | 1 | 1.0 | 1.0 | 60.9 s |

Machine-readable evidence:
[live-labeled-set-20260724-25.json](../mandate-15/evidence/live-labeled-set-20260724-25.json).

During the healthy-busy case, two covered observations classified both
`frontend` and `cart` as `busy`. Request rates rose from approximately
33.8/14.6 req/s to 66.3/22.2 req/s respectively. Their error rates and 5m/30m
burn rates remained zero, all observed pods stayed Ready with zero restarts,
and no AIOps incident or alert fired.

Hidden organizer scenarios remain grading-day evidence. The `1.0` values above
describe only this two-event controlled set and are not long-run production
accuracy.

## Reproduction

1. Apply a reviewed, reversible fault or load change through GitOps.
2. Record the workload transition time from Kubernetes.
3. Wait for fully covered detector polls (`AIOPS_POLL_SECONDS=45`).
4. Query `aiops_service_state`, `aiops_incident_active`,
   `aiops_error_budget_burn_rate` and `ALERTS` from production Prometheus.
5. Restore the GitOps override immediately after the hold window.
6. Correlate detector, Prometheus and Slack evidence by service and incident
   type.

## Claim boundary

Evidence level 5 is reached for one availability incident, its notification
lifecycle and one healthy-busy negative. Live masking resistance, live
high-burn escalation, broader production accuracy and mentor acceptance remain
pending.
