# D18-COST-03: Tối ưu EBS type, volume sizing và storage lifecycle

> Jira: [C0G-99](https://ngonguyentruongan2907.atlassian.net/browse/C0G-99)
> Evidence: AWS CLI và `kubectl` read-only collection, `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z`; raw command output không commit vào repository.
> Trạng thái: **In Progress**. Report này đối chiếu trực tiếp Scope và Acceptance Criteria của C0G-99 với live AWS/Kubernetes baseline. Chưa có gp2 migration, right-sizing hoặc lifecycle change được xác nhận hoàn tất.

## 1. Measurement contract và dependency

| Nội dung | Giá trị |
|---|---|
| Live inventory UTC | `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z` |
| AWS account / Region đã kiểm tra | `511825856493` / `us-east-1` |
| Cost Explorer window | `[2026-07-15T00:00:00Z, 2026-07-22T00:00:00Z)`; daily result đang `Estimated=true` |
| Jira dependency | D18-COST-01 baseline và D18-COST-02 owner validation. D18-COST-01 baseline nằm tại [C0G-97 report](./d18-cost-01-baseline-usage-top-cost-drivers.md); owner validation chưa hoàn tất. |
| Primary metric | Type, provisioned/used GiB, GB-Month, IOPS, throughput, retention và restore result. Không dùng USD. |

Evidence source: AWS CLI và `kubectl` read-only collection; raw command output không commit vào repository.

Cost Explorer baseline: `EBS:VolumeUsage.gp2 = 13.801 GB-Month`, `EBS:VolumeUsage.gp3 = 25.673 GB-Month`, `EBS:SnapshotUsage = 2.139 GB-Month`. Đây là billing usage trong window ngắn; không dùng để tính used GiB hoặc target size.

## 2. Bảng volume theo Jira

`Used`, `Utilization` và `Target size` chưa có live filesystem/data evidence. Không suy diễn từ provisioned size. `TBD` nghĩa là acceptance item chưa đạt, không phải giá trị 0.

| Volume | Current type | Size | Used | Utilization | Target type | Target size | Decision |
|---|---|---:|---|---|---|---|---|
| `vol-0024e483121338f0e`, OpenSearch `techx-observability/opensearch-opensearch-0` | gp2 | `40 GiB` | TBD | TBD | gp3 | TBD | Thu index/filesystem usage, IOPS/throughput và growth window. Backup/copy/cutover/rollback trước migration. |
| `vol-051c0352bdfaceb5d`, Prometheus `techx-observability/prometheus` | gp3, `3000 IOPS`, `125 MiB/s` | `20 GiB` | TBD | TBD | gp3 | TBD | Không cần type migration. Đo TSDB usage/growth và performance trước right-size. PV name `gp2-retain` cần reconcile. |
| `vol-0cb8c31ac039d6597`, PostgreSQL `techx-tf4/postgresql-pvc` | gp2 | `10 GiB` | TBD | TBD | gp3, nếu owner xác nhận workload còn dùng volume này | TBD | AWS `available` nhưng PV/PVC vẫn `Bound`; chặn cleanup/migration đến khi owner xác nhận attachment, cutover và restore state. |
| `vol-01a7d9f5b6270c06d`, Kafka `techx-tf4/kafka-pvc` | gp2 | `10 GiB` | TBD | TBD | gp3, nếu owner xác nhận workload còn dùng volume này | TBD | AWS `available` nhưng PV/PVC vẫn `Bound`; cùng gate PostgreSQL. |
| `vol-0878313d6b2957e96`, Valkey `techx-tf4/valkey-cart-pvc` | gp2 | `5 GiB` | TBD | TBD | gp3, nếu owner xác nhận workload còn dùng volume này | TBD | AWS `available` nhưng PV/PVC vẫn `Bound`; cùng gate PostgreSQL. |
| `vol-0ce59bf32f9aea7d5`, Released PV `techx-observability/postgresql-pvc` | gp2 | `10 GiB` | Not applicable | Not applicable | Not applicable | Not applicable | Orphan recovery-chain candidate, không phải right-size candidate. Recovery owner quyết định cleanup hoặc retention/expiry cùng snapshot. |

Evidence: EC2 volumes, PVs, PVCs.

Node/root volumes gp3 trong EC2 inventory không chứng minh persistent PVC storage đã gp3. Toàn bộ inventory hiện có `5` gp2 volumes / `75 GiB` và `6` gp3 volumes / `130 GiB` tại `us-east-1`.

## 3. gp2 to gp3, sizing, IOPS và throughput

StorageClass hiện có chỉ là `gp2` và `gp2-retain`, dùng in-tree `kubernetes.io/aws-ebs`; `gp2-retain` không cho expansion: StorageClasses.

Cách triển khai cho từng workload stateful:

1. Owner xác nhận workload, volume attachment, RPO/RTO, change window và rollback owner.
2. Thu filesystem/data used GiB, free space, growth rate, peak usage, EBS IOPS, throughput, queue length và latency trong window định trước.
3. Tạo CSI-based `gp3` hoặc `gp3-retain` StorageClass bằng capability EBS CSI hiện có. Không cài thêm driver.
4. Chụp backup có purpose/expiry, tạo gp3 PVC, copy hoặc restore data, rồi cut over trong maintenance window.
5. Kiểm tra data integrity, application health, trace lookup, log search, dashboard, alert và SLO. Giữ PV/EBS cũ đến hết rollback window đã duyệt.
6. Chỉ sau rollback window mới cleanup PV/EBS cũ qua GitOps/Kubernetes hoặc Terraform ownership path, rồi nộp after-scan.

Không resize trực tiếp volume đang `available` nếu PV/PVC vẫn `Bound` tham chiếu. Không chọn IOPS, throughput hoặc target GiB khi chưa có workload measurement.

## 4. Snapshot, AMI và S3 lifecycle

| Jira scope | Live baseline | Gap và closure action |
|---|---|---|
| Snapshot lifecycle | `9` self-owned snapshots; DLM trả `Policies: []`. Logical source volume size tổng `76 GiB`; snapshot billing incremental. | Recovery owner gán purpose/expiry. Implement DLM hoặc documented exception; after output phải chứng minh policy/expiry. Không xóa cutover or recovery snapshot chỉ vì tuổi. |
| AMI expiry | Không có self-owned AMI tại `us-east-1`. | Re-scan every enabled region. Nếu có AMI, bổ sung owner và expiry; nếu không có, lưu empty results cho account scope. |
| ECR lifecycle | `techx-corp` có policy expire untagged image sau 7 ngày và giữ tối đa 50 image. | Giữ policy; thu image count/size before and after nếu chọn ECR làm action. |
| S3 lifecycle/tier | CloudTrail và EKS audit buckets không có lifecycle configuration; Object Lock `COMPLIANCE` 90 ngày. Bucket `huyhoang1234` chưa rõ owner/purpose. | Forensic/storage owner thiết kế transition/expiry sau compliance floor. Không shorten/delete before 90 days. Xác nhận owner/purpose trước khi thay đổi bucket chưa phân loại. |

Evidence: DLM, snapshots, AMIs, ECR lifecycle, buckets, S3 command status.

## 5. Restore và rollback evidence

| Evidence cần có | Trạng thái | Điều kiện đạt |
|---|---|---|
| Backup/snapshot trước change | Chưa có per-migration record | Có owner, purpose, timestamp, source volume/PVC và restore procedure. |
| Restore data test | Chưa có | Restore vào target gp3 PVC hoặc isolated test target; compare data/application result. |
| Cutover plan | Chưa có | Maintenance window, owner, start/end, validation checklist và rollback trigger. |
| Rollback path | Chưa có | Giữ original PV/EBS trong approved rollback window; test hoặc document rollback operation. |
| Post-cutover validation | Chưa có | Application health, data integrity, SLO và observability checks đạt. |

Các snapshot hiện tại là recovery artifacts, không phải proof rằng restore path đã được test cho migration này.

## 6. Acceptance criteria status

| Acceptance criterion | Status | Evidence hoặc closure action |
|---|---|---|
| Có inventory toàn bộ EBS trong scope | Partially met | Section 2 có `us-east-1` inventory; cần enabled-region scan cho account scope. |
| Không còn gp2 không có approved reason | Not met | Five gp2 volumes tồn tại. Migration hoặc approved exception per volume cần có. |
| gp3 có IOPS/throughput phù hợp | Not met | Prometheus inventory ghi `3000 IOPS`/`125 MiB/s`; thiếu measurement và workload validation. |
| Volume right-size có growth headroom | Not met | `Used`, utilization, growth and target GiB đều chưa có. |
| Snapshot có retention/lifecycle | Not met | Không có DLM policy; cần owner/expiry plus policy or exception. |
| AMI có owner và expiry | Partially met | `us-east-1` không có self-owned AMI; enabled-region scan còn thiếu. |
| S3 có lifecycle khi trong scope | Not met | CloudTrail/EKS audit chưa lifecycle; compliance floor cần giữ. |
| Không mất dữ liệu hoặc restore capability | Not met | Chưa có restore/cutover/rollback validation. |
| Có storage usage trước và sau | Not met | Chưa có used data baseline hoặc post-change window. |

## 7. Điều kiện đóng C0G-99

C0G-99 chỉ hoàn thành khi every row in Section 2 has live `Used`, utilization, target decision and owner approval; every remaining gp2 volume has migrated to gp3 or an approved exception; IOPS/throughput and growth headroom are validated; snapshot/AMI/S3 lifecycle evidence is available; and migration records prove backup, restore, rollback, post-cutover application/data/SLO validation. Add this report, its raw evidence links and after-scan links to C0G-99 for mentor review.
