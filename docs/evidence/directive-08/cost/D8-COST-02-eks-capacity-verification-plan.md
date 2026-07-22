# C0G-71 — D8-COST-02: Verify EKS Capacity After Removing Self-Hosted Data Pods

**Directive:** #8 — Managed Data Services Migration
**Owner:** Tuấn — CDO-04 Performance Efficiency & Cost Optimization
**Cluster:** `techx-tf4-cluster` (`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`), namespace `techx-tf4`, region `us-east-1`
**Trạng thái tính đến `2026-07-22`:** Đã thu thập Pass 1 (ngay sau cutover) + dữ liệu pricing/Cost Explorer. Chưa final — còn thiếu Pass 2 (sau cửa sổ consolidation), billing sau khi hết `Estimated`, và evidence NodeClaim (bị chặn RBAC). Nguồn ticket: `task-week-3/epic8/task-tuan.md`.

---

## Objective

Xác minh cluster capacity và cost impact sau khi PostgreSQL, Valkey và Kafka pods được remove.

---

## Before/After Comparison

So sánh các chỉ số trước và sau khi remove self-hosted data pods:

**Nguồn "Before":** không có baseline chính thức riêng cho `D8-COST-02`/`D8-PERF-01`. Số liệu Before dưới đây lấy từ bản chụp `techx-quota` gần cutover nhất mà repo có, thuộc `D13-COST-01` (`docs/evidence/epic-09-compute-cost-optimization/D13-COST-01-ondemand-baseline/raw/05-resourcequota.txt`, capture `2026-07-20T13:43:44Z`). **Lưu ý quan trọng:** giữa `07-20` và `07-22`, hard limit `limits.cpu` của quota cũng đổi từ `9` sang `10` (không liên quan đến việc gỡ pod), và các service khác trong namespace có thể đã scale lên/xuống trong khoảng thời gian này — vì vậy delta dưới đây **không thể quy hoàn toàn** cho việc gỡ 3 pod self-hosted, chỉ là tham chiếu gần nhất hiện có cho đến khi có baseline `D8-PERF-01` chính thức.

