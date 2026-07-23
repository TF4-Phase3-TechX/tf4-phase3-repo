# C0G-71 — D8-COST-02: Verify EKS Capacity After Removing Self-Hosted Data Pods

**Directive:** #8 — Managed Data Services Migration
**Owner:** Tuấn — CDO-04 Performance Efficiency & Cost Optimization
**Cluster:** `techx-tf4-cluster` (`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`), namespace `techx-tf4`, region `us-east-1`
**Trạng thái tính đến `2026-07-22`:** Đã thu thập Pass 1 (ngay sau cutover) và Pass 2 (~3 giờ sau). Karpenter đã đánh dấu cả 2 NodeClaim `Consolidatable: True` nhưng **chưa thực thi termination** tính đến Pass 2 — chưa xác định được nguyên nhân chắc chắn, nhiều khả năng liên quan đến việc cả 2 node đang chạy nhiều pod ứng dụng thật được bảo vệ bởi PodDisruptionBudget. **Chưa thể kết luận dứt khoát là sẽ không bao giờ consolidate.** Vẫn chưa final — còn thiếu data parity PASS, stabilization PASS, rollback decision, và billing sau khi hết `Estimated`. Nguồn ticket: `task-week-3/epic8/task-tuan.md`.

**Trạng thái chính thức (CDO-04 review `2026-07-22`, xem §CDO-04 Review):**

```
D8-COST-02: IN PROGRESS
PASS 1: COMPLETE
PASS 2: COMPLETE
KARPENTER CONSOLIDATION: NOT EXECUTED AS OF PASS 2 (NodeClaim đã Consolidatable=True nhưng chưa terminate; nguyên nhân trì hoãn chưa xác nhận, khả năng liên quan PDB — không loại trừ xảy ra ở Pass sau)
FINAL CAPACITY VERDICT: PENDING (chờ Safety Rule 4/4 + billing settle)
COST SAVING: NOT PROVEN
```

---

## Objective

Xác minh cluster capacity và cost impact sau khi PostgreSQL, Valkey và Kafka pods được remove.

---

## Before/After Comparison

### A. Reservation matrix chính thức (nguồn: `D8-PERF-01`)

**Nguồn:** `docs/evidence/directive-08/01-pre-migration-baseline.md` (branch `origin/cdo04/task-d8-perf-01-pre-migration-baseline`, commit `cce88c7`, đo `2026-07-19T20:50:00Z`–`21:10:00Z` dưới tải 200 concurrent users). D8-PERF-01 đã được PM xác nhận `DONE` (`2026-07-22`) và được dùng làm baseline chính thức cho ticket này — thay cho snapshot mượn tạm `D13-COST-01` dùng ở bản trước.

Số liệu dưới đây đo đúng 3 pod bị gỡ (`postgresql`, `valkey-cart`, `kafka`), không lẫn pod-churn của service khác — đây là matrix **sạch**, thỏa acceptance criterion "before/after reservation matrix":

| Chỉ số | Before (`D8-PERF-01`, 3 pod tự host) | After (`2026-07-22`, 3 pod đã gỡ) | Evidence |
| --- | --- | --- | --- |
| Pod count (3 data pod) | 3 (`postgresql`, `valkey-cart`, `kafka`) | 0 | `01-pre-migration-baseline.md` §4A; `raw/01-pods-after.txt` |
| Total requests.cpu (3 pod) | `170m` | `0m` (giảm `170m`) | `01-pre-migration-baseline.md` §4A |
| Total requests.memory (3 pod) | `988Mi` | `0Mi` (giảm `988Mi`) | `01-pre-migration-baseline.md` §4A |
| Total limits.cpu (3 pod) | `1100m` | `0m` (giảm `1100m`) | `01-pre-migration-baseline.md` §4A |
| Total limits.memory (3 pod) | `1276Mi` | `0Mi` (giảm `1276Mi`) | `01-pre-migration-baseline.md` §4A |
| Node inventory (dưới tải đại diện) | 2 static managed-nodegroup (`t3.large`) + 2 Karpenter dynamic (`t3a.large`, nodepool `techx-general`) = 4 node | 2 static + 2 Karpenter = 4 node — **giống hệt baseline, không đổi** | `01-pre-migration-baseline.md` §4B; `raw/02-nodes-wide-pass1.txt`, `raw/24-nodes-wide-pass2.txt` |

### B. ResourceQuota namespace-level (bổ sung, không phải delta thuần vì lẫn service khác)

Bảng dưới đây giữ lại làm bối cảnh vận hành thực tế (namespace `techx-tf4` gồm tất cả service, không chỉ 3 pod data), qua 2 lần chụp Pass 1 và Pass 2 (~3 giờ sau):

