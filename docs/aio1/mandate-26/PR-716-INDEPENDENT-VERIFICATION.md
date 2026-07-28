# PR 716 — Independent Principal/Security Verification

**Scope:** TF4AIO-90 / Mandate 26  
**Implementation contract:** `IMPLEMENTATION-PLAN.md`  
**Original PR head reviewed:** `0828e8847dcd53798ef4baddbd32383423849c3f`  
**Review method:** source and execution-path verification; PR prose, prior test
claims, generated reports, and commit messages were not treated as proof.

## Verdict

**Changes Requested on the original PR head.** The implementation covered most
major components, but it was not contract-complete and contained correctness,
reliability, input-hardening, and test-oracle defects. The findings below were
fixed on the PR branch. A named reviewer verdict remains intentionally pending
until the project pytest environment reruns the full regression suite.

## Confirmed findings and resolutions

### F1 — Caller symptoms received causal credit in the wrong direction

- **Severity:** High
- **File/function:** `app/rca_engine.py`, `RCAEngine._score_candidate`
- **Execution path:** topology feature → path coverage → candidate ranking
- **Root cause:** coverage accepted both `affected -> candidate` and
  `candidate -> affected`. In a caller→callee graph, the second direction rewards
  a caller symptom for calling the actual failing callee.
- **Impact:** a downstream/caller service could tie or outrank the real root.
- **Reproduction:** graph `caller-symptom -> callee-root`, equal anomaly onset and
  confidence; inspect both candidates' `causal_coverage`.
- **Fix/test:** causal coverage now uses only affected callers that can reach the
  candidate. Added `test_causal_coverage_does_not_reward_wrong_edge_direction`.

### F2 — Candidate cap discarded priority candidates alphabetically

- **Severity:** High
- **File/function:** `app/rca_engine.py`, `RCAEngine.analyze`
- **Execution path:** candidate union → resource cap → ranking
- **Root cause:** code constructed `priority + rest`, converted it to a set, then
  sorted and truncated the complete set. That erased the priority ordering.
- **Impact:** an anomalous or trace-supported root with a later service name could
  disappear from the result.
- **Reproduction:** configure `max_services=2` with non-anomalous `a-context` and
  anomalous `y-victim`, `z-root`.
- **Fix/test:** anomalous, recovered, and failed-trace services are retained before
  fallback candidates. Added `test_candidate_cap_retains_anomalous_priority_services`.

### F3 — Missing evidence was manufactured as neutral/negative evidence

- **Severity:** High
- **File/function:** `app/rca_engine.py`, `RCAEngine._score_candidate`
- **Execution path:** availability-aware feature normalization
- **Root cause:** a trace-only root with no local Decision received an available
  anomaly score of zero; missing temporal pairs received an available synthetic
  score; unseen services inherited an available zero topology score merely
  because the global static graph was non-empty.
- **Impact:** trace-only/unseen roots were systematically diluted, contrary to the
  contract's missing-evidence rule.
- **Reproduction:** score a failed-trace service with no `RCAObservation` and
  inspect `local_anomaly_support`.
- **Fix/test:** missing candidate-specific signals are unavailable and removed from
  the denominator. Existing trace-only test was strengthened to assert this.

### F4 — Duplicate traces inflated causal evidence

- **Severity:** High
- **File/function:** `app/trace_graph.py`, `parse_jaeger_traces`
- **Execution path:** per-service Jaeger queries → merged raw traces → origin score
- **Root cause:** duplicate trace IDs only emitted a warning. The per-trace span
  index was reset, so the same spans were appended and scored repeatedly.
- **Impact:** query fan-out could change Root@1 and confidence without any new
  evidence.
- **Reproduction:** parse and score `[trace]` versus `[trace, trace]`.
- **Fix/test:** global `(trace_id, span_id)` deduplication; partial duplicate trace
  copies may add only genuinely new spans. Added duplicate-evidence invariance
  assertions.

### F5 — Malformed normalized error flags and spans were unsafe

- **Severity:** Medium
- **File/function:** `app/trace_graph.py`, `parse_normalized_spans`,
  `parse_jaeger_traces`