| Chỉ số                   | Before (`2026-07-20T13:43:44Z`, `D13-COST-01`)                                                            | After (`2026-07-22`, Pass 1)                                                                                                                                                                                                           | Evidence                                                                                                                                |
| ------------------------ | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Pod count                | `techx-quota` pods: `33/40`                                                                               | `techx-quota` pods: `28/40` (giảm 5 — **không** quy gọn cho đúng 3 pod bị gỡ, vì có thể lẫn pod-churn khác của các service không liên quan trong khoảng `07-20`→`07-22`)                                                               | `raw/04-resourcequota-pass1.yaml`; pod `postgresql`/`valkey-cart`/`kafka`/`orders-mirrormaker2` không còn trong `raw/01-pods-after.txt` |
| Total requests.cpu       | `2080m/4`                                                                                                 | `1735m/4` (giảm `345m`)                                                                                                                                                                                                                | `raw/04-resourcequota-pass1.yaml`                                                                                                       |
| Total requests.memory    | `4035Mi/9Gi`                                                                                              | `2759Mi/9Gi` (giảm `1276Mi`)                                                                                                                                                                                                           | `raw/04-resourcequota-pass1.yaml`                                                                                                       |
| Total limits.cpu         | `8150m/9`                                                                                                 | `6350m/10` (giảm `1800m` used, nhưng hard limit cũng đổi `9`→`10` cùng lúc — không phải delta thuần từ việc gỡ pod)                                                                                                                    | `raw/04-resourcequota-pass1.yaml`                                                                                                       |
| Total limits.memory      | `6661Mi/12Gi`                                                                                             | `4873Mi/12Gi` (giảm `1788Mi`)                                                                                                                                                                                                          | `raw/04-resourcequota-pass1.yaml`                                                                                                       |
| PVC/EBS resources        | 3 PVC `Bound` (`kafka-pvc` 10Gi, `postgresql-pvc` 10Gi, `valkey-cart-pvc` 5Gi = 25Gi), đang được pod dùng | Cả 3 PVC vẫn `Bound`, **chưa xóa**; EBS bên dưới đã chuyển sang `available` (đã detach). `postgresql-pvc` có 2 volume `available` (`2026-07-13`, `2026-07-14`) — cần CDO-08 xác nhận có volume mồ côi hay không                        | `raw/06-pvc-ebs-after.txt`                                                                                                              |
| Node count               | 4 `Ready`                                                                                                 | 4 `Ready` — không đổi                                                                                                                                                                                                                  | `raw/02-nodes-wide-pass1.txt`                                                                                                           |
| Node utilization         | Chưa thu thập                                                                                             | Chưa thu thập (`kubectl top` chưa chạy pass này); dùng ResourceQuota `used` ở trên làm proxy                                                                                                                                           | —                                                                                                                                       |
| Karpenter NodeClaims     | Chưa thu thập                                                                                             | `kubectl get nodeclaims` → `Forbidden` (cả `TF4-BaseReadOnly` lẫn `TF4-CostPerfReadOnlyAlerting`, thiếu RBAC `karpenter.sh`). Proxy qua node label: 2 node managed-nodegroup + 2 node Karpenter (`techx-general` nodepool) — không đổi | `raw/05-nodeclaims-pass1.yaml`, `raw/11-node-labels.txt`                                                                                |
| NodeClaim lifetime       | Không đo được (không có quyền NodeClaim)                                                                  | Không đo được (không có quyền NodeClaim)                                                                                                                                                                                               | `raw/05-nodeclaims-pass1.yaml`                                                                                                          |
| HPA                      | Chưa thu thập                                                                                             | `checkout`/`currency`/`frontend` đều tồn tại, 2-19% CPU (target 70%), không HPA nào target pod data đã gỡ                                                                                                                              | `raw/03-hpa-wide-pass1.txt`                                                                                                             |
| ResourceQuota            | Xem các dòng requests/limits ở trên                                                                       | Xem các dòng requests/limits ở trên                                                                                                                                                                                                    | `raw/04-resourcequota-pass1.yaml`                                                                                                       |
| Pending/FailedScheduling | Chưa thu thập                                                                                             | 0 sự kiện `FailedScheduling`, 0 pod `Pending`                                                                                                                                                                                          | `raw/07-events-failedscheduling-pass1.txt`                                                                                              |
| Final resting node count | —                                                                                                         | **Chưa áp dụng được** — mới ~1h sau khi pod bị chấm dứt, `desiredSize` ASG managed-nodegroup vẫn `2`, chưa qua chu kỳ `consolidateAfter` nào. Không trích dẫn đây là số node nghỉ cuối cùng                                            | `raw/10-asg-desiredsize.txt`                                                                                                            |

**Cost data hỗ trợ (không nằm trong danh sách chỉ số của ticket, thu thập để phục vụ Cost Formula bên dưới):**

- On-demand pricing `us-east-1`: `t3a.large` $0.0752/giờ, `t3.large` $0.0832/giờ, EBS `gp2` $0.10/GB-tháng (`raw/08-pricing-attempt.txt`).
- Cost Explorer `UnblendedCost` theo ngày (`2026-07-15`→`2026-07-22`), theo service: EC2-Compute `$0` mọi ngày, RDS/MSK/ElastiCache gần `$0` (chỉ xuất hiện từ `07-19`/`07-20`), **mọi ngày đều `"Estimated": true"`** — chưa dùng được làm billing final. `EC2 - Other` (EBS/data-transfer) tăng dần theo ngày, chưa xem xét kỹ (`raw/09-ce-cost-and-usage.json`).

---

## Safety Rule

Chỉ remove self-hosted pods/PVC sau khi:

- cutover PASS;
- data parity PASS;
- stabilization PASS;
- rollback decision cho phép cleanup.

**Trạng thái từng điều kiện (`2026-07-22`):**

