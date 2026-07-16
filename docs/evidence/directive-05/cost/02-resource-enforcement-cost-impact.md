# D5-06 — Báo cáo Đánh giá Tác động Chi phí của Thiết lập Giới hạn Tài nguyên (Resource Enforcement Cost Impact)

*   **Jira Ticket:** [D5-06](https://ngonguyentruongan2907.atlassian.net/browse/D5-06)
*   **Epic:** EPIC-04 Cost Optimization & EPIC-03 Performance Efficiency
*   **Người thực hiện (CDO-04):** Huy (Chính - Phân tích dữ liệu đo đạc, lập bảng đối soát tài nguyên và tính toán chi phí), An (Hỗ trợ - Phân tích ý nghĩa tài chính/nghiệp vụ và rà soát các ranh giới tối ưu hóa).
*   **Trạng thái:** Đã hoàn thành báo cáo nghiệm thu (Completed - Round 3).

---

## 1. Mục tiêu và Phạm vi Phân tích

Báo cáo này đánh giá tác động tài chính và hiệu quả vận hành hạ tầng khi áp đặt chính sách thiết lập giới hạn tài nguyên bắt buộc (Resource Requests & Limits) lên toàn bộ các workloads chạy trên cụm EKS `techx-tf4-cluster` dựa trên cấu hình hiện tại trong file `values.yaml` và các số liệu đo đạc thực tế.

Tài liệu này làm rõ ranh giới giữa việc **Tiết kiệm chi phí (Cost Saving)** và **Bảo vệ tính ổn định (Reliability Protection)** nhằm tránh gây hiểu lầm trong báo cáo tài chính dự án gửi lên Tech Lead.

> [!NOTE]
> **Lưu ý về CI/CD:**
> Quy trình thông qua CI (CI pass) của dự án chỉ xác nhận định dạng Markdown và cú pháp cấu hình Helm/YAML hợp lệ, hoàn toàn không xác nhận tính đúng đắn về mặt toán học và số liệu phân tích trong báo cáo này.

---

## 2. Số Liệu Phân Bổ Tài Nguyên Thực Tế (Resource Reservation Breakdown)

Báo cáo phân tích này tách biệt rõ ràng các thông số CPU Requests/Limits và Memory Requests/Limits của 17 dịch vụ nghiệp vụ chính trong namespace `techx-tf4`, đối chiếu cấu hình hiện tại (Current Configuration in values.yaml) với dữ liệu đo đạc thực tế.

### 2.1. Ma trận Phân bổ Tài nguyên CPU (CPU Allocation Matrix)

| STT | Dịch vụ (Service) | Current CPU Req | Current CPU Limit | Observed snapshot CPU (Pod 1 / Pod 2) | Proposed CPU Req | Proposed CPU Limit | Lý do đề xuất (CPU Rationale) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `kafka` | `100m` | `500m` | **13m** | `100m` | `500m` | Tải CPU thực tế thấp. Đề xuất giữ nguyên cấu hình hiện tại để đảm bảo an toàn baseline. |
| 2 | `ad` | `50m` | `200m` | **2m** | `50m` | `200m` | CPU thực tế thấp. Giữ nguyên làm mức tối thiểu phòng ngừa (precaution). |
| 3 | `fraud-detection` | `50m` | `200m` | **7m** | `50m` | `200m` | Giữ nguyên cấu hình hiện tại. |
| 4 | `accounting` | `50m` | `200m` | **6m** | `50m` | `200m` | Giữ nguyên cấu hình hiện tại. |
| 5 | `payment` | `50m` | `200m` | **10m / 16m** | `50m` | `200m` | Giữ nguyên đề phòng tải gRPC tăng đột biến. |
| 6 | `frontend` | `100m` | `400m` | **7m / 30m** | `100m` | `400m` | Giữ nguyên cấu hình hiện tại để phục vụ SSR định tuyến. |
| 7 | `product-reviews` | `75m` | `300m` | **14m** | `50m` | `200m` | Đề xuất giảm CPU Request xuống 50m và limit xuống 200m dựa trên dữ liệu snapshot. |
| 8 | `llm` (Mock) | `75m` | `250m` | **14m** | `75m` | `250m` | Giữ nguyên cấu hình mock. |
| 9 | `cart` | `75m` | `300m` | **7m / 13m** | `50m` | `200m` | Đề xuất tối ưu giảm CPU Request xuống 50m. |
| 10 | `checkout` | `75m` | `300m` | **1m / 5m** | `50m` | `200m` | Đề xuất tối ưu giảm CPU Request xuống 50m. |
| 11 | Các services khác* | Varies | Varies | **< 15m** | `50m` | `100m` | Chuẩn hóa baseline CPU của các services phụ trợ khác. |

### 2.2. Ma trận Phân bổ Tài nguyên Memory (Memory Allocation Matrix)

| STT | Dịch vụ (Service) | Current RAM Req | Current RAM Limit | Observed snapshot RAM (Pod 1 / Pod 2) | Proposed RAM Req | Proposed RAM Limit | Lý do đề xuất (Memory Rationale) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `kafka` | `700Mi` | `700Mi` | **506Mi** | `512Mi` | `700Mi` | Đề xuất hạ request xuống 512Mi để khớp sát snapshot thực tế, giữ limit 700Mi để phòng ngừa rủi ro OOM cho JVM. |
| 2 | `ad` | `150Mi` | `300Mi` | **215Mi** | `150Mi` | `300Mi` | RAM thực tế vượt mức request. Đề xuất giữ limit 300Mi làm giải pháp phòng ngừa OOMKilled khi có tải. |
| 3 | `fraud-detection` | `150Mi` | `300Mi` | **208Mi** | `150Mi` | `300Mi` | RAM thực tế cao. Đề xuất duy trì limit 300Mi để đảm bảo độ tin cậy của container. |
| 4 | `accounting` | `256Mi` | `256Mi` | **128Mi** | `128Mi` | `256Mi` | Đề xuất tối ưu giảm request từ 256Mi xuống 128Mi dựa trên thực tế. |
| 5 | `payment` | `64Mi` | `128Mi` | **92Mi / 96Mi** | `96Mi` | `128Mi` | RAM snapshot vượt request 64Mi. Đề xuất nâng request lên 96Mi tránh overcommit. |
| 6 | `frontend` | `192Mi` | `320Mi` | **70Mi / 78Mi** | `128Mi` | `320Mi` | Đề xuất tối ưu giảm request xuống 128Mi dựa trên thực tế. |
| 7 | `product-reviews` | `96Mi` | `192Mi` | **67Mi** | `80Mi` | `192Mi` | Đề xuất tối ưu giảm request xuống 80Mi. |
| 8 | `llm` (Mock) | `96Mi` | `192Mi` | **68Mi** | `96Mi` | `192Mi` | Giữ nguyên. |
| 9 | `cart` | `96Mi` | `192Mi` | **45Mi / 58Mi** | `64Mi` | `128Mi` | Đề xuất tối ưu giảm request xuống 64Mi và limit xuống 128Mi. |
| 10 | `checkout` | `48Mi` | `96Mi` | **9Mi / 11Mi** | `30Mi` | `60Mi` | Đề xuất giảm xuống 30Mi request / 60Mi limit làm biên an toàn phòng ngừa heap spike của Go runtime. |
| 11 | Các services khác* | Varies | Varies | **< 20Mi** | `32Mi` | `64Mi` | Chuẩn hóa baseline của các services phụ trợ khác. |

*\*Các dịch vụ phụ trợ còn lại bao gồm: `currency`, `email`, `flagd`, `image-provider`, `product-catalog`, `quote`, `recommendation`, `shipping`, `valkey-cart`, `frontend-proxy`, `postgresql` (PostgreSQL request: 50m/256Mi, limit: 500m/512Mi).*

---

### 2.3. Ràng buộc Phạm vi Thống kê (Scope Definition & Pod Count Reconcile)

Để đảm bảo số liệu nhất quán trên toàn báo cáo và tránh mâu thuẫn, các định nghĩa phạm vi được phân loại rõ ràng như sau:

1.  **Workload Components (Thành phần cấu hình Helm):** **22** components được định nghĩa trực tiếp trong file `values.yaml` (gồm 17 business services + 5 middleware/infra services là `postgresql`, `valkey-cart`, `kafka`, `load-generator` và `frontend-proxy`).
2.  **Running Application Pods (Số lượng Pod chạy baseline thực tế):** **31** Pods đang chạy thực tế trong namespace `techx-tf4`. 
    *   *Công thức khớp số liệu:* 22 baseline pods (mỗi component chạy tối thiểu 1 Pod) + 9 Pods phụ trợ do cấu hình chạy mặc định 2 replicas ở file `values.yaml` (gồm `cart` [+1], `checkout` [+1], `currency` [+1], `frontend` [+1], `frontend-proxy` [+1], `payment` [+1], `product-catalog` [+1], `quote` [+1], `shipping` [+1]). 
    *   *Xác thực lịch sử:* Số lượng 31 Pods này hoàn toàn trùng khớp với dữ liệu giám sát thực tế được ghi nhận tại mục `status.used.pods` của ResourceQuota: [37-resourcequota-round2.yaml](../../directive-03/cost/raw/37-resourcequota-round2.yaml#L35).

---

### 2.4. Tính toán tổng lượng tài nguyên đăng ký trước (Total Reservation Calculation)

Dựa trên số lượng 31 Pods chạy baseline ở trên, tổng tài nguyên đăng ký trước (Total Reservation) được tính toán như sau:

*   **Trạng thái bình thường (HPA Min / Baseline Replicas):**
    *   Tổng số Pod hoạt động: **31 Pods**
    *   👉 **Tổng CPU Requests:** **1.905 Cores** (1,905m)
    *   👉 **Tổng Memory Requests:** **3,491 MiB (~3.41 GiB)**
    *   👉 **Tổng CPU Limits:** **7.450 Cores** (7,450m)
    *   👉 **Tổng Memory Limits:** **5,893 MiB (~5.75 GiB)**
    *(Số liệu này được đối soát trùng khớp 100% với ResourceQuota thực tế đang sử dụng tại [37-resourcequota-round2.yaml:L33-37](../../directive-03/cost/raw/37-resourcequota-round2.yaml#L33-L37)).*
*   **Kịch bản đỉnh tải lý thuyết tối đa (HPA Max Scale-up):**
    Nếu 3 dịch vụ có cấu hình HPA đồng loạt scale lên mức tối đa (`frontend` tăng thêm 1 Pod [+100m CPU limit, +320Mi RAM limit], `checkout` tăng thêm 1 Pod [+300m CPU limit, +96Mi RAM limit], và `currency` tăng thêm 1 Pod [+300m CPU limit, +192Mi RAM limit]):
    *   👉 **Tổng CPU Requests tối đa:** **2.155 Cores** (2,155m)
    *   👉 **Tổng Memory Requests tối đa:** **3,827 MiB (~3.74 GiB)**
    *   👉 **Tổng CPU Limits tối đa (Lý thuyết):** **8.450 Cores** (8,450m)
    *   👉 **Tổng Memory Limits tối đa (Lý thuyết):** **6,501 MiB (~6.35 GiB)**

> [!WARNING]
> **Blocker về ResourceQuota:**
> Theo cấu hình cứng được định nghĩa tại [quota.yaml](../../../../deploy/quota.yaml#L8) và log kiểm chứng thực tế [37-resourcequota-round2.yaml#L20](../../directive-03/cost/raw/37-resourcequota-round2.yaml#L20), namespace `techx-tf4` đang bị giới hạn trần cứng là **`limits.cpu: "8"`**. 
> Do đó, kịch bản HPA Max chạm **8.450 Cores CPU Limits** ở trên chỉ là **kịch bản giả định (hypothetical scenario)** và không thể triển khai được (non-deployable) trong thực tế dưới quota hiện hành. Nếu xảy ra đỉnh tải lớn kích hoạt HPA scale tối đa, Kubernetes Admission sẽ từ chối khởi tạo các Pod mới vì vượt quá quota 8.0 Cores. Để chạy được kịch bản này, cần cập nhật quota `limits.cpu` lên ít nhất **9.0 Cores**.

---

### 2.5. Đối soát với Năng lực đáp ứng của Node (Per-Node Allocatable State)

*   **Hạ tầng Node:** Dựa trên dữ liệu cấu hình thực tế tại [node-conditions.json](../../directive-03/performance/runs/maint-20260715T172819Z/preflight/node-conditions.json), cụm EKS đang chạy gồm **3-4 Nodes** động (2x t3.large làm baseline và các node t3a.large/t3.large do Karpenter scale-up khi có tải).
*   **Tài nguyên khả dụng (Node Allocatable):**
    Mỗi máy chủ t3.large/t3a.large có cấu hình vật lý 2 vCPUs và 8 GiB RAM. Sau khi trừ đi phần EKS reservation, tài nguyên khả dụng thực tế gán cho ứng dụng là:
    *   *CPU Allocatable:* Khoảng **1.93 Cores** / Node (Tổng 3 Nodes = **5.79 Cores**).
    *   *Memory Allocatable:* Khoảng **7.2 GiB** (~7,370 MiB) / Node (Tổng 3 Nodes = **21.6 GiB**).
*   **Kịch bản lỗi mất 1 Node (Failover N-1 - Đánh giá lý thuyết):**
    *   *Aggregate Headroom:* Về mặt lý thuyết tổng thể, lượng tài nguyên yêu cầu thực tế (đỉnh CPU request HPA max = 2.155 Cores, RAM request = 3.74 GiB) có đủ khoảng trống tổng tài nguyên lý thuyết (aggregate request headroom) để chạy trên 2 Nodes còn lại (tổng năng lực allocatable của 2 nodes còn lại là 3.86 Cores CPU, 14.4 GiB RAM).
    *   *Ràng buộc Scheduler thực tế:* Tuy nhiên, việc phân bổ Pod khi sập node trong thực tế không chỉ phụ thuộc vào dung lượng tổng, mà bị chi phối mạnh mẽ bởi các quy tắc lập lịch. Logs hệ thống của Karpenter (truy xuất tại namespace `kube-system`) ghi nhận các cảnh báo:
        > `pod(s) have a preferred TopologySpreadConstraint which can prevent consolidation` đối với các pod `payment`, `checkout`, `frontend-proxy`, `cart`, `currency`, `frontend`.
        > `pod(s) have a preferred Anti-Affinity which can prevent consolidation` đối với pod `opensearch-0`.
    *   *Kết luận:* Do các ràng buộc Topology Spread Constraints (rải Pod đều trên các host) và Anti-Affinity này, Kubernetes Scheduler bị hạn chế trong việc dồn chung (bin-pack) các Pod lên số ít node. 
    *   *Giới hạn kiểm chứng thực tế:* Do tài khoản IAM/SSO hiện tại của nhóm dự án (`AWSReservedSSO_TF4-CostPerfReadOnlyAlerting`) chỉ có quyền Read-Only và bị chặn quyền Patch Node (`nodes is forbidden: User cannot patch resource nodes in API group "" at the cluster scope`), các thử nghiệm thực tế như chạy lệnh `cordon/drain` chưa thể thực hiện được. Kết luận N-1 ở đây được ghi nhận là giả thuyết lý thuyết (theoretical aggregate headroom) và cần được kiểm chứng bằng scheduler-placement validation thực tế bởi tài khoản có quyền quản trị cao hơn.

---

### 2.6. Trích xuất dữ liệu xác minh (CLI Checkpoint)
Dưới đây là snapshot tài nguyên thực tế đo được qua lệnh `kubectl top pods` ở trạng thái hoạt động bình thường để tham chiếu:

```powershell
kubectl top pods -n techx-tf4
```
```text
NAME                               CPU(cores)   MEMORY(bytes)   
accounting-6dbf7f764d-zh9qx        6m           128Mi
ad-6595659799-l75zg                2m           215Mi
cart-68ddd65c7f-6gdl8              13m          45Mi
cart-68ddd65c7f-cd9h9              7m           58Mi
checkout-68f6488757-kfvtx          1m           9Mi
checkout-68f6488757-lc5sv          5m           11Mi
currency-f586fcb4-ftbxg            2m           17Mi
currency-f586fcb4-r5vdb            2m           8Mi
email-7fb5949f98-77q8r             3m           51Mi
flagd-6cf848ccc9-t7455             2m           23Mi
fraud-detection-665f45b679-jfkmj   7m           208Mi
frontend-7ff4667fc6-6g5wh          7m           70Mi
frontend-7ff4667fc6-cpxz6          30m          78Mi
frontend-proxy-79658b874b-dsjhj    4m           16Mi
frontend-proxy-79658b874b-s6r82    8m           16Mi
image-provider-859d68d958-j9kzg    1m           4Mi
kafka-575c57b489-ts9pp             13m          506Mi
llm-6c96948c64-kqdpd               14m          68Mi
load-generator-7dbc8d784-gsmdf     17m          109Mi
payment-6d47766ff6-9vbr9           10m          92Mi
payment-6d47766ff6-fb5rb           16m          96Mi
postgresql-5b49658ddf-wbjjv        13m          47Mi
product-catalog-78b9958b94-p4mn7   5m           11Mi
product-catalog-78b9958b94-zrdr5   2m           11Mi
product-reviews-689f77f98c-2dwfb   14m          67Mi
quote-7875fd4b58-2mhbv             1m           16Mi
quote-7875fd4b58-9tm4h             1m           15Mi
recommendation-78948dd47d-6ldkw    11m          40Mi
shipping-7dbd9d698d-w2wh2          2m           3Mi
shipping-7dbd9d698d-x7lws          1m           2Mi
valkey-cart-64779877c-5fmtj        4m           4Mi
```

> [!WARNING]
> **Giới hạn của Snapshot:** Dữ liệu `kubectl top` trên chỉ là ảnh chụp tức thời (instant snapshot) tại một thời điểm baseline. Mọi kết luận về nguy cơ OOMKilled và co giãn Node (Autoscaling) được nhóm đúc kết dựa trên phân tích dòng dữ liệu liên tục (time-series) trên Grafana/Prometheus xuyên suốt các bài kiểm thử tải nặng (xem báo cáo kiểm thử đầy đủ tại [D3-PERF-02-evidence.md](../../directive-03/performance/D3-PERF-02-evidence.md) và ảnh minh chứng [grafana-resources-load.png](../../epic-03-performance-efficiency/screenshots/grafana-resources-load.png)) chứ không chỉ suy luận đơn lẻ từ snapshot này.

---

## 3. Tác Động Hạ Tầng & Mô Hình Chi Phí AWS (AWS Cost Model)

### 3.1. Số lượng Node vật lý (Node Count Impact - Giả định Kịch bản)
Trong thực tế, Karpenter tự động tắt/bật các Node máy chủ tùy theo tải (ví dụ: `t3a.large` được Karpenter quản lý linh hoạt, số liệu giờ chạy của `t3a.large` tại dữ liệu CE cho thấy có những ngày chạy 3.8 giờ và có ngày không chạy). Do đó, phân tích này giả định một **kịch bản phân bổ tĩnh minh họa gồm 3 Nodes (2× t3.large + 1× t3a.large)** để ước tính giới hạn chi phí trần, không phản ánh lượng Node chạy cố định 100% thời gian thực tế.

### 3.2. Ước tính chi phí AWS (AWS Cost Estimation)

Dưới đây là mô hình chi phí ước tính hàng tháng theo **Kịch bản minh họa 730 giờ hoạt động (730-hour illustrative scenario: 2× t3.large + 1× t3a.large)**. Mô hình này sử dụng dữ liệu đơn giá từ [39-pricing-t3a-large-round2.json](../../directive-03/cost/raw/39-pricing-t3a-large-round2.json) và [40-pricing-t3-large-round2.json](../../directive-03/cost/raw/40-pricing-t3-large-round2.json):

| Thành phần tài nguyên | Công thức tính chi phí (AWS Pricing) | Chi phí Ước tính hàng tháng | Ghi chú (Scenario Notes) |
| :--- | :--- | :--- | :--- |
| **EKS Control Plane** | `$0.10 / giờ` × 730 giờ | **`$73.00`** | Cố định cho 1 Cluster |
| **NAT Gateway** | `$0.045 / giờ / gateway` × 730 giờ | **`$32.85`** | Kết nối mạng nội bộ ra ngoài |
| **Node t3.large (x2)** | `$0.0832 / giờ / instance` × 2 × 730 giờ | **`$121.47`** | Cặp máy chủ Intel chạy baseline |
| **Node t3a.large (x1)** | `$0.0752 / giờ / instance` × 730 giờ | **`$54.90`** | Máy chủ AMD chạy dự phòng linh hoạt |
| **Tổng chi phí kịch bản**| | **`$282.22 / tháng`**| **Dữ liệu ước tính theo kịch bản (Scenario Estimate)** |

*Lưu ý quan trọng:* Bảng trên là **mô hình ước tính kịch bản (scenario estimate)** để lập kế hoạch tài nguyên, không phải là đối soát hóa đơn thực tế (billing reconciliation). Dữ liệu Cost Explorer (CE) thực tế tại [41-ce-cost-and-usage-round2.json](../../directive-03/cost/raw/41-ce-cost-and-usage-round2.json) phản ánh chi phí toàn bộ tài khoản AWS EC2 (account-wide query) chứ không giới hạn riêng phạm vi của cluster/NAT gateway này.

---

## 4. Tách Biệt Rõ Ràng Giữa Bảo Vệ Ổn Định & Tiết Kiệm Chi Phí

### 4.1. Chi phí bảo vệ ổn định hệ thống (Reliability Protection)
Việc nâng giới hạn RAM limit của các Pod như `checkout` (lên 96Mi), `frontend` (lên 320Mi) và `product-reviews` (lên 192Mi) là quyết định kỹ thuật nhằm **nâng cao tính ổn định**, hoàn toàn không phải để giảm chi phí. Khoảng đệm RAM tăng thêm giúp loại bỏ nguy cơ sập Pod bất ngờ khi runtime thực thi dọn rác (Garbage Collection) dưới tải cao.

### 4.2. Giá trị tối ưu chi phí gián tiếp (Indirect Cost Protection)
Việc thực thi chính sách tài nguyên chuẩn xác đem lại lợi ích kinh tế gián tiếp:
1.  **HPA co giãn chính xác:** HPA của `frontend`, `checkout`, và `currency` chỉ có thể kích hoạt scale-up khi có chỉ số `requests.cpu` làm mốc tham chiếu. Khi hết tải, HPA tự động scale-down giúp giải phóng tài nguyên lập tức.
2.  **Karpenter dồn cụm (Consolidation):** Karpenter dựa vào `requests` của các Pod để tính toán toán học xem có thể dồn các Pod chạy rải rác về chung 1 Node vật lý hay không để tắt bớt Node trống. Nếu không set requests, Karpenter không thể hoạt động, gây lãng phí Node chạy không tải.

---

## 5. Đánh Giá Hiệu Quả Đóng Gói (Bin-packing & Overcommit Analysis)

*   **Giảm thiểu Overcommit nguy hiểm:** Đưa tổng lượng CPU/RAM requests tiệm cận gần hơn với tải thực tế đo đạc, đảm bảo K8s Scheduler lập lịch an toàn, tránh tình trạng dồn quá nhiều Pod nặng vào một Node gây treo nghẽn vật lý.
*   **Chứng minh giới hạn địa chỉ IP (IP capacity limit):**
    Theo đặc tả kỹ thuật của AWS VPC CNI, số lượng địa chỉ IP tối đa cấp phát cho mỗi Node `t3.large`/`t3a.large` được tính theo công thức:
    $$\text{Max Pods} = \text{Số ENI} \times (\text{Số IP trên mỗi ENI} - 1) + 2 = 3 \times (12 - 1) + 2 = 35\text{ Pods}$$
    Đây là giới hạn vật lý cứng về IP trên mỗi Node của AWS EC2. Mọi quy trình lập lịch phân bổ Pod của EKS đều bị giới hạn bởi trần cứng này.
