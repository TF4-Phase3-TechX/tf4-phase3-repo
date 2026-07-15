# D3-COST-02 — Post-Maintenance Scale-Down and Cost Verification

**Directive:** #3 — Maintenance Capacity & Cost-Efficient Resilience
**Owner:** Tuấn — CDO-04 Performance Efficiency & Cost Optimization
**Cluster:** `techx-tf4-cluster` (`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`)
**Namespace:** `techx-tf4`
**Region:** `us-east-1`
**Thư mục evidence:** `./raw/`
**Trạng thái:** **PARTIAL — 4/7 tiêu chí PASS, 3/7 PENDING, 0/7 FAIL**. `quote` **không còn là unresolved drift** — CDO-08 đã xác nhận `quote` thuộc mandatory drain/SLO scope và remediation (2 replica, PDB, topology spread, TCP probes) đã apply/verify; xem mục 1. Không đánh giá/đối chiếu với D3-PERF-04 — nằm ngoài phạm vi task này.

---

## 0. Phạm vi & phương pháp

Baseline "before" duy nhất hiện có trong repo là `D3-PERF-01` (`docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-PERF-01-revenue-path-capacity-inventory/`, thu thập 2026-07-14): toàn bộ 9 service revenue-path chạy `1/1/1`, không HPA ngoại trừ `frontend`/`checkout` (min=1/max=3).

Verify qua **2 lần đo**, cách nhau ~5h40', đều read-only (`get`/`describe`/`top`/`logs`/`auth can-i`; không `scale`/`create`/`delete`/`apply`/`patch`/`exec`), cộng 1 lần đo bổ sung cho phần cost sau khi đổi role:

| Lần đo       | Thời điểm (UTC)        | Role AWS                       |
| ------------ | ---------------------- | ------------------------------ |
| Lần 1        | `2026-07-15T10:49:05Z` | `TF4-BaseReadOnly`             |
| Lần 2        | `2026-07-15T16:29Z`    | `TF4-BaseReadOnly`             |
| Lần 3 (cost) | `2026-07-15T16:35Z`    | `TF4-CostPerfReadOnlyAlerting` |

---

## 1. Temporary replicas / HPA quay về baseline

| Service           | Baseline `D3-PERF-01` (14/07) |                     Lần 1 (10:49Z) |                    Lần 2 (16:29Z) |
| ----------------- | ----------------------------: | ---------------------------------: | --------------------------------: |
| `cart`            |                         1/1/1 |                              2/2/2 |                             2/2/2 |
| `checkout`        |                1/1/1, HPA 1–3 |             2/2/2, HPA min=2/max=3 | 2/2/2, HPA min=2/max=3 (44h tuổi) |
| `currency`        |                         1/1/1 | 2/2/2, HPA min=2/max=3 (144m tuổi) |  2/2/2, HPA min=2/max=3 (8h tuổi) |
| `frontend`        |                1/1/1, HPA 1–3 |  3/3/3, HPA min=2/max=3, kịch trần | 2/2/2, HPA min=2/max=3 (44h tuổi) |
| `frontend-proxy`  |                         1/1/1 |                              2/2/2 |                             2/2/2 |
| `payment`         |                         1/1/1 |                              2/2/2 |                             2/2/2 |
| `product-catalog` |                         1/1/1 |                              2/2/2 |                             2/2/2 |
| `quote`           |                         1/1/1 |                              1/1/1 |                         **2/2/2** |
| `shipping`        |                         1/1/1 |                              2/2/2 |                             2/2/2 |