| Điều kiện                          | Trạng thái                    | Evidence                                                                                                                                                                                                                                                                                                                                                                                        |
| ---------------------------------- | ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| cutover PASS                       | **PASS**                      | `raw/01-pods-after.txt`: không còn pod `postgresql`/`valkey-cart`/`kafka`/`orders-mirrormaker2`. Khớp `docs/cdo08/week2/mandate8/evidence/MANDATE-08-MANAGED-DATA-MIGRATION-EVIDENCE.md` và `REL-17-kafka-msk-cutover-evidence.md` (§7: "PASS")                                                                                                                                                 |
| data parity PASS                   | **Chưa xác nhận sau cutover** | `docs/cdo08/week2/mandate8/evidence/REL-15-postgresql-parity-evidence.md` (`2026-07-21`) — tài liệu mới nhất tìm được — ghi `Final frozen parity: PENDING`, `App cutover: NOT STARTED`, tức là trước cutover. Không có tài liệu parity mới hơn cho Postgres; không có evidence parity cho Valkey/Kafka                                                                                          |
| stabilization PASS                 | **Chưa đạt**                  | Pod bị kill mới ~1h tại thời điểm thu thập (`raw/07-events-failedscheduling-pass1.txt`); cùng file còn ghi nhận lỗi `FailedDeployModel` (security group `DependencyViolation`) trên `postgresql-migration-bridge`/`valkey-migration-bridge` và probe failure của `orders-mirrormaker2` — cleanup hạ tầng migration bridge chưa xong. CDO-08 tự liệt kê "observation window" là follow-up còn mở |
| rollback decision cho phép cleanup | **Chưa đạt**                  | `kafka-pvc`/`postgresql-pvc`/`valkey-cart-pvc` cố tình giữ `Bound`; CDO-08 evidence nói rõ không xóa trước khi PM/owner xác nhận rollback window đã đóng                                                                                                                                                                                                                                        |

Việc thực hiện Pass 1 ở trên được tiến hành theo chỉ đạo của Tuấn dù 2/4 điều kiện chưa đạt — số liệu capacity vẫn được ghi nhận làm data point, nhưng **PVC/EBS không được xóa** và **không claim saving** cho đến khi đủ 4 điều kiện.

---

## Cost Formula

```
Removed EKS cost
= removed worker node-hours
- removed EBS/PVC cost
```

**Không claim saving nếu:**

- node count không giảm;
- NodeClaim lifetime không giảm;
- removed reservation không tạo consolidation;
- billing chưa đủ dữ liệu.

**Áp vào dữ liệu hiện có (`2026-07-22`):**

| Điều kiện chặn saving                       | Trạng thái                                                      |
| ------------------------------------------- | --------------------------------------------------------------- |
| node count không giảm                       | Đúng — vẫn 4 node, `desiredSize` ASG vẫn `2`                    |
| NodeClaim lifetime không giảm               | Không đo được (RBAC), nên coi như chưa chứng minh được giảm     |
| removed reservation không tạo consolidation | Đúng — 2 node Karpenter vẫn còn nguyên, chưa thấy consolidation |
| billing chưa đủ dữ liệu                     | Đúng — toàn bộ Cost Explorer response `Estimated: true`         |

→ **Không claim saving.** Cả 4 điều kiện chặn trong công thức đều đang áp dụng. `Removed EKS cost` hiện để `$0`/chưa xác định, khớp lập trường mặc định của `D8-COST-01` (branch `origin/codex/d8-cost-01-net-cost-model`).

---

## Acceptance Criteria

