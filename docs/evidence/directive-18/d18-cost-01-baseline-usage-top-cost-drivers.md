# D18-COST-01: Thu baseline usage ngoài compute và xếp hạng top cost drivers

> Jira: [C0G-97](https://ngonguyentruongan2907.atlassian.net/browse/C0G-97)
> Evidence: AWS CLI và `kubectl` read-only collection, `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z`; raw command output không commit vào repository.
> Trạng thái: **In Progress**. Đây là report baseline từ live AWS/Kubernetes, không phải bằng chứng đã giảm cost driver.

## 1. Measurement contract

| Nội dung | Giá trị |
|---|---|
| Live inventory UTC | `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z` |
| AWS account / Region đã kiểm tra | `511825856493` / `us-east-1` |
| Cost Explorer window | `[2026-07-15T00:00:00Z, 2026-07-22T00:00:00Z)` |
| Cost Explorer state | Daily result hiện `Estimated=true`; phải re-query settled window trước khi dùng làm baseline/after chính thức cho change. |
| Primary metric | Usage unit, không dùng USD vì account chạy credit. |
| Inventory source | AWS CLI và `kubectl` read-only; command output được giữ ngoài repository. |

Evidence source: AWS CLI và `kubectl` read-only collection; raw command output không commit vào repository.

## 2. Baseline theo phạm vi C0G-97

| Jira scope | Live baseline | Evidence | Trạng thái và việc cần thu tiếp |
|---|---|---|---|
| EBS volume count và GB theo type | `11` volumes: gp2 `5` volumes / `75 GiB`; gp3 `6` volumes / `130 GiB`. Cost Explorer: gp2 `13.801 GB-Month`, gp3 `25.673 GB-Month`. | EC2 volumes, Cost Explorer | Có cho `us-east-1`. Cần enabled-region scan để khẳng định account scope. |
| Unattached EBS count và GB | `4` `available` gp2 volumes / `35 GiB`. Trong đó chỉ `vol-0ce59bf32f9aea7d5` (`10 GiB`) đã xác nhận thuộc Released PV recovery chain; 3 volume còn lại vẫn có PV/PVC `Bound`. | EC2 volumes, PVs, PVCs | Không coi 3 volume Bound là orphan. Owner phải reconcile attachment/cutover state. |
| Snapshot count và GB | `9` self-owned snapshots; source logical size tổng `76 GiB`. Cost Explorer snapshot usage `2.139 GB-Month`. Snapshot billing là incremental, không suy ra từ logical source size. | snapshots, Cost Explorer | Có cho `us-east-1`; cần owner/purpose/expiry và enabled-region scan. |
| AMI count | `0` self-owned AMI tại `us-east-1`. | AMIs | Cần enabled-region scan trước khi kết luận toàn account. |
| S3 storage theo storage class | Bucket inventory có `9` buckets, nhưng chưa có `BucketSizeBytes` hoặc storage-class usage. | bucket inventory | **Thiếu.** Storage owner thu S3 Storage Lens hoặc CloudWatch `BucketSizeBytes` theo StorageType cho một UTC window. |
| NAT Gateway hours | Cost Explorer `NatGateway-Hours`: `160 Hrs`. | Cost Explorer | Có, nhưng settled re-query cần có trước after comparison. |
| NAT processed GB | Cost Explorer `NatGateway-Bytes`: `30.585 GB`. CloudWatch four directional counters: `33.237 GB`; đây không phải billing total. | Cost Explorer, NAT CloudWatch counters | Có. Cần Flow Logs để phân loại destination trước khi chọn VPC Endpoint. |
| Cross-AZ GB | Chưa có cluster-only cross-AZ bytes. Không có VPC Flow Logs. | Flow Log inventory | **Thiếu.** CDO-08 duyệt metadata-only Flow Logs; thu bảy ngày hoàn chỉnh và tách traffic theo AZ/workload. |
| Log ingest GB/ngày | Cost Explorer CloudWatch vended logs: `98.788 GB` trong window. Không có daily per-log-group ingest measurement. | Cost Explorer | **Thiếu phần per-day/per-log-group.** Observability owner thu `IncomingBytes` theo log group và UTC day. |
| Log stored GB | EKS control-plane log group: `10,258,951,213` bytes (`10.259 GB` decimal), retention `90` days. CloudTrail: `140,673,700` bytes (`0.141 GB` decimal), retention `90` days. | CloudWatch log groups | Có stored bytes/retention hiện tại. |
| Trace spans/giây và trace storage | Chưa có sanitized runtime trace-rate, sampling hoặc OpenSearch/Jaeger storage evidence. Full ConfigMap/workload/pod exports bị loại khỏi raw collection vì có thể lộ secret-reference metadata. | sensitive export omission | **Thiếu.** Observability owner thu sanitized collector config, trace rate và index size/age. |
| Prometheus active series, samples/giây, retention | Không có runtime active-series hoặc sample ingestion trong live collection. Repository values không phải live evidence. | sensitive export omission | **Thiếu.** Thu `prometheus_tsdb_head_series`, ingestion rate, retention và top-cardinality labels từ runtime endpoint. |
| Orphan resource count | Đã xác nhận `3` AWS billable cleanup candidates: unassociated EIP `eipalloc-02d48563f995b22e7`, Released-PV EBS `vol-0ce59bf32f9aea7d5`, snapshot `snap-00b810dbb6c60cb24`. NLB `k8s-techxobs-postgres-8d69757ceb` is active but its target group has zero registered target; it remains pending REL-15 migration-owner decision. | EIPs, volumes, snapshots, load balancers, NLB target health | Cần owner-approved cleanup/retention decision và after-scan. Chưa có account-wide count. |

## 3. Jira output: top cost drivers

Không cộng `GB`, `GB-Month`, `Hrs`, resource count và telemetry series thành một total giả. Thứ tự dưới đây là thứ tự xử lý dựa trên live baseline, mức độ xác định của action và safety gate. Nó không phải bảng quy đổi USD.

| Rank | Cost driver | Usage unit | Baseline | Evidence source | Owner |
|---:|---|---|---|---|---|
| 1 | Orphan cleanup candidates | `Hrs`, resource count, `GiB` | Idle public IPv4 `157.080 Hrs`; 1 confirmed EIP; Released recovery chain gồm 1 EBS `10 GiB` và 1 snapshot. | Cost Explorer, EIPs, volumes, snapshots | Terraform owner, recovery owner, REL-15 owner |
| 2 | EBS gp2 và snapshot lifecycle | `GB-Month` | gp2 `13.801 GB-Month`; snapshots `2.139 GB-Month`; 5 gp2 volumes / `75 GiB`; 9 snapshots. | Cost Explorer, volumes, snapshots | Stateful workload owner, recovery owner |
| 3 | NAT data path | `GB`, `Hrs` | `30.585 GB`; `160 Hrs`. | Cost Explorer | CDO-08 and network owner |

CloudWatch vended log usage is `98.788 GB` in the same Cost Explorer window. It is not selected for the first change because audit/forensic rules and live telemetry configuration have not been validated. No telemetry reduction is approved from stored-byte data alone.

## 4. Dependencies and evidence gap backlog

C0G-97 has no Jira dependency to start. Completion depends on the owners below supplying the missing live measurements and on C0G-99/C0G-98 changes producing post-change evidence where relevant.

| Missing evidence | Owner | Closure collection |
|---|---|---|
| S3 size by storage class | S3/storage owner | Storage Lens or CloudWatch `BucketSizeBytes` grouped by `StorageType`, exact UTC window. |
| EBS used GB | Stateful workload owner | Filesystem/data usage plus growth window per PVC. |
| Cross-AZ GB and NAT destination ranking | CDO-08/network owner | Approved Flow Logs, seven complete days, destination and AZ aggregation. |
| Log ingest GB/day | Observability owner | CloudWatch `IncomingBytes` per group/day. |
| Trace volume and storage | Observability owner | Sanitized deployed config, sampling, trace rate, OpenSearch/Jaeger index size and retention. |
| Prometheus series and ingest rate | Observability owner | Runtime PromQL for head series, ingestion rate, retention and label cardinality. |
| Account-wide orphan/AMI/EBS inventory | AWS account owner | Repeat read-only scan in every enabled region. |

## 5. Acceptance criteria status

| Acceptance criterion | Status | Evidence or closure action |
|---|---|---|
| Có exact UTC baseline window | Met | Section 1. |
| Không dùng USD làm primary metric | Met | Sections 1 to 3 use usage units only. |
| Có usage unit rõ cho từng cost driver | Met | Section 3. |
| Có top 3 cost drivers ngoài compute | Met as action-priority ranking | Section 3; units are not combined. |
| Có console hoặc CloudWatch evidence | Partially met | Raw AWS CLI API evidence exists; remaining runtime telemetry/S3 evidence is listed in Section 4. |
| Có owner cho từng driver | Met | Section 3 and Section 4. |
| Có link evidence trong Jira | Pending Jira update | Add this report and the linked raw evidence/SOT to C0G-97. |

## 6. Điều kiện đóng C0G-97

C0G-97 hoàn thành khi toàn bộ dòng trong Section 2 có baseline live evidence hoặc explicit `NOT_APPLICABLE`, bảng Section 3 có evidence link/owner cho từng row, và mentor có thể mở raw evidence/console để xem. Nếu C0G-97 được dùng để chứng minh reduction cho Mandate 18, phải bổ sung settled matched before/after window, configuration revision, usage delta và SLO/investigation result. Baseline một mình không chứng minh reduction.
