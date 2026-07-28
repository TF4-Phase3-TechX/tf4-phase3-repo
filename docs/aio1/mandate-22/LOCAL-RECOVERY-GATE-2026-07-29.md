# Mandate 22 post-V7 local recovery gate

- Date: 2026-07-29
- Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)
- Accountable owner: Thành Tâm
- Operator/evidence coordinator: Đinh Danh Nam
- Evidence level: **3 — tested offline and in disposable Kubernetes**

## Purpose and V7 diagnosis

V7 is a failed production drill, not a Mandate 22 pass. The bounded action and
target recovery occurred, but durable saga completion required manual GitOps
changes. Two lifecycle failures were correlated with that intervention:

1. FastAPI startup awaited `reconcile_open_sagas()`. A post-action verification
   window can exceed the liveness budget, so the pod was killed before the API
   bound.
2. Restore removed Deployment patch RBAC before saga cleanup closed the Argo
   ownership annotations. The restarted process then received `403` and exited.

The acceptance condition for this change is narrower than Mandate 22 closure:
startup recovery must remain fail-closed without entering a liveness restart
loop, retry temporary cleanup permission loss, and never start the polling
worker or a second action before recovery completes.

## Design and trade-off

Startup now creates a background recovery task and yields the API lifespan:

- `/healthz` remains available so Kubernetes does not kill a process that is
  making progress through a long verification window;
- `/readyz` stays `503` because the polling worker starts only after every open
  saga is reconciled and terminal retention is processed;
- reconciliation failure logs `startup_saga_reconcile_retry` and retries after
  `AIOPS_STARTUP_RECONCILE_RETRY_SECONDS` (default 15 seconds);
- shutdown cancels the recovery/worker task and clears the worker's running
  state deterministically.

Trade-off: a permission outage can leave the pod alive but unready for an
extended period. This is intentional. Keeping it out of Service endpoints and
preventing new detector work is safer than either a restart storm or admitting
work while external Lease/Argo ownership is unresolved.

The operational restore is therefore two-phase:

1. remove the fault/load and return the target resource profile;
2. retain live cleanup RBAC until the saga is terminal with
   `lease_held=false` and `argo_window_active=false`, then disable live RBAC.

## Artifacts

- `techx-corp-platform/src/aiops/app/main.py`
- `techx-corp-platform/src/aiops/app/config.py`
- `techx-corp-platform/src/aiops/app/worker.py`
- `techx-corp-platform/src/aiops/tests/test_startup_recovery.py`
- `techx-corp-platform/src/aiops/tests/test_saga.py`
- `techx-corp-platform/src/aiops/tests/kind/`

The Kind RBAC intentionally mirrors the live chart requirement for read-only
`deployments/status`. The disposable test first runs a real Deployment
rollback with a namespace-scoped service account, Kubernetes Lease, server
dry-run, rollout readiness, saga checkpoints and cleanup. It then removes only
Deployment patch permission, proves the terminal saga remains open, restores
the permission and proves cleanup completes without another action.

## Verification

Offline suite:

```text
python -m pytest -q
157 passed, 1 skipped (the opt-in Kind module)
```

Focused failure matrix:

```text
python -m pytest \
  tests/test_startup_recovery.py \
  tests/test_saga.py \
  tests/test_remediation.py -q
41 passed
```

Disposable Kind:

```text
kind v0.31.0
node: kindest/node:v1.34.3@
  sha256:08497ee19eace7b4b5348db5c6a1591d7752b164530a36f855cb0f2bdcbadd48

M22 Kind cycle 1: 2 passed
M22 Kind cycle 2: 2 passed
M22 Kind cycle 3: 2 passed
```

Each Kind cycle recreated `product-reviews` revision 1 (`v1-known-good`) and
revision 2 (`v2-fault`) before executing the tests. The service account was
confirmed unable to delete Deployments. No EKS, GitOps, flagd or Bedrock
endpoint was used.

## Claim boundary and next gate

### Proven

- long startup reconciliation no longer prevents liveness;
- readiness and detector polling remain closed until recovery completes;
- temporary cleanup RBAC failure is retryable without process restart;
- a terminal saga remains open while Lease/Argo cleanup is incomplete;
- actual disposable Kubernetes action, Lease, rollout verification and cleanup
  succeeded in three consecutive clean-reset cycles;
- cleanup permission loss and restoration completed without a second action.

### Not proven

- production image deployment of this change;
- production startup/recovery behavior;
- real Prometheus verification in this local Kind gate (the verifier is
  deterministic and injected; Kubernetes readiness is real);
- successful autonomous detector-to-action-to-terminal production path;
- forced-wrong production rollback and mentor/on-call acceptance.

TF4AIO-83 remains open. The next owner action is for Thành Tâm to review and
rerun the offline/Kind gate, explain the readiness design and two-phase restore,
then request review of the implementation PR. Another live drill requires the
normal named approvals and a preflight confirming exact image digest, known-good
revision, durable store, cleanup RBAC and zero open saga.
