# Kế hoạch Triển khai Di trú PostgreSQL (EKS -> RDS PostgreSQL)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Database Engineer

Tài liệu này hướng dẫn chi tiết quy trình migration PostgreSQL từ cụm EKS tự vận hành sang **Amazon RDS PostgreSQL** (Multi-AZ). Quy trình này được thiết kế chuẩn theo phương pháp GitOps và sử dụng **Argo Rollouts** để thực hiện Blue-Green cutover.

> [!IMPORTANT]
> **Tài liệu Tiền đề Chung:**
> Trước khi thực hiện kế hoạch này, bạn bắt buộc phải đọc và hoàn thành các bước thiết lập trong tài liệu [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md). Tài liệu này chứa hướng dẫn cài đặt Argo Rollouts, cấu hình bảo mật mạng, và định nghĩa các điều kiện ràng buộc hạ tầng.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target RDS Instance:** `db.t4g.micro` (Multi-AZ: 1 Primary + 1 Standby, bật `rds.logical_replication = 1` trong Parameter Group).
* **Storage:** 20 GiB gp3 (Mặc định có sẵn 3,000 IOPS và 125 MB/s throughput).
* **DMS Migration Instance:** `dms.t3.medium` On-Demand (Chỉ chạy trong thời gian di trú và window theo dõi).
* **Mục tiêu SLO Downtime (Có điều kiện):** Dưới 60 giây (Downtime Write Pause thực tế dự kiến chỉ ~10 - 15 giây khi đáp ứng đủ các điều kiện kỹ thuật).
* **Bảo mật đường truyền:** TLS Verify-Full (`sslmode=verify-full` sử dụng AWS CA Bundle).
* **Chính sách lưu trữ dự phòng (PG-04):** Giữ EKS DB standby trong **48 giờ**, sao lưu dump file lên **AWS S3 lưu trữ trong 7 ngày** trước khi hủy hoàn toàn.

---

## 2. Quản lý Cấu hình & Tệp tin trong Codebase

> [!WARNING]
> **Trạng thái Codebase:** Các tệp tin cấu hình và script dưới đây **CHƯA TỒN TẠI** trong repo hiện tại. Chúng được lập lịch để **tạo trong Pull Request (PR) triển khai sau khi bản kế hoạch này được phê duyệt**.

### A. Hạ tầng AWS (Terraform - IaC)
Sẽ được định nghĩa tại thư mục [infra/terraform/](../../../../../infra/terraform) trong PR triển khai:
- `rds.tf`: Định nghĩa `aws_db_instance` (RDS PostgreSQL Multi-AZ, Parameter Group bật `logical_replication = 1`) và Security Group Rule cho phép cổng 5432 từ EKS Worker Nodes / NLB.
- `dms.tf`: Định nghĩa `aws_dms_replication_instance`, `aws_dms_endpoint` (Source & Target), và 2 tasks: `forward_task` (EKS -> RDS) và `reverse_task` (RDS -> EKS, khởi đầu ở trạng thái dừng).

### B. Cấu hình Kubernetes (Helm Chart & GitOps)
Sẽ được bổ sung/chỉnh sửa trong PR triển khai:
- `techx-corp-chart/templates/postgres-migration-bridge.yaml`: Định nghĩa Service `LoadBalancer` nội bộ (Internal NLB) trỏ tới Pod PostgreSQL tự vận hành hiện tại để làm Endpoint cho DMS.
- `techx-corp-chart/templates/rds-ca-cert.yaml`: Định nghĩa ConfigMap `rds-ca-cert` chứa AWS CA bundle `global-bundle.pem`.
- `techx-corp-chart/templates/component.yaml`: Cập nhật hỗ trợ xuất ra tài nguyên `kind: Rollout` khi cờ `rollouts.enabled = true`.
- `deploy/values-app-stamp.yaml`: 
  - Cấu hình bật `rollouts.enabled = true` cho các component: `product-catalog`, `product-reviews`, `accounting`.
  - Định nghĩa cấu hình Blue-Green rollout (Active Service, Preview Service và bước pause auto-promotion).

