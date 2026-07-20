# Mandate 8 - Kafka Migration Decisions & ADR Record

- **Trạng thái:** Đã hoàn thiện thiết kế hợp nhất (Approved - Pending Final Sign-off)
- **Tech Leads tham gia:** Nguyễn (Lead), Quân (CDO08)

Tài liệu này ghi nhận các quyết định thiết kế kiến trúc (ADR) dạng bảng dành cho dịch vụ Kafka từ EKS self-hosted sang Amazon MSK cho Mandate 8. Hướng tiếp cận kỹ thuật trong tài liệu được thống nhất dựa trên thiết kế chi tiết của Tech Lead Nguyễn nhằm đáp ứng tối đa tính toàn vẹn dữ liệu và cam kết SLO dịch vụ.

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
| **ĐÃ CHỌN** | `Phương án B` | **Ưu điểm:** Đạt tiêu chuẩn managed service của Mandate 8, đảm bảo HA (Multi-AZ 2 brokers), chi phí cực kỳ rẻ và phù hợp ngân sách nhóm.<br>**Nhược điểm:** Phải quản lý sizing và scale-up khi tải tăng đột biến. | **Hợp lý:** Chi phí ước tính khoảng **$62.74/tháng** (khoảng **$14.6/tuần**) cho 2 nodes `kafka.t3.small` kèm 10GB storage mỗi node. | **N/A:** Chi phí nằm dưới trần phê duyệt, không cần trình phê duyệt ngân sách ngoại lệ. |
| **BỊ LOẠI BỎ** | `Phương án A` | **Ưu điểm:** Tự động co giãn theo tải thực tế.<br>**Nhược điểm:** Chi phí tối thiểu rất cao, dễ gây lãng phí tài nguyên cho hệ thống nhỏ. | **Đắt:** Chi phí tối thiểu lên tới **$324/tháng** (chưa tính phí data transfer/storage). | **Phức tạp:** Bắt buộc phải trình xin phê duyệt ngân sách ngoại lệ do vượt trần chi phí của nhóm. |
| **BỊ LOẠI BỎ** | `Phương án C` | **Ưu điểm:** Giữ nguyên trạng thái cũ, không tốn thêm chi phí AWS.<br>**Nhược điểm:** Đi ngược lại tinh thần Mandate 8, hệ thống tiếp tục chạy Kafka Kraft single-node tự quản lý, không có HA, rủi ro mất dữ liệu cao. | **Không đổi** | **Rất phức tạp:** Khả năng bị từ chối cao vì không có lý do kỹ thuật bất khả kháng nào để hoãn di trú. |

#### Kế hoạch Sizing & Scale-up cho Phương án Đã Chọn:
* **Tự động hóa ở tầng Storage (Storage Auto-Scaling):**
  - Kích hoạt tính năng **AWS Application Auto Scaling** cho cụm MSK. Thiết lập tự động tăng dung lượng đĩa EBS (ví dụ từ 10GB lên tối đa 100GB, mỗi lần tăng thêm 10%) khi dung lượng sử dụng vượt quá **80%** (ngăn chặn hoàn toàn lỗi tràn đĩa gây sập cụm broker).
* **Kế hoạch Scale-up Compute (CPU/RAM) khi tải tăng:**
  - Đối với MSK Provisioned, AWS không hỗ trợ tự động thay đổi instance type (Compute Auto-scaling) do đặc thù Kafka cần chạy partition rebalancing (chia lại phân vùng) rất nặng. Do đó, việc scale-up CPU/RAM sẽ được thực hiện bán tự động theo kịch bản:
    1. Cấu hình CloudWatch Alarm cảnh báo khi CPU Utilization trung bình của các broker vượt quá **70%** liên tục trong 15 phút.
    2. Đội vận hành thực hiện **Scale-up Vertical** bằng cách cập nhật thuộc tính `instance_type` của cụm MSK trong Terraform (ví dụ từ `kafka.t3.small` lên `kafka.m7g.large`). AWS MSK sẽ tự động thực hiện rolling nâng cấp từng broker một để đảm bảo không gián đoạn kết nối của clients.

---

## QUYẾT ĐỊNH KF-02: LỰA CHỌN PHƯƠNG THỨC DI TRÚ KAFKA (MIGRATION METHOD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng công cụ đồng bộ MirrorMaker 2 hoặc MSK Replicator.
* **Phương án B:** Dừng luồng ghi và xả hàng đợi (Controlled Drain & Switch).
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-2-lựa-chọn-phương-thức-di-trú-kafka-migration-method))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu Công cụ bổ sung | Ảnh hưởng Downtime storefront |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án A: Sử dụng MirrorMaker 2 (Apache Kafka Connect) deploy trên EKS` | **Ưu điểm:** Đạt tiêu chuẩn **Zero Downtime storefront**. Bảo vệ tuyệt đối SLO availability. Cho phép sử dụng cụm MSK giá rẻ `kafka.t3.small` (tiết kiệm chi phí broker định kỳ hàng tháng). Compute của MirrorMaker 2 chạy trên EKS tận dụng tài nguyên nhàn rỗi (Incremental cost = $0).<br>**Nhược điểm:** Phức tạp vận hành trung bình-cao. Đội ngũ tự cấu hình properties, routing, và tự giám sát offset sync. | **Có:** Deploy pod MirrorMaker 2 trên EKS. | **Zero Downtime:** Storefront phục vụ checkout bình thường trong suốt quá trình đồng bộ. |
| **BỊ LOẠI BỎ** | `Phương án B: Dừng luồng ghi và xả hàng đợi` | **Ưu điểm:** Vận hành đơn giản, không cần cấu hình replication bridge.<br>**Nhược điểm:** Đòi hỏi dừng luồng ghi checkout trong 2-3 phút để xả sạch queue cũ, gây downtime storefront và vi phạm nghiêm trọng SLO cam kết availability. | **Không có** | **Downtime ngắn (2-3 phút)** |
| **BỊ LOẠI BỎ** | `Phương án C: Sử dụng AWS MSK Replicator (Managed)` | **Ưu điểm:** Hoàn toàn managed bởi AWS, tự động vận hành và giám sát, cấu hình cực kỳ đơn giản.<br>**Nhược điểm:** Bắt buộc cụm MSK đích phải nâng cấp lên instance `m5.large` trở lên (làm tăng chi phí broker gấp 5 lần lên ~$66.52/tuần) và tốn thêm phí Replicator (~$25.20/tuần). | **Có:** Dịch vụ AWS MSK Replicator (Tốn phí). | **Zero Downtime** |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Thiết lập Hạ tầng đồng bộ:** Deploy cụm MirrorMaker 2 trên EKS (tận dụng Strimzi Kafka Operator để quản lý cấu hình và kết nối an toàn).
  2. **Cấu hình Replication Task:** Cấu hình replication task cho topic `orders`. Đảm bảo bật tính năng đồng bộ consumer offsets (offset translation) cho các consumer group (`accounting`, `fraud-detection`).
  3. **Giám sát Replication Lag:** Theo dõi chỉ số sync lag của MirrorMaker 2 trên Prometheus/Grafana. Chờ đến khi replication lag tiệm cận 0.
  4. **Thực thi Cutover (Zero Downtime):**
     * **Bước 4.1 (Switch Producer via Argo Rollouts):** Cập nhật connection string trỏ sang MSK và bật `rollouts.enabled = true` cho `checkout` trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml). Commit & push Git. Chờ Green pods ready ở trạng thái Paused, chạy script `./scripts/kafka/04-promote-producers.sh` (thực thi promote checkout) để switch traffic.
     * **Bước 4.2 (Catch-up sync):** Theo dõi CloudWatch metrics, chờ lag của MirrorMaker 2 (EKS -> MSK) về 0.
     * **Bước 4.3 (Switch Consumers via Argo Rollouts):** Cập nhật connection string sang MSK cho các consumer (`accounting`, `fraud-detection`) trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml). Commit & push Git. Chờ pods ready và chạy script `./scripts/kafka/06-promote-consumers.sh` (thực thi promote consumers) để switch. Nhờ offset translation của MM2, consumer tiếp tục tiêu thụ từ offset tương ứng.
  5. **Cleanup:** Cập nhật file values đặt cờ `mirrormaker2.enabled = false` và push Git để thu hồi container. Chạy script `./scripts/kafka/07-cleanup.sh` dọn dẹp cụm Kafka cũ.
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Bắt buộc cấu hình Offset Translation:** Trong MirrorMaker 2, bắt buộc phải set `sync.group.offsets.enabled=true` và `emit.checkpoints.enabled=true`. Nếu thiếu, khi consumer switch sang MSK, nó sẽ không biết đọc tiếp từ đâu, dẫn đến việc đọc lại từ đầu (earliest) gây trùng lặp dữ liệu lớn, hoặc đọc từ cuối (latest) gây mất mát đơn hàng.
  - **Network Security Group:** Đảm bảo mở thông cổng `9092`/`9094` trên Security Group của cả hai cụm Kafka để Replicator có thể kéo/đẩy data bình thường.

---

## QUYẾT ĐỊNH KF-03: CƠ CHẾ XÁC THỰC KẾT NỐI CLIENT (AUTHENTICATION PROTOCOL)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Sử dụng AWS IAM Authentication.
* **Phương án B:** Sử dụng SASL/SCRAM.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-3-cơ-chế-xác-thực-kết-nối-client-authentication-protocol))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu chỉnh sửa Code Client | Độ phức tạp cấu hình Infra |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án B` | **Ưu điểm:** Tương thích ngược tốt với tất cả thư viện client Kafka chuẩn của mọi ngôn ngữ mà không cần cài đặt thêm SDK của AWS. Credentials được quản lý bảo mật qua Secrets Manager.<br>**Nhược điểm:** Phải quản lý credentials dạng username/password. | **Không có:** Chỉ cần cập nhật connection string trong cấu hình client. | **Trung bình:** Cần tạo Secret trong Secrets Manager, liên kết Secret với MSK, và cấu hình IAM policy cho MSK đọc secret. |
| **BỊ LOẠI BỎ** | `Phương án A` | **Ưu điểm:** Bảo mật tích hợp sâu với IAM/IRSA, không cần quản lý mật khẩu.<br>**Nhược điểm:** Phức tạp cho ứng dụng client. Đòi hỏi cài đặt thư viện phụ trợ của AWS (ví dụ `aws-msk-iam-auth`) và sửa đổi code khởi tạo Kafka Client, tăng rủi ro tương thích đối với các client không viết bằng Java. | **Có:** Phải cài thêm dependency của AWS và sửa đổi code khởi dựng Kafka client. | **Thấp** |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Tạo Secret trên Secrets Manager:** Tạo secret chứa thông tin credentials dạng JSON (`username` và `password`). KMS key dùng để mã hóa credentials bắt buộc phải là Customer Managed Key (CMK).
  2. **Liên kết Secret với MSK:** Bật tính năng SASL/SCRAM authentication trên MSK và thực hiện associate secret đó với cụm MSK.
  3. **Cấu hình Client Connection:**
     - Cập nhật connection properties trong ứng dụng:
       ```properties
       security.protocol=SASL_SSL
       sasl.mechanism=SCRAM-SHA-512
       sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="kafka-app-user" password="secure-password-here";
       ```
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Quyền hạn KMS:** IAM Role của cụm MSK bắt buộc phải có quyền decrypt KMS key dùng để mã hóa credentials trong Secrets Manager. Nếu thiếu, MSK sẽ không thể đọc mật khẩu và client không thể authenticate.
  - **Ký tự đặc biệt trong password:** Hạn hệ các ký tự đặc biệt dễ gây lỗi parse JAAS config trong chuỗi cấu hình (ví dụ như dấu chấm phẩy `;` hoặc dấu nháy kép `"`).

---

## QUYẾT ĐỊNH KF-04: NGƯỠNG CẢNH BÁO ĐỘ TRỄ TIÊU THỤ (CONSUMER LAG THRESHOLD)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo khi lag của consumer group vượt quá 50 messages.
* **Phương án 2:** Thiết lập cảnh báo khi lag của consumer group vượt quá 200 messages.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-4-ngưỡng-cảnh-báo-độ-trễ-tiêu-thụ-consumer-lag-threshold))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Tốc độ phát hiện lỗi nghẽn | Rủi ro báo động giả (False Alarm) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án 1` | **Ưu điểm:** Phát hiện sớm tình trạng nghẽn consumer (ví dụ do lỗi logic ứng dụng hoặc crash container), giúp team vận hành phản ứng kịp thời trước khi hàng đợi phình quá lớn.<br>**Nhược điểm:** Có thể phát sinh cảnh báo giả trong thời điểm traffic tăng đột biến. | **Rất nhanh:** Phát hiện lỗi nghẽn hoặc sập consumer trong vòng 1-2 phút. | **Trung bình:** Có thể xuất hiện cảnh báo ảo trong các đợt flash sale ngắn hạn nhưng chấp nhận được để bảo vệ SLO. |
| **BỊ LOẠI BỎ** | `Phương án 2` | **Ưu điểm:** Hạn chế tối đa cảnh báo giả trong các đợt tăng tải ngắn hạn.<br>**Nhược điểm:** Phát hiện lỗi rất chậm. Khi lag đạt 200 messages, thời gian tích lũy nghẽn đã lâu, có thể gây quá thời hạn SLO xử lý đơn hàng và ảnh hưởng xấu đến luồng kế toán. | **Chậm:** Có thể mất nhiều thời gian hơn để phát hiện ra consumer đã bị treo. | **Thấp** |

---

## QUYẾT ĐỊNH KF-05: RÀNG BUỘC CHỐNG TRÙNG LẶP ĐƠN HÀNG (EVENT IDEMPOTENCY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Bắt buộc cấu hình Idempotent Producer và deduplication ở consumer.
* **Phương án B:** Chỉ cấu hình phía Infrastructure.
*(Chi tiết mô tả xem tại [MANDATE-08-KAFKA-ANALYSIS.md](./MANDATE-08-KAFKA-ANALYSIS.md#quyết-định-5-ràng-buộc-chống-trùng-lặp-đơn-hàng-event-idempotency))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Bảo vệ tính toàn vẹn giao dịch | Yêu cầu sửa đổi Code ứng dụng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án A` | **Ưu điểm:** Đảm bảo an toàn tuyệt đối cho các giao dịch đơn hàng và kế toán. Loại bỏ hoàn toàn nguy cơ trùng lặp đơn hàng ở cả tầng truyền tin (broker retry) và tầng xử lý nghiệp vụ (consumer retry).<br>**Nhược điểm:** Đòi hỏi lập trình viên sửa đổi mã nguồn ứng dụng ở cả producer và consumer. | **Tuyệt đối (100%):** Ngăn ngừa triệt để các lỗi duplicate order, duplicate payment gây thiệt hại kinh tế. | **Có:** Cấu hình producer SDK và viết thêm logic lưu vết/check-duplicate ở consumer. |
| **BỊ LOẠI BỎ** | `Phương án B` | **Ưu điểm:** Tiết kiệm thời gian phát triển, giữ nguyên code ứng dụng cũ.<br>**Nhược điểm:** Rủi ro rất cao. Cấu hình infra (retry/ACK) chỉ ngăn trùng lặp ở tầng network, không thể bảo vệ nếu consumer crash giữa chừng sau khi xử lý nhưng trước khi commit offset (khi restart consumer sẽ xử lý lại event đó lần 2). | **Kém:** Vẫn tồn tại rủi ro trùng lặp đơn hàng/kế toán do cơ chế at-least-once của consumer. | **Không có** |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Cấu hình Producer (`checkout` service):**
     - Thiết lập cấu hình connection properties của Kafka Producer SDK:
       ```properties
       enable.idempotence=true
       acks=all
       retries=2147483647
       max.in.flight.requests.per.connection=5
       ```
  2. **Cấu hình Consumer (`accounting` & `fraud-detection` services):**
     - Tạo một bảng deduplication trong PostgreSQL database hoặc một cache table trong Valkey với TTL 24 giờ để lưu các `processed_order_ids`.
     - Trong logic xử lý của consumer, trước khi chạy nghiệp vụ, kiểm tra xem `order_id` đã được xử lý chưa. Nếu đã xử lý, skip event. Nếu chưa, thực thi xử lý nghiệp vụ và insert `order_id` vào bảng deduplication trong cùng một Database Transaction.
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Duy trì Database Transaction:** Việc insert log deduplication và xử lý đơn hàng bắt buộc phải nằm trong cùng một DB transaction. Nếu tách rời, nếu sập ứng dụng giữa hai bước có thể dẫn đến việc mất event (chưa xử lý nhưng đã ghi log deduplication) trước khi thực thi thực tế, hoặc ngược lại.
