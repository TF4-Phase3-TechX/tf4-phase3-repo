# Mandate 25: LLM resilience and fault injection

## Purpose

Protect the AI Copilot from transient provider failures and malformed model
output through bounded SDK retries, an application circuit breaker, honest
fallback, and externally controlled feature flags.

## Implementation

1. Boto3 uses bounded standard-mode retries for transient HTTP failures.
2. The application circuit opens after repeated availability failures and
   fast-fails during its cooldown.
3. The UI displays a deterministic degraded state instead of fabricated data.
4. OpenFeature/flagd controls `llmRateLimitError` and
   `llmInaccurateResponse`. Injection occurs inside the adapter provider
   boundary so the normal breaker and fallback code paths are exercised.

## Evidence boundary

The committed unit tests are offline level-3 evidence. The control script
`scripts/inject_mandate25_faults.sh` is not proof that a deployed drill ran.

Runtime level 5 remains pending until a sanitized artifact tied to the exact
deployed SHA records:

- flag state transitions;
- repeated request outcomes and the circuit-open transition;
- fast-fail fallback behavior;
- recovery after the flag is disabled and cooldown elapses;
- timestamps and the runtime revision.

Related branch: `aio01/feat/mandate25-resilience`.
