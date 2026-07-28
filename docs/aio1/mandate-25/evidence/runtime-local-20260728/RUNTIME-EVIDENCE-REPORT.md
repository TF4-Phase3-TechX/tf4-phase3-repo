# Mandate 25 Local Runtime Evidence Report

## Evidence identity

- Mandate: AI MANDATE #25 — AI resilience and safe fallback
- Jira: TF4AIO-86
- Accountable owner: Tất Văn
- Evidence date: 2026-07-28
- Runtime: local Docker Compose
- Service under test: `product-reviews`
- Tested code SHA: `e6ef6d433e493eca4cea065c8eb79fe39cecc1af`
- Fault-control API: `tf4.mandate25.ResilienceControl`
- Control target: `127.0.0.1:3551`
- Control token: configured through `MANDATE25_FAULT_TOKEN`; value deliberately
  omitted from repository evidence

## Result

**Local runtime acceptance: PARTIAL — cooldown transition passed; live provider
success after cooldown remains pending.**

The collected replay output and Jaeger traces demonstrate externally controlled
timeout, throttling, provider 5xx, and malformed-output injection; bounded retry;
circuit opening and provider-call suppression; the cooldown transition back to
`closed`; and an honest safe fallback without a tool action proposal. The
post-cooldown live Bedrock request remained transport-safe but timed out, so this
packet does not claim successful green provider recovery for the tested SHA.

This report is local Docker evidence, not proof of a Kubernetes or production
deployment. The ticket must not be marked Done until the named ADR reviewer
accepts ADR-025, the PR is synchronized with `main`, and the required Jira
fields and evidence links are complete.

## Acceptance evidence

| Requirement | Observed result | Canonical evidence |
| --- | --- | --- |
| External timeout injection | Request remained transport-safe and returned `outcome=unavailable`; normalized provider error was `timeout`; the helper restored fault mode to `off`. | [`timeout-final-replay.jsonl`](timeout-final-replay.jsonl), [`timeout-final-terminal.txt`](timeout-final-terminal.txt) |
| External throttling/429 injection | Request remained transport-safe and returned `outcome=unavailable`; normalized error was `throttlingexception`; the helper restored fault mode to `off`. | [`retry-final-replay.jsonl`](retry-final-replay.jsonl), [`retry-final-terminal.txt`](retry-final-terminal.txt) |
| External provider 5xx injection | Request remained transport-safe and returned `outcome=unavailable`; normalized error was `internalserverexception`; the helper restored fault mode to `off`. | [`provider-5xx-final-replay.jsonl`](provider-5xx-final-replay.jsonl), [`provider-5xx-final-terminal.txt`](provider-5xx-final-terminal.txt) |
| Bounded retry | One failed request generated exactly two `bedrock.converse` attempt spans. The second attempt began about 102 ms after the first, matching the configured 0.1-second backoff. | [`bounded-retry-final.png`](bounded-retry-final.png), [`retry-final-replay.jsonl`](retry-final-replay.jsonl), [`retry-final-terminal.txt`](retry-final-terminal.txt) |
| Circuit opens | Six repeated throttled requests moved the breaker from `closed` to `open`; the final request returned the honest unavailable response with `transport=ok` and `has_action_proposal=false`. | [`breaker-final-replay.jsonl`](breaker-final-replay.jsonl), [`breaker-final-terminal.txt`](breaker-final-terminal.txt) |
| Provider calls stop while open | The final circuit-open request trace returned zero matches for `bedrock.converse`, proving rejection before a provider attempt. | [`circuit-open-no-provider-final.png`](circuit-open-no-provider-final.png), Jaeger trace short ID `c6b99ff` |
| Cooldown transition | After 65 seconds, status returned from `open` to `closed`. The subsequent uninjected Bedrock request remained transport-safe but timed out, so green provider recovery is not claimed. | [`recovery-final-before-status.txt`](recovery-final-before-status.txt), [`recovery-final-replay.jsonl`](recovery-final-replay.jsonl), [`recovery-final-terminal.txt`](recovery-final-terminal.txt), [`final-status.txt`](final-status.txt) |
| Malformed tool output is blocked | Injected malformed output returned `outcome=insufficient`, `has_action_proposal=false`, and `transport=ok`; fault mode auto-restored to `off` and circuit remained `closed`. | [`malformed-final-replay.jsonl`](malformed-final-replay.jsonl), [`malformed-final-terminal.txt`](malformed-final-terminal.txt) |
| Safe fallback is visible | The UI displayed the explicit temporary-unavailability response instead of fabricated product content or an error page. This screenshot predates the final merge SHA and is retained as supporting UI evidence, not exact-SHA runtime proof. | [`ui-safe-fallback.png`](ui-safe-fallback.png) |

### Jaeger trace identifiers

- Bounded retry: trace `ec4b3cf0407546200c966ed4e93b3b85`, two
  `bedrock.converse` spans; the second attempt starts about 102 ms after the
  first.
- Circuit-open fast-fail: trace short ID `c6b99ff`, zero
  `bedrock.converse` spans, duration 506.37 ms. The duration includes local
  catalog/cache work and does not contain a provider attempt.

