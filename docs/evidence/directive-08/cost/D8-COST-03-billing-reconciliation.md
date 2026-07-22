# C0G-72 — D8-COST-03: Reconcile Managed Data Migration Cost with AWS Billing

**Directive:** #8 — Managed Data Services Migration
**Owner:** Tuấn — CDO-04 Performance Efficiency & Cost Optimization
**Account:** `511825856493`, region `us-east-1`
**Trạng thái tính đến `2026-07-22`:** **BLOCKED / Pass 1 (not final).** Đã thu thập được toàn bộ data source có quyền truy cập, gồm cả MSK cluster detail và Karpenter NodeClaim lifetime, nhưng **không đủ điều kiện đóng ticket** — billing chưa qua đủ thời gian ổn định và `D8-COST-02` (dependency bắt buộc) vẫn ở trạng thái Pass 1, chưa PASS đầy đủ 4 điều kiện Safety Rule. Nguồn ticket: `task-week-3/epic8/task-tuan.md`.

---

## Objective

Đối chiếu cost model (`D8-COST-01`) với AWS usage/billing thực tế sau migration.

---

## Dependency check (bắt buộc trước khi đọc phần còn lại)

Ticket ghi rõ: *"Depends on D8-COST-02 và billing lag 24–48 giờ hoặc lâu hơn."*

| Điều kiện | Trạng thái | Evidence |
| --- | --- | --- |
| `D8-COST-02` hoàn tất | **Chưa** — Pass 1 only | `docs/evidence/directive-08/cost/D8-COST-02-eks-capacity-verification-plan.md`: chỉ 1/4 Safety Rule đạt PASS (cutover); 3/4 chưa đạt (data parity, stabilization, rollback decision), Pass 2/PVC removal còn mở |
| Billing lag 24–48h+ | **Chưa đủ cho phần lớn dữ liệu** | Xem bảng "Billing lag theo service" bên dưới — MSK/EKS cleanup mới ~vài giờ traffic; RDS/ElastiCache/MSK resource đã 3 ngày nhưng Cost Explorer vẫn `Estimated: true` toàn bộ |

→ Theo đúng Acceptance Criteria của chính ticket này ("Không claim saving khi chưa đủ billing window"), tài liệu này **chỉ ghi nhận data point Pass 1**, không đưa ra billing-reconciled verdict cuối cùng.

### Billing lag theo service

| Service | Ngày tạo resource | Ngày cutover traffic | Tuổi tại thời điểm thu thập (`2026-07-22T04:53Z`) |
| --- | --- | --- | --- |
| RDS PostgreSQL (`techx-tf4-postgresql`) | `2026-07-19T14:12:01Z` | `2026-07-21` (`REL-15-postgresql-rds-cutover-evidence.md`, chỉ ghi ngày, không có giờ) | ~3 ngày resource, ≥1 ngày traffic |
| ElastiCache Valkey (`techx-tf4-valkey-cart`) | `2026-07-19T15:39:42Z` | `2026-07-21` (`CDO08-REL-16-cart-cutover-evidence.md`, chỉ ghi ngày, không có giờ) | ~3 ngày resource, ≥1 ngày traffic |
| MSK Kafka (`techx-tf4-orders`) | `2026-07-19T14:25:48Z` | `2026-07-22 ICT` (`REL-17-kafka-msk-cutover-evidence.md`: "Pre-check, promote và post-check được thực hiện trong ngày 2026-07-22 ICT") | ~3 ngày resource, ~vài giờ traffic |
| EKS self-hosted pod removal | — | `2026-07-22` (`01-pods-after.txt` trong evidence `D8-COST-02`) | ~vài giờ |

Ngay cả với cách đọc thuận lợi nhất (RDS/ElastiCache traffic đã ≥1 ngày), Cost Explorer `get-cost-and-usage` MTD (`2026-07-01`→`2026-07-23`) vẫn trả `"Estimated": true` cho mọi ngày và AWS Budgets `CalculatedSpend.ActualSpend = $0.0` (`raw/14-aws-budgets.txt`) — actual billing chưa "settle" theo định nghĩa của ticket, bất kể tuổi resource hay tuổi traffic.

---

## Data Sources (theo danh sách của ticket)