| Chỉ số | Pass 1 (`2026-07-22T~04:53Z`) | Pass 2 (`2026-07-22T07:48:58Z`) | Nhận xét |
| --- | --- | --- | --- |
| Pod count | `28/40` | `29/40` | Tăng nhẹ — pod-churn của service khác, không liên quan việc gỡ pod data |
| Total requests.cpu | `1735m/4` | `1835m/4` | Tăng `100m` — namespace đang tải cao hơn, không giảm |
| Total requests.memory | `2759Mi/9Gi` | `2951Mi/9Gi` | Tăng `192Mi` |
| Total limits.cpu | `6350m/10` | `6750m/10` | Tăng `400m` |
| Total limits.memory | `4873Mi/12Gi` | `5193Mi/12Gi` | Tăng `320Mi` |

Evidence: `raw/04-resourcequota-pass1.yaml`, `raw/26-resourcequota-pass2.txt`. Namespace-level usage **tăng** giữa 2 pass (không giảm) — khớp với HPA `frontend` đang chạy ở `173%/70%` CPU, tối đa `3/3` replica tại thời điểm Pass 2 (`raw/27-hpa-wide-pass2.txt`) — tức có tải thật trên cluster, không phải noise.

### C. Karpenter NodeClaims — chưa có consolidation thực thi, nguyên nhân trì hoãn chưa xác nhận

| Chỉ số | Pass 1 (`2026-07-22T~04:57Z`) | Pass 2 (`2026-07-22T07:48:58Z`) | Evidence |
| --- | --- | --- | --- |
| NodeClaim count | 2 | 2 — không đổi | `raw/20-nodeclaims-granted.txt`, `raw/25-nodeclaims-pass2.txt` |
| `techx-general-djg4k` | UID `4bf307e1-1397-4555-98b2-7394c1743038`, AGE `6d1h` | **UID giống hệt**, AGE `6d3h` | cùng trên |
| `techx-general-jchb5` | UID `8d017ad8-0daf-409b-a52d-4247c8a2b662`, AGE `3d9h` | **UID giống hệt**, AGE `3d11h` | cùng trên |
| Node count | 4 `Ready` | 4 `Ready` — không đổi | `raw/02-nodes-wide-pass1.txt`, `raw/24-nodes-wide-pass2.txt` |
| ASG `desiredSize` (managed-nodegroup) | `2` | `2` — không đổi | `raw/10-asg-desiredsize.txt`, `raw/30-asg-desiredsize-pass2.txt` |
| PVC/EBS | 3 PVC `Bound`, EBS `available` (detached) | Không đổi — vẫn 3 PVC `Bound` | `raw/06-pvc-ebs-after.txt`, `raw/28-pvc-ebs-pass2.txt` |
| Pending/FailedScheduling | 0/0 | 0/0 — không đổi | `raw/07-events-failedscheduling-pass1.txt`, `raw/29-events-failedscheduling-pass2.txt` |

**So sánh bằng UID (không chỉ tên/AGE) giữa Pass 1 và Pass 2 khẳng định: đây là chính xác cùng 2 NodeClaim, không có cái nào bị terminate và tạo lại, không có NodeClaim mới.**

**Phát hiện quan trọng (từ `status.conditions` trong cùng file `raw/20`/`raw/25`, dùng `kubectl get nodeclaims -o yaml`):** cả 2 NodeClaim đều mang điều kiện `type: Consolidatable, status: "True"` — `djg4k` từ `2026-07-22T04:16:16Z`, `jchb5` từ `2026-07-22T05:41:28Z` (cả hai đều **trước** hoặc **trong** thời điểm thu thập Pass 1, và vẫn còn `True` tại Pass 2). Nghĩa là **Karpenter controller tự đánh giá cả 2 node là đủ điều kiện consolidation**, nhưng **chưa thực thi termination** dù đã treo ở trạng thái này nhiều giờ (`raw/31-nodeclaims-consolidatable-condition.txt`).

**Kiểm tra thêm để tìm nguyên nhân trì hoãn:** cả 2 node hiện đang chạy khối lượng lớn pod ứng dụng thật, không hề "rảnh":
- `ip-10-0-11-217.ec2.internal` (`djg4k`): `cart`, `checkout`, `product-catalog`, `quote`, `shipping` + nhiều pod hệ thống/observability.
- `ip-10-0-10-19.ec2.internal` (`jchb5`): `accounting`, `checkout`, `currency`, `fraud-detection`, `frontend-proxy`, `payment`, `quote`, `recommendation`, `shipping` + nhiều pod hệ thống/observability.

