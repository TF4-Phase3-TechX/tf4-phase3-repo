# Kế hoạch Triển khai Di trú PostgreSQL (EKS -> RDS PostgreSQL)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Database Engineer

Tài liệu này hướng dẫn chi tiết quy trình migration PostgreSQL từ cụm EKS tự vận hành sang **Amazon RDS PostgreSQL** (Multi-AZ). Quy trình này được thiết kế chuẩn chỉn theo phương pháp GitOps và sử dụng **Argo Rollouts** để thực hiện Blue-Green cutover:
- Mọi tài nguyên hạ tầng được quản lý qua **Terraform**.
- Mọi cấu hình ứng dụng được cập nhật qua **Helm Chart / Values Overrides** và quản lý bằng **Argo Rollouts** dưới cụm EKS.
- Phương án này giúp thực hiện Blue-Green cutover atomic (1 giây) và rollback tự động bằng **AWS DMS Reverse CDC** kết hợp nút bấm Abort trên UI hoặc CLI mà không cần đổi tên Pod, không thêm hậu tố tạm thời, giữ Git sạch sẽ.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target RDS Instance (IaC):** `db.t4g.micro` (Multi-AZ: 1 Primary + 1 Standby, bật `rds.logical_replication = 1` trong Parameter Group).
* **Storage (IaC):** 20 GiB gp3 (Mặc định có sẵn 3,000 IOPS và 125 MB/s throughput).
* **DMS Migration Instance (IaC):** `dms.t3.medium` On-Demand (Chỉ chạy tối đa 24 giờ).
* **SLO Downtime:** Dưới 60 giây (Downtime Write Pause thực tế dự kiến chỉ ~10 - 15 giây).
* **Bảo mật đường truyền:** TLS Verify-Full (`sslmode=verify-full` sử dụng AWS CA Bundle).
* **Chính sách lưu trữ dự phòng (PG-04):** Giữ EKS DB standby trong **48 giờ**, sao lưu dump file lên **AWS S3 lưu trữ trong 7 ngày** trước khi hủy hoàn toàn.

---

## 2. Quản lý Cấu hình & Tệp tin trong Codebase

### A. Hạ tầng AWS (Terraform - IaC)
Tất cả hạ tầng được định nghĩa tại thư mục [infra/terraform/](../../../../../infra/terraform):
- [rds.tf](../../../../../infra/terraform/rds.tf): Định nghĩa `aws_db_instance` (RDS PostgreSQL Multi-AZ, Parameter Group bật `logical_replication = 1`) và Security Group Rule cho phép cổng 5432 từ EKS Worker Nodes.
- [dms.tf](../../../../../infra/terraform/dms.tf): Định nghĩa `aws_dms_replication_instance`, `aws_dms_endpoint` (Source & Target), và 2 tasks: `forward_task` (EKS -> RDS) và `reverse_task` (RDS -> EKS, khởi đầu ở trạng thái dừng).

### B. Cấu hình Kubernetes (Helm Chart & GitOps)
* **Tiền đề (Prerequisite):** EKS cluster đã được cài đặt Argo Rollouts Controller. File template [techx-corp-chart/templates/component.yaml](../../../../../techx-corp-chart/templates/component.yaml) hỗ trợ xuất ra `kind: Rollout` thay vị `kind: Deployment` khi cờ `rollouts.enabled = true`.
* **Cấu hình khai báo:**
  - [techx-corp-chart/templates/rds-ca-cert.yaml](../../../../../techx-corp-chart/templates/rds-ca-cert.yaml): Định nghĩa ConfigMap `rds-ca-cert` chứa AWS CA bundle `global-bundle.pem`.
  - [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml): 
    - Cấu hình bật `rollouts.enabled = true` cho các component: `product-catalog`, `product-reviews`, `accounting`.
    - Định nghĩa cấu hình Blue-Green rollout (Active Service, Preview Service và bước pause auto-promotion).

### C. Kịch bản chạy (Bash Scripts)
Đặt tại `docs/cdo08/week2/mandate8/scripts/postgres/`:
- `01-preflight-check.sh`
- `02-export-schema.sh`
- `03-disable-triggers.sh`
- `04-enable-triggers.sh`
- `05-lock-source-writes.sh`
- `06-reset-sequences.sh`
- `07-promote-rollout.sh`
- `08-drop-replication-slot.sh`
- `09-backup-to-s3.sh`
- `rollback-01-abort-rollout.sh`
- `rollback-02-unlock-source.sh`
- `rollback-03-reset-sequences.sh`

---

## 3. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường & Cấu hình WAL
*Thực hiện trước chiến dịch di trú trong khung giờ bảo trì được lên kế hoạch trước*

- [ ] **1.1. Provision RDS & Network (TF):**
  - Khai báo RDS PostgreSQL Multi-AZ và Security Group trong [rds.tf](../../../../../infra/terraform/rds.tf). Đảm bảo Parameter Group của RDS đã bật `rds.logical_replication = 1`.
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline tự động apply.
  - **Expected Output:** AWS Console hiển thị cụm RDS PostgreSQL ở trạng thái `Available`.
- [ ] **1.2. Cấu hình logical WAL trên EKS Postgres (GitOps):**
  - Cập nhật tham số `-c wal_level=logical` vào command arg của PostgreSQL pod trong file Helm values [techx-corp-chart/values.yaml](../../../../../techx-corp-chart/values.yaml) dưới mục `postgresql`. Commit và push lên Git.
  - Chờ ArgoCD tự động đồng bộ và restart StatefulSet PostgreSQL.
  - **Expected Output:** Pod PostgreSQL cũ bị terminated, Pod mới chuyển sang trạng thái `Running` và `1/1 Ready`.
- [ ] **1.3. Kiểm tra tiền di trú (Preflight Check):**
  - Chạy script kiểm tra:
    ```bash
    ./scripts/postgres/01-preflight-check.sh
    ```
    - **Script thực hiện:** Kết nối EKS Postgres chạy `SHOW wal_level;` để xác nhận cấu hình đã ăn. Đồng thời tự động tạo tài khoản `dms_user` dùng cho DMS.
    - **Expected Output:** Script in `[OK] wal_level = logical` và `[OK] dms_user created`.
- [ ] **1.4. Chuẩn bị AWS CA Certificate Bundle (GitOps):**
  - Download CA Bundle từ AWS:
    ```bash
    curl -sS https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o global-bundle.pem
    ```
  - Sao chép nội dung tệp cert vào tệp manifest [techx-corp-chart/templates/rds-ca-cert.yaml](../../../../../techx-corp-chart/templates/rds-ca-cert.yaml).
  - Commit và push thay đổi lên Git branch để ArgoCD tự động đồng bộ ConfigMap `rds-ca-cert` vào cụm.
  - **Expected Output:** Chạy `kubectl get configmap rds-ca-cert` trả về thông tin configmap thành công.

---

### BƯỚC 2: Đồng bộ Schema & Thiết lập AWS DMS

- [ ] **2.1. Đồng bộ Schema (DDL Only) sang RDS:**
  ```bash
  ./scripts/postgres/02-export-schema.sh
  ```
  - **Script thực hiện:** Chạy `pg_dump --schema-only` từ EKS Postgres và import trực tiếp vào target RDS.
  - **Expected Output:** Kết nối vào RDS chạy `\dt` thấy đầy đủ cấu trúc bảng trống nhưng chưa có dữ liệu.
- [ ] **2.2. Vô hiệu hóa Constraints và Triggers trên RDS:**
  ```bash
  ./scripts/postgres/03-disable-triggers.sh
  ```
  - **Script thực hiện:** Kết nối RDS, chạy lệnh SQL `ALTER TABLE ... DISABLE TRIGGER ALL` cho tất cả các bảng.
  - **Expected Output:** Query kiểm tra `pg_trigger` trả về trạng thái `tgenabled = D` cho toàn bộ triggers trên RDS.
- [ ] **2.3. Provision AWS DMS Resources (TF):**
  - Khai báo DMS Replication Instance, Endpoints, `forward_task` và `reverse_task` trong [dms.tf](../../../../../infra/terraform/dms.tf).
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline apply.
  - **Expected Output:** AWS Console hiển thị DMS Replication Instance được tạo ở trạng thái `Active`, 2 tasks hiển thị đầy đủ (task reverse ở trạng thái Ready).
- [ ] **2.4. Khởi chạy và Giám sát DMS Task di trú:**
  - **Thực hiện trên AWS Console:**
    1. Truy cập dịch vụ **Database Migration Service (DMS)** -> **Database migration tasks**.
    2. Chọn task `forward_task` (EKS -> RDS) và nhấn **Actions** -> **Restart/Resume**.
    3. Chờ trạng thái chuyển sang **Replication ongoing**.
    4. Chọn tab **Table statistics** ở bảng dưới, kiểm tra cột **Validation State** hiển thị `Validated` và **Validation Pending Records** bằng `0`.
  - **Expected Output:** Trạng thái Task trên Console hiển thị `Load complete, replication ongoing`. Tab Table statistics: `Validation State = Validated` và `Validation Pending Records = 0`.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause dự kiến: ~10 - 15 giây*

