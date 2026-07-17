# Mandate 8 - Valkey Migration Decisions & ADR Record

* **Trạng thái:** Đã điền phân tích, chờ ký duyệt (Tech Lead: Quân)

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
| **ĐÃ CHỌN** | `B` | Cart chỉ có 1 field, luôn TTL 60 phút — bản chất là dữ liệu tạm thời. Cold cutover không cần dual-write, không sửa code `cart`, rủi ro thấp, làm nhanh — hợp deadline. Nhược: user đang có cart sẽ thấy giỏ trống, phải add lại. | Không ảnh hưởng success rate checkout. Cutover ở **low-traffic window** để giảm số user bị ảnh hưởng; cart quá TTL vốn đã tự hết hạn nên không phải "mất thêm". |
| **BỊ LOẠI BỎ** | `A` | Cần dual-write/export-import trong lúc hệ thống chạy — phức tạp, rủi ro race condition — để bảo toàn dữ liệu vốn tự hết hạn sau 1 giờ. Không tương xứng chi phí kỹ thuật. | N/A |

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
| **ĐÃ CHỌN** | `1` | Khác Kafka (async), `checkout` đọc cart **đồng bộ** qua `cart` service — Valkey chết là checkout fail ngay trên critical path. `cart` chạy 2 replicas nhưng cùng trỏ 1 Valkey — redundancy tầng app không cứu được. `t4g.micro` có 512MiB RAM, dư ~8x so với giới hạn 64Mi hiện tại. | **Verified (AWS Price List API, 2026-07-17):** `cache.t4g.micro` = $0.0160/giờ → Single-Node **$11.68/tháng**, Multi-AZ **$23.36/tháng**. Chênh chỉ **~$2.69/tuần** — quá rẻ so với việc bảo vệ 1 dependency trên critical path. Backup/cross-AZ transfer thêm không đáng kể (<$1/tuần). | Auto-failover (~vài chục giây) khi node/AZ lỗi, thay vì chờ AWS tự phục hồi single-node. |
| **BỊ LOẠI BỎ** | `2` | Rẻ nhất nhưng không có failover — 1 sự cố node là checkout ngừng hoàn toàn. Tiết kiệm ~$2.69/tuần không đáng đổi rủi ro này khi budget còn nhiều dư (baseline + cả 3 managed service ở mức cost-first ≈ $81/tuần, còn dư ~$219/tuần so với trần $300/tuần). | $11.68/tháng (verified) — rẻ hơn không đáng kể. | Không auto-failover; RTO phụ thuộc AWS, không kiểm soát được. |
| **BỊ LOẠI BỎ** | `3` | Cart chỉ dùng 32-64Mi RAM hiện tại, TTL 60p nên không tích luỹ — instance lớn hơn là over-provision không cần thiết. | Đắt hơn đáng kể, không tương xứng lợi ích. | Không cải thiện gì thêm so với Phương án 1 cho khối lượng dữ liệu này. |

---

## QUYẾT ĐỊNH VK-03: LỰA CHỌN KỸ THUẬT DI TRÚ (MIGRATION TECHNIQUE)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** RDB Export & Import.
* **Phương án B:** Application Dual-Write & SCAN Backfill.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-3-lựa-chọn-kỹ-thuật-di-trú-migration-technique))*

### 2. Phân tích & Lựa chọn của Tech Lead

