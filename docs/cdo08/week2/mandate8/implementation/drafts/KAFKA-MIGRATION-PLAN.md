# Kế hoạch Triển khai Di trú Kafka (EKS -> AWS MSK)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Messaging/Infra Engineer

Tài liệu này hướng dẫn chi tiết quy trình migration Apache Kafka từ cụm EKS tự vận hành sang **Amazon MSK Provisioned** (Multi-AZ). Quy trình này được thiết kế chuẩn theo phương pháp GitOps và sử dụng **Argo Rollouts** để thực hiện Blue-Green cutover.

> [!IMPORTANT]
> **Tài liệu Tiền đề Chung:**
> Trước khi thực hiện kế hoạch này, bạn bắt buộc phải đọc và hoàn thành các bước thiết lập trong tài liệu [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md). Tài liệu này chứa hướng dẫn cài đặt Argo Rollouts, cấu hình bảo mật mạng, và định nghĩa các điều kiện ràng buộc hạ tầng.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target MSK Instance:** 2 Brokers `kafka.t3.small` (Multi-AZ).
* **Storage:** 10 GiB gp3 per broker + Storage Auto-Scaling lên tối đa 100 GiB khi đạt ngưỡng 80%.
* **Cơ chế xác thực:** SASL/SCRAM + SSL/TLS (credentials lưu tại AWS Secrets Manager).
* **Công cụ migration:** MirrorMaker 2 deployed trên EKS.
* **Mục tiêu SLO Downtime (Có điều kiện):** **Zero Downtime (0%)** đối với luồng đặt hàng storefront khi đáp ứng đủ điều kiện kỹ thuật.

---

## 2. Quản lý Cấu hình & Tệp tin trong Codebase

> [!WARNING]
> **Trạng thái Codebase:** Các tệp tin cấu hình và script dưới đây **CHƯA TỒN TẠI** trong repo hiện tại. Chúng được lập lịch để **tạo trong Pull Request (PR) triển khai sau khi bản kế hoạch này được phê duyệt**.

### A. Hạ tầng AWS (Terraform - IaC)
Sẽ được định nghĩa tại thư mục [infra/terraform/](../../../../../infra/terraform) trong PR triển khai:
- `msk.tf`: Định nghĩa `aws_msk_cluster` (broker types, storage scaling), KMS Key và liên kết `aws_msk_scram_secret` lưu thông tin xác thực.

### B. Cấu hình Kubernetes (Helm Chart & GitOps)
Sẽ được bổ sung/chỉnh sửa trong PR triển khai:
- `techx-corp-chart/templates/mirrormaker2.yaml`: Định nghĩa manifest chạy MirrorMaker 2 (Strimzi Custom Resource `KafkaMirrorMaker2` - phương án chính thức đã chọn ở Gate 2.3). Cấu hình hỗ trợ cả Connector chiều đi (`forward`) và chiều ngược (`reverse`).
- `techx-corp-chart/templates/component.yaml`: Cập nhật hỗ trợ xuất ra tài nguyên `kind: Rollout` cho các component producer (`checkout`) và consumers (`accounting`, `fraud-detection`) khi cờ `rollouts.enabled = true`.
- `deploy/values-app-stamp.yaml`: 
  - Khai báo bật chạy MirrorMaker 2 (cờ `mirrormaker2.enabled = true`).
  - Khai báo cờ `reverse-mm2.enabled = false` (mặc định tắt khi vận hành bình thường).
  - Bật `rollouts.enabled = true` cho các component: `checkout`, `accounting`, `fraud-detection`.
  - Cập nhật bootstrap server của các ứng dụng sang endpoint SASL_SSL của MSK mới.

### C. Kịch bản chạy (Bash Scripts)
Sẽ được tạo tại `docs/cdo08/week2/mandate8/scripts/kafka/` trong PR triển khai:
- `01-verify-msk-connectivity.sh` (Verify network port và SASL/SCRAM auth)
- `02-deploy-mirrormaker2.sh` (Khởi tạo và chạy MirrorMaker 2)
- `03-monitor-mm2-lag.sh` (Kiểm tra lag đồng bộ của MirrorMaker 2)
- `04-promote-producers.sh` (Thăng cấp Rollout cho Producer)
- `05-verify-catchup.sh` (Đảm bảo lag về 0 trước khi chuyển Consumer)
- `06-promote-consumers.sh` (Thăng cấp Rollout cho Consumer)
- `07-cleanup.sh` (Dọn dẹp Kafka StatefulSet cũ)
- `rollback-01-abort-rollout.sh` / `rollback-02-reset-offsets.sh`

---

## 3. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường

- [ ] **1.1. Cài đặt Argo Rollouts:** Đảm bảo bước **P1.1** và **P1.2** trong [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md) đã hoàn thành.
- [ ] **1.2. Cài đặt Strimzi Kafka Operator:**
  * Thực hiện theo hướng dẫn tại **Mục 2.3** của [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md). Tiến hành cài đặt Strimzi Operator vào cụm EKS để quản lý MirrorMaker 2 thông qua Custom Resource `KafkaMirrorMaker2`.
