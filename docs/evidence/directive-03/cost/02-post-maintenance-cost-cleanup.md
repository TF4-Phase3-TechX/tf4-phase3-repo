# D3-COST-02 — Post-Maintenance Scale-Down and Cost Verification

**Directive:** #3 — Maintenance Capacity & Cost-Efficient Resilience
**Owner:** Tuấn — CDO-04 Performance Efficiency & Cost Optimization
**Cluster:** `techx-tf4-cluster` (`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`)
**Namespace:** `techx-tf4`
**Region:** `us-east-1`
**Thư mục evidence:** `./raw/`
**Trạng thái:** **PARTIAL — 5/7 tiêu chí đạt (2 có giải trình từ CDO-08/D3-COST-01), 2/7 chưa đạt/không xác nhận được** (chi tiết mục 8, cập nhật sau khi đối chiếu `D3-COST-01`/`CDO08-REL-01`). Không đánh giá/đối chiếu với D3-PERF-04 — nằm ngoài phạm vi task này.

---

## 0. Phạm vi & phương pháp

Task `D3-COST-02` độc lập, không phụ thuộc `D3-COST-01`/`D3-PERF-04` (xác nhận trực tiếp với PM). Baseline "before" duy nhất hiện có trong repo là `D3-PERF-01` (`docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-PERF-01-revenue-path-capacity-inventory/`, thu thập 2026-07-14): toàn bộ 9 service revenue-path chạy `1/1/1`, không HPA ngoại trừ `frontend`/`checkout` (min=1/max=3).

Verify qua **2 lần đo**, cách nhau ~5h40', đều read-only (`get`/`describe`/`top`/`logs`/`auth can-i`; không `scale`/`create`/`delete`/`apply`/`patch`/`exec`), cộng 1 lần đo bổ sung cho phần cost sau khi đổi role:

| Lần đo | Thời điểm (UTC) | Role AWS |
|---|---|---|
| Lần 1 | `2026-07-15T10:49:05Z` | `TF4-BaseReadOnly` |
| Lần 2 | `2026-07-15T16:29Z` | `TF4-BaseReadOnly` |
| Lần 3 (cost) | `2026-07-15T16:35Z` | `TF4-CostPerfReadOnlyAlerting` |

---

## 1. Temporary replicas / HPA quay về baseline

| Service | Baseline `D3-PERF-01` (14/07) | Lần 1 (10:49Z) | Lần 2 (16:29Z) |
|---|---:|---:|---:|
| `cart` | 1/1/1 | 2/2/2 | 2/2/2 |
| `checkout` | 1/1/1, HPA 1–3 | 2/2/2, HPA min=2/max=3 | 2/2/2, HPA min=2/max=3 (44h tuổi) |
| `currency` | 1/1/1 | 2/2/2, HPA min=2/max=3 (144m tuổi) | 2/2/2, HPA min=2/max=3 (8h tuổi) |
| `frontend` | 1/1/1, HPA 1–3 | 3/3/3, HPA min=2/max=3, kịch trần | 2/2/2, HPA min=2/max=3 (44h tuổi) |
| `frontend-proxy` | 1/1/1 | 2/2/2 | 2/2/2 |
| `payment` | 1/1/1 | 2/2/2 | 2/2/2 |
| `product-catalog` | 1/1/1 | 2/2/2 | 2/2/2 |
| `quote` | 1/1/1 | 1/1/1 | **2/2/2** |
| `shipping` | 1/1/1 | 2/2/2 | 2/2/2 |

**Cập nhật — đã tìm thấy giải trình chính thức, quét lại codebase 2026-07-15/16:**

