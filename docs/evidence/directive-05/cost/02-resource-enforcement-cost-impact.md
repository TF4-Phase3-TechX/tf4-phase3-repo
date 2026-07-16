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

## 2. Bảng So Sánh Phân Bổ Tài Nguyên Đăng Ký Trước (Reservation Before vs After)

Dưới đây là bảng đối chiếu chi tiết tổng tài nguyên đăng ký trước (Requests) của 17 dịch vụ nghiệp vụ chạy trong namespace `techx-tf4` trước và sau khi áp dụng cấu hình Right-sizing:

### 2.1. Bảng so sánh tài nguyên theo từng dịch vụ

| STT | Dịch vụ (Service) | Replicas | CPU Request Cũ | CPU Request Mới | RAM Request Cũ | RAM Request Mới | Ghi chú & Lý do (Rationale) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `checkout` | 2 | `0m` | `50m` (x2) | `0Mi` | `30Mi` (x2) | Tăng an toàn để chạy GC của Go, tránh OOM |
| 2 | `frontend` | 2 | `0m` | `100m` (x2) | `0Mi` | `150Mi` (x2) | Phục vụ SSR của Next.js |
| 3 | `product-reviews` | 1 | `0m` | `50m` | `0Mi` | `80Mi` | Python gRPC xử lý text |
| 4 | `llm` (Mock) | 1 | Không có | `100m` | Không có | `128Mi` | Khai báo mới để tránh tranh chấp |
| 5 | `payment` | 1 | `0m` | `50m` | `0Mi` | `40Mi` | Dịch vụ thanh toán cốt lõi |
| 6 | `accounting` | 1 | `50m` | `50m` | `256Mi` | `256Mi` | Giữ nguyên cấu hình chuẩn |
| 7 | 11 services còn lại* | 1 | `0m` | `50m` (x11) | `0Mi` | `64Mi` (x11) | Áp dụng baseline tiêu chuẩn |
| **Tổng** | **17 Services** | **19 Pods** | **50m** | **1,100m (1.1 vCPU)** | **256Mi** | **1,568Mi (~1.53 GiB)** | **Tăng tài nguyên đăng ký trước** |

*\*11 services còn lại bao gồm: `cart`, `shipping`, `product-catalog`, `ad`, `recommendation`, `currency`, `email`, `fraud-detection`, `flagd`, `valkey-cart`, `image-provider`.*

### 2.2. Đánh giá sự biến động tổng lượng Reservation
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