- [ ] **1.3. Provision MSK Cluster (TF):**
  - Khai báo cụm MSK Provisioned và Secrets Manager trong `msk.tf`.
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline apply.
  - **Expected Output:** AWS Console hiển thị cụm MSK ở trạng thái `Active`, Secrets Manager hiển thị liên kết SCRAM credentials thành công.
- [ ] **1.4. Mở thông cổng mạng & Kiểm tra kết nối:**
  - Cấu hình Security Group của MSK cho phép inbound port `9094` (SASL_SSL) từ Security Group của EKS Worker Nodes.
  - Chạy script kiểm tra:
    ```bash
    ./scripts/kafka/01-verify-msk-connectivity.sh
    ```
    - **Script thực hiện:** Spin up debug pod tạm thời kết nối tới MSK Broker cổng `9094` sử dụng `nc -zv`, chạy thử lệnh verify credentials.

---

### BƯỚC 2: Cấu hình Đồng bộ dữ liệu (Live Replication)

- [ ] **2.1. Deploy MirrorMaker 2 trên EKS (GitOps):**
  - Khai báo manifest MirrorMaker 2 và bật `enabled: true` trong `deploy/values-app-stamp.yaml`. Commit và push lên Git.
  - Chạy script kiểm tra:
    ```bash
    ./scripts/kafka/02-deploy-mirrormaker2.sh
    ```
    - **Expected Output:** Pod Connect/MirrorMaker2 chuyển sang trạng thái `Running`, gọi REST API của Connect cluster kiểm tra thấy các sync tasks ở trạng thái `RUNNING`.
- [ ] **2.2. Giám sát MirrorMaker 2 lag:**
  - Theo dõi metrics Consumer Group Lag của MirrorMaker 2 trên CloudWatch cho đến khi độ trễ sync giảm hẳn về mức **0** và giữ ổn định liên tục.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause = 0*

- [ ] **3.1. Đẩy cấu hình MSK cho Producer (GitOps):**
  - Cập nhật bootstrap server của `checkout` sang MSK endpoint (`9094`) và cấu hình SCRAM credentials trong `deploy/values-app-stamp.yaml`. Commit và push lên Git.
  - **Cơ chế hoạt động:** Argo Rollouts tự tạo một ReplicaSet mới (Green pods - trỏ MSK) song song với ReplicaSet cũ (Blue pods - trỏ EKS Kafka) và tạm dừng ở trạng thái `Paused`.
  - **Expected Output:** `kubectl get rollout` hiển thị trạng thái `Paused`. Pods Green mới ở trạng thái `Running` và `1/1 Ready` nhưng chưa nhận traffic.
- [ ] **3.2. Thăng cấp Rollout Producer chuyển traffic (Promote):**
  - Kích hoạt promote trên giao diện ArgoCD UI (nút **Promote**), hoặc chạy script CLI:
    ```bash
    ./scripts/kafka/04-promote-producers.sh
    ```
  - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service sang pods Green ngay lập tức. Đơn hàng mới đổ về trực tiếp từ checkout sang MSK. EKS Kafka cũ không phát sinh ghi mới.
- [ ] **3.3. Kiểm tra MM2 catch-up sync & Thực hiện Đối soát Dữ liệu Trước Cutover:**
  - Chạy script kiểm tra lag:
    ```bash
    ./scripts/kafka/05-verify-catchup.sh
    ```
  - Thực hiện kiểm tra đối soát dữ liệu theo **Mục 5.1: Đối soát Dữ liệu Trước Cutover (Pre-Cutover Parity Check)** bên dưới để đảm bảo mọi tin nhắn cũ trên EKS Kafka đã được đồng bộ hoàn toàn sang MSK trước khi chuyển đổi Consumer.
- [ ] **3.4. Đẩy cấu hình MSK cho Consumers (GitOps):**
  - Cập nhật bootstrap server của các consumer (`accounting`, `fraud-detection`) sang MSK endpoint (`9094`) trong `deploy/values-app-stamp.yaml`. Commit và push lên Git.