- **7/9 service (`cart`, `checkout`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `shipping`) tăng lên 2 replica là thay đổi baseline có chủ đích, đã duyệt** — theo `docs/cdo08/week2/cdo08-rel-01-replica-availability-proposal.md` (`CDO08-REL-01`, owner Hoàng Nam, P0, mục tiêu loại SPOF single-replica trên customer/checkout path). Đề xuất chốt **2 replica làm fixed baseline**, không phải scale tạm cho một lần test. Vậy **mức 2/2/2 quan sát được ở cả 2 lần đo không phải "temporary replicas cần rollback" — đây là baseline mới đã duyệt**, tiêu chí "temporary replicas về baseline" áp dụng đúng hơn cho baseline mới này, không phải baseline `D3-PERF-01` (1/1/1) vốn đã lỗi thời sau `REL-01`.
- **HPA `frontend`/`checkout` (min=2/max=3) được xác nhận trong `docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md`** (mục 4.3, 5 — "Reliability input từ CDO-08", dependency đánh dấu **RESOLVED**), cùng nguồn xác nhận PDB `minAvailable=1` cho 8 service. Tài liệu D3-COST-01 có **runtime validation lúc `2026-07-15T11:23:53Z`** (`raw/17-final-validation-metadata.txt` của D3-COST-01) — nằm trong đúng buổi sáng 15/07, khớp thời điểm 2 lần đo của D3-COST-02.
- **`currency` HPA (min=2/max=3) KHÔNG có trong danh sách D3-COST-01/CDO08-REL-01** — chỉ liệt kê `frontend`/`checkout`. Vẫn **chưa giải trình được**, cần hỏi CDO-08/Vinh riêng cho `currency`.
- **`quote`**: D3-COST-01 mục 10 ghi rõ **"Quyết định còn chờ: `quote`"** — tại thời điểm validation `11:23:53Z`, `quote` vẫn `1/1`, scope quyết định (thuộc mandatory drain scope hay loại trừ) **còn PENDING CDO-08 REVIEW**, và "Controlled drain chưa được thực hiện cho đến khi quyết định này được chốt." Vậy việc `quote` tăng lên `2/2/2` ở lần đo 2 (16:29Z) của D3-COST-02 — **sau** thời điểm D3-COST-01 còn ghi PENDING — là một thay đổi **chưa có evidence quyết định chính thức đi kèm**. Đây là điểm duy nhất trong mục này vẫn cần escalate.

**Kết quả: ĐẠT có giải trình cho 7/9 service (theo `CDO08-REL-01` + `D3-COST-01`). Còn 2 điểm hở:** HPA `currency` chưa rõ nguồn, và việc `quote` tăng replica sau khi D3-COST-01 còn ghi "PENDING" chưa có quyết định đi kèm.

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

**Kết quả: KHÔNG xác nhận được.** Không có bằng chứng load-generator đã dừng — ngược lại, cấu hình `AUTOSTART=true` là rủi ro cụ thể. Cần người có quyền `pods/exec` hoặc Grafana UI (dashboard `LoadGeneratorTrafficOutsideTestWindow`, `docs/audit/runbooks/flash-sale-alerts.md`) xác nhận dứt điểm.

---

## 4. Không còn temporary resources / không phát sinh workload chạy nền ngoài kế hoạch

- **Node Karpenter ngoài ASG** phát hiện ở **cả 2 lần đo** — 2 instance khác nhau nhưng cùng một kiểu tồn tại kéo dài không giải trình:
  - Lần 1: `ip-10-0-10-74` / `i-029d41ebaa83f4358`, `t3a.large`, launch `2026-07-15T03:46:26Z`, đã chạy ~7h tại thời điểm đo. (`raw/07-ec2-instance-10-0-10-74.json`, `raw/11-node-ip-10-0-10-74-describe.txt`)
  - Lần 2: `ip-10-0-10-17` / `i-05a5387fbf39a3e02`, `t3a.large`, launch `2026-07-15T10:52:32Z`. (`raw/24-node-ip-10-0-10-17-describe-round2.txt`, `raw/27-ec2-karpenter-node-ip-10-0-10-17-round2.json`)
  - `aws ec2 describe-instances` lọc theo tag cluster (mọi trạng thái) chỉ trả về 2 instance ASG gốc — node Karpenter không mang tag `eks:cluster-name` giống ASG, xác nhận đây là compute ngoài luồng quản lý chuẩn. (`raw/26-ec2-all-cluster-instances-round2.json`)
  - Pod `load-generator` (mục 3) chạy trên chính node Karpenter này ở lần 2.