Namespace `techx-tf4` có 9 `PodDisruptionBudget` (`cart`, `checkout`, `currency`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `quote`, `shipping`), mỗi cái `minAvailable: 1` / `allowedDisruptions: 1` (`raw/31-nodeclaims-consolidatable-condition.txt`).

**Kết luận:** Karpenter đã đánh giá cả 2 node là *có thể* consolidate (`Consolidatable: True`), nhưng **chưa thực thi** tính đến Pass 2 — nhiều khả năng liên quan đến việc phải di dời an toàn số lượng lớn pod production đang được PDB bảo vệ, nhưng **chưa xác nhận được đây là nguyên nhân chắc chắn** (dữ liệu tĩnh trong repo không đủ để loại trừ các khả năng khác). **Không thể khẳng định "sẽ không bao giờ consolidate"** — `Consolidatable: True` vẫn đang treo, có thể thực thi ở bất kỳ thời điểm nào sau đó. Đây là data point hợp lệ cho Pass 2 (không có consolidation *tính đến thời điểm này*), nhưng không phải kết luận cuối cùng, dứt khoát.

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

| Điều kiện | Trạng thái | Evidence |
| --- | --- | --- |
| cutover PASS | **PASS** | `raw/01-pods-after.txt`: không còn pod `postgresql`/`valkey-cart`/`kafka`/`orders-mirrormaker2`. Khớp `docs/cdo08/week2/mandate8/evidence/MANDATE-08-MANAGED-DATA-MIGRATION-EVIDENCE.md` và `REL-17-kafka-msk-cutover-evidence.md` (§7: "PASS") |
| data parity PASS | **Chưa xác nhận sau cutover** | `docs/cdo08/week2/mandate8/evidence/REL-15-postgresql-parity-evidence.md` (`2026-07-21`) — tài liệu mới nhất tìm được — ghi `Final frozen parity: PENDING`, `App cutover: NOT STARTED`, tức là trước cutover. Không có tài liệu parity mới hơn cho Postgres; không có evidence parity cho Valkey/Kafka |
| stabilization PASS | **Chưa đạt** | Pod bị kill mới ~1h tại thời điểm thu thập Pass 1 (`raw/07-events-failedscheduling-pass1.txt`); cùng file còn ghi nhận lỗi `FailedDeployModel` (security group `DependencyViolation`) trên `postgresql-migration-bridge`/`valkey-migration-bridge` và probe failure của `orders-mirrormaker2` — cleanup hạ tầng migration bridge chưa xong. CDO-08 tự liệt kê "observation window" là follow-up còn mở |
| rollback decision cho phép cleanup | **Chưa đạt** | `kafka-pvc`/`postgresql-pvc`/`valkey-cart-pvc` cố tình giữ `Bound`; CDO-08 evidence nói rõ không xóa trước khi PM/owner xác nhận rollback window đã đóng |

Việc thực hiện Pass 1/Pass 2 ở trên được tiến hành theo chỉ đạo của Tuấn dù chỉ **1/4 điều kiện đạt PASS** (cutover) — **3/4 điều kiện còn lại (data parity, stabilization, rollback decision) đều pending**. Số liệu capacity vẫn được ghi nhận làm data point, nhưng **PVC/EBS không được xóa** và **không claim saving** cho đến khi đủ 4 điều kiện.

---

## CDO-04 Review

**CDO-04 review `2026-07-22`: APPROVE PASS 1 / KEEP TASK OPEN.**

D8-COST-02 đã hoàn thành tốt phần thu thập capacity ngay sau cutover: không còn PostgreSQL/Valkey/Kafka pod tự host; node count vẫn 4; không có Pending/FailedScheduling; HPA/ResourceQuota vẫn hoạt động; đọc trực tiếp được 2 Karpenter NodeClaim; không có NodeClaim mới sinh ra từ cutover; không claim saving khi node-hours/PVC/EBS cost chưa giảm.

Các điểm chưa đủ để đóng task tại thời điểm review: Safety Rule thực tế 1/4 PASS (không phải 2/4 chưa đạt như bản ghi trước đó); before reservation matrix khi đó còn mượn từ `D13-COST-01`; node count 4→4 mới là Pass 1, chưa phải final resting; chưa có Karpenter consolidation evidence; PVC vẫn `Bound`/EBS chỉ detached; chưa có post-cutover data parity; stabilization window chưa đủ.

