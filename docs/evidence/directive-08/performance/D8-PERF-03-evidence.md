# D8-PERF-03 Evidence Index

## GitHub Evidence

- Zero-Downtime Managed Data Cutover Contract: [`D8-PERF-03-cutover-contract.md`](./D8-PERF-03-cutover-contract.md)
- Reference Migration Plans:
  - PostgreSQL: [`POSTGRESQL-MIGRATION-PLAN.md`](../../../cdo08/week2/mandate8/implementation/drafts/POSTGRESQL-MIGRATION-PLAN.md)
  - Valkey: [`VALKEY-MIGRATION-PLAN.md`](../../../cdo08/week2/mandate8/implementation/drafts/VALKEY-MIGRATION-PLAN.md)
  - Kafka: [`KAFKA-MIGRATION-PLAN.md`](../../../cdo08/week2/mandate8/implementation/drafts/KAFKA-MIGRATION-PLAN.md)

---

## Commands for Terminal Screenshots

Run these from the repository root after authenticating the approved AWS profile. Capture the complete command and output, including the UTC timestamp.

### Screenshot 1 — Contract and Git Revision
```powershell
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
git rev-parse --short HEAD
git branch --show-current
Get-Content docs/evidence/directive-08/performance/D8-PERF-03-cutover-contract.md -TotalCount 25
```

Suggested filename:
```text
docs/evidence/directive-08/performance/screenshots/d8-perf-03-contract-and-revision.png
```

### Screenshot 2 — Pre-Cutover Health Check (Pods & HPA)
```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
kubectl get pods -n techx-tf4
kubectl get hpa -n techx-tf4 -o wide
```

Suggested filename:
```text
docs/evidence/directive-08/performance/screenshots/d8-perf-03-pre-cutover-pods-hpa.png
```

### Screenshot 3 — EKS Node Resources Check
```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
kubectl get nodes -o wide
kubectl top nodes
```

Suggested filename:
```text
docs/evidence/directive-08/performance/screenshots/d8-perf-03-node-resources.png
```

### Screenshot 4 — DMS Replication Task Status
```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
aws dms describe-replication-tasks --region us-east-1 --query "ReplicationTasks[*].[ReplicationTaskIdentifier,Status,ReplicationTaskStats.PercentComplete]"
```

Suggested filename:
```text
docs/evidence/directive-08/performance/screenshots/d8-perf-03-dms-tasks.png
```

### Screenshot 5 — ElastiCache and MSK Status
```powershell
$env:AWS_PROFILE='511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION='us-east-1'
Get-Date -AsUTC -Format 'yyyy-MM-ddTHH:mm:ssZ'
aws elasticache describe-replication-groups --region us-east-1 --query "ReplicationGroups[*].[ReplicationGroupId,Status]"
aws msk list-clusters --region us-east-1 --query "ClusterInfoList[*].[ClusterName,State]"
```

Suggested filename:
```text
docs/evidence/directive-08/performance/screenshots/d8-perf-03-elasticache-msk.png
```

---

## Submission Comment

**Đã làm gì?**

Đã định nghĩa Hợp đồng Cắt chuyển Dữ liệu Managed Services Không Downtime (Zero-Downtime Managed Data Cutover Contract) cho việc di trú PostgreSQL, Valkey (Redis), và Apache Kafka sang các dịch vụ quản lý RDS, ElastiCache, và MSK. Hợp đồng định nghĩa đầy đủ các mốc thời gian (before/during/after), mốc chỉ số cam kết (Primary Gate: Checkout success rate >= 99% trong toàn bộ window), các ngưỡng hiệu năng/lỗi bổ trợ (Browse/Cart success rate, Checkout latency p95, database connection errors, cache timeout/evictions, message queue consumer lags, OOMKilled, Pending pods, observability availability), các điều kiện kiểm tra đối soát dữ liệu (data parity), các kịch bản dừng khẩn cấp (Stop conditions) và rollback chi tiết cho từng loại hạ tầng.

**Kiểm chứng bằng cách nào?**

Các điều khoản hợp đồng được thiết kế tương thích hoàn toàn với các tài liệu thiết kế di trú CDO-08 (PostgreSQL, Valkey, Kafka Migration Plans). Đã xây dựng sẵn checklist các câu lệnh kiểm tra hạ tầng chi tiết (kubectl, aws cli) để Mentor có thể witness trực tiếp hoặc chạy lại quy trình đánh giá sức khỏe hệ thống và kiểm chứng trạng thái cắt chuyển trước, trong và sau khi thực hiện cutover.

**Evidence nằm ở đâu?**

Hợp đồng cutover và mục lục bằng chứng được lưu tại:
- Hợp đồng: [`docs/evidence/directive-08/performance/D8-PERF-03-cutover-contract.md`](./D8-PERF-03-cutover-contract.md)
- Bằng chứng/Mục lục: [`docs/evidence/directive-08/performance/D8-PERF-03-evidence.md`](./D8-PERF-03-evidence.md)
- Mẫu biên bản kết quả cutover (Verdict Template) nằm ở cuối tệp hợp đồng.
