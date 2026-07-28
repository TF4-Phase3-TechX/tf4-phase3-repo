# D18-PM-01 — ADR và evidence chi phí ngoài node compute

**Owner:** CDO-04 (Performance & Cost)  
**Phạm vi:** Directive 18 / hidden cost ngoài compute  
**Verdict chính:** **CONDITIONAL PASS**  
**Nguyên tắc đo:** dùng count, GiB, GB, GB-month, hours, spans/s và series/s;
không cộng các đơn vị khác nhau thành một tổng cost giả. Account đang chạy
credit nên USD chỉ dùng để giải thích trade-off.

## 1. Tóm tắt quyết định

| Khu vực | Quyết định | Owner / guardrail |
|---|---|---|
| Baseline | Chốt baseline live ngày `2026-07-22`, account `511825856493`, region `us-east-1`; Cost Explorer còn `Estimated=true`. | CDO-04; query lại settled window trước cost verdict chính thức. |
| Top driver | Ưu tiên orphan cleanup, GP2/snapshot lifecycle, sau đó NAT data path. | Terraform owner, recovery owner, CDO-08/network owner. |
| Orphan | Xóa tài nguyên đã xác nhận mồ côi; giữ snapshot recovery/migration có owner và expiry. | Không xóa volume `Bound`, recovery snapshot hoặc shared LB khi thiếu quyết định owner. |
| EBS/storage | OpenSearch đã chuyển gp2 `40 GiB` → gp3 `160 GiB`, `120 IOPS` → `3,000 IOPS`, mở rộng filesystem online. | Stateful workload owner; backup, cutover, restore và rollback gate. |
| NAT/Endpoint | Giữ S3 Gateway và Interface Endpoint cho security/operational boundary và AWS-service path đã đo; không claim đây là cost saving thuần túy. | CDO-08/network owner; rollback bằng Terraform revision. |
| Cross-AZ | Không claim giảm khi chưa có Flow Logs đủ 7 ngày và aggregation theo destination/AZ. | Network/IaC owner. |
| Telemetry | Không tự ý giảm sampling/telemetry khi chưa có SLO và forensic sign-off; baseline trace sampling là 100%. | Observability owner. |
| Retention | Giữ compliance floor 90 ngày cho CloudWatch/Object Lock; snapshot phải có purpose/expiry. | Compliance, recovery và observability owners. |
| Cardinality | Không giảm label/cardinality production nếu thiếu before/after PromQL và reliability review. | Observability owner. |

## 2. Baseline usage ngoài compute

**Cửa sổ inventory:** `2026-07-22T04:19:53Z`–`2026-07-22T04:21:07Z`  
**Cost Explorer:** `[2026-07-15T00:00:00Z, 2026-07-22T00:00:00Z)`  
**Account / region:** `511825856493` / `us-east-1`

| Driver | Baseline |
|---|---:|
| EBS gp2 | 5 volumes / 75 GiB; `13.801 GB-Month` |
| EBS gp3 | 6 volumes / 130 GiB; `25.673 GB-Month` |
| EBS `available` | 4 volumes / 35 GiB |
| Self-owned snapshot | 9; logical source size 76 GiB; `2.139 GB-Month` |
| Self-owned AMI | 0 tại `us-east-1` |
| NAT Gateway | 160 hours; `30.585 GB` |
| CloudWatch vended logs | `98.788 GB` trong Cost Explorer window |
| EKS control-plane logs | `10.259 GB`, retention 90 ngày |
| CloudTrail logs | `0.141 GB`, retention 90 ngày |
| Traces | khoảng 4,644 spans/s; sampling 100% |
| Prometheus | 179,044 active series; 3,535.45 samples/s |

## 3. Top cost driver và quyết định

1. **Orphan candidates:** EIP unassociated, Released-PV EBS/snapshot chain và
   migration bridge không còn dùng. Cleanup cần owner approval và after-scan.
2. **GP2 và snapshot lifecycle:** chỉ migrate active GP2 qua backup, cutover,
   restore và rollback gate; không suy ra target size từ một lần đo filesystem.
3. **NAT data path:** dùng Flow Logs và route evidence để phân biệt AWS-service
   traffic với Internet egress trước khi đổi topology.

## 4. Quyết định orphan cleanup

After-scan lúc `2026-07-25T17:00Z`–`17:02Z` ghi nhận:

- `us-east-1`: 7 EBS volumes, tất cả `in-use`; `0 available / 0 GiB`.
- `0` EIP unassociated và `0` self-owned AMI.
- 4 snapshot còn giữ, gắn với OpenSearch volume; cần purpose, owner và expiry.
- 16 enabled regions còn lại trả về 0 volume, snapshot, EIP rời và AMI.

Quyết định: các EBS/EIP đã xác nhận orphan được cleanup; snapshot recovery,
snapshot migration và tài nguyên đang phục vụ LB không coi là orphan khi chưa
có quyết định owner mới.

## 5. Quyết định EBS và storage lifecycle

OpenSearch migration evidence ghi nhận:

- gp2 `40 GiB` → gp3 `160 GiB`;
- `120 IOPS` → `3,000 IOPS`, throughput `125 MiB/s`;
- filesystem mở rộng online, giữ nguyên Pod/PVC/PV identity;
- StatefulSet reconciliation đạt `1/1 Ready`, zero restart.

Đây là quyết định tăng headroom/reliability, không phải giảm provisioned GiB.
Prometheus vẫn là gp3 `20 GiB`, `3,000 IOPS`, `125 MiB/s`.

Snapshot `snap-0a6903e05af18a326` được giữ đến `2026-08-01`. Báo cáo execution
ghi nhận DLM policy `policy-08ed1dffc099481b5`, tag `D18Snapshot=true`, chạy
daily `23:15 UTC`, giữ 7 snapshot. CloudTrail và EKS audit bucket có Object
Lock COMPLIANCE 90 ngày; lifecycle báo cáo archive GLACIER_IR từ ngày 91,
expire ngày 365. Mentor cần đối chiếu trực tiếp policy/lifecycle trong console.

## 6. NAT, VPC Endpoint và cross-AZ

Apply endpoint diễn ra `2026-07-25T03:28:06Z`–`03:37:12Z`:

- 1 S3 Gateway Endpoint và 7 Interface Endpoint ở trạng thái `AVAILABLE`.
- Private DNS của STS, SSM, Logs và ECR API trỏ về địa chỉ private VPC.
- S3 Gateway route active trên `rtb-03b6b2cb0144ce3bb`.
- Flow Logs `fl-099595bbcfdd3bf5a`: `ACTIVE`, delivery `SUCCESS`, retention 7 ngày.

Endpoint policy phải giới hạn trong VPC security boundary và AWS service path
cần thiết. Terraform source và CDO-08 response là policy/config reference;
không chấp nhận policy rộng hơn khi chưa có owner decision.

Matched NAT window 13.53 giờ:

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| `BytesOutToDestination` | 79,063,981 bytes | 83,768,702 bytes | **+5.95%** |

Trade-off được ghi nhận: PrivateLink khoảng `$102.20/tháng` so với NAT saving
đo được khoảng `$7.53/tháng`; Interface Endpoint có thể làm net cost tăng.
ECR, Logs và S3 có measured path/security justification; STS/SSM chủ yếu giữ
vì security và operational boundary. Cross-AZ reduction chưa được claim.

## 7. Telemetry sampling, retention và cardinality

| Tín hiệu | Baseline | Quyết định |
|---|---|---|
| Logs | EKS control-plane 17.38 GB/ngày; CloudWatch 90 ngày; OpenSearch logs 3 ngày theo báo cáo | Giữ compliance/forensic floor; không giảm mù. |
| Traces | khoảng 4,644 spans/s; sampling 100%; Jaeger khoảng 18.4 GB/ngày | Không giảm sampling nếu thiếu SLO và investigation sign-off. |
| Metrics | 179,044 active series; 3,535.45 samples/s | Review cardinality bằng PromQL trước khi giảm label. |

After snapshot Prometheus: `208,592` active series, `33,287.225/s` samples và
`4.802 GB` blocks; chưa thể coi là reduction evidence. Dashboard before/after
phải cùng UTC window, query, datasource và dashboard revision.

## 8. Performance, reliability và residual risk

- Mọi apply phải có Terraform plan review và change window.
- Sau endpoint change phải kiểm tra Private DNS, ECR pull, SSM, Logs delivery
  và S3 route.
- Stateful storage phải có backup, restore, integrity, rollback window,
  application health và zero-restart validation.
- Không suy ra SLO PASS chỉ từ trạng thái Pod `Running`.
- Rollback dùng Terraform revision đã review, sau đó kiểm tra NAT route, DNS,
  ECR, SSM và logging.
