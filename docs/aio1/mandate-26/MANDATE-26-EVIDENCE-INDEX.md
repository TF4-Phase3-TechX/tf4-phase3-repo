# Mandate 26 — Evidence Index

**Jira:** [TF4AIO-90](https://aio1-xbrain.atlassian.net/browse/TF4AIO-90)  
**Title:** Evidence-based cross-service root-cause attribution  
**Evidence level of this package:** implementation + offline replay (not mentor acceptance, not production deployment observation)

## One-command repro (repository root)

```powershell
py -3 techx-corp-platform/src/aiops/benchmark/rca_replay.py `
  docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl `
  --output docs/aio1/mandate-26/rca-replay-report-v1.json `
  --force
```

Expected exit code: **0**

## Artifacts

| Artifact | Path |
|---|---|
| Labeled scenarios | `docs/aio1/mandate-26/rca-labeled-scenarios-v1.jsonl` |
| Machine-readable report | `docs/aio1/mandate-26/rca-replay-report-v1.json` |
| ADR / design note | `docs/aiops/ADR-026-rca-root-cause-attribution.md` |
| Reviewer verdict | `docs/aio1/mandate-26/REVIEWER-VERDICT.md` |

## Exact hashes (regenerate after edits)

Run:

```powershell
py -3 -c "import hashlib, pathlib; p=pathlib.Path('docs/aio1/mandate-26');
for name in ['rca-labeled-scenarios-v1.jsonl','rca-replay-report-v1.json']:
  b=(p/name).read_bytes(); print(name, hashlib.sha256(b).hexdigest())"
git rev-parse HEAD
```

Values recorded by the independent verification rerun:

| Item | Value |
|---|---|
| Input SHA-256 | `c229b3c7343420fc2c4cf203dfaaef39891b3fef078ed09f32f26c3170fa9667` |
| Report SHA-256 | `1adec1b95a552612f718b74b9b9c7750d1db06e003f119074c89ed10fbc14ad0` |
| Reviewed code Git revision embedded in report | `f39697f9e426370f28ac59549c8eeb59211b93d3` |
| Model version | `m26-v1` |

The report embeds `git_revision`, `input_sha256`, and per-case rankings. The
embedded revision identifies the code and replay runner that produced the
results; the evidence-only packaging commit necessarily follows it. Between
that revision and the packaging commit, only this index and the generated
report change.

The report hash covers the exact committed UTF-8/LF bytes. Replay input hashes
canonicalize CRLF and LF text to LF, and `.gitattributes` enforces LF for the
Mandate 26 JSON/JSONL evidence so the recorded hashes are portable across
Windows and Unix checkouts.

## Aggregate results (committed suite)

From `rca-replay-report-v1.json`:

- cases: 8 labeled, 8 passed, 0 failed  
- Root@1: **1.0**  
- Root@3: **1.0**  
- MRR: **1.0**  
- noise precision / recall / F1: **1.0 / 1.0 / 1.0**
- false noise-rejection rate: **0.0**
- processing p50 / p95: **1.4395 / 3.4886 ms** (review workstation, pure engine)
- attribution coverage: 0.875 (one intentional multi-cluster abstention)

### Scenario coverage

| Case ID | Intent | Result |
|---|---|---|
| `payment-cascade-with-ad-noise` | cascade root + correlated noise | root=`payment`, noise=`ad` |
| `product-catalog-multi-branch` | multi-branch victims | root=`product-catalog` |
| `external-provider-boundary` | LLM external boundary | root=`external-llm-provider` |
| `trace-only-root` | root without local Decision | root=`payment` |
| `unseen-renamed-topology` | names absent from static TechX graph | root=`billing-core` |
| `missing-trace-topology-temporal-fallback` | Jaeger unavailable | root=`payment`, trace unavailable |
| `multiple-independent-clusters` | abstention | status=`multiple_independent_clusters` |
| `cycle-and-retry` | cycles + retries | root=`svc-b` |

## Tests

From `techx-corp-platform/src/aiops`:

```powershell
py -3 -m pytest `
  tests/test_service_identity.py `
  tests/test_dependency_graph.py `
  tests/test_trace_graph.py `
  tests/test_rca_engine.py `
  tests/test_rca_episode.py `
  tests/test_rca_replay.py `
  tests/test_worker_rca.py `
  tests/test_worker.py `
  tests/test_m15_replay.py `
  tests/test_m22_mitigation_replay.py `
  -v
```

Independent verification additionally ran the committed replay, the full AIOps
suite (**222 passed, 1 skipped**), focused regressions for trace-root candidate
caps and the end-to-end RCA timeout/latency metric, and `git diff --check`.
The named reviewer must still rerun the command before changing
`REVIEWER-VERDICT.md` from `Pending`.

## Safety / non-interference

- **flagd:** not imported or modified by M26 modules.  
- **Remediation:** `Incident.affected_service` remains the detector service; worker tests assert remediation targets stay on original services.  
- **Mandate 15 schema:** `benchmark/replay.py` schema v1 unchanged; M26 uses `schema_name=techx.aiops.rca`.  
- **SLO:** RCA has dedicated timeout/caps; failure skips enrichment only.

## Known limitations

1. Seed weights are not production-calibrated.  
2. Labeled suite is small — proves mechanism, not production causal accuracy.  
3. Missing graph edge ≠ proof of independence.  
4. Episode tracker is process-local (lost on restart).  
5. RCA is informational; root-targeted mitigation needs separate policy approval.

## Claim boundary

This evidence supports **implementation readiness and offline reproducibility**. It is **not**:

- deployment evidence;
- live multi-service incident observation;
- mentor acceptance (requires named reviewer verdict).
