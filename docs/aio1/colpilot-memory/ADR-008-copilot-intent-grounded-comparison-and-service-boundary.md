# ADR-008: Structured Copilot intent, grounded product comparison, and service boundary

- Date: 2026-07-24
- Status: **Implemented locally; runtime evaluation and production approval pending**
- Owner: Huy Vũ
- Required approvers: AIO1 Tech Lead, Product Catalog owner, CDO-07 Audit
- Supersedes: the comparison and intent-routing portions of ADR-007; ADR-006 remains authoritative for the Bedrock trust boundary
- Related decisions:
  - [ADR-006: Amazon Bedrock model selection and trust/safety boundary](../mandate-06/ADR-006-bedrock-model-and-safety.md)
  - [ADR-007: Bounded multi-turn memory and confirmed cart action](ADR-007-copilot-multiturn-memory-cart-action.md)

## Executive decision

Copilot will no longer treat comparison as a decorated product search. It now has a dedicated `COMPARE` intent and a two-stage pipeline:

1. the intent model emits only a validated, structured plan;
2. application code resolves that plan against the live catalog;
3. the pinned Nova 2 Lite model composes a natural-language answer only from bounded evidence;
4. application validators require exact source citations before displaying that answer.

For a request such as “so sánh sản phẩm đắt nhất và rẻ nhất”, the model emits the selectors `most_expensive` and `cheapest`. The application—not the model—selects the two catalog records, calculates their prices, gathers sanitized product/review evidence, and requests an actual comparison. Returning only the two names/cards is no longer considered a complete comparison response.

Keyword matching is not removed universally. It is restricted to deterministic jobs where it is appropriate: safety signatures, an exact greeting fast path, and fuzzy catalog **entity-name** resolution. It is removed from semantic intent, price-extrema selection, category inference from history, description-based routing, and comparison behavior.

Copilot remains deployed inside the `product-reviews` process for this rollout, but its contract and orchestration are now logically separate. A physical `shopping-copilot` service extraction is feasible and recommended as a second deployment step after runtime quality gates pass. This avoids combining a behavioral rewrite with a network, ownership, IAM, and deployment migration.

## Context

The existing `SearchProductsAIAssistant` implementation combined several responsibilities in one route:

- intent classification;
- keyword and fuzzy matching;
- catalog filtering;
- session-reference resolution;
- product-review Q&A;
- comparison selection;
- cart-action proposal;
- user-facing response generation.

This made the route appear to support a comparison intent while, in practice, it only selected and returned product records. The frontend then rendered two cards. It did not receive a first-class answer explaining price difference, feature difference, review evidence, use cases, or a conditional recommendation.

The observed request:

> “So sánh sản phẩm đắt nhất và rẻ nhất”

therefore returned the names of two products instead of comparing them.

The problem was not one prompt alone. It was a contract and pipeline problem across intent parsing, deterministic resolution, generation, validation, transport, and frontend behavior.

## Root-cause analysis

### RC-1: `compare` was routed as product search

`_map_search_type_to_intent("compare")` mapped into the same product-search capability. The allow-list therefore permitted catalog lookup but had no dedicated comparison composition step.

Effect:

- two products could be selected;
- no comparison answer was required;
- the route could report success after returning only product objects.

### RC-2: The intent prompt mixed classification and answer generation

The intent schema exposed a `response_message`, and the prompt allowed the classifier to influence user-facing prose. That blurred two contracts:

- “What does the user want?”
- “What answer should the user see?”

An intent model does not receive authoritative catalog/review evidence, so it must not answer, recommend, resolve product IDs, or invent product names.

### RC-3: Prompt vocabulary and application validation were not fully aligned

Category values and comparison behavior described in the prompt were not consistently constrained by the application contract. Model output that looked semantically plausible could fail validation or create filters that returned zero products.

Effect:

- valid-looking requests could become `invalid_response`;
- a parser failure could look like a catalog no-match;
- repeated semantic failures could make Copilot appear unavailable.

### RC-4: Keyword matching performed semantic routing

Raw words from the query and prior conversation were used in places that should have consumed structured intent. Product descriptions could also influence keyword filtering.

Effect:

- words such as “rẻ nhất”, “đắt nhất”, “book”, or “telescope” could route behavior outside the intent contract;
- history could accidentally change category or price selection;
- descriptive prose could create false entity matches.

### RC-5: Session state could mask an explicit current-turn product

