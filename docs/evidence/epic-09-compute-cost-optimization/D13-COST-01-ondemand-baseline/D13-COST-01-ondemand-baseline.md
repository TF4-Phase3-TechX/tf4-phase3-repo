# C0G-76 — D13-COST-01: Capture On-Demand Compute Baseline and Node-Hours

**Directive:** #13 — Compute Cost Optimization
**Owner:** Tuấn — CDO-04 Performance Efficiency & Cost Optimization
**Cluster:** `techx-tf4-cluster` (`arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`), namespace `techx-tf4`, region `us-east-1`
**Load profile:** Locust `load-generator`, 200 concurrent users
**Trạng thái tính đến `2026-07-22`:** Pass 1 collected. Baseline xác nhận capacity 100% On-Demand, 100% x86_64 (chưa có Spot/Graviton). Một run locust bị loại bỏ vì nhiễu bởi rollout `checkout` chạy song song; run dùng làm baseline là run sau, sạch.

```
D13-COST-01: PASS 1 COMPLETE
ON-DEMAND SHARE: 100% (0 Spot instance nào xuất hiện trong EC2 hoặc Cost Explorer, 8 ngày liên tục)
ARCHITECTURE: 100% x86_64 (chưa có ARM64/Graviton)
CHECKOUT SLO (run dùng làm baseline): 99.22% — ĐẠT (>=99.0%)
KNOWN CONCURRENT INCIDENT: recommendation service ImagePullBackOff (không liên quan node capacity) — xem §Ghi chú sự cố
NODE-HOUR TRONG ĐÚNG KHUNG GIỜ TEST: CHƯA CHỐT (thiếu Grafana node-count-over-time; xem §Việc còn lại)
```

---

## Mục tiêu

Thu baseline hiện tại (100% On-Demand, x86_64) trước khi bật Spot và Graviton, dùng cùng load curve (locust 200 users) để so sánh với optimized run ở D13-COST-02.

---

## Ghi chú quan trọng: một run locust đã bị loại bỏ

Trong lúc thu thập, phát hiện run locust 200-user đầu tiên bị nhiễu: `checkout` đang chạy blue-green rollout (revision 9→10→11) song song, gây pod-churn và 500 error (`/api/checkout` success rate 81.6%) không liên quan capacity On-Demand. Toàn bộ raw file của run đó đã bị xoá theo quyết định của Tuấn (không phù hợp làm baseline). Run dùng làm baseline chính thức trong tài liệu này là run locust 200-user **sau đó**, khi rollout `checkout` đã ổn định trên revision hiện hành.

---

## A. EC2 Instance Inventory (baseline On-Demand)

Nguồn: `raw/10-ec2-instances-table.txt`. Filter theo tag `kubernetes.io/cluster/techx-tf4-cluster=owned`, state `running`. (Bản `-o json` đầy đủ không đưa vào repo vì chứa `ClientToken` — idempotency token của EC2 Fleet/Karpenter, không phải credential nhưng bị secret-scanner CI flag entropy cao; bảng rút gọn này đã đủ toàn bộ field cần cho evidence.)

| Instance ID           | Type      | Arch   | Purchase Option                       | Launch Time (UTC)      | AZ         | Node                          | Termination                                                |
| --------------------- | --------- | ------ | ------------------------------------- | ---------------------- | ---------- | ----------------------------- | ---------------------------------------------------------- |
| `i-0825abf366929a005` | t3.large  | x86_64 | On-Demand (`InstanceLifecycle: None`) | `2026-07-09T01:54:31Z` | us-east-1b | `ip-10-0-11-40.ec2.internal`  | — (vẫn Running)                                            |
| `i-01b00d955a0af0fac` | t3.large  | x86_64 | On-Demand                             | `2026-07-09T01:54:31Z` | us-east-1a | `ip-10-0-10-231.ec2.internal` | —                                                          |
| `i-0b9df4a4ec1d03c16` | t3a.large | x86_64 | On-Demand                             | `2026-07-16T03:57:11Z` | us-east-1b | `ip-10-0-11-217.ec2.internal` | **Đang bị Karpenter drain, chưa xong** (xem ghi chú dưới)  |
| `i-01aae8ffa93cdb3ec` | t3a.large | x86_64 | On-Demand                             | `2026-07-22T10:41:34Z` | us-east-1b | `ip-10-0-11-37.ec2.internal`  | — (Karpenter scale-out mới, ~2.4h tuổi tại thời điểm chụp) |
| `i-0869b2c204e950346` | t3a.large | x86_64 | On-Demand                             | `2026-07-22T10:51:28Z` | us-east-1a | `ip-10-0-10-8.ec2.internal`   | — (Karpenter scale-out mới, ~2.3h tuổi tại thời điểm chụp) |