- Không phát hiện Deployment/Pod thủ công nào khác ngoài Helm-managed workload trong `techx-tf4` — danh sách pod khớp với các service đã biết trong `ARCHITECTURE.md`.

**Cập nhật — có giải trình một phần từ `D3-COST-01`:** tài liệu `docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md` (mục 3.2, 4.1, 7) xác nhận Karpenter capacity build-up là **có chủ đích**, không phải rò rỉ ngẫu nhiên:

- NodePool Karpenter cho phép `t3.large`/`t3a.large`, `limits.cpu=16`, `consolidationPolicy=WhenEmptyOrUnderutilized`, `consolidateAfter=5m` — nghĩa là Karpenter **tự động co node khi không còn cần**, không cần ai xoá thủ công.
- D3-COST-01 mục 7 (Scenario B) chốt **"4 total workers" (2 managed + 2 Karpenter) là minimum maintenance target** cho controlled-drain rehearsal — tức việc có thêm node Karpenter ngoài 2 node ASG **là kế hoạch đã duyệt**, không phải lỗi.
- Runtime validation của D3-COST-01 lúc `11:23:53Z` ghi nhận **4 node Ready** (2 managed + 2 Karpenter). Lần đo 2 của D3-COST-02 (16:29Z, ~5h sau) chỉ còn **3 node** (2 managed + 1 Karpenter) — tức Karpenter **đã tự co bớt 1 node** đúng theo consolidation policy, một phần scale-down đã xảy ra tự nhiên.

**Điểm còn hở:** D3-COST-01 tự nhận trạng thái cuối là **"READY FOR REVIEW — NOT YET CLOSED"** (mục 11), còn treo mục "actual-cost reconciliation" và quyết định `quote`. Tài liệu đó cũng không định nghĩa rõ **baseline nghỉ cuối cùng sau rehearsal là bao nhiêu node** (chỉ nói 4 node là target *trong lúc* rehearsal) — nên chưa thể khẳng định chắc chắn node Karpenter còn lại ở lần đo 2 (`ip-10-0-10-17`) là "steady-state hợp lệ do REL-01 cần thêm capacity cho 2-replica baseline" hay "phần chưa co hết". `load-generator` (mục 3) đang chạy ngay trên node này cũng cần lưu ý riêng.

**Kết quả: ĐẠT có giải trình một phần.** Việc có node Karpenter ngoài ASG khớp với kế hoạch đã duyệt trong `D3-COST-01` (không phải resource lạ/rò rỉ), và đã quan sát được Karpenter tự consolidate 4→3 node đúng theo policy. Còn thiếu: xác nhận rõ ràng node Karpenter còn lại ở lần đo 2 là baseline nghỉ hợp lệ hay cần co tiếp — cần Vinh/CDO-08 chốt trong lần cập nhật D3-COST-01 tiếp theo.

---

## 5. Resource usage trở về mức bình thường

**CPU/Memory (lần 2, `2026-07-15T16:29Z`):**

| Node | CPU | Memory |
|---|---:|---:|
| `ip-10-0-10-17` (Karpenter) | 251m (13%) | 3821Mi (53%) |
| `ip-10-0-10-231` | 286m (14%) | 3338Mi (47%) |
| `ip-10-0-11-40` | 475m (24%) | 3982Mi (56%) |

Không node nào pressure. (`raw/35-top-nodes-round2.txt`, `raw/36-top-pods-round2.txt`)

**Namespace quota (`techx-quota`), lần 2:** `limits.cpu = 7450m/8000m` (**93.1%** đã dùng), `limits.memory = 5893Mi/12288Mi` (48%), `pods = 31/40`. (`raw/37-resourcequota-round2.yaml`) Ở lần 1 quota CPU từng chạm **96.25%** kèm nhiều lần `FailedCreate` khi HPA `frontend` cố scale (`raw/10-events-techx-tf4.txt`). Lần 2 không còn `FailedCreate` tại thời điểm đo, nhưng quota CPU vẫn sát trần — nếu replica/HPA elevated ở mục 1 không phải baseline chính thức đã duyệt, đây là rủi ro tái diễn `FailedCreate` bất cứ lúc nào có scale-up tiếp theo.