| Source | Truy cập được? | Kết quả | Evidence |
| --- | --- | --- | --- |
| AWS Cost Explorer | Có | Per-service `UnblendedCost`, MTD + daily 07-15→07-22, mọi kết quả `Estimated: true` | `raw/09-ce-cost-and-usage.json`, `raw/12-ce-mtd-service-breakdown.json` |
| CUR (Cost and Usage Report) | Có quyền gọi API, nhưng **không có report nào được cấu hình** | `aws cur describe-report-definitions` → `{"ReportDefinitions": []}` | `raw/17-cur-report-definitions.txt` |
| RDS usage | Có | 1 instance `techx-tf4-postgresql`, `db.t4g.micro`, Multi-AZ, `gp3` 20GiB, `available` | `raw/16-rds-elasticache-describe.txt` |
| ElastiCache usage | Có | 1 replication group `techx-tf4-valkey-cart`, `cache.t4g.micro` ×2 node, Multi-AZ, automatic failover enabled | `raw/16-rds-elasticache-describe.txt` |
| MSK usage | Có (một phần) | Cluster `techx-tf4-orders`, `kafka.t3.small` × 2 broker, storage 10GiB/broker, `State: ACTIVE`, tạo `2026-07-19T14:25:48Z`, tag `Owner: CDO_04`. Chưa có broker-level detail (`kafka:ListNodes`/`GetBootstrapBrokers` bị từ chối) | `raw/22-msk-describe-cluster-confirmed.json` (có); `raw/19-msk-partial-grant-still-denied.txt` (phần còn thiếu); xem `D8-ACCESS-REQUEST-cost-perf-readonly.md` §3 |
| EC2 worker hours | Có | 5 instance đang chạy: 2× `t3.large` managed-nodegroup (launch `2026-07-09`), 2× `t3a.large` Karpenter `techx-general` nodepool (launch `2026-07-16`, `2026-07-18` — trước cutover, không phải node mới), 1× `t3.nano` bastion (ngoài phạm vi cluster cost) | `raw/13-ec2-worker-instances.txt` |
| Karpenter NodeClaim lifetime | Có | 2 NodeClaim, AGE `6d1h`/`3d9h`, cả hai tạo trước cutover — xem `D8-COST-02-eks-capacity-verification-plan.md` §Karpenter NodeClaims | `directive-08/cost/raw/20-nodeclaims-granted.txt` |
| EBS/PVC | Có (đã thu thập ở `D8-COST-02`, không lặp lại) | 3 PVC self-hosted vẫn `Bound`, chưa xóa | `directive-08/cost/raw/06-pvc-ebs-after.txt` |
| CloudWatch | Có, qua CE breakdown | `AmazonCloudWatch` không xuất hiện trong danh sách service có cost > $0 trong kỳ MTD → chưa phát sinh chi phí đáng kể | `raw/12-ce-mtd-service-breakdown.json` |
| NAT/data transfer | Có, qua CE breakdown | `AWS Data Transfer`: `-$6.83` MTD (âm — có vẻ là credit/adjustment, chưa rõ nguyên nhân); `EC2 - Other`: `+$6.82` MTD (bao gồm EBS + NAT + data-transfer gộp, CE không tách riêng NAT ở mức dimension này) | `raw/12-ce-mtd-service-breakdown.json` |
| Secrets Manager/KMS | Có, qua CE breakdown | `AWS Secrets Manager`: `-$0.0000002`; `AWS Key Management Service`: `$0.0000003` — không đáng kể | `raw/12-ce-mtd-service-breakdown.json` |
| AWS Budgets (bổ sung, không có trong danh sách ticket nhưng cần cho Budget Verdict) | Có | Budget `techx-tf4-monthly-cost-budget`: limit `$300/month`, `ActualSpend $0.0`, `ForecastedSpend $267.841`, `HealthStatus HEALTHY` | `raw/14-aws-budgets.txt` |

---

## Required Separation

| Hạng mục | Giá trị | Ghi chú |
| --- | --- | --- |
| Fixed/shared platform cost | Không tách được từ CE ở mức chi tiết này | `EC2 - Other` gộp EBS root volume + NAT + misc — cần cost allocation tag để tách theo ticket yêu cầu |
| Managed data service cost (RDS + ElastiCache + MSK) | RDS `$0.0000000054`, ElastiCache `$0` (có dòng riêng `Amazon ElastiCache` trong CE breakdown, giá trị đúng bằng 0), MSK `$0.0012` — tất cả **gần như bằng 0** dù RDS/ElastiCache/MSK đều đã chạy 3 ngày | Có 2 khả năng, chưa xác nhận được khả năng nào đúng: (a) `db.t4g.micro`/`cache.t4g.micro` rơi vào AWS Free Tier của account; (b) billing/cost-allocation chưa populate đầy đủ. MSK (`kafka.t3.small`) không có free tier điển hình nhưng cũng gần `$0` — làm yếu giả thuyết (a), nghiêng về (b), nhưng **không tự kết luận**, cần CDO-08/billing owner xác nhận |
| Variable traffic cost | Chưa đo được | Cần CloudWatch request/throughput metrics theo managed endpoint, ngoài phạm vi RBAC hiện có |
| Removed EKS cost | `$0` (giữ nguyên lập trường của `D8-COST-01` và `D8-COST-02`) | Node count không đổi (vẫn 4 node K8s + không có NodeClaim mới từ Karpenter kể từ cutover), `desiredSize` ASG không đổi — xem `D8-COST-02-eks-capacity-verification-plan.md` |
| Estimate (modeled) | `D8-COST-01`: HA-recommended scenario, whole-TF weekly guardrail `$300/week`; MTD proxy run-rate trước đó `~$270.72/month` | `origin/codex/d8-cost-01-net-cost-model` — **CONDITIONAL / INPUTS PENDING**, chưa được approve chính thức |
| Actual billing (billing-reconciled) | **Chưa có** | Toàn bộ Cost Explorer `Estimated: true`; AWS Budgets `ActualSpend $0.0` — không có ngày nào billing đã settle kể từ cutover |

