# ADR-007: Bounded multi-turn memory and confirmed cart action (excessive-agency control) for the Shopping Copilot

- Date: 2026-07-21
- Status: **Implemented, verification pending** (local unit/type checks pass; runtime canary and named approvals remain)
- Owner: Huy Vũ
- Required approvers: AIO1 Tech Lead (Nam), CartService owner (cross-team dependency, see Open Items), CDO-07 Audit
- Signatures: to be recorded through the closure PR once runtime gates pass

## Context

The Copilot currently answers grounded, single-turn product questions (ADR-006) and refuses any request matching an action pattern (e.g. "add to cart") with a generic block, before any provider call. Two capabilities are needed on top of that baseline:

1. **Bounded multi-turn memory** — follow-up questions that reference earlier turns ("does the first one have a warranty?").
2. **Confirmed cart action** — letting the Copilot propose `ADD_TO_CART` with a human-in-the-loop confirmation gate, instead of a hard refusal, while preserving the Mandate 6/14 hard bar of `Unauthorized Writes = 0`.

An initial design (v1) let the client submit `repeated ChatMessage history` directly in the gRPC request. Review of that design surfaced a concrete threat not present in the single-turn baseline: a compromised or buggy client could submit a fabricated `role: "assistant"` message (e.g. instructing the model to skip confirmation), and the backend had no way to distinguish it from a real prior turn. This is a new trust-boundary problem that ADR-006's threat model does not cover, because ADR-006 has no concept of conversation history at all.

Four design iterations (v1–v5) closed this and eight further gaps found by code review against the actual `safety.py`, `bedrock_adapter.py`, `product_reviews_server.py`, and `ai_assistant.py` implementations. This ADR records the resulting decision.

## Decision

### 1. Server-side session store eliminates client-supplied history spoofing

The client sends only `session_id` (client-generated UUID) and the current `query`/`question`. It can never submit `history` or an `assistant`-role message. All prior turns are stored and read server-side (Valkey/Redis in EKS/staging/production; in-memory TTL cache fallback permitted **only** in local single-instance dev — multi-pod EKS makes in-memory fallback silently drop history in production, so it is explicitly excluded there). Session keys are `session:{user_id}:{session_id}` (or `guest` when unauthenticated) to prevent cross-user session collision. Bound to 5 recent turns / 2,000 tokens per session, matching ADR-006's existing context-size discipline.

### 2. Input safety checks are split, not merged

The existing `is_attack_or_action()` conflated two different trust boundaries: it was used both to quarantine untrusted **review** content and to hard-block the user's own **query**. Reusing it unmodified for the new cart flow would have either left reviews unprotected or kept blocking legitimate cart requests. It is split into:

- `is_attack(text)` — `_ATTACK_PATTERNS` only (injection/leaking). Blocks user queries; **checked first**, before any action-intent routing.
- `is_action_intent(text)` — `_ACTION_PATTERNS` only. Routes a direct user query into cart-intent handling instead of a hard block.
- `is_attack_or_action(text)` — preserved unchanged for review quarantine in `prepare_context()`, so the existing prompt-injection defense (ADR-006, TF4AIO-26/27/34) does not regress.

Check order in both `search_products_ai()` and `GroundedAssistant.answer()`: `is_attack()` → hard block; else `is_action_intent()` → cart flow; else normal path.

### 3. Dual-surface cart action, with different quantity-extraction strategies per surface

Cart action is supported on both `SearchProductsAIAssistant` and `AskProductAIAssistant`, because a user may ask to add an item either from global Copilot search or from a product detail page mid-Q&A.

- **Search surface**: `parse_search_intent()` gains a `cart_action` value in `SEARCH_INTENT_SCHEMA`/`_VALID_SEARCH_TYPES`, with a dedicated validation branch in `_validate_search_intent()` requiring a product identifier and a bounded `quantity`, following the same fail-closed pattern already used for `compare`.
- **Q&A surface**: `product_id` is already known from page context, so `GroundedAssistant.answer()` takes an early-exit branch on `is_action_intent(question)` **before** the review-fetch/grounding logic — the existing `if not prepared.reviews: return INSUFFICIENT` path does not apply to cart actions, since a zero-review product is still a valid product to add to cart. Quantity is extracted via a lightweight regex (`r"(?:thêm|add)\s+(\d{1,2})"`, default `1`) rather than an extra LLM call, as a deliberate latency/cost trade-off — not an oversight.
- `CartActionProposal.product_name` on the Q&A surface is populated from `fetch_product_info(product_id)` (real catalog data), never from model or regex output, consistent with the Search surface's product-resolution rule below.

### 4. Deterministic product resolution — the model's output is never trusted as a database key

Neither surface uses an LLM-produced `product_id` directly. A new `_fuzzy_match_product_by_name()` (built from the existing token-matching logic in `_match_comparison_target()`) resolves the model's proposed name/keywords against the real catalog:

- **0 matches** → refuse ("Không tìm thấy sản phẩm này trong danh mục").
- **1 match** → build `CartActionProposal` from the resolved catalog record.
- **≥2 matches** → do not auto-select; return a clarifying response listing the matched product names and wait for a follow-up turn.

`quantity` is clamped to `max(1, min(proposed_qty, 10))` regardless of source (LLM or regex).

### 5. Confirmation is server-authorized and single-use

`product-reviews` creates an opaque 256-bit confirmation token and stores the authoritative proposal in Valkey with a five-minute TTL. The client receives the token in the existing `idempotency_key` field but never supplies `product_id` or quantity to the write path. A separate `ConfirmCartAction` RPC atomically validates the token's `user_id` and `session_id`, consumes it, then calls `CartService.AddItem` using only the server-stored values. Replay, cross-user and cross-session confirmation therefore fail before a cart write.