- **7/9 service (`cart`, `checkout`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `shipping`) tăng lên 2 replica là thay đổi baseline có chủ đích, đã duyệt** — theo `docs/cdo08/week2/cdo08-rel-01-replica-availability-proposal.md` (`CDO08-REL-01`, owner Hoàng Nam, P0, mục tiêu loại SPOF single-replica trên customer/checkout path). Đề xuất chốt **2 replica làm fixed baseline**, không phải scale tạm cho một lần test. Vậy **mức 2/2/2 quan sát được ở cả 2 lần đo không phải "temporary replicas cần rollback" — đây là baseline mới đã duyệt**, tiêu chí "temporary replicas về baseline" áp dụng đúng hơn cho baseline mới này, không phải baseline `D3-PERF-01` (1/1/1) vốn đã lỗi thời sau `REL-01`.
- **HPA `frontend`/`checkout` (min=2/max=3) được xác nhận trong `docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md`** (mục 4.3, 5 — dependency đánh dấu **RESOLVED**), cùng nguồn xác nhận PDB `minAvailable=1` cho 8 service. Tài liệu D3-COST-01 có **runtime validation lúc `2026-07-15T11:23:53Z`** (`raw/17-final-validation-metadata.txt` của D3-COST-01) — nằm trong đúng buổi sáng 15/07, khớp thời điểm 2 lần đo của D3-COST-02.
- **`currency` HPA (min=2/max=3) KHÔNG có trong danh sách D3-COST-01/CDO08-REL-01** — chỉ liệt kê `frontend`/`checkout`. Vẫn **chưa giải trình được**, cần hỏi CDO-04/Vinh riêng cho `currency`.
- **`quote` — RESOLVED, không còn là unresolved drift.** Tại thời điểm validation `11:23:53Z` (bản D3-COST-01 trước cập nhật), `quote` vẫn `1/1` và scope quyết định còn PENDING CDO-04 REVIEW. Sau đó **CDO-08 đã xác nhận `quote` thuộc mandatory drain/SLO scope**, và bản cập nhật của `D3-COST-01` (mục 4.2/4.4/10, PR #226) ghi nhận remediation đã **apply và verify**: `2/2` ready, PDB `minAvailable=1`/`allowedDisruptions=1`, topology spread theo `kubernetes.io/hostname`, readiness/liveness probe `tcpSocket:8080`, 2 serving endpoints trên 2 node/2 AZ khác nhau (`raw/30-quote-post-remediation-cost-input.txt`, `raw/31-post-remediation-node-inventory.txt` của `D3-COST-01`). Vậy **`quote` 2/2 là baseline mới đã được approve**, không phải một thay đổi thiếu quyết định đi kèm.

**Kết quả: Replica đã ĐẠT cho 9/9 service** (`cart`, `checkout`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `shipping` theo `CDO08-REL-01`; `quote` theo remediation đã verify trong `D3-COST-01` bản cập nhật; `currency` replica count cũng ở baseline 2/2/2 đã duyệt). **Nhưng HPA `currency` (min=2/max=3) chưa rõ nguồn** — giữ **PENDING EXPLANATION** cho đến khi có PR/config decision hoặc owner confirmation xác nhận ai tạo và có nên giữ. Vì vậy tiêu chí gộp "replica & HPA" của mục này map sang **PENDING** trong mục 9 (không phải FAIL — chỉ 1/9 service có 1 sub-item chưa rõ nguồn).

Raw: `raw/03-hpa-wide.txt`, `raw/04-deploy-replica-summary.txt` (lần 1) và `raw/19-deploy-replica-summary-round2.txt`, `raw/20-hpa-wide-round2.txt` (lần 2). Nguồn giải trình: `docs/cdo08/week2/cdo08-rel-01-replica-availability-proposal.md`, `docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md`.

---

## 2. Node group quay về baseline nếu đã tăng

- **EKS-managed node group (ASG chính):** `desiredSize=2/minSize=2/maxSize=4` — **không đổi** giữa baseline, lần 1, lần 2. 2 instance `i-01b00d955a0af0fac` (`ip-10-0-10-231`) và `i-0825abf366929a005` (`ip-10-0-11-40`), cả hai `InService`/`Healthy` liên tục, `LaunchTime` không đổi từ `2026-07-09`. (`raw/22-nodegroup-describe-round2.json`, `raw/28-asg-describe-round2.json`)
- `kubectl describe node ip-10-0-10-231`: `Unschedulable: false`, không taint — node đang ở trạng thái schedulable bình thường, không phải đang bị cordon tạm. (`raw/23-node-ip-10-0-10-231-describe-round2.txt`)

**Kết quả: ĐẠT.** Node group ASG chính không hề tăng vượt baseline ở bất kỳ thời điểm nào trong 2 lần đo — không có gì cần "quay về" vì chưa từng rời khỏi `desiredSize=2`.

---

## 3. Load-generator dừng

- `LOCUST_AUTOSTART=true` ở **cả 2 lần đo** — trái quy định bắt buộc `false` (gap `COST-01` đã biết từ epic-01). (`raw/08-loadgenerator-env.json`, `raw/32-loadgenerator-env-round2.json`)
- Pod `load-generator-7dbc8d784-gsmdf` chạy liên tục **6h10m** tính đến lần đo 2 (từ ~10:19 UTC), không có dấu hiệu đã dừng.
- `kubectl logs --since=15m` rỗng — không đủ để kết luận có/không traffic (Locust web-mode không log mỗi request ra stdout).
- Không xác nhận được active user qua Locust stats API: `kubectl auth can-i create pods/exec` và `pods/portforward` đều trả `no` ở cả 2 lần đo. (`raw/14-permission-checks.txt`)

**Kết quả: PENDING.** Không có bằng chứng load-generator đã dừng — cần evidence cụ thể Deployment `replicas=0` hoặc traffic/users=0 ngoài test window; ngược lại, cấu hình `AUTOSTART=true` là rủi ro cụ thể. Cần người có quyền `pods/exec` hoặc Grafana UI (dashboard `LoadGeneratorTrafficOutsideTestWindow`, `docs/audit/runbooks/flash-sale-alerts.md`) xác nhận dứt điểm.

---

## 4. Không còn temporary resources / không phát sinh workload chạy nền ngoài kế hoạch

- **Node Karpenter ngoài ASG (dynamic capacity)** quan sát được ở **cả 2 lần đo** — 2 instance khác nhau, khớp với dynamic capacity mà `D3-COST-01` đã mô hình hóa (không phải resource lạ):
  - Lần 1: `ip-10-0-10-74` / `i-029d41ebaa83f4358`, `t3a.large`, launch `2026-07-15T03:46:26Z`, đã chạy ~7h tại thời điểm đo. (`raw/07-ec2-instance-10-0-10-74.json`, `raw/11-node-ip-10-0-10-74-describe.txt`)
  - Lần 2: `ip-10-0-10-17` / `i-05a5387fbf39a3e02`, `t3a.large`, launch `2026-07-15T10:52:32Z`. (`raw/24-node-ip-10-0-10-17-describe-round2.txt`, `raw/27-ec2-karpenter-node-ip-10-0-10-17-round2.json`)
  - `aws ec2 describe-instances` lọc theo tag cluster (mọi trạng thái) chỉ trả về 2 instance ASG gốc — node Karpenter không mang tag `eks:cluster-name` giống ASG, xác nhận đây là compute ngoài luồng quản lý chuẩn. (`raw/26-ec2-all-cluster-instances-round2.json`)
  - Pod `load-generator` (mục 3) chạy trên chính node Karpenter này ở lần 2.
- Không phát hiện Deployment/Pod thủ công nào khác ngoài Helm-managed workload trong `techx-tf4` — danh sách pod khớp với các service đã biết trong `ARCHITECTURE.md`.

**Cập nhật — có giải trình một phần từ `D3-COST-01`:** tài liệu `docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md` (mục 3.2, 4.1, 7) xác nhận Karpenter capacity build-up là **có chủ đích**, không phải rò rỉ ngẫu nhiên:

- NodePool Karpenter cho phép `t3.large`/`t3a.large`, `limits.cpu=16`, `consolidationPolicy=WhenEmptyOrUnderutilized`, `consolidateAfter=5m` — nghĩa là Karpenter **tự động co node khi không còn cần**, không cần ai xoá thủ công.
- D3-COST-01 mục 7 (Scenario B) chốt **"4 total workers" (2 managed + 2 Karpenter) là minimum maintenance target** cho controlled-drain rehearsal — tức việc có thêm node Karpenter ngoài 2 node ASG **là kế hoạch đã duyệt**, không phải lỗi.
- Runtime validation của D3-COST-01 lúc `11:23:53Z` ghi nhận **4 node Ready** (2 managed + 2 Karpenter). Lần đo 2 của D3-COST-02 (16:29Z, ~5h sau) chỉ còn **3 node** (2 managed + 1 Karpenter) — tức Karpenter **đã tự co bớt 1 node** đúng theo consolidation policy, một phần scale-down đã xảy ra tự nhiên.

**Điểm còn hở:** Theo bản cập nhật mới nhất của `D3-COST-01` (PR #226), `quote` scope decision đã **RESOLVED**, nhưng controlled-drain rehearsal và actual-cost reconciliation vẫn còn **PENDING** — tài liệu đó tự nhận trạng thái tổng **"READY FOR REVIEW — NOT YET CLOSED"**. Quan trọng: `D3-COST-01` xác nhận **runtime hiện tại là 3 workers (2 managed `t3.large` + 1 Karpenter `t3a.large`)** — đây là **observed runtime state**, được chính tài liệu đó ghi rõ là "chưa đủ để chứng minh controlled drain an toàn"; 4 node vẫn chỉ là **khuyến nghị minimum target cho rehearsal**, chưa phải node hiện có. Vậy node Karpenter còn lại ở lần đo 2 (`ip-10-0-10-17`) **không phải "node thừa"/"non-value-add"/"rớt lại"** — nó là một phần của capacity model đã được `D3-COST-01` mô hình hóa và giải thích (Scenario A/B, mục 7) — nhưng **final resting baseline (số worker nghỉ chính thức sau khi hoàn tất mọi rehearsal) vẫn chưa được formally approved**. `load-generator` (mục 3) đang chạy ngay trên node này cũng cần lưu ý riêng.

**Kết quả: PENDING (không phải KHÔNG ĐẠT).** Việc có node Karpenter ngoài ASG khớp với capacity model đã duyệt trong `D3-COST-01` (không phải resource lạ/rò rỉ/"thừa"), và đã quan sát được Karpenter tự consolidate 4→3 node đúng theo policy. Còn thiếu duy nhất: **formal approval cho final resting baseline** (3 workers hiện observed so với 4 workers là target rehearsal) — cần Vinh/CDO-04 chốt trong lần cập nhật `D3-COST-01` tiếp theo (controlled-drain rehearsal + actual-cost reconciliation vẫn PENDING theo chính `D3-COST-01`).

---

## 5. Resource usage trở về mức bình thường

**CPU/Memory (lần 2, `2026-07-15T16:29Z`):**

| Node                        |        CPU |       Memory |
| --------------------------- | ---------: | -----------: |
| `ip-10-0-10-17` (Karpenter) | 251m (13%) | 3821Mi (53%) |
| `ip-10-0-10-231`            | 286m (14%) | 3338Mi (47%) |
| `ip-10-0-11-40`             | 475m (24%) | 3982Mi (56%) |

Không node nào pressure. (`raw/35-top-nodes-round2.txt`, `raw/36-top-pods-round2.txt`)

**Namespace quota (`techx-quota`), lần 2:** `limits.cpu = 7450m/8000m` (**93.1%** đã dùng), `limits.memory = 5893Mi/12288Mi` (48%), `pods = 31/40`. (`raw/37-resourcequota-round2.yaml`) Ở lần 1 quota CPU từng chạm **96.25%** kèm nhiều lần `FailedCreate` khi HPA `frontend` cố scale (`raw/10-events-techx-tf4.txt`). Lần 2 không còn `FailedCreate` tại thời điểm đo, nhưng quota CPU vẫn sát trần — nếu replica/HPA elevated ở mục 1 không phải baseline chính thức đã duyệt, đây là rủi ro tái diễn `FailedCreate` bất cứ lúc nào có scale-up tiếp theo.

**Jaeger (`techx-observability`, thuộc gap `COST-02` — observability stack — CDO-04 đang theo dõi):** lần 1 phát hiện pod `jaeger-5f589cc9f6-qp4ft` có 34 lần restart, gần nhất ~105s trước thời điểm đo (`raw/16-observability-pods.txt`). Lần 2, pod hiện tại (`jaeger-5f589cc9f6-2nftq`) có 0 restart, chạy ổn định 6h11m — anomaly đã tự phục hồi. (`raw/38-jaeger-pods-round2.txt`)

**Kết quả: PASS (có điều kiện).** CPU/memory node hiện bình thường và Jaeger đã ổn định, nhưng quota namespace vẫn sát trần (93.1%) — cần theo dõi tiếp nếu replica/HPA ở mục 1 không được giảm về baseline.

---

## 6. Ước tính chi phí (lần 3, `2026-07-15T16:35Z`, role `TF4-CostPerfReadOnlyAlerting`)

`raw/39-pricing-t3a-large-round2.json`, `raw/40-pricing-t3-large-round2.json`: giá On-Demand Linux, `us-east-1`, hiệu lực `2026-07-01`:

| Instance type                        | Giá compute On-Demand (USD/giờ) |
| ------------------------------------ | ------------------------------: |
| `t3a.large` (Karpenter dynamic node) |                       `$0.0752` |
| `t3.large` (2 node ASG baseline)     |                       `$0.0832` |

**Full worker cost (compute + root EBS)** — dùng đúng công thức đã áp dụng trong `D3-COST-01` (mục 2.2): root EBS `20 GiB gp3` = `$1.60/tháng` ≈ `$0.0021918/giờ`/node.

```text
Full t3a.large worker cost/node/giờ
= $0.0752 + $0.0021918
≈ $0.0773918/giờ
```

**Ước tính chi phí node Karpenter dynamic capacity (mục 4), dùng full worker cost:**

- Node hiện tại `ip-10-0-10-17`, launch `2026-07-15T10:52:32Z`, vẫn đang chạy tại thời điểm viết (`16:29:45Z`) → đã chạy **~5h37m** → **~$0.435** (`5.617h × $0.0773918`) tích lũy tính đến lúc đo, và **vẫn đang tiếp tục phát sinh** vì node chưa được Karpenter consolidate.
- Nếu để chạy nguyên 24h không xử lý: `24h × $0.0773918 ≈ $1.86/ngày`.
- Nếu để chạy nguyên 1 tuần không xử lý: `168h × $0.0773918 ≈ $13.00/tuần` — nhỏ so với ngân sách `~$300/tuần/TF`.
- Đây là chi phí của **dynamic capacity đã được `D3-COST-01` mô hình hóa** (Scenario A: 3 workers, mục 7) — không phải chi phí "non-value-add" của một node thừa. Vẫn cần approval formal cho final resting baseline (mục 4, mục 8 timeline) trước khi coi đây là chi phí ổn định lâu dài thay vì chi phí capacity đang chờ chốt.

**Đối chiếu Cost Explorer actual billing:** `raw/41-ce-cost-and-usage-round2.json` — `aws ce get-cost-and-usage` (`DAILY`, `2026-07-14` → `2026-07-16`, group theo `USAGE_TYPE`) chạy thành công, nhưng cả 2 ngày đều đánh dấu `"Estimated": true`, và bucket `BoxUsage:t3a.large` của **ngày 2026-07-15 hoàn toàn không xuất hiện** trong kết quả dù `kubectl`/`aws ec2` đã xác nhận node đó chạy suốt từ `10:52:32Z` — CE actual data có độ trễ xử lý, không phản ánh kịp usage trong ngày. Vì vậy con số **$0.435 / $1.86 / $13.00 ở trên là ước tính dựa trên full worker cost model (compute + EBS) × giờ chạy quan sát được qua `kubectl`/`aws ec2 describe-instances`, không phải actual billing đã đối chiếu** — cần chạy lại `aws ce get-cost-and-usage` sau khi CE hoàn tất xử lý (thường 24-48h) để đối chiếu con số thật.

**Kết quả: PASS** (có ước tính đầy đủ theo full worker cost, đã ghi rõ là estimate không phải actual billing).

---

## 7. Cleanup checklist có chữ ký operator

| Hạng mục                                    | Baseline (`D3-PERF-01`) | Lần 1 (10:49Z)                                  | Lần 2 (16:29Z)                                                                                        | Kết quả                                                                                                                                     | Verify | Thời gian (UTC)   |
| ------------------------------------------- | ----------------------- | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ----------------- |
| Temporary replicas về baseline              | 1/1/1                   | 8/9 > baseline (`quote` vẫn ở baseline 1/1/1)   | 9/9 > baseline (`quote` remediation apply sau đó, xem `D3-COST-01`)                                   | ✅ Đạt có giải trình (`CDO08-REL-01` 7/9 + `D3-COST-01` `quote` remediation verified) — 8/9 rõ nguồn                                        | Tuấn   | 2026-07-15T16:29Z |
| HPA về min replica                          | min=1                   | min=2 (`frontend`/`checkout`), mới ở `currency` | Không đổi so với lần 1                                                                                | ⚠️ PENDING — `frontend`/`checkout` đã giải trình (`D3-COST-01`); `currency` vẫn **PENDING EXPLANATION**                                     | Tuấn   | 2026-07-15T16:29Z |
| Node group về baseline                      | desired=2               | desired=2                                       | desired=2, 2 instance InService                                                                       | ✅ Đạt                                                                                                                                      | Tuấn   | 2026-07-15T16:29Z |
| Load-generator dừng                         | N/A                     | `AUTOSTART=true`, không xác nhận active user    | Không đổi                                                                                             | ⚠️ PENDING — cần evidence Deployment `replicas=0` hoặc traffic/users=0 ngoài test window                                                    | Tuấn   | 2026-07-15T16:29Z |
| Không còn temporary resources               | 2 node                  | 3 node (1 Karpenter dynamic capacity)           | 3 node (1 Karpenter dynamic capacity, instance khác)                                                  | ⚠️ PENDING — khớp capacity model `D3-COST-01` (Scenario B + consolidation 4→3 quan sát được), final resting baseline chưa formally approved | Tuấn   | 2026-07-15T16:29Z |
| Resource usage bình thường                  | 93%/80% CPU (2 node)    | <90%/<85% (3 node)                              | 13-24% CPU, 47-56% mem (3 node); quota 93.1%                                                          | ✅ Đạt (có điều kiện — quota sát trần)                                                                                                      | Tuấn   | 2026-07-15T16:29Z |
| Không phát sinh workload nền ngoài kế hoạch | N/A                     | `AUTOSTART=true` + node Karpenter dynamic       | Không đổi                                                                                             | ⚠️ PENDING — load-generator chưa xác nhận idle; node Karpenter đã khớp capacity model đã duyệt                                              | Tuấn   | 2026-07-15T16:29Z |
| Estimated cost                              | N/A                     | Không lấy được (role thiếu quyền)               | Full worker cost `t3a.large` $0.0773918/h; ~$0.435 tích lũy, ~$1.86/24h, ~$13.00/tuần nếu không xử lý | ✅ Có ước tính đầy đủ (không phải actual billing)                                                                                           | Tuấn   | 2026-07-15T16:35Z |

---

## 8. Maintenance lifecycle timeline (worker count & node-hours)

Chưa có một controlled-drain rehearsal chính thức nào được thực hiện (rehearsal vẫn **PENDING** theo chính `D3-COST-01` mục 11). Bảng dưới đây ghi lại các mốc quan sát được quanh giai đoạn remediation/replica-scale-up (`CDO08-REL-01`) và scale-down tự nhiên của Karpenter, không phải một sự kiện drain đã lên kế hoạch.

| Giai đoạn                                                                 | Thời điểm (UTC)                                                                                                                                      | Nguồn                                                                        | Worker count                                                                                                                                                 | Node-hours (dynamic/Karpenter)                                                                                                          |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| **Before** (baseline pre-maintenance)                                     | 2026-07-14                                                                                                                                           | `D3-PERF-01` `raw/06-nodes-wide.txt`                                         | 2 (managed `t3.large` only: `ip-10-0-10-231`, `ip-10-0-11-40`)                                                                                               | 0h — chưa có Karpenter node                                                                                                             |
| **During** — lần đo 1 (`D3-COST-02`)                                      | `2026-07-15T10:49:05Z`                                                                                                                               | `D3-COST-02` `raw/00`, `raw/02`                                              | 3 (2 managed + 1 Karpenter `ip-10-0-10-74`, launch `03:46:26Z`)                                                                                              | ~7h tích lũy tại thời điểm đo                                                                                                           |
| **During** — final validation (`D3-COST-01`, pre-`quote`-update)          | `2026-07-15T11:23:53Z`                                                                                                                               | `D3-COST-01` `raw/23-final-node-capacity.txt`, `raw/24-final-node-usage.txt` | 4 (2 managed + 2 Karpenter — `ip-10-0-10-17`, `CreationTimestamp` `10:52:56Z`, age ~31 phút; `ip-10-0-11-89`, `CreationTimestamp` `11:08:54Z`, age ~15 phút) | `ip-10-0-10-17` ~31 phút; `ip-10-0-11-89` ~15 phút tại thời điểm đo                                                                     |
| **Maintenance completed** — Karpenter co node qua nhiều lần churn         | Giữa `10:49:05Z` và `16:29Z` (các thời điểm terminate chính xác không có evidence, suy ra từ các lần đo)                                             | `D3-COST-01` `raw/23`/`raw/24` + `D3-COST-02` mục 4                          | 3 (2 managed + 1 Karpenter `ip-10-0-10-17` — cả `ip-10-0-10-74` lẫn `ip-10-0-11-89` đều đã bị terminate qua 2 lần churn riêng biệt)                          | `ip-10-0-10-74`: bounded ~7h02m–~7h37m (biến mất trước `11:23:53Z`); `ip-10-0-11-89`: bounded ~15 phút–~5h20m (biến mất trước `16:29Z`) |
| **Post-check 1** — lần đo 2 (`D3-COST-02`)                                | `2026-07-15T16:29Z`                                                                                                                                  | `D3-COST-02` `raw/19`–`raw/38`                                               | 3 (2 managed + 1 Karpenter `ip-10-0-10-17`)                                                                                                                  | ~5h37m tích lũy (`ip-10-0-10-17`), ≈ `$0.435` theo full worker cost                                                                     |
| **Post-check 2** — `D3-COST-01` post-remediation validation (`quote` 2/2) | Suy ra ~`17:2Xz` từ AGE `6h30m` trong `raw/31-post-remediation-node-inventory.txt` (launch `10:52:32Z`; không có timestamp tuyệt đối trong evidence) | `D3-COST-01` `raw/30`–`raw/33` (PR #226)                                     | 3 (2 managed + 1 Karpenter `ip-10-0-10-17`, không đổi)                                                                                                       | ~6h30m tích lũy (`ip-10-0-10-17`)                                                                                                       |

**Sửa lại so với bản nháp trước:** bản trước của mục này gán nhầm `ip-10-0-10-74` là node Karpenter thứ hai tại thời điểm final validation (`11:23:53Z`) của `D3-COST-01`. Đối chiếu trực tiếp `raw/23-final-node-capacity.txt`/`raw/24-final-node-usage.txt` của `D3-COST-01` cho thấy node thứ hai thực tế là `ip-10-0-11-89` (`CreationTimestamp` `2026-07-15T11:08:54Z`) — một instance Karpenter khác, chưa từng xuất hiện trong bất kỳ raw evidence nào của `D3-COST-02`. Vậy có **3 instance Karpenter riêng biệt** xuất hiện xuyên suốt task này, không phải 2: `ip-10-0-10-74` (lần đo 1, mất trước `11:23:53Z`), `ip-10-0-11-89` (chỉ thấy trong `D3-COST-01` lúc `11:23:53Z`, mất trước `16:29Z`), và `ip-10-0-10-17` (xuất hiện từ `~10:52Z`, tồn tại xuyên suốt đến lần đo cuối). Không có timestamp terminate chính xác cho `ip-10-0-10-74` hay `ip-10-0-11-89` trong evidence hiện có — chỉ biết khoảng tồn tại bị chặn trên/dưới như trong bảng trên. Không suy diễn số chính xác vượt quá bằng chứng sẵn có.

---

## 9. Acceptance Criteria assessment (chuẩn hóa PASS/PENDING/FAIL)

| #   | Tiêu chí                                                              | Kết quả     | Giải trình ngắn gọn                                                                                                                                                                                                                                                                                                                  |
| --- | --------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Before/during/after replica & HPA evidence, quay về baseline đã duyệt | **PENDING** | Replica: 9/9 service (bao gồm `quote`, nay đã RESOLVED) khớp baseline đã duyệt qua `CDO08-REL-01` + `D3-COST-01`. HPA: `frontend`/`checkout` đã giải trình; `currency` (min=2/max=3) vẫn **PENDING EXPLANATION** — chưa có PR/config decision hoặc owner confirmation. Gộp chung → PENDING vì 1 sub-item (HPA `currency`) chưa đóng. |
| 2   | Node count before/during/after                                        | **PASS**    | ASG managed node group không đổi (`desiredSize=2`) xuyên suốt; xem mục 8 (timeline) cho biến động Karpenter.                                                                                                                                                                                                                         |
| 3   | Load-generator dừng/idle sau maintenance                              | **PENDING** | `AUTOSTART=true` ở cả 2 lần đo; không có evidence Deployment `replicas=0` hoặc traffic/users=0 ngoài test window; thiếu quyền `pods/exec`/Grafana để xác nhận dứt điểm.                                                                                                                                                              |
| 4   | CPU/memory post-test về mức bình thường                               | **PASS**    | 13–24% CPU, 47–56% memory ở cả 3 node (lần 2); lưu ý namespace quota CPU 93.1% (từng chạm 96.25%) — cần theo dõi, không chặn PASS.                                                                                                                                                                                                   |
| 5   | Estimated cost                                                        | **PASS**    | Ước tính bằng full worker cost (`$0.0773918/giờ` cho `t3a.large`, gồm compute + EBS): ~`$0.435` tại thời điểm đo, ~`$1.86`/24h, ~`$13.00`/tuần nếu không xử lý. Đã ghi rõ không phải actual billing (mục 6).                                                                                                                         |
| 6   | Xác nhận có/không temporary resource ngoài kế hoạch                   | **PENDING** | 1 node Karpenter dynamic capacity quan sát được, khớp capacity model đã duyệt trong `D3-COST-01` (không phải resource lạ/rò rỉ) — nhưng **final resting baseline (3 workers) chưa được formally approved**; controlled-drain rehearsal + actual-cost reconciliation vẫn PENDING theo chính `D3-COST-01`.                             |
| 7   | Cleanup checklist có chữ ký operator                                  | **PASS**    | Checklist mục 7, ký Tuấn, cho phần đã tự verify read-only.                                                                                                                                                                                                                                                                           |

**Tổng: 4/7 PASS, 3/7 PENDING, 0/7 FAIL.**

Không có tiêu chí nào FAIL — 3 điểm PENDING đều là "cần xác nhận/approval thêm từ người khác", không phải lỗi do Tuấn tự gây ra hay bị chặn bởi bằng chứng phủ định.

**Kết luận tổng (cập nhật 2026-07-16 theo phản hồi PM, sau khi đối chiếu `D3-COST-01` bản post-`quote`-remediation):** `D3-COST-02` đạt **4/7 PASS, 3/7 PENDING**. `quote` **không còn nằm trong danh sách điểm hở** — CDO-08 đã xác nhận scope và remediation đã apply/verify (mục 1). **Còn lại đúng 3 điểm PENDING:**

1. HPA `currency` (min=2/max=3) không nằm trong danh sách CDO-08 đã xác nhận — **PENDING EXPLANATION**, giữ nguyên cho đến khi có PR/config decision hoặc owner confirmation.
2. Load-generator chưa xác nhận idle/stopped — cần evidence Deployment `replicas=0` hoặc traffic/users=0 ngoài test window (`AUTOSTART=true` hiện tại là rủi ro cụ thể, chưa phải bằng chứng đã dừng).
3. Final resting baseline của worker count (3 workers: 2 managed + 1 Karpenter) chưa được formally approved — node Karpenter khớp capacity model `D3-COST-01` (không phải node thừa/non-value-add), nhưng cần Vinh/CDO-04 chốt baseline nghỉ chính thức.

Không có phần nào trong số này được Tuấn tự sửa/scale — cần CDO-04/Vinh xác nhận nốt 3 điểm trên.

---

## 10. Việc cần làm tiếp / đang chờ ai

| Việc                                                 | Cần làm gì                                                                                                                                                     | Chờ ai                                |
| ---------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------- |
| Xác nhận nguồn gốc HPA `currency` (min=2/max=3)      | Không có trong `CDO08-REL-01`/`D3-COST-01` — xác nhận ai tạo và có nên giữ. Giữ **PENDING EXPLANATION** đến khi có PR/config decision hoặc owner confirmation. | CDO-04 / Vinh                         |
| Chốt final resting baseline của worker count         | D3-COST-01 chưa định nghĩa rõ baseline nghỉ sau rehearsal (3 workers observed vs. 4 workers target) — cần formal approval, không mặc định coi là "thừa"        | CDO-04 / Vinh (cập nhật `D3-COST-01`) |
| Xác nhận load-generator idle/stopped                 | Cần evidence Deployment `replicas=0` hoặc traffic/users=0 ngoài test window — cần quyền `pods/exec` hoặc Grafana access                                        | Ninh/Reliability                      |
| Đối chiếu lại estimated cost bằng CE actual billing  | Chạy lại `aws ce get-cost-and-usage` sau 24-48h khi CE xử lý xong dữ liệu ngày 15/07 (bucket `t3a.large` hiện còn thiếu)                                       | Tuấn (retry)                          |
| Rủi ro quota CPU namespace (93.1%, từng chạm 96.25%) | Đánh giá tăng `techx-quota` hay giảm HPA/replica dư thừa — namespace quota chưa được D3-COST-01 tính vào cost model                                            | CDO-04 / Vinh                         |

Tài liệu này sẽ được cập nhật (không tạo file mới) khi có thêm evidence — mỗi lần cập nhật ghi rõ ngày UTC và phần nào vừa được bổ sung.

---

## 11. Danh sách raw evidence (`raw/`)

Lần 1 (`2026-07-15T10:49Z`): `00` metadata · `01`/`01b` pods (wide, sorted by creation) · `02` nodes wide · `03` hpa wide · `04` deploy replica summary · `05` nodegroup describe · `06` ASG describe · `07`/`07b` EC2 instance/tag detail node Karpenter · `08` load-generator env · `09`/`09b` load-generator pod describe/logs · `10` k8s events · `11` node Karpenter describe · `12`/`13` top nodes/pods · `14` permission checks (`can-i`) · `15` karpenter controller pods · `16` observability pods (Jaeger) · `17` cost pricing access attempt (bị từ chối do role).

Lần 2 (`2026-07-15T16:29Z`): `18` metadata · `19` deploy replica · `20` hpa · `21` nodes wide · `22` nodegroup describe · `23` node `ip-10-0-10-231` describe · `24` node Karpenter describe · `26` EC2 toàn bộ instance cluster · `27` EC2 detail node Karpenter · `28` ASG describe · `32` load-generator env · `33` load-generator pods · `34` load-generator logs · `35` top nodes · `36` top pods · `37` resourcequota · `38` jaeger pods.

Lần 3 (`2026-07-15T16:35Z`, role `TF4-CostPerfReadOnlyAlerting`): `39` pricing `t3a.large` · `40` pricing `t3.large` · `41` Cost Explorer `get-cost-and-usage` daily 14→16/07 (actual, đánh dấu `Estimated: true`, thiếu bucket `t3a.large` ngày 15/07).
