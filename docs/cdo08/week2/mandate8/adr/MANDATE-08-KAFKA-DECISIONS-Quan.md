# Mandate 8 - Kafka Migration Decisions & ADR Record

* **Trạng thái:** Đã điền phân tích, chờ ký duyệt (Tech Lead: Quân)

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
| **ĐÃ CHỌN** | `B` | Chỉ 1 topic `orders`, throughput thấp — không cần auto-scale của Serverless. 2 broker `kafka.t3.small`, RF=2 (tăng từ RF=1) là cân bằng hợp lý giữa cải thiện HA và chi phí. | **Verified (AWS Price List API, 2026-07-17):** `kafka.t3.small` = $0.0456/broker-giờ, storage $0.10/GB-tháng → **$68.6-70.6/tháng (~$15.8-16.3/tuần)**. Số này **cao hơn ~10-13%** so với ước tính cũ kế thừa từ REL-03 (`$61.04/tháng`, không có nguồn AWS Pricing backing). Vẫn là cấu phần đắt nhất của migration, trong trần $300/tuần. **Worst-case:** `t3.small` là burstable (CPU credit) — nếu cạn credit dưới traffic thật, đường nâng cấp là `kafka.m7g.large` ($0.204/giờ) → **~$298/tháng (~$68.6/tuần), gấp ~4.3 lần**. | **Bắt buộc CDO04 duyệt riêng** — reopen chỗ CDO04 từng defer MSK ở REL-03. Cần hỏi CDO04: (1) trần $300/tuần có nới cho Directive #8 không, (2) nếu vượt duyệt thì escalate BTC (Mandate 8 bắt buộc, không tự chọn defer), (3) chấp nhận ngưỡng escalation lên `m7g.large` nếu t3.small cạn credit. |
| **BỊ LOẠI BỎ** | `A` | Tự động co giãn, không cần quản lý broker — nhưng vỡ budget cho workload nhỏ. | Verified: $0.75/giờ base = $547.50/tháng + partition-hour/data/storage → **~$550-560/tháng (~$127-129/tuần)** — ~8x Provisioned. | Cần xin duyệt ngân sách ngoại lệ lớn — không có cơ sở khi Provisioned đã đủ đáp ứng với chi phí thấp hơn nhiều. |
| **BỊ LOẠI BỎ** | `C` | Từng hợp lý ở REL-03, nhưng Directive #8 hiện **bắt buộc** migrate — defer riêng Kafka là vi phạm mandate. | Rẻ nhất (~free) nhưng đi ngược yêu cầu directive. | Chỉ hợp lệ nếu có văn bản miễn trừ từ BTC — không phải quy trình duyệt qua CDO04 thông thường. |

---

## QUYẾT ĐỊNH KF-02: LỰA CHỌN PHƯƠNG THỨC DI TRÚ KAFKA (MIGRATION METHOD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng công cụ đồng bộ MirrorMaker 2 hoặc MSK Replicator.
* **Phương án B:** Dừng luồng ghi và xả hàng đợi (Controlled Drain & Switch).
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-2-lựa-chọn-phương-thức-di-trú-kafka-migration-method))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu Công cụ bổ sung | Ảnh hưởng Downtime storefront |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `B` | 1 topic, throughput thấp, producer đã fire-and-forget (async, không chờ ack) — drain-to-lag-0 rồi repoint là đủ an toàn, không cần replicator phức tạp. | Không cần — chỉ dùng lệnh Kafka admin có sẵn. | Gần như bằng 0 với checkout (producer không block); chỉ trễ downstream (accounting/fraud) vài giây. |
| **BỊ LOẠI BỎ** | `A` | Zero-downtime lý thuyết, nhưng overkill cho 1 topic nhỏ — thêm thành phần vận hành 24/7 không đáng cho lợi ích không đáng kể so với B. | Cần triển khai + vận hành MirrorMaker 2/MSK Replicator. | Zero-downtime, nhưng không có ý nghĩa thực tế khi B đã gần 0 downtime. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Provision MSK, tạo topic `orders`. (2) Job pre-flight test connectivity/TLS. (3) Drain: `accounting`+`fraud-detection` đọc lag về 0 trên broker cũ. (4) Repoint 2 consumer sang MSK trước (topic rỗng, vô hại) → repoint producer `checkout` sau. (5) Verify lag broker cũ vẫn = 0 (không straggler). (6) Repoint init container + otel-collector. (7) Publish test order, verify cả 2 consumer nhận đúng 1 lần.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không repoint producer trước consumer. Giữ broker cũ warm tới khi bake ổn định. Tạm nâng `RequiredAcks` lên `WaitForAll` trong window cutover (xem KF-05).

---

