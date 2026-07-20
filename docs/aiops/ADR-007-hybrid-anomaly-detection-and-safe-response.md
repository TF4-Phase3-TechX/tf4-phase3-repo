# ADR-007: Hybrid anomaly detection, evidence-weighted RCA and safe response

- Original decision date: 2026-07-17
- Revised after design review: 2026-07-20
- Status: **Accepted for Mandate 7a design and implementation scope**
- Live activation status: **Not approved; Mandate 7b evidence is still required**

## Recorded signatures

This table is the signature record. Approval is not inferred from a pull-request review.

| Name | Role | Decision | Date | Scope |
|---|---|---|---|---|
| Dinh Danh Nam | AIO1 Tech Lead and decision owner | Accepted | 2026-07-17 | 7a detector architecture, implementation boundary and safe-response policy |
| _Name required_ | CDO deployment owner | Pending | — | In-cluster activation, RBAC, rollback and SLO verification |
| _Name required_ | On-call/SRE owner | Pending | — | Alert routing, escalation ownership and controlled incident drill |

The pending rows are deliberate. No person is recorded as an approver until that person explicitly signs this table or an attached named approval record.

## Context

TF4 exports metrics, logs and traces, but incident discovery still depends on a human watching dashboards. Mandate 7a requires executable detector/baseline code, analysis of at least three important signals, an initial end-to-end response design and a signed decision record. It does not authorize production incident injection or autonomous remediation.

The 2026-07-20 review identified four weaknesses in the first revision:

1. the LLM metric was assigned to a hard-coded `product-reviews` owner;
2. Isolation Forest was fitted but had no explicit decision contribution;
3. the spike-oriented gate did not identify a gradual drain before an absolute floor;
4. EWMA and normalization seeds were not configurable or supported by a reproducible sensitivity artifact.

This revision closes those design/implementation gaps while retaining the team's existing detector, evidence, RCA, incident lifecycle and guarded-remediation work.

## Decision

Adopt a lightweight, auditable hybrid detector:

1. **Per-service primary telemetry.** Prometheus is the required detection source. Latency and request-error signals keep an independent rolling history per service. Every `app_llm_*` emitter must attach low-cardinality `service.name` and `llm.operation` attributes; Prometheus preserves `service_name`, and the worker creates one decision per returned service series. Configuration may describe expected callers for missing-coverage reporting, but it cannot assign an incident to a different service.
2. **Two anomaly paths.** An acute path requires the absolute safety floor plus either a meaningful ratio shift or corroborating z-score/EWMA evidence. A gradual path uses a recent linear trend, minimum current-to-baseline ratio and monotonic consistency, and may fire before the absolute floor. This is how the design handles slow symptoms such as increasing latency/error rate caused by memory pressure or queue growth; it does not claim to identify the physical cause from one metric.
3. **Robust baseline with explicit trade-off.** Median/MAD filtering removes isolated historical spikes before mean/pstdev scoring. This reduces masking by one noisy sample and does not assume a Gaussian distribution. It can also exclude the beginning of a long incident, so the gradual path uses the unfiltered recent sequence and the design requires replay calibration.
4. **Isolation Forest is confidence evidence, not an alert gate.** It remains useful as a non-linear outlier indicator and preserves the team's BARO-lite experiment. Its configurable contribution is capped in decision confidence. It cannot create an incident by itself because the current production history is not sufficiently labelled to justify an opaque firing boundary.
5. **All detector seeds are runtime configuration.** MAD bands, ratio/z/EWMA thresholds, EWMA alpha, trend settings, Isolation Forest contamination and confidence contributions are environment-backed settings and explicit Helm values. Changing them requires a reviewed calibration artifact.
6. **Sustained decisions and lifecycle control.** A breach must persist for two polls by default. Incident upsert and cooldown suppress duplicate notification. Recovery requires consecutive fully covered healthy polls; missing/warming telemetry never counts as healthy recovery.
7. **Evidence before mutation.** OpenSearch logs and Jaeger traces enrich the decision. New incidents expose exact queries, values, coverage, scores, RCA candidates, confidence, runbook and recommended action. Missing secondary evidence is recorded, not silently treated as healthy.
8. **Bounded response.** The default is dry-run. The only automatic mutation shape is an allowlisted rollback after explicit, unexpired per-incident approval, separate Helm/RBAC enablement, rollout verification and SLO verification. Failure restores the captured original pod template and escalates. LLM output cannot authorize an action, and the detector never changes flagd.

## Initial signal analysis

These are design seeds, not measured production normal ranges.

| Signal | Scope and ownership | Acute rule | Gradual rule | Response |
|---|---|---|---|---|
| p95 server-span latency | `frontend`, `checkout`, `product-reviews`, `llm`; one history per service | Current p95 at or above 1,000 ms and ratio ≥1.5, or z-score ≥3 with EWMA score ≥1 | Six-point fitted rise ≥25%, at least 75% positive steps, current value ≥1.2× robust long-window mean | Investigate dependency/deployment evidence; rollback remains approval-gated |
| Request error rate | Same monitored critical services; one history per service | At least 20 requests in five minutes, current rate ≥5%, and the acute adaptive rule | Same multi-window trend rule; can alert before 5% when degradation is consistent | Correlate failed traces/logs and escalate to the service owner |
| LLM/provider error rate | Every `app_llm_*` series grouped by its emitted `service_name`; no global owner | At least five calls in five minutes, current rate ≥5%, and the acute adaptive rule | Same multi-window trend rule per emitting caller | Check provider/configuration/fallback, then escalate to that caller's owner |

