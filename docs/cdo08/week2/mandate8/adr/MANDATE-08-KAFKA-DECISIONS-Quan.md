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
| **ĐÃ CHỌN** | `B` | Provisioned với broker nhỏ (`kafka.t3.small` × 2, 1 broker/AZ, RF=2 tăng từ RF=1 hiện tại) đáp ứng đúng workload thực tế: **chỉ 1 topic `orders`**, throughput thấp (order event, không phải high-frequency stream). Không cần auto-scale linh hoạt như Serverless vì traffic pattern ổn định, dễ dự đoán. RF=2 (thay vì 3-broker RF=3 tốn hơn) là cân bằng hợp lý: cải thiện so với RF=1 in-cluster hiện tại mà không tốn kém như cấu hình full-HA. | **~$61-67/tháng (~$14-15/tuần)** — đây là **cấu phần đắt nhất** trong toàn bộ migration (chiếm ~70% phần chi phí tăng thêm so với baseline hiện tại `~$56.83/tuần`). Vẫn nằm trong trần `$300/tuần` (tổng sau migration ước tính ~`$77/tuần`, ~26% budget) nhưng là dòng chi phí cần giải trình rõ nhất với CDO04. | **Bắt buộc CDO04 duyệt riêng** trước khi provision — đây là quyết định reopen lại chỗ CDO04 từng defer MSK ở REL-03 (`docs/cdo08/week2/mandate3/review-requests/REVIEW-REQUEST-CDO04-COST-REL03-HA-OPTIONS.md`). Cần làm rõ với CDO04: (1) trần `$300/tuần` có được nới cho Directive #8 không (BUDGET.md cho phép BTC nới khi ban hành directive lớn bắt buộc migration), (2) nếu MSK vượt duyệt thì escalate BTC vì Mandate 8 là bắt buộc — không thể tự ý chọn Phương án C. |
| **BỊ LOẠI BỎ** | `A` | MSK Serverless có ưu điểm auto-scale, không cần quản lý broker/capacity — nhưng **base cost ~$0.75/giờ/cluster ≈ $540/tháng (~$124/tuần)** chỉ riêng phí nền, chưa tính usage — vỡ hoàn toàn trần `$300/tuần` cho một workload chỉ 1 topic, throughput thấp. Trả tiền cho khả năng co giãn mà hệ thống hiện tại không cần. | Đắt hơn Provisioned nhiều lần cho cùng workload — không hợp lý về mặt cost-efficiency (nguyên tắc chấm điểm theo BUDGET.md). | Sẽ cần xin duyệt ngân sách ngoại lệ lớn — không có cơ sở hợp lý để trình khi Provisioned đã đáp ứng đủ nhu cầu với chi phí thấp hơn nhiều. |
| **BỊ LOẠI BỎ** | `C` | Waiver/Defer từng là hướng đi hợp lý ở REL-03 (khi managed service chưa bắt buộc) nhưng Directive #8 (Mandate 8) hiện **bắt buộc** migrate toàn bộ data layer, deadline 2026-07-20 — defer Kafka riêng lẻ là vi phạm mandate, không phải quyết định Tech Lead có thể tự chọn nếu không có ngoại lệ từ BTC. | Rẻ nhất (giữ nguyên ~free in-cluster) nhưng đi ngược trực tiếp yêu cầu của directive. | Chỉ hợp lệ nếu có **văn bản miễn trừ từ BTC** — không phải quy trình phê duyệt thông thường qua CDO04; đây là lựa chọn "escalate", không phải lựa chọn mặc định. |

---

