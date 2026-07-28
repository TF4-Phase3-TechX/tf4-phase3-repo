Mandate 24 production evidence capture is complete.

- Source: PR #707, merged as `8c10da36e70161d2d5dfcbd35fdc9b56c013324c`.
- Runtime: `405fd07-product-reviews`; desired immutable digest
  `sha256:d301bf0d3a59688a3d2344a613455e921463a202078bc4b3d8dc4ad619222fc2`.
- Complete chain: trace `7c86a2172fcdded6c0f45dc9076d6b44` reconstructs
  frontend-proxy → frontend → product-reviews → Bedrock model →
  catalog-search tool → product-catalog → PostgreSQL.
- Model evidence: `us.amazon.nova-2-lite-v1:0`, Guardrail v3, 2,981 input
  tokens, 67 output tokens, estimated cost `0.0010618 USD`, model latency
  `851.25 ms`, outcome `success`.
- Aggregate: 1h calls, estimated cost and p95 latency grouped by
  `llm_model` and `ai_surface`, with non-empty `copilot_search` and
  `product_qa` series.
- Privacy: synthetic marker trace `5f1dfcb2ca62d10016dc880dcd2fa6da`;
  raw marker hits are Jaeger `0` and OpenSearch `0` across three successful
  `otel-logs-*` shards. Only the marker SHA-256 is retained in the bounded
  report.
- Provider fallback: shared Mandate 25 throttling trace
  `79c796323a46dc4cacc3eb34c918b30f`; two failed provider attempts are
  recorded and the request outcome is `unavailable`.
- Overhead: matched cold Product Q&A server-path p95 moved from
  `2185.809 ms` to `2119.050 ms` (`-3.054%`), passing the `≤ +5%` gate.

Important claim boundary: the originally supplied trace
`4c0b33900665391ee04ce35d305ef0ab` was exported but contains no
`bedrock.converse` span. It is retained as frontend/retrieval/tool evidence,
not as the full model chain. The exact live Argo sync revision was not queried;
runtime Jaeger attributes independently confirm the promoted image tags.

Artifact index: `docs/aio1/mandate-24/runtime-20260729/README.md`.

Remaining before Done: record the named ADR-024 decisions and attach this
artifact pack.