The LLM query is grouped and joined `on(service_name)`. A future `shopping-copilot` instrumented with the same contract therefore produces a `shopping-copilot` incident rather than a `product-reviews` incident. An unlabeled LLM series is rejected as `unattributed` coverage degradation and cannot create a wrongly owned incident.

## Seed values and justification

| Setting | 7a seed | Design intent and limitation |
|---|---:|---|
| Lookback / Prometheus range step | 30 minutes / 60 seconds | Provides a small recent history without claiming a seasonal production model |
| Poll / sustain | 45 seconds / 2 polls | Bounds alert spam while keeping nominal confirmation near 90 seconds |
| Median/MAD tolerance | `max(6×MAD, 50% of median)` | Removes extreme masking samples while retaining ordinary relative variation; must be checked on labelled long incidents |
| Ratio / z-score | 1.5 / 3 | Requires a material change or a conventional high standardized deviation; neither value is claimed optimal |
| EWMA alpha | 0.35 | Gives recent observations meaningful weight without making one point dominate; sensitivity checks also run 0.2 and 0.5 |
| EWMA residual gate | 1.0 after `max(3×spread, 25% expected, 1)` normalization | Requires residual evidence while protecting flat/near-zero series from division instability |
| Trend window | 6 points | Approximately six minutes at the current range step; short enough to lead the floor but long enough to test consistency |
| Trend gates | rise 25%, current ratio 1.2, positive-step consistency 75% | Separates monotonic degradation from a single jump and oscillating noise |
| Isolation Forest | contamination 0.15, confidence weight 0.05 | Supporting evidence only; never a firing condition until labelled production calibration justifies a stronger role |

The reproducible [detector seed sensitivity report](./evidence/DETECTOR_SEED_SENSITIVITY.md) evaluates acute, stable-high, oscillating-noise, masking-noise and gradual-drift fixtures, plus a 27-combination parameter grid. It demonstrates the behavior and trade-off of the seed. It explicitly does **not** establish production precision/recall or optimality.

## End-to-end control flow

```text
Prometheus labelled series / OpenSearch logs / Jaeger traces
  -> per-service rolling history and coverage state
  -> acute-floor path OR consistent gradual-drift path
  -> sustained decision
  -> evidence bundle + confidence + service-scoped RCA candidate
  -> bounded incident store and structured audit log
  -> Prometheus incident counter
  -> Alertmanager -> Slack/email on-call route
  -> no approved safe action? escalate with runbook
  -> approved allowlisted rollback? dry-run or gated execution
  -> rollout + p95 + checkout/storefront error-rate verification
  -> resolve, or restore original template and escalate
```

The detector identifies **where the measured degradation is emitted** and offers investigation evidence. It does not claim that a rising queue, memory leak, deployment or provider is the root cause until correlated evidence confirms it.

## Alternatives considered

- **Static thresholds only:** simpler, but misses consistent degradation before the floor and behaves poorly across services with different normal levels.
- **Median/MAD plus spike detection only:** robust to isolated noise, but insufficient for memory-drain/queue-growth symptoms; retained only as the acute path.
- **Isolation Forest as the firing gate:** rejected because the current data does not justify contamination or decision-boundary calibration and on-call explanation would be weak.
- **Full learned multivariate model:** rejected as the primary gate because TF4 lacks representative labelled production history.
- **One global LLM owner:** rejected because it creates incorrect ownership as soon as another service calls an LLM.
- **Autonomous remediation from an RCA score:** rejected because correlation is not authorization and a wrong rollback can deepen an outage.

## Consequences and limitations

- The gradual path improves lead time for monotonic degradation, but direct queue-depth or memory metrics still need their own validated telemetry contracts before the detector may name those physical symptoms.
- Short trend windows can be sensitive during coordinated load ramps. Sustain, consistency and replay calibration are therefore mandatory.
- Median/MAD filtering resists isolated masking noise but can remove early long-incident points from the long baseline; the recent trend intentionally uses the unfiltered sequence.
- Minimum request/call gates reduce low-denominator error alerts and can delay detection on very low-traffic services.
- Isolation Forest affects confidence only. Its seed is not presented as a learned production parameter.
- In-memory incident state is bounded and inexpensive, but restart loses API history; structured audit events remain in OpenSearch.
- Offline RCAEval-v2 results demonstrate deterministic service localization, not TF4 live causal correctness.

## Evidence and activation gates

| Evidence/gate | Status |
|---|---|
| Unified implementation | [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281); must be conflict-free and merged before 7a closure |
| Service-aware LLM attribution | Implemented with emitter labels, grouped PromQL and a two-caller worker test |
| Acute/noise/gradual detector tests | Implemented; exact passing count must be taken from the final PR head CI |
| Seed sensitivity | [Report](./evidence/DETECTOR_SEED_SENSITIVITY.md) and [machine-readable grid](./evidence/detector-seed-sensitivity.json) |
| RCAEval-v2 60-case offline benchmark | Top-1 0.7667, Top-3 0.9333, MRR 0.8644; [report](./evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md) |
| Live TF4 normal/incident calibration | Pending Mandate 7b; required before claiming production accuracy |
| Alert delivery and controlled incident drill | Pending Mandate 7b |
| Live remediation | Disabled; requires named CDO/on-call signatures and a controlled drill |

## Sign-off boundary

The AIO1 owner accepts the 7a architecture, implementation scope and non-autonomous safety boundary. This signature does not approve production activation, incident injection or live remediation. The two pending runtime approvers must sign by name after reviewing the final merged implementation and controlled evidence.