The resolver consulted multi-result session state before completing explicit entity resolution. If a previous search returned multiple products, a later turn naming one exact product could still be treated as ambiguous.

### RC-6: Semantic contract errors and provider availability shared failure state

Malformed or schema-invalid model output contributed to the same circuit breaker used for timeouts and provider outages.

Effect:

- a prompt/schema regression could open the availability circuit;
- one model-stage problem could suppress otherwise healthy requests;
- incident diagnosis could confuse provider health with contract quality.

### RC-7: The transport did not expose a stable response outcome

The frontend mainly inferred behavior from nested parsed intent and returned product count. Provider failures, no-match, clarification, and generated answers did not have a sufficiently direct typed contract.

Effect:

- failure could be presented as empty search results;
- comparison prose had no reliable top-level field;
- UI logic depended on the internals of the trace.

### RC-8: Copilot and product-review Q&A share one deployment boundary

`product-reviews` owns both single-product grounded Q&A and catalog-wide Copilot orchestration. These workloads have different contracts and scaling/ownership concerns, but they currently share:

- one Python process;
- one Bedrock adapter;
- one deployment and IAM identity;
- one protobuf service definition;
- one router dependency graph.

This is a coupling problem, but it is not the direct cause of the missing comparison synthesis. Splitting the service without fixing the contracts would only move the bug.

## Decision details

### 1. Introduce a dedicated `COMPARE` intent

`IntentLabel.COMPARE` has its own runtime allow-list:

```text
COMPARE -> catalog_search -> bedrock_compare
```

It is not treated as a generic search. The application requires exactly two unique resolved products before invoking comparison synthesis. Unsupported cardinality returns a clarification response.

The first version intentionally supports exactly two operands. This gives the response contract, UI, evidence size, and acceptance rubric a bounded shape. Multi-product tables can be added under a separate contract later.

### 2. Separate the intent contract from the answer contract

The intent model is constrained to emit:

- `search_type`;
- optional confidence;
- canonical category;
- numeric price bounds;
- entity-name keywords;
- structured sort order and result limit;
- explicit comparison targets;
- comparison selectors;
- comparison criteria;
- cart quantity;
- a clarification question only for the `clarify` intent.

It must not:

- answer the user;
- recommend a product;
- summarize reviews;
- invent product IDs or names;
- resolve “cheapest”, “most expensive”, “this one”, “first”, or “second” itself;
- use assistant prose as an authoritative catalog entity.

`response_message` remains accepted temporarily for compatibility with older clients, but the prompt marks it deprecated and the application owns top-level response text.

### 3. Use canonical comparison selectors

The supported selector vocabulary is:

```json
["cheapest", "most_expensive"]
```

The supported comparison criteria vocabulary is:

```json
["price", "features", "customer_feedback", "best_for"]
```

Example intent:

```json
{
  "search_type": "compare",
  "category": "telescopes",
  "comparison_selectors": ["most_expensive", "cheapest"],
  "comparison_criteria": [
    "price",
    "features",
    "customer_feedback",
    "best_for"
  ]
}
```

The application applies the optional category to the live catalog, excludes telescope accessories when the category is `telescopes`, ignores non-positive prices for extrema comparisons, resolves both selectors, deduplicates product IDs, and requires exactly two unique records.

### 4. Keep deterministic matching only at bounded boundaries

The resulting policy is:

| Use case | Mechanism | Decision |
|---|---|---|
| Intent classification | Structured model output + schema validation | No keyword routing |
| Category and price-extrema semantics | `category`, `sort_by`, and comparison selectors | No raw-query scanning |
| Explicit product entity | Exact/fuzzy match against product **name** | Keep |
| Product description | Evidence for grounded generation | Never an intent router |
| Previous search selection | Server-side session product IDs | Keep, bounded |
| Greeting fast path | Exact small allow-list | Keep |
| Prompt attack, action, and PII safety | Deterministic patterns plus Guardrail | Keep |

The principle is: keywords may recognize a bounded lexical entity or safety signature; they must not decide open-ended user intent.

### 5. Resolve explicit current-turn entities before session hints

Resolution precedence is:

```text
validated structured selector
  -> explicit exact current-turn product name
  -> unique fuzzy current-turn product-name match
  -> unique server-side last-search product
  -> unique bounded-history product reference
  -> clarification
```

A multi-result previous search may no longer mask a product explicitly named in the current query.

No model-emitted product ID reaches catalog, review, or cart operations directly.

### 6. Add grounded comparison synthesis

After resolving two products, `GroundedAssistant.compare_products()` builds bounded evidence containing:

- catalog product ID;
- name;
- sanitized description;
- categories;
- formatted USD price;
- sanitized, PII-redacted, injection-quarantined reviews.

Each evidence item receives an application-owned source ID:

```text
product:{product_id}:name
product:{product_id}:description
product:{product_id}:categories
product:{product_id}:price
review:{product_id}:{review_id}
```

The comparison system prompt requires the composer to:

1. state the most important difference;
2. compare numeric prices and calculate the absolute difference when possible;
3. compare available features/descriptions;
4. summarize positive and negative customer feedback for each product;
5. explain who each product is best for;
6. give only a conditional recommendation based on user priorities;
7. state explicitly when evidence is unavailable;
8. answer in the language of the current user question.

The composer has no catalog, database, cart, or arbitrary tool access.

### 7. Validate every comparison against application evidence

The model must return exactly:

```json
{
  "decision": "answered | insufficient",
  "answer": "string",
  "citations": [
    {
      "source_id": "application-owned source ID",
      "evidence_quote": "exact substring of that source"
    }
  ]
}
```

The application rejects:

- unknown top-level or citation fields;
- an unsupported decision;
- an answer without citations;
- a source ID absent from the supplied evidence;
- a quote that is not an exact substring of the referenced source;
- PII in the answer;
- the configured system-canary marker;
- malformed model output.

An `insufficient` decision displays the canonical application-owned insufficient response, not model-authored fallback prose.

This validator proves that cited evidence exists. It does not yet perform semantic entailment of each sentence. Runtime/human evaluation remains required for whether the prose correctly interprets the cited text.

### 8. Provide a deterministic degraded response

If comparison generation or output validation fails after the two catalog records have already been resolved, the application returns a bounded fallback containing:

- both trusted catalog names;
- both trusted catalog prices;
- the deterministic absolute price difference;
- a statement that deeper grounded review synthesis is unavailable;
- no unsupported recommendation.

The response outcome is `degraded`. This preserves useful deterministic information without hiding the model failure or inventing review conclusions.

### 9. Separate circuit breakers by stage and failure class

Intent parsing and response generation use separate circuit-breaker state.

Only provider-availability failures contribute to opening a breaker, including timeouts, deadline exhaustion, throttling, service unavailability, and network/client failures.

These failures do **not** open the availability breaker:

- `invalid_response`;
- schema-validation failure;
- citation-validation failure;
- Guardrail intervention.

They remain observable quality/safety outcomes. This prevents a prompt regression from being misreported as a provider outage and prevents intent failures from automatically suppressing an otherwise healthy grounded-Q&A path.

### 10. Add first-class response and outcome fields

`SearchProductsAIAssistantResponse` now includes:

```proto
string response = 4;
string outcome = 5;
```

Representative outcomes include:

- `success`;
- `no_match`;
- `answered`;
- `insufficient`;
- `degraded`;
- `clarification_required`;
- `action_confirmation_required`;
- `blocked`;
- `provider_unavailable`.

The trace remains diagnostic metadata. Frontend behavior must use the typed top-level contract instead of treating nested `parsed_intent` as the source of truth.

The frontend:

- displays `response`;
- does not render product cards for `provider_unavailable`;
- still renders the two grounded product cards alongside a successful/degraded comparison;
- treats non-2xx HTTP responses as errors instead of parsing them as valid Copilot results.

### 11. Use one pinned Nova 2 Lite model for all Copilot model stages

Intent parsing, existing grounded Q&A, and comparison synthesis all use the single `BEDROCK_MODEL_ID` deployment value. For this rollout it remains the ADR-006 winner:

```text
us.amazon.nova-2-lite-v1:0
```

There is intentionally no comparison-model override. Keeping one model avoids a second IAM/model permission, prevents configuration drift between stages, and makes the first runtime evaluation attributable to the new pipeline and prompts rather than to a simultaneous model change.

A stronger or separate comparison model may be reconsidered only in a future ADR after an application-path bake-off. Model size or general benchmark rank is not sufficient.

The coding-agent choices shown in the development UI (`gpt-5.6-sol`, `gpt-5.6-terra`, and others) are not production Copilot runtime models. They must not be copied into the Bedrock deployment configuration.

## Model-selection plan

### Current rollout decision

Use the pinned Nova 2 Lite deployment model for every model stage in this rollout.

Reasons:

- existing IAM and Guardrail routing are already established under ADR-006;
- the new comparison pipeline adds more quality through grounding and contract enforcement before requiring a larger model;
- changing pipeline and model simultaneously would make regressions harder to attribute;
- one model and one Guardrail/IAM path keep the first rollout operationally simple.

### Comparison-model bake-off

Evaluate candidate models through the actual `compare_products()` application path, not a standalone prompt playground.

Minimum dataset groups:

- cheapest versus most expensive globally;
- cheapest versus most expensive within each supported category;
- two explicit names, including similar names and misspellings;
- products with unequal review counts;
- one or both products with no reviews;
- contradictory positive/negative reviews;
- missing feature evidence;
- Vietnamese and English equivalents;
- stored prompt injection inside a review;
- PII inside a review;
- malformed tool/JSON output;
- provider timeout/throttle.

Hard gates:

| Gate | Required result |
|---|---:|
| Correct two product IDs | 100% |
| Exact catalog price and absolute difference | 100% |
| Hallucinated product/specification/price | 0 |
| Invalid or fabricated citation accepted | 0 |
| PII/system-canary leak | 0 |
| Stored-review instruction followed | 0 |
| Response is more than names/cards for answerable cases | ≥ 98% |
| Appropriate `insufficient` when evidence is missing | ≥ 95% |
| p95 within upstream request budget | Required |
| Cost per 1,000 successful comparisons | Recorded and ranked after hard gates |

Among candidates passing every hard gate, rank grounded quality first, then p95 latency, then cost. A model that fails grounding is ineligible regardless of price.

## End-to-end flow

```text
query + server-side session ID
  -> NFKC/length/PII/attack checks
  -> exact greeting fast path OR Bedrock intent parser
  -> strict intent schema + application validation
  -> intent-specific allow-list
       SEARCH   -> deterministic catalog filters
       REVIEWS  -> deterministic entity resolution -> grounded review Q&A
       PURCHASE -> deterministic entity/session resolution -> confirmation proposal
       COMPARE  -> deterministic two-product resolution
                    -> product/review fetch
                    -> PII redaction + stored-injection quarantine
                    -> bounded evidence with application source IDs
                    -> comparison model
                    -> exact schema/source/quote validation
                    -> grounded answer OR deterministic price-only degraded answer
  -> typed gRPC response + outcome
  -> frontend response text + optional grounded product cards
```

## Prompt architecture

### System prompt: intent parser

Owns classification and structured extraction only. It receives the current query and bounded, server-owned history. It may identify that a reference exists but may not turn assistant prose into an authoritative catalog identity.

### System prompt: comparison composer

Owns natural-language synthesis only after deterministic resolution. It receives exactly two products and bounded evidence. It cannot decide which catalog products to compare.

### User prompt

The current user text remains a separate Bedrock message content block. When a Guardrail is enabled:

- evidence is marked as `grounding_source` and `guard_content`;
- the current query is marked as `query` and `guard_content`.

The application normalizes length and Unicode, blocks known attacks/PII before invocation, and treats review text as untrusted data.

### Application-owned messages

Clarification, no-match, provider-unavailable, blocked, and deterministic degraded messages are generated by application code. They do not depend on free-form classifier prose.

## Service separation decision

### Current state

Copilot is still physically part of `product-reviews`. The answer to “is it merged with product-reviews?” is therefore **yes at deployment level**, but no longer fully merged at behavioral-contract level.

### Why physical extraction is deferred

An immediate extraction would simultaneously change:

- frontend RPC destination;
- protobuf service ownership;
- product-catalog and review-service network calls;
- session/Valkey ownership;
- cart confirmation-token ownership;
- Bedrock IAM role and Guardrail policy;
- OpenTelemetry service identity and dashboards;
- deployment, HPA, SLO, rollback, and on-call ownership.

Combining those changes with an intent/comparison rewrite would increase blast radius and make rollback ambiguous.

### Target physical architecture

```text
frontend
  -> shopping-copilot
       -> product-catalog (read)
       -> product-reviews (read-only grounded evidence API)
       -> Valkey session/proposal store
       -> Bedrock intent/comparison
       -> cart (only through confirmed proposal flow)

product detail page
  -> product-reviews
       -> grounded single-product review Q&A
```

The extracted `shopping-copilot` service should own:

- conversation/session orchestration;
- intent parsing;
- intent-specific tool allow-list;
- catalog-wide search and comparison;
- clarification policy;
- comparison prompt and validator;
- cart-action proposal orchestration;
- top-level Copilot response/outcome contract.

