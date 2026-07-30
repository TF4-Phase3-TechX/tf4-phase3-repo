# Mandate 24 matched ON/OFF overhead evidence — 2026-07-30

**Jira:** TF4AIO-85

**Owner:** Đình Thông Trần

**Accepted run:** `20260730-1605`

**Capture window:** 2026-07-30 08:07:45–08:10:20 UTC

**Result:** Pass

## Result

The accepted run measured 20 cold, paired Product Q&A cases per arm. Order
alternated `OFF→ON` and `ON→OFF` to distribute time/provider drift. Every
measured request had:

- `cache_status=miss`;
- `model_calls=1`;
- non-zero input and output tokens;
- a non-empty response.

| Metric | OFF | ON |
|---|---:|---:|
| Count | 20 | 20 |
| Mean | 1123.256 ms | 1064.672 ms |
| Median | 1068.207 ms | 1054.414 ms |
| p95 | 1403.304 ms | 1135.990 ms |
| Maximum | 1491.904 ms | 1189.742 ms |

Observed p95 change was **-19.049%**, passing the acceptance gate of no more
than **+5%**. The paired median delta was `+24.934 ms`; therefore the negative
p95 result must not be described as observability improving latency. Provider
variance remains larger than the small local instrumentation cost.

## Controls

- Both arms used the exact production image:
  `686786b-product-reviews@sha256:7454e332e5bd2067a19d9f8ed3a30f44b8dbb4eee1aceedba023eb8a78a91cb4`.
- Both shadow pods and the runner were pinned to
  `ip-10-0-10-192.ec2.internal`.
- The pods used the production environment/config/secret references and
  service account.
- Shadow labels did not match the production `product-reviews` Service
  selector. The runtime manifest records an empty
  `shadow_pods_in_production_service` list.
- Principals were arm- and run-scoped, with equal-length ON/OFF identifiers,
  preventing shared Valkey cache hits.
- Calls were paced by 2.2 seconds to remain below the observed provider
  throughput boundary.
- OFF used `LLM_OBSERVABILITY_ENABLED=false` and
  `OTEL_SDK_DISABLED=true`. ON used the production settings
  `LLM_OBSERVABILITY_ENABLED=true` and `OTEL_SDK_DISABLED=false`.

`LLM_OBSERVABILITY_ENABLED=false` alone does not disable every custom
`bedrock.converse`/`tool.*` span in the current implementation. Disabling the
whole OpenTelemetry SDK therefore provides a conservative, broader
all-telemetry-off baseline rather than under-measuring the Mandate 24 subset.
The trace-mode check observed zero non-zero application trace IDs in OFF and
67 unique non-zero trace IDs in ON.

## Invalid diagnostic attempts

The following attempts are retained only as diagnostics and are excluded from
the acceptance result:

- `diagnostic-run1.log`: 35/80 measured rows returned zero-token provider
  fallback at an excessive request rate.
- `diagnostic-run2.log`: 3/40 measured rows returned zero-token fallback from
  pair 18; its otherwise passing p95 was rejected.
- `diagnostic-run3-cache-collision.log`: cache keys collided with the previous
  run because the first runner revision did not namespace principals by run.
- `diagnostic-run4-guardrail.log`: a timestamp-like run ID in the question was
  correctly blocked as possible PII before a provider call.

The final validator fails closed on any cache hit, model-call mismatch,
zero-token result or empty response.

## Claim boundary

This is production-observed, same-image/node/window evidence that the enabled
telemetry stack did not exceed the `+5%` p95 latency gate in this 20-pair
window. It is not a capacity benchmark, a confidence interval, or proof that
telemetry reduces latency. It replaces the earlier three-pair comparison
across different observation sessions for pre-grading closure.

All three test pods were deleted after capture. The production deployment
remained at generation `104`, observed generation `104`, and `2/2` ready
replicas; its two Service endpoints remained the original deployment pods.

## Artifacts

- `matched-overhead.jsonl`: 6 warm-up rows plus 40 accepted measurement rows.
- `overhead-summary.json`: fail-closed statistics and gate result.
- `runtime-manifest.json`: image, node, pod identity, capture window and
  Service-isolation evidence.
- `trace-mode-check.json`: OFF/ON trace-mode proof.
- `runner.log`: immutable stdout from the accepted runner.
- `prepare-shadow_pods.ps1`, `launch_runner.ps1`,
  `run_matched_overhead.py`: reproducible capture tooling.