## QUYẾT ĐỊNH KF-02: LỰA CHỌN PHƯƠNG THỨC DI TRÚ KAFKA (MIGRATION METHOD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng công cụ đồng bộ MirrorMaker 2 hoặc MSK Replicator.
* **Phương án B:** Dừng luồng ghi và xả hàng đợi (Controlled Drain & Switch).
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-2-lựa-chọn-phương-thức-di-trú-kafka-migration-method))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu Công cụ bổ sung | Ảnh hưởng Downtime storefront |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `B` | Với **1 topic duy nhất (`orders`)**, throughput thấp, producer đã là fire-and-forget (`RequiredAcks=NoResponse`) và cả 2 consumer group (`accounting`, `fraud-detection`) đều dùng `AutoOffsetReset=Earliest` — drain-to-lag-0 rồi repoint là đủ đơn giản và an toàn, không cần công cụ đồng bộ phức tạp cho khối lượng dữ liệu nhỏ này. Vì producer là **async, không block user response** trên checkout, cửa sổ drain hầu như không ảnh hưởng tới trải nghiệm khách hàng thấy được — chỉ trễ downstream (accounting/fraud) trong vài giây. | Không cần công cụ mới — chỉ dùng lệnh Kafka admin có sẵn (tạo topic, kiểm tra consumer lag) và thao tác repoint env value, giảm bề mặt rủi ro/vận hành so với vận hành thêm 1 replicator 24/7. | **Gần như bằng 0** đối với response time checkout (producer không chờ ack) — cửa sổ downtime thực chất chỉ là khoảng trễ ngắn trong xử lý downstream (accounting ghi order vào RDS, fraud-detection quét gian lận), không phải lỗi hiển thị cho khách hàng. |
| **BỊ LOẠI BỎ** | `A` | MirrorMaker 2/MSK Replicator cho phép cutover gần như zero-downtime kèm bảo toàn offset — nhưng đây là năng lực dành cho migration nhiều topic/traffic cao, không tương xứng với 1 topic đơn giản, throughput thấp của hệ thống này. Thêm 1 thành phần vận hành 24/7 (dù chỉ chạy tạm trong window migrate) làm tăng bề mặt lỗi (replicator lag, cấu hình offset mapping) mà lợi ích thu được (giảm downtime vốn đã gần 0 với phương án B) là không đáng kể. | Cần triển khai + vận hành MirrorMaker 2/MSK Replicator — thành phần hạ tầng mới, tốn thời gian setup không cần thiết cho quy mô dữ liệu này. | Zero-downtime lý thuyết, nhưng lợi ích này không có ý nghĩa thực tế khi Phương án B vốn đã gần như 0 downtime do bản chất async của producer. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Provision MSK (2 broker `kafka.t3.small`, RF=2) trong private subnet, security group chỉ mở từ EKS node SG. (2) Tạo topic `orders` trên MSK (partition/RF theo cấu hình đã duyệt). (3) Job pre-flight (VAP-compliant) test connectivity/auth/TLS từ `techx-tf4`. (4) **Drain:** để `accounting` + `fraud-detection` đọc lag về 0 trên broker in-cluster. (5) **Flip đồng bộ theo thứ tự:** repoint 2 consumer group sang MSK trước (idle trên topic rỗng, vô hại) → repoint producer `checkout` sau. (6) Verify lag group cũ trên broker in-cluster vẫn = 0 sau flip (không có straggler kẹt giữa 2 bước) — nếu có, replay sang MSK. (7) Repoint `wait-for-kafka` init container + otel-collector `kafkametrics` receiver sang MSK bootstrap. (8) Publish test order, verify cả 2 consumer group nhận đúng 1 lần.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không repoint producer trước consumer (tránh event bị "mất" vào MSK trong lúc consumer vẫn đọc broker cũ). Giữ broker in-cluster + `kafka-pvc` **warm** (đã có `resource-policy: keep`) cho tới khi bake ổn định. Tạm nâng `RequiredAcks` từ `NoResponse` lên `WaitForLocal`/`WaitForAll` **trong window cutover** để giảm rủi ro rớt event khi broker có hiccup lúc chuyển tiếp (xem thêm KF-05).

---

