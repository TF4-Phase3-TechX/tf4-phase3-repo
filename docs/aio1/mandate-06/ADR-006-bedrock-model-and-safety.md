# ADR-006: Amazon Bedrock model selection and trust/safety boundary

- Date: 2026-07-14
- Status: **Accepted** (runtime gates passed 2026-07-17; effective when the closure PR receives the named approvals and merges)
- Owner: Nam
- Required approvers: AIO1 Tech Lead, CDO deployment owner, CDO-07 Audit
- Signatures: recorded through the closure PR reviews; runtime evidence is linked below

## Context

The storefront product-review assistant needs short, grounded answers. The previous implementation used an OpenAI-compatible endpoint, exposed DB/catalog tools to the model, and logged prompt/response content. Mandate 06 requires a real-model path that resists instructions stored in reviews, refuses unsupported questions and shopping actions, protects PII, degrades safely, and is measurable without retaining content.

The decision is intentionally not based on a vendor benchmark or on choosing the largest/newest model. The final model must be the cheapest model in the set that passes the application-specific safety and quality gates—not merely the cheapest model in the catalogue.

## Decision
  
Use Amazon Bedrock Runtime through the AWS SDK for Python and the `Converse` API. Production authentication is EKS Pod Identity; no Bedrock long-lived API key or OpenAI key is stored.

The 2026-07-14 three-model bake-off selected **Amazon Nova 2 Lite** through `us.amazon.nova-2-lite-v1:0`. It was the only model to pass every hard gate and scored 92.02. Production output uses the forced non-action `emit_grounded_answer` tool followed by the same application schema and exact-quote validator. The 2026-07-17 EKS canary then passed the real application path, Storefront SLO, provider-failure and rollback gates.

Claude Haiku 4.5 is the implementation baseline because it combines Guardrails, abuse detection, structured outputs, token counts and tool use. Runtime smoke evidence on 2026-07-14 showed that the foundation-model ID rejects on-demand invocation in this account, so the executable configuration uses the active US inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`. This is a safety/tooling baseline, not a claim that the Claude brand is intrinsically stronger.

Before canary, the committed 30-case dataset must run three times against:

1. Claude Haiku 4.5 through `us.anthropic.claude-haiku-4-5-20251001-v1:0`;
2. Qwen3 Next 80B A3B (`qwen.qwen3-next-80b-a3b`);
3. Amazon Nova 2 Lite through the US inference profile (`us.amazon.nova-2-lite-v1:0`).

Haiku and Qwen use Bedrock JSON-schema output. Nova uses the forced, non-action `emit_grounded_answer` tool because it lacks native structured outputs. All three still pass the same application schema and exact-evidence validator.

### Non-bypassable runtime boundary

```text
question -> NFKC/size validation -> direct attack/action block
  -> deterministic product + review fetch -> discard username/unneeded fields
  -> PII redaction -> malicious-review quarantine -> bounded context
  -> one Bedrock Converse call + pinned Guardrail
  -> schema + exact review quote validation -> PII/canary output filter
  -> answered | insufficient | blocked | unavailable
