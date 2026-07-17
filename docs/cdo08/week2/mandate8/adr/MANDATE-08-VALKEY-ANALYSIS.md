# Mandate 8 - Valkey to Amazon ElastiCache Migration Analysis

Tài liệu này định nghĩa cấu trúc dữ liệu hiện tại và các hướng di trú Valkey để hội đồng Tech Leads cùng nghiên cứu và đối chiếu.

---

## 1. Hiện trạng Valkey Cart (Current State Analysis)

* **Phiên bản:** Valkey v9.0.1 (chạy dưới dạng Pod đơn lẻ `valkey-cart` trong EKS cluster).
* **Lưu trữ hiện tại:** PVC `valkey-cart-pvc` dung lượng 5 GiB, StorageClass `gp2` (mount tại `/data`). Đã bật AOF (`--appendonly yes`) để bảo vệ dữ liệu giỏ hàng.
* **Dịch vụ phụ thuộc:** `cart` service đọc/ghi thông tin giỏ hàng của người dùng. `checkout` service đọc thông tin giỏ hàng từ `cart` để tạo đơn hàng. Dữ liệu giỏ hàng có thuộc tính TTL (Time-To-Live).

---

## 2. Các Quyết định & Hướng giải quyết (Decisions & Options)

### QUYẾT ĐỊNH 1: LỰA CHỌN CHÍNH SÁCH DỮ LIỆU GIỎ HÀNG (CART DATA POLICY)
* **Phương án A:** Di trú giỏ hàng đang hoạt động (Active Cart Migration - giữ lại giỏ hàng cho các user đang online).
* **Phương án B:** Chuyển đổi lạnh (Cold Cutover / Discard Carts - xóa trắng giỏ hàng của các user đang online).

---

### QUYẾT ĐỊNH 2: CẤU HÌNH TARGET ELASTICACHE (HA, SIZING INSTANCE & REPLICAS)
* **Phương án 1:** Cấu hình 2-node Multi-AZ (`cache.t4g.micro`, 1 primary + 1 replica ở 2 AZs, tự động failover).
* **Phương án 2:** Cấu hình Single-Node (`cache.t4g.micro`, chỉ chạy duy nhất 1 node đơn lẻ).
* **Phương án 3:** Cấu hình instance lớn hơn (`cache.m7g.large` trở lên) hoặc tăng số lượng replica.

---

### QUYẾT ĐỊNH 3: LỰA CHỌN KỸ THUẬT DI TRÚ (MIGRATION TECHNIQUE)
* **Phương án A:** RDB Export & Import (Tạo snapshot RDB từ Valkey nguồn và restore lên ElastiCache).
* **Phương án B:** Application Dual-Write & SCAN Backfill (Ghi song song cả 2 nguồn, kết hợp chạy script SCAN nạp dữ liệu cũ sang đích).

---

### QUYẾT ĐỊNH 4: CHIẾN LƯỢC ROLLBACK SAU KHI CÓ DỮ LIỆU GHI MỚI
* **Phương án A:** Rollback tức thì sử dụng dữ liệu ghi nhận song song (nếu chọn phương án Dual-write).
* **Phương án B:** Quét ngược dữ liệu (Reconcile / Backfill dữ liệu mới từ ElastiCache về lại EKS Valkey cũ).
* **Phương án C:** Chấp nhận mất giỏ hàng mới (Big Bang Revert trỏ thẳng endpoint về cũ và xóa trắng giỏ hàng mới).

---

### QUYẾT ĐỊNH 5: CẢNH BÁO TRÀN BỘ NHỚ (EVICTION MANAGEMENT)
* **Phương án 1:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 80% bộ nhớ của instance.
* **Phương án 2:** Thiết lập cảnh báo ở mức 90% bộ nhớ của instance.
