# ADR-023: Exact AI response caching and explicit-consent memory

- Status: Accepted
- Date: 2026-07-26
- Accepted: 2026-07-27
- Deadline: 2026-07-28
- Decision owner: Nguyễn Trần Huy Vũ
- Implementer: Nguyễn Trần Huy Vũ
- Named reviewers: Cái Xuân Hòa (`@XUanhoa04`), Lê Ngọc Thành Tâm (`@H1eu232`)

## Context

Product Q&A and Shopping Copilot previously paid the provider cost again for repeated requests. Copilot kept a bounded session history, but its router read only five messages while the store retained five exchanges. No cross-session preference store, cache evidence contract, or reproducible runtime replay existed.

Mandate 23 requires real hit/miss behavior, freshness after source changes, user isolation, context over at least three dependent turns, explicit long-term memory across sessions, and measured runtime benefit.

## Decision

### Exact response cache

Use Valkey exact caching on both AI surfaces:

- Product Q&A caches only schema-, safety-, and grounding-validated `answered` responses.
- Copilot caches only deterministic review Q&A when the current request contains one exact catalog ID or full canonical product name and an explicit review marker.
- Safety, PII, and attack checks run before lookup.
- Blocked, unavailable, insufficient, malformed, profile-dependent, comparison, session-relative, and cart-proposal responses are not cached.
- Cache outage maps to `cache_status=miss` and `cache_reason=cache_error`; the provider path remains available.
- A short Valkey `SET NX` lock bounds duplicate fills. Waiters retry lookup for a bounded interval and then continue rather than hanging.

Physical cache keys contain no raw question, user ID, or session ID. They include:

- cache namespace/schema and surface;
- HMAC-SHA256 user identity;
- product ID;
- SHA-256 of NFKC/trim/whitespace-collapse/case-fold request text;
- dependency class;
- model, prompt, guardrail, and response-schema configuration digest; and
- source fingerprint.

The source fingerprint is SHA-256 of canonical JSON containing only catalog fields and review `id`, `description`, and `score` actually available to the answer path. Username and other review identity fields are excluded. Source changes therefore cause an immediate key change and miss; TTL is cleanup and capacity control rather than the primary freshness mechanism.

### Cache/session boundary

The Copilot cache dependency class is `explicit_product_review_v1`. Session ID is excluded only because the strict resolver proves the same exact current-turn product with empty and current history. Generic, fuzzy, ambiguous, comparative, ordinal, superlative, and relational references bypass early cache.

Every safe response is finalized through a complete user/assistant exchange append, including cache hits, deterministic answers, clarifications, comparisons, and cart proposals. Thus a hit does not remove context needed by the next turn.

### Short-term memory

`MAX_HISTORY_EXCHANGES=5` means ten messages at both storage and router boundaries. The store applies the count and 2,000-token approximation together, discarding complete oldest exchanges only. Staging and production require Valkey; process memory remains a local-development/test implementation.

### Long-term memory

Long-term memory is keyed by HMAC user identity and never by session. It writes only after an explicit remember command. Version 1 allows:

- `preferred_category`, validated against live catalog categories; and
- `max_budget_usd_cents`, a positive integer number of cents.

Profiles contain schema version, allow-listed values, consent time, update time, and expiry time. They do not contain raw utterances, arbitrary JSON, session history, name, email, or phone. Reads do not refresh the 30-day TTL. Remember, show, apply, and forget operations always bypass response caching. Read errors continue without personalization; write/delete errors fail closed and never claim success.

### Evidence contract

Both protobuf responses add:

- `cache_status` (`hit` or `miss`);
- `cache_eligible` and bounded `cache_reason`;
- `model_calls`, input/output tokens, estimated cost, and latency; and
- `memory_status`.

The production-boundary replay accepts external `{request, user_id, session_id}` JSONL and writes per-case, aggregate, configuration, command, report, and hash-manifest artifacts.

## Parameters and calibration state

| Parameter | Selected value | Status | Selection evidence |
|---|---:|---|---|
| Intent confidence | 0.60 | Provisional baseline | Existing compatible router default; runtime calibration pending |
| History | 5 exchanges | Provisional baseline | ADR-007-compatible and regression tested at 10 messages |
| Session TTL | 1,800 seconds | Provisional baseline | Existing production value; metadata-only gap calibration pending |
| Cache TTL | 300 seconds | Provisional baseline | Fingerprint owns freshness; runtime hit-rate/capacity calibration pending |
| Profile TTL | 30 days from explicit write | Accepted by this decision | Data minimization plus cross-session use |
| Hit rate, latency, cost | Not preset | Runtime-only | Must be generated by Mandate 23 replay |

No predicted number is accepted as evidence.

## Security and operational consequences

- User isolation depends on server-owned identity and secret HMAC key material. The public Next.js routes ignore body-supplied ownership and replace it with a signed HttpOnly pseudonymous principal cookie. Production deployment requires Kubernetes Secret `ai-state-hmac-secret` with independently generated `cache-hmac-secret`, `memory-hmac-secret`, and `principal-hmac-secret` values; no value is committed.
- Valkey loss removes optimization and profile availability but cannot produce a fabricated remembered/deleted state.
- Computing a source fingerprint still reads current catalog/review data on lookup. This is required for freshness and is cheaper than a repeated provider call.
- Exact caching intentionally leaves semantic equivalents as misses.
- Copilot early eligibility is conservative, so some safe repeated queries remain misses by design.
- The replay contract accepts caller-supplied `user_id` values because hidden
  evaluation must control identities. In the anonymous demo frontend this ID
  is an unguessable client session identifier, not an authenticated account
  principal. Production account memory must bind `user_id` at a trusted
  gateway to the authenticated subject and must not expose the internal gRPC
  service publicly.

## Alternatives rejected

- Semantic/vector cache: larger correctness and invalidation surface than required for version 1.
- Cache shared across users: lower storage use but violates the required user boundary.
- Profile fingerprint in response keys: unnecessary complexity; all profile-dependent traffic bypasses cache.
- Fuzzy product-name eligibility: could turn approximate similarity into the wrong unique referent.
- Read-based profile TTL refresh: retains data without new consent.

## Approval record

This ADR was accepted after two named independent reviewers approved the final
implementation head `8a279eb`. PR #692 was subsequently squash-merged as
`e6f571e`.

| Role | Full name | Decision | Date | Approval evidence |
|---|---|---|---|---|
| AIO1 / decision owner | Nguyễn Trần Huy Vũ | Accepted | 2026-07-27 | ADR acceptance recorded in this document; [merged implementation](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/e6f571ec7a5c746f06e686b0df5ccfc9a440c5ed) |
| Independent reviewer | Cái Xuân Hòa (`@XUanhoa04`) | Approved | 2026-07-27 | [PR approval at `8a279eb`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/692#pullrequestreview-4788865475) |
| Independent reviewer | Lê Ngọc Thành Tâm (`@H1eu232`) | Approved | 2026-07-27 | [PR approval at `8a279eb`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/692#pullrequestreview-4788809074) |