---

## Reporting

### Monthly modeled delta

```
Monthly modeled delta = modeled post-migration cost − modeled pre-migration cost
```

Lấy từ `D8-COST-01` (workbook `outputs/d8-cost-01/D8-COST-01-managed-data-services-net-cost-model.xlsx`, chưa merge, trạng thái `CONDITIONAL / INPUTS PENDING`): net-cost formula là

```
Net monthly impact = RDS + ElastiCache + MSK
 + backup/storage/I-O/processing/monitoring/transfer/security
 − proven removed EKS node-hour cost
 − removed EBS/PVC cost
```

Với `proven removed EKS node-hour cost = $0` (chưa chứng minh được, xem `D8-COST-02`) và `removed EBS/PVC cost = $0` (PVC chưa xóa), **modeled delta hiện tại thiên về tăng chi phí ròng** cho đến khi node-hour/PVC removal được chứng minh. Con số chính xác nằm trong workbook chưa merge — tài liệu này không trích số liệu cụ thể từ file `.xlsx` chưa qua kiểm tra vì không tự động verify được nội dung binary.

### Observed delta

```
Observed delta = billing-complete post-migration usage − comparable baseline usage
```

**Không tính được.** Không có "billing-complete" usage cho bất kỳ ngày nào (mọi kết quả CE `Estimated: true`; AWS Budgets `ActualSpend = $0.0`). Đúng theo Acceptance Criteria của ticket ("Không claim saving khi chưa đủ billing window"), giá trị này để trống, không suy diễn.

### Weekly / Monthly projection

- **Weekly projection:** không tính mới — dùng nguyên trạng `$300/week` whole-TF guardrail từ `D8-COST-01` cho đến khi có input billing thật.
- **Monthly projection:** AWS Budgets forecast hiện tại là `$267.841/month` (`HealthStatus: HEALTHY` so với budget `$300/month`) — nhưng đây là forecast **trước khi RDS/ElastiCache/MSK cost thật sự phản ánh trong billing** (xem cảnh báo ở Required Separation), nên **không thể coi là monthly projection hậu-migration đáng tin cậy**. Chỉ ghi nhận làm data point tham chiếu.

---

## Budget Verdict

**Không thể ra verdict cuối cùng.** Lý do:

1. `D8-COST-02` (dependency bắt buộc) chưa PASS đầy đủ.
2. Billing chưa qua đủ observation window — mọi dữ liệu Cost Explorer vẫn `Estimated`.
3. Managed service cost (RDS/ElastiCache/MSK) hiện gần `$0` trong CE dù resource đã chạy, nguyên nhân chưa xác định (free-tier hay billing-lag) — nếu dùng con số này làm verdict sẽ tạo ảo giác "cost giảm" không có căn cứ.

**Interim signal (không phải verdict):** AWS Budgets `techx-tf4-monthly-cost-budget` báo `HEALTHY` với forecast `$267.841` so với hạn mức `$300/month`. Ghi nhận như một tín hiệu tham khảo tại `2026-07-22`, sẽ cần re-pull sau khi billing settle.

---

## Variance giữa model và actual

Không tính được — không có "actual" đã settle để so sánh với "model" (`D8-COST-01`). Xem phần Reporting ở trên.

---

## Acceptance Criteria