The token is consumed before the downstream call. This gives at-most-once execution at the Copilot boundary: after a timeout or CartService failure the request is not retried because the first call may have applied. The user must request a fresh proposal. Native deduplication inside `CartService` remains a broader cross-team improvement, not a prerequisite for preventing Copilot replay.

### 6. Caller observability

OpenTelemetry spans propagate `app.caller.feature` (`product_qa` vs `copilot_search`) alongside `rpc.method`, so cart-action and multi-turn traffic from either surface is distinguishable in traces/logs/Prometheus without content retention — consistent with ADR-006's telemetry-without-content-retention posture.

### Non-bypassable runtime boundary (extends ADR-006's diagram)

```text
query/question + session_id -> NFKC/size validation
  -> is_attack() hard block (unchanged from ADR-006)
  -> is_action_intent() ? cart-intent path : normal grounded-QA/search path
  [cart-intent path]
  -> server-side session history lookup (Valkey/Redis; never client-supplied)
  -> LLM intent parse (search surface) OR regex quantity extract (Q&A surface, product_id already page-bound)
  -> deterministic catalog resolution (_fuzzy_match_product_by_name)
       0 match -> refuse | 1 match -> proposal | >=2 matches -> clarify, no auto-select
  -> quantity clamp [1,10]
  -> authoritative proposal stored in Valkey with 5-minute TTL
  -> CartActionProposal (opaque confirmation token, confirmation_required=true)
  -> Frontend confirmation gate (human click required)
  -> ConfirmCartAction validates user/session + atomically consumes token
  -> CartService.AddItem using server-stored product and quantity
```

The LLM never calls `CartService` directly, never selects a `product_id` that reaches the cart write path unresolved, and never bypasses the confirmation gate. This preserves the `Unauthorized Writes = 0` bar established under Mandate 6/14.

## Alternatives rejected

- **Client-supplied `history` array** (v1 design): allows fabricated `assistant`-role messages to influence model behavior with no server-side means of detection. Rejected in favor of server-side session store.
- **Single merged `is_attack_or_action()` reused as-is**: would either regress review-quarantine coverage or keep blocking legitimate cart requests. Rejected in favor of splitting into `is_attack()` / `is_action_intent()`.
- **Auto-selecting the first fuzzy-match product on ambiguity**: creates a real risk of confirming a cart-add for the wrong product if the user does not read the confirmation card carefully. Rejected in favor of a mandatory clarification turn.
- **Trusting an LLM-emitted `product_id` directly**: the model has no reliable memory of real catalog IDs; using it as a database key risks displaying/adding an incorrect or non-existent product. Rejected in favor of deterministic catalog resolution.
- **In-memory session store fallback in production EKS**: silently breaks under multi-pod routing (session lost when a later turn lands on a different pod than an earlier one). Restricted to local single-instance dev only; Valkey/Redis is mandatory in staging/production.
- **Frontend-only confirmation/idempotency**: a disabled button cannot stop HTTP/gRPC retries or a crafted request. Rejected in favor of an authoritative, atomic, single-use proposal store at the product-reviews boundary.
- **Retrying `AddItem` after timeout**: the first call may already have mutated the cart. Rejected; consume-before-call provides at-most-once behavior and requires a fresh user-confirmed proposal after failure.

## Consequences and open items

Cart action and multi-turn memory add a new trust boundary (session store) and a new write-adjacent surface (`CartActionProposal`) that did not exist under ADR-006. The following are accepted gaps or cross-team dependencies, not yet closed:

| Item | Status | Notes |
|---|---|---|
| `CartService.AddItem` native dedupe | Optional, cross-team | Copilot consumes proposals once; CartService-wide idempotency would protect other callers too |
| `cart_action` schema validation in `bedrock_adapter.py` | Implemented | Strict branch in `SEARCH_INTENT_SCHEMA` and `_validate_search_intent()` |
| Ambiguity-resolution eval coverage | Design complete, dataset pending | `cart_action_ambiguous_match`, `cart_action_qa_surface_no_reviews`, `multi_turn_ambiguity_followup` test groups to be added to `generate_dataset.py` |
| Multi-turn quality vs. security rubric split | Noted, not yet reflected in `AI_EVAL_RUBRIC.md` | `multi_turn_ambiguity_followup` measures memory quality (partial-pass possible); `fake_history_attack` measures a hard security gate (pass/fail only) — these should not share one scoring rubric |
| Valkey/Redis availability in staging/production | Configured, runtime proof pending | Chart points product-reviews at `valkey-cart`; startup and runtime fail closed when unavailable outside local dev |
| Session identity binding without full auth | Accepted platform constraint | Current storefront identity is client-generated. Tokens remain high-entropy, short-lived and user/session-bound; replace with authenticated subject when platform auth exists |

| Evidence | Link/status |
|---|---|
| Design iteration record (v1–v5) | Complete: this document supersedes `implementation_plan.md` v1–v5 |
| Proto changes (`demo.proto`) | Implemented on integration branch |
| `bedrock_adapter.py` cart_action schema | Implemented on integration branch |
| Session/proposal safety unit tests | Local pass: bounded/scoped history, invalid IDs, expiry, cross-user/cross-session rejection and replay rejection |
| Frontend type check | Local `npx tsc --noEmit` pass |
| Eval dataset additions (6 new test groups) | Not yet implemented |
| Runtime canary (multi-pod session store, cart confirmation flow) | Pending |
| AIO1 Tech Lead (Nam) | Review required |
| CartService owner | Review required for idempotency dependency |
| CDO-07 Audit | Review required |