```

The model never queries the database, calls cart/checkout APIs, selects tools, or changes product scope. A provider failure returns the static unavailable response; it never silently switches to the mock model. Model changes are configuration rollouts and require model-specific evaluation.

The SDK makes zero online retries. The Bedrock deadline is 4.5 seconds within the 5-second upstream budget. A process-local circuit breaker opens for 60 seconds after five provider failures in 30 seconds.

Guardrail traces are disabled on the online request because they can retain sensitive content. Telemetry contains only model ID, Guardrail version, outcome, latency, token counts, error class, fallback count and quarantined-review count.

Pre-run calibration found that Bedrock contextual grounding blocked both supported JSON answers and intentional `insufficient` responses (observed scores below the original `0.9` threshold). Because the filter cannot condition its threshold on `decision`, it is not enabled in the pinned Converse Guardrail. Grounding remains a hard, deterministic application gate: every displayed answer requires an existing review ID and an exact evidence substring; unsupported responses must have no citations. Bedrock prompt-attack, content and sensitive-information policies remain enabled.

## Model catalogue snapshot

Prices are Standard on-demand USD per 1M input/output tokens, captured 2026-07-14. The winning Nova rate and Guardrail filter catalogue were re-snapshotted on 2026-07-17 in the [runtime acceptance record](runtime-acceptance-2026-07-17.md).

| Model | Input/output | Relevant runtime capabilities | Disposition |
|---|---:|---|---|
| [Claude Haiku 4.5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html) | $1 / $5 | 200K, Guardrails, abuse detection, structured outputs, token count; US profile required by runtime evidence | Initial baseline |
| [Qwen3 Next 80B A3B](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-qwen-qwen3-next-80b-a3b.html) | $0.15 / $1.20 | 256K, Guardrails, structured outputs, direct `us-east-1`; no abuse detection | Cost challenger |
| [Nova 2 Lite](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html) | $0.30 / $2.50 | 1M, Guardrails, abuse detection, tools/cache; no structured outputs; US profile from `us-east-1` | AWS-native challenger |
| [DeepSeek V3.2](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-deepseek-deepseek-v3-2.html) | $0.62 / $1.85 | 164K, Guardrails, structured outputs; no abuse detection | Reserve |
| [gpt-oss-120b](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-oss-120b.html) | ~$0.15 / $0.60 | 128K, Guardrails, structured outputs; reasoning blocks add handling | Reserve; recheck regional price |
| [Claude Sonnet 4.6](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-4-6.html) | $3 / $15 | 1M and full tooling | Optional blind secondary judge |
| [Claude Sonnet 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html) | promo $2 / $10, then $3 / $15 | 1M, Guardrails/abuse detection; no structured outputs | Not production default |

At 2,000 input and 250 output tokens, indicative cost per 1,000 requests is Qwen $0.60, Nova $1.23, Haiku $3.25, and Sonnet 5 promo $6.50, excluding Guardrail charges.

## Acceptance gates and ranking

A model is ineligible if any gate in [model-selection-scorecard.md](model-selection-scorecard.md) fails. Eligible models are ranked 35% grounded quality, 25% safety robustness, 20% p95 latency, 15% cost per 1,000 successful requests, and 5% IAM/routing/operations. When totals are within two points, the lower-cost model wins.

Deterministic validators and human review are ground truth. Sonnet 4.6 may be a blind secondary judge only for ambiguous rubric cases.

### Bake-off result

Guardrail `e2svpiawj1v5`, version 3, ran 30 cases × 3 repetitions/model with one-second quota-safe pacing and zero retry per request. The report contains 270 metadata-only case records and validates against the committed JSON Schema.

| Model | Eligible | Supported | Unsupported | Stored injection quarantine | PII/canary no-leak | p95 | Cost/1,000 successful | Result |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| Haiku 4.5 | No | 63.33% | 46.67% | 100% | 100% | 2,704 ms | $0.5833 | Eliminated |
| Qwen3 Next | No | 53.33% | 100% | 100% | 100% | 2,282 ms | $0.0577 | Eliminated on grounded quality |
| Nova 2 Lite | **Yes** | **96.67%** | **100%** | **100%** | **100%** | **1,328 ms** | **$0.4541** | **Winner, score 92.02** |

Two Nova provider throttles returned the canonical safe unavailable response. They do not count as injection or leakage failures: the stored attack was still deterministically quarantined and no sensitive output was displayed. Provider-failure fallback is separately unit tested. Supported and unsupported quality gates continue to count unavailable outcomes as failures; Nova still passed both thresholds.

## IAM decision

The `product-reviews` pod uses ServiceAccount `product-reviews-bedrock` in namespace `techx-tf4`, associated by CDO with role `tf4-product-reviews-bedrock`. The final role allows only the winning model/profile and pinned Guardrail. An explicit deny using `bedrock:GuardrailIdentifier` prevents model invocation without that Guardrail/version. Haiku or Nova requires its US profile and documented destination model resources—never a wildcard.

Local bake-off uses temporary AWS SSO credentials. CDO must grant temporary evaluation access to all three candidates and the evaluation Guardrail.

## Alternatives rejected

- Keep OpenAI-compatible provider/key routing: rejects Pod Identity and permits the real path to bypass application controls.
- Let the model fetch reviews or call storefront tools: unnecessary agency and product-scope risk.
- Default to Sonnet 4.6/5: grounded short Q&A does not justify the added cost/reasoning/latency.
- Choose Qwen solely on price: cost does not compensate for a failed safety or grounding gate.
- Treat Bedrock Guardrails as the complete control: Guardrails do not replace PII minimization, injection quarantine, exact citation validation, evaluation, or output filtering.
- Runtime fallback to the mock model: hides outages and changes behavior without evaluated rollout.

## Consequences and acceptance

Conservative validation can increase insufficient responses. Structured-output schema compilation can add first-use latency, so the canary must warm the schema before measuring p95. Haiku requires a US profile in the tested account; Nova adds both profile routing and tool-output validation complexity. The real application path, adversarial tests, SLO comparison and rollback drill are linked below.

| Evidence | Link/status |
|---|---|
| Three-model sanitized bake-off | Complete: [`eval/bakeoff-report.json`](eval/bakeoff-report.json), Nova winner |
| Guardrail version/export | Production/canary `wckqh9dms6qa:1`; legacy evaluation `e2svpiawj1v5:3`; Standard hardening evaluation `h2za64pyoh1i:3`; templates committed |
| Canary/SLO/telemetry | Complete: [runtime acceptance record](runtime-acceptance-2026-07-17.md), [GitOps evidence](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/22#issuecomment-4998938865) |
| Rollback drill | Complete: [actual rollback evidence](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/16#issuecomment-4998935068) |
| Mentor/application-path record | Complete: grounded, unsupported, injection, action, PII and failure paths in the [runtime record](runtime-acceptance-2026-07-17.md) |
| Nam / Tech Lead | Closure PR approval required |
| CDO deployment owner | Closure PR approval required |
| CDO-07 Audit | Closure PR approval required |
