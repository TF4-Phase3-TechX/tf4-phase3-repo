# ADR-026: Evidence-based cross-service root-cause attribution

- Status: **Implemented for Mandate 26 / TF4AIO-90 (reviewer verdict pending)**
- Date: 2026-07-27
- Jira: [TF4AIO-90](https://aio1-xbrain.atlassian.net/browse/TF4AIO-90)
- Related: Mandate 15 (detection replay), Mandate 22 (closed-loop mitigation), ADR-007

## Context

When an incident cascades across services, operators currently see multiple red
downstream symptoms. Mandate 26 requires a deterministic, evidence-based ranking
that selects **one suspected root service** and explains the choice from
trace, topology, temporal, and anomaly evidence — without retargeting Mandate 22
remediation and without touching flagd.

## Decision

Implement a pure, deterministic RCA engine shared by:

1. an external offline replay CLI (`benchmark/rca_replay.py`) for mentor-style
   scenarios and graded hidden files;
2. the AIOps worker, which enriches incidents when two or more distinct canonical
   services are affected (or recent episode members remain in the analysis window).

### Edge direction

All graph APIs use **caller → callee**. Failure impact propagates in the reverse
direction. Methods are named `callees`, `callers`, `reachable_*`, `has_call_path`
to avoid ambiguous “upstream/downstream” wording.

### Static versus dynamic topology

- Static TechX edges are verified from application clients (frontend APIs,
  checkout dependencies, shipping→quote, product-reviews→catalog/LLM boundary).
- Trace-discovered edges are scoped to the analysis window, carry provenance,
  and never permanently mutate the static graph.
- Scenario fixtures may replace the static graph for unseen topologies.

### Candidate universe

```
anomalous services
∪ services on failed trace paths
∪ graph dependencies that can explain the affected cluster
```

A service is **not** excluded merely because it has no local anomalous `Decision`
(trace-only root).

Recently recovered services with a recorded episode onset are also retained.
Candidate/resource truncation preserves anomalous, recovered, and failed-trace
services before deterministic alphabetical fallback candidates.

### Scoring

Four inspectable features with availability-aware normalization:

| Feature | Seed weight | Role |
|---|---:|---|
| `trace_origin_support` | 0.35 | Root-like vs victim-like span evidence |
| `causal_coverage` | 0.30 | Fraction of affected services explained via call paths |
| `temporal_consistency` | 0.20 | Pairwise onset ordering within tolerance |
| `local_anomaly_support` | 0.15 | Detector confidence corroboration (max per service) |

Missing evidence removes that feature from the denominator (not scored as zero).
Bounded penalties apply for dependency-victim contradictions and disconnected
parallel anomalies. Seed weights are design defaults, not production-calibrated
coefficients.

`base_score` and the named penalty map are serialized per candidate so the final
score can be reproduced. A tie or margin below the configured attribution margin
abstains instead of turning alphabetical order into a causal decision.

### Correlation / noise

An anomalous service may be classified `unexplained_parallel_anomaly` when it is
not part of the selected root’s explained cascade. It is reported, not silently
discarded, and must not win Root@1 when the cascade is supported.

### Abstention

Statuses: `attributed` | `multiple_independent_clusters` | `insufficient_evidence`.
Independent multi-cluster faults without trace-supported single-cascade evidence
abstain rather than invent a global root.

An independent-cluster abstention does not relabel one cluster as correlated
noise. A disconnected anomaly is classified as noise only when relevant trace
coverage is present; missing trace evidence leaves it unresolved.

### External input and trace hardening

- Jaeger trace IDs and span IDs are deduplicated before evidence aggregation.
- Normalized and Jaeger parsing skip malformed spans with explicit errors rather
  than aborting the whole case.
- Both trace formats enforce the configured trace/span caps.
- Explicit boolean error fields are parsed semantically (`"false"` is false).
- Malformed/unbounded service identifiers are replaced by a stable, distinct,
  bounded digest identity before they enter Markdown, logs, or candidate output.
- Namespace and deployment-suffix stripping require explicit opt-in so different
  environments are not silently merged.

### End-to-end replay mode

`end_to_end_series` uses each signal's `series` array of
`{"timestamp": <ISO-8601>, "value": <finite number>}` records plus an
`incident_start_index`. Series across services must be timestamp-aligned. The
runner replays the production `Detector` sequentially and derives first breach
and anomaly timestamps; labels remain isolated in the evaluator.

### Episode state

`RCAEpisodeTracker` is process-local. Recovered roots remain candidates until the
analysis window expires. Restart loses state (documented limitation).

### Remediation boundary

RCA is **informational only**:

- `Incident.affected_service` remains the detector-owned service;
- runbook, recommended action, and remediation target are unchanged;
- root-targeted mitigation requires a separate CDO-approved policy change.

### Observability and caps

Prometheus: `aiops_rca_duration_seconds`, `aiops_rca_candidates_total`,
`aiops_rca_traces_processed_total`, `aiops_rca_spans_processed_total`,
`aiops_rca_skipped_total{reason}`, `aiops_rca_attribution_total{status}`.

Timeouts and max services/traces/spans are env-configured and fail closed at
startup when invalid. RCA failure/timeout never blocks incident creation.

## Alternatives considered

1. **Metric-only BARO-lite ranking** — already used offline for RCAEval; does not
   encode call-path or victim-like trace evidence for live cross-service claims.
2. **LLM free-form RCA** — rejected; non-deterministic and policy-unsafe.
3. **Full research BARO/TORAI reproduction** — out of scope for the mandate floor.
4. **Retarget remediation to suspected root** — explicitly forbidden by Mandate 26
   safety boundary until a separate policy/catalog change.

## Failure modes and uncertainty

- Incomplete or sampled traces can miss the true root.
- Missing graph edges are not proof of independence.
- Seed weights are not calibrated on production labeled cascades.
- Small labeled suite proves mechanism, not production accuracy.
- Clock skew and async messaging remain approximate (tolerance-based).
- Episode memory is lost on process restart.

## Implementation notes

The implementation includes explicit LLM boundary naming
(`external-llm-provider`), a legacy `signals` projection, eligibility by
distinct canonical services or a multi-service failed trace, and deterministic
contribution rounding.

## Consequences

- Mentors can inject external JSONL scenarios/traces without code changes.
- Operators see ranked candidates and an informational suspected root on multi-
  service incidents.
- Mandate 15/22 behavior is preserved; flagd is untouched.
