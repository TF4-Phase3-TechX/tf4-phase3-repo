# Mandate 8 - PostgreSQL Migration Decisions & ADR Record

* **Trạng thái:** Chờ điền thông tin và ký duyệt (Draft)

Tài liệu này là bản ghi nhận các quyết định thiết kế kiến trúc (ADR) dạng bảng dành cho cá nhân Tech Lead điền phân tích độc lập. Khung hướng dẫn triển khai chỉ yêu cầu mô tả quy trình chung và các lưu ý phòng ngừa lỗi cho phương án được chọn ở các quyết định kỹ thuật phức tạp.

---

## QUYẾT ĐỊNH PG-00 (QUYẾT ĐỊNH CHUNG): THỨ TỰ DI TRÚ & ĐIỀU KIỆN DỪNG KHẨN CẤP (ABORT TRIGGERS)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** 
  - Thứ tự di trú: **Valkey → Kafka/MSK → PostgreSQL** (mỗi store có change window riêng, không chạy song song).
  - Điều kiện dừng khẩn cấp (Abort & Rollback): Checkout success rate < 99% liên tục 5 phút; hoặc latency p95 > 1s; hoặc fail data parity check (schema/row/checksum/sequence/offsets).
* **Phương án B:** 
  - Thứ tự di trú khác (ví dụ di trú PostgreSQL đầu tiên).
  - Điều kiện dừng khẩn cấp nới lỏng hơn (chỉ rollback khi hệ thống bị sập hoàn toàn).
*(Chi tiết mô tả xem tại [CDO08-REL-13-managed-data-migration-plan.md](./CDO08-REL-13-managed-data-migration-plan.md#7-cutover-slo-v%C3%A0-%C4%91i%E1%BB%81u-ki%E1%BB%87n-d%E1%BB%ABng))*

### 2. Phân tích & Lựa chọn của Tech Lead

*(Quyết định này không phát sinh chi phí trực tiếp nên cột Chi phí được lược bỏ)*

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Khả năng kiểm soát rủi ro SLO | Mức độ phức tạp điều phối |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá an toàn SLO]` | `[Điền đánh giá độ phức tạp]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

---

## QUYẾT ĐỊNH PG-01: LỰA CHỌN PHƯƠNG THỨC DI TRÚ (MIGRATION METHOD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A.1:** Native PostgreSQL Logical Replication.
* **Phương án A.2:** AWS Database Migration Service (AWS DMS).
* **Phương án B:** Offline Dump & Restore.
*(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-1-lựa-chọn-phương-thức-di-trú-migration-method))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Phân tích Chi phí (Cost) | Độ phức tạp Triển khai |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền phân tích chi phí]` | `[Điền đánh giá độ phức tạp]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[Điền chi phí so sánh]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH PG-02: CẤU HÌNH TARGET RDS (SIZING INSTANCE, STORAGE & MULTI-AZ)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** RDS Multi-AZ (`db.t4g.micro`, đĩa 20 GiB gp3, có standby instance chạy đồng bộ ở AZ khác).
* **Phương án 2:** RDS Single-AZ (`db.t4g.micro`, đĩa 20 GiB gp3, chỉ chạy 1 instance đơn lẻ).
* **Phương án 3:** Cấu hình instance lớn hơn (`db.t3.medium` trở lên) hoặc SSD dung lượng cao hơn.
*(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-2-cấu-hình-target-rds-multi-az-vs-single-az))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Phân tích Chi phí (Cost) | Khả năng tự động phục hồi (RTO/RPO) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền phân tích chi phí]` | `[Điền đánh giá thời gian phục hồi]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[Điền chi phí so sánh]` | `[N/A]` |

---

## QUYẾT ĐỊNH PG-03: CHIẾN LƯỢC ROLLBACK SAU KHI CÓ WRITE MỚI (POST-WRITE ROLLBACK)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Dừng ghi luồng ứng dụng và Đồng bộ ngược (Reverse-Sync & Reconcile).
* **Phương án B:** Chuyển đổi nhanh (Big Bang Switch-Back).
*(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-3-chiến-lược-rollback-sau-khi-có-write-mới-post-write-rollback))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Rủi ro Vận hành | RPO & Ảnh hưởng dữ liệu khách hàng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá rủi ro vận hành]` | `[Điền đánh giá mức độ mất dữ liệu khách]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[Điền đánh giá rủi ro vận hành]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH PG-04: THỜI GIAN GIÁM SÁT & DỌN DẸP HẠ TẦNG CŨ (OBSERVATION WINDOW)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Standby 48 giờ + Archive S3 30 ngày.
* **Phương án 2:** Xóa ngay lập tức (Immediate Cleanup).
*(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-4-thời-gian-giám-sát--dọn-dẹp-hạ-tầng-cũ-observation-window))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Quy trình dọn dẹp (Cleanup Runbook) | Khả năng khôi phục khẩn cấp |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá tính đơn giản của runbook]` | `[Điền đánh giá khả năng recovery]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[Điền đánh giá tính đơn giản của runbook]` | `[N/A]` |

---

## QUYẾT ĐỊNH PG-05: CƠ CHẾ BẢO MẬT ĐƯỜNG TRUYỀN (TLS MODE FOR CLIENTS)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** TLS Verify-Full (`sslmode=verify-full`).
* **Phương án B:** TLS Prefer/Require (`sslmode=require` hoặc `prefer`).
*(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-5-cơ-chế-bảo-mật-đường-truyền-tls-mode-for-clients))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Độ phức tạp cấu hình Client ứng dụng |
| :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá công việc ở client]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH PG-06: PHẠM VI AN NINH MẠNG (SECURITY GROUP ACCESS SCOPE)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A (SG-to-SG):** Giới hạn chỉ mở inbound port 5432 cho chính xác Security Group của các client Pod (`product-catalog`, `product-reviews`, `accounting`) và migration runner.
* **Phương án B (Node-to-SG):** Mở rộng port 5432 cho toàn bộ dải IP/Security Group của Worker Nodes EKS.
*(Chi tiết mô tả xem tại [CDO08-REL-13-managed-data-migration-plan.md](./CDO08-REL-13-managed-data-migration-plan.md#41-network))*

### 2. Phân tích & Lựa chọn của Tech Lead

*(Quyết định này không phát sinh chi phí hạ tầng nên cột Chi phí được lược bỏ)*

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Mức độ kiểm soát an ninh (Least Privilege) | Độ phức tạp quản lý Terraform |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá độ an toàn bảo mật]` | `[Điền đánh giá độ phức tạp IaC]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |
