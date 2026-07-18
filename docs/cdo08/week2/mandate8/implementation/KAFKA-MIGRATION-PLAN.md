# Kế hoạch Triển khai Di trú Kafka (EKS -> AWS MSK)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Messaging/Infra Engineer

Tài liệu này hướng dẫn chi tiết quy trình migration Apache Kafka từ cụm EKS tự vận hành sang **Amazon MSK Provisioned** (Multi-AZ). Quy trình này được thiết kế chuẩn chỉn theo phương pháp GitOps và sử dụng **Argo Rollouts** để thực hiện Blue-Green cutover:
- Cụm AWS MSK và SCRAM Secrets được khai báo qua **Terraform** và commit, push, merge vào branch `main` để pipeline tự động apply. Không chạy `terraform apply` thủ công.
- Cấu hình MirrorMaker 2 (Strimzi) và tham số kết nối của ứng dụng được khai báo qua **Helm Chart / Values Overrides** và quản lý bằng **Argo Rollouts** dưới cụm EKS.
- Phương án này giúp thực hiện Blue-Green cutover atomic và rollback tức thời bằng nút bấm trên UI hoặc CLI **mà không cần đổi tên Pod, không thêm hậu tố tạm thời, giữ Git sạch sẽ**.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target MSK Instance (IaC):** 2 Brokers `kafka.t3.small` (Multi-AZ).
* **Storage (IaC):** 10 GiB gp3 per broker + Storage Auto-Scaling lên tối đa 100 GiB khi đạt ngưỡng 80%.
* **Cơ chế xác thực (IaC):** SASL/SCRAM + SSL/TLS (credentials lưu tại AWS Secrets Manager).
* **Công cụ migration:** MirrorMaker 2 deployed trên EKS (Incremental cost = $0).
* **SLO Downtime:** **Zero Downtime (0%)** đối với luồng đặt hàng storefront.

---

## 2. Quản lý Cấu hình & Tệp tin trong Codebase

### A. Hạ tầng AWS (Terraform - IaC)
Hạ tầng được định nghĩa tại thư mục [infra/terraform/](../../../../../infra/terraform):
- [msk.tf](../../../../../infra/terraform/msk.tf): Định nghĩa `aws_msk_cluster` (broker types, storage scaling), KMS Key và liên kết `aws_msk_scram_secret` lưu thông tin xác thực.

### B. Cấu hình Kubernetes (Helm Chart & GitOps)
* **Tiền đề (Prerequisite):** 
  - EKS cluster đã được cài đặt Argo Rollouts Controller.
  - File template [techx-corp-chart/templates/component.yaml](../../../../../techx-corp-chart/templates/component.yaml) hỗ trợ xuất ra `kind: Rollout` cho các component producer (`checkout`) và consumers (`accounting`, `fraud-detection`) khi cờ `rollouts.enabled = true`.
  - Có sẵn file template [techx-corp-chart/templates/mirrormaker2.yaml](../../../../../techx-corp-chart/templates/mirrormaker2.yaml) hỗ trợ cả Connector chiều đi (`forward`) và chiều về (`reverse`).
* **Cấu hình khai báo:**
  - [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml): 
    - Khai báo bật chạy MirrorMaker 2 (cờ `mirrormaker2.enabled = true`).
    - Khai báo cờ `reverse-mm2.enabled = false` (mặc định tắt khi vận hành bình thường).
    - Bật `rollouts.enabled = true` cho các component: `checkout`, `accounting`, `fraud-detection`.
    - Cập nhật bootstrap server của các ứng dụng sang endpoint SASL_SSL của MSK mới.

### C. Kịch bản chạy (Bash Scripts)
Đặt tại `docs/cdo08/week2/mandate8/scripts/kafka/`:
- `01-verify-msk-connectivity.sh`
- `02-deploy-mirrormaker2.sh`
- `03-monitor-mm2-lag.sh`
- `04-promote-producers.sh`
- `05-verify-catchup.sh`
- `06-promote-consumers.sh`
- `07-cleanup.sh`
- `rollback-01-abort-rollout.sh`
- `rollback-02-reset-offsets.sh`

---

## 3. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường
- [ ] **1.1. Provision MSK Cluster (TF):**
  - Khai báo cụm MSK Provisioned và Secrets Manager trong [msk.tf](../../../../../infra/terraform/msk.tf).
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline apply.
  - **Expected Output:** AWS Console hiển thị cụm MSK ở trạng thái `Active`, Secrets Manager hiển thị liên kết SCRAM credentials thành công.
- [ ] **1.2. Mở thông cổng mạng:** Cấu hình Security Group của MSK cho phép inbound port `9094` (SASL_SSL) từ Security Group của EKS Worker Nodes.
- [ ] **1.3. Kiểm tra kết nối từ EKS tới MSK:**
  ```bash
  ./scripts/kafka/01-verify-msk-connectivity.sh
  ```
  - **Script thực hiện:** Spin up debug pod tạm thời kết nối tới MSK Broker cổng `9094` sử dụng `nc -zv`, chạy thử lệnh verify credentials.
  - **Expected Output:** Script in `[OK] Connection to <msk-broker> 9094 succeeded` và `[OK] SASL/SCRAM auth verified`.

---

### BƯỚC 2: Cấu hình Đồng bộ dữ liệu (Live Replication)

- [ ] **2.1. Deploy MirrorMaker 2 trên EKS (GitOps):**
  - Khai báo manifest MirrorMaker 2 và bật `enabled: true` cho Connect cluster trong file [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml). Commit và push lên Git.
  - Chạy script kiểm tra:
    ```bash
    ./scripts/kafka/02-deploy-mirrormaker2.sh
    ```
    - **Script thực hiện:** Kiểm tra pod Connect/MirrorMaker2 chuyển sang trạng thái `Running`, gọi REST API của Connect cluster để kiểm tra trạng thái tasks.
    - **Expected Output:** Script in `[OK] MirrorMaker 2 pod Running. Connector tasks: source-record-sender-task RUNNING, offset-sync RUNNING`.
- [ ] **2.2. Giám sát MirrorMaker 2 lag (Giám sát CloudWatch):**
  - **Thực hiện trên AWS Console:**
    1. Truy cập dịch vụ **CloudWatch** -> **Metrics** -> **All metrics**.
    2. Chọn danh mục **AWS/Kafka** hoặc **MSK**.
    3. Chọn metrics về Consumer Group Lag cho MirrorMaker 2 task.
    4. Theo dõi biểu đồ cho đến khi lag sync giảm hẳn về mức **0** và giữ ổn định liên tục.
  - **Expected Output:** Biểu đồ lag hiển thị mốc 0 ổn định.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window — Zero Downtime)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause = 0*

- [ ] **3.1. Đẩy cấu hình MSK cho Producer (GitOps):**
  - Cập nhật bootstrap server của `checkout` sang MSK endpoint (`9094`) và cấu hình SCRAM credentials trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml). Commit và push lên Git.
  - **Cơ chế hoạt động:** Argo Rollouts tự tạo một ReplicaSet mới (Green pods - trỏ MSK) song song với ReplicaSet cũ (Blue pods - trỏ EKS Kafka) và tạm dừng ở trạng thái `Paused`.
  - **Expected Output:** `kubectl get rollout` hiển thị trạng thái `Paused`. Pods Green mới ở trạng thái `Running` và `1/1 Ready` nhưng chưa nhận traffic.
- [ ] **3.2. Thăng cấp Rollout Producer chuyển traffic (Promote):**
  - Kích hoạt promote trên giao diện ArgoCD UI (nút **Promote**), hoặc chạy script CLI:
    ```bash
    ./scripts/kafka/04-promote-producers.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts promote checkout`.
  - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service sang pods Green ngay lập tức. Đơn hàng mới đổ về trực tiếp từ checkout sang MSK. EKS Kafka cũ không phát sinh ghi mới.
- [ ] **3.3. Kiểm tra MM2 catch-up sync:**
  ```bash
  ./scripts/kafka/05-verify-catchup.sh
  ```
  - **Script thực hiện:** Kiểm tra lag của consumer group MirrorMaker 2 trên EKS Kafka cũ về 0 (Đảm bảo toàn bộ messages cũ đã được sync hết sang MSK).
  - **Expected Output:** Script in `[OK] MM2 catch-up complete. EKS Kafka LAG = 0`.
- [ ] **3.4. Đẩy cấu hình MSK cho Consumers (GitOps):**
  - Cập nhật bootstrap server của các consumer (`accounting`, `fraud-detection`) sang MSK endpoint (`9094`) trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml). Commit và push lên Git.
  - **Cơ chế hoạt động:** Argo Rollouts tự động tạo các ReplicaSet mới (Green pods - trỏ MSK) song song với ReplicaSet cũ (Blue pods - trỏ EKS Kafka).
