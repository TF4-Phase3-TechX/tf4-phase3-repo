# Mandate 18: Kế hoạch triển khai cắt hidden cost ngoài compute

> **Phạm vi triển khai:** hệ thống chính tại `us-east-1`.
>
> **Mục đích:** Source of Truth cho việc triển khai [`MANDATE-18-cost-beyond-compute.md`](workspace/FINAL-PHASE/tf4-phase3-repo/mandates/MANDATE-18-cost-beyond-compute.md). Tài liệu chuyển baseline đo được và cấu hình hiện hành trong repository thành các bước triển khai có acceptance evidence.

## 1. Mục tiêu và nguyên tắc

Mandate 18 cắt usage ngoài node compute ở năm nhóm: orphaned resources, storage/lifecycle, NAT/cross-AZ, telemetry và top non-compute cost driver. Account chạy bằng credit nên bằng chứng chính là usage: resource count, GiB, GiB-month, hours, processed GB, stored bytes, retention days, trace rate và active series.

Mỗi thay đổi được triển khai theo quy trình:

1. ghi baseline, UTC window, Region và configuration revision;
2. thay đổi qua ownership path hiện hữu: Terraform, Helm/GitOps hoặc AWS Load Balancer Controller;
3. thu after evidence cùng phạm vi, đơn vị và thời lượng;
4. kiểm tra application health, SLO, trace lookup, log search, dashboard và alert liên quan.

Không xóa trực tiếp resource do Terraform, Helm/GitOps hoặc controller quản lý. Dữ liệu điều tra sự cố giữ nguyên COMPLIANCE retention floor 90 ngày.

## 2. Baseline triển khai

| Nội dung | Giá trị đã đo |
|---|---|
| Live inventory timestamp | `2026-07-24T05:48:29Z` |
| Region | `us-east-1` |
| Nguồn baseline | Sanitized AWS/Kubernetes current-state evidence; resource identifiers được giữ trong restricted evidence store |
| Kubernetes scope | PV, PVC, VolumeAttachment, StorageClass, Pod, Service, EndpointSlice, Ingress và TargetGroupBinding |
| AWS scope | EIP, EBS, snapshot, AMI, DLM, NAT, endpoint, Flow Logs, ALB/NLB/TG, Cost Explorer, CloudWatch, EKS, RDS, Backup, ElastiCache, MSK, CloudTrail và Config |
| Cost Explorer window | `[2026-07-15, 2026-07-22)`; `Estimated=true` được dùng làm baseline triển khai NAT/cross-AZ |

Raw identifiers, account identity, IP, ARN và bucket name không nằm trong bản phân phối này. Evidence nộp mentor dùng count, resource class, ownership, relationship, timestamp và sanitized command result.

## 3. Kế hoạch tổng thể

| Workstream | Baseline đã đo | Thay đổi triển khai | Acceptance evidence |
|---|---|---|---|
| 1. Orphaned resources | 1 Terraform-managed unassociated EIP; 1 Released PV/EBS/snapshot chain; 1 migration NLB không còn traffic/backend | Dọn qua Terraform và Helm/GitOps/controller | Candidate count về 0; after inventory và ownership change record |
| 2. Storage/lifecycle | OpenSearch dùng gp2 40 GiB; 4 available gp2 volume/35 GiB; 9 untagged snapshots; 0 DLM | Tạo CSI gp3 classes, migrate stateful data, thêm snapshot/S3 lifecycle | Runtime volume type, migration validation, DLM/lifecycle output |
| 3. NAT/cross-AZ | 1 NAT, 0 endpoint, 0 Flow Logs; 168 NAT hours, 30.953530 processed GB, 643.682040 regional-transfer GB/7 ngày | Thu Flow Logs, triển khai S3 Gateway Endpoint và endpoint được traffic chứng minh, tối ưu AZ path | Matched NAT/cross-AZ before-after và application health |
| 4. Telemetry | EKS/CloudTrail retention 7 ngày; Prometheus 174,964 active series; OpenSearch ISM chưa gắn vào index hiện hành | Gắn ISM, expose trace rate, áp dụng một sampling/cardinality control | Volume/cardinality before-after và investigation checks |
| 5. Top driver | Data-transfer là driver usage lớn nhất đã đo trong nhóm network; idle EIP/storage/NLB là usage không phục vụ main flow | Thực hiện network reduction và các cleanup ít blast radius theo thứ tự mục 8 | Cùng-unit delta, deployment revision và SLO evidence |