**Xác nhận acceptance criterion "Baseline chủ yếu/toàn On-Demand":** 5/5 instance `InstanceLifecycle: None` (= On-Demand), 5/5 `Architecture: x86_64`. **Không có Spot, không có ARM64/Graviton trong baseline.**

- `techx-general-djg4k` (node `ip-10-0-11-217`, instance `i-0b9df4a4ec1d03c16`) **đang giữa quá trình bị Karpenter chấm để terminate**, không phải node ổn định như bảng ở trên có thể gây hiểu lầm: `status.conditions` có `Consolidatable: True` (từ `2026-07-22T10:46:55Z`), `DisruptionReason: Underutilized`, và `deletionTimestamp: 2026-07-22T10:48:52Z` (`raw/04-nodeclaims-full.json`). Node mang taint `karpenter.sh/disrupted:NoSchedule`, và `raw/08-nodes-describe.txt` ghi nhận 3 sự kiện `FailedDraining` liên tiếp, nguyên nhân cụ thể: _"Failed to drain node, evicting pod violates a PDB (Pod=techx-tf4/shipping-759cd5f66c-hlfg7)"_.
- 2 NodeClaim mới (`techx-general-2k74s` trên `ip-10-0-11-37`, `techx-general-v6zw9` trên `ip-10-0-10-8`, cả hai launch `2026-07-22` ~`10:41Z`/`10:51Z`) là capacity thay thế Karpenter đã dựng lên **trước khi** `djg4k` drain xong — đúng cơ chế Karpenter consolidation/replace (dựng node mới trước, drain node cũ sau, không phải dọn xong mới dựng).

**Kết luận cho baseline:** tại thời điểm chụp, cluster có 5 node nhưng chỉ **4 là steady-state thực sự**; `djg4k` là tồn dư đang bị thay thế, bị PDB chặn drain — không nên tính node này như một phần capacity "ổn định" khi so sánh với D13-COST-02 sau này.

---

## B. Kubernetes Node / NodeClaim Inventory

Nguồn: `raw/01-nodes-wide.txt`, `raw/03-nodeclaims-wide.txt`, `raw/04-nodeclaims-full.json`.

| Node                          | NodeClaim                                    | Nodepool        | Type      | Capacity  | AGE (tại thời điểm chụp `2026-07-22T13:08Z`) |
| ----------------------------- | -------------------------------------------- | --------------- | --------- | --------- | -------------------------------------------- |
| `ip-10-0-10-231.ec2.internal` | _(không phải NodeClaim — managed nodegroup)_ | —               | t3.large  | on-demand | 13d                                          |
| `ip-10-0-11-40.ec2.internal`  | _(không phải NodeClaim — managed nodegroup)_ | —               | t3.large  | on-demand | 13d                                          |
| `ip-10-0-11-217.ec2.internal` | `techx-general-djg4k`                        | `techx-general` | t3a.large | on-demand | 6d9h                                         |
| `ip-10-0-11-37.ec2.internal`  | `techx-general-2k74s`                        | `techx-general` | t3a.large | on-demand | 146m                                         |
| `ip-10-0-10-8.ec2.internal`   | `techx-general-v6zw9`                        | `techx-general` | t3a.large | on-demand | 136m                                         |

5 node `Ready`, 0 `Pending`/`NotReady` tại thời điểm chụp.

---

## C. Node-Hours

**Cumulative node-hours tính đến thời điểm thu thập (`2026-07-22T13:08:01Z`), theo LaunchTime từng instance:**

| Instance                          | Launch            | Giờ chạy đến thời điểm chụp |
| --------------------------------- | ----------------- | --------------------------- |
| `i-0825abf366929a005` (t3.large)  | `07-09T01:54:31Z` | ≈323.2h                     |
| `i-01b00d955a0af0fac` (t3.large)  | `07-09T01:54:31Z` | ≈323.2h                     |
| `i-0b9df4a4ec1d03c16` (t3a.large) | `07-16T03:57:11Z` | ≈153.2h                     |
| `i-01aae8ffa93cdb3ec` (t3a.large) | `07-22T10:41:34Z` | ≈2.4h                       |
| `i-0869b2c204e950346` (t3a.large) | `07-22T10:51:28Z` | ≈2.3h                       |
| **Tổng**                          |                   | **≈804.3 node-hours**       |

