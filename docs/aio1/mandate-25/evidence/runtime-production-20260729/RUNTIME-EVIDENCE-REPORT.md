# Mandate 25 production runtime evidence — 2026-07-29

## Verdict

The bounded production drill passed every technical Mandate 25 runtime gate on
the deployed `405fd07` Product Reviews image. Timeout, throttling, provider 5xx,
malformed output, bounded retry, circuit-open provider suppression, cooldown,
and successful real-provider recovery were observed. The final fault mode was
`off`; the dedicated control Secret was deleted; both replicas were replaced
after deletion and returned Ready with zero restarts.

This packet reaches evidence level 5 (observed in production). TF4AIO-86 still
requires a named reviewer to accept ADR-025 before the mandate can claim level
6 or move to Done.

## Runtime identity

- Run ID: `20260728T1724Z`.
- Observed window: 2026-07-28 17:24–17:27 UTC / 2026-07-29 00:24–00:27 ICT.
- Account and namespace: `511825856493`, `techx-tf4`.
- Deployment: `product-reviews`, generation `84`, rollout revision `81`, 2/2
  Ready before activation and after cleanup.
- Application commit: `405fd07175423d1914aad42f002e5a6a98f107d1`.
- Runtime image:
  `405fd07-product-reviews@sha256:d301bf0d3a59688a3d2344a613455e921463a202078bc4b3d8dc4ad619222fc2`.
- GitOps PR #261 merged as
  `562fdaed6787bafca9b836cefb6c38631ef88291` and promoted `405fd07`.
- Operator session: `tamhieu` using the
  `TF4-AIReadOnlyOrLimitedInvoke` SSO role. Tất Văn remains the accountable
  mandate owner.

The role cannot read the Argo Application resource. Therefore this packet does
not claim a directly observed Argo sync revision; it records the GitOps merge
commit and directly observed immutable runtime digest instead.

Machine-readable identity: [`runtime-identity.json`](runtime-identity.json).

## Results

| Requirement | Production result | Evidence |
|---|---|---|
| Timeout fallback | Transport stayed `ok`; honest `unavailable`; no action proposal; normalized error `timeout`; 115.894 ms. | [`faults-and-breaker.json`](faults-and-breaker.json) |
| Throttling fallback | Transport stayed `ok`; honest `unavailable`; no action proposal; normalized error `throttlingexception`; 114.995 ms. | [`faults-and-breaker.json`](faults-and-breaker.json) |
| Provider 5xx fallback | Transport stayed `ok`; honest `unavailable`; no action proposal; normalized error `internalserverexception`; 115.627 ms. | [`faults-and-breaker.json`](faults-and-breaker.json) |
| Malformed output | Returned `insufficient`; no action proposal; circuit remained closed. | [`faults-and-breaker.json`](faults-and-breaker.json) |
| Bounded retry | Exact trace `2aac18e9e8b2501b408302ba297eb325` contains two `bedrock.converse` spans. | [`bounded-retry-trace-summary.json`](bounded-retry-trace-summary.json) |
| Circuit opens | The fifth sustained throttled search opened the circuit; the sixth fast-failed in 4.083 ms. | [`faults-and-breaker.json`](faults-and-breaker.json) |
| Provider suppression | Exact fast-fail trace `26821388a279c63e60dde111d4abecc8` contains zero `bedrock.converse` spans. | [`circuit-fast-fail-trace-summary.json`](circuit-fast-fail-trace-summary.json) |
| Cooldown recovery | Pre-request state was `half_open`; a real Bedrock request succeeded in 941.778 ms; state became `closed`, provider outcome `success`, fault `off`. | [`post-cooldown-recovery.json`](post-cooldown-recovery.json) |
| Recovery provider call | Exact recovery trace `a3bae6635cf3d8928603b5feda675f00` contains one application `bedrock.converse` span and one AWS Bedrock `Converse` span. | [`post-cooldown-recovery-trace-summary.json`](post-cooldown-recovery-trace-summary.json) |

## Activation, safety, and cleanup

The operator generated a 32-byte random token in memory and created only the
dedicated `product-reviews-mandate25-control` Secret. The two replicas were
replaced sequentially, with Deployment readiness restored to 2/2 before the
next replacement. No flagd, GitOps, image, chart, or shared provider setting
was mutated.

The drill ran inside one deployed Product Reviews pod through authorized
`pods/exec`; application-namespace port-forward was not permitted. Every fault
had a 30-second TTL. The in-pod harness restored `off` in a `finally` path.
Jaeger was queried read-only through the observability access path by exact
trace ID.

Cleanup order was:

1. verify the canonical recovery ended `fault.mode=off` and
   `circuit_state=closed`;
2. delete `product-reviews-mandate25-control`;
3. replace both replicas sequentially so the token leaves process
   environments;
4. verify the Secret returns NotFound and the new replicas are 2/2 Ready with
   zero restarts on the same immutable digest.

The public DNS name was not resolvable from the operator workstation during
the final check. This packet therefore uses Kubernetes readiness plus the
successful in-cluster real-provider request as its post-drill health evidence
and does not claim a public-browser smoke.

## Reproduction

The production harness is
[`tests/eval_mandate25/production_drill.py`](../../../../../tests/eval_mandate25/production_drill.py).
It must be streamed into a selected deployed Product Reviews pod; it reads the
control token only from the pod environment and never prints it. The
content-free Jaeger verifier is
[`tests/eval_mandate25/summarize_trace.py`](../../../../../tests/eval_mandate25/summarize_trace.py).

Do not rerun this production drill without an approved operator window. A
rerun must provision a new token, use bounded TTLs, restore `off`, delete the
Secret, replace every token-bearing replica, and record a new run ID.

## Remaining acceptance gate

All executable source, CI, deployment, production failure/recovery, trace, and
cleanup evidence is complete. The only remaining closure gate is named
reviewer acceptance of ADR-025 and linking this packet in TF4AIO-86. The
operator must not self-assign that independent approval or mark the ADR
Accepted without the reviewer.
