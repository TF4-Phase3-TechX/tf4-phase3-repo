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
| Implementation plan | `docs/aio1/mandate-26/IMPLEMENTATION-PLAN.md` |
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

Values recorded at implementation time (pre-PR commit may differ):

| Item | Value |
|---|---|
| Input SHA-256 | `c229b3c7343420fc2c4cf203dfaaef39891b3fef078ed09f32f26c3170fa9667` |
| Report SHA-256 | see regenerated report after final commit |
| Git revision (at first report gen) | `f135035eabb9200b20fe8978e02000f390bf1633` (base before M26 commit) |
| Model version | `m26-v1` |

The report embeds `git_revision`, `input_sha256`, and per-case rankings.

## Aggregate results (committed suite)

From `rca-replay-report-v1.json`:

- cases: 8 labeled, 8 passed, 0 failed  
- Root@1: **1.0**  
- Root@3: **1.0**  
- MRR: **1.0**  
- processing p50 / p95: ~1.5–2.5 ms (developer machine, pure engine)  
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
  tests/test_rca_replay.py `
  tests/test_worker_rca.py `
  tests/test_worker.py `
  tests/test_m15_replay.py `
  tests/test_m22_mitigation_replay.py `
  -v
```

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