**Giới hạn của số liệu này — đọc kỹ trước khi dùng làm baseline so sánh D13-COST-02:** đây là tổng giờ chạy cộng dồn của các instance **đang sống tại thời điểm chụp**, tính từ lúc launch thật của từng instance — **không phải** node-hours phát sinh riêng trong đúng khung giờ chạy locust 200-user. 2 instance đã chạy từ `07-09` (13 ngày), việc gộp chung với 2 instance mới ~2.3h làm số tổng không phản ánh đúng "node-hours cho load curve này". Số node-hours-trong-đúng-khung-test-window **chưa chốt được** vì thiếu mốc thời gian bắt đầu/kết thúc chính xác của run locust dùng làm baseline (xem §Việc còn lại, mục 1).

---

## D. HPA

Nguồn: `raw/05-hpa-wide.txt`, chụp trong lúc locust 200-user baseline đang chạy.

| Namespace | HPA      | Reference           | CPU (current/target) | Min/Max | Replicas        |
| --------- | -------- | ------------------- | -------------------- | ------- | --------------- |
| techx-tf4 | checkout | Rollout/checkout    | 25% / 70%            | 2/3     | 2               |
| techx-tf4 | currency | Deployment/currency | 7% / 70%             | 2/3     | 2               |
| techx-tf4 | frontend | Deployment/frontend | **172% / 70%**       | 2/3     | **3/3 (maxed)** |

`frontend` đang chạm max replica (3/3) với CPU vượt xa target (172%/70%) dưới tải 200 users — đáng chú ý cho D13-COST-02 so sánh sau (nếu optimized run vẫn maxed tương tự thì không phải do thiếu Spot/Graviton mà do `maxReplicas: 3` quá thấp cho tải này).

---

## E. Workload / SLO Evidence (Locust 200-user run dùng làm baseline)

Nguồn: `locust/locust-stats-requests.json`, `locust/locust-stats-requests.csv`, `locust/locust-report.html`. Run đã kết thúc (`state: stopped`) tại thời điểm chụp cuối.

| Chỉ số                                                                                       | Giá trị                       |
| -------------------------------------------------------------------------------------------- | ----------------------------- |
| User count (peak)                                                                            | 200                           |
| Tổng requests (toàn run)                                                                     | 86,948                        |
| Tổng failures (toàn run)                                                                     | 4,434                         |
| **`/api/checkout` requests**                                                                 | **7,608**                     |
| **`/api/checkout` failures**                                                                 | **59**                        |
| **Checkout success rate**                                                                    | **99.22% — ĐẠT SLO (≥99.0%)** |
| Aggregate success rate (bao gồm cả outage `recommendation`)                                  | 94.90%                        |
| Aggregate success rate (loại trừ `/api/recommendations`, do outage không liên quan capacity) | ≈99.55%                       |

**Successful checkouts dùng làm workload denominator cho D13-COST-02: 7,549 (7,608 − 59).**

---

## F. Cost Explorer Usage Quantity Baseline

Nguồn: `raw/13-ce-usage-quantity-daily.json`. Metric `UsageQuantity`, service `Amazon Elastic Compute Cloud - Compute`, group by Purchase Option + Instance Type, granularity Daily (`2026-07-15`→`2026-07-22`).

- **`HOURLY` granularity bị chặn**: `AccessDeniedException` — "Hourly data granularity is an opt-in only feature", cần bật ở Payer account Cost Explorer Settings. Đã fallback sang `DAILY`.
- **100% dòng dữ liệu 8 ngày liên tục đều là `On Demand Instances`** — không có dòng Spot nào xuất hiện, khớp với EC2 inventory ở mục A.
- Instance type xuất hiện trong CE: `t3.large` (~48h/ngày = 2 instance × 24h, khớp 2 managed-nodegroup), `t3a.large` (dao động theo Karpenter scale-out/in), và **`t3.nano`** (~24h/ngày) — `t3.nano` **không xuất hiện trong `kubectl get nodes`**, tức là một EC2 instance ngoài phạm vi cluster (có thể bastion/NAT/tooling instance), giữ nguyên làm ghi chú, không tính vào node-hours của cluster.
- Tất cả record đều `"Estimated": true"` (dữ liệu CE gần-thời-gian-thực, chưa final billing) — cùng tình trạng đã ghi nhận ở `D8-COST-02`.
- Ngày `2026-07-22` (hôm nay) chưa có dữ liệu group nào >0 tại thời điểm truy vấn — ngày chưa kết thúc, CE chưa cập nhật.

