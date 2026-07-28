# Mandate 24 production evidence — 2026-07-29

**Jira:** TF4AIO-85

**Capture window:** 2026-07-28 15:17–17:47 UTC
**Runtime image:** `405fd07-product-reviews`

## Result

The production observability contract is observed for a real Shopping Copilot
model request:

`frontend-proxy -> frontend -> product-reviews -> bedrock.converse -> tool.catalog_search -> product-catalog -> postgresql`

The replacement complete trace is
`7c86a2172fcdded6c0f45dc9076d6b44`. Its model span records Nova 2 Lite,
Guardrail version 3, 2,981 input tokens, 67 output tokens, estimated cost
`0.0010618 USD`, model latency `851.25 ms`, success outcome and
`app.content.retained=false`.

The originally supplied trace
`4c0b33900665391ee04ce35d305ef0ab` was exported and retained, but it has no
`bedrock.converse` span. It proves the frontend/retrieval/tool chain only and is
not represented as the full model chain.

## Evidence map

| Requirement | Artifact | Result |
|---|---|---|
| Exact original trace fetch | `original-trace-4c0b33900665391ee04ce35d305ef0ab.json`, `original-trace-assessment.json` | Exported; missing model span |
| Complete normal chain | `normal-trace-7c86a2172fcdded6c0f45dc9076d6b44.json`, `normal-trace-summary.json` | Pass |
| Model/surface aggregate | `aggregate-1h.json` | Pass; calls, cost and p95 for `copilot_search` and `product_qa` |
| PII marker negative search | `pii-marker-absence.json`, PII response/trace and bounded OpenSearch response | Pass; Jaeger 0, OpenSearch 0 |
| Provider fallback | `provider-fallback-trace-79c796323a46dc4cacc3eb34c918b30f.json`, `provider-fallback-summary.json` | Pass; two throttled provider attempts, final outcome `unavailable` |
| Main-path overhead | `overhead-baseline.jsonl`, `overhead-candidate.jsonl`, `overhead.json` | Pass; p95 change `-3.05%` against the `+5%` gate |
| Runtime/GitOps identity | `manifest.json` | Runtime tags and desired immutable digests correlated |

## Overhead comparison boundary

The baseline is the clean pre-Mandate-24 matched Product Q&A replay captured at
2026-07-26T17:55Z. The candidate repeats the same product and question with
three independent cold principals on the fully enabled production image. To
compare the same server boundary, candidate latency is the Jaeger
`get_ai_assistant_response` span, not the extra public ALB/frontend client
latency.

- baseline p95: `2185.809 ms`;
- candidate p95: `2119.050 ms`;
- change: `-3.054%`;
- acceptance gate: no more than `+5%`.

## Remaining acceptance boundary

Runtime evidence is complete and the task owner accepted ADR-024 in PR #745.
The AIE/Chatbot, Observability/AIOps and Audit reviewer decisions remain
pending, and this pack still has to be attached to TF4AIO-85 before the ticket
can move to Done. The exact live Argo sync revision was not queried; the
runtime Jaeger resource attributes nevertheless prove both promoted
application image tags.
