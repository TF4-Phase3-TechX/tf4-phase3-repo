# D5-PERF-03 evidence submission

## Attachment: terminal screenshots

Run the commands below from the repository root and capture the terminal after
each command. They are read-only and do not restart or modify a workload.

```powershell
$Run = "docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout"
Get-Content "$Run/verdict.md"
```

Capture this output to show the controlled-window verdict, executed scope,
baseline SLO signals, safety stop, and required unblock.

```powershell
$Run = "docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout"
Get-Content "$Run/baseline/raw/pods-before.txt"
Get-Content "$Run/01-low-risk-stateless/raw/rollout-status.txt"
Get-Content "$Run/01-low-risk-stateless/raw/warnings-after.txt"
```

Capture this output to show pod state and Wave 1 verification.

```powershell
$Run = "docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout"
Get-Content "$Run/baseline/raw/prometheus-before.txt"
Get-Content "$Run/01-low-risk-stateless/rollback-command.txt"
```

Capture this output to show the before dashboard-equivalent Prometheus sample
and the exact rollback command. An after comparison is intentionally absent:
the run stopped when the authoritative reconciler reverted Wave 1, before a
valid post-remediation observation window could be established.

Optional live-state screenshot, after AWS/EKS authentication is configured:

```powershell
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get deploy ad email image-provider `
  -o custom-columns='NAME:.metadata.name,READY:.status.readyReplicas,CPU_REQ:.spec.template.spec.containers[0].resources.requests.cpu,CPU_LIMIT:.spec.template.spec.containers[0].resources.limits.cpu,MEM_REQ:.spec.template.spec.containers[0].resources.requests.memory,MEM_LIMIT:.spec.template.spec.containers[0].resources.limits.memory'
```

Do not scale the load generator or execute another rollout merely to obtain a
screenshot. A new live run requires an approved window and an authoritative
GitOps delivery path.

## GitHub evidence

- Rollout design and wave overlays: `deploy/resource-remediation/README.md`
- Controlled rollout harness: `scripts/resource-rollout.sh`
- Official run verdict: `docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout/verdict.md`
- Raw evidence: `docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout/baseline/raw/`
  and `01-low-risk-stateless/raw/`
- Rollback evidence: `docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout/01-low-risk-stateless/rollback-command.txt`

## Submission comment

**Đã làm gì?**  Đã chuẩn bị rollout resources theo 5 wave, kiểm tra Helm/admission
server-side dry-run, thu baseline và thực hiện Wave 1 trong controlled window.
Run được dừng trước Wave 2 khi phát hiện Helm thiếu quyền đọc namespace Role và
GitOps reconciler hoàn nguyên resource values; load generator được giữ ở 0 để
ngăn traffic ngoài approved window.

**Kiểm chứng bằng cách nào?**  Đã kiểm tra pod/Deployment/HPA/node/quota, Helm
lint và server-side dry-run, rollout status, Pending/CrashLoop/OOM warning, cùng
Prometheus Browse/Cart/Checkout và CPU throttling. Verdict của run là `STOPPED`,
không phải hoàn tất 5 wave.

**Evidence nằm ở đâu?**  Trong
`docs/evidence/directive-05/official-D5-20260715T071042Z/resource-rollout/`, gồm
`verdict.md`, baseline raw output, Wave 1 raw output và rollback command. Thiết
kế/harness nằm tại `deploy/resource-remediation/` và
`scripts/resource-rollout.sh`.