---

## Ghi chú sự cố đồng thời (không thuộc phạm vi D13-COST-01, chỉ ghi nhận)

Trong lúc thu thập, phát hiện `recommendation` Deployment chỉ có **1 pod**, kẹt ở `ImagePullBackOff` liên tục (~145 phút tại thời điểm phát hiện): ECR trả `MANIFEST_UNKNOWN` / policy admission `require-signed-techx-images` (Kyverno) từng trả `401 Unauthorized` khi verify signature. Kết quả: **100% request `/api/recommendations` fail** trong run locust baseline (4,065/4,065). Đây là outage tầng image/registry, không liên quan node capacity hay Spot/Graviton — không ảnh hưởng kết luận On-Demand baseline ở tài liệu này, nhưng cần được flag riêng cho Platform/CI-CD (ngoài scope CDO-04) vì đang treo browse-path thật.

---

## Acceptance Criteria

- [x] Baseline xác nhận capacity chủ yếu/toàn On-Demand. — **Đạt**, 5/5 EC2 instance + 8/8 ngày Cost Explorer đều On-Demand, 0 Spot.
- [x] Có node inventory và launch time. — **Đạt**, §A/§B.
- [x] Có total worker node-hours. — **Đạt** Có cumulative node-hours-to-date (§C, ≈804.3h).
- [x] Có workload denominator. — **Đạt**, §E (7,608 checkout requests, 7,549 successful).
- [x] Có Cost Explorer Usage Quantity baseline. — **Đạt** (Daily; Hourly bị chặn ở tài khoản, đã ghi rõ).
- [x] Không dùng cột USD làm metric chính. — Tuân thủ, toàn bộ tài liệu dùng UsageQuantity/node-hours/node count, không dẫn USD.
- [x] Evidence cùng load curve với optimized run. — Locust 200-user, cùng profile sẽ dùng lại cho D13-COST-02; run nhiễu đã bị loại, không lẫn vào baseline.

---

## Evidence files

### `raw/`

| File                                                        | Nội dung                                                                                    |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `00-collection-metadata.txt`                                | Timestamp, kubectl context, ghi chú sự cố đồng thời                                         |
| `01-nodes-wide.txt`                                         | `kubectl get nodes -o wide`                                                                 |
| `03-nodeclaims-wide.txt` / `04-nodeclaims-full.json`        | `kubectl get nodeclaims -o wide` / `-o json`                                                |
| `05-hpa-wide.txt`                                           | `kubectl get hpa -A -o wide`, chụp trong lúc locust 200-user chạy                           |
| `06-pods-wide.txt`                                          | `kubectl get pods -n techx-tf4 -o wide`                                                     |
| `07-top-nodes.txt`                                          | `kubectl top nodes`                                                                         |
| `08-nodes-describe.txt`                                     | `kubectl describe nodes`                                                                    |
| `09-caller-identity.json`                                   | `aws sts get-caller-identity`                                                               |
| `10-ec2-instances-table.txt`                                | `aws ec2 describe-instances` (rút gọn field cần), filter theo tag cluster, running — bản `-o json` đầy đủ không đưa vào repo vì chứa `ClientToken` (EC2 Fleet idempotency token, không phải credential nhưng bị secret-scanner CI flag entropy cao) |
| `13-ce-usage-quantity-daily.json`                           | `aws ce get-cost-and-usage`, DAILY, UsageQuantity, group by Purchase Option + Instance Type |

### `locust/`

| File                         | Nội dung                                                                             |
| ---------------------------- | ------------------------------------------------------------------------------------ |
| `locust-stats-requests.json` | `/stats/requests` — toàn bộ per-endpoint stats, run 200-user baseline (đã `stopped`) |
| `locust-stats-requests.csv`  | Cùng dữ liệu, dạng CSV                                                               |
| `locust-report.html`         | Locust HTML report đầy đủ                                                            |
