# D3-PERF-02 Evidence Index

## GitHub evidence

- Test contract: [`02-maintenance-load-test-contract.md`](./02-maintenance-load-test-contract.md)
- Approved harness: [`scripts/run-load-test-task4.sh`](../../../../scripts/run-load-test-task4.sh)
- Runtime evidence root after an official run:
  `docs/evidence/directive-03/performance/runs/<RUN_ID>/`

## Commands for terminal screenshots

Run these from the repository root after authenticating the approved AWS
profile. Capture the complete command and output, including the UTC timestamp.

### Screenshot 1 — contract and Git revision

```powershell
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
git rev-parse --short HEAD
git branch --show-current
Get-Content docs/evidence/directive-03/performance/02-maintenance-load-test-contract.md -TotalCount 25
```

Suggested filename:

```text
docs/evidence/directive-03/performance/screenshots/d3-perf-02-contract-and-revision.png
```

### Screenshot 2 — pre-test workload and HPA state

```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
kubectl get pods -n techx-tf4
kubectl get hpa -n techx-tf4 -o wide
```

Suggested filename:

```text
docs/evidence/directive-03/performance/screenshots/d3-perf-02-pods-hpa.png
```

### Screenshot 3 — node readiness and pressure

```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
kubectl get nodes -o wide
kubectl describe nodes | Select-String -Pattern 'Name:|MemoryPressure|DiskPressure|PIDPressure|Ready' -Context 0,1
kubectl top nodes
```

Suggested filename:

```text
docs/evidence/directive-03/performance/screenshots/d3-perf-02-node-capacity.png
```

### Screenshot 4 — harness guard and configuration

This command is read-only. If `pods/exec` is not granted, capture the first
three commands and record process inspection as `NOT AUTHORIZED`.

```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
kubectl get deploy load-generator -n techx-tf4
kubectl get pods -n techx-tf4 -l app.kubernetes.io/name=load-generator
kubectl get deploy load-generator -n techx-tf4 -o jsonpath='{.spec.template.spec.containers[0].env}'
kubectl exec -n techx-tf4 deploy/load-generator -- pgrep -af locust
```

Suggested filename:

```text
docs/evidence/directive-03/performance/screenshots/d3-perf-02-harness-guard.png
```

### Screenshot 5 — raw Locust artifacts after official execution

```powershell
$runId='<RUN_ID>'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
Get-ChildItem "docs/evidence/directive-03/performance/runs/$runId/raw-locust" |
  Select-Object Name,Length,LastWriteTimeUtc
Get-Content "docs/evidence/directive-03/performance/runs/$runId/verdict.md"
```

Suggested filename:

```text
docs/evidence/directive-03/performance/screenshots/d3-perf-02-raw-artifacts-verdict.png
```

## AWS Console screenshot

For a maintenance run involving an EKS managed node group:

1. Open AWS Console in account `511825856493`, region `us-east-1`.
2. Go to **EKS → Clusters → techx-tf4-cluster → Compute**.
3. Open the target managed node group.
4. Capture node-group status, desired/min/max size and update health. Do not
   include browser credentials, access keys, session tokens or unrelated account
   information.
5. Save as:

```text
docs/evidence/directive-03/performance/screenshots/d3-perf-02-eks-nodegroup.png
```

## Submission comment

**Đã làm gì?**

Đã xây dựng maintenance load-test contract cho 200 concurrent users, xác định
ramp-up, steady-state, maintenance timestamp, ramp-down, Browse/Cart/Checkout
weights, volume guards, stop conditions, raw artifact contract và rerun runbook.
Harness được cập nhật để ramp đúng 60 giây và lưu đầy đủ Locust artifacts theo
RUN_ID.

**Kiểm chứng bằng cách nào?**

Đối chiếu contract với SLO gốc; kiểm tra `git diff --check`; kiểm tra harness
nhận users/spawn/timeline/evidence path; pre-test runtime được xác minh bằng
Pods, HPA, Nodes, Node conditions và Metrics API. Official maintenance result
chỉ được kết luận sau khi chạy trong approved absolute UTC window.

**Evidence nằm ở đâu?**

Contract và evidence index nằm trong
`docs/evidence/directive-03/performance/`. Raw CSV/HTML, runtime snapshots,
dashboard screenshots và verdict của mỗi lần chạy nằm tại
`docs/evidence/directive-03/performance/runs/<RUN_ID>/`.

