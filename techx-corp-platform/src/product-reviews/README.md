# Product Reviews Service

This gRPC service returns product reviews and answers short questions through grounded Amazon Bedrock paths. The application fetches product/review evidence deterministically, removes unneeded identity fields, redacts PII, quarantines instruction-like reviews, invokes one pinned Bedrock model with a pinned Guardrail, and validates exact evidence quotes before display. The model has no DB, cart, checkout, or arbitrary tool access.

## Build and test

From the platform root:

```sh
docker compose build product-reviews
python -m pytest src/product-reviews/tests -q 
```

## Runtime configuration

| Variable | Required/default | Purpose |
|---|---|---|
| `BEDROCK_MODEL_ID` | required | Pinned foundation model or inference profile ID |
| `BEDROCK_GUARDRAIL_ID` | required | Guardrail ID/ARN |
| `BEDROCK_GUARDRAIL_VERSION` | required numeric | Immutable Guardrail version; `DRAFT` is rejected |
| `BEDROCK_OUTPUT_MODE` | `json_schema` | `json_schema`, or `tool` for Nova 2 Lite |
| `BEDROCK_DEADLINE_SECONDS` | `4.5` | SDK read and application deadline |
| `AWS_REGION` | `us-east-1` | Bedrock Runtime region |
| `BEDROCK_SYSTEM_CANARY` | empty | Optional non-secret leak-detection marker |
| `VALKEY_ADDR` | `valkey-cart:6379` | Shared exact cache, sessions, cart proposals, and profiles |
| `AI_CACHE_HMAC_SECRET` | required in staging/production | HMAC key for user-scoped response-cache keys |
| `AI_MEMORY_HMAC_SECRET` | required in staging/production | HMAC key for user-scoped profile keys |
| `AI_RESPONSE_CACHE_TTL_SECONDS` | `300` | Exact-cache cleanup/capacity TTL |
| `MAX_HISTORY_EXCHANGES` | `5` | Complete user/assistant exchanges retained per session |

The cache contract is additive on both AI responses: `cache_status` is always
`hit` or `miss`; `cache_eligible` and `cache_reason` explain bypass/error;
model calls, tokens, estimated cost, latency, and memory status are returned per
request. Guest traffic is not response-cached and cannot use cross-session
profiles because it has no stable user boundary.

Production credentials come only from EKS Pod Identity using ServiceAccount `product-reviews-bedrock`; the repo has no provider key. Local real-model evaluation uses temporary AWS SSO credentials.

Single-product provider errors return the static unavailable response. A resolved two-product comparison may degrade to a deterministic catalog-price comparison, but never to model-authored or review claims. There is no automatic fallback to a mock or different model. Online logs/traces must keep `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` and contain metadata only.

The canonical decision, IAM template and evaluation procedure are in [`docs/aio1/mandate-06`](../../../docs/aio1/mandate-06/ADR-006-bedrock-model-and-safety.md).
