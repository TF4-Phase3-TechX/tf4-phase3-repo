# ADR-007: Hybrid anomaly detection, evidence-weighted RCA and safe response

- Date: 2026-07-17
- Status: **Accepted for Mandate 7a design and implementation scope**
- Decision owner: **Dinh Danh Nam, AIO1 Tech Lead**
- Owner sign-off: **Accepted — 2026-07-17**
- Runtime activation approvers: CDO deployment owner and on-call/SRE owner
- Live-evidence status: pending Mandate 7b controlled drill

## Context

TF4 already exports metrics, logs and traces, but incident discovery still depends on a human watching dashboards. Mandate 7a requires real detector and baseline code, analysis of at least three important metrics, and a signed decision record. It does not require a production injection or live precision/recall claim; those belong to Mandate 7b.

The design must stay lightweight, tolerate missing secondary telemetry, avoid alert spam, preserve the mentor-owned flagd incident mechanism, and never let an inferred root cause directly authorize a production mutation.

## Decision

Adopt a hybrid, auditable detector rather than a single opaque model:

1. Prometheus is the required detection source. Each `service × signal` has its own rolling 30-minute baseline and absolute safety floor.
2. Ratio, z-score and EWMA residual gates must agree with the absolute floor. Isolation Forest is retained as supporting evidence, not the sole firing condition.
3. A breach must persist for two polls (45 seconds per poll by default). Incident upsert and a 10-minute cooldown suppress duplicate notifications.
4. OpenSearch logs and Jaeger traces enrich evidence and confidence. An unreachable source is recorded as `unavailable`, never as a healthy empty result.
5. TORAI-lite combines available metric/log/trace/deployment/AI evidence using declared weights and renormalizes when a source is missing. BARO-lite ranks likely services from baseline-versus-incident metric deviation. Both names mean research-inspired subsets, not paper reproductions.
6. New incidents expose structured evidence, RCA candidates, confidence, a runbook and a recommended action. A severity-labelled Prometheus event counter feeds the existing Alertmanager Slack/email route.
7. Automatic action is allowed only for a bounded, allowlisted rollback runbook after per-incident human approval. Dry-run is the default. A live action requires a separate Helm RBAC gate, rollout verification and SLO verification; failure restores the original pod template and escalates.
8. LLM output cannot select or execute an action. The detector never changes or disables flagd.

## Initial metric analysis

These ranges are the 7a design baselines used to seed the implementation. They are hypotheses to be recalibrated from a labelled normal window in 7b; they are not presented as live production measurements.

| Signal and scope | Why it matters | Initial normal range | Anomaly rule | Method |
|---|---|---|---|---|
| p95 span latency for `frontend`, `checkout`, `product-reviews`, `llm` | Direct user-visible degradation and dependency slowdown | 200–800 ms; service-specific rolling mean remains primary | Current p95 ≥1,000 ms **and** ≥1.5× baseline, z-score ≥3, or EWMA residual score ≥1; sustained two polls. Severity becomes critical-equivalent at ≥2,000 ms | PromQL histogram quantile + ratio/z-score/EWMA; Isolation Forest evidence |
| Error rate for the same critical services | Measures failed requests and error-budget burn before customers report | 0–2% in a healthy window | Current rate ≥5% **and** ≥1.5× baseline, z-score ≥3, or EWMA residual score ≥1; sustained two polls. Severity becomes critical-equivalent at ≥10% | Error calls / all calls from OTel span metrics + rolling statistical baseline |
| LLM/provider error rate for `product-reviews` and `llm` | AI-path provider failure can silently degrade review assistance while the storefront remains up | 0–2%; isolated provider failures may occur without forming an incident | Error rate ≥5% or at least three scoped timeout/rate-limit/error logs; sustained two polls. ≥25% is critical-equivalent | Application counters + OpenSearch correlation + TORAI-lite evidence score |

The detector currently queries `traces_span_metrics_duration_milliseconds_bucket`, `traces_span_metrics_calls_total`, `app_llm_calls_total`, and `app_llm_errors_total`. Query windows are five minutes inside the 30-minute lookback. Thresholds are configurable so 7b calibration can change values without rewriting the algorithm.

## End-to-end control flow

```text
Prometheus / OpenSearch / Jaeger
  -> per-service rolling baseline
  -> sustained anomaly decision
  -> evidence bundle + BARO/TORAI-lite candidates
  -> bounded incident store and audit log
  -> Prometheus incident counter
  -> Alertmanager -> Slack/email on-call notification
  -> no approved auto-action? escalate with runbook
  -> approved allowlisted action? dry-run or gated rollback
  -> rollout + p95 + checkout/storefront error-rate verification
  -> resolve, or restore original template and escalate
```

## Alternatives considered

- Static thresholds only: simple but too sensitive to expected load shifts; retained only as safety floors.
- Full BARO/TORAI reproduction: rejected for 7a because it adds research and operational complexity not justified by current data and deadline. The lite implementations preserve explainable ideas and state their limits.
- Fully learned multivariate model: rejected as the primary gate because TF4 lacks a sufficiently representative labelled production history, and opaque firing would make on-call tuning harder.
- Direct webhook calls from the worker: rejected for the MVP. Prometheus/Alertmanager already provides grouping, retry, routing and secret ownership.
- Autonomous remediation from an RCA score: rejected. Correlation is not authorization, and a wrong rollback can deepen an outage.

## Consequences and trade-offs

- Absolute floors plus adaptive evidence reduce noise, but a slow drift that never crosses a floor may be missed.
- Two-poll sustain and cooldown reduce spam at the cost of additional detection delay.
- Missing-source renormalization preserves degraded operation, but confidence must expose which sources were absent.
- In-memory incidents keep the MVP inexpensive, but pod restart loses API history; structured stdout remains available in OpenSearch.
- Offline RCAEval-v2 results demonstrate deterministic service localization, not TF4 live precision/recall or causal correctness.

## Evidence and activation gates

| Evidence/gate | Status |
|---|---|
| Unified implementation and review | [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281) |
| Unit/integration tests | 20 passing on 2026-07-17 |
| RCAEval-v2 60-case benchmark | Top-1 0.7667, Top-3 0.9333, MRR 0.8644; [report](evidence/RCAEVAL_V2_BARO_LITE_BENCHMARK.md) |
| Read-only observability adapters and status probe | Implemented; shared production access to Prometheus/OpenSearch/Jaeger verified on 2026-07-17; live AIOps component probe remains pending 7b deployment |
| Alertmanager notification rule | Implemented; live delivery evidence pending 7b |
| Live E2E injection, precision, recall and lead time | Pending Mandate 7b (due 2026-07-25) |
| Live remediation | Disabled; requires reviewed GitOps values, CDO/on-call approval and controlled drill |

## Sign-off boundary

The owner accepts the detection architecture and 7a implementation scope above. This signature does **not** approve production deployment, incident injection, or live remediation. Those actions require the named runtime approvers and separate 7b evidence.
