# Mandate 23 implementation and evidence index

## Current status

The code path, unit/regression tests, additive protobuf contract, container closure, metrics, replay harness, runtime replay, and safe invalidation drill are implemented. A PR/commit link, Jira comment, and named ADR approval are intentionally still pending.

Do not close `AI MANDATE #23` until those external artifacts exist.

## Implementation map

| Requirement | Implementation |
|---|---|
| Product Q&A exact cache | `techx-corp-platform/src/product-reviews/response_cache.py`, `ai_assistant.py` |
| Copilot conservative early cache | `techx-corp-platform/src/product-reviews/router.py` |
| Five complete short-term exchanges | `session_store.py`, router ten-message read |
| Explicit cross-session profile | `profile_store.py`, Copilot memory routes |
| Hit/miss and benefit metadata | `techx-corp-platform/pb/demo.proto`, server/router response finalizers |
| Low-cardinality metrics | `metrics.py`, `product_reviews_server.py` |
| Production replay | `tests/eval_mandate23/replay.py` |
| Safe source invalidation | `tests/eval_mandate23/invalidation_drill.py` |
| Architecture decision | `ADR-023-genai-caching-and-memory.md` |

## Configuration

| Variable | Default / requirement | Purpose |
|---|---|---|
| `VALKEY_ADDR` | `valkey-cart:6379` | Shared response cache, sessions, and profiles |
| `AI_CACHE_HMAC_SECRET` | required in staging/production | User-bound cache-key HMAC |
| `AI_MEMORY_HMAC_SECRET` | required in staging/production | User-bound profile-key HMAC |
| `AI_RESPONSE_CACHE_TTL_SECONDS` | `300` | Cache cleanup/capacity TTL |
| `MAX_HISTORY_EXCHANGES` | `5` | Complete session exchanges retained |
| `APP_ENV` | deployment-specific | Staging/production disallow process-memory fallback |

The Helm deployment reads both HMAC values from key `hmac-secret` in Kubernetes Secret `ai-state-hmac-secret`. Provision that secret through the approved secret-management path before rollout; never commit the value.

## Local verification

From `techx-corp-platform/src/product-reviews`:

```sh
venv/bin/python -m pytest -q
```

Container closure check from `techx-corp-platform`:

```sh
docker compose build product-reviews
docker compose run --rm --entrypoint /venv/bin/python product-reviews -c \
  "import router, copilot_review_summary, response_cache, profile_store"
```

## Runtime replay

After the stack is healthy and temporary AWS credentials/Guardrail configuration are present:

```sh
tests/eval_mandate23/repro.sh
```

The canonical proof starts with Product Q&A because every safe grounded question is cache eligible. Copilot evidence is additional and must use an exact full product name or ID plus a review marker.

Run at least three repetitions per case with the same dataset, model, prompt, Guardrail, and price snapshot. Attach:

- `per_case.jsonl`;
- `aggregate.json`;
- `report.md`;
- `command.txt`;
- `config.json`; and
- `manifest.sha256`.

Do not manually enter or estimate hit rate, latency, tokens, or cost.

## Frontend diagnostics

Product Q&A and Shopping Copilot render an expandable `AI diagnostics` panel
only when the Next.js server starts with:

```sh
AI_DEBUG_METADATA_ENABLED=true
```

This is a server-side gate. When disabled or unset, the API projection removes
cache, model-call, token, cost, latency, and memory metadata before serializing
the browser response. Production therefore does not rely on CSS or hidden DOM
content to protect diagnostics. The Compose default is `false`; local
developers can opt in through `.env.override`.

### Captured runtime evidence

The 2026-07-26 replay used the production gRPC boundary from the rebuilt
`product-reviews` container, the same dataset/configuration, three independent
identity suffixes, and three cold → warm sequences:

`tests/eval_mandate23/evidence/runtime-20260726T1602Z/`

| Product Q&A observation | Runtime result |
|---|---:|
| Successful cases | 9 / 9 |
| Cold misses | 3 / 3 |
| Warm hits | 6 / 6 |
| Warm hit rate | 66.67% |
| Model calls | 3 (cold only) |
| Input / output tokens | 4,434 / 1,002 |
| Estimated cost | USD 0.00383520 |
| Mean cold / warm cost | USD 0.00127840 / USD 0 |
| Mean cold / warm tokens | 1,812 / 0 |
| Mean cold latency | 2,899.98 ms |
| Mean warm latency | 9.73 ms |
| Measured latency reduction | 99.66% |

All nine deterministic memory cases succeeded. Each repetition stored a
preference, recalled it in a different session for the same user, and returned
`not_found` for the cross-user lookup. Memory operations intentionally bypass
response caching and made zero model calls.

The three repetitions use distinct user identities. Therefore the second and
third cold observations also prove that an answer warmed by an earlier user
does not become a cross-user hit.

The evidence directory contains the replay command/configuration, per-case
responses, aggregate report, invalidation output, and a passing SHA-256
manifest. Runtime target ports are ephemeral local Docker mappings and are
recorded in `command.txt` and `config.json`.

The short-term replay is captured separately at:

`tests/eval_mandate23/evidence/short-term-20260726T1610Z/`

All 9 / 9 calls succeeded across three independent conversations. In every
conversation the initial telescope search returned six candidates, the
session-relative second turn selected product `6E92ZMYYFZ` as the cheapest,
and the third turn asked only about “this product” yet returned an answered
review summary for the same `6E92ZMYYFZ`. The third turn's
`cache_reason=no_unique_product` records that conservative early caching was
bypassed while normal session resolution still used the correct referent.

## Mentor invalidation record

The mutable source is a row in `reviews.productreviews` for product `OLJCESPC7Z`. The row ID must be discovered at runtime, not guessed:

```sh
techx-corp-platform/src/product-reviews/venv/bin/python \
  tests/eval_mandate23/invalidation_drill.py \
  --db-dsn "$DB_CONNECTION_STRING" \
  --target localhost:3551 \
  --output /tmp/mandate23-invalidation.json
```

The drill records the exact row ID and original description/score, checks miss → hit, mutates that row with a unique marker, checks `source_changed` miss, restores in `finally`, and verifies restoration.

## Acceptance checklist

- [x] Existing 132 product-review tests remain green.
- [x] Cold miss → hit with no second provider call.
- [x] Cross-user repeat misses.
- [x] Source/model/prompt/Guardrail/schema identity participates in keys.
- [x] Unsafe, insufficient, unavailable, action, and malformed responses are not cached.
- [x] TTL, cache-error degradation, and fill lock are tested.
- [x] Copilot exact-name review eligibility performs no classifier call.
- [x] Ambiguous, comparison, ordinal, and session-relative review requests bypass early cache.
- [x] Cache hit is appended as a complete session exchange.
- [x] Router reads five exchanges / ten messages and trimming retains whole pairs.
- [x] Three independent runtime conversations completed three context-dependent turns.
- [x] Profile requires explicit consent and rejects PII/arbitrary fields.
- [x] Profile show/apply/forget, expiry, cross-session recall, and cross-user isolation are tested.
- [x] Runtime cold/warm replay executed with three independent repetitions.
- [x] Runtime source invalidation drill captured and restored.
- [x] Rebuilt production container imported the complete module closure and served the runtime replay.
- [ ] PR/commit linked to Jira.
- [ ] ADR-023 has named approval.
- [ ] Jira ticket has the four required evidence items.
