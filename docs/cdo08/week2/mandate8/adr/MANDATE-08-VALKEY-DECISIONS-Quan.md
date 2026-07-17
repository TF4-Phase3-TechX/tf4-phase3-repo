# Mandate 8 - Valkey Migration Decisions & ADR Record

* **Trạng thái:** Chờ điền thông tin và ký duyệt (Draft)

Tài liệu này cung cấp khung mẫu quyết định thiết kế kiến trúc (ADR format) trống dạng bảng so sánh để cá nhân Tech Lead tự điền nghiên cứu độc lập. Khung hướng dẫn triển khai chỉ yêu cầu mô tả quy trình chung và các lưu ý phòng ngừa lỗi cho phương án được chọn ở các quyết định kỹ thuật phức tạp.

---

## QUYẾT ĐỊNH VK-01: LỰA CHỌN CHÍNH SÁCH DỮ LIỆU GIỎ HÀNG (CART DATA POLICY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Di trú giỏ hàng đang hoạt động (Active Cart Migration).
* **Phương án B:** Chuyển đổi lạnh (Cold Cutover / Discard Carts).
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-1-lựa-chọn-chính-sách-dữ-liệu-giỏ-hàng-cart-data-policy))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Ảnh hưởng Trải nghiệm Khách hàng (SLO) |
| :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá tác động tới SLO đặt hàng]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` |

---

## QUYẾT ĐỊNH VK-02: CẤU HÌNH TARGET ELASTICACHE (HA, SIZING INSTANCE & REPLICAS)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Cấu hình 2-node Multi-AZ (`cache.t4g.micro`, 1 primary + 1 replica, tự động failover).
* **Phương án 2:** Cấu hình Single-Node (`cache.t4g.micro`, chỉ chạy duy nhất 1 node đơn lẻ).
* **Phương án 3:** Cấu hình instance lớn hơn (`cache.m7g.large` trở lên) hoặc tăng số lượng replica.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-2-cấu-hình-target-elasticache-ha-vs-single-node))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Phân tích Chi phí (Cost) | Khả năng Sẵn sàng (HA) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền phân tích chi phí]` | `[Điền đánh giá khả năng failover]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[Điền chi phí so sánh]` | `[N/A]` |

---

## QUYẾT ĐỊNH VK-03: LỰA CHỌN KỸ THUẬT DI TRÚ (MIGRATION TECHNIQUE)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** RDB Export & Import.
* **Phương án B:** Application Dual-Write & SCAN Backfill.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-3-lựa-chọn-kỹ-thuật-di-trú-migration-technique))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu sửa đổi Code ứng dụng | Độ phức tạp Vận hành |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá can thiệp code]` | `[Điền đánh giá vận hành]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH VK-04: CHIẾN LƯỢC ROLLBACK SAU KHI CÓ DỮ LIỆU GHI MỚI

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Rollback tức thì sử dụng dữ liệu ghi nhận song song.
* **Phương án B:** Quét ngược dữ liệu (Reconcile / Backfill).
* **Phương án C:** Chấp nhận mất giỏ hàng mới (Big Bang Revert).
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-4-chiến-lược-rollback-sau-khi-có-dữ-liệu-ghi-mới))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Thời gian Rollback (RTO) | Mức độ mất mát dữ liệu giỏ hàng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá thời gian rollback]` | `[Điền đánh giá rủi ro mất giỏ]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH VK-05: CẢNH BÁO TRÀN BỘ NHỚ (EVICTION MANAGEMENT)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 80% bộ nhớ.
* **Phương án 2:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 90% bộ nhớ.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-5-cảnh-báo-tràn-bộ-nhớ-eviction-management))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Thời gian Phản ứng của Platform | Rủi ro mất key do Eviction |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá thời gian phản ứng]` | `[Điền đánh giá rủi ro mất giỏ]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |
