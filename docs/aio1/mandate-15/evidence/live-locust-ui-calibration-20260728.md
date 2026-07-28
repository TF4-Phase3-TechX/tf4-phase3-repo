# Mandate 15 live Locust UI calibration — 2026-07-28

**Canonical ticket:** TF4AIO-80  
**Accountable owner:** Cái Xuân Hòa  
**Operator:** Đinh Danh Nam  
**Environment:** `techx-tf4` production namespace  
**Detector image:** `f135035-aiops@sha256:0fb253867561a378f6f89b024c40cd454689f08223f3bc2df4de3ee0f2788dde`  
**Load-generator image:** `181bf50-load-generator@sha256:0ccd1a8229a60d56a26259f717a4452e87bfc3d599ca2e80049b6e9ed0044e18`

## Purpose and safety boundary

The drill tried to create the missing live Mandate 15 masking case: a short,
unrelated noise spike plus a subtle checkout incident. Load was changed through
the existing Locust UI REST API only. No GitOps load change, flagd mutation,
paid-AI request, or remediation action was used.

The load-generator retained `LOCUST_PAID_AI_ENABLED=false`. Locust was restored
to 10 users after every attempt. The checkout helper used valid product, cart,
person and checkout payloads already shipped with the load-generator.

Stop conditions were:

- abort a calibration step when its rolling last-100 workflow failure ratio
  exceeded 10%;
- do not increase load after readiness loss or an unexpected incident;
- restore Locust to 10 users in a `finally` path;
- do not call a healthy window or an overload window a masking pass.

## Observations

| Case | Traffic | Result | Classification |
|---|---|---|---|
| Unpaced boundary | 5 checkout workflow workers for 45 s | 2,177 attempts; 874 failed (40.15%); p95 178.6 ms; mostly HTTP 503 across product/cart/checkout | Unsafe overload calibration; not masking evidence |
| Paced low | 2 workers, 350 ms pacing, 45 s | 224 attempts; 0 failures; p95 65.5 ms | Healthy negative |
| Paced middle | 4 workers, 150 ms pacing, 45 s | 824 attempts; 6 failures (0.73%); four checkout and two product HTTP 503; p95 116.1 ms; all workloads Ready; no incident | Near-threshold healthy/noise negative |
| Mixed masking candidate | 4 workers, 100 ms pacing plus Locust UI `10 -> 125 -> 10` for 8 s | Guard stopped at 550 attempts; 11 product HTTP 429; no checkout failures reached the target service | Noise reached ingress/rate limiting before checkout; invalid as masking proof |
| Preloaded checkout candidate | 1,200 valid carts at 80 ms pacing, then 1,200 checkout-only calls with 4 workers/100 ms plus the same 8 s Locust spike | Preload 1,200/1,200; checkout 1,200/1,200; checkout p95 106.4 ms; no detector incident; every inspected Deployment Ready | Stronger high-load-healthy/noise-rejection evidence; no subtle incident |

The preloaded run was observed from `2026-07-28T09:09:56Z` through
`2026-07-28T09:12:31Z`. Its noise spike ran from `09:11:59Z` through
`09:12:07Z`. The final Locust snapshot was 10 users, 3.9 req/s, zero current
failures and p95 65 ms. After a detector cycle:

- `load-generator`, `frontend`, `cart`, `checkout`, `product-catalog` and
  `aiops` were fully Ready;
- no incident had `detected_at >= 2026-07-28T09:09:50Z`;
- no manual resolution or remediation was performed.

The unpaced overload created a separate transient
`frontend/service_availability` incident while the HPA was scaling. It
auto-resolved after the detector observed two healthy polls. That lifecycle is
useful detector behavior, but it is an obvious availability incident and is
not the required subtle checkout signal.

## Rerun recipe

1. Confirm Locust is at 10 users and paid AI is disabled.
2. Confirm AIOps has no active incident and all target Deployments are Ready.
3. From the load-generator pod, preload unique carts with known product IDs and
   valid `people.json` payloads at no more than the measured safe rate.
4. Submit checkout-only calls from the staged user IDs.
5. During checkout, call Locust UI `POST /swarm` with 125 users and spawn rate
   25 for eight seconds, then immediately call it again with 10 users.
6. Capture request counts, status codes, p50/p95/p99, detector incident JSON,
   incident summary and the final Deployment snapshot.
7. Accept a masking pass only if the noise remains non-pageable while a
   separately labelled subtle checkout incident fires within one detector
   cycle with the expected severity.

## Design conclusion and trade-off

Load-only injection is operationally cheap and needs no deployment, but the
system has a broad healthy region followed by ingress/rate-limit or HPA
behavior. It did not produce a repeatable, separately labelled subtle checkout
incident. Increasing load further would create an obvious shared overload,
which weakens the masking claim and risks interfering with production.

The next controlled option is a reviewed, time-bounded checkout-specific fault
or latency injector that leaves the separate Locust spike as noise. The
alternative is to wait for the organizer hidden scenario. Either option must
retain the same restore and no-flagd-mutation boundaries.

## Claim boundary

Evidence level 5 is established for the observed healthy/noise windows and the
automatic recovery of the overload calibration incident. The live masking case
did **not** pass because no subtle checkout incident existed in the candidate
window. TF4AIO-80 therefore remains In Progress. This document does not claim
organizer acceptance, production precision/recall, or Mandate 15 closure.
