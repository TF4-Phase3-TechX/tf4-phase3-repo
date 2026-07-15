# D5-PERF-05 evidence submission

## Current verdict

**BLOCKED - DO NOT START LOAD**

The controlled preflight did not authorize Locust or the frontend surge
exercise. The repository does not contain a passing D5-PERF-03 remediation
verdict, the supplied admission evidence says enforcement is inactive, and no
absolute UTC approved window was provided.

Positive live observations were captured without changing the cluster:

- application pods were collected for Pending, restart and OOM review;
- HPA definitions and current metrics were collected;
- node allocation and scheduler headroom were collected;
- deployment state and namespace events were collected.

The Pod and Deployment YAML snapshots are sanitized for GitHub: plaintext
database password fields are replaced with `REDACTED`. Resource configuration,
status, restart history, scheduling fields and secret references are unchanged.

The absence of raw Locust artifacts and same-window dashboard screenshots is
intentional: producing them before the entry gates pass would create an invalid
official performance-regression run.

## Attachment: terminal screenshots

Run these commands from the repository root. Capture each command together
with its output and the terminal clock. These commands are read-only.

### 1. Verdict and immutable run metadata

```powershell
$Run = "docs/evidence/directive-05/official-D5-PERF-20260715T083224Z/performance-regression"
Get-Date -AsUTC
Get-Content "$Run/metadata.md"
Get-Content "$Run/precheck-verdict.md"
```

### 2. Live pod, restart, Pending and OOM state

```powershell
Get-Date -AsUTC
kubectl config current-context
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get pods -o custom-columns='POD:.metadata.name,PHASE:.status.phase,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount,LAST_REASON:.status.containerStatuses[*].lastState.terminated.reason,LAST_FINISHED:.status.containerStatuses[*].lastState.terminated.finishedAt'
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
```

### 3. HPA metric validity

```powershell
Get-Date -AsUTC
kubectl -n techx-tf4 get hpa
kubectl -n techx-tf4 describe hpa checkout
kubectl -n techx-tf4 describe hpa currency
kubectl -n techx-tf4 describe hpa frontend
```

### 4. Scheduler headroom and frontend surge contract

```powershell
Get-Date -AsUTC
kubectl describe nodes
kubectl -n techx-tf4 get deployment frontend -o jsonpath='{.spec.replicas}{" replicas; maxSurge="}{.spec.strategy.rollingUpdate.maxSurge}{"; maxUnavailable="}{.spec.strategy.rollingUpdate.maxUnavailable}{"; cpuRequest="}{.spec.template.spec.containers[0].resources.requests.cpu}{"; memoryRequest="}{.spec.template.spec.containers[0].resources.requests.memory}{"\n"}'
```

Do **not** run `kubectl rollout restart` until the preflight verdict is PASS and
the approved test window is active.

### 5. Admission controls after Security reports enforcement ready

Capture both controls in the target enforcement scope. The negative control
must be rejected and the compliant control must pass.

```powershell
Get-Date -AsUTC
kubectl apply --dry-run=server -f <missing-resource-negative-control.yaml>
kubectl apply --dry-run=server -f <compliant-resource-control.yaml>
```

Replace the placeholders with Security-reviewed manifests. Do not claim PASS
from the historical negative control because it was accepted.

## Attachment: AWS Console screenshots

Use account `511825856493`, region `us-east-1`, and include the browser account,
region and clock in each screenshot.

1. **EKS > Clusters > techx-tf4-cluster > Compute**: capture node group and
   current node count.
2. **EKS > Clusters > techx-tf4-cluster > Resources > Workloads**: filter
   namespace `techx-tf4` and capture workload readiness.
3. **CloudWatch > Container Insights > Performance monitoring**: select the
   cluster and the same absolute UTC window used by the eventual official load
   run; capture CPU, memory, pod restart and Pending evidence.
4. **Managed Grafana/private Grafana**: only after a valid official run, pin
   every required dashboard to the exact metadata T0/T1 UTC window and capture
   Browse/Cart/Checkout SLO, p95, throttling, OOM/restarts, HPA, and node
   headroom.

## GitHub evidence links

- [Performance regression contract](../../D5-PERF-05-performance-regression-contract.md)
- [Preflight verdict](precheck-verdict.md)
- [Run metadata](metadata.md)
- [Raw pod snapshot](raw/pods-before.yaml)
- [Raw HPA snapshot](raw/hpa-before.yaml)
- [Raw node allocation](raw/nodes-before.txt)
- [Raw namespace events](raw/events-before.txt)
- [Preflight harness](../../../../../scripts/d5-performance-regression-preflight.ps1)

## Submission comment

**Đã làm gì?**

Đã định nghĩa contract D5-PERF-05, chạy controlled preflight read-only và sửa
harness để chuỗi `not PASS`, admission evidence không active hoặc window
`NOT PROVIDED` không thể tạo false-positive. Không chạy Locust và không rolling
restart vì entry gate chưa đạt.

**Kiểm chứng bằng cách nào?**

Đã thu snapshot Pod, Deployment, HPA, Node và Event từ cluster; kiểm tra verdict
remediation, admission evidence và approved UTC window. Preflight trả về
`BLOCKED - DO NOT START LOAD` với ba lý do cụ thể.

**Evidence nằm ở đâu?**

Trong thư mục
`docs/evidence/directive-05/official-D5-PERF-20260715T083224Z/performance-regression/`,
gồm `metadata.md`, `precheck-verdict.md`, thư mục `raw/` và tài liệu
`evidence-submission.md` này. Contract và harness nằm lần lượt tại
`docs/evidence/directive-05/D5-PERF-05-performance-regression-contract.md` và
`scripts/d5-performance-regression-preflight.ps1`.