- **Execution path:** external trace fixture/runtime Jaeger response → parser
- **Root cause:** `bool("false")` evaluated to true; malformed numeric timestamps
  raised and aborted a case; a string parent ID was split into characters;
  normalized input ignored trace/span caps.
- **Impact:** false error evidence, avoidable execution failure, and cap bypass.
- **Reproduction:** `error: "false"`, `start_us: "not-a-number"`, or normalized
  spans exceeding configured caps.
- **Fix/test:** semantic boolean parsing, fail-soft per-span numeric validation,
  scalar-parent normalization, and caps for both formats.

### F6 — A client timeout was credited to the caller as root-like evidence

- **Severity:** High
- **File/function:** `app/trace_graph.py`, `analyze_trace_origins`
- **Execution path:** failed client span with `peer.service` and missing server span
- **Root cause:** the caller received positive root support when its dependency
  timed out.
- **Impact:** exactly the downstream-symptom selection prohibited by Mandate 26.
- **Reproduction:** one failed checkout client span calling payment with no payment
  server span.
- **Fix/test:** caller receives victim-like evidence; the named missing callee gets
  bounded inferred support with an explicit “server span unavailable” fact.

### F7 — Episode state was overwritten by decision ordering

- **Severity:** High
- **File/function:** `app/worker.py`, `poll_once`;
  `app/rca_episode.py`, `RCAEpisodeTracker.observe`
- **Execution path:** multiple detector Decisions for one service → episode update
- **Root cause:** the tracker was updated once per Decision. A later healthy signal
  reset `currently_anomalous` after an earlier anomalous signal. Breach onset was
  also recorded only after sustained anomaly.
- **Impact:** stale/incorrect temporal ordering and recovered roots disappearing.
- **Reproduction:** latency anomalous followed by error-rate healthy for the same
  service in one poll.
- **Fix/test:** aggregate service state before one tracker update; record first
  breach independently; add recovery/expiry tests.

### F8 — Recovered unseen roots were fetched but not passed to the engine

- **Severity:** High
- **File/function:** `app/worker.py`, `_run_cross_service_rca`
- **Execution path:** recent episode members → trace query → engine input
- **Root cause:** recent services were added only to the trace-query list. No
  observation/candidate context was created for them.
- **Impact:** an unseen root that recovered before downstream symptoms could not
  remain eligible when absent from the sampled trace/static graph.
- **Reproduction:** recover `novel-root`, then analyze current checkout/frontend
  anomalies with no trace for the root.
- **Fix/test:** recovered episode observations with recorded onsets are included in
  engine input and candidate construction.

### F9 — Single-service observations could never activate trace-discovered RCA

- **Severity:** High
- **File/function:** `app/worker.py`, `poll_once`, `_run_cross_service_rca`
- **Execution path:** one locally anomalous service → eligibility check
- **Root cause:** worker rejected the case before reading traces, despite the
  contract allowing a multi-service failed trace to reveal an unmonitored root.
- **Impact:** trace-only cross-service roots were supported offline but unreachable
  in the equivalent runtime path.
- **Reproduction:** checkout is the only anomalous Decision; its failed client span
  names payment.
- **Fix/test:** perform the already-required bounded trace lookup, then run RCA only
  if observations/episode state or failed trace evidence spans at least two
  services. Empty single-service traces still return `rca_skipped=single_service`.

### F10 — Independent clusters were falsely counted as noise rejection

- **Severity:** Medium
- **File/function:** `app/rca_engine.py`, attribution/classification pass;
  `benchmark/rca_replay.py`, evaluator
- **Execution path:** multi-cluster abstention → candidate classification → noise
  metrics
- **Root cause:** after abstaining, non-top independent roots retained
  `unexplained_parallel_anomaly`.
- **Impact:** false correlation claims and inflated/incorrect noise metrics.
- **Reproduction:** committed `multiple-independent-clusters` case previously
  predicted `ad` as noise although labels contained no noise.
- **Fix/test:** abstained clusters remain root candidates. Aggregate noise metrics
  now include micro precision/recall/F1 and false-rejection rate.

### F11 — RCA result could remain stale in an active incident

- **Severity:** Medium
- **File/function:** `app/store.py`, `IncidentStore.upsert`
- **Execution path:** attributed incident → later RCA abstention/skip → dedup upsert
- **Root cause:** root/result fields were copied only when the new value was
  non-null.
