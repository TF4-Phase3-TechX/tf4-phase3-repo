# ADR-M07: Rule-based, per-service anomaly detection for the AIOps MVP

- **Status:** Proposed — requires AIO lead/reviewer sign-off for Mandate 07a
- **Date:** 2026-07-16
- **Owners:** AIO01
- **Jira:** [TF4AIO-71](https://aio1-xbrain.atlassian.net/browse/TF4AIO-71), [TF4AIO-72](https://aio1-xbrain.atlassian.net/browse/TF4AIO-72)
- **Implementation:** [PR #137](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/137), [PR #181](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/181), [PR #208](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208)

## Context

TF4 already emits metrics, logs, and traces, but an operator still has to inspect dashboards to discover an incident. Mandate 07 requires the system to detect anomalies and surface a visible alert before a user reports the problem.

The current evidence verifies telemetry schemas and source fields, but it does not establish a 48-hour normal-traffic baseline. During the latest cluster check, span metrics had no samples because the cluster was idle. Therefore all numeric ranges in Mandate 07a are initial engineering baselines and must not be represented as measured production baselines.

The product-reviews service currently emits these Bedrock-specific metrics:

- `app_llm_calls_total`, partitioned by `llm.outcome` and `error.class`;
- `app_llm_errors_total` for provider failures returning the safe fallback;
- `app_llm_latency_seconds` for provider-call latency;
- token and estimated-cost counters.

The detector must use these real contracts instead of inventing an `app_llm_requests_total` signal.

## Decision

For the MVP, AIO01 will use auditable rule-based detection with the following layers:

1. **Per-service univariate rules are the mandatory floor.** Each `service × signal` pair has its own initial normal band, anomaly threshold, sustained duration, severity, and minimum-traffic guard.
2. **Prometheus is the primary decision source** for p95 latency, service error rate, and LLM provider failures. OpenSearch logs and Jaeger traces provide corroborating evidence and investigation links.
3. **The Python detector may correlate signals** into an incident score and summary, but correlation must not suppress a critical base rule. An unavailable telemetry source is reported as `unknown`, never as a healthy zero.
4. **Alertmanager/structured detector output is the visible output contract.** Events include rule, service, environment, severity, timestamp, evidence query/link, and source availability. Alerts use sustained windows, minimum traffic, grouping, and warning/critical severity to reduce spam.
5. **Mandate 07a values are provisional engineering baselines.** They become calibrated baselines only after the labeled normal/incident windows required by Mandate 07b.

### Initial detection contract

| Signal | Scope | Initial normal assumption | Initial anomaly rule | Method |
| --- | --- | --- | --- | --- |
| p95 request latency | `product-reviews`, `checkout`, `cart` | Candidate band `200–800 ms` under active traffic; not yet measured as a 48-hour baseline | warning `>1000 ms`, critical `>2000 ms`, sustained `3m` | `histogram_quantile()` over `traces_span_metrics_duration_milliseconds_bucket`, grouped per service |
| Service error rate | `product-reviews`, `checkout`, `cart` | Candidate band `0–1%`; live calibration pending | warning `>1%`, critical `>5%`, minimum 10 requests, sustained `2m` | error/total ratio from `traces_span_metrics_calls_total` |
| LLM provider failures | `product-reviews` | Expected `rate(app_llm_errors_total[3m]) = 0` during a healthy provider window | warning `>0.1 errors/s`, critical `>0.5 errors/s`, sustained `3m` | Prometheus error counter, corroborated by `otel-logs-*` timeout/rate-limit/provider-error events |

These values are safe starting points for a controlled MVP. They are hypotheses to test, not claims of measured steady-state behavior.

## Alternatives considered

| Alternative | Advantages | Disadvantages | Outcome |
| --- | --- | --- | --- |
| Per-service rules plus optional correlation | Explainable, reproducible, works with limited labeled data, easy to tune and roll back | Requires manual calibration and can miss novel patterns | **Selected** |
| One global static threshold for all services | Very simple | Ignores different service baselines and creates false positives/negatives | Rejected |
| Weighted correlation score only | Produces one incident score and can combine weak signals | Can hide a severe individual signal and is harder to defend without calibration | Supplementary only |
| ML anomaly-detection model | Can learn seasonality and nonlinear behavior | Insufficient labeled/history data, operational complexity, poor MVP explainability | Deferred until post-MVP evidence exists |
| Logs-only detection | Easy keyword matching | Misses latency/saturation and is sensitive to log wording | Corroboration only |

## Consequences

### Positive

- Every alert is traceable to a real telemetry query and a service-specific decision.
- The detector remains understandable during mentor review and incident response.
- Minimum-traffic and sustained-window guards reduce low-volume and cold-start noise.
- The design can later evolve toward burn-rate or learned baselines without replacing the output contract.

### Trade-offs and residual risks

- Initial thresholds can be too sensitive or too permissive until Mandate 07b calibration.
- Missing span metrics during idle periods prevents claiming historical production baselines.
- Metric and label cardinality must remain bounded; user prompts, model responses, review text, and PII must never become metric labels or detector logs.
- A provider quota outage can supply a labeled failure window, but it cannot substitute for a healthy normal window when calculating precision.

## Mandate 07b validation and acceptance

The runtime decision is accepted only after AIO01 and CDO execute a controlled GitOps test window and capture:

1. pre-state revision, active rule version, and normal window;
2. a labeled set of injected incidents with exact start timestamps;
3. the resulting detector event and visible Alertmanager/log/dashboard evidence;
4. recall (`caught incidents / K`), precision (`correct alerts / all alerts`), and lead-time (`first alert - incident start`);
5. warning/critical routing, grouping behavior, and false-alert count in the normal window;
6. rollback revision and post-rollback health.

Threshold or query changes after calibration must be committed through GitOps and linked from TF4AIO-72.

## Rollback and review triggers

- Roll back the detector/rule revision through the previous GitOps commit; do not edit the production ConfigMap directly.
- Disable notification routing, not telemetry collection, if an alert storm occurs during calibration.
- Revisit this ADR when precision or recall is unacceptable, the service SLO changes, a metric contract changes, or enough history exists to evaluate seasonal/ML baselines.

## Evidence

- [Mandate 07a evidence summary](./MANDATE-07a-evidence.md)
- [Detection rule specification](../aiops_detection_rules_specs.md)
- [Mandate 07 implementation guide](../MANDATE-07_Guide.md)
- [Detector output/schema PR #137](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/137)
- [Detector implementation PR #208](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208)

## Sign-off

GitHub approval on the ADR pull request is the auditable signature. Do not change `Status` to `Accepted` until the required human approval exists.

| Role | Name/team | Decision | Date | Evidence |
| --- | --- | --- | --- | --- |
| Decision owner | AIO01 Tech Lead | Pending | — | PR approval required |
| Implementation reviewer | AIO01 | Pending | — | PR approval required |
| Runtime witness for 07b | AIO01 + CDO | Not required for 07a; pending for 07b | — | TF4AIO-72 runtime evidence |
