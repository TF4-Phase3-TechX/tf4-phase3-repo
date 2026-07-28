# Mandate 24 evidence index

**Prepared:** 2026-07-27
**Reviewed source:** local branch `aio01/feat/mandate24-llm-observability`
**Claim boundary:** code and offline tests only; no deployment/live acceptance yet

| Requirement | Current evidence | Status |
|---|---|---|
| Per-real-call model/version, usage, cost, latency, outcome and trace ID | `llm_observability.py`, Bedrock decorators and focused tests | Implemented/offline tested |
| Anonymized user/session | Salted HMAC request attributes; raw-value negative unit test | Implemented/offline tested |
| Retrieval/model/tool reconstruction | Bedrock and runtime tool child spans | Implemented/offline tested |
| External replay returns trace ID | `tests/eval_mandate24/replay.py`; protobuf field | Implemented/offline tested |
| Fetch trace by ID | `tests/eval_mandate24/fetch_trace.py` | Implemented/offline tested |
| Aggregate cost/latency by model/surface/window | `tests/eval_mandate24/aggregate.py` | Implemented/offline tested |
| Provider error/fallback trace | Existing controlled flag plus replay/fetch procedure | Live evidence pending |
| PII/secret raw marker absent | `verify_marker_absence.py` | Live evidence pending |
| Main-path latency overhead | Matched replay comparator with 5% p95 gate | Live A/B pending |
| Pre-deployment live baseline | `PREDEPLOYMENT-LIVE-READOUT-20260727.md`; live Prometheus aggregate and exact Jaeger fetch verified against the old image | Observed; not acceptance |
| Deployed image/Argo revision | None for this change | Pending |
| Signed ADR | ADR-024 created with named pending roles | Pending |

## Required live artifacts

- `runtime/manifest.json`: merged SHA, image digest, Argo revision and config.
- `runtime/normal-replay.jsonl` plus fetched normal Jaeger trace.
- `runtime/provider-fallback-replay.jsonl` plus fetched failure Jaeger trace.
- `runtime/aggregate-1h.json`.
- `runtime/pii-marker-absence.json`.
- `runtime/overhead.json` with matched baseline/candidate inputs.
- Named approval links for ADR-024.

No row marked Pending may be represented as observed or complete in Jira.