The Jaeger URLs point to a local ephemeral instance, so the screenshots and
trace IDs are the durable repository evidence.

## Malformed-output interpretation

The malformed-output replay reports `last_provider_outcome=success` because the
injected provider envelope was received successfully. The response-contract
boundary then rejected its malformed tool payload. The acceptance signal is the
resulting `outcome=insufficient` together with `has_action_proposal=false`;
therefore no tool action was proposed or executed.

## Reproduction

Run from the repository root in Git Bash. Use a fresh local-only token and do
not paste its value into terminal screenshots or committed files.

```bash
python -m venv .venv-m25
source .venv-m25/Scripts/activate
python -m pip install -r techx-corp-platform/src/product-reviews/requirements-test.txt

export MSYS_NO_PATHCONV=1
export MANDATE25_FAULT_TOKEN="<redacted-local-token>"

docker compose -f techx-corp-platform/docker-compose.yml build product-reviews
docker compose -f techx-corp-platform/docker-compose.yml up -d product-reviews

export MANDATE25_TARGET="$(
  docker compose -f techx-corp-platform/docker-compose.yml \
    port product-reviews 3551
)"

python3() {
  python "$@"
}
export -f python3

./scripts/inject_mandate25_faults.sh status
```

### Timeout, throttling, and provider 5xx

Replace `<mode>` with `timeout`, `throttling`, or `provider_5xx`.

```bash
./scripts/inject_mandate25_faults.sh <mode> -- \
  python -m tests.eval_mandate25.replay \
  tests/eval_mandate25/cases.example.jsonl \
  --target 127.0.0.1:3551 \
  --repeat 1 \
  --output /tmp/mandate25-<mode>.jsonl
```

### Bounded retry and circuit-open proof

```bash
./scripts/inject_mandate25_faults.sh throttling -- \
  python -m tests.eval_mandate25.replay \
  docs/aio1/mandate-25/evidence/runtime-local-20260728/retry-case.jsonl \
  --target 127.0.0.1:3551 \
  --repeat 6 \
  --output /tmp/mandate25-breaker.jsonl
```

In Jaeger, open the failed request and use the trace-local **Find** box for
`bedrock.converse`. A retrying request must show two matches. The final
circuit-open fast-fail request must show zero matches.

### Cooldown recovery

```bash
sleep 65
./scripts/inject_mandate25_faults.sh status

python -m tests.eval_mandate25.replay \
  docs/aio1/mandate-25/evidence/runtime-local-20260728/recovery-final-case.jsonl \
  --target 127.0.0.1:3551 \
  --repeat 1 \
  --output /tmp/mandate25-recovery.jsonl

./scripts/inject_mandate25_faults.sh status
```

Expected final state: fault mode `off`, circuit state `closed`, provider error
`none`, and provider outcome `success`.

### Malformed tool output

```bash
./scripts/inject_mandate25_faults.sh malformed_output -- \
  python -m tests.eval_mandate25.replay \
  docs/aio1/mandate-25/evidence/runtime-local-20260728/malformed-case.jsonl \
  --target 127.0.0.1:3551 \
  --repeat 1 \
  --output /tmp/mandate25-malformed.jsonl
```

Expected result: transport `ok`, `outcome=insufficient`, and
`has_action_proposal=false`.

## Defended retry and breaker decision

- SDK retries are disabled with `max_attempts=0`, preventing hidden attempts.
- The application permits at most two visible provider attempts.
- Retry backoff is bounded at 0.1 seconds and remains within the 4.5-second
  provider deadline.
- Five failed requests in a 30-second window open the breaker.
- The breaker fast-fails during a 60-second cooldown, preventing an outage from
  becoming a provider retry storm.
- Fault injection requires a token, uses allow-listed modes, requires a TTL,
  caps TTL at 120 seconds, and automatically restores mode `off`.

This policy allows one short retry for transient provider errors while keeping
latency and provider load deterministic. The per-attempt spans make the retry
count auditable, and the pre-attempt breaker check makes provider suppression
directly observable.

## Security and evidence hygiene

- The token value is not present in this report or text evidence.
- `healthy baseline.png` is intentionally excluded because the screenshot
  contains a local control-token value. It must not be staged or committed.
- Rotate the exposed local token before any further run.
- Older non-`final` artifacts may remain in an operator workspace as raw
  history but are not part of the committed packet. The canonical evidence is
  the `*-final-*` set linked above.

## Remaining closure gates

- ADR-025 currently says `Proposed; named reviewer acceptance pending`; obtain
  the named reviewer signature/acceptance and link the signed ADR.
- Obtain successful post-cooldown real-provider recovery on the exact reviewed
  SHA, then capture the final `closed`/`success` readback.
- Deploy the reviewed revision and repeat the external drill against that exact
  deployed image/Argo revision.
- In Jira, use summary `AI MANDATE #25`, labels `ai-mandate` and `m25`, and one
  accountable assignee (Tất Văn).
- Add the PR/commit link, exact reproduction commands, runtime screenshots/logs,
  and signed ADR link to the Jira comment before moving the ticket to Done.
