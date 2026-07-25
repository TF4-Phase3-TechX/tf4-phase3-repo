# Mandate 22 final evidence packet — 2026-07-25

Canonical Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)

## Submission verdict

The team reached runtime evidence level 5 for detector-triggered policy
evaluation, one autonomous bounded Kubernetes action, real-telemetry
verification, automatic safety rollback, escalation, mutation blocking and a
complete GitOps restore.

The team does **not** claim a successful Mandate 22 closed-loop pass. The target
service recovered during all three post-action latency polls, but the deployed
verifier coupled every action to an aggregate frontend/checkout error-rate
guard. Unrelated checkout errors vetoed the product-reviews result, so the
controller correctly followed its fail-closed rollback/escalation path.

## 1. PRs and commits

### Application

- [#473](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/473),
  merged as `0b63c2002e3c279ec9f48a14b5f7b660f63f9bfa`: canonical
  detector-driven controller, deterministic policy, Lease, server dry-run,
  verification, rollback, escalation, audit and external replay.
- [#553](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/553),
  merged as `66ed32b5cea9eb6af3eece2e55fb64c24c4281b1`: secure release
  image; final-image AIOps suite passed and Trivy reported zero
  HIGH/CRITICAL findings.
- [#654](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/654),
  merged as `581f63cda69c99cc4b9c7711eb74f1724bd1d29e`: production-informed
  confidence calibration without weakening the independent safety checks.
- [#659](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/659),
  merged as `0b45ba948ab09f4b4adb40c0ddb326baeaac2271`: verification
  waits 120 seconds, then reads a 2-minute post-action window over three polls
  20 seconds apart.

### GitOps

- [#199](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/199),
  merged as `b44ffa6d344971c1a08955f8929929019bd19674`: promoted signed
  digest
  `sha256:97c45472e4897393115269ad829cf809a4379ae84ace18538b83963104be5eb7`.
- [#200](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/200),
  merged as `09296694a87e22b5d05e9798a4e4cfd2fd47051b`: bounded activation.
- [#202](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/202),
  merged as `b419c9eacc44504525c9c23b9b0d35aedf2f2e39`: previously
  reviewed `150/10` ramp after the `30/3` stage produced only a 1.20 ratio.
- [#201](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/201),
  merged as `df6b9ca5dc479f7431e58226d359cbff563c2bf0`: exact restore.

## 2. Repro

No production command should be run during the CDO-04 freeze window. The safe
offline entry accepts external JSONL without code changes:

```bash
cd techx-corp-platform/src/aiops
python -m benchmark.mitigation_replay \
  ../../../docs/aio1/mandate-22/scenarios-v1.jsonl \
  --output ../../../docs/aio1/mandate-22/replay-report.json \
  --force
python -m pytest tests/test_remediation.py \
  tests/test_m22_mitigation_replay.py tests/test_verification.py -q
```

The three committed cases cover verified action success, forced-wrong verified
rollback and unhealthy rollback with mutation block plus escalation. This
replay uses the production controller with bounded Kubernetes/telemetry
adapters and is evidence level 3, not a live pass.

Final local verification on this evidence branch:

- targeted verifier/remediation/replay: `17 passed`;
- external replay: `3/3 passed`;
- full AIOps suite: first run hit the existing 80ms event-loop timing test
  once; the isolated rerun passed and the second full run passed `107/107`;
- Ruff passed for every changed Python file;
- machine-readable runtime evidence passed JSON parsing;
- `git diff --check` passed.

Repository-wide Ruff still reports two pre-existing unused imports in
`tests/test_m15_replay.py`; they are outside this change and are not represented
as a Mandate 22 regression.

## 3. Runtime evidence

Machine-readable record:
[`evidence/live-drill-inc-c35170a68bef.json`](evidence/live-drill-inc-c35170a68bef.json).

### Trigger and action

- Namespace/target: `techx-tf4` / `product-reviews`.
- Incident: `inc-c35170a68bef`, detected
  `2026-07-25T14:44:28.966446Z`.
- Trigger: p95 `15000ms`, ratio `2.1304`, z-score `10.5572`, EWMA
  `3.7114`, slow-drift `1.0`, confidence `0.8426`.
- Every `m22-v1` autonomous policy check passed.
- Target Lease, preflight and Kubernetes server-side dry-run passed.
- `action_executed` at `2026-07-25T14:44:39.429212Z`, changing the
  target from the constrained `25m/50m` CPU profile to the retained
  `75m/300m` profile.

### Real-telemetry verification

After the 120-second settle delay, all three target p95 samples were `1.9ms`
against the `1000ms` threshold. The target symptom therefore recovered.

The legacy verifier also required the aggregate frontend/checkout error rate to
be below 1% for every target. Its samples were 4.75%, 2.87% and 3.18%.
Consequently the composite result was unhealthy even though product-reviews
latency had recovered.

### Automatic failure branch

- `rollback_applied` at `2026-07-25T14:47:19.706478Z`.
- Rollback verification samples: `7097.83ms`, `105.5ms`, `105.5ms`.
- The controller requires every poll to be healthy; the stale first sample
  kept the rollback result unverified.
- `rollback_unverified_escalation` at
  `2026-07-25T14:49:59.975736Z`.
- Further mutation was blocked and the target Lease was released.

### Safe restore

GitOps #201 restored, and runtime observation at approximately
`2026-07-25T14:54:38Z` confirmed:

- `REMEDIATION_MODE=dry-run`;
- autonomous remediation false and no target allowlist;
- load generator `10/1`;
- product-reviews `75m/300m`;
- AIOps, product-reviews and load-generator Ready with zero restarts.

## 4. Timing and before/after

| Measure | Observed |
|---|---:|
| Detector decision to action | 10.463s |
| Detector decision to first healthy target sample | approximately 130s |
| Target p95 before → after action | 15000ms → 1.9ms |
| Detector decision to safety escalation | 331.009s |
| Manual-remediation baseline | not collected |

The approximate 130-second value is dominated by the intentional 120-second
settle delay. The incident payload did not timestamp each verification sample,
so the team does not present it as millisecond-precise MTTR. There was no
controlled manual baseline before the freeze; no MTTR-improvement percentage is
claimed.

## 5. ADR and authorization

Architecture and activation gates are in
[ADR-022](ADR-022-safe-closed-loop-mitigation.md).

The AIO policy owner is named. A controlled drill was announced to the shared
team and the activation/restoration PRs received named GitOps reviews. However,
the ADR on `main` still has pending CDO deployment-owner and on-call/SRE
signature rows. Generic PR approval and chat acknowledgement are not promoted
into formal ADR signatures.

## 6. Constraints and blockers

The available runtime window was materially reduced by shared observability
degradation first reported on 2026-07-23:

- OTel Collector and Jaeger memory limiting refused/dropped telemetry;
- the stale Kafka metrics receiver repeatedly attempted to resolve disabled
  `kafka:9092`;
- AIOps emitted coverage-degraded alerts while Prometheus baselines were
  incomplete.

The team waited for shared telemetry to become usable and then ran only
reviewed, bounded GitOps changes. At 22:00 Asia/Saigon the environment had to be
returned to CDO teams. CDO-04 subsequently issued a mandatory freeze for its
Mandate 13 ARM64/Spot rollout, node disruption rehearsal and 60-minute load
curve. The freeze prohibits EKS/GitOps changes and load/chaos testing by AIO.

Therefore no additional production or isolated load drill is attempted in this
submission. The verifier scope fix is validated only offline/CI until a new
approved runtime window or the BTC hidden grading scenario.

## 7. Claim boundary and remaining acceptance work

### Proven

- detector-driven incident and decision;
- deterministic pre-authorized safety policy;
- autonomous bounded Kubernetes action;
- real telemetry over the full configured verification window;
- automatic rollback, escalation, mutation block and Lease release;
- reconstructable audit record and safe GitOps restoration;
- deterministic external replay for success and failure branches.

### Not yet proven

- successful live end-to-end remediation accepted healthy by the deployed
  verifier;
- manual-versus-automatic MTTR improvement;
- formal ADR acceptance by both named CDO deployment and on-call/SRE owners;
- grading-day BTC hidden scenarios.

TF4AIO-83 should remain open or pending mentor acceptance. This evidence packet
must not be used to claim a full pass before those remaining conditions are
accepted or exercised.
