# Mandate 24 light-mode screenshots

These screenshots are reviewer-facing views of the production evidence in the
parent directory. They were captured from the authenticated Jaeger and Grafana
UIs without browser chrome, Cloudflare tokens, real email addresses or client
IP attributes.

| File | Evidence |
|---|---|
| `m24-01-normal-full-chain.png` | Normal request: full frontend, model, tool and catalog trace chain |
| `m24-02-normal-model-fields.png` | Normal model span: model/version, tokens, cost, latency, outcome and content-retention flag |
| `m24-03-pii-trace-zero-raw-marker.png` | Synthetic marker search in its exact Jaeger trace, with zero matches |
| `m24-04-prometheus-cost-by-model-surface.png` | Prometheus 1h cost aggregate grouped by model and AI surface |
| `m24-05-provider-fallback-error-fields.png` | Controlled provider throttling span with bounded error fields |
| `m24-06-provider-fallback-request-outcome.png` | Final request outcome after the controlled provider failures |

The PII canary shown in the Jaeger search field is a synthetic `.example.test`
value, not a real identity. The authoritative machine-readable zero-hit result
for Jaeger and OpenSearch remains `../pii-marker-absence.json`.
