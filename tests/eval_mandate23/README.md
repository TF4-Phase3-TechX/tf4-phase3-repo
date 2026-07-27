# Mandate 23 production replay

This harness calls the deployed `ProductReviewService` gRPC boundary. It does not import or invoke the cache, profile store, router, or provider directly.

Each JSONL case accepts the externally controlled identity contract:

```json
{
  "surface": "product_qa",
  "request": {
    "product_id": "OLJCESPC7Z",
    "question": "What do customer reviews say about this telescope?"
  },
  "user_id": "mentor-user",
  "session_id": "mentor-session"
}
```

Repository-owned cases also include an `expect` object. The replay validates
cache status, model-call count, memory status, outcome, response substrings,
and exact/contained product IDs as configured. A semantic mismatch is written
to `per_case.jsonl` as `AssertionError`, excluded from successful aggregates,
and makes the command exit non-zero. External hidden cases may omit `expect`
when the caller performs its own assertions.

For Copilot, use `"surface": "copilot"` and `{"query": "..."}`. A cache-eligible Copilot proof must use one exact catalog ID or full canonical name plus an explicit review marker, for example `Reviews for National Park Foundation Explorascope`. Generic or session-relative review questions intentionally return `cache: miss`.

Run the complete cache, long-term memory, and short-term memory replay:

```sh
tests/eval_mandate23/repro.sh
```

The script defaults to three repetitions, adds a UTC timestamp identity suffix,
and discovers the local Compose-published ProductReview port. It does not
require the gitignored `.env.override` file. Set `MANDATE23_GRPC_TARGET` to
override the target for port-forwarded or deployed environments.

To include the source invalidation drill in the same evidence root, provide a
host-reachable PostgreSQL DSN:

```sh
MANDATE23_DB_DSN='host=localhost port=5432 user=otelu password=otelp dbname=otel' \
MANDATE23_REQUIRE_INVALIDATION=1 \
tests/eval_mandate23/repro.sh
```

Each run writes `runtime/`, `short-term/`, and either `invalidation.json` or an
explicit `invalidation-skipped.txt`. Runtime configuration records the source
revision, dirty state, runtime image/digest/code hash when supplied, model,
Guardrail, and price snapshot. Set `MANDATE23_RUNTIME_IMAGE`,
`MANDATE23_RUNTIME_IMAGE_DIGEST`, and `MANDATE23_RUNTIME_CODE_SHA256` when
capturing submission evidence.

For a benchmark with three independent cold → warm sequences, pass
`--repetitions 3 --identity-suffix=-<unique-run-id>` to `replay.py`. The suffix
is applied to external test identities only; every repetition uses the same
requests and configuration while avoiding state left by earlier runs.

`cases.short-term.jsonl` is the three-turn context proof: catalog search,
session-relative cheapest selection, then a review question about “this
product” without repeating its identity. Run it with the same repetition and
identity-suffix options to capture three isolated conversations.

The output directory contains `per_case.jsonl`, `aggregate.json`, `report.md`, `command.txt`, `config.json`, and `manifest.sha256`. Runtime numbers must come from these outputs; this repository does not pre-fill predicted hit rate, latency, token, or cost claims. A valid submission has zero `assertion_failures`.

For invalidation, run `invalidation_drill.py` with an explicit PostgreSQL DSN. The script discovers and records the exact `reviews.productreviews.id` for product `OLJCESPC7Z`, captures the original description and score, performs miss → hit → source mutation → miss, and restores the exact values in `finally`. Do not edit a guessed review ID.