#### GIAI ĐOẠN 1: CHUẨN BỊ (Trước cutover 15-30 phút)
- [ ] **3.1. Kích hoạt lại Constraints & Triggers trên RDS:**
  ```bash
  ./scripts/postgres/04-enable-triggers.sh
  ```
  - **Script thực hiện:** Kết nối RDS, chạy `ALTER TABLE ... ENABLE TRIGGER ALL` cho toàn bộ các bảng.
  - **Expected Output:** Trạng thái trigger trên `pg_trigger` trả về `tgenabled = O` (enabled).
- [ ] **3.2. Đẩy cấu hình RDS lên Git (GitOps):**
  - Cập nhật connection string và ConfigMap cert trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml) của các component (`product-catalog`, `product-reviews`, `accounting`) trỏ sang RDS.
  - Commit và push thay đổi lên Git branch.
  - **Cơ chế hoạt động:** Argo Rollouts tự động phát hiện thay đổi cấu hình, tạo song song một ReplicaSet mới (Green pods - trỏ RDS) bên cạnh ReplicaSet cũ (Blue pods - trỏ EKS DB). Quá trình deploy này tự động dừng ở trạng thái `Paused` nhờ cấu hình Blue-Green rollout, chưa chuyển traffic.
  - **Expected Output:** `kubectl get rollout` hiển thị trạng thái `Paused`. Các pod Green mới ở trạng thái `Running` và `1/1 Ready` nhưng chưa nhận traffic.

#### GIAI ĐOẠN 2: THỰC THI CUTOVER
- [ ] **3.3. Khóa ghi trên Source DB (EKS PostgreSQL):**
  ```bash
  ./scripts/postgres/05-lock-source-writes.sh
  ```
  - **Script thực hiện:** Chạy `ALTER DATABASE otel SET default_transaction_read_only = on;` và gọi `pg_terminate_backend` để ngắt các write sessions cũ.
  - **Expected Output:** Lệnh `SHOW default_transaction_read_only;` trên EKS DB trả về `on`. Các giao dịch Write từ khách hàng bị chặn kèm lỗi `read-only transaction`.
- [ ] **3.4. Đợi DMS sync sạch dữ liệu (Giám sát CloudWatch):**
  - **Thực hiện trên AWS Console:**
    1. Truy cập dịch vụ **Database Migration Service (DMS)** -> **Database migration tasks**.
    2. Click chọn task `forward_task`.
    3. Chọn tab **CloudWatch metrics** ở khu vực tab bên dưới (ngay bên cạnh tab Table statistics).
    4. Theo dõi trực tiếp các biểu đồ thông số (Throughput/Latency/Row count) tại đây cho đến khi các metrics sync sạch dữ liệu, lag giảm về mức **0 giây**.
    5. Tiến hành **Stop** `forward_task` trên DMS Console.
  - **Expected Output:** Các biểu đồ metrics trong tab CloudWatch metrics hiển thị lag về 0 giây ổn định.

- [ ] **3.5. Reset Database Sequences trên RDS:**
  ```bash
  ./scripts/postgres/06-reset-sequences.sh
  ```
  - **Script thực hiện:** Chạy SQL reset sequence khớp với `MAX(id)` của từng bảng trên RDS.
  - **Expected Output:** Trả về kết quả reset sequence thành công cho tất cả các bảng.
- [ ] **3.6. Thăng cấp Rollout (Promote) & Khởi chạy Reverse CDC:**
  - Kích hoạt promote trên giao diện ArgoCD UI (nút **Promote**), hoặc chạy script CLI:
    ```bash
    ./scripts/postgres/07-promote-rollout.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts promote <rollout-name>` cho cả 3 ứng dụng.
  - **Bật đồng bộ ngược ngay lập tức:** Vào AWS DMS Console, chọn `reverse_task` (RDS -> EKS) và nhấn **Actions** -> **Restart/Resume**.
  - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service sang ReplicaSet Green ngay lập tức (atomic ~1 giây). Giao dịch checkout chạy thành công trên RDS. `reverse_task` trên DMS chuyển sang trạng thái `Replication ongoing` để sync ngược dữ liệu mới phát sinh về EKS Postgres cũ.

#### GIAI ĐOẠN 3: HOÀN TẤT & DỌN DẸP
- [ ] **3.7. Xóa Replication Slot trên EKS Postgres cũ:**
  ```bash
  ./scripts/postgres/08-drop-replication-slot.sh
  ```
  - **Script thực hiện:** Kết nối EKS Postgres cũ, chạy `SELECT pg_drop_replication_slot('dms_slot_name');` (Chỉ xóa slot của chiều đi `forward_task`, giữ nguyên EKS DB chạy nhận sync từ chiều về `reverse_task`).
  - **Expected Output:** Lệnh chạy thành công. Slot của chiều đi được giải phóng.
- [ ] **3.8. Dọn dẹp tài nguyên DMS đi (TF):**
  - Disable hoặc xóa cấu hình `forward_task` trong [dms.tf](../../../../../infra/terraform/dms.tf) (vẫn giữ nguyên `reverse_task` chạy cho đến khi hết observation window).
  - Commit, push và merge các thay đổi Terraform vào branch `main`.
  - **Expected Output:** `forward_task` được xóa khỏi AWS Console.
- [ ] **3.9. Standby 48 giờ & Backup S3:**
  - Giữ EKS Postgres cũ làm standby read-only trong 48 giờ để nhận dữ liệu sync ngược từ RDS.
  - Sau 48 giờ chạy ổn định không phát sinh sự cố:
    - Stop `reverse_task` trên DMS Console.
    - Chạy script backup lần cuối:
      ```bash
      ./scripts/postgres/09-backup-to-s3.sh
      ```
      - **Script thực hiện:** `pg_dump` full data từ EKS cũ (đã được sync đầy đủ dữ liệu mới từ RDS qua Reverse CDC), upload lên Amazon S3 lưu trữ trong 7 ngày, sau đó dọn dẹp PVC và StatefulSet PostgreSQL cũ trên EKS.
    - Xóa nốt `reverse_task` và DMS instance trong [dms.tf](../../../../../infra/terraform/dms.tf), commit & push Git để pipeline destroy tài nguyên.
    - **Expected Output:** File dump xuất hiện trên S3. Tất cả tài nguyên PostgreSQL cũ và DMS được dọn dẹp sạch sẽ.

---

## 4. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng trên RDS trong observation window (24 giờ), thực hiện theo quy trình rollback tự động sử dụng DMS Reverse CDC:

- [ ] **Bước R.1. Khóa ghi trên RDS để đóng băng dữ liệu:**
  - Thiết lập tham số database target RDS sang `read-only` (hoặc cấu hình app pause write) để dừng phát sinh dữ liệu mới trên RDS.
- [ ] **Bước R.2. Chờ DMS Reverse CDC hoàn tất đồng bộ:**
  - Giám sát CloudWatch metric `CDCLag` của `reverse_task` cho đến khi về `0` (đảm bảo tất cả dữ liệu ghi mới trên RDS kể từ lúc cutover đã được đồng bộ an toàn về EKS Postgres).
  - Tiến hành **Stop** `reverse_task` trên AWS Console.
- [ ] **Bước R.3. Reset Database Sequences trên EKS Postgres cũ:**
  ```bash
  ./scripts/postgres/rollback-03-reset-sequences.sh
  ```
  - **Script thực hiện:** Chạy SQL reset sequence trên EKS Postgres khớp với `MAX(id)` của dữ liệu vừa được sync về (vì DMS CDC không sync giá trị sequence, cần chạy lại để tránh lỗi trùng khóa khi ghi mới).
  - **Expected Output:** Sequences được reset thành công trên EKS Postgres.
- [ ] **Bước R.4. Hủy bỏ Rollout (Abort / Switch-Back):**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/postgres/rollback-01-abort-rollout.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts abort` cho cả 3 ứng dụng.
  - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service quay trở lại ReplicaSet Blue cũ ngay lập tức. Traffic hướng sang EKS Postgres cũ.
- [ ] **Bước R.5. Mở khóa ghi trên EKS Postgres cũ:**
  ```bash
  ./scripts/postgres/rollback-02-unlock-source.sh
  ```
  - **Script thực hiện:** Chạy `ALTER DATABASE otel SET default_transaction_read_only = off;` và giải phóng các session bị treo.
  - **Expected Output:** Giao dịch Write từ khách hàng được tiếp nhận bình thường trên EKS Postgres cũ, dữ liệu được bảo toàn đầy đủ (RPO = 0, RTO dưới 1 phút).