### C. Kịch bản chạy (Bash Scripts)
Sẽ được tạo tại `docs/cdo08/week2/mandate8/scripts/postgres/` trong PR triển khai:
- `01-preflight-check.sh` (Verify logical WAL, tạo dms_user)
- `02-export-schema.sh` (Export DDL từ EKS Postgres sang RDS)
- `03-disable-triggers.sh` / `04-enable-triggers.sh` (Tắt/Bật trigger trên RDS)
- `05-lock-source-writes.sh` (Khóa ghi EKS DB)
- `06-reset-sequences.sh` (Đồng bộ sequences trên RDS)
- `07-promote-rollout.sh` (Thăng cấp Argo Rollout)
- `08-drop-replication-slot.sh` (Dọn dẹp slot chiều đi)
- `09-backup-to-s3.sh` (Backup EKS cũ lên S3)
- `rollback-01-abort-rollout.sh` / `rollback-02-unlock-source.sh` / `rollback-03-reset-sequences.sh`

---

## 3. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường & Cấu hình WAL
*Thực hiện trước chiến dịch di trú trong khung giờ bảo trì*

- [ ] **1.1. Cài đặt Argo Rollouts:** Đảm bảo bước **P1.1** và **P1.2** trong [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md) đã hoàn thành.
- [ ] **1.2. Thiết lập Cầu nối Mạng cho PostgreSQL:**
  - Vì EKS PostgreSQL hiện tại chạy dạng `ClusterIP`, ta phải tạo Internal NLB bằng cách deploy file `postgres-migration-bridge.yaml` (xem chi tiết tại phần **2.2.A** của [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md)).
  - **DMS Endpoint Connection:** AWS DMS Source Endpoint sẽ được cấu hình kết nối tới DNS của Internal NLB này.
  - Cập nhật Security Group của EKS Worker Nodes cho phép cổng `5432` từ IP của DMS Replication Instance.
- [ ] **1.3. Provision RDS & Network (TF):**
  - Khai báo RDS PostgreSQL Multi-AZ và Security Group trong `rds.tf`. Đảm bảo Parameter Group của RDS đã bật `rds.logical_replication = 1`.
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline tự động apply.
  - **Expected Output:** AWS Console hiển thị cụm RDS PostgreSQL ở trạng thái `Available`.
- [ ] **1.4. Cấu hình logical WAL trên EKS Postgres (GitOps):**
  - Cập nhật tham số `-c wal_level=logical` vào command arg của PostgreSQL pod trong file Helm values `techx-corp-chart/values.yaml` dưới mục `postgresql`. Commit và push lên Git.
  - Chờ ArgoCD tự động đồng bộ và restart StatefulSet PostgreSQL.
  - **Expected Output:** Pod PostgreSQL cũ bị terminated, Pod mới chuyển sang trạng thái `Running` và `1/1 Ready`.
- [ ] **1.5. Kiểm tra tiền di trú (Preflight Check):**
  - Chạy script kiểm tra:
    ```bash
    ./scripts/postgres/01-preflight-check.sh
    ```
    - **Script thực hiện:** Kết nối EKS Postgres chạy `SHOW wal_level;` để xác nhận cấu hình đã ăn. Đồng thời tự động tạo tài khoản `dms_user` dùng cho DMS.
    - **Expected Output:** Script in `[OK] wal_level = logical` và `[OK] dms_user created`.
- [ ] **1.6. Chuẩn bị AWS CA Certificate Bundle (GitOps):**
  - Download CA Bundle từ AWS:
    ```bash
    curl -sS https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o global-bundle.pem
    ```
  - Sao chép nội dung tệp cert vào tệp manifest `techx-corp-chart/templates/rds-ca-cert.yaml`.
  - Commit và push thay đổi lên Git branch để ArgoCD tự động đồng bộ ConfigMap `rds-ca-cert` vào cụm.

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
  - **Script thực hiện:** Kết nối RDS, chạy lệnh SQL `ALTER TABLE ... DISABLE TRIGGER ALL` cho tất cả các bảng. (Điều này giúp tăng tốc độ đồng bộ full-load của DMS và tránh lỗi khóa ngoại).
- [ ] **2.3. Provision AWS DMS Resources (TF):**
  - Khai báo DMS Replication Instance, Endpoints, `forward_task` và `reverse_task` trong `dms.tf`.
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
- [ ] **3.2. Đẩy cấu hình RDS lên Git (GitOps):**
  - Cập nhật connection string và ConfigMap cert trong `deploy/values-app-stamp.yaml` của các component (`product-catalog`, `product-reviews`, `accounting`) trỏ sang RDS.
  - Commit và push thay đổi lên Git branch.
  - **Cơ chế hoạt động:** Argo Rollouts tự động phát hiện thay đổi cấu hình, tạo song song một ReplicaSet mới (Green pods - trỏ RDS) bên cạnh ReplicaSet cũ (Blue pods - trỏ EKS DB). Quá trình deploy này tự động dừng ở trạng thái `Paused` nhờ cấu hình Blue-Green rollout, chưa chuyển traffic.
  - **Expected Output:** `kubectl get rollout` hiển thị trạng thái `Paused`. Các pod Green mới ở trạng thái `Running` và `1/1 Ready` nhưng chưa nhận traffic.

