# 06. Performance Risk & Follow-up Backlog

Tài liệu này tổng hợp các rủi ro hiệu năng còn lại của hệ thống TechX và danh sách các tác vụ follow-up (backlog) cần thực hiện trong Week 2 để tối ưu hóa hệ thống.

---

## 1. Danh Sách Rủi Ro Hiệu Năng Còn Lại (Performance Risks)

| STT | Rủi Ro (Risk) | Khả năng xảy ra / Ảnh hưởng | Mô Tả Chi Tiết | Giải Pháp Giảm Thiểu (Mitigation) |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **Giảm hiệu năng khi swap sang LLM thật** | Cao / Nghiêm trọng | Hiện tại đang dùng Mock LLM phản hồi trong ~98ms. Khi chuyển sang OpenAI/Gemini thật ở Week 2, latency sẽ tăng vọt lên **1.5s - 3s**, làm chậm API hỏi đáp sản phẩm. | - Áp dụng Valkey/Redis cache câu hỏi phổ biến.<br>- Cấu hình Streaming Response (Server-Sent Events) gRPC để hiển thị text dần dần cho user. |
| **2** | **Nghẽn/Sập Node do thiếu giới hạn CPU** | Trung bình / Cao | Hầu hết các service chưa có CPU requests/limits. Một service bị loop hoặc tải cao có thể chiếm dụng toàn bộ CPU của Node, gây ảnh hưởng đến các service chạy chung Node. | Áp dụng cấu hình CPU Requests & Limits đã đề xuất trong tài liệu [Right-sizing](file:///D:/tf4-phase3-repo/docs/evidence/epic-03-performance-efficiency/05-scaling-right-sizing-recommendation.md). |
| **3** | **Lỗi OOM-Killed khi chạy tải cao ở dịch vụ Go** | Trung bình / Trung bình | Cấu hình `checkout` hiện tại quá sát (`limit 20Mi` và `GOMEMLIMIT 16MiB`). Khi lượng order tăng đột biến, GC không giải phóng kịp RAM sẽ làm pod bị restart liên tục. | Nâng giới hạn RAM lên `60Mi` và `GOMEMLIMIT` lên `48MiB` như đề xuất. |
| **4** | **PostgreSQL bị nghẽn (Database Saturation)** | Thấp / Trung bình | Các truy vấn search catalog và review sản phẩm thiếu LIMIT và INDEX, khi lượng dữ liệu lớn có thể gây full scan bảng và nghẽn CPU database. | Thực hiện tạo INDEX cho khóa ngoại `product_id` và thêm phân trang (pagination) cho API. |


---

## 2. Kế Hoạch Hành Động & Follow-up Backlog (Week 2)

Dưới đây là các task cần đưa vào backlog để giải quyết triệt để trong Week 2:

### Task 1: Triển khai cấu hình Right-sizing & HPA
* **Mô tả**: Cập nhật file `values.yaml` để thêm CPU/Memory requests & limits cho toàn bộ 17 services, đồng thời deploy Helm chart của Horizontal Pod Autoscaler (HPA) cho `frontend` và `checkout`.
* **Người thực hiện**: Huy (Owner)
* **Độ ưu tiên**: High
* **Tiêu chí hoàn thành**: Áp dụng thành công lên EKS, kiểm tra pod chạy bình thường với config mới.

### Task 2: Fix lỗi Metrics Server trên EKS
* **Mô tả**: Liên hệ và theo dõi đội CDO04 hoàn tất việc deploy `metrics-server` để lệnh `kubectl top nodes/pods` hoạt động bình thường.
* **Người thực hiện**: Huy (Owner) / Ninh (Support)
* **Độ ưu tiên**: Medium
* **Tiêu chí hoàn thành**: Chạy lệnh `kubectl top nodes` trả về chỉ số CPU/RAM thực tế.

### Task 3: Tối ưu hóa Database queries (INDEX & LIMIT)
* **Mô tả**: Viết migration script tạo index trên PostgreSQL và cập nhật câu query trong `product-catalog` và `product-reviews` để áp dụng LIMIT/OFFSET hoặc phân trang.
* **Người thực hiện**: Dev Team
* **Độ ưu tiên**: Medium
* **Tiêu chí hoàn thành**: Query running time giảm, EXPLAIN ANALYZE không còn Table Scan.

### Task 4: Tích hợp LLM thật & Cấu hình Caching/Streaming
* **Mô tả**: Thay thế Mock LLM bằng API LLM thật, triển khai Valkey/Redis cache cho các câu hỏi trùng lặp và chuyển API trả về dạng stream.
* **Người thực hiện**: Dev Team
* **Độ ưu tiên**: High
* **Tiêu chí hoàn thành**: Trải nghiệm người dùng mượt mà, thời gian phản hồi từ lúc click đến khi xuất hiện chữ đầu tiên < 300ms.
