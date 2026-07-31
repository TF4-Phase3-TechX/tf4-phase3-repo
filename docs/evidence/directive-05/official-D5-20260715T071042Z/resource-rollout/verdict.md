# D5-PERF-03 official run verdict

**RUN_ID:** `D5-20260715T071042Z`  
**Execution model:** single-owner controlled change window  
**Verdict:** **STOPPED — GitOps/Helm ownership conflict**

## What was executed

1. Collected application, HPA, node, resource, Helm and Prometheus baseline.
2. Detected uncontrolled synthetic traffic and stopped the load-generator by
   patching its Deployment to zero replicas.
3. Recovered the observability path and queried Prometheus through a compliant
   short-lived pod in `techx-admission-test`.
4. Rendered and server-dry-ran the reviewed wave overlays.
5. Attempted Wave 1 only (`ad`, `email`, `image-provider`) and waited for each
   Deployment rollout.
6. Stopped before Wave 2 when the applied values did not remain authoritative.

No Wave 2, Wave 3, Wave 4 or Wave 5 resource rollout was attempted.

## Preflight observations

- Application Pending pods: `0`.
- Application CrashLoopBackOff pods: `0` at preflight.
- HPA metrics were available.
- Three worker nodes were Ready.
- ResourceQuota after the load-generator safety stop:
  - CPU limits: `6275m / 8`.
  - CPU requests: `1465m / 4`.
  - Memory limits: `5005Mi / 12Gi`.
  - Memory requests: `3047Mi / 8Gi`.
- Currency had a pre-existing OOM/restart incident under uncontrolled load.

## Baseline performance evidence

Prometheus query results before remediation:

| Metric | Baseline |
|---|---:|
| Browse p95 | approximately `613–839ms` across two samples |
| Browse success | `100%` |
| Cart success | `100%` |
| Checkout success | `0%` |
| Checkout p95 | approximately `4850ms` |
| Load-generator span rate | approximately `13.105/s` |
| Aggregate CPU throttling ratio | approximately `8.67%` |
| Pending metric | `0` |

Checkout logs confirmed the failures were real: order preparation failed while
converting product prices through Currency. Currency had OOMKilled terminations
under the active synthetic load. The load-generator was therefore stopped in
accordance with the task stop condition.

## Why the run stopped

The role can patch Deployments and Helm release Secrets, but full Helm upgrade
failed while reading the existing namespace Role `loadgen-portforward`:

```text
roles.rbac.authorization.k8s.io "loadgen-portforward" is forbidden
```

A scoped `kubectl set resources` fallback successfully created new Wave 1 pods,
and those pods became Ready. Shortly afterward, the live Deployment resources
returned to the previous values. This demonstrates that another authoritative
controller/reconciler owns the desired state. Continuing manual waves would be
non-durable and would not satisfy resource governance.

## Current authoritative resource state

At the final read, all application Deployment containers had CPU/memory
requests and limits. Examples showing the Wave 1 values had reverted:

| Deployment | CPU request/limit | Memory request/limit |
|---|---|---|
| `ad` | `50m / 200m` | `150Mi / 300Mi` |
| `email` | `20m / 100m` | `50Mi / 100Mi` |
| `image-provider` | `10m / 50m` | `25Mi / 50Mi` |

## Rollback

Wave-specific rollback commands are stored in each wave directory. No manual
rollback was executed because the authoritative controller restored the prior
values automatically. The load-generator remains at zero replicas as the
safety-stop state and must only be re-enabled inside an approved load window.

## Required unblock

Use exactly one authoritative delivery path:

1. Merge the reviewed resource values into the GitOps source tracked by the
   production reconciler, then let that controller apply each wave; or
2. Pause the reconciler for the controlled window and grant Helm read access to
   namespace RBAC resources required to compare the release, then resume it
   after committing the same desired state.

After the ownership conflict is resolved, start a new RUN_ID. Do not append new
waves to this stopped run.

