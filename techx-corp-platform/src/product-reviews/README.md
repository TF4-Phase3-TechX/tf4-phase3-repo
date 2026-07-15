# Product Reviews Service

This gRPC service returns product reviews and answers short questions through a grounded Amazon Bedrock path. The application fetches product/review evidence deterministically, removes unneeded identity fields, redacts PII, quarantines instruction-like reviews, invokes one pinned Bedrock model with a pinned Guardrail, and validates exact review quotes before display. The model has no DB, cart, checkout, or arbitrary tool access.

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

Production credentials come only from EKS Pod Identity using ServiceAccount `product-reviews-bedrock`; the repo has no provider key. Local real-model evaluation uses temporary AWS SSO credentials.

Provider errors return the static unavailable response. There is no automatic fallback to a mock or different model. Online logs/traces must keep `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=false` and contain metadata only.

The canonical decision, IAM template and evaluation procedure are in [`docs/aio1/mandate-06`](../../../docs/aio1/mandate-06/ADR-006-bedrock-model-and-safety.md).