**Jaeger (`techx-observability`, thuộc gap `COST-02` — observability stack — CDO-04 đang theo dõi):** lần 1 phát hiện pod `jaeger-5f589cc9f6-qp4ft` có 34 lần restart, gần nhất ~105s trước thời điểm đo (`raw/16-observability-pods.txt`). Lần 2, pod hiện tại (`jaeger-5f589cc9f6-2nftq`) có 0 restart, chạy ổn định 6h11m — anomaly đã tự phục hồi. (`raw/38-jaeger-pods-round2.txt`)

**Kết quả: ĐẠT (có điều kiện).** CPU/memory node hiện bình thường và Jaeger đã ổn định, nhưng quota namespace vẫn sát trần (93.1%) — cần theo dõi tiếp nếu replica/HPA ở mục 1 không được giảm về baseline.

---

## 6. Ước tính chi phí (lần 3, `2026-07-15T16:35Z`, role `TF4-CostPerfReadOnlyAlerting`)

`raw/39-pricing-t3a-large-round2.json`, `raw/40-pricing-t3-large-round2.json`: giá On-Demand Linux, `us-east-1`, hiệu lực `2026-07-01`:

| Instance type | Giá On-Demand (USD/giờ) |
|---|---:|
| `t3a.large` (node Karpenter thừa) | `$0.0752` |
| `t3.large` (2 node ASG baseline) | `$0.0832` |

**Ước tính chi phí node Karpenter ngoài ASG chưa giải trình (mục 4):**
- Node hiện tại `ip-10-0-10-17`, launch `2026-07-15T10:52:32Z`, vẫn đang chạy tại thời điểm viết (`16:29:45Z`) → đã chạy **~5h37m** → **~$0.42** tích lũy tính đến lúc đo, và **vẫn đang tiếp tục phát sinh** vì chưa ai thu hồi.
- Nếu để chạy nguyên ngày không xử lý: `24h × $0.0752 ≈ $1.80/ngày`, tương đương **~$12.63/tuần** — nhỏ so với ngân sách `~$300/tuần/TF`, nhưng là chi phí non-value-add vì không có evidence chính thức nào giải trình mục đích của node này, và đây là node **thứ hai liên tiếp** xuất hiện dạng này (mục 4) — khả năng là một node Karpenter "rớt lại" tái diễn liên tục thay vì một lần tạm thời.

**Đối chiếu Cost Explorer actual billing:** `raw/41-ce-cost-and-usage-round2.json` — `aws ce get-cost-and-usage` (`DAILY`, `2026-07-14` → `2026-07-16`, group theo `USAGE_TYPE`) chạy thành công, nhưng cả 2 ngày đều đánh dấu `"Estimated": true`, và bucket `BoxUsage:t3a.large` của **ngày 2026-07-15 hoàn toàn không xuất hiện** trong kết quả dù `kubectl`/`aws ec2` đã xác nhận node đó chạy suốt từ `10:52:32Z` — CE actual data có độ trễ xử lý, không phản ánh kịp usage trong ngày. Vì vậy con số **$0.42 / ~$12.63 tuần ở trên là ước tính dựa trên pricing model × giờ chạy quan sát được qua `kubectl`/`aws ec2 describe-instances`, không phải actual billing đã đối chiếu** — cần chạy lại `aws ce get-cost-and-usage` sau khi CE hoàn tất xử lý (thường 24-48h) để đối chiếu con số thật.

**Kết quả: ĐẠT** (có ước tính, đã ghi rõ là estimate không phải actual billing).

---

## 7. Cleanup checklist có chữ ký operator