**Required next steps đã thực hiện trong Pass 2 này:** chạy Pass 2 sau khi qua nhiều chu kỳ consolidation window; so sánh NodeClaim UID/count, node count, ASG `desiredSize`, node-hours (§Before/After Comparison mục C); dùng `D8-PERF-01` (PM đã xác nhận `DONE`) làm reservation matrix chính thức thay `D13-COST-01` (§mục A).

**Required next steps còn mở:** chốt post-cutover parity; chờ rollback approval rồi mới xóa PVC/EBS; re-pull billing khi không còn `Estimated`; công bố final result kể cả trường hợp saving bằng 0 — kết luận "Karpenter consolidation: không xảy ra" ở Pass 2 chính là áp dụng nguyên tắc này.

**Proposed status (PM, giữ nguyên sau Pass 2):**

```
D8-COST-02: IN PROGRESS
PASS 1: COMPLETE
FINAL CAPACITY VERDICT: PENDING
COST SAVING: NOT PROVEN
```

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

**Áp vào dữ liệu hiện có (`2026-07-22`, sau Pass 2):**

| Điều kiện chặn saving | Trạng thái |
| --- | --- |
| node count không giảm | Đúng — vẫn 4 node qua cả Pass 1 và Pass 2, `desiredSize` ASG vẫn `2` |
| NodeClaim lifetime không giảm | Đúng — chứng minh bằng UID: cả 2 NodeClaim giống hệt giữa Pass 1 và Pass 2, không NodeClaim nào kết thúc |
| removed reservation không tạo consolidation | Đúng, tính đến Pass 2 — cả 2 NodeClaim đã `Consolidatable: True` nhưng chưa terminate; chưa loại trừ khả năng xảy ra ở Pass sau |
| billing chưa đủ dữ liệu | Đúng — toàn bộ Cost Explorer response `Estimated: true` |

→ **Không claim saving.** Cả 4 điều kiện chặn trong công thức đều đang áp dụng. `Removed EKS cost` hiện để `$0`/chưa xác định, khớp lập trường mặc định của `D8-COST-01` (branch `origin/codex/d8-cost-01-net-cost-model`).

---

## Acceptance Criteria

- [x] Không còn PostgreSQL pod tự host. — xác nhận `2026-07-22`, `raw/01-pods-after.txt`.
- [x] Không còn Valkey pod tự host. — xác nhận `2026-07-22`, `raw/01-pods-after.txt`.
- [x] Không còn Kafka pod tự host. — xác nhận `2026-07-22`, `raw/01-pods-after.txt`.
- [x] Có before/after reservation matrix. — **Đạt.** Dùng baseline chính thức `D8-PERF-01` (PM xác nhận `DONE`), delta sạch 100% attributable cho 3 pod bị gỡ (§Before/After Comparison mục A).
- [x] Có before/after node count. — **Đạt.** 4→4, xác nhận ổn định qua 2 pass cách nhau ~3 giờ (không chỉ 1 lần chụp).
- [x] Có Karpenter consolidation evidence. — **Đạt, ở dạng quan sát chưa kết luận cuối.** Pass 2 chứng minh bằng UID: chưa có consolidation nào xảy ra tính đến thời điểm này; đồng thời phát hiện cả 2 NodeClaim đã `Consolidatable: True` nhưng chưa terminate, nhiều khả năng do PDB trên các pod production đang chạy trên đó — chưa xác nhận chắc chắn, không loại trừ consolidation xảy ra sau. Đây là bằng chứng hợp lệ theo đúng nguyên tắc "công bố final result kể cả saving = 0", không phải bằng chứng "sẽ không bao giờ xảy ra".
- [ ] Có removed PVC/EBS inventory. — **Chưa đạt.** Cả 3 PVC vẫn `Bound` ở cả Pass 1 và Pass 2, EBS chỉ detach chứ chưa xóa — chờ rollback decision.
- [x] Không có Pending hoặc node pressure. — xác nhận qua cả Pass 1 và Pass 2, `raw/07-events-failedscheduling-pass1.txt`, `raw/29-events-failedscheduling-pass2.txt`.
- [x] Không claim saving nếu node-hours chưa giảm. — tuân thủ, xem phần Cost Formula ở trên.

---

## Dependency

Depends on successful cutover và cleanup approval.

- **Cutover:** thành công — xem Safety Rule ở trên (`PASS`).
- **Cleanup approval:** **chưa có.** Rollback decision chưa cho phép cleanup (PVC vẫn giữ `Bound`), nên tiêu chí "removed PVC/EBS inventory" chưa thể đóng.

---

## Evidence files (`docs/evidence/directive-08/cost/raw/`)

