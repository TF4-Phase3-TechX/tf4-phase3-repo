# MANDATE-07a Mentor Brief: AIOps Detection Design and Initial Implementation

> Tài liệu tổng hợp để mentor và các team review một lần: mandate yêu cầu gì,
> team đã làm gì, feedback đã được xử lý ra sao, evidence nằm ở đâu, task thuộc
> về ai và runtime work nào thuộc 7b thay vì 7a.

## 1. Executive Summary

| Nội dung | Kết luận hiện tại |
|---|---|
| Mandate | AIOps Detection — Design and Initial Implementation |
| Canonical Jira | [TF4AIO-71](https://aio1-xbrain.atlassian.net/browse/TF4AIO-71) |
| Primary telemetry | Prometheus metrics |
| Supporting evidence | OpenSearch logs and Jaeger traces |
| Signals | Service p95 latency, request error rate, LLM/provider error rate |
| Detector | Robust baseline + acute gate + gradual-drift gate |
| RCA | Evidence-weighted deterministic candidate ranking |
| Decision record | [ADR-007](../../aiops/ADR-007-hybrid-anomaly-detection-and-safe-response.md) |
| Status | Done for 7a design/initial-implementation scope |
| Verdict | Ready for mentor re-review; live acceptance remains 7b/15 |

The team delivered executable detector/baseline code, analysis for the three
signal families, per-service ownership, incident/RCA evidence, an initial
end-to-end response design, configurable parameters, reproducible sensitivity
and production-informed seed calibration.

Mandate 7a does not claim live alert delivery, controlled incident injection,
general production precision/recall/MTTD or autonomous remediation.

## 2. What Mandate 7a Required

| Requirement | Operational meaning |
|---|---|
| Detector and baseline code | Real implementation, not only diagrams or PromQL ideas |
| At least three important signals | Explain why selected, definition of normal, anomaly condition and method |
| Initial end-to-end design | Detection through evidence/RCA, alert/escalation and guarded automation |
| Parameter rationale | Seeds and trade-offs must be documented and reproducible |
| Signed ADR | Decision owner and human reviewers explicitly accept the design scope |
| Honest scope boundary | Runtime alerting, drills and measured live quality remain in 7b |

## 3. What the Team Implemented

### 3.1 Per-service and namespace-scoped telemetry

- Every Prometheus query is scoped to `k8s_namespace_name`.
- Latency and request-error state are independent per service.
- LLM callers emit `service.name` and `llm.operation`; Prometheus preserves
  `service_name`.
- Missing/unlabelled LLM series is coverage degradation, not an incident
  assigned to a guessed owner.

### 3.2 Hybrid detector

The detector has two paths:

1. **Acute degradation:** absolute safety floor plus material ratio shift or
   corroborating z-score/EWMA evidence.
2. **Gradual degradation:** recent trend, positive-step consistency,
   current-to-baseline ratio and minimum SLO proximity.

Median/MAD filtering protects the long baseline from isolated masking spikes.
The gradual path uses the unfiltered recent sequence so a slowly increasing
memory/queue-style symptom is not reduced to “spikes only.”

Isolation Forest remains a bounded confidence/audit contribution and cannot
fire an incident by itself.

### 3.3 Evidence, RCA and response boundary

- Prometheus is the required firing source.
- OpenSearch and Jaeger enrich the incident with supporting evidence.
- Incident output includes service, signal, values/query, coverage, confidence,
  severity, RCA candidates, runbook and recommended action.
- Correlation is not presented as proven physical cause.
- Default response is dry-run/escalation. Detection confidence cannot authorize
  an unbounded mutation.

Key code:

- [`detection.py`](../../../techx-corp-platform/src/aiops/app/detection.py)
- [`worker.py`](../../../techx-corp-platform/src/aiops/app/worker.py)
- [`telemetry.py`](../../../techx-corp-platform/src/aiops/app/telemetry.py)
- [`models.py`](../../../techx-corp-platform/src/aiops/app/models.py)
- [`summary.py`](../../../techx-corp-platform/src/aiops/app/summary.py)
- [`runbooks.yaml`](../../../techx-corp-platform/src/aiops/runbooks.yaml)

## 4. Signal Analysis

| Signal | Why selected | Normal baseline | Anomaly method | Initial response |
|---|---|---|---|---|
| Per-service p95 latency | Direct customer-visible symptom of slow dependencies, queueing or resource pressure | Robust recent history for that service; `1000ms` is a safety floor, not the learned baseline | Acute floor + ratio/z/EWMA or gradual trend/consistency/SLO proximity | Correlate traces/logs/deployments and route to emitting service owner |
| Per-service request error rate | Direct availability/error-budget consumption | Robust recent server-span error history with minimum denominator | `5%` floor plus adaptive evidence, or consistent gradual rise | Correlate failed traces/logs and use service-error runbook |
| Per-caller LLM/provider error rate | AI feature can fail while general service metrics remain healthy | Robust recent history for each emitted `service_name`, with minimum call count | `5%` floor plus adaptive evidence, or per-caller gradual rise | Investigate provider/config/fallback and escalate to the caller owner |

## 5. Review Feedback and Resolution

| Feedback from 20/07 review | Resolution |
|---|---|
| LLM owner was hard-coded to `product-reviews` | Query groups/joins by emitted `service_name`; decisions and state are per caller. Unlabelled data is `unattributed` coverage degradation |
| Isolation Forest was fitted but had no explicit role | Configurable contribution is capped at `0.05` confidence and recorded for audit; IF cannot fire an incident |
| Spike-focused logic did not cover memory/queue slow degradation | Added trend window, relative rise, consistency, baseline ratio and 70% SLO-proximity gate |
| EWMA `0.35` and other seeds lacked justification | Moved to runtime config, documented intent/limitations, tested alternative seeds and replayed 81 parameter combinations |
| Median/MAD may remove long-incident evidence | Trade-off documented; long baseline is filtered while recent gradual sequence remains unfiltered |

## 6. Calibration and Benchmark Results

### 6.1 Production-informed detector seed

- 12 namespace-scoped Prometheus signal windows.
- Six anomalous and six normal windows.
- Selected seed: `6 TP / 0 FP / 6 TN / 0 FN`.
- At 60% SLO proximity, one false positive remained.
- At 80%, one incident signal was missed.
- The selected 70% seed avoided both on this small dataset.

This result justifies the initial seed; it is not a claim of general production
precision/recall or optimality.

### 6.2 RCAEval-v2

| Metric | Result |
|---|---:|
| Cases | `60` |
| Top-1 accuracy | `0.7667` |
| Top-3 accuracy | `0.9333` |
| MRR | `0.8644` |

RCAEval demonstrates deterministic service localization on its offline dataset.
It does not prove TF4 live causal correctness.

## 7. Parameter Intent and Trade-offs

| Parameter | Seed | Intent / limitation |
|---|---:|---|
| Lookback / step | 30m / 60s | Recent history without claiming seasonal modelling |
| PromQL rate window | 5m | Smooth scrape jitter while retaining useful lead time |
| Ratio / z-score | 1.5 / 3 | Material relative or standardized deviation; not claimed optimal |
| EWMA alpha | 0.35 | Give recent samples weight without one sample dominating; sensitivity also tests 0.2 and 0.5 |
| Trend window | 6 points | Detect consistent short-horizon degradation |
| Trend SLO proximity | 70% | Avoid harmless low-level ramps while allowing early warning |
| Isolation Forest contamination / weight | 0.15 / 0.05 | Supporting evidence only, never sole gate |
| Minimum request / LLM calls | 20 / 5 per 5m | Avoid unstable percentages at tiny denominators |

## 8. Task Ownership

| Jira | Work | Owner | Evidence/output |
|---|---|---|---|
| `TF4AIO-71` | Canonical 7a submission, design/initial implementation closure | Trần Đình Thông | Jira closure, reviewed implementation and evidence package |
| `TF4AIO-73` | Detector delivery/output contract | Thành Tâm | Structured detector output and delivery contract |
| `TF4AIO-74` | Detector and incident summary implementation | Huỳnh Xuân Hậu | Rule-based detector/incident-summary foundation |
| `TF4AIO-75` | Telemetry, detection rules and runbook integration | Cái Xuân Hòa | Prometheus/OpenSearch/Jaeger contract and rule/runbook mapping |
| `TF4AIO-78` | Detector unit/integration tests | Nguyễn Trần Huy Vũ | Acute, noise, masking, stable-busy, ownership and drift tests |
| Integration/ADR work | Unified implementation, feedback fixes, calibration and safe-response boundary | Đinh Danh Nam | PR #281 author/integration and ADR decision ownership |
| `TF4AIO-72/76/77` | Live deployment, alerting and measured E2E quality | 7b follow-up owners | Explicitly not required for 7a closure |

## 9. Mentor Evidence Map

| Evidence | Purpose |
|---|---|
| [AIOps README](../../aiops/README.md) | Canonical runtime/design overview |
| [ADR-007](../../aiops/ADR-007-hybrid-anomaly-detection-and-safe-response.md) | Decision, alternatives, trade-offs and signatures |
| [Detection-rule specification](../../aio01/aiops_detection_rules_specs.md) | Signal/rule design |
| [Seed sensitivity report](../../aiops/evidence/DETECTOR_SEED_SENSITIVITY.md) | Acute/noise/masking/drift behavior and alternative seeds |
| [Production-informed calibration](../../aiops/evidence/PRODUCTION_INFORMED_CALIBRATION.md) | 81 combinations over 12 labelled windows |
| [Raw labelled windows](../../aiops/evidence/tf4-prometheus-labelled-windows-20260721.json) | Replay inputs and provenance |
| [Machine-readable calibration](../../aiops/evidence/production-informed-calibration.json) | Selected seed output |
| [RCAEval-v2 report](../../aiops/evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md) | Offline RCA benchmark |
| [RCAEval-v2 result](../../aiops/evidence/rcaeval-v2-baro-lite-results.json) | Machine-readable benchmark output |
| [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281) | Canonical implementation and human reviews |
| [PR #458](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/458) | Explicit full-name signatures |

## 10. End-to-End Target Flow

```text
Prometheus metrics + OpenSearch logs + Jaeger traces
    -> per-service baseline and coverage
    -> acute gate OR gradual-drift gate
    -> sustained incident decision
    -> evidence + confidence + RCA candidates
    -> incident summary + audit + incident metric
    -> Alertmanager/on-call route
    -> no authorized action: runbook escalation
    -> separately authorized bounded action: execute
    -> verify readiness and SLO
    -> recover, or restore original state and escalate
```

## 11. Claim Boundary

Supported for 7a:

- executable detector and baseline;
- three-signal analysis;
- service-aware ownership;
- acute and gradual detection paths;
- parameter rationale and reproducible seed evidence;
- initial end-to-end response design;
- named ADR signatures.

Deferred to 7b/15:

- live Alertmanager/Slack delivery;
- controlled labelled incident drill;
- general production precision/recall/MTTD;
- production-stability acceptance.

Deferred to Mandate 22:

- autonomous production remediation;
- live successful mitigation and forced-wrong rollback evidence.

## 12. Suggested Mentor Submission

```text
MANDATE-07a is ready for mentor re-review. The package contains executable
detector/baseline code, explicit analysis for latency/error/LLM signals,
service-aware ownership, acute and slow-drift paths, reproducible seed
sensitivity, production-informed calibration, offline RCA benchmarking and a
signed ADR. Live alert delivery and measured production quality are explicitly
tracked under 7b/15 rather than being overstated as 7a evidence.
```

## 13. Mentor Sign-Off

**Mentor name:** ______________________________________

**Decision:** `ACCEPT` / `RE-RUN REQUIRED`

**Date/time:** ______________________________________

**Comments:**

```text

```
