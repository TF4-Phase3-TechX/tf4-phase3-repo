# Mandate 25 canonical evidence index

**Jira:** TF4AIO-86

**Accountable owner:** Tất Văn

**Canonical runtime packet:** `evidence/runtime-production-20260729/`

**Evidence level:** 5 — observed in the bounded production drill

**Closure boundary:** technical runtime gates passed; named ADR reviewer acceptance remains pending

## Which packet is authoritative?

Use the production packet below for every Mandate 25 runtime claim:

[`evidence/runtime-production-20260729/RUNTIME-EVIDENCE-REPORT.md`](evidence/runtime-production-20260729/RUNTIME-EVIDENCE-REPORT.md)

The earlier local Docker packet is historical supporting evidence. It proved
fault control, bounded retry, circuit opening, provider suppression, malformed
output handling, UI fallback and the cooldown state transition, but its real
provider request after cooldown timed out. That local result was superseded for
the recovery gate by the later production request that succeeded and closed the
circuit. Do not combine the local PARTIAL verdict with the production verdict.

## Single runtime result map

| Gate | Canonical result | Artifact |
|---|---|---|
| Timeout fallback | transport `ok`; `unavailable`; no action; 115.894 ms | `runtime-production-20260729/faults-and-breaker.json` |
| Throttling fallback | transport `ok`; `unavailable`; no action; 114.995 ms | `runtime-production-20260729/faults-and-breaker.json` |
| Provider 5xx fallback | transport `ok`; `unavailable`; no action; 115.627 ms | `runtime-production-20260729/faults-and-breaker.json` |
| Malformed output | `insufficient`; no action; breaker stayed closed | `runtime-production-20260729/faults-and-breaker.json` |
| Bounded retry | exactly two `bedrock.converse` spans | `runtime-production-20260729/bounded-retry-trace-summary.json` |
| Circuit opens | fifth sustained failed request opened the circuit | `runtime-production-20260729/faults-and-breaker.json` |
| Provider suppression | sixth request fast-failed in 4.083 ms with zero provider spans | `runtime-production-20260729/circuit-fast-fail-trace-summary.json` |
| Cooldown recovery | `half_open` → real Bedrock success in 941.778 ms → `closed` | `runtime-production-20260729/post-cooldown-recovery.json` |
| Recovery provider call | one application model span and one AWS Bedrock span | `runtime-production-20260729/post-cooldown-recovery-trace-summary.json` |
| Final fault state | `off` | `runtime-production-20260729/post-cooldown-recovery.json` |
| Cleanup | control Secret removed; both replicas replaced and Ready 2/2 with zero restarts | `runtime-production-20260729/RUNTIME-EVIDENCE-REPORT.md` |

## Identity and reproduction

- Runtime image: `405fd07-product-reviews`.
- Immutable digest and GitOps merge identity:
  `evidence/runtime-production-20260729/runtime-identity.json`.
- Production harness: `tests/eval_mandate25/production_drill.py`.
- Trace verifier: `tests/eval_mandate25/summarize_trace.py`.
- Local external helper: `scripts/inject_mandate25_faults.sh`.

Do not rerun the production drill without an approved operator window. A
rerun must use a fresh control token, bounded TTL, `finally` restoration,
Secret deletion, token-bearing replica replacement and a new runtime identity.

## Claim boundary

### Proven

- timeout, throttling and provider-5xx normalization;
- two-attempt bounded retry;
- circuit opening and zero-provider-span fast fail;
- honest unavailable/insufficient responses with no action proposal;
- half-open cooldown and successful real-provider recovery;
- final `fault.mode=off`, Secret deletion and replica replacement.

### Not yet proven or accepted

- named independent acceptance of ADR-025;
- direct live Argo Application sync revision from the restricted operator role;
- public-browser post-drill smoke (public DNS did not resolve in the operator session);
- behavior outside the bounded controlled drill.
