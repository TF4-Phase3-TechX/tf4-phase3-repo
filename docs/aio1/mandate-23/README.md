# Mandate 23 implementation and evidence index

## Current status

The code path, unit/regression tests, additive protobuf contract, container
closure, metrics, semantic replay harness, runtime replay, and safe
invalidation drill were merged to `main` in PR #692. ADR-023 has named
approval. Jira linkage and final evidence submission remain pending.

The final-revision evidence package is captured in the repository. Do not close
`AI MANDATE #23` until the follow-up commit/PR and evidence are linked from the
Jira ticket.

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

The Helm deployment reads distinct `cache-hmac-secret`, `memory-hmac-secret`,
and `principal-hmac-secret` keys from Kubernetes Secret `ai-state-hmac-secret`.
The frontend uses the third key to sign its HttpOnly pseudonymous AI principal
cookie and ignores body-supplied user ownership fields. Provision three independently
generated values through the approved
secret-management path before rollout; never commit either value. The
deployment intentionally fails closed when the secret or any required key is absent.

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

Run at least three repetitions per case with the same dataset, model, prompt,
Guardrail, and configured price snapshot. Cost values are estimates computed
from the pinned runtime coefficients, not AWS invoice or Cost and Usage Report
amounts. Attach:

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

The canonical submission replay is:

`tests/eval_mandate23/evidence/submission-d0ac437-final/`

It was captured from clean tracked revision
`d0ac437d07c34a771f8d52f790c8b3bfd727b26b`, rebased on
`origin/main@eb74a54`, through the rebuilt production container. Both replay
configurations record the runtime image reference, image digest, code SHA-256,
model, Guardrail, and configured-estimate price snapshot (`0.33` input /
`2.75` output USD per million tokens). The manifests under `runtime/` and
`short-term/` verify successfully; the root `manifest.sha256` additionally
covers both children and the invalidation record.

| Product Q&A observation | Runtime result |
|---|---:|
| Semantically validated cases | 9 / 9 |
| Assertion failures | 0 |
| Cold misses | 3 / 3 |
| Warm hits | 6 / 6 |
| Warm hit rate | 66.67% |
| Model calls | 3 (cold only) |
| Input / output tokens | 4,434 / 991 |
| Configured estimated cost | USD 0.00418847 |
| Mean cold latency | 2,247.52 ms |
| Mean warm latency | 10.93 ms |
| Measured latency reduction | 99.51% |

All nine memory operations were also semantically validated with zero
assertion failures: each repetition stored an allow-listed preference,
recalled it from a new session for the same user, and proved `not_found` for a
different user. These deterministic memory operations made zero model calls.

The `short-term/` child is the canonical three-turn context proof. All 9 / 9
calls were semantically validated with zero assertion failures across three
independent conversations. Every conversation asserted that the initial search
contained product `6E92ZMYYFZ`, the relative cheapest turn selected exactly
that product, and the “this product” review turn returned the same product and
named Solar Filter. The replay made nine model calls, used 27,096 input and 580
output tokens, and measured a configured estimate of USD 0.01053668.

`invalidation.json` records the safe source drill against the discovered
`reviews.productreviews.id=1`: cold miss, warm hit with no model call, then
`source_changed` miss after mutation. `restore_verified=true` proves the exact
original description and score were restored.

The earlier 2026-07-26 replay remains preserved for historical comparison, but
is not the canonical submission because it predates the final parser, replay
provenance, and clean-checkout hardening:

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

- [x] Product-review and Mandate 23 replay suites remain green (197 tests).
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
- [x] Runtime replay semantic assertions executed with zero failures.
- [x] Runtime source invalidation drill captured and restored.
- [x] Rebuilt production container imported the complete module closure and served the runtime replay.
- [x] Frontend AI diagnostics tests (5 / 5) and Next.js production build pass.
- [x] Helm 3.17.3 template render and Docker Compose configuration pass.
- [ ] PR/commit linked to Jira.
- [x] ADR-023 has named approval.
- [ ] Jira ticket has the four required evidence items.