#### GIAI ĐOẠN 2: THỰC THI CUTOVER
- [ ] **3.3. Khóa ghi trên Source DB (EKS PostgreSQL):**
  ```bash
  ./scripts/postgres/05-lock-source-writes.sh
  ```
  - **Script thực hiện:** Chạy `ALTER DATABASE otel SET default_transaction_read_only = on;` và gọi `pg_terminate_backend` để ngắt các write sessions cũ.
- [ ] **3.4. Đợi DMS sync sạch dữ liệu (Giám sát CloudWatch):**
  - Theo dõi trực tiếp các biểu đồ thông số trên CloudWatch hoặc DMS Console cho đến khi các metrics sync sạch dữ liệu, lag giảm về mức **0 giây**.
  - Tiến hành **Stop** `forward_task` trên DMS Console.
- [ ] **3.5. Thực hiện Đối soát Dữ liệu Trước Cutover:**
  - Thực hiện kiểm tra theo **Mục 5.1: Đối soát Dữ liệu Trước Cutover (Pre-Cutover Parity Check)** bên dưới để đảm bảo dữ liệu 2 bên khớp hoàn toàn trước khi cho phép ứng dụng R/W vào RDS.
- [ ] **3.6. Reset Database Sequences trên RDS:**
  ```bash
  ./scripts/postgres/06-reset-sequences.sh
  ```
  - **Script thực hiện:** Chạy SQL reset sequence khớp với `MAX(id)` của từng bảng trên RDS.
- [ ] **3.7. Thăng cấp Rollout (Promote) & Khởi chạy Reverse CDC:**
  - Kích hoạt promote trên giao diện ArgoCD UI (nút **Promote**), hoặc chạy script CLI:
    ```bash
    ./scripts/postgres/07-promote-rollout.sh
    ```
  - **Bật đồng bộ ngược ngay lập tức:** Vào AWS DMS Console, chọn `reverse_task` (RDS -> EKS) và nhấn **Actions** -> **Restart/Resume**.
  - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service sang ReplicaSet Green ngay lập tức (atomic ~1 giây). Giao dịch checkout chạy thành công trên RDS. `reverse_task` bắt đầu sync ngược dữ liệu mới phát sinh về EKS Postgres cũ.
- [ ] **3.8. Thực hiện Đối soát Dữ liệu Sau Cutover:**
  - Thực hiện kiểm tra theo **Mục 5.2: Đối soát Dữ liệu Sau Cutover (Post-Cutover Parity Check)** bên dưới.

#### GIAI ĐOẠN 3: HOÀN TẤT & DỌN DẸP
- [ ] **3.9. Xóa Replication Slot trên EKS Postgres cũ:**
  ```bash
  ./scripts/postgres/08-drop-replication-slot.sh
  ```
- [ ] **3.10. Dọn dẹp tài nguyên DMS đi (TF):**
  - Xóa cấu hình `forward_task` trong `dms.tf`. Commit, push và merge để pipeline apply.
- [ ] **3.11. Standby 48 giờ & Backup S3:**
  - Giữ EKS Postgres cũ làm standby read-only trong 48 giờ để nhận dữ liệu sync ngược từ RDS.
  - Sau 48 giờ chạy ổn định không phát sinh sự cố:
    - Stop `reverse_task` trên DMS Console.
    - Chạy script backup lần cuối:
      ```bash
      ./scripts/postgres/09-backup-to-s3.sh
      ```
    - Xóa nốt `reverse_task`, DMS instance và Internal NLB trong `dms.tf` và K8s manifests, commit & push Git để pipeline destroy tài nguyên.

---

## 4. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng trên RDS trong observation window (24 giờ), thực hiện theo quy trình rollback tự động sử dụng DMS Reverse CDC:

- [ ] **Bước R.1. Khóa ghi trên RDS để đóng băng dữ liệu:**
  - Thiết lập Parameter Group hoặc chạy script để chuyển target RDS sang `read-only` nhằm dừng phát sinh dữ liệu mới trên RDS.
- [ ] **Bước R.2. Chờ DMS Reverse CDC hoàn tất đồng bộ:**
  - Giám sát CloudWatch metric `CDCLag` của `reverse_task` cho đến khi về `0` (đảm bảo tất cả dữ liệu ghi mới trên RDS kể từ lúc cutover đã được đồng bộ an toàn về EKS Postgres).
  - Tiến hành **Stop** `reverse_task` trên AWS Console.