| Hạng mục | Baseline (`D3-PERF-01`) | Lần 1 (10:49Z) | Lần 2 (16:29Z) | Kết quả | Verify | Thời gian (UTC) |
|---|---|---|---|---|---|---|
| Temporary replicas về baseline | 1/1/1 | 8/9 > baseline | 8/9 > baseline (không đổi so với lần 1) | ✅ Đạt có giải trình (`CDO08-REL-01`, 7/9 service) — `quote` còn hở | Tuấn | 2026-07-15T16:29Z |
| HPA về min replica | min=1 | min=2 (`frontend`/`checkout`), mới ở `currency` | Không đổi so với lần 1 | ✅ Đạt có giải trình (`D3-COST-01`) cho `frontend`/`checkout` — `currency` chưa rõ nguồn | Tuấn | 2026-07-15T16:29Z |
| Node group về baseline | desired=2 | desired=2 | desired=2, 2 instance InService | ✅ Đạt | Tuấn | 2026-07-15T16:29Z |
| Load-generator dừng | N/A | `AUTOSTART=true`, không xác nhận active user | Không đổi | ⚠️ Không xác nhận được | Tuấn | 2026-07-15T16:29Z |
| Không còn temporary resources | 2 node | 3 node (1 Karpenter thừa) | 3 node (1 Karpenter thừa, instance khác) | ✅ Đạt có giải trình một phần (`D3-COST-01` Scenario B + Karpenter consolidation 4→3 quan sát được) | Tuấn | 2026-07-15T16:29Z |
| Resource usage bình thường | 93%/80% CPU (2 node) | <90%/<85% (3 node) | 13-24% CPU, 47-56% mem (3 node); quota 93.1% | ✅ Đạt (có điều kiện — quota sát trần) | Tuấn | 2026-07-15T16:29Z |
| Không phát sinh workload nền ngoài kế hoạch | N/A | `AUTOSTART=true` + node Karpenter thừa | Không đổi | ⚠️ Load-generator vẫn chưa xác nhận idle; node Karpenter đã có giải trình một phần | Tuấn | 2026-07-15T16:29Z |
| Estimated cost | N/A | Không lấy được (role thiếu quyền) | `t3a.large` $0.0752/h; node thừa ~$0.42 tích lũy, ~$12.63/tuần nếu không xử lý | ✅ Có ước tính (không phải actual billing) | Tuấn | 2026-07-15T16:35Z |

---

## 8. Acceptance Criteria assessment

- [x] Có before/during/after replica evidence (`D3-PERF-01` → lần 1 → lần 2).
- [x] Có node count before/during/after.
- [ ] Load-generator 0/0 hoặc idle — **không xác nhận được**, có gap cấu hình `AUTOSTART=true`.
- [x] CPU/memory post-test — bình thường, kèm cảnh báo quota sát trần (93.1%).
- [x] Estimated cost — có ước tính (mục 6), dựa trên pricing model, đã ghi rõ không phải actual billing.
- [x] Xác nhận có/không temporary resource — **CÓ**, 1 node Karpenter ngoài ASG qua 2 lần đo; đã tìm giải trình một phần từ `D3-COST-01` (mục 4), còn hở việc xác nhận baseline nghỉ cuối cùng.
- [x] Cleanup checklist có chữ ký operator (Tuấn) cho phần đã tự verify.

**Kết luận tổng (cập nhật sau khi quét lại codebase cho giải trình Karpenter/HPA):** `D3-COST-02` đạt **5/7** tiêu chí, trong đó 2 tiêu chí (replica, temporary resources) chuyển từ "không đạt" sang "đạt có giải trình" nhờ tìm thấy `docs/cdo08/week2/cdo08-rel-01-replica-availability-proposal.md` (CDO08-REL-01) và `docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md` (D3-COST-01) — cả hai đều là tài liệu chính thức trong CDO-04/CDO-08, không phải suy đoán. **Còn lại 3 điểm hở cụ thể, chưa phải "không đạt" toàn diện mà là "cần xác nhận thêm":**
1. HPA `currency` (min=2/max=3) không nằm trong danh sách CDO-08 đã xác nhận — nguồn gốc chưa rõ.
2. `quote` tăng lên `2/2/2` sau khi D3-COST-01 còn ghi quyết định scope là PENDING — thay đổi chưa có quyết định chính thức đi kèm.
3. Load-generator vẫn chưa xác nhận idle (`AUTOSTART=true`), và node Karpenter còn lại ở lần đo 2 chưa rõ là baseline nghỉ hợp lệ hay phần chưa co hết.