## QUYẾT ĐỊNH KF-03: CƠ CHẾ XÁC THỰC KẾT NỐI CLIENT (AUTHENTICATION PROTOCOL)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng AWS IAM Authentication.
* **Phương án B:** Sử dụng SASL/SCRAM.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-3-cơ-chế-xác-thực-kết-nối-client-authentication-protocol))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu chỉnh sửa Code Client | Độ phức tạp cấu hình Infra |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `B` | 3 client hiện tại thuộc **3 ngôn ngữ khác nhau** (`checkout` Go/sarama, `accounting` C#/Confluent, `fraud-detection` Kotlin/JVM) — SASL/SCRAM (username/password) là cơ chế chuẩn được cả 3 stack hỗ trợ **native**, không cần thư viện IAM-signer riêng cho từng ngôn ngữ. Việc này tận dụng được path Secrets Manager + ESO **đã có sẵn** trong repo (IRSA `external-secrets-read-production`, convention `techx/tf4/*`) để lưu username/password, triển khai nhanh hơn — phù hợp deadline Mandate 8 sát (2026-07-20). | Trung bình — chỉ cần đổi config bootstrap + bật `SASL_SSL` với username/password từ Secret (`secretKeyRef`), không cần restructure code hay thêm dependency mới cho cả 3 service. | Trung bình — tạo Secret `techx/tf4/msk` (username/password) + `ExternalSecret` (tái dùng ESO có sẵn), cấu hình SASL/SCRAM user trên MSK qua Secrets Manager association — không cần cấu hình IAM policy/role phức tạp cho từng client. |
| **BỊ LOẠI BỎ** | `A` | AWS IAM Auth (qua IRSA) có lợi thế dài hạn: không password để xoay vòng/rotate, tận dụng identity EKS sẵn có. Tuy nhiên đòi hỏi **cả 3 client phải hỗ trợ SASL/IAM signer** — với Go (sarama) cần thư viện cộng đồng `aws-msk-iam-sasl-signer-go`, .NET/Confluent và Kotlin/JVM cũng cần thư viện/plugin riêng biệt — phối hợp nâng cấp 3 codebase khác ngôn ngữ trong thời gian ngắn là rủi ro tiến độ không cần thiết khi SASL/SCRAM đã đủ đáp ứng yêu cầu bảo mật (mã hoá + xác thực) của Mandate 8. Ghi nhận là hướng nâng cấp tương lai sau khi đã verify tương thích thư viện IAM cho cả 3 ngôn ngữ. | Cao — phải thêm/point tới thư viện IAM-signer riêng biệt cho **3 ngôn ngữ khác nhau**, test tương thích từng client trước khi go-live. | Thấp hơn về vận hành lâu dài (không cần rotate secret) nhưng cao hơn ở giai đoạn triển khai ban đầu (thiết lập IAM policy/role cho từng client qua IRSA). |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Sinh username/password cho MSK SASL/SCRAM, lưu vào AWS Secrets Manager path `techx/tf4/msk`. (2) Thuỷ (SEC-13¹, cần renumber — xem ghi chú) tạo `ExternalSecret` tái dùng `ClusterSecretStore aws-secretsmanager` sẵn có → sinh K8s Secret. (3) Cấu hình MSK cluster liên kết user SASL/SCRAM với Secret trên. (4) Cập nhật config 3 client (`checkout`, `accounting`, `fraud-detection`) dùng `secretKeyRef` cho username/password + bật `security.protocol=SASL_SSL`. (5) Test connectivity qua Job pre-flight trước khi go-live.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không hardcode username/password trong `values.yaml` (lặp lại lỗi hiện tại của Postgres `otelu/otelp`) — bắt buộc qua Secret. Test riêng từng client trước cutover thật vì mỗi ngôn ngữ có cách cấu hình SASL hơi khác nhau (sarama config khác Confluent .NET khác Kotlin).

---

## QUYẾT ĐỊNH KF-04: NGƯỠNG CẢNH BÁO ĐỘ TRỄ TIÊU THỤ (CONSUMER LAG THRESHOLD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo khi lag của consumer group vượt quá 50 messages.
* **Phương án 2:** Thiết lập cảnh báo khi lag của consumer group vượt quá 200 messages.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-4-ngưỡng-cảnh-báo-độ-trễ-tiêu-thụ-consumer-lag-threshold))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Tốc độ phát hiện lỗi nghẽn | Rủi ro báo động giả (False Alarm) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `1` | Cả 2 consumer group đều gắn với nghiệp vụ nhạy cảm thời gian: `accounting` ghi audit-trail đơn hàng vào RDS (bị trễ = báo cáo tài chính lệch pha), `fraud-detection` cần phát hiện gian lận **sớm** để có tác dụng. Ngưỡng thấp (50) giúp phát hiện consumer bị nghẽn/chậm gần như ngay khi mới bắt đầu tích lag, tối đa hoá thời gian phản ứng trước khi backlog lớn dần. Đánh đổi: nhạy hơn với traffic burst tự nhiên (vd Locust load-generator test) có thể gây một số false alarm — chấp nhận được vì có thể tune thêm evaluation window (vd cảnh báo chỉ khi vượt ngưỡng liên tục N phút) ở bước cấu hình alert cụ thể sau này. | Nhanh — phát hiện consumer group bắt đầu tụt hậu gần như ngay lập tức, tối đa thời gian platform phản ứng trước khi ảnh hưởng tới độ chính xác/độ trễ của accounting và fraud-detection. | Cao hơn Phương án 2 — có thể trigger trong các đợt traffic spike hợp lệ ngắn hạn; giảm thiểu bằng cách thêm điều kiện "duration" (lag > 50 **liên tục** trong X phút) khi implement alert rule thay vì chỉ threshold tức thời. |
| **BỊ LOẠI BỎ** | `2` | Giảm nhiễu cảnh báo cho platform team, nhưng cho phép backlog tích tới 200 message trước khi có tín hiệu — với `accounting` (audit-trail tài chính) và `fraud-detection` (cần phản ứng nhanh), một backlog lớn không được phát hiện sớm là rủi ro nghiệp vụ lớn hơn lợi ích giảm nhiễu cảnh báo mang lại. | Chậm hơn — độ trễ phát hiện lớn hơn, backlog có thể đã tích luỹ đáng kể trước khi có cảnh báo. | Thấp hơn Phương án 1, nhưng đánh đổi này không tương xứng khi 2 consumer đều là nghiệp vụ nhạy cảm thời gian/tài chính. |