- [ ] **Bước R.3. Reset Database Sequences trên EKS Postgres cũ:**
  ```bash
  ./scripts/postgres/rollback-03-reset-sequences.sh
  ```
- [ ] **Bước R.4. Hủy bỏ Rollout (Abort / Switch-Back):**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/postgres/rollback-01-abort-rollout.sh
    ```
- [ ] **Bước R.5. Mở khóa ghi trên EKS Postgres cũ:**
  ```bash
  ./scripts/postgres/rollback-02-unlock-source.sh
  ```

---

## 5. Quy trình Kiểm thử và Đối soát Dữ liệu (Data Parity Checklist)

Để đảm bảo tính toàn vẹn và nhất quán của dữ liệu giữa EKS Postgres (Source) và RDS Postgres (Target), Database Engineer phải thực hiện checklist đối soát sau:

### 5.1. Đối soát Dữ liệu Trước Cutover (Pre-Cutover Parity Check)
Thực hiện ngay sau khi EKS Postgres đã được khóa ghi (Bước 3.3) và DMS Task đã sync xong (Bước 3.4):

- [ ] **P-1. Kiểm tra Schema và Cấu trúc Bảng:**
  * Chạy truy vấn đếm tổng số lượng tables, indexes, và triggers trên cả 2 database.
  * *Query đối chiếu:*
    ```sql
    SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';
    SELECT count(*) FROM pg_indexes WHERE schemaname = 'public';
    ```
  * **Tiêu chuẩn đạt:** Số lượng bảng và index trên RDS khớp 100% với EKS.
- [ ] **P-2. Đối soát Số lượng Bản ghi (Row Count Reconciliation):**
  * Thực hiện đếm số dòng (Row Count) trên tất cả các bảng chính.
  * *Query đối chiếu:*
    ```sql
    SELECT 
      schemaname, 
      relname AS table_name, 
      n_live_tup AS row_count 
    FROM pg_stat_user_tables 
    ORDER BY n_live_tup DESC;
    ```
  * **Tiêu chuẩn đạt:** Số lượng bản ghi của mọi bảng trên RDS khớp 100% với EKS Postgres.
- [ ] **P-3. Đối soát Giá trị Khóa chính lớn nhất (Max ID Reconciliation):**
  * Đối với các bảng có khóa chính tự tăng (auto-increment `id`), đối chiếu giá trị lớn nhất hiện tại.
  * *Query đối chiếu:*
    ```sql
    SELECT MAX(id) FROM orders;
    SELECT MAX(id) FROM products;
    ```
  * **Tiêu chuẩn đạt:** Giá trị `MAX(id)` trên RDS khớp 100% với EKS.

---

### 5.2. Đối soát Dữ liệu Sau Cutover (Post-Cutover Parity Check)
Thực hiện sau khi đã chuyển traffic thành công sang RDS (Bước 3.7):

- [ ] **A-1. Kiểm tra Trạng thái Ghi trên RDS:**
  * Kiểm tra ứng dụng có thể thực hiện thành công các thao tác ghi (ví dụ: tạo đơn hàng mới, cập nhật thông tin sản phẩm).
  * Kiểm tra log ứng dụng để đảm bảo không có lỗi `read-only transaction` hoặc `permission denied`.
- [ ] **A-2. Xác minh Reset Sequence thành công:**
  * Đảm bảo các sequence trên RDS đã được reset cao hơn giá trị `MAX(id)` để tránh lỗi trùng khóa (Duplicate Key) khi có bản ghi mới.
  * *Query đối chiếu:*
    ```sql
    SELECT last_value, is_called FROM order_id_seq;
    ```
- [ ] **A-3. Xác minh Đồng bộ ngược (Reverse CDC Verification):**
  * Sau khi có các giao dịch ghi mới trên RDS (ví dụ: một order mới có `id = 1005`), kết nối vào EKS Postgres cũ và kiểm tra xem bản ghi mới này đã được sync ngược về qua DMS `reverse_task` hay chưa.
  * *Query đối chiếu trên EKS Postgres:*
    ```sql
    SELECT * FROM orders WHERE id = 1005;
    ```
  * **Tiêu chuẩn đạt:** Bản ghi mới xuất hiện trên EKS Postgres cũ với đầy đủ dữ liệu trong vòng dưới 5 giây kể từ khi được tạo trên RDS.

