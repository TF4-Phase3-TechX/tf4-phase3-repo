# Mandate 8 - Kafka to Amazon MSK Migration Analysis

Tài liệu này định nghĩa cấu trúc dữ liệu hiện tại và các hướng di trú Kafka để hội đồng Tech Leads cùng nghiên cứu và đối chiếu.

---

## 1. Hiện trạng Kafka (Current State Analysis)

* **Phiên bản:** Kafka KRaft (chạy dưới dạng Pod đơn lẻ `kafka` đóng vai trò cả broker và controller trong EKS cluster).
* **Topic & Dữ liệu:** Chủ yếu là topic `orders`.
  * `checkout` service đóng vai trò **Producer** (đẩy đơn hàng mới vào Kafka).
  * `accounting` và `fraud-detection` services đóng vai trò **Consumers** (đọc event từ topic `orders` để xử lý kế toán và phát hiện gian lận).
* **Lưu trữ hiện tại:** PVC `kafka-pvc` dung lượng 10 GiB, StorageClass `gp2` (mount tại `/tmp/kafka-data`). 
* **Bảo mật hiện tại:** Sử dụng giao thức Plaintext (cổng `9092`), chưa bật mã hóa TLS hay xác thực SASL cho các client nội bộ.

---

## 2. Các Quyết định & Hướng giải quyết (Decisions & Options)

### QUYẾT ĐỊNH 1: LỰA CHỌN PHƯƠNG ÁN GIẢI QUYẾT CHI PHÍ MSK (COST & SIZING OPTION)
* **Phương án A:** Sử dụng MSK Serverless (Tự động co giãn, base cost cao và yêu cầu xin duyệt ngân sách ngoại lệ).
* **Phương án B:** Sử dụng MSK Provisioned với Broker cỡ nhỏ (Chạy cụm node cố định `t3.small` hoặc `m7g.large`).
* **Phương án C:** Trình xin văn bản Miễn trừ (Waiver / Defer) hoãn di trú và giữ Kafka in-cluster đính kèm PVC.

---

### QUYẾT ĐỊNH 2: LỰA CHỌN PHƯƠNG THỨC DI TRÚ KAFKA (MIGRATION METHOD)
* **Phương án A:** Sử dụng công cụ đồng bộ MirrorMaker 2 hoặc MSK Replicator (Đồng bộ trực tuyến cả record và offset).
* **Phương án B:** Dừng luồng ghi và xả hàng đợi (Controlled Drain & Switch - dừng checkout ngắn, chờ consumer đọc sạch lag rồi đổi endpoint).

---

### QUYẾT ĐỊNH 3: CƠ CHẾ XÁC THỰC KẾT NỐI CLIENT (AUTHENTICATION PROTOCOL)
* **Phương án A:** Sử dụng AWS IAM Authentication (Bảo mật IAM/IRSA, không mật khẩu, yêu cầu cập nhật code client).
* **Phương án B:** Sử dụng SASL/SCRAM (Username/password lưu trong Secrets Manager, tương thích ngược nhanh không cần sửa code).

---

### QUYẾT ĐỊNH 4: NGƯỠNG CẢNH BÁO ĐỘ TRỄ TIÊU THỤ (CONSUMER LAG THRESHOLD)
* **Phương án 1:** Thiết lập cảnh báo và trì hoãn cutover khi lag của consumer group vượt quá 50 messages.
* **Phương án 2:** Thiết lập cảnh báo và trì hoãn cutover khi lag của consumer group vượt quá 200 messages.

---

### QUYẾT ĐỊNH 5: RÀNG BUỘC CHỐNG TRÙNG LẶP ĐƠN HÀNG (EVENT IDEMPOTENCY)
* **Phương án A:** Bắt buộc cấu hình Idempotent Producer (`acks=all`, `enable.idempotence=true`) ở code producer và deduplication ở code consumer.
* **Phương án B:** Chỉ cấu hình phía Infrastructure (giữ nguyên code client, chỉ cấu hình tham số retry và replication factor trên cụm MSK).
