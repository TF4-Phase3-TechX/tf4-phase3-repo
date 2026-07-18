# Kế hoạch Triển khai Di trú Kafka (EKS -> AWS MSK)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Messaging/Infra Engineer

Tài liệu này hướng dẫn chi tiết quy trình di trú Apache Kafka từ cụm EKS tự vận hành sang **Amazon MSK Provisioned** (Multi-AZ). Kế hoạch này được thiết kế để một kỹ sư có thể thực thi độc lập và tự kiểm tra kết quả thông qua các **Kết quả mong muốn (Expected Output)** đi kèm mỗi bước.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target MSK Instance:** 2 Brokers `kafka.t3.small` (Multi-AZ).
* **Storage:** 10 GiB gp3 per broker (Kích hoạt Storage Auto-Scaling để tự động scale-up ổ đĩa EBS lên tối đa 100GB khi đạt ngưỡng 80% dung lượng sử dụng).
* **Cơ chế xác thực:** SASL/SCRAM kết hợp SSL/TLS (Sử dụng mật khẩu mã hóa thông qua AWS Secrets Manager).
* **Công cụ di trú:** MirrorMaker 2 deployed trên cụm EKS (Incremental cost = $0).
* **SLO Downtime:** **Zero Downtime (0%)** đối với luồng đặt hàng storefront.

---

## 2. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường (Preparation)
- [ ] **1.1. Khởi tạo MSK Cluster:** Sử dụng Terraform provision cụm MSK Provisioned với instance `kafka.t3.small`.
- [ ] **1.2. Mở thông cổng mạng:**
  - Cấu hình Security Group của MSK cho phép nhận inbound port `9094` (SASL_SSL) từ Security Group của cụm EKS Worker Nodes.
- [ ] **1.3. Cấu hình SCRAM Authentication:**
  - Tạo một KMS Customer Managed Key (CMK) dùng để mã hóa mật khẩu.
  - Tạo Secret trên AWS Secrets Manager chứa thông tin credentials dạng JSON (`username` và `password`). 
  - Liên kết Secret này với MSK Cluster.
  - **Kết quả mong muốn (Expected Output):** Cụm MSK hiển thị trạng thái `Active`, và mục "Associated secrets" hiển thị đúng Secrets ARN của database credentials.

---

### BƯỚC 2: Cấu hình Đồng bộ dữ liệu (Live Replication)
- [ ] **2.1. Deploy MirrorMaker 2 trên EKS:**
  - Deploy pod Connect chạy MirrorMaker 2 sử dụng Strimzi Kafka Operator.
- [ ] **2.2. Cấu hình MirrorMaker 2 Connector:**
  - Thiết lập source (EKS Kafka) và target (MSK), cấu hình SASL/SCRAM kết hợp SSL/TLS.
  - Bật tính năng đồng bộ consumer offsets:
    ```properties
    sync.group.offsets.enabled=true
    emit.checkpoints.enabled=true
    ```
- [ ] **2.3. Khởi chạy và theo dõi lag:**
  - Start pod MirrorMaker 2.
  - **Kết quả mong muốn (Expected Output):**
    - `kubectl get pods` hiển thị pod Connect/MirrorMaker ở trạng thái `Running` và `1/1 Ready`.
    - Log pod hiển thị `Connector source-record-sender-task-0 is RUNNING` và `Offset sync connector is RUNNING`.
    - Chỉ số replication lag (Consumer Lag) của topic `orders` tiệm cận về `0` (xem qua Grafana Dashboard hoặc lệnh check offset group).

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window - Zero Downtime)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause = 0*

- [ ] **3.1. Switch Producer (Chuyển luồng ghi):**
  - Cập nhật bootstrap server của producer ứng dụng (`checkout` service) sang các địa chỉ broker endpoint SSL của MSK mới.
  - Thực hiện rolling update `checkout` service.
  - **Kết quả mong muốn (Expected Output):** 
    - Checkout pod restart thành công, sẵn sàng nhận request.
    - Chạy thử lệnh consumer trên MSK để kiểm tra xem event mới có xuất hiện trên MSK hay không:
      ```bash
      kafka-console-consumer.sh --bootstrap-server <msk-bootstrap-servers> --topic orders --consumer.config client.properties
      ```
    - Các order mới ghi thành công thẳng vào MSK. Cụm EKS Kafka cũ không phát sinh thêm record mới.
- [ ] **3.2. Chờ MM2 sync sạch dữ liệu (Catch-up sync):**
  - Đợi khoảng 10-15 giây để MirrorMaker 2 hoàn tất đồng bộ nốt các message cuối từ EKS Kafka cũ sang MSK.
  - **Kết quả mong muốn (Expected Output):** Lệnh kiểm tra offset group của EKS Kafka cũ báo cáo `LAG = 0` cho toàn bộ các consumer partitions.
- [ ] **3.3. Switch Consumers (Chuyển luồng đọc):**
  - Cập nhật bootstrap server của các consumer (`accounting`, `fraud-detection`) sang MSK.
  - Thực hiện rolling update các consumer services.
  - **Kết quả mong muốn (Expected Output):**
    - Các consumer pods khởi chạy thành công.
    - Log consumer hiển thị bắt đầu đọc tiếp các events đơn hàng từ offset chính xác trên MSK mà không bị sập hay đọc trùng.
- [ ] **3.4. Dọn dẹp:**
  - Stop MirrorMaker 2 pod và xóa cụm Kafka cũ trên EKS.

---

## 3. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố consumer không thể xử lý topic hoặc mất mát offset trên MSK:

- [ ] **Bước R.1. Redirect Producer:**
  - Cấu hình bootstrap server của producer (`checkout` service) trỏ ngược về lại EKS Kafka cũ. Thực hiện rolling update.
- [ ] **Bước R.2. Sync Catch-up:**
  - Đợi consumer xử lý nốt các message tồn đọng trên MSK.
- [ ] **Bước R.3. Redirect Consumers:**
  - Đổi bootstrap server của các consumer (`accounting`, `fraud-detection`) về lại EKS Kafka cũ. Thực hiện rolling update.
- [ ] **Bước R.4. Reset Offsets (Nếu lệch):**
  - Sử dụng lệnh `kafka-consumer-groups.sh` trên EKS để reset offset của consumer group về vị trí offset cuối cùng đã được xác thực trước khi chạy cutover:
    ```bash
    kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group accounting --reset-offsets --to-offset <last-known-offset> --execute
    ```
  - **Kết quả mong muốn (Expected Output):** Bảng hiển thị thông báo reset thành công, hiển thị `NEW-OFFSET` chính xác bằng `<last-known-offset>`.
- [ ] **Bước R.5. Verify:** Đảm bảo luồng event đơn hàng hoạt động ổn định trên cụm EKS Kafka cũ.
