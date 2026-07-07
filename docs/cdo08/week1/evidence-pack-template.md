# Mẫu Báo Cáo Bằng Chứng - CDO08 (Tuần 1)

**Quy ước đặt tên file bằng chứng (Ảnh/Log):**
* Lưu bằng chứng tại thư mục: `docs/cdo08/week1/evidence/`
* Cú pháp tên file: `[tên-owner]-[tên-service]-[loại-bằng-chứng].[định-dạng]`
* Ví dụ: `nam-checkout-missing-probe.png`

---

## 1. Biểu mẫu chuẩn (Copy phần này để điền)
* **Tên owner:**
* **Task liên quan:**
* **Vấn đề phát hiện:**
* **File hoặc service liên quan:**
* **Lệnh đã chạy (nếu có):**
* **Kết quả lệnh / Ảnh dashboard:** [Chèn text kết quả hoặc link ảnh markdown]
* **Log hoặc trace (nếu có):** [Chèn snippet log hoặc ID trace]
* **Cách hiểu bằng chứng (Rủi ro là gì?):**
* **Link tới backlog hoặc quyết định liên quan:**

---

## 2. Ví dụ mẫu 1 (Mảng Runtime - Nam)
* **Tên owner:** Nam
* **Task liên quan:** Task 18 - Audit readiness và liveness probe coverage
* **Vấn đề phát hiện:** Service `checkout` đang thiếu cấu hình liveness probe và readiness probe.
* **File hoặc service liên quan:** `techx-corp-chart/templates/checkout-deployment.yaml`
* **Lệnh đã chạy:** `kubectl get deployment checkout -n tf4 -o yaml | grep probe`
* **Kết quả lệnh / Ảnh dashboard:** Lệnh không trả về kết quả (Blank output).
* **Log hoặc trace:** N/A
* **Cách hiểu bằng chứng:** Pod checkout thiếu liveness probe nên nếu app bị treo bên trong, Kubernetes sẽ không biết để tự restart. Thiếu readiness probe khiến pod có thể nhận traffic khi chưa khởi động xong, gây lỗi 5xx trực tiếp cho luồng doanh thu.
* **Link tới backlog:** `[Link Jira Task 18]`

---

## 3. Ví dụ mẫu 2 (Mảng Checkout - Quân)
* **Tên owner:** Quân
* **Task liên quan:** Task 11 - Xác định timeout và retry gaps của checkout
* **Vấn đề phát hiện:** Checkout service gọi sang Payment service nhưng không có cấu hình giới hạn thời gian chờ (timeout).
* **File hoặc service liên quan:** `techx-corp-platform/src/checkout/...`
* **Lệnh đã chạy:** Đọc source code tĩnh luồng gọi HTTP.
* **Kết quả lệnh / Ảnh dashboard:** `http.Get("http://payment-service/charge")` đang sử dụng default HTTP client không set timeout.
* **Log hoặc trace:** N/A
* **Cách hiểu bằng chứng:** Nếu service Payment bị chậm hoặc treo, request checkout của khách hàng cũng sẽ bị treo theo vô thời hạn. Điều này làm hỏng SLO độ trễ (latency) và có thể gây cạn kiệt tài nguyên hệ thống.
* **Link tới backlog:** `[Link Jira Task 11]`