> Vì VK-01 đã chọn Cold Cutover, quyết định này chỉ còn ý nghĩa **pre-flight/smoke-test**, không phải di trú cart thật.

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu sửa đổi Code ứng dụng | Độ phức tạp Vận hành |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `A` | Dump/restore thuần vận hành, không đụng code `cart` — nhất quán cold-cutover. Dùng để test connectivity trước cutover, tuỳ chọn seed vài key mẫu để smoke test. | Không cần. | Thấp — 1 lệnh dump + 1 lệnh restore, chạy 1 lần trong Job ngắn (VAP-compliant). |
| **BỊ LOẠI BỎ** | `B` | Chỉ có giá trị nếu migrate cart sống — nhưng VK-01 đã loại hướng đó. Áp dụng ở đây là over-engineering. | Có — sửa `ValkeyCartStore.cs` để ghi song song 2 nơi. | Cao — vận hành 2 backend song song, rollback phức tạp hơn. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Provision ElastiCache Multi-AZ trong private subnet, SG chỉ mở từ node SG. (2) Job pre-flight test connectivity/TLS. (3) Tuỳ chọn dump/restore để smoke test. (4) Repoint `VALKEY_ADDR` trong low-traffic window, rolling restart `cart`. (5) Cart smoke test end-to-end (add → get → checkout) qua Jaeger.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không repoint khi chưa pass pre-flight. Giữ pod/PVC `valkey-cart` cũ warm tới khi bake xong (24-48h). Cần PM/business sign-off việc mất cart tại cutover.

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
| **ĐÃ CHỌN** | `C` | Nhất quán cold-cutover — pod/PVC cũ còn giữ nên rollback chỉ là repoint env. Đơn giản, nhanh, rủi ro thấp nhất. | Rất nhanh — chỉ đổi env `VALKEY_ADDR` + rolling restart, tính bằng phút. | Cart tạo trên ElastiCache trong window cutover→rollback sẽ mất — chấp nhận được (ephemeral, đã có sign-off ở VK-01). |
| **BỊ LOẠI BỎ** | `A` | Chỉ khả thi nếu có dual-write (VK-03 đã loại phương án đó) — mâu thuẫn. | N/A | N/A |
| **BỊ LOẠI BỎ** | `B` | Khả thi kỹ thuật nhưng tốn effort SCAN/backfill không tương xứng dữ liệu ephemeral — làm rollback **chậm hơn** đúng lúc cần nhanh nhất. | Chậm hơn C. | Thấp hơn C về lý thuyết nhưng không đáng đổi thời gian rollback tăng thêm. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** Trigger khi chạm ngưỡng (checkout success < 99%, cart smoke test fail, ElastiCache lỗi kết nối): (1) repoint `VALKEY_ADDR` về `valkey-cart:6379`, (2) rollout `cart`, (3) verify smoke test lại trên Valkey cũ, (4) báo incident channel + ghi evidence.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không debug trên production — repoint ngay, điều tra sau. Giữ pod/PVC `valkey-cart` cũ tới khi bake ổn định 24-48h.

---

## QUYẾT ĐỊNH VK-05: CẢNH BÁO TRÀN BỘ NHỚ (EVICTION MANAGEMENT)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 80% bộ nhớ.
* **Phương án 2:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 90% bộ nhớ.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-5-cảnh-báo-tràn-bộ-nhớ-eviction-management))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Thời gian Phản ứng của Platform | Rủi ro mất key do Eviction |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `1` | Cache chứa cart đang hoạt động — evict sớm hơn TTL tự nhiên là mất giỏ hàng khách chưa được thông báo trước (khác việc mất cart do cutover đã có sign-off). Đổi lại nhiều cảnh báo hơn (một số false alarm khi có traffic spike). | Nhanh hơn — buffer ~20% để xử lý trước khi evict. | Thấp hơn — có thời gian scale/điều tra trước ngưỡng evict thật. |
| **BỊ LOẠI BỎ** | `2` | Ít nhiễu hơn nhưng chỉ còn ~10% buffer — với data ảnh hưởng trực tiếp khách hàng, đánh đổi này không hợp lý. | Chậm hơn. | Cao hơn — dễ evict trước khi platform kịp scale. |

---

## Ghi chú chung

* **Fact-check cost (2026-07-17):** số ElastiCache đã verify qua AWS Price List API (SKU `GUTP43BSNHYMZJ57`, `cache.t4g.micro`) — khớp ước tính ban đầu ($11.68/tháng, $23.36/tháng), không cần điều chỉnh. Backup/cross-AZ transfer bổ sung không đáng kể.
