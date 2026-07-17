# Mandate 8 - PostgreSQL to Amazon RDS Migration Analysis

Tài liệu này định nghĩa cấu trúc dữ liệu hiện tại và các hướng di trú PostgreSQL để hội đồng Tech Leads cùng nghiên cứu và đối chiếu.

---

## 1. Hiện trạng PostgreSQL (Current State Analysis)

* **Phiên bản:** PostgreSQL v17.6 (chạy dưới dạng Pod đơn lẻ `postgresql` trong EKS cluster).
* **Database & Schemas:** Database chính là `otel`. Gồm 3 schemas:
  * `catalog`: Đọc bởi `product-catalog` service.
  * `reviews`: Đọc/ghi bởi `product-reviews` service.
  * `accounting`: Ghi bởi `accounting` service.
* **Lưu trữ hiện tại:** PVC `postgresql-pvc` dung lượng 10 GiB, StorageClass `gp2` (mount tại `/var/lib/postgresql/data`).
* **Bảo mật hiện tại:** Sử dụng credential dạng plain text trong Helm values; một số client chưa cấu hình TLS bắt buộc khi kết nối.

---

## 2. Các Quyết định & Hướng giải quyết (Decisions & Options)

### QUYẾT ĐỊNH 0 (QUYẾT ĐỊNH CHUNG): THỨ TỰ DI TRÚ & ĐIỀU KIỆN DỪNG KHẨN CẤP (ABORT TRIGGERS)
* **Phương án A:** 
  - Thứ tự di trú: **Valkey → Kafka/MSK → PostgreSQL** (mỗi store có change window riêng, không chạy song song).
  - Điều kiện dừng khẩn cấp (Abort & Rollback): Checkout success rate < 99% liên tục 5 phút; hoặc latency p95 > 1s; hoặc fail data parity check.
* **Phương án B:** 
  - Thứ tự di trú khác (ví dụ: PostgreSQL chạy trước).
  - Điều kiện dừng khẩn cấp nới lỏng hơn (chỉ rollback khi hệ thống bị sập hoàn toàn).

---

### QUYẾT ĐỊNH 1: LỰA CHỌN PHƯƠNG THỨC DI TRÚ (MIGRATION METHOD)
* **Phương án A.1:** Native PostgreSQL Logical Replication (Đồng bộ logic trực tiếp giữa DB-to-DB).
* **Phương án A.2:** AWS Database Migration Service (AWS DMS - CDC Task dùng máy chủ trung gian).
* **Phương án B:** Offline Dump & Restore (`pg_dump` & `pg_restore` và dừng ghi luồng ứng dụng).

---

### QUYẾT ĐỊNH 2: CẤU HÌNH TARGET RDS (SIZING INSTANCE, STORAGE & MULTI-AZ)
* **Phương án 1:** RDS Multi-AZ (`db.t4g.micro`, đĩa 20 GiB gp3, có standby instance chạy đồng bộ ở AZ khác để tự động failover).
* **Phương án 2:** RDS Single-AZ (`db.t4g.micro`, đĩa 20 GiB gp3, chỉ chạy 1 instance đơn lẻ).
* **Phương án 3:** Cấu hình instance lớn hơn (`db.t3.medium` trở lên) hoặc SSD dung lượng cao hơn.

---

### QUYẾT ĐỊNH 3: CHIẾN LƯỢC ROLLBACK SAU KHI CÓ WRITE MỚI (POST-WRITE ROLLBACK)
* **Phương án A:** Dừng ghi luồng ứng dụng, chạy script đồng bộ ngược (reverse-sync/reconcile) dữ liệu mới từ RDS về lại EKS, reset sequence, rồi mới switch endpoint về cũ.
* **Phương án B:** Chuyển đổi nhanh (Big Bang Switch-Back) trỏ thẳng endpoint về EKS cũ và chấp nhận mất dữ liệu mới ghi trên RDS.

---

### QUYẾT ĐỊNH 4: THỜI GIAN GIÁM SÁT & DỌN DẸP HẠ TẦNG CŨ (OBSERVATION WINDOW)
* **Phương án 1:** Standby 48 giờ (scale replica về 0, giữ PVC) + Archive S3 30 ngày (dump dữ liệu cất lên S3) rồi mới xóa tài nguyên cũ.
* **Phương án 2:** Xóa ngay lập tức (xóa Pod, PVC và Service cũ ngay sau khi cutover thành công).

---

### QUYẾT ĐỊNH 5: CƠ CHẾ BẢO MẬT ĐƯỜNG TRUYỀN (TLS MODE FOR CLIENTS)
* **Phương án A:** Bắt buộc sử dụng mã hóa TLS với chế độ xác thực đầy đủ chứng chỉ (`sslmode=verify-full` kèm RDS CA Bundle).
* **Phương án B:** Chỉ bật mã hóa TLS thông thường không xác thực chứng chỉ (`sslmode=require` hoặc `prefer`).

---

### QUYẾT ĐỊNH 6: PHẠM VI AN NINH MẠNG (SECURITY GROUP ACCESS SCOPE)
* **Phương án A (SG-to-SG):** Giới hạn chỉ mở inbound port 5432 cho Security Group của các client Pod (`product-catalog`, `product-reviews`, `accounting`) và migration runner (bảo mật tối đa).
* **Phương án B (Node-to-SG):** Mở rộng port 5432 cho toàn bộ dải IP/Security Group của Worker Nodes EKS.