---

## QUYẾT ĐỊNH KF-05: RÀNG BUỘC CHỐNG TRÙNG LẶP ĐƠN HÀNG (EVENT IDEMPOTENCY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Bắt buộc cấu hình Idempotent Producer và deduplication ở consumer.
* **Phương án B:** Chỉ cấu hình phía Infrastructure.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-5-ràng-buộc-chống-trùng-lặp-đơn-hàng-event-idempotency))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Bảo vệ tính toàn vẹn giao dịch | Yêu cầu sửa đổi Code ứng dụng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `A` | Topic `orders` là nguồn dữ liệu đầu vào trực tiếp cho **audit-trail tài chính** (`accounting` ghi order/orderitem/shipping vào RDS) — event trùng lặp đồng nghĩa **ghi đơn hàng 2 lần** trong sổ sách kế toán, một lỗi nghiêm trọng hơn nhiều so với mất mát nhỏ ở cart (Valkey). Producer hiện tại đã có điểm yếu sẵn có (`RequiredAcks=NoResponse`, fire-and-forget) — migration sang MSK là thời điểm tự nhiên để đóng luôn lỗ hổng durability này song song với việc tăng bảo vệ chống trùng lặp, thay vì mang nguyên rủi ro cũ sang hạ tầng mới. Đánh đổi: cần sửa code ở cả producer (Go) và 2 consumer (C#, Kotlin) — effort thật nhưng tương xứng với rủi ro tài chính. | Cao — `enable.idempotence=true` + `acks=all` ở producer loại bỏ trùng lặp do retry ở tầng broker; dedup theo `OrderId` (khoá tự nhiên có sẵn trong `OrderResult`) ở tầng consumer loại bỏ thêm rủi ro trùng lặp do consumer rebalance/reprocess — bảo vệ 2 lớp cho 1 luồng dữ liệu tài chính. | Trung bình-cao — đổi cấu hình producer (`checkout`/Go, bỏ `NoResponse` → `acks=all` + bật idempotence) và thêm logic dedup theo `OrderId` ở 2 consumer (`accounting`/C#, `fraud-detection`/Kotlin). Effort thật nhưng đóng đồng thời 2 vấn đề: nợ kỹ thuật cũ (fire-and-forget) + yêu cầu mới (chống trùng khi migrate). |
| **BỊ LOẠI BỎ** | `B` | Nhanh hơn để triển khai (chỉ chỉnh retry/replication factor ở cụm MSK, không đụng code) nhưng **không loại bỏ** rủi ro trùng lặp ở tầng producer/consumer — retry ở mức infra dưới cơ chế at-least-once vẫn có thể sinh event trùng khi producer retry mà không idempotent, hoặc consumer restart/rebalance đọc lại message chưa commit offset. Để lại lỗ hổng correctness cho đúng luồng dữ liệu nhạy cảm nhất (tài chính) chỉ để tiết kiệm effort code — đánh đổi không hợp lý so với cart (Valkey), nơi rủi ro tương tự có thể chấp nhận được. | Thấp hơn — vẫn tồn tại khả năng trùng lặp dưới các kịch bản retry/rebalance, không có lớp bảo vệ ở code. | Thấp — chỉ thay đổi tham số hạ tầng (retry, RF), không cần sửa code — nhưng đổi lại chấp nhận rủi ro correctness còn tồn đọng cho dữ liệu tài chính. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Producer `checkout` (Go/sarama): đổi `RequiredAcks` từ `NoResponse` → `WaitForAll`/`acks=all`, bật idempotent producer. (2) Consumer `accounting` (C#/Confluent): thêm check `OrderId` đã xử lý chưa trước khi ghi vào `order`/`orderitem`/`shipping` (constraint unique trên `OrderId` hoặc check-before-insert). (3) Consumer `fraud-detection` (Kotlin): thêm dedup theo `OrderId` trước khi tính vào fraud count/log. (4) Test bằng cách publish trùng thủ công 1 `OrderId` và verify chỉ xử lý 1 lần ở cả 2 consumer.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Đây là thay đổi **code ứng dụng**, cần review riêng (không chỉ là hạ tầng) — phối hợp với Nguyên (technical review) trước khi merge. Kết hợp chặt với KF-02 (drain & switch): idempotency là lớp phòng thủ bổ sung cho đúng thời điểm chuyển tiếp (edge case 1 message bị xử lý lại do consumer rebalance ngay lúc cutover).

---

## Ghi chú chung

* Các quyết định trên tham chiếu context kỹ thuật từ recon trực tiếp `techx-corp-chart/values.yaml` (Kafka: KRaft single-broker, `kafka:9092`, topic `orders`, `RequiredAcks=NoResponse`, 2 consumer group `accounting`/`fraud-detection` cùng `AutoOffsetReset=Earliest`) và `infra/terraform/*.tf` (VPC `10.0.0.0/16`, private subnet `10.0.10.0/24`/`10.0.11.0/24`, EKS 1.34).
* KF-01, KF-03 phụ thuộc quyết định của CDO04 (cost) và Thuỷ (secret path) — xem `docs/cdo08/week2/mandate3/review-requests/REVIEW-REQUEST-CDO04-COST-REL03-HA-OPTIONS.md` cho tiền lệ cost review, và convention `techx/tf4/*` cho Secrets Manager.
* KF-02, KF-05 phối hợp với thứ tự cutover chung của Mandate 8 (Valkey → PostgreSQL → Kafka đề xuất) để đảm bảo checkout SLO ≥ 99% trong lúc migrate.
