# D5-06 — Báo cáo Đánh giá Tác động Chi phí của Thiết lập Giới hạn Tài nguyên (Resource Enforcement Cost Impact)

*   **Jira Ticket:** [D5-06](https://ngonguyentruongan2907.atlassian.net/browse/D5-06)
*   **Epic:** EPIC-04 Cost Optimization & EPIC-03 Performance Efficiency
*   **Người thực hiện (CDO-04):** Huy (Chính - Phân tích dữ liệu đo đạc, lập bảng đối soát tài nguyên và tính toán chi phí), An (Hỗ trợ - Phân tích ý nghĩa tài chính/nghiệp vụ và rà soát các ranh giới tối ưu hóa).
*   **Trạng thái:** Đã hoàn thành báo cáo nghiệm thu (Completed - Round 2).

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

| STT | Dịch vụ (Service) | Current CPU Req | Current CPU Limit | Observed Peak CPU | Proposed CPU Req | Proposed CPU Limit | Lý do đề xuất (CPU Rationale) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `kafka` | `100m` | `500m` | **13m** | `100m` | `500m` | Hoạt động ổn định, tải CPU thấp. Giữ nguyên cấu hình hiện tại. |
| 2 | `ad` | `50m` | `200m` | **2m** | `50m` | `200m` | CPU thực tế rất thấp. Giữ nguyên requests/limits. |
| 3 | `fraud-detection` | `50m` | `200m` | **7m** | `50m` | `200m` | CPU thực tế thấp. Giữ nguyên. |
| 4 | `accounting` | `50m` | `200m` | **6m** | `50m` | `200m` | CPU thực tế thấp. Giữ nguyên. |
| 5 | `payment` | `50m` | `200m` | **16m** | `50m` | `200m` | Giữ nguyên để gánh tải luồng thanh toán gRPC. |
| 6 | `frontend` | `100m` | `400m` | **30m** | `100m` | `400m` | Giữ nguyên để phục vụ SSR và định tuyến. |
| 7 | `product-reviews` | `75m` | `300m` | **14m** | `50m` | `200m` | Tối ưu hóa: giảm CPU Request xuống 50m và limit xuống 200m dựa trên thực tế. |
| 8 | `llm` (Mock) | `75m` | `250m` | **14m** | `75m` | `250m` | Giữ nguyên cấu hình mock. |
| 9 | `cart` | `75m` | `300m` | **13m** | `50m` | `200m` | Tối ưu hóa: giảm CPU Request từ 75m xuống 50m dựa trên thực tế. |
| 10 | `checkout` | `75m` | `300m` | **5m** | `50m` | `200m` | Tối ưu hóa: giảm CPU Request từ 75m xuống 50m để tiết kiệm CPU. |
| 11 | Các services khác* | Varies | Varies | **< 15m** | `50m` | `100m` | Chuẩn hóa baseline CPU requests/limits của các services phụ trợ khác. |

### 2.2. Ma trận Phân bổ Tài nguyên Memory (Memory Allocation Matrix)

| STT | Dịch vụ (Service) | Current RAM Req | Current RAM Limit | Observed Peak RAM | Proposed RAM Req | Proposed RAM Limit | Lý do đề xuất (Memory Rationale) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `kafka` | `700Mi` | `700Mi` | **506Mi** | `512Mi` | `700Mi` | Tải thực tế 506Mi. Đặt request 512Mi để khớp sát tải, limit 700Mi bảo vệ OOM. |
| 2 | `ad` | `150Mi` | `300Mi` | **215Mi** | `150Mi` | `300Mi` | RAM thực tế vượt mức request. Cần giữ limit 300Mi để không bị OOMKilled. |
| 3 | `fraud-detection` | `150Mi` | `300Mi` | **208Mi** | `150Mi` | `300Mi` | RAM thực tế cao. Giữ nguyên ranh giới 300Mi để bảo vệ an toàn cụm. |
| 4 | `accounting` | `256Mi` | `256Mi` | **128Mi** | `128Mi` | `256Mi` | RAM thực tế là 128Mi. Tối ưu giảm request từ 256Mi xuống 128Mi. |
| 5 | `payment` | `64Mi` | `128Mi` | **96Mi** | `96Mi` | `128Mi` | RAM thực tế đạt 96Mi. Tăng request lên 96Mi để tránh overcommit. |
| 6 | `frontend` | `192Mi` | `320Mi` | **78Mi** | `128Mi` | `320Mi` | Tối ưu giảm request từ 192Mi xuống 128Mi dựa trên thực tế. |
| 7 | `product-reviews` | `96Mi` | `192Mi` | **67Mi** | `80Mi` | `192Mi` | Tối ưu giảm request từ 96Mi xuống 80Mi. |
| 8 | `llm` (Mock) | `96Mi` | `192Mi` | **68Mi** | `96Mi` | `192Mi` | Giữ nguyên. |
| 9 | `cart` | `96Mi` | `192Mi` | **58Mi** | `64Mi` | `128Mi` | Tối ưu giảm request xuống 64Mi và limit xuống 128Mi. |
| 10 | `checkout` | `48Mi` | `96Mi` | **11Mi** (18.2Mi tải) | `30Mi` | `60Mi` | Tối ưu giảm xuống 30Mi request / 60Mi limit dựa trên thực tế. |
| 11 | Các services khác* | Varies | Varies | **< 20Mi** | `32Mi` | `64Mi` | Các service rất nhẹ (như `shipping` dùng 3Mi, `valkey-cart` dùng 4Mi) có thể hạ tiếp xuống `32Mi / 64Mi`. |

*\*Các dịch vụ phụ trợ còn lại bao gồm: `currency`, `email`, `flagd`, `image-provider`, `product-catalog`, `quote`, `recommendation`, `shipping`, `valkey-cart`, `frontend-proxy`, `postgresql` (PostgreSQL request: 50m/256Mi, limit: 500m/512Mi).*

---

### 2.2. Tính toán tổng lượng tài nguyên đăng ký trước (Total Reservation Calculation)

Để có số liệu toán học chính xác, tổng tài nguyên đăng ký trước (Total Reservation) được tính toán dựa trên số lượng Pod thực tế hoạt động trong cụm (gồm số lượng replica tối thiểu và tối đa khi kích hoạt HPA):

*   **Trạng thái bình thường (HPA Min / Default Replicas):**
    *   Tổng số Pod hoạt động: **22 Pods**
    *   👉 **Tổng CPU Requests:** **1.905 Cores** (1,905m)
    *   👉 **Tổng Memory Requests:** **3,491 MiB (~3.41 GiB)**
    *   👉 **Tổng CPU Limits:** **7.450 Cores**
    *   👉 **Tổng Memory Limits:** **5,893 MiB (~5.75 GiB)**
*   **Trạng thái đỉnh tải cao nhất (HPA Max cho Frontend, Checkout, Currency):**
    *   `frontend` scale-up từ 2 lên 3 replicas (tăng thêm 1 Pod: +100m CPU, +192Mi RAM)
    *   `checkout` scale-up từ 2 lên 3 replicas (tăng thêm 1 Pod: +75m CPU, +48Mi RAM)
    *   `currency` scale-up từ 2 lên 3 replicas (tăng thêm 1 Pod: +75m CPU, +96Mi RAM)
    *   👉 **Tổng CPU Requests tối đa:** **2.155 Cores** (2,155m)
    *   👉 **Tổng Memory Requests tối đa:** **3,827 MiB (~3.74 GiB)**
    *   👉 **Tổng CPU Limits tối đa:** **8.450 Cores**
    *   👉 **Tổng Memory Limits tối đa:** **6,501 MiB (~6.35 GiB)**

---

### 2.3. Đối soát với Năng lực đáp ứng của Node (Per-Node Allocatable State)

*   **Hạ tầng Node hiện tại:** Cụm chạy trên **3 Nodes** vật lý (gồm **2x t3.large** và **1x t3a.large**). Mỗi node có cấu hình phần cứng là **2 vCPUs và 8 GiB RAM**.
*   **Khả năng phân bổ của EKS (Allocatable Capacity):**
    EKS mặc định đặt trước một lượng tài nguyên cho các tiến trình hệ thống (OS, Kubelet, Kube-proxy, DaemonSets). 
    *   *CPU Allocatable:* Khoảng **1.93 Cores** / Node (Tổng 3 Nodes = **5.79 Cores**).
    *   *Memory Allocatable:* Khoảng **7.2 GiB** (~7,370 MiB) / Node (Tổng 3 Nodes = **21.6 GiB**).
*   **Đánh giá Tải trọng tối đa (Headroom & Failover):**
    *   Ở trạng thái đỉnh tải cao nhất (HPA Max), tổng yêu cầu tài nguyên (**2.155 Cores CPU** và **3.74 GiB RAM**) chỉ chiếm lần lượt **37.2% CPU** và **17.3% Memory** tổng năng lượng của cụm 3 Nodes.
    *   **Kịch bản mất 1 Node (Failover N-1):** Nếu 1 Node vật lý gặp sự cố dừng hoạt động, cụm còn lại 2 Nodes (Tổng năng lực allocatable: 3.86 Cores CPU, 14.4 GiB RAM). Lượng tài nguyên yêu cầu tối đa (2.155 Cores, 3.74 GiB) **vẫn hoàn toàn nằm trong mức đáp ứng an toàn của 2 Nodes còn lại**. Hệ thống không bị rơi vào trạng thái thiếu hụt tài nguyên gây Pending pod hoặc sập cụm.

---

### 2.4. Trích xuất dữ liệu xác minh (CLI Checkpoint)
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
> **Giới hạn của Snapshot:** Dữ liệu `kubectl top` trên chỉ là ảnh chụp tức thời (instant snapshot) tại một thời điểm baseline. Mọi kết luận về nguy cơ OOMKilled và co giãn Node (Autoscaling) được nhóm đúc kết dựa trên phân tích dòng dữ liệu liên tục (time-series) trên Grafana/Prometheus xuyên suốt các bài kiểm thử tải nặng chứ không chỉ suy luận đơn lẻ từ snapshot này.

---

## 3. Tác Động Hạ Tầng & Mô Hình Chi Phí AWS (AWS Cost Model)

### 3.1. Số lượng Node vật lý (Node Count Impact)
Việc cấu hình tài nguyên an toàn cho các Pods giúp Kubernetes lập lịch phân bổ đồng đều. Số lượng máy chủ chạy baseline cố định là **3 Nodes** và không tăng thêm dưới tải tĩnh.

### 3.2. Ước tính chi phí AWS (AWS Cost Estimation)

Dưới đây là mô hình ước tính chi phí tính toán hàng tháng ( monthly estimate) cho hạ tầng EKS của dự án tại region `us-east-1`:

| Thành phần tài nguyên | Công thức tính chi phí (AWS Pricing) | Chi phí Ước tính hàng tháng | Ghi chú (Estimate Notes) |
| :--- | :--- | :--- | :--- |
| **EKS Control Plane** | `$0.10 / giờ` | **`$73.00`** | Cố định của AWS cho 1 Cluster |
| **NAT Gateway** | `$0.045 / giờ / gateway` | **`$32.85`** | Phục vụ kết nối Internet ra ngoài |
| **Node t3.large (x2)** | `$0.0832 / giờ / instance` (x2) | **`$119.81`** | Máy chủ Intel chạy workload chính |
| **Node t3a.large (x1)** | `$0.0752 / giờ / instance` (x1) | **`$54.14`** | Máy chủ AMD giá rẻ, tiết kiệm ~10% |
| **Tổng chi phí ước tính**| | **`$279.80 / tháng`**| **Đây chỉ là số liệu ước tính (Estimate)** |

*Lưu ý:* Chi phí thực tế hàng tháng có thể biến động nhẹ phụ thuộc vào dung lượng ổ đĩa EBS volume gắn thêm, lượng dữ liệu truyền qua NAT Gateway (Data Transfer pricing), và sự co giãn đột xuất của Karpenter khi nâng thêm Node trong các bài test tải Flash Sale.

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
*   **Chứng minh mật độ đóng gói tối đa (Pods per Node Limit):**
    *   Theo đặc tả kỹ thuật của AWS VPC CNI, số lượng địa chỉ IP tối đa cấp phát cho mỗi Node `t3.large`/`t3a.large` được tính theo công thức:
        $$\text{Max Pods} = (\text{Số ENI} \times (\text{Số IP trên mỗi ENI} - 1)) + 2 = (3 \times (12 - 1)) + 2 = 35\text{ Pods}$$
    *   Trừ đi khoảng **5-8 Pods** dự phòng cho các dịch vụ hệ thống của EKS (kube-proxy, aws-node, ebs-csi, collector-agent,...), số lượng Pod ứng dụng tối đa có thể xếp trên 1 Node vật lý trong thực tế là **khoảng 27 Pods**.
    *   Với tổng số 19 Pod ứng dụng hiện tại, cụm **3 Nodes** hoàn toàn đáp ứng khả năng phân bổ IP một cách thoải mái (mật độ thực tế chỉ khoảng ~6-7 Pods/node, dư dả vị trí trống cho việc co giãn HPA).
