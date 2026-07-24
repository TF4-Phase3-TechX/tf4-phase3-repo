# ADR-007: Hybrid anomaly detection, evidence-weighted RCA and safe response

- Original decision date: 2026-07-17
- Revised after design review and production-informed replay: 2026-07-21
- Status: **Accepted for Mandate 7a design and implementation scope**
- Live activation status: **Not approved; Mandate 7b evidence is still required**

## Recorded signatures

This table is the signature record. Approval is not inferred from a pull-request review.

| Name | Role | Decision | Date | Scope |
|---|---|---|---|---|
| Đinh Danh Nam (`c0mmie-b0msh3ll`) | AIO1 Tech Lead and decision owner | Accepted | 2026-07-17 | 7a detector architecture, implementation boundary and safe-response policy |
| Cái Xuân Hòa (`XUanhoa04`) | AIOps technical reviewer | Approved | 2026-07-21 | 7a detector/baseline design, service-scoped ownership, calibration evidence and safe-response boundary; [review](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281#pullrequestreview-4745190607) |
| Trần Đình Thông (`trandinhthong7`) | AIO1 PM and delivery reviewer | Approved | 2026-07-21 | 7a scope, evidence completeness and merge readiness; [review](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281#pullrequestreview-4745710714) |
| _Name required_ | CDO deployment owner | Pending for 7b | — | 7b only: in-cluster activation, RBAC, rollback and SLO verification |
| _Name required_ | On-call/SRE owner | Pending for 7b | — | 7b only: alert routing, escalation ownership and controlled incident drill |

The named records above close the 7a design/initial-implementation decision. The two pending rows are deliberate 7b runtime-activation gates, not missing 7a signatures. No person is recorded for those roles until that person explicitly signs this table or an attached named approval record.

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

1. **Per-service, namespace-scoped primary telemetry.** Prometheus is the required detection source. Every runtime query is constrained by `k8s_namespace_name` so stale or accidental deployments in another namespace cannot contaminate the baseline. Latency and request-error signals keep an independent rolling history per service. Every `app_llm_*` emitter must attach low-cardinality `service.name` and `llm.operation` attributes; Prometheus preserves `service_name`, and the worker creates one decision per returned service series. Configuration may describe expected callers for missing-coverage reporting, but it cannot assign an incident to a different service.
2. **Two anomaly paths.** An acute path requires the absolute safety floor plus either a meaningful ratio shift or corroborating z-score/EWMA evidence. A gradual path uses a recent linear trend, minimum current-to-baseline ratio, monotonic consistency and an early-warning boundary at 70% of the signal's SLO floor. It may therefore fire before the absolute floor without treating a harmless low-level load ramp as an incident. This is how the design handles slow symptoms such as increasing latency/error rate caused by memory pressure or queue growth; it does not claim to identify the physical cause from one metric.
3. **Robust baseline with explicit trade-off.** Median/MAD filtering removes isolated historical spikes before mean/pstdev scoring. This reduces masking by one noisy sample and does not assume a Gaussian distribution. It can also exclude the beginning of a long incident, so the gradual path uses the unfiltered recent sequence and the design requires replay calibration.
4. **Isolation Forest is confidence evidence, not an alert gate.** It remains useful as a non-linear outlier indicator and preserves the team's BARO-lite experiment. Its configurable contribution is capped in decision confidence. It cannot create an incident by itself because the current production history is not sufficiently labelled to justify an opaque firing boundary.
5. **All detector seeds are runtime configuration.** MAD bands, ratio/z/EWMA thresholds, EWMA alpha, trend settings, Isolation Forest contamination and confidence contributions are environment-backed settings and explicit Helm values. Changing them requires a reviewed calibration artifact.
6. **Sustained decisions, impact and lifecycle control.** Detection remains independent from impact classification. For a service with an approved success SLO, the worker computes request-weighted error-budget burn over exact 5-minute and 30-minute windows. Both windows must exceed the same configured boundary before impact is raised (`2x` warning, `10x` critical), so a brief spike cannot claim sustained critical customer impact. Incident upsert and cooldown suppress duplicate notification. Recovery requires consecutive fully covered healthy polls; missing/warming telemetry never counts as healthy recovery.
7. **Evidence before mutation.** OpenSearch logs and Jaeger traces enrich the decision. New incidents expose exact queries, values, coverage, scores, RCA candidates, confidence, runbook and recommended action. Missing secondary evidence is recorded, not silently treated as healthy.
8. **Bounded response.** The default is dry-run. The only automatic mutation shape is an allowlisted rollback after explicit, unexpired per-incident approval, separate Helm/RBAC enablement, rollout verification and SLO verification. Failure restores the captured original pod template and escalates. LLM output cannot authorize an action, and the detector never changes flagd.

## Initial signal analysis

The table is deliberately explicit about the four items required by Mandate 7a for each signal: why it was selected, what the initial normal baseline means, what is anomalous, and which method is used. The ranges are configurable **design seeds**, not measured claims about TF4 production. The baseline is learned independently for each `service × signal`; a stable busy service can therefore remain normal even when its raw value is high.

| Signal and ownership | Why selected | Initial definition of normal | What is anomalous | Method and response |
|---|---|---|---|---|
| p95 server-span latency for `frontend`, `checkout`, `product-reviews` and `llm`; one history per service | It is the clearest user-visible symptom and is directly tied to the storefront p95 SLO. It also exposes slow dependency, queue and resource-pressure symptoms without pretending to identify their physical cause. | The robust mean/spread of that service's previous 30-minute, 60-second-step history after Median/MAD masking-noise removal. A stable busy window is normal when the relative/z/EWMA and gradual gates remain false; 1,000 ms is a safety floor, not the learned baseline. | Acute: current p95 ≥1,000 ms **and** ratio ≥1.5, or z-score ≥3 with EWMA score ≥1. Gradual: six-point fitted rise ≥25%, ≥75% positive steps, current ≥1.2× the robust long-window mean and current p95 ≥70% of the SLO floor. | Per-service Median/MAD baseline + ratio/z-score/EWMA acute gate + unfiltered short-window trend. Correlate deployment/dependency evidence; rollback remains separately approval-gated. |
| Request error rate for the same critical services; one history per service | Failures consume the availability error budget and can be severe even when latency has not risen. The signal is calculated only from server spans so client/internal spans do not distort ownership. | The robust mean/spread of the service's own preceding 30-minute error-rate history. A window is eligible only with ≥20 requests in five minutes; low-volume ratios are unavailable rather than normal. A stable high-load period with no deviation remains normal. | Acute: current rate ≥5% plus the same adaptive ratio/z/EWMA rule. Gradual: the same trend rule can fire before 5% when a consistent rise is consuming the budget. | The anomaly gate detects change. Separately, approved success SLOs (`frontend`/`cart` 99.5%, `checkout` 99.0%) convert the request-weighted error ratio into 5m/30m budget burn. Both windows must cross 2x/10x to claim warning/critical impact. |
| LLM/provider error rate for every `app_llm_*` caller grouped by emitted `service_name` | Provider timeouts/rate limits directly remove the AI feature while ordinary service request metrics may remain healthy. Caller attribution is required so a future service is not assigned to `product-reviews`. | The robust mean/spread of each caller's own preceding 30-minute LLM error-rate history. A window is eligible only with ≥5 calls in five minutes. Missing or unlabeled series are coverage failures, never healthy samples and never assigned to a configured global owner. | Acute: current rate ≥5% plus the adaptive rule. Gradual: the same per-caller trend rule. A current rate ≥25% raises severity to high but does not alter the anomaly gate. | Label-preserving PromQL + per-caller robust baseline and two-path detector. Logs/TORAI-lite enrich confidence only; check provider/configuration/fallback and escalate to that caller's owner. |

The LLM query is grouped and joined `on(service_name)`. A future `shopping-copilot` instrumented with the same contract therefore produces a `shopping-copilot` incident rather than a `product-reviews` incident. An unlabeled LLM series is rejected as `unattributed` coverage degradation and cannot create a wrongly owned incident.

## Seed values and justification

| Setting | 7a seed | Design intent and limitation |
|---|---:|---|
| Lookback / Prometheus range step | 30 minutes / 60 seconds | Provides a small recent history without claiming a seasonal production model |
| PromQL rate window | 5 minutes | Smooths scrape-level jitter while remaining short enough for the target MTTD; replay must quantify the actual lead-time trade-off |
| Poll / sustain | 45 seconds / 2 polls | Bounds alert spam while keeping nominal confirmation near 90 seconds |
| Minimum adaptive / Isolation Forest history | 4 / 8 points | Avoids unstable statistics on a thin baseline; the service reports `warming` and still permits a severe floor breach. IF waits longer because fitting an unsupervised model on fewer points would be misleading |
| Latency / request-error / LLM safety floor | 1,000 ms / 5% / 5% | Latency reuses the storefront p95 objective; the percentage floors mark material initial degradation. They are guardrails combined with adaptive evidence, not definitions of normal |
| Median/MAD tolerance | `max(6×MAD, 50% of median)` | Removes extreme masking samples while retaining ordinary relative variation; must be checked on labelled long incidents |
| Ratio / z-score | 1.5 / 3 | Requires a material change or a conventional high standardized deviation; neither value is claimed optimal |
| EWMA alpha | 0.35 | Gives recent observations meaningful weight without making one point dominate; sensitivity checks also run 0.2 and 0.5 |
| EWMA residual gate | 1.0 after `max(3×spread, 25% expected, 1)` normalization | Requires residual evidence while protecting flat/near-zero series from division instability |
| Trend window | 6 points | Approximately six minutes at the current range step; short enough to lead the floor but long enough to test consistency |
| Trend gates | rise 25%, current/baseline ratio 1.2, positive-step consistency 75%, current/SLO ratio 70% | Separates monotonic degradation from a single jump, oscillating noise and harmless ramp-up far below the SLO. In the 12-window replay, 60% retained one false positive, 80% missed one incident signal, and 70% produced neither; this remains a provisional seed pending broader 7b validation |
| Error-budget burn windows | 5 minutes / 30 minutes | The short window reacts to current customer failures; the long window requires persistence and suppresses critical escalation for a single short spike. These are configurable initial operating seeds, not a claim of canonical SRE thresholds. |
| Error-budget burn impact | 2x warning / 10x critical, both windows | A 1% error budget burns at 10x when the observed error rate is 10%. Requiring both windows is intentionally conservative. Mandate 7b must recalibrate the seeds against labelled TF4 traffic and accepted paging load. |
| Isolation Forest | contamination 0.15, confidence weight 0.05 | Supporting evidence only; never a firing condition until labelled production calibration justifies a stronger role |
| Isolation Forest random seed | 7 | Makes the 7a audit and tests reproducible; it is not a learned production parameter |

### Confidence, severity and evidence-weight justification

Confidence is an operator-prioritisation score, **not a calibrated incident probability** and not an authorization token. All values below are runtime/Helm configuration so the production replay can replace them without changing code.

| Setting | 7a seed | Design intent and limitation |
|---|---:|---|
| Latency / request-error / LLM confidence base | 0.45 / 0.50 / 0.45 | A primary metric breach starts below the 0.75 remediation boundary. Error rate receives a slightly higher triage prior because it directly consumes availability budget. These priors do not claim empirical probability. |
| z-score / EWMA / gradual-trend contribution | 0.10 / 0.15 / 0.10 | Independent explainable corroboration can raise priority. EWMA is slightly stronger because it incorporates recent sequence; no single contribution authorizes action. |
| Isolation Forest contribution / confidence cap | 0.05 / 0.95 | Keeps opaque unsupervised evidence subordinate and prevents a displayed score of 1.0 from implying certainty. |
| TORAI-lite source weights | metric 0.35, trace 0.25, log 0.20, deployment 0.10, AI 0.10 | Primary metric evidence leads; trace/log correlation supports it; deployment/AI hints remain weaker because correlation is not cause. Missing sources are reported and available weights are renormalized. TORAI-lite changes confidence only, never the firing gate. |
| TORAI metric/log normalization | +50% relative span / three matching logs | Saturates bounded evidence without allowing an unbounded ratio or duplicated logs to dominate. These are replay-tunable seeds, not measured optima. |
| High severity | latency ≥2× safety floor; approved-SLO request errors require 5m and 30m burn ≥10x; LLM error rate ≥25% | Separates material customer impact from a medium anomaly. A request-error service without an approved SLO retains an explicitly labelled fixed-threshold fallback. Severity changes routing/priority, not whether an anomaly exists. |
| Denominator gates | 20 requests / 5 LLM calls per five minutes | Avoids unstable percentages from tiny denominators, accepting delayed detection for very low-traffic services. |
| Remediation confidence boundary | 0.75 | A defense-in-depth prerequisite in addition to named approval, allowlist, RBAC and verification. Live remediation remains disabled until 7b evidence and runtime signatures exist. |

The reproducible [detector seed sensitivity report](./evidence/DETECTOR_SEED_SENSITIVITY.md) evaluates acute, stable-high, oscillating-noise, masking-noise and gradual-drift fixtures. The separate [production-informed calibration report](./evidence/PRODUCTION_INFORMED_CALIBRATION.md) replays 81 parameter combinations over 12 namespace-scoped Prometheus signal windows. It demonstrates the behavior and trade-off of the seed. It explicitly does **not** establish general production precision/recall or optimality.

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
- Short trend windows can be sensitive during coordinated load ramps. The 70% SLO proximity guard, sustain, consistency and replay calibration reduce this risk but require broader 7b validation.
- Median/MAD filtering resists isolated masking noise but can remove early long-incident points from the long baseline; the recent trend intentionally uses the unfiltered sequence.
- Minimum request/call gates reduce low-denominator error alerts and can delay detection on very low-traffic services.
- Multi-window burn rate is an impact classifier, not a causal signal. The initial 5m/30m and 2x/10x seeds require labelled TF4 load/incident calibration; this change does not claim production-optimal paging precision.
- `product-reviews` and `llm` have no approved user-visible success SLO in the cited requirements, so the implementation deliberately reports a fixed-threshold fallback instead of inventing an error budget.
- Isolation Forest affects confidence only. Its seed is not presented as a learned production parameter.
- In-memory incident state is bounded and inexpensive, but restart loses API history; structured audit events remain in OpenSearch.
- Offline RCAEval-v2 results demonstrate deterministic service localization, not TF4 live causal correctness.

## Evidence and activation gates

| Evidence/gate | Status |
|---|---|
| Unified implementation | [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281); must be conflict-free and merged before 7a closure |
| Service-aware LLM attribution | Implemented with emitter labels, grouped PromQL and a two-caller worker test |
| Impact-aware request-error routing | Implemented with approved per-service SLOs, request-weighted 5m/30m PromQL, explicit fallback/unavailable states, incident summary evidence and multi-window tests |
| Acute/noise/gradual detector tests | Implemented; exact passing count must be taken from the final PR head CI |
| Seed sensitivity | [Report](./evidence/DETECTOR_SEED_SENSITIVITY.md) and [machine-readable grid](./evidence/detector-seed-sensitivity.json) |
| RCAEval-v2 60-case offline benchmark | Top-1 0.7667, Top-3 0.9333, MRR 0.8644; [report](./evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md) |
| TF4 production-informed normal/incident replay | Complete for 12 namespace-scoped latency/error signal windows (6 anomalous, 6 normal): seed result 6 TP / 0 FP / 6 TN / 0 FN. [Report](./evidence/PRODUCTION_INFORMED_CALIBRATION.md), [raw labelled windows](./evidence/tf4-prometheus-labelled-windows-20260721.json), and [machine-readable result](./evidence/production-informed-calibration.json). Labels come from committed load-test/postmortem evidence; independent validation, LLM windows and controlled drills remain 7b gates |
| Alert delivery and controlled incident drill | Pending Mandate 7b |
| Live remediation | Disabled; requires named CDO/on-call signatures and a controlled drill |

## Sign-off boundary

The AIO1 owner accepts the 7a architecture, implementation scope and non-autonomous safety boundary. This signature does not approve production activation, incident injection or live remediation. The two pending runtime approvers must sign by name after reviewing the final merged implementation and controlled evidence.
