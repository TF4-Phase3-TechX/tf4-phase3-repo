# AIO weekly operations review — Week 2

- Date: 2026-07-14
- Current release state: Bedrock implementation and offline real-model bake-off complete; cluster canary pending.
- Proposed model: Nova 2 Lite through `us.amazon.nova-2-lite-v1:0`.
- ADR state: `Proposed` until canary, SLO, rollback, mentor validation and signatures complete.

## Evidence completed

- 270 metadata-only evaluation records across Haiku, Qwen and Nova.
- Nova: supported 96.67%, unsupported 100%, stored injection quarantine 100%, PII/canary leakage 0, evaluation p95 1.328 seconds.
- Static unavailable fallback, 4.5-second deadline, zero online retry and 5-failure circuit breaker are unit tested.
- PR #131 telemetry contract is preserved for tokens, estimated cost, latency, calls and errors.
- Prompt/review/response content is excluded from application logs and trace attributes.

## Risks and next actions

| Risk | Current control | Remaining evidence / owner |
|---|---|---|
| Bedrock outage or throttle | Static fallback and circuit breaker | CDO failure drill and deployed metric proof / Văn, Tâm |
| Cost runaway | Token/cost counters; Nova price variables pinned | Verify PromQL and current price snapshot / Hòa, Thông |
| Injection or PII leakage | Pre-filter, quarantine, Guardrail v3, exact-quote validator | Mentor storefront attack test / Hậu |
| Storefront latency regression | One provider call and 4.5-second deadline | Before/after SLO dashboard / Tâm, CDO |
| Missing detection evidence | Silent-attack review records observability access gaps | Provide private read-only query path / CDO |

## Operational boundaries

- AIO does not mutate `flagd`; fault-injection flags remain incident controls.
- Provider failure does not switch to a mock or another model.
- CDO owns Pod Identity association, canary deployment and GitOps rollback.
- Evidence contains metadata and GitHub links only—never credentials, raw prompts, reviews, responses, PII or Guardrail traces.

See [Mandate 06 evidence](../aio1/mandate-06/README.md) and the [silent-attack detection review](incidents/2026-07-14-silent-attack-detection-review.md).
