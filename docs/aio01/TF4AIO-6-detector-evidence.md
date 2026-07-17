# Detector validation evidence (Task TF4AIO-56)

## Context
- Scope mapping: TF4AIO-6 is the detector foundation scope (not this validation task), with key detector tasks TF4AIO-39 and TF4AIO-40.
- Task in this document: TF4AIO-56 (validate latency/error detector with controlled load test or failure drill, with CDO coordination).
- Drill reviewed: silent attack drill window `2026-07-14 07:10-07:40 UTC`.
- Source summary: PR comment and evidence thread in https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/138.

## Acceptance criteria mapping
- Detector catches controlled degradation **or** limitation is documented: `PASS (limitation branch)`.
- False positives/false negatives are recorded: `PASS (recorded below with confidence level)`.

## Evidence collected for the 2026-07-14 drill

### Positive collection (what was checked)
- Kubernetes events were queried for drill window.
- EKS audit logs were reviewed and showed 727 in-window requests.
- Selected workload pod logs were sampled for attack/error patterns.
- Alert evidence checks were attempted (detector firing alert / Alertmanager path).

### Negative collection (what was not available)
- No automated attack-detection evidence was observable in the reviewed window.
- Prometheus/OpenSearch/Jaeger API query path was not available from current access context.
- `pods/portforward=no` prevented direct port-forward based verification.
- Kubernetes service-proxy requests timed out.
- Kafka metrics scraping failed due to cross-namespace DNS resolution issues.

## Validation result (bounded)

| Item | Expected | Observed | Result |
| --- | --- | --- | --- |
| Controlled degradation should be observable via telemetry | Queryable metrics/logs/traces + detector output | Telemetry query APIs unavailable in current context | Limitation documented |
| Detector alert evidence in drill window | At least one machine-verifiable detector signal or alert trace | No detector firing evidence observed in reviewed artifacts | Negative controlled-drill result |
| Platform-side corroboration | Security/audit trace indicates attack behavior can be correlated with detector | Audit shows 727 requests but 0 non-system actions | Inconclusive for attack reality |

### Bounded conclusion
- This review is treated as a **negative controlled-drill result**.
- The absence of observable alert evidence does **not** prove no attack occurred.
- Because telemetry access path was blocked, this run cannot be used to claim detector success.
- The task remains valid under acceptance via documented limitations and explicit re-run plan.

## False positive / false negative register

| Type | Status | Notes |
| --- | --- | --- |
| False positive | `None observed` | No detector alert was captured, so no confirmed false-positive alert instance exists in this run. |
| False negative | `Uncertain risk` | No alert evidence was seen during an announced drill window, but attack ground truth was not provable from available telemetry. Classified as potential miss with low confidence due to observability gaps. |
| Unknown | `Present` | Telemetry/API access limitations create an unknown zone that blocks strict TP/FP/FN attribution. |

## Follow-up required (CDO dependency)
1. Restore programmatic telemetry access for Prometheus, OpenSearch, and Jaeger from approved execution path.
2. Enable one of: service account based API query, approved in-cluster runner, or controlled proxy path with stable timeout settings.
3. Fix Kafka metrics scraping dependency across namespaces (DNS/network policy).
4. Re-run one controlled load/failure drill with fixed query access and capture machine-verifiable detector outputs.
5. Attach rerun evidence to Jira/PR and update TP/FP/FN counts from `uncertain` to confirmed values.

## Re-run evidence checklist
- Drill window (UTC), scenario, owner, CDO approver.
- Detector raw output lines (JSONL) and query snapshots.
- Alert pipeline evidence (if used): firing/resolved timestamps.
- TP/FP/FN classification with confidence and rationale.
- Time-to-detect and known residual limitations.

## Cross references
- Planning doc: [AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md](./AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md).
- Detector deployment/channel evidence: [TF4AIO-40-detector-evidence.md](./TF4AIO-40-detector-evidence.md).
- Drill review thread: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/138.