- Không chấp nhận mất critical alert; cần alert history/query tương ứng.

| Khu vực | Owner | Rủi ro còn lại |
|---|---|---|
| Cost baseline/package | CDO-04 | Cost Explorer baseline còn estimated. |
| Orphan cleanup | Terraform/recovery/REL-15 owners | Snapshot giữ lại cần owner/expiry rõ. |
| EBS lifecycle | Stateful workload owners | GP2 còn lại và target sizing cần growth/IOPS evidence. |
| NAT/endpoint/cross-AZ | CDO-08 và network/IaC owner | NAT matched result tăng; Flow Logs chưa đủ 7 ngày. |
| Telemetry | Observability owner | Sampling, cardinality và dashboard before/after chưa đầy đủ. |
| SLO | Storefront/performance owner | Cần run Browse, Cart, Checkout và p95/p99 sau endpoint. |

## 9. Evidence index

| Evidence | Vị trí / tham chiếu | Phạm vi |
|---|---|---|
| Baseline top driver | `docs/evidence/directive-18/d18-cost-01-baseline-usage-top-cost-drivers.md`; PR #493 | Usage baseline và ranking |
| Orphan inventory | `docs/evidence/directive-18/D18-COST-02-orphaned-resources/README.md`; PR #459 / #500 | Volumes, EIPs, snapshots, AMIs, LBs, target groups |
| EBS/storage | `docs/evidence/directive-18/d18-cost-03-ebs-type-sizing-lifecycle.md`; PR #493 / #670 | EBS type/size, gp3 migration, lifecycle |
| NAT/cross-AZ | `docs/evidence/directive-18/D18-COST-04-nat-cross-az-analysis/README.md`; PR #339 | NAT baseline, cross-AZ method, endpoint opportunities |
| CDO-08 coordination | `docs/evidence/directive-18/D18-COST-04-nat-cross-az-analysis/D18-CDO08-request-platform-coordination.md` | Security/network coordination |
| Endpoint runtime | `docs/evidence/directive-18/D18-PLAT-01-vpc-endpoints-runtime-evidence.md`; PR #632 | Endpoint, DNS, route, Flow Logs, NAT |
| Telemetry baseline | PR #523 | Log/trace/metric volume, retention, cardinality; report không có trong branch hiện tại |
| Usage consolidation | `docs/evidence/directive-18/D18-COST-05-usage-reduction-top-cost-driver/README.md`; PR #671 | After inventory và matched NAT |

## 10. Screenshot hỗ trợ đang có trong project

Các file dưới đây có thể hỗ trợ mentor review, nhưng phải xác minh timestamp,
account/region và dashboard revision trước khi coi là D18 exact evidence:

| Phạm vi | File |
|---|---|
| EBS volumes | `docs/evidence/epic-04-cost-optimization/runtime/screenshots/Kiểm tra EBS volumes.jpg` |
| NAT Gateway | `docs/evidence/epic-04-cost-optimization/runtime/screenshots/Kiểm tra NAT Gateway.jpg` |
| Load Balancer | `docs/evidence/epic-04-cost-optimization/runtime/screenshots/Kiểm tra ALB.jpg` |
| CloudWatch log groups | `docs/evidence/epic-04-cost-optimization/runtime/screenshots/Kiểm tra CloudWatch log groups.jpg` |
| Grafana/Jaeger | `docs/evidence/epic-04-cost-optimization/runtime/screenshots/Grafana overkill.jpg`, `Jaeger overkill.jpg` |
| Storefront flow | `docs/evidence/epic-03-performance-efficiency/screenshots/browse-product-flow.png`, `cart-and-delivery-processing.png`, `checkout-flow-1-1.png`, `checkout-flow-2-1.png` |
| Grafana latency/error | `docs/evidence/epic-03-performance-efficiency/screenshots/grafana-latency.png`, `grafana-error-rate.png` |

## 11. Checklist nghiệm thu

- [x] ADR và các quyết định đã được tổng hợp.
- [x] Evidence index tham chiếu baseline, orphan, storage, network, telemetry và COST-05.
- [x] Before/after usage đã ghi ở các cửa sổ có số liệu.
- [x] Top cost driver và trade-off đã được nêu rõ.
- [x] Investigation path đã được mô tả.
- [x] CDO-08 coordination response đã được liên kết.