Không có phần nào trong số này được Tuấn tự sửa/scale — cần CDO-08/Vinh xác nhận nốt 3 điểm trên trong lần cập nhật D3-COST-01 tiếp theo.

---

## 9. Việc cần làm tiếp / đang chờ ai

| Việc | Cần làm gì | Chờ ai |
|---|---|---|
| Xác nhận nguồn gốc HPA `currency` (min=2/max=3) | Không có trong `CDO08-REL-01`/`D3-COST-01` — xác nhận ai tạo và có nên giữ | CDO-08 / Vinh |
| Chốt quyết định scope `quote` | D3-COST-01 còn ghi PENDING nhưng `quote` đã tăng lên `2/2/2` — cần quyết định chính thức đi kèm | CDO-08 (theo mục 10 của `D3-COST-01`) |
| Xác nhận node Karpenter còn lại (lần đo 2) là baseline nghỉ hợp lệ hay cần co tiếp | D3-COST-01 chưa định nghĩa rõ baseline nghỉ sau rehearsal | CDO-08 / Vinh (cập nhật `D3-COST-01`) |
| Xác nhận load-generator có đang phát traffic thật không | Cần quyền `pods/exec` hoặc Grafana access | Ninh/Reliability |
| Đối chiếu lại estimated cost bằng CE actual billing | Chạy lại `aws ce get-cost-and-usage` sau 24-48h khi CE xử lý xong dữ liệu ngày 15/07 (bucket `t3a.large` hiện còn thiếu) | Tuấn (retry) |
| Rủi ro quota CPU namespace (93.1%, từng chạm 96.25%) | Đánh giá tăng `techx-quota` hay giảm HPA/replica dư thừa — namespace quota chưa được D3-COST-01 tính vào cost model | CDO-08 / Vinh |

Tài liệu này sẽ được cập nhật (không tạo file mới) khi có thêm evidence — mỗi lần cập nhật ghi rõ ngày UTC và phần nào vừa được bổ sung.

---

## 10. Danh sách raw evidence (`raw/`)

Lần 1 (`2026-07-15T10:49Z`): `00` metadata · `01`/`01b` pods (wide, sorted by creation) · `02` nodes wide · `03` hpa wide · `04` deploy replica summary · `05` nodegroup describe · `06` ASG describe · `07`/`07b` EC2 instance/tag detail node Karpenter · `08` load-generator env · `09`/`09b` load-generator pod describe/logs · `10` k8s events · `11` node Karpenter describe · `12`/`13` top nodes/pods · `14` permission checks (`can-i`) · `15` karpenter controller pods · `16` observability pods (Jaeger) · `17` cost pricing access attempt (bị từ chối do role).

Lần 2 (`2026-07-15T16:29Z`): `18` metadata · `19` deploy replica · `20` hpa · `21` nodes wide · `22` nodegroup describe · `23` node `ip-10-0-10-231` describe · `24` node Karpenter describe · `26` EC2 toàn bộ instance cluster · `27` EC2 detail node Karpenter · `28` ASG describe · `32` load-generator env · `33` load-generator pods · `34` load-generator logs · `35` top nodes · `36` top pods · `37` resourcequota · `38` jaeger pods.

Lần 3 (`2026-07-15T16:35Z`, role `TF4-CostPerfReadOnlyAlerting`): `39` pricing `t3a.large` · `40` pricing `t3.large` · `41` Cost Explorer `get-cost-and-usage` daily 14→16/07 (actual, đánh dấu `Estimated: true`, thiếu bucket `t3a.large` ngày 15/07).
