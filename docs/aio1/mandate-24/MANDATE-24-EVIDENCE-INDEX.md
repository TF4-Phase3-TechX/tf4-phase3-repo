# Mandate 24 evidence index

**Prepared:** 2026-07-27

**Runtime reconciled:** 2026-07-30 (Asia/Ho_Chi_Minh)

**Reviewed source:** merged PR #707 plus production image `405fd07-product-reviews`

**Claim boundary:** runtime and matched overhead evidence complete; remaining
named ADR signatures are not inferred from Jira status

| Requirement | Current evidence | Status |
|---|---|---|
| Per-real-call model/version, usage, cost, latency, outcome and trace ID | `runtime-20260729/normal-trace-summary.json` | Production observed |
| Anonymized user/session | Production request span has only salted HMAC pseudonyms and `app.content.retained=false` | Production observed |
| Retrieval/model/tool reconstruction | Complete trace `7c86a2172fcdded6c0f45dc9076d6b44` | Production observed |
| External replay returns trace ID | Public Copilot response returned exact non-zero trace ID | Production observed |
| Fetch trace by ID | Exact Jaeger API export in `runtime-20260729/` | Production observed |
| Aggregate cost/latency by model/surface/window | `runtime-20260729/aggregate-1h.json` | Production observed |
| Provider error/fallback trace | Shared Mandate 25 throttling trace `79c796323a46dc4cacc3eb34c918b30f` | Production observed |
| PII/secret raw marker absent | `runtime-20260729/pii-marker-absence.json` | Production observed; Jaeger 0, OpenSearch 0 |
| Main-path latency overhead | `runtime-20260730-matched/` | Pass; 20 paired cold cases/arm in one window, `-19.049%` p95 vs `+5%` gate, 0 invalid rows |
| Pre-deployment live baseline | `PREDEPLOYMENT-LIVE-READOUT-20260727.md` plus matched replay baseline | Observed |
| Deployed image/Argo revision | Runtime trace tags + GitOps desired digest in `runtime-20260729/manifest.json` | Runtime tag observed; live Argo sync revision not queried |
| Signed ADR | Task-owner acceptance recorded in PR #745; AIE/AIOps/Audit decisions remain pending | Partially signed |

## Production artifact pack

- `runtime-20260729/manifest.json`: merged SHA, production source, runtime image
  tags, desired immutable digests and configuration boundary.
- `runtime-20260729/normal-response.json` plus fetched normal Jaeger trace.
- `runtime-20260729/provider-fallback-summary.json` plus fetched failure trace.
- `runtime-20260729/aggregate-1h.json`.
- `runtime-20260729/pii-marker-absence.json`.
- `runtime-20260729/overhead.json` with bounded matched inputs.
- `runtime-20260730-matched/README.md` plus raw rows, fail-closed summary,
  runtime identity, trace-mode proof and reproducible shadow-run tooling. This
  is the canonical same-window overhead evidence; the earlier three-pair,
  cross-session comparison is retained as historical evidence only.
- Named approval links for ADR-024.

The originally supplied trace `4c0b33900665391ee04ce35d305ef0ab`
contains no model span and must not be used as the complete-chain proof. No row
marked Pending may be represented as accepted or complete in Jira.
