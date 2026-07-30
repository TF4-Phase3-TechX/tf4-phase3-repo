Mandate 24 matched ON/OFF overhead rerun is complete.

- Accepted production window: 2026-07-30 08:07:45–08:10:20 UTC
- Runtime: exact image digest and same node for ON/OFF
- Design: 20 cold paired cases per arm, alternating order, 2.2 s pacing
- Validity: 0 cache hits, 0 fallback/zero-token rows, 0 model-call mismatches
- OFF p95: 1403.304 ms
- ON p95: 1135.990 ms
- p95 change: -19.049%
- Gate: no more than +5%
- Result: PASS

OFF disabled both the Mandate 24 identity flag and the complete OpenTelemetry
SDK. This is a conservative all-telemetry-off baseline because the current
`LLM_OBSERVABILITY_ENABLED=false` path alone does not bypass every custom
model/tool span.

Claim boundary: this is a 20-pair production observation, not a capacity
benchmark or proof that telemetry improves latency. The paired median delta was
+24.934 ms, so the negative p95 is treated only as “no observed material
overhead.”

The shadow pods never matched the production Service selector and were deleted
after capture. Production remained generation 104, observed generation 104,
and 2/2 ready.

Evidence entry point:
`docs/aio1/mandate-24/runtime-20260730-matched/README.md`
