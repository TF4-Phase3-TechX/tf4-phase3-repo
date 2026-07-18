# Kế hoạch Triển khai Di trú PostgreSQL (EKS -> RDS PostgreSQL)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Database Engineer

Tài liệu này hướng dẫn chi tiết quy trình di trú PostgreSQL từ cụm EKS tự vận hành sang **Amazon RDS PostgreSQL** (Multi-AZ). Kế hoạch này được thiết kế để một kỹ sư có thể thực thi độc lập và tự kiểm tra kết quả thông qua các **Kết quả mong muốn (Expected Output)** đi kèm mỗi bước.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target RDS Instance:** `db.t4g.micro` (Multi-AZ: 1 Primary + 1 Standby).
* **Storage:** 20 GiB gp3 (Mặc định có sẵn 3,000 IOPS và 125 MB/s throughput).
* **DMS Migration Instance:** `dms.t3.medium` On-Demand (Chỉ chạy tối đa 24 giờ).
* **SLO Downtime:** Dưới 60 giây (Downtime Write Pause thực tế dự kiến chỉ ~10 - 15 giây).
* **Bảo mật đường truyền:** TLS Verify-Full (`sslmode=verify-full` sử dụng AWS CA Bundle).
* **Chính sách lưu trữ dự phòng (PG-04):** Giữ EKS DB standby trong **48 giờ**, sao lưu dump file lên **AWS S3 lưu trữ trong 7 ngày** trước khi hủy hoàn toàn.

---

## 2. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường & Cấu hình WAL (T-7 ngày)
*Thực hiện trước chiến dịch di trú trong khung giờ bảo trì được lên kế hoạch trước*

- [ ] **1.1. Khởi tạo RDS:** Sử dụng Terraform provision cụm RDS PostgreSQL Multi-AZ.
- [ ] **1.2. Mở thông cổng mạng:**
  - Cấu hình Security Group của RDS cho phép nhận inbound port `5432` từ IP range (hoặc Security Group) của cụm EKS Worker Nodes (theo PG-06: Node-to-SG).
- [ ] **1.3. Kiểm tra & Cấu hình Source DB (EKS PostgreSQL):**
  - **Kiểm tra trước (Preflight check):** Kết nối vào EKS Postgres chạy lệnh:
    ```sql
    SHOW wal_level;
    ```
    - **Kết quả mong muốn (Expected Output):**
      ```text
       wal_level 
      -----------
       logical
      (1 row)
      ```
    - *Nếu kết quả đã là `logical`, bỏ qua bước cấu hình WAL bên dưới.*
  - **Cấu hình logical WAL:** Thêm `-c wal_level=logical` vào command arg của Pod PostgreSQL trong file `values.yaml` của Helm chart.
  - **Khởi động lại Pod:** Chạy lệnh `helm upgrade`. 
    - *Lưu ý:* Do đĩa PVC sử dụng chế độ `ReadWriteOnce`, pod mới không thể mount đĩa nếu pod cũ chưa tắt. Sử dụng strategy `Recreate` để khởi động lại pod.
    - **Kết quả mong muốn (Expected Output):** Pod cũ bị terminated và pod mới chuyển sang trạng thái `Running` sau 30-40 giây. Kiểm tra lại `SHOW wal_level;` trả về `logical`.
  - **Tạo User DMS Replication:** Kết nối vào EKS Postgres và tạo tài khoản:
    ```sql
    CREATE USER dms_user WITH PASSWORD 'secure_password';
    GRANT rds_superuser TO dms_user; -- Hoặc cấp quyền replication & select cụ thể
    ```
- [ ] **1.4. Chuẩn bị AWS CA Certificate Bundle (TLS Verify-Full):**
  - *Lý do:* Để đáp ứng quyết định PG-05, ứng dụng client bắt buộc phải verify chứng chỉ số của RDS để chống tấn công MitM.
  - **Tải file CA bundle của AWS:**
    ```bash
    curl -sS https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o global-bundle.pem
    ```
  - **Tạo Kubernetes ConfigMap trong namespace của ứng dụng:**
    ```bash
    kubectl create configmap rds-ca-cert --from-file=global-bundle.pem -n <namespace>
    ```
  - **Kết quả mong muốn (Expected Output):** ConfigMap `rds-ca-cert` được tạo thành công. Lệnh `kubectl get configmap rds-ca-cert -o yaml` hiển thị đúng key `global-bundle.pem` chứa dữ liệu cert.

---

### BƯỚC 2: Đồng bộ Schema & Thiết lập AWS DMS (T-24 giờ)
*Bắt đầu chạy trước giờ Cutover 24 giờ*

- [ ] **2.1. Đồng bộ Schema (DDL Only) sang RDS:**
  - *Lý do:* AWS DMS chỉ đồng bộ dữ liệu thô và cấu hình bảng cơ bản. Ta cần export cấu hình schema trống sang RDS trước để giữ các indexes, foreign keys, triggers.
  - **Chạy lệnh export cấu hình (DDL only) từ EKS:**
    ```bash
    pg_dump -h <eks-postgres-ip> -U postgres -d otel --schema-only -f postgres_schema.sql
    ```
  - **Import file schema vào RDS mới:**
    ```bash
    psql -h <rds-dns-endpoint> -U postgres -d otel -f postgres_schema.sql
    ```
  - **Xác thực kết quả (Expected Output):** Kết nối vào RDS Postgres chạy `\dt` hoặc `\d reviews.productreviews`, bảng trống xuất hiện với đầy đủ cấu trúc cột, kiểu dữ liệu và khóa chính/khóa ngoại.
- [ ] **2.2. Vô hiệu hóa Constraints và Triggers tạm thời trên RDS:**
  - **Chạy SQL script vô hiệu hóa tạm thời trên target RDS:**
    ```sql
    ALTER TABLE reviews.productreviews DISABLE TRIGGER ALL;
    ALTER TABLE reviews.products DISABLE TRIGGER ALL;
    ```
  - **Xác thực kết quả (Expected Output):** Chạy truy vấn kiểm tra trạng thái trigger, cột `tgenabled` của trigger chuyển sang `D` (disabled):
    ```sql
    SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid = 'reviews.productreviews'::regclass;
    ```
- [ ] **2.3. Cấu hình AWS DMS Task:**
  - Tạo máy chủ DMS Replication Instance `dms.t3.medium` On-Demand trong cùng VPC/Subnet với EKS Worker Nodes.
  - Tạo **Source Endpoint** trỏ tới Service IP của EKS Postgres (Port 5432, user `dms_user`).
  - Tạo **Target Endpoint** trỏ tới Endpoint DNS của RDS (Port 5432, master user).
  - Tạo **DMS Replication Task**:
    - Chế độ chạy: `Migrate existing data and replicate ongoing changes` (Full Load + CDC).
    - Bật tính năng **Validation enabled**.
    - Cấu hình **Target table preparation mode = Do nothing**.
- [ ] **2.4. Khởi chạy và Giám sát:**
  - Start Task trên DMS console.
  - **Xác thực kết quả (Expected Output):**
    - Trạng thái Task trên DMS Console chuyển sang: `Load complete, replication ongoing`.
    - Dưới mục **Table statistics**, trạng thái của toàn bộ các bảng hiển thị: `Table state: Replicating`, `Validation State: Validated` và `Validation Pending Records: 0`.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause dự kiến: ~10 - 15 giây*

#### GIAI ĐOẠN 1: CHUẨN BỊ (Trước cutover 15-30 phút)
- [ ] **3.1. Kích hoạt lại Constraints & Triggers trên RDS:**
  - Bật lại toàn bộ khóa ngoại và trigger trên database RDS:
    ```sql
    ALTER TABLE reviews.productreviews ENABLE TRIGGER ALL;
    ALTER TABLE reviews.products ENABLE TRIGGER ALL;
    ```
  - **Xác thực kết quả (Expected Output):** Chạy truy vấn trạng thái trigger, cột `tgenabled` chuyển về `O` (origin/enabled).
- [ ] **3.2. Triển khai Deployment Green (Bảo mật TLS Verify-Full):**
  - Cấu hình file YAML Deployment của các ứng dụng client (`product-catalog`, `product-reviews`, `accounting`) mount file cert từ ConfigMap:
    ```yaml
    spec:
      containers:
      - name: app
        volumeMounts:
        - name: rds-ca-vol
          mountPath: /ssl
          readOnly: true
      volumes:
      - name: rds-ca-vol
        configMap:
          name: rds-ca-cert
          defaultMode: 0444
    ```
  - Cấu hình connection string của ứng dụng trỏ đến target RDS kèm tham số chứng chỉ:
    `postgresql://<user>:<password>@<rds-dns-endpoint>:5432/otel?sslmode=verify-full&sslrootcert=/ssl/global-bundle.pem`
  - Deploy Deployment Green song song lên EKS cluster.
  - **Xác thực kết quả (Expected Output):**
    - `kubectl get pods -l version=rds` hiển thị trạng thái `Running` và `1/1 Ready`.
    - Log pod không báo lỗi SSL/TLS handshake và chứng thực được RDS server thành công.

#### GIAI ĐOẠN 2: THỰC THI CUTOVER
- [ ] **3.3. Khóa ghi trên Source DB (EKS PostgreSQL):**
  - Chạy lệnh SQL khóa ghi trên database EKS cũ để đảm bảo dữ liệu tĩnh tuyệt đối:
    ```sql
    ALTER DATABASE otel SET default_transaction_read_only = on;
    ```
  - Chạy SQL ngắt các session ghi đang hoạt động:
    ```sql
    SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'otel' AND pid <> pg_backend_pid();
    ```
  - **Xác thực kết quả (Expected Output):** Chạy lệnh `SHOW default_transaction_read_only;` trả về `on`. Các request Write gửi tới database cũ sẽ bị từ chối kèm lỗi `cannot execute INSERT in a read-only transaction`.
- [ ] **3.4. Đợi DMS sync sạch dữ liệu:**
  - Giám sát CloudWatch metric `CDCLag` của DMS Task.
  - **Xác thực kết quả (Expected Output):** CDCLag của Task đạt `0` giây và Validation báo cáo 100% khớp. Thực hiện **Stop** DMS Replication Task thành công.
- [ ] **3.5. Kiểm tra Checksum & Reset Database Sequences:**
  - Đồng bộ sequences trên RDS Postgres khớp với giá trị `MAX(id)` để tránh lỗi trùng lặp khóa chính:
    ```sql
    SELECT setval(pg_get_serial_sequence('reviews.productreviews', 'id'), (SELECT MAX(id) FROM reviews.productreviews));
    ```
  - **Xác thực kết quả (Expected Output):**
    - Lệnh chạy thành công và trả về giá trị ID lớn nhất hiện tại.
- [ ] **3.6. Atomic Service Switch chuyển traffic:**
  - Cập nhật Kubernetes Service selector để chuyển hướng toàn bộ traffic sang các Pod của Deployment Green mới:
    ```bash
    kubectl patch service reviews-service -p '{"spec":{"selector":{"version":"rds"}}}'
    ```
  - **Xác thực kết quả (Expected Output):**
    - `kubectl get svc reviews-service` hiển thị selector mới `version=rds`.
    - Thực hiện giao dịch checkout/ghi thử nghiệm trên web thành công. Bản ghi mới xuất hiện trên RDS Postgres và sequences tự động tăng chính xác.

#### GIAI ĐOẠN 3: HOÀN TẤT & DỌN DẸP
- [ ] **3.7. Xóa Replication Slot trên Source DB (EKS Postgres) ngay lập tức:**
  - *Lý do:* Khi tắt DMS Task, nếu giữ EKS Postgres chạy standby mà không xóa replication slot, PostgreSQL sẽ tiếp tục tích lũy WAL files trong thư mục `pg_wal` dẫn tới tràn đĩa PVC và sập DB nguồn ngay trong thời gian chờ standby.
  - **Chạy SQL xóa replication slot trên EKS Postgres:**
    ```sql
    -- Tìm tên replication slot liên quan đến DMS
    SELECT slot_name FROM pg_replication_slots;
    -- Xóa replication slot
    SELECT pg_drop_replication_slot('dms_slot_name');
    ```
  - **Kết quả mong muốn (Expected Output):** Lệnh trả về thành công. Kiểm tra lại `SELECT * FROM pg_replication_slots;` không còn slot nào hoạt động.
- [ ] **3.8. Xóa DMS Task & Instance:**
  - Tiến hành xóa DMS Replication Task và Replication Instance trên AWS Console để dừng tính phí.
- [ ] **3.9. Standby 48 giờ & Backup S3 (Chính sách PG-04):**
  - **Trong vòng 48 giờ:** Giữ nguyên StatefulSet PostgreSQL cũ trên EKS ở trạng thái chạy bình thường nhưng khóa ghi (`read-only`) làm dự phòng nóng.
  - **Sau 48 giờ chạy thử ổn định:**
    - Kết nối vào EKS Postgres cũ và chạy dump dữ liệu lần cuối:
      ```bash
      pg_dump -h <eks-postgres-ip> -U postgres -d otel -F c -b -v -f /tmp/postgres_final_backup.dump
      ```
    - Upload file backup lên Amazon S3 và cấu hình Lifecycle lưu trữ trong **7 ngày** trước khi tự động hủy.
    - Chạy lệnh xóa PVC, Service và StatefulSet PostgreSQL cũ trên cụm EKS để giải phóng hoàn toàn tài nguyên.

---

## 3. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng trên RDS trong 24 giờ observation window:

- [ ] **Bước R.1. Khởi chạy Reverse CDC:**
  - Khởi chạy task **Reverse CDC** trên AWS DMS đã được cấu hình sẵn (Source: RDS Postgres, Target: EKS Postgres cũ) để đồng bộ ngược toàn bộ dữ liệu đơn hàng mới tạo từ RDS về lại EKS.
  - **Xác thực kết quả (Expected Output):** Trạng thái task Reverse CDC chuyển sang `Replicating`.
- [ ] **Bước R.2. Khóa ghi trên RDS:**
  - Chạy lệnh SQL khóa ghi trên RDS Postgres target:
    ```sql
    ALTER DATABASE otel SET default_transaction_read_only = on;
    ```
  - Termination các active sessions trên RDS để ép nhận read-only mode.
- [ ] **Bước R.3. Đợi Reverse CDC lag về 0:**
  - Giám sát task Reverse CDC cho tới khi lag về `0` giây. Stop task Reverse CDC.
  - **Xác thực kết quả (Expected Output):** Lag = 0, Validation báo 100% khớp.
- [ ] **Bước R.4. Reset Sequence trên EKS:**
  - Chạy script SQL đồng bộ lại sequences trên EKS Postgres cũ khớp với `MAX(id) + 1` thực tế trên RDS.
- [ ] **Bước R.5. Atomic Switch-Back:**
  - Cập nhật selector của Kubernetes Service để trỏ kết nối quay về các Pod chạy trên EKS Postgres cũ.
  - **Xác thực kết quả (Expected Output):** Selector service trỏ về `version=eks` (hoặc cấu hình cũ). Hệ thống chạy bình thường trên EKS Postgres.
