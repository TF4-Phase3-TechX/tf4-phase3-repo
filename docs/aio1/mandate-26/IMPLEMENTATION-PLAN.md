# Mandate 26 Implementation Plan

## Evidence-Based Cross-Service Root-Cause Attribution

**Jira:** [TF4AIO-90](https://aio1-xbrain.atlassian.net/browse/TF4AIO-90)  
**Status of this document:** implementation handoff plan  
**Required implementation verdict before closure:** reviewer-approved  
**Primary safety boundary:** RCA is informational in Mandate 26 and must not retarget Mandate 22 remediation.

---

## 1. Objective

Implement a deterministic cross-service RCA capability that:

1. Accepts an externally supplied cross-service incident scenario and/or Jaeger trace without code changes.
2. Produces a ranked list of root-service candidates.
3. Selects one suspected root service when the input contains a supported cascade.
4. Explains the selection using inspectable trace, topology, temporal, and anomaly evidence.
5. Does not stop at a downstream symptom.
6. Does not treat a disconnected simultaneous anomaly as causal without evidence.
7. Works with service names and topologies not present in the committed labeled fixtures.
8. Preserves detector availability, runtime SLO, budget, flagd, and Mandate 22 safety policy.

The implementation must not claim perfect causality. It must distinguish:

- evidence supporting a candidate;
- evidence contradicting a candidate;
- missing evidence;
- an unexplained parallel anomaly;
- insufficient evidence to attribute a root safely.

---

## 2. Definition of Done

Mandate 26 is ready for reviewer approval only when all of the following are true:

- [ ] A standalone replay command accepts an external JSONL file.
- [ ] The input may contain raw Jaeger v1 traces or normalized spans.
- [ ] Ground-truth labels are optional.
- [ ] The engine never receives or reads ground-truth labels.
- [ ] An unlabeled scenario still emits a ranking, suspected root, evidence, and explanation.
- [ ] A labeled scenario additionally emits Root@1, Root@3, and reciprocal-rank evaluation.
- [ ] At least one cascade contains an actually anomalous disconnected noise service.
- [ ] Adding that noise service does not change the selected cascade root.
- [ ] At least one root is discovered from trace/topology even though it has no local anomalous `Decision`.
- [ ] At least one scenario uses service names/topology absent from the static TechX topology.
- [ ] Missing trace data is reported as unavailable and is not scored as healthy or as zero causal support.
- [ ] Multiple anomalous signals from one service do not count as multiple affected services.
- [ ] Runtime RCA failure or timeout does not block incident detection.
- [ ] `Incident.affected_service`, runbook selection, and remediation target remain unchanged.
- [ ] Existing Mandate 15 and Mandate 22 tests still pass.
- [ ] RCA runtime latency and trace/span processing caps are measured and documented.
- [ ] Machine-readable evidence records the input hash, Git revision, model version, config, limitations, and per-candidate contributions.
- [ ] ADR/design note documents the mechanism, trade-offs, failure modes, and uncertainty.
- [ ] A named reviewer reruns the command and records an explicit verdict.

---

## 3. Non-Goals and Safety Boundaries

The following are explicitly out of scope:

1. Retargeting automatic remediation to the selected root service.
2. Changing any flagd configuration, data, deployment, or behavior.
3. Allowing an LLM to choose a root or produce an unbounded free-form action.
4. Claiming that absence of a graph edge proves absence of causality.
5. Treating this small labeled suite as production-accuracy evidence.
6. Replacing the existing per-service detector.
7. Reproducing BARO, TORAI, or another research system in full.

Mandate 22 remediation must continue to operate only on the original detector-created incident and its pre-authorized target. Root-targeted mitigation requires a separate CDO-approved policy/action-catalog change.

---

## 4. Verified Repository Constraints

The implementation must account for these current contracts:

1. `Decision` has no onset timestamp. It currently contains anomaly state, service, confidence, severity, evidence, and local candidates.
2. The worker emits several decisions per service, such as latency, error rate, availability, and LLM error.
3. The worker currently creates incidents one decision at a time.
4. Jaeger traces are currently fetched after an incident object is created and are fetched per anomalous decision.
5. `Incident.rca_candidates` is currently `list[dict[str, Any]]`.
6. The incident summary expects each legacy candidate dictionary to contain a `signals` object.
7. Mandate 15 replay accepts schema version 1 and intentionally rejects version 2.
8. Default monitored services are narrower than the complete application topology.
9. The current RCAEval BARO-lite result is offline service localization and is not evidence of live cross-service causal correctness.

Consequences:

- Do not trigger cross-service RCA by checking only `len(anomalous_decisions)`.
- Aggregate by canonical service first.
- Do not restrict the candidate set to anomalous decisions.
- Do not modify the Mandate 15 schema parser.
- Keep a compatibility projection for `Incident.rca_candidates`.

---

## 5. Graph Semantics

### 5.1 Canonical edge direction

All graph APIs and serialized topology must use:

```text
caller -> callee
```

Example:

```text
frontend -> checkout -> payment
```

If payment fails, the failure-impact direction is the reverse:

```text
payment -> checkout -> frontend
```

Avoid ambiguous method names such as `upstream()` and `downstream()`.

Required graph methods:

```python
callees(service)
callers(service)
reachable_callees(service)
reachable_callers(service)
has_call_path(caller, callee)
affected_callers_explained_by(candidate, affected_services)
connected_components(services)
```

### 5.2 Static topology

Create a small verified static topology from application client configuration and source, not from Docker Compose `depends_on` alone.

Minimum verified application edges should include:

```python
TECHX_CALL_GRAPH = {
    "frontend": {
        "ad",
        "cart",
        "checkout",
        "currency",
        "product-catalog",
        "product-reviews",
        "recommendation",
        "shipping",
    },
    "checkout": {
        "cart",
        "currency",
        "email",
        "payment",
        "product-catalog",
        "shipping",
    },
    "product-reviews": {"product-catalog"},
    "shipping": {"quote"},
}
```

Before committing additional edges, verify them in service source/configuration. In particular, do not add these previously proposed invalid edges:

```text
payment -> currency
cart -> product-catalog
shipping -> currency
quote -> shipping
```

Model an external LLM/provider boundary separately from an internal service. Define and test the canonical mapping between current `llm` telemetry labels, `product-reviews`, and the external Bedrock dependency.

### 5.3 Cycles and dynamic topology

Do not assume the real graph is a DAG.

- Traversal must use a visited set.
- Depth must not be the primary root signal.
- If condensation is required, compute strongly connected components.
- Trace-discovered edges are scoped to the current analysis window.
- Dynamic edges must record provenance and confidence.
- Dynamic edges must not permanently mutate the static graph.
- Scenario topology overrides must be isolated to that replay case.

---

## 6. Service Identity Normalization

Add `app/service_identity.py`.

It must normalize names before graph construction, candidate aggregation, and scoring:

- whitespace and case;
- `service.name` versus `resource.service.name`;
- known aliases such as `frontend-web` versus `frontend`;
- namespace or deployment suffixes when explicitly configured;
- external provider identifiers;
- empty or unknown service names.

Do not silently merge arbitrary unknown names. Return both:

```python
canonical_service
original_service
normalization_reason
```

The replay must support a per-scenario alias map without modifying global aliases.

---

## 7. Data Models

Add typed models before implementing the engine.

Suggested contract:

```python
class SignalObservation(BaseModel):
    signal: str
    anomalous: bool
    breached: bool = False
    coverage_status: Literal["available", "warming", "unavailable"]
    confidence: float
    severity: str
    observed_at: datetime
    first_breached_at: datetime | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class RCAObservation(BaseModel):
    service: str
    original_service_names: list[str] = Field(default_factory=list)
    signals: list[SignalObservation] = Field(default_factory=list)
    first_breached_at: datetime | None = None
    first_anomalous_at: datetime | None = None


class RCAEvidenceFact(BaseModel):
    source: Literal["trace", "topology", "temporal", "anomaly"]
    fact: str
    support: float
    available: bool = True
    trace_id: str | None = None
    span_ids: list[str] = Field(default_factory=list)
    observed_at: datetime | None = None
    provenance: str | None = None


class RCASignalContribution(BaseModel):
    available: bool
    raw_value: float | None
    weight: float
    weighted_value: float | None
    reason: str


class RCACandidate(BaseModel):
    service: str
    score: float
    rank: int
    classification: Literal[
        "suspected_root",
        "root_candidate",
        "explained_downstream_symptom",
        "unexplained_parallel_anomaly",
        "insufficient_evidence",
    ]
    contributions: dict[str, RCASignalContribution]
    explained_affected_services: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    evidence: list[RCAEvidenceFact] = Field(default_factory=list)


class RCAResult(BaseModel):
    schema_version: int = 1
    model_version: str
    attribution_status: Literal[
        "attributed",
        "insufficient_evidence",
        "multiple_independent_clusters",
    ]
    suspected_root_service: str | None
    confidence: float
    score_margin: float | None
    explanation: str
    candidates: list[RCACandidate]
    unavailable_signals: list[str] = Field(default_factory=list)
    topology_provenance: list[str] = Field(default_factory=list)
    analysis_started_at: datetime
    analysis_ended_at: datetime
```

Extend `Incident` backward-compatibly:

```python
suspected_root_service: str | None = None
rca_result: RCAResult | None = None
```

Keep `rca_candidates` temporarily as a legacy dictionary projection. Its `signals` key must be generated from candidate contributions so the existing summary consumer remains valid.

---

## 8. Trace Normalization and Propagation Analysis

Add `app/trace_graph.py`.

### 8.1 Supported input

Support:

1. Raw Jaeger v1 trace objects containing `traceID`, `spans`, `processes`, tags, references, timestamps, and durations.
2. A normalized span format used by focused tests and simple mentor fixtures.

### 8.2 Required normalization

For every span, derive:

- trace ID;
- span ID;
- parent span IDs/references;
- canonical service;
- operation name;
- span kind when available;
- start and end timestamp;
- error status from supported OTel/Jaeger tag forms;
- peer/callee service when available;
- whether the span is server, client, internal, producer, or consumer;
- whether references are missing or ambiguous.

Handle:

- duplicate trace IDs returned by queries for multiple services;
- duplicate span IDs;
- orphan references;
- partial traces;
- missing process mappings;
- client timeouts with no server span;
- retry spans;
- async producer/consumer edges;
- clock skew within a configurable tolerance.

### 8.3 Root-like versus victim-like evidence

Trace scoring must not count all error spans in a service as origin evidence.

Root-like evidence includes:

- a local/server span failing before caller-side client failures;
- an error boundary in the candidate with no earlier failed callee explaining it;
- repeated traces showing the same service as the deepest supported failure boundary.

Victim-like evidence includes:

- only client spans failing while calling another service;
- a matching downstream server error that begins before the candidate's propagated error;
- cancellations or timeouts consistently explained by a failed callee.

Store trace/span identifiers and derived facts, not full sensitive trace payloads, in incidents and reports.

---

## 9. RCA Scoring

Add `app/rca_engine.py`.

### 9.1 Candidate universe

Candidates are the union of:

```text
services with anomalous observations
∪ services on failed trace paths
∪ graph dependencies capable of explaining the affected cluster
```

A service must not be excluded merely because it has no local anomaly.

### 9.2 Service-level aggregation

Aggregate all signals for one canonical service before cross-service scoring.

Do not double-count latency and error rate as two affected services. For local anomaly support, use a bounded aggregation such as the maximum supported confidence or another documented bounded rule.

### 9.3 Features

Use four inspectable feature families:

1. `trace_origin_support`
   - rewards a supported error origin;
   - penalizes dependency-victim evidence.
2. `causal_coverage`
   - rewards the fraction of affected services whose call paths can reach the candidate;
   - computes coverage only within the incident cluster, never over the global service count.
3. `temporal_consistency`
   - rewards candidate onset no later than the services it explains;
   - uses pairwise ordering and a tolerance rather than global min-max normalization.
4. `local_anomaly_support`
   - uses detector confidence/coverage as corroboration;
   - does not treat severity as proof of causality.

Suggested seed weights:

```text
trace_origin_support = 0.35
causal_coverage      = 0.30
temporal_consistency = 0.20
local_anomaly        = 0.15
```

These are deterministic seed values, not empirically proven production coefficients. The ADR and machine report must state that boundary.

### 9.4 Availability-aware normalization

For candidate `S`:

```text
base_score(S) =
    sum(weight_i * feature_i for available features)
    / sum(weight_i for available features)

score(S) =
    base_score(S)
    - contradiction_penalty(S)
    - likely_parallel_anomaly_penalty(S)
```

Rules:

- Missing evidence removes that feature from the denominator.
- Missing trace is not a trace score of zero.
- All contributions and penalties must be present in output.
- Configuration must validate nonnegative weights and a positive total.
- Penalties must be bounded.
- Sorting must be deterministic.
- Report the score margin between the first and second candidate.

### 9.5 Correlation handling

An anomalous service may be classified as `unexplained_parallel_anomaly` only when:

- it is not connected to the primary affected component in static or observed topology;
- it shares no causal trace path with the primary component;
- its temporal behavior does not support propagation;
- relevant topology/trace coverage is available.

When coverage is missing, explain the anomaly as unresolved rather than definitively ruling it out.

Ground-truth fields such as `correlated_noise_services` must be used only by the evaluator.

### 9.6 Attribution and abstention

For a supported cascade, select one suspected root.

For genuinely independent clusters or insufficient evidence, return an explicit status rather than inventing causality:

```text
attributed
multiple_independent_clusters
insufficient_evidence
```

The required floor scenarios must contain a supported cascade and therefore must produce one suspected root. Independent-fault negative cases are robustness tests, not substitutes for the floor cascade.

---

## 10. Replay Contract

Do not modify the Mandate 15 replay schema. Add:

```text
benchmark/rca_schema.py
benchmark/rca_replay.py
```

### 10.1 Top-level schema

Use a schema-specific identity:

```json
{
  "schema_name": "techx.aiops.rca",
  "schema_version": 1,
  "id": "external-case-01",
  "description": "External cross-service cascade",
  "mode": "attribution_snapshot",
  "observations": [],
  "traces": {
    "format": "jaeger-v1",
    "data": []
  },
  "topology": {
    "edge_direction": "caller_to_callee",
    "edges": []
  },
  "service_aliases": {},
  "labels": {
    "expected_root_service": "optional",
    "correlated_noise_services": []
  }
}
```

### 10.2 Replay modes

Implement:

1. `attribution_snapshot`
   - accepts already observed anomaly state/timestamps and traces;
   - isolates RCA from detector quality;
   - is the minimum required mentor path.
2. `end_to_end_series`
   - accepts aligned timestamped metric series;
   - replays the existing detector poll by poll;
   - derives first breach/anomaly time rather than accepting a ground-truth onset;
   - proves detector-to-RCA composition.

The first mode is required for the floor. The second mode is required before claiming full runtime equivalence.

### 10.3 Label isolation

The replay runner must create two objects:

```text
engine_input
evaluation_labels
```

Pass only `engine_input` to `RCAEngine.analyze()`.

Add a unit test that patches/captures the engine call and proves no expected-root or noise label is present.

### 10.4 Validation and resource limits

Validate:

- duplicate or missing case IDs;
- schema name/version;
- timestamp format and ordering;
- finite confidence/metric values;
- duplicate services/signals;
- topology edge direction;
- self-edges and unknown references;
- trace/span limits;
- file/case/service limits;
- label service names;
- empty input;
- supported trace formats.

Unknown service names must be accepted. Invalid structures must produce actionable per-case errors.

### 10.5 CLI behavior

The CLI must run from the repository root:

```powershell
python techx-corp-platform/src/aiops/benchmark/rca_replay.py `
  <external-scenarios.jsonl> `
  --output m26-rca-report.json `
  --force
```

Exit codes:

```text
0 = all parsed cases executed and all labeled acceptance cases passed
1 = an evaluated labeled case failed
2 = input/schema/execution error
```

Unlabeled cases must not fail merely because expected-root labels are absent.

---

## 11. Machine-Readable Report

The report must include:

```json
{
  "schema_name": "techx.aiops.rca.report",
  "schema_version": 1,
  "generated_at": "...",
  "git_revision": "...",
  "model_version": "...",
  "input_path": "...",
  "input_sha256": "...",
  "config": {},
  "aggregate": {},
  "cases": [],
  "errors": [],
  "limitations": []
}
```

Each case must contain:

- attribution status;
- selected root;
- complete ranking;
- per-signal contributions;
- supporting facts and contradictions;
- noise/unexplained classification;
- unavailable evidence;
- explanation;
- processing time;
- trace/span counts;
- evaluation only when labels exist.

Aggregate labeled metrics:

- Root@1;
- Root@3;
- MRR;
- noise precision;
- noise recall;
- noise F1;
- false noise-rejection rate;
- attribution coverage/abstention rate;
- p50 and p95 processing time;
- parsing/execution failures.

Do not publish accuracy claims without stating the labeled sample size and fixture limitations.

---

## 12. Runtime Integration

### 12.1 Worker pipeline

Refactor `poll_once()` into logical phases without changing the detector's decision logic:

```text
1. collect metric/log/availability telemetry
2. produce all Decision objects
3. aggregate Decision objects by canonical service
4. update episode/onset state
5. identify distinct affected services
6. fetch bounded traces concurrently
7. normalize and deduplicate traces
8. run bounded RCA
9. construct/enrich incidents
10. store, notify, and invoke existing remediation behavior
```

Cross-service RCA eligibility must use the number of distinct affected canonical services, not the number of anomalous decisions.

### 12.2 Episode state

Add a bounded in-process `RCAEpisodeTracker` initially:

- records first breach/anomaly timestamp by service;
- keeps recently affected services for a configurable analysis window;
- allows the root to remain a candidate if it recovers before downstream symptoms;
- expires state deterministically;
- has tests for recovery and expiry.

Document process-restart loss as a limitation unless state is persisted.

### 12.3 Trace collection

- Fetch relevant traces concurrently.
- Apply an RCA-specific timeout.
- Cap services, traces per service, total traces, and total spans.
- Deduplicate by trace ID before parsing.
- Prefer error-related trace queries when the Jaeger API supports them.
- Do not blindly increase the global Jaeger limit from 5 to 20.

### 12.4 Failure isolation

If RCA fails or exceeds its budget:

- continue creating the original incidents;
- keep the original local suspected-cause text;
- record an `rca_skipped` reason;
- do not block store, notification, or approved remediation.

### 12.5 Remediation boundary

RCA enrichment must not modify:

- `affected_service`;
- `incident_type`;
- `runbook_id`;
- `recommended_action`;
- remediation target;
- target lock/cooldown behavior.

Add an integration test proving that a downstream incident enriched with `suspected_root_service="payment"` still passes the original affected service to the existing remediation controller.

---

## 13. Configuration

Add and validate:

```text
AIOPS_RCA_ENABLED=true
AIOPS_RCA_MODEL_VERSION=m26-v1
AIOPS_RCA_ANALYSIS_WINDOW_SECONDS=180
AIOPS_RCA_TEMPORAL_TOLERANCE_SECONDS=45
AIOPS_RCA_TIMEOUT_SECONDS=2
AIOPS_RCA_MAX_SERVICES=32
AIOPS_RCA_MAX_TRACES=50
AIOPS_RCA_MAX_SPANS=5000
AIOPS_RCA_TRACE_WEIGHT=0.35
AIOPS_RCA_TOPOLOGY_WEIGHT=0.30
AIOPS_RCA_TEMPORAL_WEIGHT=0.20
AIOPS_RCA_ANOMALY_WEIGHT=0.15
AIOPS_RCA_CONTRADICTION_PENALTY=0.20
AIOPS_RCA_PARALLEL_ANOMALY_PENALTY=0.25
```

Validation:

- weights and penalties are finite and nonnegative;
- total feature weight is positive;
- penalties are at most 1;
- timeouts/windows/limits are positive;
- analysis window is not shorter than temporal tolerance;
- config errors fail at startup with a clear message.

These settings are normal application environment settings and must not be implemented through flagd.

---

## 14. Observability and SLO Proof

Add:

```text
aiops_rca_duration_seconds
aiops_rca_candidates_total
aiops_rca_traces_processed_total
aiops_rca_spans_processed_total
aiops_rca_skipped_total{reason}
aiops_rca_attribution_total{status}
```

The evidence report must document:

- replay p50/p95 RCA duration;
- maximum observed trace/span processing;
- runtime timeout behavior;
- detector behavior when Jaeger is unavailable;
- absence of additional infrastructure;
- any increase in telemetry requests per polling cycle.

The worker must maintain the existing poll loop even when RCA reaches its timeout.

---

## 15. Required Tests

### 15.1 Service identity

- canonical known aliases;
- preserve unknown service names;
- per-scenario alias isolation;
- no accidental merge of similarly named services.

### 15.2 Dependency graph

- caller/callee semantics;
- transitive paths;
- reverse affected-caller coverage;
- disconnected components;
- cycles/SCC;
- self-edge rejection;
- dynamic edge provenance;
- scenario override isolation;
- verified TechX topology edges and invalid-edge regression tests.

### 15.3 Trace parser

- raw Jaeger v1 process mapping;
- normalized spans;
- parent/child references;
- server versus client error;
- client timeout without server span;
- partial/orphan trace;
- retry;
- duplicate trace and span IDs;
- same-service internal spans;
- async producer/consumer edge;
- clock skew tolerance;
- service alias normalization.

### 15.4 RCA engine

- standard cascade root ranks first;
- root not locally anomalous;
- multiple signals from one service count once;
- equal onset times;
- missing onset;
- missing trace versus zero error traces;
- topology-only fallback;
- trace-only unseen topology;
- disconnected anomalous noise;
- incomplete graph does not produce an overconfident noise claim;
- downstream victim has dependency-failure penalty;
- input-order invariance;
- service-renaming metamorphic test;
- duplicate-trace invariance;
- adding noise does not change selected root;
- deterministic tie behavior;
- multiple independent clusters;
- insufficient evidence;
- candidate contribution sum matches final score.

### 15.5 Replay

- schema validation;
- labeled and unlabeled inputs;
- labels never passed to engine;
- Jaeger trace input;
- normalized trace input;
- unknown topology/service;
- file and resource limits;
- correct exit codes;
- stable machine-readable output;
- Root@1/Root@3/MRR;
- noise precision/recall/F1;
- input SHA and Git revision.

### 15.6 Worker integration

- two signals on one service do not trigger cross-service RCA;
- two distinct services do trigger RCA;
- traces fetched once per service and deduplicated;
- RCA timeout does not block incident creation;
- RCA exception does not block incident creation;
- legacy summary still renders;
- incident store round-trip preserves RCA result;
- remediation target remains the original affected service;
- recovered root remains in an active episode until expiry.

### 15.7 Regression and performance

- full `src/aiops/tests` suite;
- Mandate 15 replay tests;
- Mandate 22 mitigation/verification tests;
- replay p50/p95 performance;
- configured max trace/span enforcement.

---

## 16. Labeled Scenario Suite

Create:

```text
docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl
```

Minimum cases:

1. `payment-cascade-with-ad-noise`
   - payment is supported by failed traces;
   - checkout and frontend are downstream victims;
   - ad has a real simultaneous anomaly but no supported relation.
2. `product-catalog-multi-branch`
   - product-catalog explains cart/recommendation/frontend branches.
3. `external-provider-boundary`
   - explicitly defines whether the root candidate is the external provider or owning service boundary.
4. `trace-only-root`
   - root has no local anomalous decision.
5. `unseen-renamed-topology`
   - all service names are absent from static topology.
6. `missing-trace-topology-temporal-fallback`
   - trace source is unavailable, not empty.
7. `multiple-independent-clusters`
   - returns the correct non-attributed status.
8. `cycle-and-retry`
   - proves traversal termination and duplicate/retry resistance.

Every correlated-noise fixture must make the noise service actually anomalous. Do not mark a baseline-like series as noise and count it as a successful rejection.

Keep ground truth exclusively inside the `labels` object.

---

## 17. Documentation and Evidence Artifacts

Create:

```text
docs/aiops/ADR-026-rca-root-cause-attribution.md
docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl
docs/aio1/mandate-26/rca-replay-report-v1.json
docs/aio1/mandate-26/MANDATE-26-EVIDENCE-INDEX.md
docs/aio1/mandate-26/REVIEWER-VERDICT.md
```

ADR must cover:

- explicit edge direction;
- static versus trace topology;
- candidate universe;
- availability-aware score;
- correlation claim boundary;
- abstention;
- episode-state limitation;
- trace sampling and SLO caps;
- seed weights;
- alternatives;
- remediation non-integration.

Evidence index must contain:

- exact Git revision;
- exact command;
- input and output hashes;
- expected exit code;
- report links;
- test results;
- SLO measurement;
- known limitations;
- flagd non-interference statement;
- reviewer verdict link.

Reviewer verdict must record:

- reviewer full name;
- date/time;
- reviewed Git revision;
- exact rerun command;
- observed output hash;
- verdict: `Approved` or `Changes Requested`;
- remaining limitations and uncertainty.

Do not describe a generated replay report as deployment, runtime observation, or mentor acceptance.

---

## 18. Implementation Order

Execute in this order:

1. Freeze schema, edge direction, label isolation, and acceptance tests.
2. Add typed models and backward-compatible incident fields.
3. Implement service identity normalization.
4. Implement dependency graph with verified static edges.
5. Implement Jaeger/normalized trace parser.
6. Implement deterministic RCA engine and unit tests.
7. Implement external replay schema/CLI and evaluator.
8. Add labeled, noise, missing-data, and unseen scenarios.
9. Generate the first machine-readable report.
10. Refactor worker into two-phase aggregation/RCA flow.
11. Add timeout, caps, observability, and remediation-boundary tests.
12. Run full regression and performance tests.
13. Write ADR and evidence index.
14. Have a named reviewer rerun and record the verdict.

Do not start with worker integration. First prove the pure engine through the external replay contract.

---

## 19. Verification Commands

Run focused tests from `techx-corp-platform/src/aiops`:

```powershell
python -m pytest `
  tests/test_service_identity.py `
  tests/test_dependency_graph.py `
  tests/test_trace_graph.py `
  tests/test_rca_engine.py `
  tests/test_rca_replay.py `
  tests/test_worker.py `
  -v
```

Run the mentor-style replay from the repository root:

```powershell
python techx-corp-platform/src/aiops/benchmark/rca_replay.py `
  docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl `
  --output docs/aio1/mandate-26/rca-replay-report-v1.json `
  --force
```

Run an unlabeled hidden case:

```powershell
python techx-corp-platform/src/aiops/benchmark/rca_replay.py `
  <mentor-hidden-scenarios.jsonl> `
  --output m26-hidden-report.json `
  --force
```

Run the full AIOps regression suite:

```powershell
Set-Location techx-corp-platform/src/aiops
python -m pytest tests -v
```

Inspect the report and verify:

- one suspected root for supported cascades;
- evidence facts cite trace IDs/span IDs or graph paths;
- downstream victims are explained;
- noisy anomalies are not selected without being silently discarded;
- unavailable evidence is explicit;
- score contributions reproduce final scores;
- labels are absent from engine input/output reasoning;
- runtime/performance limitations are present.

---

## 20. Handoff Rules for the Implementing Agent

The implementing agent must:

1. Treat this document as the implementation contract unless repository evidence requires a correction.
2. Verify every static topology edge before committing it.
3. Preserve unrelated user changes in the worktree.
4. Avoid modifying Mandate 15 replay behavior.
5. Avoid touching flagd.
6. Avoid changing remediation targets or policy.
7. Implement and test the pure engine before runtime wiring.
8. Keep explanations deterministic and evidence-derived.
9. Record missing evidence rather than manufacturing confidence.
10. Report any deviation from this plan in the ADR and final handoff.

If time is constrained, complete the external trace-capable replay, pure RCA engine, label isolation, noise case, unseen case, machine report, and reviewer-ready documentation first. Runtime integration may not be claimed complete until its worker, timeout, regression, and remediation-boundary tests pass.

---

## 21. Estimate

A metric-only prototype may fit in 4–6 hours, but it does not satisfy this plan.

Expected effort for a review-ready implementation:

- models, graph, identity, trace parser: 0.5–1 day;
- RCA engine and tests: 0.5–1 day;
- replay schema, CLI, scenarios, report: 0.5–1 day;
- runtime integration, SLO controls, regression: 0.5–1 day;
- ADR, evidence, reviewer rerun: additional review time.

---

## 22. Implementation Hardening Notes (post-review)

These notes tighten the handoff without changing the mandate DoD:

1. **Package layout.** Keep pure RCA under `app/` so the worker and replay share one import path. Put schema/CLI only under `benchmark/`.
2. **Legacy candidate projection.** Always emit `rca_candidates[].signals` as a flat map of feature → weighted contribution so `IncidentSummaryGenerator` keeps working without edits beyond optional root display.
3. **Onset fallback.** When `first_breached_at` is absent, use `first_anomalous_at`, then `observed_at`. Never invent a timestamp.
4. **LLM boundary.** Canonical internal owner remains `product-reviews`. External provider candidate uses service name `external-llm-provider` (alias of telemetry label `llm` when configured). Topology edge: `product-reviews -> external-llm-provider`.
5. **Score reproducibility.** Round final scores to 6 decimal places. Ties break by ascending service name, then rank.
6. **Replay acceptance gate.** Labeled cascade cases require Root@1 match. Status-only cases (`multiple_independent_clusters`, `insufficient_evidence`) compare `attribution_status` only.
7. **Worker eligibility.** Cross-service RCA runs when `len(distinct_affected_canonical_services) >= 2` **or** traces show multi-service error paths among recent episode members. Single-service multi-signal never triggers solely by decision count.
8. **Performance budget.** Pure-engine analysis of the committed suite must finish under the configured timeout per case on a developer machine; document p50/p95 in the report.
9. **No flagd / no remediation retarget.** Grep-verify no flagd path is imported; remediation tests assert `affected_service` is the detector service.
10. **Plan deviation log.** Any deliberate deviation from sections 1–21 must appear in `ADR-026` §Deviations.

