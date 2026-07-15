# D5-PERF-05 precheck verdict

**Precheck date:** `2026-07-15T08:04–08:08Z`  
**Verdict:** **BLOCKED — DO NOT START LOAD**

## Evidence

- D5-PERF-03 official run `D5-20260715T071042Z` is `STOPPED`, not `PASS`.
- Wave 1 values were reverted by the authoritative GitOps reconciler; Waves
  2–5 were not executed.
- The captured pre-remediation Checkout success was `0%`, so that window is not
  a valid passing performance baseline.
- A missing-resource Pod was accepted by `kubectl apply --dry-run=server` in
  `techx-admission-test`; resource admission enforcement is not active for the
  test scope. The compliant control manifest was also accepted.
- Kafka was OOMKilled at `2026-07-15T08:04:09Z`, inside this precheck window.
- Currency retains four OOMKilled restarts; product-catalog retains seven error
  restarts. These historical counters require a clean T0 snapshot after the
  Kafka incident is resolved.
- Node CPU requests were approximately `85%`, `89%`, and `100%`. The third node
  has no request-based CPU headroom for a surge pod.
- ResourceQuota CPU limits were `6875m/8`, CPU requests `1765m/4`, memory limits
  `5517Mi/12Gi`, memory requests `3303Mi/8Gi`, and pods `29/40`.
- HPA metrics were valid (`checkout 2%/70%`, `frontend 13%/70%`) and all current
  application Pods were Running, but these positive gates do not override the
  admission/OOM/headroom blockers.
- The role cannot use `services/proxy` or `pods/portforward`, so it cannot read
  Locust state or collect same-window UI evidence through the approved private
  path.

## Decision

No Locust process was started and no rolling restart was performed. Starting a
post-enforcement test before enforcement/remediation completes would not test
the state named by D5-PERF-05 and would contaminate evidence.

## Required unblock

1. Merge resource values into the authoritative GitOps source and obtain a
   passing D5-PERF-03 verdict for all applicable waves.
2. Attach Security evidence that missing-resource manifests are rejected in
   `techx-tf4` while compliant manifests pass.
3. Deploy and verify the resource admission policy: missing-resource dry-run
   must be rejected and the compliant control must pass.
4. Resolve the Kafka OOM, wait for a clean stabilization period, and record new
   restart counters immediately before T0.
5. Restore scheduler CPU headroom sufficient for the frontend surge request,
   including topology/spread constraints.
6. Grant scoped `services/proxy` or `pods/portforward` access, or provide an
   approved SSM/private dashboard tunnel.
7. Approve an absolute UTC test window.
8. Identify a valid pre-remediation baseline using the identical 200-user,
   60-second ramp and 15-minute steady-state profile.

Then run `scripts/d5-performance-regression-preflight.ps1`. Only a PASS result
authorizes the approved Locust UI run described in the contract.