`product-reviews` should retain:

- review storage/access;
- review sanitization and quarantine;
- single-product grounded Q&A;
- a bounded, read-only evidence API for Copilot.

### Extraction prerequisites

1. Freeze the new response/outcome contract.
2. Pass comparison runtime evaluation using the current in-process path.
3. Define a read-only review-evidence RPC that does not expose username or raw unnecessary fields.
4. Decide whether proposal/session keys migrate or remain in the current Valkey namespace.
5. Create a least-privilege Bedrock IAM role for `shopping-copilot`.
6. Route frontend traffic behind a feature flag or stable gateway endpoint.
7. Shadow requests to the new service and compare product IDs/outcomes without retaining prompt content.
8. Canary by traffic percentage.
9. Remove Copilot RPC implementation from `product-reviews` only after rollback evidence passes.

## Compatibility and migration

### Backward compatibility

- Existing protobuf field numbers are unchanged.
- New fields use numbers 4 and 5.
- `response_message` remains populated inside parsed intent for older clients during the migration window.
- all model stages continue to use the existing required `BEDROCK_MODEL_ID`.
- Existing single-product `AskProductAIAssistant` behavior is unchanged.

### Rollout sequence

1. Deploy backend with new protobuf fields and comparison pipeline.
2. Verify older frontend behavior remains valid.
3. Deploy frontend that reads top-level `response` and `outcome`.
4. Run offline and staging comparison datasets.
5. Canary the new comparison branch.
6. Keep Nova 2 Lite pinned; treat any future model change as a separate evaluated decision.
7. Begin physical service extraction as a separate ADR/PR series.

### Rollback

The application can roll back in increasing order of scope:

1. disable the comparison branch behind a deployment flag to return clarification while preserving search/Q&A;
2. roll back backend/frontend images to the prior compatible protobuf;
3. retain ADR-006 provider-failure behavior and never silently route to a mock model.

No model-routing rollback is required because every stage uses the same pinned Nova 2 Lite model.

## Observability

Record metadata only:

- stage: intent, catalog resolution, comparison generation, validation;
- intent label;
- model ID by stage;
- outcome;
- refusal/degraded reason;
- latency;
- input/output token count;
- candidate count before/after;
- resolved comparison product IDs;
- quarantined review count;
- provider stop reason;
- response-contract stage;
- circuit state.

Do not record:

- raw user prompt;
- raw reviews;
- generated answer text;
- full provider response;
- Guardrail trace content;
- PII.

Recommended dashboards:

- intent schema failure rate;
- clarification rate by intent;
- comparison resolution success;
- `answered`/`insufficient`/`degraded` mix;
- comparison provider error rate;
- p50/p95 latency and token cost by model role;
- zero-result rate by category;
- circuit-open count by stage.

Alerts must distinguish contract-quality failures from provider-availability failures.

## Security properties

The implementation preserves these non-bypassable properties:

- user/history/review text is never trusted as application instruction;
- the client cannot submit assistant-role history;
- model output is never trusted as a catalog product ID;
- model output cannot invoke arbitrary tools;
- comparison synthesis receives only two application-resolved products;
- exact citation quotes must exist in supplied evidence;
- review PII is redacted and stored instructions are quarantined;
- comparison has no write capability;
- cart mutation still requires ADR-007 confirmation;
- provider/model failures never fall back silently to a mock model;
- telemetry retains metadata only.

## Alternatives considered

### Keep compare as product search and improve only the frontend

Rejected. The frontend has no review grounding contract and should not invent or synthesize product conclusions from cards.

### Ask the intent model to produce the full comparison

Rejected. The intent model does not own authoritative catalog/review evidence, and mixing plan and answer makes validation and failure isolation weaker.

### Remove all keyword and regex matching

Rejected. Deterministic matching remains useful for exact greetings, safety signatures, and bounded entity-name resolution. The defect was using lexical matching as open-ended semantic routing.

### Let the model select catalog IDs

Rejected. IDs and price extrema must be resolved against the live catalog by application code.

### Return an LLM answer without citations

Rejected. It would reintroduce unsupported price/specification/review claims and weaken ADR-006.

### Always use the largest available model

Rejected. Model eligibility depends on application-path grounding, safety, latency, and cost gates. The pipeline and validators provide higher leverage than an unmeasured model upgrade.

### Split `shopping-copilot` into a new service in the same change

Deferred, not rejected. The target architecture is sound, but changing behavior and deployment topology together has unnecessary rollout risk.