| File | Nội dung |
| --- | --- |
| `00-collection-metadata.txt` | Timestamp, AWS identity Pass 1 |
| `01-pods-after.txt` | `kubectl get pods -n techx-tf4 -o wide` |
| `02-nodes-wide-pass1.txt` | `kubectl get nodes -o wide` (Pass 1) |
| `03-hpa-wide-pass1.txt` | `kubectl get hpa -A -o wide` (Pass 1) |
| `04-resourcequota-pass1.yaml` | `kubectl get/describe resourcequota techx-quota` (Pass 1) |
| `06-pvc-ebs-after.txt` | `kubectl get pvc` + `aws ec2 describe-volumes` cho từng PVC (Pass 1) |
| `07-events-failedscheduling-pass1.txt` | Sự kiện `FailedScheduling`, pod `Pending` (Pass 1) |
| `08-pricing-attempt.txt` | `aws pricing get-products` cho `t3a.large`/`t3.large`/`gp2` |
| `09-ce-cost-and-usage.json` | `aws ce get-cost-and-usage`, `2026-07-15`..`2026-07-22` theo ngày theo service |
| `10-asg-desiredsize.txt` | `aws autoscaling describe-auto-scaling-groups` (Pass 1) |
| `11-node-labels.txt` | Label node phân biệt managed-nodegroup vs. Karpenter |
| `20-nodeclaims-granted.txt` | `kubectl get nodeclaims -o wide/-o yaml` (Pass 1) — 2 NodeClaim, AGE `6d1h`/`3d9h` |
| `21-nodepools-still-denied.txt` | `kubectl get nodepools` — `Forbidden`; xem `D8-ACCESS-REQUEST-cost-perf-readonly.md` §4 nếu cần config NodePool sau này |
| `23-pass2-collection-metadata.txt` | Timestamp, AWS identity Pass 2 (`2026-07-22T07:48:58Z`) |
| `24-nodes-wide-pass2.txt` | `kubectl get nodes -o wide` (Pass 2) |
| `25-nodeclaims-pass2.txt` | `kubectl get nodeclaims -o wide/-o yaml` (Pass 2) — cùng UID với Pass 1 |
| `26-resourcequota-pass2.txt` | `kubectl get/describe resourcequota techx-quota` (Pass 2) |
| `27-hpa-wide-pass2.txt` | `kubectl get hpa -A -o wide` (Pass 2) — `frontend` ở `173%/70%`, `3/3` replica |
| `28-pvc-ebs-pass2.txt` | `kubectl get pvc -n techx-tf4 -o wide` (Pass 2) |
| `29-events-failedscheduling-pass2.txt` | Sự kiện `FailedScheduling`, pod `Pending` (Pass 2) — 0/0 |
| `30-asg-desiredsize-pass2.txt` | `aws autoscaling describe-auto-scaling-groups` (Pass 2) |
| `31-nodeclaims-consolidatable-condition.txt` | `Consolidatable: True` condition trên cả 2 NodeClaim (chưa terminate); PDB namespace `techx-tf4`; danh sách pod thật đang chạy trên 2 node Karpenter |

---

## Việc còn lại trước khi đóng ticket

1. ~~Pass 2~~ — **Đã hoàn thành.** Kết luận: chưa có Karpenter consolidation tính đến thời điểm này (chứng minh bằng NodeClaim UID qua 2 pass cách nhau ~3 giờ), nhưng cả 2 NodeClaim đã `Consolidatable: True` — chưa loại trừ khả năng xảy ra sau. Nên chạy thêm Pass 3 xa hơn (ví dụ sau 12-24h) nếu cần kết luận chắc hơn về việc consolidation có bao giờ thực thi hay không.
2. Quyền đọc `nodepools.karpenter.sh` hiện vẫn `Forbidden` (`raw/21-nodepools-still-denied.txt`) — không chặn kết luận consolidation ở trên, nhưng cần nếu sau này phải kiểm tra cấu hình NodePool.
3. Re-pull Cost Explorer sau khi hết cờ `Estimated: true` (24-48h+ sau cutover) trước khi tính `Removed EKS cost` thật.
4. Data-parity PASS chính thức sau cutover cho cả 3 data store (hiện chỉ có bản parity Postgres trước cutover, đã cũ) — flag CDO-08 nếu vẫn thiếu.
5. Xác nhận thời điểm/điều kiện xóa PVC/EBS (rollback window đóng) trước khi đánh dấu "removed PVC/EBS inventory" hoàn tất — đây là điều kiện duy nhất còn lại chưa có bằng chứng, cùng với data parity/stabilization/rollback decision ở Safety Rule.