## QUYẾT ĐỊNH KF-03: CƠ CHẾ XÁC THỰC KẾT NỐI CLIENT (AUTHENTICATION PROTOCOL)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng AWS IAM Authentication.
* **Phương án B:** Sử dụng SASL/SCRAM.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-3-cơ-chế-xác-thực-kết-nối-client-authentication-protocol))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu chỉnh sửa Code Client | Độ phức tạp cấu hình Infra |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `B` | 3 client 3 ngôn ngữ khác nhau (Go, C#, Kotlin) — SASL/SCRAM hỗ trợ native cả 3, không cần thư viện IAM-signer riêng. Tận dụng ESO/Secrets Manager có sẵn (`techx/tf4/*`) — triển khai nhanh hơn, hợp deadline. | Trung bình — chỉ đổi config bootstrap + `SASL_SSL`, không restructure code. | Trung bình — tạo Secret + `ExternalSecret` (tái dùng ESO), không cần IAM policy riêng cho từng client. |
| **BỊ LOẠI BỎ** | `A` | Lợi thế dài hạn (không rotate password) nhưng cần thư viện IAM-signer riêng cho **cả 3 ngôn ngữ** — rủi ro tiến độ khi deadline sát. Ghi nhận là hướng nâng cấp tương lai. | Cao — thư viện riêng biệt cho 3 ngôn ngữ, test tương thích từng client. | Thấp hơn lâu dài, cao hơn lúc triển khai ban đầu. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Sinh username/password, lưu Secrets Manager `techx/tf4/msk`. (2) Thuỷ tạo `ExternalSecret` (tái dùng ESO có sẵn). (3) Cấu hình MSK liên kết SASL/SCRAM user với Secret. (4) Cập nhật 3 client dùng `secretKeyRef` + `SASL_SSL`. (5) Test connectivity qua Job pre-flight.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không hardcode username/password trong `values.yaml`. Test riêng từng client trước cutover (cấu hình SASL khác nhau giữa sarama/Confluent/Kotlin).

---

## QUYẾT ĐỊNH KF-04: NGƯỠNG CẢNH BÁO ĐỘ TRỄ TIÊU THỤ (CONSUMER LAG THRESHOLD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo khi lag của consumer group vượt quá 50 messages.
* **Phương án 2:** Thiết lập cảnh báo khi lag của consumer group vượt quá 200 messages.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-4-ngưỡng-cảnh-báo-độ-trễ-tiêu-thụ-consumer-lag-threshold))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Tốc độ phát hiện lỗi nghẽn | Rủi ro báo động giả (False Alarm) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `1` | `accounting` (audit-trail tài chính) và `fraud-detection` (cần phát hiện sớm) đều nhạy cảm thời gian — ngưỡng thấp phát hiện nghẽn sớm, tối đa thời gian phản ứng. Có thể tune thêm evaluation window để giảm false alarm sau. | Nhanh — phát hiện tụt hậu gần như ngay lập tức. | Cao hơn Phương án 2, nhưng giảm được bằng điều kiện "duration" khi implement alert. |
| **BỊ LOẠI BỎ** | `2` | Ít nhiễu hơn nhưng cho phép backlog tích tới 200 msg trước khi có tín hiệu — rủi ro nghiệp vụ (tài chính/fraud) lớn hơn lợi ích giảm nhiễu. | Chậm hơn. | Thấp hơn, nhưng không tương xứng với mức nhạy cảm của 2 consumer này. |

---

## QUYẾT ĐỊNH KF-05: RÀNG BUỘC CHỐNG TRÙNG LẶP ĐƠN HÀNG (EVENT IDEMPOTENCY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Bắt buộc cấu hình Idempotent Producer và deduplication ở consumer.
* **Phương án B:** Chỉ cấu hình phía Infrastructure.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-5-ràng-buộc-chống-trùng-lặp-đơn-hàng-event-idempotency))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Bảo vệ tính toàn vẹn giao dịch | Yêu cầu sửa đổi Code ứng dụng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `A` | Topic `orders` feed trực tiếp audit-trail tài chính — event trùng = ghi đơn 2 lần trong sổ sách. Producer hiện có sẵn điểm yếu (`NoResponse`, fire-and-forget) — migration là lúc tự nhiên để đóng luôn lỗ hổng này. Cần sửa code cả producer + 2 consumer, nhưng tương xứng rủi ro tài chính. | Cao — idempotent producer + dedup theo `OrderId` ở consumer = 2 lớp bảo vệ. | Trung bình-cao — đổi acks ở producer (Go), thêm dedup ở 2 consumer (C#, Kotlin). |
| **BỊ LOẠI BỎ** | `B` | Nhanh hơn (chỉ đổi tham số infra) nhưng không loại được risk trùng lặp do retry/rebalance — để lại lỗ hổng correctness cho đúng luồng dữ liệu tài chính. | Thấp hơn — vẫn có khả năng trùng dưới retry/rebalance. | Thấp — không sửa code, nhưng chấp nhận rủi ro correctness còn tồn đọng. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Producer `checkout`: đổi `NoResponse` → `acks=all` + bật idempotence. (2) Consumer `accounting`: check `OrderId` đã xử lý trước khi ghi DB. (3) Consumer `fraud-detection`: dedup theo `OrderId`. (4) Test bằng cách publish trùng 1 `OrderId`, verify chỉ xử lý 1 lần ở cả 2 consumer.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Đây là thay đổi code ứng dụng — cần review riêng với Nguyên trước khi merge. Phối hợp chặt với KF-02 (drain & switch) để chống trùng ở đúng thời điểm chuyển tiếp.

---

## Ghi chú chung

* Context kỹ thuật tham chiếu trực tiếp `techx-corp-chart/values.yaml` (Kafka KRaft single-broker, topic `orders`, `RequiredAcks=NoResponse`, 2 consumer group `accounting`/`fraud-detection`) và `infra/terraform/*.tf` (VPC, EKS 1.34).
* KF-01, KF-03 phụ thuộc quyết định CDO04 (cost) và Thuỷ (secret path).
* KF-02, KF-05 phối hợp với thứ tự cutover chung (Valkey → PostgreSQL → Kafka đề xuất) để đảm bảo checkout SLO ≥ 99%.
* **Fact-check cost (2026-07-17):** số MSK ở KF-01 đã verify qua AWS Price List API, không dùng số kế thừa từ REL-03. Lưu ý: `docs/audit/adr/004-in-cluster-datastores-week1-baseline.md` ước tính MSK ~$50-100/tuần — cao hơn 3-6 lần số verified, không có nguồn Pricing backing, nên coi là placeholder cũ, không dùng để quyết định approve/reject.