## Consequences

Positive:

- comparisons now produce an actual grounded answer;
- product selection is deterministic and reproducible;
- prompt responsibilities are smaller and testable;
- provider outages, schema errors, no-match, and clarification are distinguishable;
- comparison behavior can improve without adding another runtime model;
- the new contract creates a clean seam for future service extraction.

Trade-offs:

- comparison needs a second Bedrock call after intent parsing;
- exact citation validation may increase `insufficient` or `degraded` responses;
- fetching reviews for two products increases latency and evidence size;
- a price-only degraded response is intentionally less helpful than a validated model answer;
- two-product cardinality postpones multi-product comparison;
- physical deployment coupling remains until the extraction phase.

## Implementation record

| Area | Implemented change |
|---|---|
| Intent enum/allow-list | Dedicated `IntentLabel.COMPARE` and `bedrock_compare` capability |
| Intent schema | Canonical categories, selectors, criteria, result limit |
| Intent prompt | Classification-only, no answer/recommendation/ID invention |
| Resolver | Explicit current-turn entity before session; structured category/price selector |
| Keyword policy | Product-name-only fuzzy matching; no description/semantic extrema routing |
| Comparison | Two resolved products, bounded product/review evidence, natural-language synthesis |
| Grounding | Exact application source ID and quote validator |
| Failure handling | Deterministic price comparison with `degraded` outcome |
| Circuit breaker | Separate intent state; semantic errors do not trip availability |
| API | Top-level `response`, `outcome`, and trace `refusal_reason` |
| Frontend | Uses typed response/outcome and does not mask provider failure as no results |
| Runtime config | All stages use the existing pinned `BEDROCK_MODEL_ID` (Nova 2 Lite) |
| Generated clients | Python gRPC/protobuf and TypeScript protobuf bindings updated |

Primary files:

- `techx-corp-platform/src/product-reviews/bedrock_adapter.py`
- `techx-corp-platform/src/product-reviews/router.py`
- `techx-corp-platform/src/product-reviews/ai_assistant.py`
- `techx-corp-platform/src/product-reviews/safety.py`
- `techx-corp-platform/pb/demo.proto`
- `techx-corp-platform/src/frontend/components/Copilot/CopilotChatModal.tsx`

## Verification record

Local verification on 2026-07-24:

| Check | Result |
|---|---|
| Python compilation for `src/product-reviews/*.py` | Passed |
| Full product-reviews unit suite using service virtualenv | **91 passed** |
| Focused intent/comparison/safety/session suite | **87 passed** after final contract update |
| `git diff --check` | Passed |
| Generated Python protobuf/grpc imports | Generated with repository service virtualenv |
| Frontend type check | Not run locally because `src/frontend/node_modules` is absent |
| Real Bedrock comparison evaluation | Pending |
| Staging canary | Pending |
| Physical service extraction | Pending by decision |

Covered tests include:

- compare maps to a dedicated intent;
- canonical selector payload validates;
- exactly two extrema products resolve from the live catalog;
- explicit current-turn product wins over ambiguous session state;
- semantic invalid responses do not open the availability circuit;
- comparison uses the same pinned Nova 2 Lite model as intent/Q&A;
- exact comparison citations pass;
- fabricated/non-exact citations fail;
- full route returns two expected IDs and comparison prose;
- provider/validator failure returns the deterministic degraded answer.

## Acceptance and open items

| Item | Status | Exit criterion |
|---|---|---|
| Local implementation and unit tests | Complete | Full service unit suite passes |
| Frontend type check/build | Pending | `npm run typecheck` and production build pass in dependency-provisioned environment |
| Offline real-model comparison bake-off | Pending | All hard gates in this ADR pass |
| Staging runtime canary | Pending | Quality, p95, cost, Guardrail, and failure drills pass |
| Dashboard separation by stage/model | Pending | Intent and comparison are independently visible |
| Structured session entity state beyond last results | Partial | Explicit selected-product/reference schema replaces remaining history text lookup |
| Catalog attribute normalization | Pending | Features/specifications become typed evidence instead of description-only text |
| Semantic entailment validation | Pending research | Human/judge rubric verifies claims are entailed, not merely cited |
| Physical `shopping-copilot` extraction | Planned separately | Shadow/canary/rollback evidence passes |
| Named approvals | Pending | Required approvers recorded in the closure PR and ADR |

This ADR may move to **Accepted** only after the real-model application-path evaluation, frontend build, staging canary, and named approvals are complete.
