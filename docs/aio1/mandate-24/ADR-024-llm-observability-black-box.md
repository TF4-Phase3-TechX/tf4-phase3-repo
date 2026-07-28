# ADR-024 — Content-free LLM observability black box

- Status: Proposed — implementation and production runtime evidence verified; signatures pending
- Date: 2026-07-27
- Decision owner: Đình Thông Trần
- Jira: TF4AIO-85

## Context

The application already exports AI metrics, logs and distributed traces, but a
caller cannot reliably receive a trace ID and reconstruct one model request
through retrieval/model/tool boundaries. Existing evidence also does not prove
that a marked sensitive value is absent from retained trace/log stores.

Mandate 24 requires per-call reconstruction and aggregate model/surface
observability without retaining prompt or response content.

## Decision

1. W3C trace context is the canonical correlation identifier.
2. Every real Bedrock attempt creates one `bedrock.converse` client span.
3. Model spans retain only bounded metadata: model, guardrail version,
   operation, output-tool name, usage, token-cost estimate, latency, outcome,
   stop reason and contract stage.
4. Application tool boundaries create child spans without arguments or result
   content.
5. Request spans retain salted HMAC pseudonyms for user/session. The salt comes
   from a Kubernetes Secret and is never exported.
6. Prompt, response, raw identity, tool arguments and confirmation tokens are
   prohibited trace attributes.
7. External replay returns the trace ID in the protobuf evidence envelope.
8. Jaeger is the fetch-by-ID source. Prometheus is the aggregate cost/latency
   source. OpenSearch is used only for bounded audit/negative searches.
9. Missing trace ID, missing salt, unavailable required measurements or a raw
   marker hit fail the evidence workflow closed.

## Alternatives considered

- Log prompt/response content: rejected due to privacy and injection/secret
  retention risk.
- Correlate only through logs: rejected because it cannot reconstruct child
  retrieval/model/tool timing.
- Generate a separate application request ID: rejected as the canonical key;
  W3C trace ID already propagates through gRPC and telemetry backends.
- Unsalted hashing of user/session: rejected because it is vulnerable to
  dictionary correlation.

## Consequences

- Trace reconstruction and per-model/surface aggregation become reproducible.
- Added spans increase telemetry volume and add small local processing cost;
  matched before/after p95 evidence is required before acceptance.
- Token cost remains an estimate based on pinned price coefficients and excludes
  Guardrail processing charges.
- Backend retention/access control remains owned by the observability platform.
- Pseudonyms are stable only while the configured salt is stable.

## Acceptance record

| Role | Name | Decision | Date |
|---|---|---|---|
| Task owner | Đình Thông Trần | Pending final live evidence | — |
| AIE/Chatbot lead | Nguyễn Trần Huy Vũ | Pending | — |
| Observability/AIOps owner | Đinh Danh Nam or delegate | Pending | — |
| Audit reviewer | Named CDO-07 reviewer | Pending | — |

Production evidence is captured under `runtime-20260729/`, including a complete
model/tool trace, aggregate view, PII-marker negative proof, provider-fallback
trace and passing overhead comparison. The ADR is still not signed and
TF4AIO-85 must not be marked Done until the named decisions and evidence pack
are attached.
