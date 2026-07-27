# Mandate 25: LLM Resilience and Chaos Engineering

## Objective
Implement a robust 4-layer defense mechanism (Boto3 Capped Retry, Circuit Breaker, Honest Fallback, Feature Flags) to protect the AI Copilot from LLM instability and rate limits. 

## Implementation Details
1. **Boto3 Capped Retry**: Implemented in `bedrock_adapter.py` to automatically retry transient failures up to 3 times before failing to prevent infinite hangs.
2. **Circuit Breaker**: Implemented to fast-fail subsequent requests when the LLM provider goes down (using `pybreaker`).
3. **Honest Fallback**: The UI displays a graceful degradation message instead of crashing or showing a generic error.
4. **Chaos Engineering (OpenFeature/flagd)**: Integrated `flagd` feature flags (`llmRateLimitError`, `llmInaccurateResponse`) directly into the LLM adapter to synthetically inject `ThrottlingException` and malformed JSON errors for testing.

## Evidence
The chaos engineering run has been verified via the `inject_mandate25_faults.sh` script. Evidence of the circuit breaker opening and fallback UI logic executing can be found in:
- `evidence/MANDATE25_CHAOS_EVIDENCE.log`

## Related PRs
- Branch: `aio01/feat/mandate25-resilience`
