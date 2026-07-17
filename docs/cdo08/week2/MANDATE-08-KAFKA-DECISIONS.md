# Mandate 8 - Kafka Migration Decisions & ADR Record

* **Trạng thái:** Chờ điền thông tin và ký duyệt (Draft)

Tài liệu này cung cấp khung mẫu quyết định thiết kế kiến trúc (ADR format) trống dạng bảng so sánh để cá nhân Tech Lead tự điền nghiên cứu độc lập. Khung hướng dẫn triển khai chỉ yêu cầu mô tả quy trình chung và các lưu ý phòng ngừa lỗi cho phương án được chọn (ở các quyết định KF-02, KF-03, KF-05).

---

## QUYẾT ĐỊNH KF-01: LỰA CHỌN PHƯƠNG ÁN GIẢI QUYẾT CHI PHÍ MSK (COST & SIZING OPTION)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng MSK Serverless.
* **Phương án B:** Sử dụng MSK Provisioned với Broker cỡ nhỏ.
* **Phương án C:** Trình xin văn bản Miễn trừ (Waiver / Defer Migration).
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-1-lựa-chọn-phương-án-giải-quyết-chi-phí-msk-cost--sizing-option))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Phân tích Chi phí (Cost) | Quy trình Phê duyệt (Approval Gate) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền phân tích chi phí]` | `[Điền đánh giá phê duyệt ngoại lệ]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[Điền chi phí so sánh]` | `[N/A]` |

---

## QUYẾT ĐỊNH KF-02: LỰA CHỌN PHƯƠNG THỨC DI TRÚ KAFKA (MIGRATION METHOD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng công cụ đồng bộ MirrorMaker 2 hoặc MSK Replicator.
* **Phương án B:** Dừng luồng ghi và xả hàng đợi (Controlled Drain & Switch).
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-2-lựa-chọn-phương-thức-di-trú-kafka-migration-method))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu Công cụ bổ sung | Ảnh hưởng Downtime storefront |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá phát sinh công cụ]` | `[Điền đánh giá downtime checkout]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH KF-03: CƠ CHẾ XÁC THỰC KẾT NỐI CLIENT (AUTHENTICATION PROTOCOL)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng AWS IAM Authentication.
* **Phương án B:** Sử dụng SASL/SCRAM.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-3-cơ-chế-xác-thực-kết-nối-client-authentication-protocol))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu chỉnh sửa Code Client | Độ phức tạp cấu hình Infra |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá sửa code client]` | `[Điền đánh giá cấu hình secrets/KMS]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`

---

## QUYẾT ĐỊNH KF-04: NGƯỠNG CẢNH BÁO ĐỘ TRỄ TIÊU THỤ (CONSUMER LAG THRESHOLD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo khi lag của consumer group vượt quá 50 messages.
* **Phương án 2:** Thiết lập cảnh báo khi lag của consumer group vượt quá 200 messages.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-4-ngưỡng-cảnh-báo-độ-trễ-tiêu-thụ-consumer-lag-threshold))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Tốc độ phát hiện lỗi nghẽn | Rủi ro báo động giả (False Alarm) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá tốc độ cảnh báo]` | `[Điền đánh giá tần suất báo giả]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

---

## QUYẾT ĐỊNH KF-05: RÀNG BUỘC CHỐNG TRÙNG LẶP ĐƠN HÀNG (EVENT IDEMPOTENCY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Bắt buộc cấu hình Idempotent Producer và deduplication ở consumer.
* **Phương án B:** Chỉ cấu hình phía Infrastructure.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-5-ràng-buộc-chống-trùng-lặp-đơn-hàng-event-idempotency))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Bảo vệ tính toàn vẹn giao dịch | Yêu cầu sửa đổi Code ứng dụng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `[ ]` | `[Điền phân tích lý do chọn, các mặt lợi/hại]` | `[Điền đánh giá mức độ an toàn]` | `[Điền đánh giá công sức sửa code]` |
| **BỊ LOẠI BỎ** | `[ ]` | `[Điền phân tích lý do loại bỏ]` | `[N/A]` | `[N/A]` |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** `[Tech Lead mô tả quy trình các bước thực hiện ở mức tổng quan]`
* **Lưu ý & Biện pháp phòng ngừa lỗi:** `[Tech Lead nêu các lưu ý quan trọng để tránh lỗi trong quá trình thực hiện]`
