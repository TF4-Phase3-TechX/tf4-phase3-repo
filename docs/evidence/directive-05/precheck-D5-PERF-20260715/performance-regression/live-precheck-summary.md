# D5-PERF-05 live precheck summary

## Passing observations

- AWS account/cluster access succeeded for account `511825856493` and context
  `d5-readonly`.
- All 29 application pods observed during precheck were Running; no pod was
  Pending or in CrashLoopBackOff.
- All Deployment containers had CPU and memory requests and limits.
- HPA metrics were valid:
  - `checkout`: CPU `2%/70%`, replicas `2`, range `2–3`.
  - `frontend`: CPU `13%/70%`, replicas `2`, range `2–3`.
- All three nodes were Ready with MemoryPressure, DiskPressure and PIDPressure
  false.
- Frontend uses RollingUpdate with `maxSurge: 25%` and
  `maxUnavailable: 25%`; current replicas are two.

## Blocking observations

### Resource admission is not enforced

The negative control was accepted:

```text
kubectl apply --dry-run=server -f d5-missing-resources.yaml
pod/d5-perf05-missing-resources created (server dry run)
```

The Pod omitted all CPU/memory requests and limits but otherwise used the same
non-root security shape as the compliant control. Expected result was an
admission rejection. The compliant control was accepted as expected.

The role may create/delete Pods in `techx-admission-test`, but cannot list
ValidatingAdmissionPolicy or bindings. Kyverno CRDs were not present under the
queried resource names.

### New OOM during precheck

```text
kafka/kafka  restarts=1  last=OOMKilled  exit=137
finishedAt=2026-07-15T08:04:09Z
```

Other retained restart history:

- Currency: four restarts, last reason OOMKilled at `2026-07-15T07:13:16Z`.
- Product catalog: seven restarts, last reason Error/exit 1 at
  `2026-07-15T06:30:05Z`.

An official post-enforcement test cannot establish “no new OOM/restart burst”
while a new OOM occurs during its entry check.

### Scheduler headroom is insufficiently demonstrated

| Node | CPU requests | Memory requests | Pressure |
|---|---:|---:|---|
| `ip-10-0-10-231` | `1655m/1930m` (85%) | `2246Mi` (31%) | none |
| `ip-10-0-10-74` | `1720m/1930m` (89%) | `4917Mi` (69%) | none |
| `ip-10-0-11-40` | `1930m/1930m` (100%) | `1158Mi` (16%) | none |

The frontend surge pod requests `100m` CPU and `192Mi` memory. Cluster-wide
capacity may fit it on two nodes, but the 100%-requested node plus topology and
concurrent HPA/load behavior make the surge acceptance unsafe to assert before
the test. No rolling restart was triggered.

### Evidence access is incomplete

- `pods/portforward`: denied.
- actual `services/proxy` request to Locust: denied, despite an earlier
  `kubectl auth can-i` result that appeared permissive for an incorrectly
  specified resource string.
- Therefore Locust idle/user state and same-window private dashboard evidence
  cannot be collected through this role.

## Decision

No load and no rollout restart were started. The run remains a precheck, not an
official performance-regression RUN_ID.