- [x] Không còn PostgreSQL pod tự host. — xác nhận `2026-07-22`, `raw/01-pods-after.txt`.
- [x] Không còn Valkey pod tự host. — xác nhận `2026-07-22`, `raw/01-pods-after.txt`.
- [x] Không còn Kafka pod tự host. — xác nhận `2026-07-22`, `raw/01-pods-after.txt`.
- [ ] Có before/after reservation matrix. — đã có ở bảng Before/After Comparison, nhưng "before" mượn từ snapshot `D13-COST-01` (`2026-07-20`, không phải baseline chính thức `D8-PERF-01` của ticket này) và delta lẫn cả pod-churn/quota-resize không liên quan đến việc gỡ pod, nên matrix chưa được coi là hoàn chỉnh/sạch.
- [ ] Có before/after node count. — đã có (4 → 4), nhưng chưa qua cửa sổ consolidation nên chưa phải "after" cuối cùng.
- [ ] Có Karpenter consolidation evidence. — **Chưa đạt.** `desiredSize` không đổi, 2 node Karpenter vẫn còn, không quan sát được consolidation.
- [ ] Có removed PVC/EBS inventory. — **Chưa đạt.** Cả 3 PVC vẫn `Bound`, EBS chỉ detach chứ chưa xóa.
- [x] Không có Pending hoặc node pressure. — xác nhận `2026-07-22`, `raw/07-events-failedscheduling-pass1.txt`.
- [x] Không claim saving nếu node-hours chưa giảm. — tuân thủ, xem phần Cost Formula ở trên.

---

## Dependency

Depends on successful cutover và cleanup approval.

- **Cutover:** thành công — xem Safety Rule ở trên (`PASS`).
- **Cleanup approval:** **chưa có.** Rollback decision chưa cho phép cleanup (PVC vẫn giữ `Bound`), nên các tiêu chí liên quan đến PVC/EBS removal và before/after final chưa thể đóng.

---

## Evidence files (`docs/evidence/directive-08/cost/raw/`)

| File                                   | Nội dung                                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `00-collection-metadata.txt`           | Timestamp, AWS identity, ghi rõ đây chỉ là Pass 1                                                                   |
| `01-pods-after.txt`                    | `kubectl get pods -n techx-tf4 -o wide`                                                                             |
| `02-nodes-wide-pass1.txt`              | `kubectl get nodes -o wide`                                                                                         |
| `03-hpa-wide-pass1.txt`                | `kubectl get hpa -A -o wide`                                                                                        |
| `04-resourcequota-pass1.yaml`          | `kubectl get/describe resourcequota techx-quota`                                                                    |
| `05-nodeclaims-pass1.yaml`             | Cả 2 lần thử (`TF4-BaseReadOnly`, `TF4-CostPerfReadOnlyAlerting`) — `Forbidden` cả hai, lỗ hổng RBAC `karpenter.sh` |
| `06-pvc-ebs-after.txt`                 | `kubectl get pvc` + `aws ec2 describe-volumes` cho từng PVC                                                         |
| `07-events-failedscheduling-pass1.txt` | Sự kiện `FailedScheduling`, pod `Pending`, event log gần đây                                                        |
| `08-pricing-attempt.txt`               | `aws pricing get-products` cho `t3a.large`/`t3.large`/`gp2` (chạy được sau khi đổi role)                            |
| `09-ce-cost-and-usage.json`            | `aws ce get-cost-and-usage`, `2026-07-15`..`2026-07-22` theo ngày theo service                                      |
| `10-asg-desiredsize.txt`               | `aws autoscaling describe-auto-scaling-groups`                                                                      |
| `11-node-labels.txt`                   | Label node phân biệt managed-nodegroup vs. Karpenter                                                                |

Chưa có file `-pass2` nào — cần một cửa sổ consolidation thực sự (≥1 chu kỳ `consolidateAfter`) trước khi chạy lại.

---

## Việc còn lại trước khi đóng ticket

1. Pass 2: chạy lại `02`/`10`/`11` sau khi có đủ thời gian consolidation, để xem reservation được giải phóng có khiến Karpenter giảm node hay không.
2. NodeClaim: cần role có RBAC `karpenter.sh`, hoặc nhờ CDO-08/Platform pull hộ.
3. Re-pull Cost Explorer sau khi hết cờ `Estimated: true` (24-48h+ sau cutover) trước khi tính `Removed EKS cost` thật.
4. Data-parity PASS chính thức sau cutover cho cả 3 data store (hiện chỉ có bản parity Postgres trước cutover, đã cũ) — flag CDO-08 nếu vẫn thiếu.
5. Xác nhận thời điểm/điều kiện xóa PVC/EBS (rollback window đóng) trước khi đánh dấu "removed PVC/EBS inventory" hoàn tất.