- [ ] **3.5. Thăng cấp Rollout Consumers chuyển traffic (Promote):**
  - Kích hoạt promote trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/kafka/06-promote-consumers.sh
    ```
  - **Expected Output:** Consumers chuyển hướng kết nối sang MSK thành công.
- [ ] **3.6. Thực hiện Đối soát Dữ liệu Sau Cutover:**
  - Thực hiện kiểm tra đối soát theo **Mục 5.2: Đối soát Dữ liệu Sau Cutover (Post-Cutover Parity Check)** bên dưới.
- [ ] **3.7. Dọn dẹp:**
  ```bash
  ./scripts/kafka/07-cleanup.sh
  ```
  - Cập nhật `deploy/values-app-stamp.yaml` tắt MirrorMaker 2. Commit và push lên Git. Chạy lệnh xóa Kafka StatefulSet cũ trên EKS.

---

## 4. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng sau khi cutover, tùy thuộc vào trạng thái dữ liệu ghi, thực hiện theo một trong hai kịch bản sau:

### TRƯỜNG HỢP 1: Rollback TRƯỚC KHI có dữ liệu ghi mới vào MSK (RPO = 0)
*Áp dụng khi phát hiện lỗi ngay trong lúc cutover/verify, trước khi đơn hàng mới được tạo trên MSK*
- [ ] **Bước R1.1. Hủy bỏ Rollout (Abort / Switch-Back):**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script:
    ```bash
    ./scripts/kafka/rollback-01-abort-rollout.sh
    ```

### TRƯỜNG HỢP 2: Rollback SAU KHI đã có dữ liệu ghi mới vào MSK (Đồng bộ ngược bằng Reverse MirrorMaker 2 - RPO = 0)
- [ ] **Bước R2.1. Khóa ghi trên MSK để đóng băng dữ liệu:** Dừng ghi tin nhắn từ producer `checkout` vào MSK cluster.
- [ ] **Bước R2.2. Khởi chạy Reverse MirrorMaker 2 (MSK -> EKS Kafka) qua GitOps:**
  - Cập nhật cờ `reverse-mm2.enabled = true` trong `deploy/values-app-stamp.yaml`. Commit và push lên Git để ArgoCD khởi chạy task Reverse MM2.
- [ ] **Bước R2.3. Giám sát Reverse MM2 sync sạch dữ liệu (Giám sát CloudWatch):**
  - Giám sát metric lag của Reverse MM2 cho đến khi về **0** (đảm bảo toàn bộ tin nhắn mới trên MSK đã được copy đầy đủ sang EKS Kafka).
  - Cập nhật `reverse-mm2.enabled = false` và push Git để tắt task sync ngược.
- [ ] **Bước R2.4. Hủy bỏ Rollout đưa traffic về EKS Kafka cũ:**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script `rollback-01-abort-rollout.sh` cho checkout và các consumers.
- [ ] **Bước R2.5. Đồng bộ / Reset Offsets trên EKS Kafka cũ:**
  ```bash
  ./scripts/kafka/rollback-02-reset-offsets.sh
  ```
  - **Script thực hiện:** Chạy lệnh `kafka-consumer-groups.sh --reset-offsets` trên EKS Kafka cũ để đồng bộ lại offset của các consumer group (`accounting`, `fraud-detection`) khớp với các tin nhắn vừa được sync về từ MSK.

---

## 5. Quy trình Kiểm thử và Đối soát Dữ liệu (Data Parity Checklist)

### 5.1. Đối soát Dữ liệu Trước Cutover (Pre-Cutover Parity Check)
Thực hiện sau khi chuyển traffic Producer sang MSK (Bước 3.2) và trước khi chuyển đổi Consumer (Bước 3.4):

- [ ] **M-1. Đối soát Offsets tin nhắn (Offset Parity Check):**
  * Sử dụng CLI `kafka-run-class.sh kafka.tools.GetOffsetShell` (hoặc script tương đương) kiểm tra giá trị `LogEndOffset` của từng partition trên các topic quan trọng (ví dụ: `orders`) trên cả EKS Kafka và MSK.
  * **Tiêu chuẩn đạt:** Hiệu số offset giữa EKS Kafka và MSK của các bản tin cũ phải bằng 0.
- [ ] **M-2. Xác minh Consumer Group Lag của MirrorMaker 2:**
  * Chạy lệnh kiểm tra consumer group của MirrorMaker 2 trên EKS Kafka cũ:
    ```bash
    kafka-consumer-groups.sh --bootstrap-server kafka:9092 --describe --group mirrormaker2-group
    ```
  * **Tiêu chuẩn đạt:** Lag của tất cả các partitions của các topic đang thực hiện di trú phải đạt **0** (hoặc đã sync sạch bản tin cuối cùng).

---

### 5.2. Đối soát Dữ liệu Sau Cutover (Post-Cutover Parity Check)
Thực hiện sau khi đã chuyển traffic Consumer sang MSK (Bước 3.5):

- [ ] **A-1. Kiểm tra Dòng chảy Tin nhắn Đơn hàng (Message Flow Verification):**
  * Kiểm tra log của producer `checkout` xem có lỗi kết nối SASL/SCRAM hay không.
  * Kiểm tra log của các consumer `accounting` và `fraud-detection`.
  * **Tiêu chuẩn đạt:** Consumer nhận được tin nhắn và xử lý thành công (không có log báo lỗi deserialization hoặc lỗi kết nối).
- [ ] **A-2. Kiểm tra Offset Commit trên MSK:**
  * Chạy lệnh describe consumer groups trên cụm MSK mới để kiểm tra trạng thái offset của các consumer:
    ```bash
    kafka-consumer-groups.sh --bootstrap-server <msk_bootstrap_server>:9094 --describe --group accounting-group
    ```
  * **Tiêu chuẩn đạt:** Các consumer group đã commit offset đúng theo tiến độ và lag ở mức thấp (tùy theo tải hệ thống).
- [ ] **A-3. Kiểm tra Reverse MM2 Sync Back (Dry-run):**
  * Kích hoạt thử Reverse MM2 trên môi trường thử nghiệm và verify rằng tin nhắn ghi mới vào MSK được đẩy thành công về EKS Kafka để sẵn sàng cho kịch bản rollback nếu xảy ra sự cố.

