# ADR-014: AI trust and safety controls for the product review assistant

- Date: 2026-07-14
- Status: Superseded before acceptance
- Superseded by: [`docs/aio1/mandate-06/ADR-006-bedrock-model-and-safety.md`](../../aio1/mandate-06/ADR-006-bedrock-model-and-safety.md)

The initial planning ADR proposed provider-key routing and operational rollback to a mock model. Mandate 06 implementation instead standardizes on Amazon Bedrock Converse, EKS Pod Identity, a pinned Bedrock Guardrail, deterministic context fetch, and no silent runtime mock fallback. ADR-006 is the canonical proposed decision and remains unaccepted until real bake-off and application-path evidence exist.