- [ ] Cost Explorer data không còn Estimated hoặc được ghi rõ. — **Ghi rõ**: toàn bộ vẫn `Estimated: true` tại `2026-07-22` (`raw/09-ce-cost-and-usage.json`, `raw/12-ce-mtd-service-breakdown.json`). Chưa đạt điều kiện "không còn Estimated".
- [ ] RDS cost được tách riêng. — Có dòng riêng trong CE (`raw/12-ce-mtd-service-breakdown.json`) nhưng giá trị gần `$0`, chưa xác nhận đáng tin cậy (free-tier vs billing-lag chưa rõ) — coi là **chưa đạt đủ điều kiện tách rõ ràng**.
- [ ] ElastiCache cost được tách riêng. — Tương tự RDS, giá trị `$0`, chưa xác nhận — **chưa đạt**.
- [ ] MSK cost được tách riêng. — **Chưa đạt.** Có cluster detail thật (`kafka.t3.small` × 2 broker, storage 10GiB/broker), nhưng chỉ có dòng CE tổng `$0.0012`, chưa tách được theo broker/storage/monitoring/transfer riêng vì `kafka:ListNodes`/`GetBootstrapBrokers` vẫn bị từ chối.
- [ ] Removed EC2/EBS cost được đối chiếu. — **Chưa đạt** — giữ nguyên `$0` theo `D8-COST-02` vì node count/PVC chưa giảm.
- [ ] Có weekly và monthly projection. — Có, nhưng đều gắn caveat "chưa billing-reconciled" (xem Reporting).
- [ ] Có budget verdict. — **Không có verdict cuối**, chỉ có interim signal (xem Budget Verdict).
- [ ] Có variance giữa model và actual. — **Chưa có** — không có actual settled để so sánh.
- [x] Không claim saving khi chưa đủ billing window. — Tuân thủ trong toàn bộ tài liệu này.

---

## Dependency

Depends on `D8-COST-02` và billing lag 24–48 giờ hoặc lâu hơn.

- **`D8-COST-02`:** chưa hoàn tất — xem `D8-COST-02-eks-capacity-verification-plan.md` (chỉ 1/4 Safety Rule PASS — cutover; data parity/stabilization/rollback decision đều chưa đạt, Pass 2 chưa chạy).
- **Billing lag:** chưa đủ — toàn bộ Cost Explorer/`AWS Budgets` vẫn ở trạng thái estimate, kể cả với RDS/ElastiCache/MSK đều đã tồn tại 3 ngày.

---

## Evidence files (`docs/evidence/directive-08/cost/raw/`)

| File | Nội dung |
| --- | --- |
| `09-ce-cost-and-usage.json` | CE daily `2026-07-15`→`2026-07-22`, theo service (dùng chung với `D8-COST-02`) |
| `12-ce-mtd-service-breakdown.json` | CE MTD `2026-07-01`→`2026-07-23`, theo service, toàn bộ dòng |
| `13-ec2-worker-instances.txt` | `aws ec2 describe-instances` (running), launch time, nodepool tag |
| `14-aws-budgets.txt` | `aws budgets describe-budgets` — budget `$300/month`, actual/forecast/health |
| `16-rds-elasticache-describe.txt` | `aws rds describe-db-instances`, `aws elasticache describe-replication-groups`/`describe-cache-clusters` |
| `17-cur-report-definitions.txt` | `aws cur describe-report-definitions` — không có report nào cấu hình |
| `19-msk-partial-grant-still-denied.txt` | `aws kafka list-nodes`/`get-bootstrap-brokers` — `AccessDeniedException`, broker-level detail chưa lấy được |
| `20-nodeclaims-granted.txt` | `kubectl get nodeclaims -o wide/-o yaml` — 2 NodeClaim, AGE `6d1h`/`3d9h` (dùng chung với `D8-COST-02`) |
| `21-nodepools-still-denied.txt` | `kubectl get nodepools` — `Forbidden` (dùng chung với `D8-COST-02`) |
| `22-msk-describe-cluster-confirmed.json` | `aws kafka describe-cluster`/`describe-cluster-v2` — cluster `techx-tf4-orders` |

---

## Việc còn lại trước khi đóng ticket

1. Chờ `D8-COST-02` đạt đủ 4 điều kiện Safety Rule (data parity PASS, stabilization PASS, rollback decision) và chạy xong Pass 2.
2. Re-pull Cost Explorer + AWS Budgets sau ít nhất 48–72h kể từ cutover thật (`2026-07-22`), kiểm tra cờ `Estimated` đã tắt chưa trước khi tính Observed delta.
3. Xác nhận với CDO-08/billing owner lý do RDS/ElastiCache/MSK cost gần `$0` dù đã chạy 3 ngày (free-tier vs billing-lag) — không tự suy diễn.
4. Xin thêm `kafka:ListNodes`/`GetBootstrapBrokers` để tách MSK cost chi tiết theo broker — theo dõi qua `D8-ACCESS-REQUEST-cost-perf-readonly.md`.
5. Xin cost-allocation tag hoặc CUR (hiện chưa cấu hình report nào) để tách "Fixed/shared platform cost" ra khỏi `EC2 - Other`/NAT thay vì dùng service-level CE.
6. Sau khi có billing-complete, đối chiếu với workbook `D8-COST-01` (`outputs/d8-cost-01/...xlsx`, branch `origin/codex/d8-cost-01-net-cost-model`, hiện `CONDITIONAL / INPUTS PENDING`) để tính variance thật.
