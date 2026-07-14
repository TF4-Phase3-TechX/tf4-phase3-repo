# ADR-014: AI trust and safety controls for the product review assistant

- Date: 2026-07-14
- Status: Proposed
- Decision owners: AIO1 AIE track
- Required reviewers: AIO1 Tech Lead, CDO deployment owner, CDO-07 Audit
- Sign-off: Pending implementation and runtime evidence
- Mandate: `docs/requirements/mandates/MANDATE-06-ai-trust-safety.md`

## Context

The product-review assistant is exposed through the storefront. The current baseline uses a deterministic mock LLM, while Mandate 06 requires a real model, safe degradation, grounded answers, protection against prompt injection and PII leakage, reproducible evaluation, and a mentor-run adversarial demonstration.

The real-provider path can bypass `src/llm/app.py` when `product-reviews` points `LLM_BASE_URL` directly at an OpenAI-compatible provider. Guardrails implemented only inside the mock service therefore do not protect the production request path.

## Decision

### 1. Put controls on the non-bypassable request path

The mandatory control flow is:

```text
Storefront request
  -> product-reviews request validation
  -> fetch product/review evidence
  -> sanitize untrusted review content and redact PII
  -> bounded real-LLM call
  -> validate tool calls and product scope
  -> groundedness/output safety gate
  -> safe answer or explicit fallback
```

Controls may later be extracted into an LLM gateway, but real and mock modes must not bypass them.

### 2. Select mode explicitly

Use an explicit mode such as `LLM_MODE=mock|real`. The presence of `OPENAI_API_KEY` is not a valid mode switch because the existing mock deployment uses a dummy key.

- `mock`: use the in-cluster mock endpoint.
- `real`: require an approved provider URL, pinned model identifier and secret-backed API key.
- Missing or invalid real-mode configuration: fail closed and keep the storefront responsive.

The API key must be supplied through a Kubernetes Secret or approved secret store and must never be committed, pasted into Jira, or logged.

### 3. Bound provider failure

All provider calls, including tool-call follow-ups, must use a defined timeout, at most a bounded retry, and a circuit-breaker/cooldown policy. Timeout, rate-limit, provider error and invalid response return a safe user-facing fallback without exposing raw errors.

Operational rollback is an explicit configuration change back to `LLM_MODE=mock`, followed by rollout and verification. Runtime failure handling is distinct from operational rollback.

### 4. Treat reviews and model output as untrusted

- Detect instruction-override and prompt-exfiltration patterns in both user questions and review/tool content.
- Redact supported PII classes before content leaves the TF4 boundary and scan the model output again before display.
- Never place secrets or hidden operational instructions in the model prompt.
- Force tool arguments to the product and operation authorized by the application request.
- Reject unknown tools and actions; cart/checkout actions require the separately approved Copilot confirmation policy.

Deterministic filters are defense-in-depth, not proof of semantic safety. Their known false-positive and false-negative limits must be recorded.

### 5. Gate display on evidence

Answers must be supported by the fetched product/review evidence. If the requested fact is absent or validation fails, the assistant returns an explicit insufficient-information response or the approved fallback. A fluent answer is not sufficient evidence of correctness.

### 6. Require reproducible evaluation and runtime evidence

Commit a versioned dataset and script that report at least:

- grounded/faithful answer rate;
- unsupported-question refusal rate;
- prompt-injection block rate, including attacks embedded in reviews;
- PII leakage rate;
- tool-policy violation rate when tools are enabled;
- provider error/fallback success rate;
- latency and token/cost observations, clearly separating offline provider latency from storefront end-to-end latency.

The mentor validation must enter through the real product-review request path, not only the mock `/v1/chat/completions` endpoint.

## Release gates

1. Offline real-model eval passes the thresholds approved in the evaluation report.
2. Local/integration tests prove timeout, rate-limit, invalid response and unavailable-provider fallback.
3. Guardrails run on the real request path and malicious review cases cannot override behavior.
4. PII is redacted before provider transmission and before display.
5. Controlled deployment uses a pinned model, secret-backed key, resource requests/limits, non-root security context and no public operational endpoint.
6. A 1-2 product smoke test and rollback rehearsal pass without breaking storefront SLO.
7. Mentor-run adversarial cases and the signed evidence package are complete.

## Consequences

- Positive: controls protect both real and mock modes and can be tested deterministically.
- Positive: unsupported or unsafe answers fail safely instead of reaching customers.
- Trade-off: conservative gates can increase refusal rate.
- Trade-off: pre/post validation adds latency; thresholds and implementation must preserve storefront SLO.
- Trade-off: the team must maintain attack/eval datasets as new failure modes appear.

## Jira mapping

- `TF4AIO-22`: mock eval pipeline readiness only; not real-model quality evidence.
- `TF4AIO-23`: controlled real LLM selection and cutover.
- `TF4AIO-24`: safe provider-failure fallback.
- `TF4AIO-26`: prompt injection in review content.
- `TF4AIO-27`: pre-provider and output PII/system-prompt protection.
- `TF4AIO-29`: timeout and circuit breaker.
- `TF4AIO-30`: token/cost monitoring; merged runtime artifact still requires verification.
- `TF4AIO-34`: tool allow-list and excessive-agency guardrail.
- `TF4AIO-52`: AI telemetry; merged runtime artifact still requires verification.
- `TF4AIO-64`: reproducible real-model trust/safety evaluation and numeric report.
- `TF4AIO-65`: mentor end-to-end validation, rollback evidence and signed submission.

## Evidence required before acceptance

This ADR remains `Proposed` until code, tests, numeric eval report, controlled runtime evidence, rollback evidence, mentor validation and named sign-off are linked. Unit tests against only the deterministic mock are not sufficient.