- **Impact:** operators could see an obsolete root after current evidence no longer
  supported it.
- **Reproduction:** upsert an attributed incident, then the same dedup key with
  null RCA fields.
- **Fix/test:** latest point-in-time RCA replaces or clears both fields; result is
  now typed as `RCAResult`.

### F12 — Replay contract accepted invalid input and falsely advertised E2E mode

- **Severity:** High
- **File/function:** `benchmark/rca_schema.py`, `validate_case`;
  `benchmark/rca_replay.py`, `run_case`
- **Execution path:** external JSONL → validation → engine
- **Root cause:** `end_to_end_series` was accepted but treated as a snapshot;
  timestamps could be missing/out of order; alias-equivalent duplicate services,
  confidence outside `[0,1]`, malformed topology confidence, and resource
  overages were not rejected; missing `observed_at` was replaced with wall-clock
  time.
- **Impact:** nondeterminism, silent truncation, label mismatch, and a CLI contract
  that was only partially implemented.
- **Reproduction:** use `mode=end_to_end_series`, duplicate
  `frontend-web`/`frontend`, or onset later than observation.
- **Fix/test:** strict resource/timestamp/identity/label/topology validation,
  deterministic snapshot timestamps, normalized evaluator labels, output I/O
  exit code 2, and a real timestamp-aligned Detector replay path.

### F13 — Service identity normalization crossed a trust boundary

- **Severity:** Medium (security/data-integrity)
- **File/function:** `app/service_identity.py`, `normalize_service_name`
- **Execution path:** external scenario/telemetry service name → logs, Markdown,
  graph, candidate output
- **Root cause:** arbitrary unsafe/very long names were preserved; namespace and
  deployment suffixes were stripped implicitly.
- **Impact:** Markdown injection/resource amplification and accidental merging of
  distinct environment services.
- **Reproduction:** service `<script>alert(1)</script>`, `prod.checkout`, and
  `checkout-v2`.
- **Fix/test:** unsafe identities become bounded stable digest identities;
  namespace/suffix stripping is explicit opt-in; similarly named unknown services
  remain distinct.

## Contract status after fixes

| Contract area | Status | Evidence |
|---|---|---|
| External JSONL, Jaeger v1, normalized spans | Fully implemented | replay/schema/trace parser |
| Optional labels and label isolation | Fully implemented | split engine/evaluator tests |
| Ranking, evidence, explanation, abstention | Fully implemented | engine models and replay |
| Trace-only and unseen roots | Fully implemented | focused scenarios/tests |
| Noise invariance and independent clusters | Fully implemented | replay metrics/tests |
| Availability-aware four-signal scoring | Fully implemented | per-candidate contributions, base score, penalties |
| Runtime aggregation, timeout/failure isolation | Fully implemented | worker path/tests |
| Recovered root episode behavior | Fully implemented, process-local | episode/worker tests |
| Remediation/flagd boundary | Fully implemented | affected-service assertions; no flagd path changed |
| `end_to_end_series` | Implemented with timestamp-aligned poll snapshots | schema and Detector replay path |
| Machine report and documentation | Implemented; report regenerated after code commit | report, ADR, evidence index |
| Named reviewer approval | Pending by design | `REVIEWER-VERDICT.md` |
| Live production run | Not required by Directive 26 | external replay is the required mentor verification gate |

## Verification executed in this review environment

- Python compile of `app`, `benchmark`, and `tests`: passed.
- Mentor-style committed replay: exit `0`; 8/8 labeled cases passed;
  Root@1 = 1.0, Root@3 = 1.0, MRR = 1.0; noise precision/recall/F1 = 1.0;
  false noise-rejection rate = 0.
- Direct executable regression assertions: trace deduplication, false-string error
  parsing, malformed-span isolation, causal direction, identity hardening,
  episode breach/recovery/expiry, stale store clearing, and invalid config.
- `git diff --check`: passed.
- Full pytest was not executable in this sandbox because the available Python
  runtime lacks pytest/numpy/sklearn/prometheus-client and outbound package
  installation is blocked. This is why the named reviewer verdict remains
  pending; CI or a project virtual environment must run the documented full suite.