## 4. Workstream 1 — orphaned resources và load balancer

### 4.1 Resource cleanup plan

| Resource class | Baseline live tại `us-east-1` | Implementation plan | After evidence |
|---|---|---|---|
| Unassociated EIP | 1 allocation không có association; có Terraform ownership tag | Xác định Terraform address/state, bỏ resource khỏi configuration theo owner approval, review plan rồi apply | Unassociated allocation count `1 → 0`; Terraform apply record |
| Released recovery chain | 1 PV `Released`/`Retain` map tới 1 available gp2 EBS 10 GiB và 1 completed snapshot | Recovery owner xác nhận hết restore window; xóa PV qua Kubernetes/GitOps; xóa EBS qua approved ownership path; xóa snapshot hoặc gắn owner/expiry | PV/EBS candidate count về 0; snapshot register/lifecycle cập nhật |
| Bound-but-detached volumes | 3 gp2 volume 5/10/10 GiB ở AWS state `available`; PV/PVC vẫn `Bound`; không có VolumeAttachment hoặc Pod consumer | Reconcile Valkey/PostgreSQL/Kafka cutover state; cập nhật PV/PVC ownership; đưa volume còn cần vào gp3 migration, đưa recovery artifact hết hạn vào cleanup change | PV/PVC/VolumeAttachment/Pod/EBS mapping nhất quán sau change |
| Snapshots | 9 self-owned completed snapshots, untagged; logical source size 76 GiB | Lập owner/purpose/expiry register; đưa recurring recovery set vào DLM; xóa snapshot hết retention qua approved lifecycle path | 100% snapshot có owner/purpose/expiry hoặc DLM policy |
| AMI | 0 self-owned AMI | Giữ inventory check trong after scan | Self-owned AMI count giữ ở 0 |

### 4.2 Giữ internet-facing ALB cho main flow

Live routing đã xác nhận:

```text
Internet → ALB:80 → frontend-proxy:8080 → frontend và internal APIs
```

- Ingress dùng `scheme: internet-facing`, target type `ip` và route `/` tới `frontend-proxy:8080`: [`deploy/ingress.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/deploy/ingress.yaml).
- Listener rule forward tới target group có 2 healthy IP targets, khớp 2 ready `frontend-proxy` endpoints ở hai AZ.
- Window `[2026-07-17T00:00Z, 2026-07-24T06:00Z]` ghi nhận:
  - `RequestCount`: `22,938`;
  - `ProcessedBytes`: `134,814,795` bytes;
  - `NewConnectionCount`: `7,642`;
  - mỗi daily period đều có traffic.

Implementation plan: giữ ALB, Ingress, listener rule và frontend-proxy target group. Sau mỗi network/storage change, chạy external storefront request và xác nhận hai target healthy, HTTP success rate, latency và controller reconciliation.

### 4.3 Retire internal PostgreSQL migration NLB

NLB này là REL-15 migration-only bridge, không nằm trong main storefront flow:

- Helm template khai báo internal NLB TCP/5432 cho PostgreSQL migration: [`postgresql-migration-bridge.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-chart/templates/postgresql-migration-bridge.yaml).
- Live Service vẫn render nhưng EndpointSlice rỗng.
- Target group có 0 registered target.
- Không có DMS replication instance, task hoặc endpoint.
- Toàn bộ NLB lifetime được kiểm tra không có datapoint cho `ProcessedBytes`, `NewFlowCount_TCP` và `ActiveFlowCount_TCP`.

Implementation sequence:

1. lưu final sanitized evidence cho DMS count, EndpointSlice, target health và NLB traffic;
2. đặt `postgresqlMigrationBridge.enabled: false` trong deployed Helm values source;
3. render/lint chart và sync qua GitOps;
4. để AWS Load Balancer Controller xóa Service-owned NLB, listener và target group;
5. xác nhận Service, TargetGroupBinding, NLB và target group đã được dọn;
6. chạy storefront/API smoke test để chứng minh main flow không phụ thuộc migration bridge.

## 5. Workstream 2 — gp3, right-sizing và lifecycle

### 5.1 Persistent storage plan

| Data set | Baseline live | Implementation plan |
|---|---|---|
| OpenSearch | gp2 40 GiB, `in-use` | Tạo gp3 PVC, snapshot/backup, restore/copy data, cutover trong maintenance window, kiểm tra index health/search/ingestion, giữ old PV trong rollback window rồi dọn |
| Prometheus | backing EBS gp3 20 GiB; PV/class naming còn `gp2-retain` | Reconcile PV/StorageClass declaration với runtime gp3; giữ size đến khi có growth/headroom window; kiểm tra TSDB query và scrape health |
| Kafka/PostgreSQL/Valkey retained data | gp2 10/10/5 GiB trong nhóm Bound-but-detached | Hoàn tất mapping/cutover reconciliation, sau đó migrate từng data set sang CSI gp3 bằng backup/restore và rollback record |

Repository hiện có EBS CSI capability nhưng cluster chỉ có `gp2` và `gp2-retain` dùng in-tree provisioner. Implementation:

1. thêm CSI-backed `gp3` và `gp3-retain` StorageClass, reuse pattern từ [`storageclass-prometheus.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-chart/templates/storageclass-prometheus.yaml);
2. cấu hình reclaim policy và volume expansion rõ ràng;
3. migrate từng PVC qua volume mới; không dùng thay đổi `storageClassName` như một cơ chế migrate PVC hiện hữu;
4. đo filesystem usage, growth, IOPS, throughput, queue depth và latency trong window bao phủ peak trước khi right-size;
5. chỉ xóa old PV/EBS khi integrity, application SLO và rollback window hoàn tất.

### 5.2 Snapshot và S3 lifecycle

- Tạo snapshot register gồm workload, owner, purpose, creation/cutover context, retention và expiry.
- Tạo DLM policy qua Terraform cho recovery snapshots có lịch lặp lại; snapshot migration/cutover dùng expiry tag theo owner-approved rollback window.
- EKS audit-log và CloudTrail S3 giữ Object Lock COMPLIANCE 90 ngày.
- Thêm Terraform lifecycle transition/expiration bắt đầu sau retention floor; bao gồm current và noncurrent versions, storage tier, retrieval expectation và forensic-owner approval.
- Giữ ECR lifecycle hiện hành: untagged image hết hạn sau 7 ngày, tối đa 50 images.

Acceptance:

- OpenSearch backing volume chuyển sang gp3 và index health/search/ingestion đạt.
- Mọi persistent data set dùng gp3 hoặc có owner-approved migration date.
- Mọi snapshot có owner/expiry hoặc DLM quản lý.
- S3 lifecycle không rút ngắn 90-day COMPLIANCE retention.

## 6. Workstream 3 — NAT, VPC Endpoint và cross-AZ

### 6.1 Measured migration baseline

Topology tại `us-east-1`:

- 1 NAT Gateway;
- 2 application AZ theo Terraform với `single_nat_gateway=true`: [`infra/terraform/vpc.tf`](workspace/FINAL-PHASE/tf4-phase3-repo/infra/terraform/vpc.tf);
- 0 VPC Endpoint;
- 0 VPC Flow Log.

Cost Explorer UsageQuantity trong `[2026-07-15, 2026-07-22)`:

| Usage type | Baseline |
|---|---:|
| NAT Gateway hours | `168 Hrs` |
| NAT processed data | `30.953530 GB` |
| EC2-Other regional transfer | `643.682040 GB` |

Các daily rows mang `Estimated=true`; đây là measured baseline đủ để khởi động migration NAT/cross-AZ. Các đơn vị được theo dõi riêng, không cộng thành một total.

### 6.2 Implementation sequence

1. Bật metadata-focused VPC Flow Logs qua Terraform với source/destination address, ports, protocol, action, bytes, packets, interface, VPC/subnet và AZ identifiers; đặt retention, encryption, IAM và cost-allocation tags.
2. Thu 7 UTC ngày và group traffic theo destination service, source/destination AZ và workload interface.
3. Triển khai S3 Gateway Endpoint trước, cập nhật route tables và endpoint policy.
4. Với ECR API/DKR, STS, CloudWatch Logs và SSM, triển khai interface endpoint khi Flow Logs xác nhận traffic; đặt endpoint theo AZ được workload sử dụng, private DNS và least-privilege security group/policy.
5. Tối ưu cross-AZ path từ bảng top talkers: align workload với managed-service endpoint/AZ, topology spread hoặc routing; giữ HA replica placement.
6. Giữ NAT cho internet egress; endpoint reduction nhắm vào `NatGateway-Bytes`. `NatGateway-Hours` chỉ giảm khi toàn bộ remaining egress có replacement được kiểm thử.
7. Thu matched seven-day after window, cùng workload profile và cùng UsageType.

Không cộng bốn NAT directional CloudWatch counters vì mỗi flow xuất hiện ở các counter đối xứng. Dùng Cost Explorer `NatGateway-Bytes` cho billing usage và Flow Logs cho attribution.

### 6.3 Acceptance evidence

- Flow Logs có đủ 7 UTC ngày và destination/AZ ranking.
- S3 route đi qua Gateway Endpoint; selected AWS APIs resolve/route qua approved interface endpoint.
- Image pull, application startup, CloudWatch delivery và AWS API calls hoạt động.
- `NatGateway-Bytes` giảm trong matched window.
- Regional-transfer usage giảm theo cùng UsageType/window sau AZ path change.
- ALB external storefront path, internal APIs và operational endpoints giữ health/SLO.

## 7. Workstream 4 — telemetry sampling, retention và cardinality

### 7.1 Live baseline

| Telemetry | Baseline live |
|---|---|
| EKS control-plane | `audit` và `authenticator`; CloudWatch retention 7 ngày; audit subscription downstream hoạt động |
| CloudTrail | Multi-Region, log-file validation và CloudWatch delivery enabled; retention 7 ngày |
| Prometheus | Retention 1 tuần; `174,964` active head series; append rate `3,527.154/s`; TSDB blocks `4,708,273,476` bytes |
| OTel Collector | Không có `tail_sampling` hoặc `probabilistic_sampler` processor trong effective processor set |
| Jaeger | Cleaner schedule hoạt động và lần chạy quan sát thành công |
| OpenSearch | Retention policy và CronJob tồn tại; current `otel-logs` index có 0 ISM policy assignment |

### 7.2 Implementation sequence

1. Sửa OpenSearch retention job/policy matching để `otel-logs-*` index nhận ISM policy; kiểm tra policy assignment, index age, rollover/delete transition và search retrieval.
2. Expose sanitized accepted/refused span counters và trace rate từ SDK/collector pipeline.
3. Thu Prometheus top metric/label cardinality, dashboard/alert usage và ingestion rate trong cùng window.
4. Chọn một bounded control:
   - thêm probabilistic/tail sampling theo service/error/latency policy; hoặc
   - bỏ promoted label không được dashboard/alert sử dụng; hoặc
   - giảm collector self-telemetry detail sau khi giữ các health metrics cần vận hành.
5. Giữ full fidelity cho error traces và critical storefront/payment investigation path theo owner policy.
6. Thu same-window before/after cho spans/s, accepted/refused spans, active series, samples/s, stored bytes và index growth.

Acceptance:

- ISM policy được gắn vào đúng index pattern và retention transition chạy.
- Active series/trace volume hoặc stored-byte growth giảm theo control đã chọn.
- Trace lookup, log search, Prometheus query, Grafana dashboard, alert query và incident investigation hoàn tất.
- Collector/Jaeger/OpenSearch/Prometheus không tăng OOM, restart hoặc ingestion error.

## 8. Top driver và execution order

Data-transfer là top measured usage driver trong network category, với `643.682040 GB` regional transfer và `30.953530 GB` NAT processing trong 7 ngày. NAT/cross-AZ workstream là reduction proof chính của Mandate 18. Cleanup EIP/storage/NLB được thực hiện trước để loại bỏ recurring usage không phục vụ main flow.

Thứ tự triển khai:

1. dọn Terraform-managed unassociated EIP;
2. dọn Released PV/EBS/snapshot recovery chain;
3. disable PostgreSQL migration bridge và để controller dọn internal NLB/TG;
4. tạo CSI gp3 classes và migrate OpenSearch;
5. triển khai snapshot DLM và post-lock S3 lifecycle;
6. bật Flow Logs, triển khai S3 Gateway Endpoint, selected interface endpoints và AZ path optimization;
7. sửa OpenSearch ISM assignment và áp dụng một telemetry sampling/cardinality control.

Mỗi action công bố:

- configuration revision và ownership path;
- UTC before/after window;
- Region `us-east-1`;
- cùng metric, UsageType và unit;
- absolute delta và percentage delta;
- storefront/API health, SLO và investigation result.

## 9. Mentor evidence package

Mentor review theo thứ tự:

1. orphan before/after inventory và Terraform/GitOps/controller change records;
2. gp3 StorageClass, runtime volume mapping, migration/rollback evidence;
3. snapshot register, DLM và S3 lifecycle sau 90-day retention floor;
4. Cost Explorer NAT/cross-AZ baseline, Flow Log destination/AZ ranking, endpoint routes và matched after window;
5. telemetry before/after, ISM assignment, sampling/cardinality control;
6. ALB main-flow health, trace lookup, log search, dashboards, alerts và SLO sau từng change.

Mandate implementation package hoàn chỉnh khi:

- EIP, Released recovery chain và migration NLB đã được dọn qua ownership path;
- EBS persistent data dùng gp3 và right-sizing dựa trên multi-day usage;
- snapshots và audit S3 có lifecycle;
- endpoint/AZ changes làm giảm measured NAT/cross-AZ usage;
- telemetry có finite retention, sampling/cardinality control và giảm measured volume;
- top data-transfer driver có same-unit before/after reduction;
- storefront, APIs, SLO và investigation workflow tiếp tục hoạt động.

## 10. Source ledger

- [`MANDATE-18-cost-beyond-compute.md`](workspace/FINAL-PHASE/tf4-phase3-repo/mandates/MANDATE-18-cost-beyond-compute.md)
- [`D18-COST-01 baseline`](workspace/FINAL-PHASE/tf4-phase3-repo/docs/evidence/directive-18/d18-cost-01-baseline-usage-top-cost-drivers.md)
- [`D18-COST-03 storage/lifecycle`](workspace/FINAL-PHASE/tf4-phase3-repo/docs/evidence/directive-18/d18-cost-03-ebs-type-sizing-lifecycle.md)
- [`deploy/ingress.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/deploy/ingress.yaml)
- [`infra/terraform/vpc.tf`](workspace/FINAL-PHASE/tf4-phase3-repo/infra/terraform/vpc.tf)
- [`infra/terraform/eks.tf`](workspace/FINAL-PHASE/tf4-phase3-repo/infra/terraform/eks.tf)
- [`techx-corp-chart/templates/postgresql-migration-bridge.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-chart/templates/postgresql-migration-bridge.yaml)
- [`techx-corp-chart/templates/storageclass-prometheus.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-chart/templates/storageclass-prometheus.yaml)
- [`techx-corp-chart/values.yaml`](workspace/FINAL-PHASE/tf4-phase3-repo/techx-corp-chart/values.yaml)
