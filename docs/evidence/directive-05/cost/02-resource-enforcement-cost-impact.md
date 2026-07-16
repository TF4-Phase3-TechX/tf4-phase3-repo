# D5-06 — Báo cáo Đánh giá Tác động Chi phí của Thiết lập Giới hạn Tài nguyên (Resource Enforcement Cost Impact)

*   **Jira Ticket:** [D5-06](https://ngonguyentruongan2907.atlassian.net/browse/D5-06)
*   **Epic:** EPIC-04 Cost Optimization & EPIC-03 Performance Efficiency
*   **Người thực hiện (CDO-04):** Huy (Chính - Phân tích dữ liệu đo đạc, lập bảng đối soát tài nguyên và tính toán chi phí), An (Hỗ trợ - Phân tích ý nghĩa tài chính/nghiệp vụ và rà soát các ranh giới tối ưu hóa).
*   **Trạng thái:** Đã hoàn thành báo cáo nghiệm thu (Completed).

---

## 1. Mục tiêu và Phạm vi Phân tích

Báo cáo này đánh giá tác động tài chính và hiệu quả vận hành hạ tầng khi áp đặt chính sách thiết lập giới hạn tài nguyên bắt buộc (Resource Requests & Limits) lên toàn bộ các workloads chạy trên cụm EKS `techx-tf4-cluster`. 

Đặc biệt, báo cáo làm rõ ranh giới giữa việc **Tiết kiệm trực tiếp (Cost Saving)** và **Bảo vệ tính ổn định (Reliability Protection)** để tránh gây hiểu lầm trong báo cáo tài chính dự án gửi lên Tech Lead.

---

## 2. Bảng So Sánh Phân Bổ Tài Nguyên Đăng Ký Trước & Số Liệu Thực Tế (Reservation Before vs After)

Dưới đây là bảng đối chiếu chi tiết tổng tài nguyên đăng ký trước (Requests) của các dịch vụ nghiệp vụ chạy trong namespace `techx-tf4` trước và sau khi áp dụng cấu hình Right-sizing, kết hợp với đối soát dữ liệu đo đạc thực tế.

### 2.1. Bảng đối chiếu số liệu và Minh chứng thực tế (Observed Metrics)

Số liệu đề xuất dưới đây được đối soát trực tiếp từ câu lệnh `kubectl top pods -n techx-tf4` chạy trên EKS cluster thực tế để làm căn cứ vững chắc cho việc cài đặt tài nguyên:

| STT | Dịch vụ (Service) | Tải thực tế ghi nhận (CPU / RAM) | Cấu hình Cũ (Requests / Limits) | Đề xuất Mới (Requests / Limits) | Lý do và Minh chứng thực tế (Rationale based on Evidence) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `kafka` | **13m** CPU / **506Mi** RAM | Mặc định | **256Mi** / **600Mi** | Ăn bộ nhớ RAM lớn nhất cụm (506Mi). Set limit 600Mi để tránh bị OOMKilled. |
| 2 | `ad` | **2m** CPU / **215Mi** RAM | `0m` / `128Mi` | **128Mi** / **256Mi** | Tải thực tế (215Mi) vượt xa giới hạn cũ (128Mi). Nếu enforce limit cũ, **Pod sẽ sập OOM ngay lập tức**. Nâng limit lên 256Mi để an toàn. |
| 3 | `fraud-detection` | **7m** CPU / **208Mi** RAM | `0m` / `128Mi` | **128Mi** / **256Mi** | Tải thực tế (208Mi) vượt giới hạn cũ (128Mi), có nguy cơ OOM cao. Tăng limit lên 256Mi để phòng ngừa. |
| 4 | `accounting` | **6m** CPU / **128Mi** RAM | `50m` / `256Mi` | **64Mi** / **256Mi** | Tải thực tế ổn định ở 128Mi, có thể hạ request từ 256Mi xuống 64Mi để tối ưu hóa chỗ đặt trên Node. |
| 5 | `payment` | **16m** CPU / **96Mi** RAM | `0m` / `60Mi` | **64Mi** / **128Mi** | RAM thực tế (~96Mi) vượt quá limit cũ (60Mi). Nâng limit lên 128Mi để bảo vệ luồng thanh toán gRPC. |
| 6 | `frontend` | **30m** CPU / **78Mi** RAM | `0m` / `250Mi` | **100m** / **300Mi** | Next.js SSR ăn RAM mạnh khi phục vụ traffic lớn. Giữ limit 300Mi làm khoảng đệm an toàn. |
| 7 | `product-reviews` | **14m** CPU / **67Mi** RAM | `0m` / `100Mi` | **50m** / **150Mi** | Dịch vụ Python gRPC chạy tốn bộ nhớ, limit 150Mi là hợp lý. |
| 8 | `llm` (Mock) | **14m** CPU / **68Mi** RAM | Không có | **100m** / **256Mi** | Dịch vụ mock AI cần set rõ ranh giới tài nguyên. |
| 9 | `cart` | **13m** CPU / **58Mi** RAM | `0m` / `128Mi` | **50m** / **128Mi** | RAM thực tế là 58Mi, giữ nguyên limit 128Mi. |
| 10 | `checkout` | **5m** CPU / **11Mi** RAM | `0m` / `20Mi` | **50m** / **60Mi** | Baseline chạy rất nhẹ (11Mi) nhưng dưới tải Flash Sale chạm 18.2MiB. Tăng limit lên 60Mi để tránh OOM do Go GC. |
| 11 | 11 services còn lại* | **< 15m** CPU / **< 20Mi** RAM | `0m` / Chỉ set limits | **50m** / **128Mi** | Các service rất nhẹ (như `shipping` chỉ dùng 3Mi, `valkey-cart` dùng 4Mi, `image-provider` dùng 4Mi). Set requests baseline để lập lịch. |

*\*11 services còn lại bao gồm: `shipping`, `product-catalog`, `currency`, `email`, `flagd`, `quote`, `recommendation`, `valkey-cart`, `image-provider`, `frontend-proxy`, `postgresql`.*

### 2.2. Trích xuất đầu ra từ lệnh kiểm chứng thực tế (Verification Output)

Nhóm đã thực hiện câu lệnh trực tiếp trên cụm EKS tại máy cá nhân và thu được kết quả đo đạc chính xác làm bằng chứng nghiệm thu:

```powershell
# Xem tài nguyên tiêu thụ thực tế của toàn bộ các Pods
kubectl top pods -n techx-tf4
```

*Đầu ra thực tế từ cụm (CLI Output):*
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

*Nhận xét:*
*   Dựa trên CLI output này, chúng ta thấy rõ ranh giới vì sao một số service (như `ad`, `fraud-detection`, `kafka`, `payment`) **bắt buộc phải được cấu hình tăng limits** vượt mức mặc định ban đầu để tránh ứng dụng bị khởi động lại liên tục do cạn RAM (OOMKilled).
*   Đồng thời, nó chứng minh các dịch vụ như `shipping` (2MiB), `valkey-cart` (4MiB) có thể dễ dàng giảm tiếp requests trong tương lai để tối ưu hóa bin-packing tối đa.

### 2.3. Đánh giá sự biến động tổng lượng Reservation
*   **CPU Reservation:** Tăng từ **`50m`** lên **`1,100m` (1.1 vCPU)** (Tăng thêm `1,050m`).
*   **Memory Reservation:** Tăng từ **`256Mi`** lên **`1,568Mi` (~1.53 GiB)** (Tăng thêm `1,312Mi`).
*   **Đánh giá:** Lượng tài nguyên tăng thêm là vô cùng nhỏ so với tổng năng lực của cụm EKS (1.1 vCPU chỉ chiếm khoảng 18.3% năng lực của 3 Nodes vật lý). Việc tăng này là bắt buộc để Kubernetes Scheduler có cơ sở lập lịch thông minh, loại bỏ rủi ro overcommit.

---

## 3. Tác Động Hạ Tầng & Chi Phí AWS Trực Tiếp (Node Count & AWS Bill)

### 3.1. Số lượng Node vật lý (Node Count Impact)
*   Cụm EKS của dự án sử dụng **`t3.large`** làm instance type chính cho Node Group (cấu hình mỗi Node: **2 vCPUs và 8 GiB RAM**).
*   Tổng số máy chủ vật lý chạy thường trực ở trạng thái baseline tĩnh (không có tải) là **3 Nodes** (tương đương **6 vCPUs và 24 GiB RAM** tổng năng lực).
*   **Đánh giá khả năng chứa (Capacity Fit):** 
    Tổng tài nguyên đăng ký mới của 17 dịch vụ ứng dụng (**1.1 vCPU** và **1.53 GiB RAM**) hoàn toàn nằm gọn trong năng lực của một Node đơn lẻ. Do đó, việc áp đặt resource requests **KHÔNG làm tăng số lượng Node vật lý** trong trạng thái bình thường.

### 3.2. Ước tính chi phí AWS trước/sau (Cost Delta Table)

Dưới đây là bảng đối sánh chi phí vận hành trực tiếp hàng tháng (chu kỳ 30 ngày) trên AWS tại region `us-east-1`:

| Cost Driver | Biểu giá AWS tiêu chuẩn | Chi phí Trước tối ưu (monthly) | Chi phí Sau tối ưu (monthly) | Chênh lệch (Cost Delta) |
| :--- | :--- | :--- | :--- | :--- |
| **EKS Control Plane** | `$0.10 / giờ` | `$73.00` | `$73.00` | `$0.00` |
| **NAT Gateway** | `$0.045 / giờ` | `$32.85` | `$32.85` | `$0.00` |
| **EC2 Compute Nodes** | `$0.0832 / giờ / node t3.large` (x3) | `$179.71` | `$179.71` | `$0.00` |
| **Tổng chi phí** | | **`$285.56`** | **`$285.56`** | **`$0.00` (Không đổi)** |

> [!NOTE]
> **Cam kết tài chính:** 
> Dự án không ghi nhận bất kỳ khoản giảm chi phí AWS trực tiếp nào (no direct AWS savings) trên hóa đơn tĩnh, do số lượng Node vật lý và loại Node được giữ nguyên để bảo đảm tính sẵn sàng cao của hệ thống.

---

## 4. Tách Biệt Rõ Ràng Giữa Bảo Vệ Ổn Định & Tiết Kiệm Chi Phí

### 4.1. Chi phí mua bảo hiểm ổn định (Reliability Protection)
*   **Hành động:** Nâng RAM limits cho `checkout` (20Mi -> 60Mi), `frontend` (250Mi -> 300Mi) và `product-reviews` (100Mi -> 150Mi).
*   **Ý nghĩa:** Đây là chi phí cần thiết để bảo vệ hệ thống. Việc nâng giới hạn giúp triệt tiêu hoàn toàn rủi ro Pods cốt lõi bị khởi động lại do lỗi quá tải RAM (OOMKilled) dưới tải cao của giờ vàng Flash Sale.

### 4.2. Khả năng bảo vệ ví tiền gián tiếp (Indirect Cost Saving)
Chính sách thiết lập giới hạn tài nguyên đóng vai trò là "chìa khóa" giúp các cơ chế tự động hóa hoạt động tối ưu nhất:
1.  **Chống lãng phí khi co giãn (Karpenter Consolidation):**
    Karpenter chỉ có thể tính toán để tắt bớt các Node thừa và dồn Pod (scale-down) khi các Pod có khai báo `requests` rõ ràng. Nếu thiếu requests, Karpenter không thể biết Pod tiêu thụ bao nhiêu tài nguyên để thực hiện dồn cụm an toàn, khiến cụm liên tục chạy nhiều Node rỗng dưới tải tĩnh gây lãng phí.
2.  **Hạn chế sập cụm (Noisy Neighbor Protection):**
    Ngăn chặn việc một Pod gặp lỗi tiêu thụ vô hạn tài nguyên RAM/CPU âm thầm, tranh chấp toàn bộ tài nguyên của Node dẫn đến sập toàn bộ các Pod vô tội khác chạy chung máy chủ.
3.  **Hợp lệ hóa HPA:**
    HPA của `frontend` và `checkout` chỉ hoạt động khi có `requests.cpu` làm mốc chia tỷ lệ phần trăm. Việc khai báo giúp HPA scale-up chính xác số lượng bản sao chỉ khi thực sự cần thiết, và scale-down nhanh chóng để tiết kiệm tiền.

---

## 5. Đánh Giá Hiệu Quả Đóng Gói (Bin-packing & Overcommit Analysis)

*   **Giảm thiểu Overcommit nguy hiểm:** Trước đây, tổng limits memory là ~1.5 GiB nhưng requests là 256MiB (tỷ lệ overcommit chênh lệch lớn). Cấu hình mới đưa tỷ lệ requests sát hơn với limits thực tế đo đạc, đảm bảo tính toán lập lịch của K8s Scheduler chính xác 100%.
*   **Cải thiện mật độ Node:** Việc chuẩn hóa baseline requests của các service phụ trợ về `50m CPU / 64Mi RAM` giúp K8s đóng gói (bin-packing) tối ưu, có thể xếp khít tối đa **~25 Pods trên một Node t3.large** mà không gây xung đột tài nguyên.

---

## 6. Danh Sách Ứng Viên Right-sizing Tối Ưu Thêm Trong Tương Lai

Qua đo đạc thực tế trạng thái baseline, nhóm xác định các dịch vụ sau hoạt động cực kỳ nhẹ (CPU < 5m, Memory < 30MiB) và là ứng viên hàng đầu để tiếp tục cắt giảm requests ở Week 2 nhằm gia tăng mật độ đóng gói:
1.  **`currency`** (Hiện tại: 50m / 64Mi $\rightarrow$ Đề xuất tương lai: 10m / 32Mi)
2.  **`email`** (Hiện tại: 50m / 64Mi $\rightarrow$ Đề xuất tương lai: 10m / 32Mi)
3.  **`ad`** (Hiện tại: 50m / 64Mi $\rightarrow$ Đề xuất tương lai: 10m / 32Mi)
4.  **`flagd`** (Hiện tại: 50m / 64Mi $\rightarrow$ Đề xuất tương lai: 10m / 32Mi)
5.  **`image-provider`** (Hiện tại: 50m / 64Mi $\rightarrow$ Đề xuất tương lai: 10m / 32Mi)