- [ ] **3.5. Thăng cấp Rollout Consumers chuyển traffic (Promote):**
  - Kích hoạt promote trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/kafka/06-promote-consumers.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts promote accounting` và `kubectl argo rollouts promote fraud-detection`.
  - **Expected Output:** Consumers chuyển hướng kết nối sang MSK thành công. Verify logs consumer đọc tiếp tục từ offset chính xác trên MSK.
- [ ] **3.6. Dọn dẹp:**
  ```bash
  ./scripts/kafka/07-cleanup.sh
  ```
  - **Script thực hiện:** Cập nhật [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml) tắt MirrorMaker 2. Commit và push lên Git. Chạy lệnh xóa Kafka StatefulSet cũ trên EKS.
  - **Expected Output:** MirrorMaker 2 pod được thu hồi, cụm Kafka cũ được dọn dẹp sạch sẽ.

---

## 4. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng sau khi cutover, tùy thuộc vào trạng thái dữ liệu ghi, thực hiện theo một trong hai kịch bản sau:

### TRƯỜNG HỢP 1: Rollback TRƯỚC KHI có dữ liệu ghi mới vào MSK (RPO = 0)
*Áp dụng khi phát hiện lỗi ngay trong lúc cutover/verify, trước khi đơn hàng mới được tạo trên MSK*

- [ ] **Bước R1.1. Hủy bỏ Rollout (Abort / Switch-Back):**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/kafka/rollback-01-abort-rollout.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts abort checkout` và abort cho các consumer.
    - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service quay trở lại ReplicaSet Blue cũ ngay lập tức. Hệ thống chạy trên EKS Kafka cũ.

---

### TRƯỜNG HỢP 2: Rollback SAU KHI đã có dữ liệu ghi mới vào MSK (Đồng bộ ngược bằng Reverse MirrorMaker 2 - RPO = 0)
*Áp dụng khi hệ thống đã hoạt động trên MSK một thời gian, phát sinh nhiều tin nhắn đơn hàng mới, nhưng sau đó gặp lỗi nghiêm trọng bắt buộc phải quay lại EKS Kafka*

- [ ] **Bước R2.1. Khóa ghi trên MSK để đóng băng dữ liệu:**
  - Cấu hình dừng ghi tin nhắn từ producer `checkout` vào MSK cluster.
- [ ] **Bước R2.2. Khởi chạy Reverse MirrorMaker 2 (MSK -> EKS Kafka) qua GitOps:**
  - Cập nhật cờ `reverse-mm2.enabled = true` trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml).
  - Commit và push lên Git để ArgoCD tự động deploy và khởi chạy task Reverse MirrorMaker 2.
  - **Expected Output:** Pod Reverse MM2 chuyển sang trạng thái `Running` trên EKS, bắt đầu kéo tin nhắn từ MSK về EKS Kafka cũ.
- [ ] **Bước R2.3. Giám sát Reverse MM2 sync sạch dữ liệu (Giám sát CloudWatch):**
  - Giám sát CloudWatch metric lag của Reverse MM2 cho đến khi về **0** (đảm bảo toàn bộ tin nhắn đơn hàng mới tạo trên MSK đã được copy đầy đủ sang EKS Kafka).
  - Sau khi lag về 0, cập nhật `reverse-mm2.enabled = false` và push Git để tắt task sync ngược.
- [ ] **Bước R2.4. Hủy bỏ Rollout đưa traffic về EKS Kafka cũ:**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/kafka/rollback-01-abort-rollout.sh
    ```
    - **Script thực hiện:** Hủy bỏ (Abort) rollout của `checkout` và các consumers để chuyển hướng kết nối quay về EKS Kafka cũ.
- [ ] **Bước R2.5. Đồng bộ / Reset Offsets trên EKS Kafka cũ:**
  ```bash
  ./scripts/kafka/rollback-02-reset-offsets.sh
  ```
  - **Script thực hiện:** Chạy lệnh `kafka-consumer-groups.sh --reset-offsets` trên EKS Kafka cũ để đồng bộ lại offset của các consumer group (`accounting`, `fraud-detection`) khớp với các tin nhắn vừa được sync về từ MSK, tránh việc consumer đọc trùng lặp hoặc bỏ sót dữ liệu.
  - **Expected Output:** Bảng CLI hiển thị `NEW-OFFSET` được reset thành công trên EKS Kafka. Hệ thống hoạt động bình thường trên EKS Kafka cũ với đầy đủ dữ liệu tin nhắn (RPO = 0).
