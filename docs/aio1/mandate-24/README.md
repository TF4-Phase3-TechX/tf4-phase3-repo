# Mandate 24 — LLM Observability Black Box

**Jira:** [TF4AIO-85](https://aio1-xbrain.atlassian.net/browse/TF4AIO-85)
**Owner:** Đình Thông Trần
**Status:** implementation and offline verification complete; deployment and live evidence pending

This package adds a content-free, reconstructable trace contract to the
Shopping Copilot/Product Q&A model boundary.

## Trace contract

Every real `BedrockRuntime.Converse` attempt creates a `bedrock.converse` child
span with:

- W3C trace ID and timestamp from the span envelope;
- `gen_ai.request.model`, operation and bounded output-tool name;
- pinned guardrail version;
- input/output token counts, estimated token cost and provider latency;
- success/error outcome, bounded error type, stop reason and contract stage;
- `app.content.retained=false`.

The parent request span records only a salted HMAC pseudonym for user/session.
Raw prompt, response, user ID, session ID, tool arguments and confirmation token
are not accepted by the observability helper.

Runtime catalog/review/cart tool boundaries create content-free `tool.*` child
spans. `SearchEvidenceTrace.trace_id` returns the active trace ID to an external
replay caller.

Production requires the `product-reviews-llm-observability/hash-salt` Secret
referenced by `deploy/values-aio-llm.yaml`.

## Offline verification

```bash
DB_CONNECTION_STRING=postgresql://unused:unused@127.0.0.1:1/unused \
  techx-corp-platform/src/product-reviews/.venv/bin/python -m pytest -q \
  techx-corp-platform/src/product-reviews/tests \
  tests/eval_mandate24/tests
```

## External replay

Port-forward the deployed service, then replay externally supplied JSONL:

```bash
kubectl -n techx-tf4 port-forward svc/product-reviews 3551:3551

PYTHONPATH=. techx-corp-platform/src/product-reviews/.venv/bin/python \
  -m tests.eval_mandate24.replay \
  tests/eval_mandate24/sample-requests.jsonl \
  --target localhost:3551 \
  --output /tmp/m24-replay.jsonl
```

Each output row contains a request hash, outcome, measured usage/cost and a
non-zero trace ID. It never repeats the request text or caller identity.

## Fetch trace by ID

```bash
kubectl -n techx-observability port-forward svc/jaeger 16686:16686

TRACE_ID="$(jq -r 'select(.case_id=="normal-product-search") | .trace_id' \
  /tmp/m24-replay.jsonl)"

PYTHONPATH=. techx-corp-platform/src/product-reviews/.venv/bin/python \
  -m tests.eval_mandate24.fetch_trace "$TRACE_ID" \
  --jaeger-url http://localhost:16686/jaeger/ui \
  --output /tmp/m24-trace.json
```

## Aggregate model/surface view

```bash
kubectl -n techx-observability port-forward svc/prometheus 9090:9090

PYTHONPATH=. techx-corp-platform/src/product-reviews/.venv/bin/python \
  -m tests.eval_mandate24.aggregate \
  --prometheus-url http://localhost:9090 \
  --window 1h \
  --output /tmp/m24-aggregate.json
```

The report queries calls, estimated cost and p95 latency grouped by model and
surface. It does not read raw logs.

## PII/secret negative proof

After replaying the marked case and fetching its trace:

```bash
kubectl -n techx-observability \
  port-forward svc/opensearch 9200:9200

PYTHONPATH=. techx-corp-platform/src/product-reviews/.venv/bin/python \
  -m tests.eval_mandate24.verify_marker_absence \
  --marker 'm24-canary-alice@example.test' \
  --trace-json /tmp/m24-trace.json \
  --opensearch-url http://localhost:9200 \
  --index 'otel-logs-*' \
  --output /tmp/m24-marker-absence.json
```

The committed/output report retains only the marker SHA-256 and hit counts.

## Provider failure/fallback trace

Use the existing reviewed `llmRateLimitError` flag through the normal GitOps
change/restore process. Replay until the response outcome is
`provider_unavailable`, then fetch that returned trace ID. The trace must contain
an error `bedrock.converse` span and the safe fallback outcome, without prompt
content. Restore the flag immediately after capture.

## Instrumentation overhead

Capture matched replay sets before and after rollout, then compare:

```bash
PYTHONPATH=. techx-corp-platform/src/product-reviews/.venv/bin/python \
  -m tests.eval_mandate24.compare_latency \
  /tmp/m24-baseline.jsonl /tmp/m24-candidate.jsonl \
  --max-p95-increase-percent 5 \
  --output /tmp/m24-overhead.json
```

This task is not complete until the live artifacts, deployed image/Argo
revision and named ADR approvals are attached to TF4AIO-85.
