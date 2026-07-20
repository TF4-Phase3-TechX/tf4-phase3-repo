# Mandate 8 - PostgreSQL Migration Decisions & ADR Record

- **Trạng thái:** Đã hoàn thiện thiết kế độc lập (Approved - Pending review)

Tài liệu này là bản ghi nhận các quyết định thiết kế kiến trúc (ADR) dạng bảng dành cho cá nhân Tech Lead điền phân tích độc lập. Khung hướng dẫn triển khai chỉ yêu cầu mô tả quy trình chung và các lưu ý phòng ngừa lỗi cho phương án được chọn ở các quyết định kỹ thuật phức tạp.

---

## QUYẾT ĐỊNH PG-00 (QUYẾT ĐỊNH CHUNG): THỨ TỰ DI TRÚ & ĐIỀU KIỆN DỪNG KHẨN CẤP (ABORT TRIGGERS)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án A:**
  - Thứ tự di trú: **Valkey → Kafka/MSK → PostgreSQL** (mỗi store có change window riêng, không chạy song song).
  - Điều kiện dừng khẩn cấp (Abort & Rollback): Checkout success rate < 99% liên tục 5 phút; hoặc latency p95 > 1s; hoặc fail data parity check (schema/row/checksum/sequence/offsets).
- **Phương án B:**
  - Thứ tự di trú khác (ví dụ di trú PostgreSQL đầu tiên).
  - Điều kiện dừng khẩn cấp nới lỏng hơn (chỉ rollback khi hệ thống bị sập hoàn toàn).
    _(Chi tiết mô tả xem tại [CDO08-REL-13-managed-data-migration-plan.md](./CDO08-REL-13-managed-data-migration-plan.md#7-cutover-slo-v%C3%A0-%C4%91i%E1%BB%81u-ki%E1%BB%87n-d%E1%BB%ABng))_

### 2. Phân tích & Lựa chọn của Tech Lead

_(Quyết định này không phát sinh chi phí trực tiếp nên cột Chi phí được lược bỏ)_

| Trạng thái     | Phương án     | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                       | Khả năng kiểm soát rủi ro SLO                                                                                                                                                            | Mức độ phức tạp điều phối                                                                                              |
| :------------- | :------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------- |
| **ĐÃ CHỌN**    | `Phương án A` | **Ưu điểm:** Phân tách rõ ràng change window của từng store, giúp giảm thiểu rủi ro quá tải hệ thống, dễ dàng cô lập lỗi và rollback độc lập.<br>**Nhược điểm:** Tổng thời gian change window của chiến dịch dài hơn do phải chạy tuần tự. | **Tốt nhất:** Cho phép chủ động dừng khẩn cấp và rollback ngay khi có dấu hiệu bất thường về hiệu năng hoặc tính toàn vẹn dữ liệu, trước khi ảnh hưởng nghiêm trọng đến người dùng cuối. | **Trung bình:** Yêu cầu phối hợp chặt chẽ giữa các change window và tuân thủ nghiêm ngặt checklist của từng giai đoạn. |
| **BỊ LOẠI BỎ** | `Phương án B` | **Ưu điểm:** Có thể rút ngắn thời gian triển khai nếu chạy song song.<br>**Nhược điểm:** Rất khó xác định nguyên nhân gốc rễ nếu hệ thống suy giảm hiệu năng; rủi ro ảnh hưởng chéo cao.                                                   | **Kém:** Chỉ rollback khi hệ thống sập hoàn toàn sẽ làm tăng nguy cơ mất mát dữ liệu giao dịch (PostgreSQL/Kafka) và vi phạm cam kết SLO nghiêm trọng.                                   | **Phức tạp:** Rất khó điều phối xử lý sự cố đồng thời trên nhiều store nếu xảy ra lỗi.                                 |

---

## QUYẾT ĐỊNH PG-01: LỰA CHỌN PHƯƠNG THỨC DI TRÚ (MIGRATION METHOD)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án A.1:** Native PostgreSQL Logical Replication.
- **Phương án A.2:** AWS Database Migration Service (AWS DMS).
- **Phương án B:** Offline Dump & Restore.
  _(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-1-lựa-chọn-phương-thức-di-trú-migration-method))_

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái     | Phương án       | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                                                                   | Phân tích Chi phí (Cost)                                                                                                            | Độ phức tạp Triển khai                                                                                              |
| :------------- | :-------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------ |
| **ĐÃ CHỌN**    | `Phương án A.2` | **Ưu điểm:** Quản lý CDC tự động, hỗ trợ cơ chế Validation dữ liệu trực tiếp giúp đảm bảo tính toàn vẹn 100%. Có bảng điều khiển theo dõi trực quan và ổn định.<br>**Nhược điểm:** Phải cấu hình các tài nguyên phụ trợ như DMS Replication Instance, Endpoints và Task mapping rules. | **Tăng nhẹ:** Phát sinh thêm chi phí chạy máy chủ DMS (ví dụ: `dms.t3.medium` khoảng $0.05/giờ, chạy trong 24 giờ (1 ngày) tốn khoảng $1.20). | **Trung bình - Cao:** Yêu cầu phối hợp thiết lập cấu hình IAM, Network endpoints và cấu hình Task trên AWS Console. |
| **BỊ LOẠI BỎ** | `Phương án A.1` | **Ưu điểm:** Không tốn thêm chi phí máy chủ trung gian.<br>**Nhược điểm:** Quản lý thủ công phức tạp qua SQL, khó theo dõi độ trễ (lag) trực quan và không có tính năng tự động validate dữ liệu.                                                                                      | **Không đổi:** Tận dụng tính năng có sẵn của PostgreSQL, không mất phí tài nguyên ngoài.                                            | **Trung bình:** Cần thiết lập publication và subscription thủ công bằng lệnh SQL trên cả 2 database.                |
| **BỊ LOẠI BỎ** | `Phương án B`   | **Ưu điểm:** Đơn giản nhất về mặt kỹ thuật, không sợ lỗi đồng bộ.<br>**Nhược điểm:** Yêu cầu dừng toàn bộ luồng ghi ứng dụng trong suốt thời gian dump/restore, gây downtime lớn (10-30 phút).                                                                                         | **Không đổi:** Không phát sinh thêm chi phí hạ tầng.                                                                                | **Thấp:** Chỉ cần chạy lệnh `pg_dump` và `pg_restore`.                                                              |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:

- **Cách triển khai đề xuất:**
  1. **Cấu hình EKS PostgreSQL (Source DB) — Planned Maintenance Window riêng biệt:**
     - **Kiểm tra trước (preflight check):** Chạy `SHOW wal_level;` trên EKS Postgres. Nếu kết quả đã là `logical` thì bỏ qua toàn bộ bước này.
     - **Chỉ cần thay đổi `wal_level = logical`:** Thêm `-c wal_level=logical` vào command arg của Pod PostgreSQL trong `values.yaml`. _(Lý do: `max_replication_slots` và `max_wal_senders` mặc định của PostgreSQL 17 đều là 10, đã đủ dùng, không cần chỉnh)_.
     - **Khởi động lại Pod:** Áp dụng thay đổi bằng `helm upgrade`. Do PostgreSQL chỉ chạy `replicas: 1`, mọi chiến lược restart đều gây downtime — không thể có Pod mới lên trước khi Pod cũ tắt (vì Pod mới không thể mount PVC `ReadWriteOnce` đang bị Pod cũ giữ). `strategy: Recreate` là lựa chọn đúng để tránh deadlock, downtime thực tế khoảng **~30-40 giây**.
     - **Xử lý downtime này:** Đây là **planned maintenance window độc lập**, thực hiện trước khi bắt đầu migration (ví dụ: T-7 ngày). Thông báo trước cho team và lên lịch vào khung giờ thấp điểm. Downtime này **không phải là downtime của cutover** — giai đoạn cutover thực sự vẫn là zero-downtime bằng Blue-Green.

  2. **Chuẩn bị Schema (DDL Only) trên RDS (Target DB):**
     - Dump cấu trúc DDL (tables, indexes, sequences, primary keys, nhưng không lấy data) từ EKS Postgres và import sang RDS Postgres trước. _(Lý do: AWS DMS mặc định chỉ tạo cấu trúc bảng cơ bản và đồng bộ dữ liệu thô, nó không tự tạo tốt các khóa ngoại, indexes phức tạp, giá trị mặc định, trigger và sequences. Việc tạo trước schema giúp database đích tối ưu hiệu năng ngay từ đầu)_.
     - Vô hiệu hóa (disable) temporary các foreign key constraints và triggers trên RDS trong suốt quá trình đồng bộ. _(Lý do: Tránh việc DMS load dữ liệu thô gặp lỗi ràng buộc khóa ngoại do thứ tự insert giữa các bảng không đồng đều, hoặc trigger chạy ghi đè làm sai lệch dữ liệu)_.
  3. **Khởi tạo và cấu hình AWS DMS:**
     - Tạo **AWS DMS Replication Instance** (`dms.t3.medium` là tối ưu chi phí) trong cùng VPC/Subnet với Worker Nodes. _(Lý do: Bảo đảm kết nối mạng nội bộ có độ trễ thấp và băng thông rộng, tránh phát sinh cước truyền dữ liệu qua Internet)_.
     - Tạo **Source Endpoint** (trỏ tới Service IP của EKS Postgres) và **Target Endpoint** (trỏ tới RDS Postgres endpoint).
     - Tạo **DMS Replication Task**:
       - Cấu hình _Target table preparation mode = Do nothing_ _(Lý do: Giữ nguyên cấu trúc DDL hoàn chỉnh có đầy đủ indexes và keys mà ta đã import ở bước 2)_.
       - Bật _Validation enabled_ _(Lý do: Yêu cầu DMS tự động đối chiếu checksum từng dòng dữ liệu giữa nguồn và đích để phát hiện sai lệch dữ liệu trong thời gian thực)_.
       - Chọn chế độ chạy _Full load + Ongoing replication_ _(Lý do: Sao chép toàn bộ dữ liệu hiện tại trước, sau đó tự động chuyển sang chế độ bắt các thay đổi CDC liên tục)_.
  4. **Kế hoạch Thực thi Cutover — Blue-Green Pod Switch (Chi tiết từng bước & Thời gian dự kiến):**
     - **GIAI ĐOẠN 1: CHUẨN BỊ VÀ WARM UP (Thực hiện trước cutover 15-30 phút)**
       - **Bước 1.1: Kích hoạt lại Foreign Keys & Triggers trên RDS**
         - _Hành động:_ Bật lại các ràng buộc khóa ngoại và triggers trên RDS Postgres.
         - _Thời gian:_ ~1 phút.
         - _Lý do:_ Đưa RDS về trạng thái hoạt động chuẩn, bảo đảm tính toàn vẹn dữ liệu trước khi nhận traffic.
       - **Bước 1.2: Triển khai Deployment B (Green - trỏ RDS) song song**
         - _Hành động:_ Tạo Deployment mới (`product-catalog-rds`, `product-reviews-rds`, `accounting-rds`) với cấu hình connection string trỏ đến target RDS.
         - _Thời gian:_ ~2 phút.
         - _Lý do:_ Chạy song song độc lập, hoàn toàn không ảnh hưởng đến traffic của Deployment A đang chạy trên EKS.
       - **Bước 1.3: Chờ Deployment B Ready & Đạt trạng thái Sẵn sàng**
         - _Hành động:_ Chờ tất cả Pod mới của Deployment B vượt qua cuộc kiểm tra `readinessProbe` và có trạng thái `Running`.
         - _Thời gian:_ ~2 phút (phụ thuộc vào thời gian khởi chạy container).
         - _Lý do:_ **Bắt buộc** Deployment B phải chạy ổn định và kết nối thành công tới RDS trước khi ta can thiệp vào Deployment cũ.

     - **GIAI ĐOẠN 2: THỰC THI CUTOVER (Thời gian Write Pause dự kiến: ~10 - 15 giây)**
       - **Bước 2.1: Bắt đầu khóa ghi (Stop writes) trên EKS Postgres**
         - _Hành động:_ Chạy lệnh SQL trên EKS Postgres:
           `ALTER DATABASE otel SET default_transaction_read_only = on;`
         - _Thời gian:_ Lệnh chạy mất ~1-2 giây để áp dụng. Tuy nhiên, **trạng thái khóa ghi (Write Pause) sẽ bắt đầu từ đây và kéo dài liên tục** qua các bước đồng bộ, checksum, và reset sequence tiếp theo cho tới khi hoàn tất việc switch traffic ở Bước 2.5 (tổng cộng khoảng 10-15 giây).
         - _Lý do:_ Khóa quyền ghi ở tầng DB nguồn để đảm bảo dữ liệu tĩnh tuyệt đối, giúp DMS đồng bộ nốt phần lag còn lại sang RDS mà không phát sinh thêm dữ liệu mới. Deployment A vẫn tiếp tục phục vụ các truy vấn Read bình thường.
       - **Bước 2.2: Chờ DMS đồng bộ nốt dữ liệu còn lại (Thời gian: ~3 - 5 giây)**
         - _Hành động:_ Theo dõi CloudWatch metric `CDCLag` của DMS Task cho tới khi bằng 0 giây và trạng thái Validation báo cáo 100% khớp.
         - _Lý do:_ Bảo đảm toàn bộ các giao dịch ghi cuối cùng trước thời điểm khóa DB đã được chuyển hoàn toàn sang RDS.
       - **Bước 2.3: Kiểm tra Checksum & Xác thực Dữ liệu (Thời gian: ~3 giây)**
         - _Hành động:_ Chạy so sánh MD5 checksum giữa các bảng cốt lõi (ví dụ: `reviews.productreviews`) để đối chiếu nhanh.
         - _Lý do:_ Đảm bảo không có sai lệch dữ liệu giữa nguồn và đích trước khi chuyển hướng người dùng.
       - **Bước 2.4: Reset Sequence trên RDS (Thời gian: ~1 giây)**
         - _Hành động:_ Chạy lệnh SQL đồng bộ sequence cho cột Identity:
           `SELECT setval(pg_get_serial_sequence('reviews.productreviews', 'id'), (SELECT MAX(id) FROM reviews.productreviews));`
         - _Lý do:_ Thiết lập sequence trên RDS khớp chính xác với ID lớn nhất hiện tại để tránh lỗi `Duplicate Key` khi ứng dụng ghi dữ liệu mới.
       - **Bước 2.5: Atomic Service Switch chuyển traffic (Thời gian: ~1 giây)**
         - _Hành động:_ Cập nhật Service selector trỏ sang label của Deployment B:
           `kubectl patch service <service-name> -p '{"spec":{"selector":{"version":"rds"}}}'`
         - _Lý do:_ Thao tác switch diễn ra tức thì ở tầng kube-proxy. Toàn bộ traffic mới (bao gồm cả ghi và đọc) được định tuyến trực tiếp vào Deployment B đã sẵn sàng trên RDS.

     - **GIAI ĐOẠN 3: DỌN DẸP & HOÀN TẤT (Thực hiện sau cutover 15-30 phút)**
       - **Bước 3.1: Theo dõi & Verify Post-Migration**
         - _Hành động:_ Giám sát kỹ application logs, error rates và smoke-test toàn bộ tính năng nghiệp vụ.
       - **Bước 3.2: Dọn dẹp tài nguyên cũ**
         - _Hành động:_ Dừng DMS Task, xóa Replication Slot trên EKS Postgres, giải phóng Deployment A cũ để tiết kiệm tài nguyên.

- **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Không switch traffic trước khi DMS lag = 0:** Nếu switch sớm, RDS còn thiếu data → user đọc dữ liệu không nhất quán hoặc mất data. Đây là lỗi logic cơ bản nhất của cutover.
  - **Không reset sequence trước khi stop writes:** Nếu EKS vẫn đang ghi, MAX(id) thay đổi liên tục, giá trị reset sẽ không chính xác.
  - **Write pause ~5-10 giây là industry standard:** Bước stop writes không phải "downtime" theo nghĩa truyền thống — đây là _planned write quiesce_ diễn ra ở off-peak hours, chấp nhận được theo mọi SLO production thực tế.
  - **Network Security Group:** Phải mở cổng 5432 trên Security Group của EKS Postgres để cho phép IP của DMS Replication Instance truy cập.
  - **Giám sát WAL size trên EKS:** Khi bật logical replication, nếu DMS bị dừng hoặc mất kết nối, WAL files tích lũy và có thể gây tràn đĩa. Cần cấu hình Prometheus Alert cho metric `pg_wal` directory size.

---

## QUYẾT ĐỊNH PG-02: CẤU HÌNH TARGET RDS (SIZING INSTANCE, STORAGE & MULTI-AZ)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án 1:** RDS Multi-AZ (`db.t4g.micro`, đĩa 20 GiB gp3, có standby instance chạy đồng bộ ở AZ khác).
- **Phương án 2:** RDS Single-AZ (`db.t4g.micro`, đĩa 20 GiB gp3, chỉ chạy 1 instance đơn lẻ).
- **Phương án 3:** Cấu hình instance lớn hơn (`db.t3.medium` trở lên) hoặc SSD dung lượng cao hơn.
  _(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-2-cấu-hình-target-rds-multi-az-vs-single-az))_

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái     | Phương án     | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                                                                                                  | Phân tích Chi phí (Cost)                                                                                               | Khả năng tự động phục hồi (RTO/RPO)                                                                                                                  |
| :------------- | :------------ | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ĐÃ CHỌN**    | `Phương án 1` | **Ưu điểm:** Đảm bảo High Availability (HA) ở mức Production. Sử dụng chip Graviton2 (`db.t4g`) hiệu năng cao và tiết kiệm điện. Đĩa gp3 20 GiB cung cấp dung lượng dự phòng 100% (so với PVC 10GB hiện tại) và cho phép cấu hình IOPS độc lập.<br>**Nhược điểm:** Chi phí vận hành cao hơn gấp đôi so với Single-AZ. | **Phù hợp:** Chi phí khoảng **$28.30/tháng** (bao gồm ~$26 instance và ~$2.30 storage). Nằm trong ngân sách phê duyệt. | **RTO < 60s** (failover tự động thông qua DNS chuyển hướng sang standby instance).<br>**RPO = 0** (dữ liệu được ghi đồng bộ synchronous).            |
| **BỊ LOẠI BỎ** | `Phương án 2` | **Ưu điểm:** Chi phí rẻ nhất.<br>**Nhược điểm:** Không có tính năng tự động failover. Nếu AZ gặp sự cố, DB sẽ offline hoàn toàn cho đến khi AZ được khôi phục hoặc phải restore thủ công từ backup.                                                                                                                   | **Rẻ nhất:** Khoảng **$14.15/tháng** (tiết kiệm được ~$14/tháng so với Multi-AZ).                                      | **Kém:** RTO có thể kéo dài nhiều giờ (phụ thuộc vào thời gian restore và cấu hình lại DNS thủ công). RPO phụ thuộc vào tần suất snapshot cuối cùng. |
| **BỊ LOẠI BỎ** | `Phương án 3` | **Ưu điểm:** Hiệu năng tính toán dư thừa lớn.<br>**Nhược điểm:** Lãng phí tài nguyên và chi phí cho DB có lượng dữ liệu nhỏ (10GB) và tải nhẹ như hiện tại.                                                                                                                                                           | **Lãng phí:** `db.t3.medium` Multi-AZ tốn khoảng **$85/tháng** (đắt gấp 3 lần t4g.micro).                              | **Tương đương:** Giống Phương án 1 (RTO < 60s, RPO = 0).                                                                                             |

---

## QUYẾT ĐỊNH PG-03: CHIẾN LƯỢC ROLLBACK SAU KHI CÓ WRITE MỚI (POST-WRITE ROLLBACK)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án A:** Dừng ghi luồng ứng dụng và Đồng bộ ngược (Reverse-Sync & Reconcile).
- **Phương án B:** Chuyển đổi nhanh (Big Bang Switch-Back).
  _(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-3-chiến-lược-rollback-sau-khi-có-write-mới-post-write-rollback))_

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái     | Phương án     | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                                                                     | Rủi ro Vận hành                                                                                                    | RPO & Ảnh hưởng dữ liệu khách hàng                                                                                                  |
| :------------- | :------------ | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------------------------------- |
| **ĐÃ CHỌN**    | `Phương án A` | **Ưu điểm:** Bảo toàn 100% dữ liệu mới (orders, reviews, accounting) phát sinh trên RDS trong thời gian chạy thử nghiệm. Tránh mất mát dữ liệu khách hàng.<br>**Nhược điểm:** Tăng độ phức tạp vận hành do cần chuẩn bị kịch bản đồng bộ ngược và yêu cầu downtime ngắn khi switch-back. | **Trung bình:** Cần chuẩn bị sẵn kịch bản và chạy thử nghiệm trước script đồng bộ ngược để tránh xung đột dữ liệu. | **RPO = 0** (không mất mát dữ liệu khách hàng). Ảnh hưởng tối thiểu đến trải nghiệm người dùng.                                     |
| **BỊ LOẠI BỎ** | `Phương án B` | **Ưu điểm:** Rollback cực nhanh (chỉ cần trỏ lại connection string về EKS cũ).<br>**Nhược điểm:** Chấp nhận mất toàn bộ dữ liệu mới ghi trên RDS kể từ khi cutover. Vi phạm nghiêm trọng tính toàn vẹn dữ liệu tài chính/giao dịch.                                                      | **Thấp:** Thao tác đổi DNS/connection string rất đơn giản và an toàn về mặt vận hành hạ tầng.                      | **RPO > 0** (mất mát dữ liệu mới ghi). Nguy cơ gây lỗi logic ứng dụng và khiếu nại từ khách hàng do mất giỏ hàng/lịch sử giao dịch. |

- **Cách triển khai đề xuất:**
  1. Ngay sau khi cutover thành công sang RDS Postgres, khởi tạo sẵn một AWS DMS Task đồng bộ ngược (Reverse CDC) từ RDS (Source) về lại EKS Postgres (Target) ở trạng thái tạm dừng (Suspended).
  2. Nếu phát hiện lỗi nghiêm trọng kích hoạt Abort trigger, quy trình rollback (truyền dữ liệu ngược về) được thực hiện tuần tự tương ứng với logic truyền dữ liệu đi:
     a. Kích hoạt chạy task Reverse CDC trên AWS DMS để bắt đầu đồng bộ toàn bộ dữ liệu mới ghi từ RDS về lại EKS Postgres.
     b. **Bắt đầu khóa ghi (Stop writes) trên RDS Postgres:** Chạy lệnh SQL khóa ghi trên RDS: `ALTER DATABASE otel SET default_transaction_read_only = on;` (hoặc thu hồi quyền ghi của application user).
     c. **Chờ DMS đồng bộ ngược nốt dữ liệu còn lại:** Giám sát lag của task Reverse CDC cho tới khi về 0 giây (đảm bảo toàn bộ các giao dịch ghi cuối cùng trên RDS đã được chuyển về EKS).
     d. **Reset Sequence trên EKS Postgres:** Chạy script SQL đồng bộ (reset) lại sequences trên EKS Postgres về giá trị `MAX(id) + 1` thực tế để tránh lỗi trùng lặp khóa chính (Duplicate Key) mà không cần tạo khoảng trống logic (Sequence Offsetting).
     e. **Atomic Service Switch chuyển traffic trở lại EKS:** Cập nhật lại selector của Kubernetes Service để trỏ kết nối của clients quay về các Pod chạy trên EKS Postgres (kubectl rollout / patch service).
     f. Dừng task Reverse CDC và dọn dẹp tài nguyên.
- **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Bảo toàn tính tuần tự:** Không switch traffic của clients về EKS khi chưa khóa ghi trên RDS và chưa chờ Reverse CDC lag về 0 để tránh mất mát dữ liệu hoặc ghi đè sai lệch dữ liệu.
  - **Dọn dẹp tài nguyên:** Nếu kết thúc 48 giờ observation window an toàn và hệ thống chạy ổn định trên RDS, bắt buộc phải xóa ngay task Reverse CDC và replication slot trên RDS để tránh tích lũy WAL gây đầy dung lượng đĩa RDS.

---

## QUYẾT ĐỊNH PG-04: THỜI GIAN GIÁM SÁT & DỌN DẸP HẠ TẦNG CŨ (OBSERVATION WINDOW)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án 1:** Standby 48 giờ + Archive S3 7 ngày.
- **Phương án 2:** Xóa ngay lập tức (Immediate Cleanup).
  _(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-4-thời-gian-giám-sát--dọn-dẹp-hạ-tầng-cũ-observation-window))_

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái     | Phương án     | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                                                           | Quy trình dọn dẹp (Cleanup Runbook)                                                                                                            | Khả năng khôi phục khẩn cấp                                                                                                                                |
| :------------- | :------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ĐÃ CHỌN**    | `Phương án 1` | **Ưu điểm:** Biên an toàn rất cao (48 giờ) để kiểm soát tải thực tế, tính ổn định và phát hiện lỗi phát sinh muộn. Lưu trữ bản dump trên S3 giúp bảo toàn dữ liệu lâu dài với chi phí cực kỳ rẻ.<br>**Nhược điểm:** Tạm thời giữ lại tài nguyên PVC 10GB trên EKS thêm 48 giờ. | **Đơn giản:** Sau 48 giờ, tiến hành scale replica của PostgreSQL cũ về 0, chạy script dump dữ liệu lên S3, sau đó chạy lệnh xóa PVC và Pod cũ. | **Rất cao:** Trong 48 giờ đầu tiên, có thể khôi phục tức thời bằng cách scale lại Pod cũ. Sau 48 giờ, có thể khôi phục thông qua tệp dump lưu trữ trên S3. |
| **BỊ LOẠI BỎ** | `Phương án 2` | **Ưu điểm:** Giải phóng tài nguyên CPU/RAM/Disk trên EKS ngay lập tức, tiết kiệm chi phí.<br>**Nhược điểm:** Rất mạo hiểm. Nếu RDS phát sinh lỗi hệ thống sau vài giờ chạy thực tế, không còn bản gốc để đối chiếu hoặc rollback an toàn.                                      | **Không có:** Xóa trực tiếp Pod và PVC cũ mà không qua bước lưu trữ dự phòng.                                                                  | **Không có:** Mất khả năng khôi phục nhanh nếu xảy ra thảm họa dữ liệu trên RDS sau cutover.                                                               |

---

## QUYẾT ĐỊNH PG-05: CƠ CHẾ BẢO MẬT ĐƯỜNG TRUYỀN (TLS MODE FOR CLIENTS)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án A:** TLS Verify-Full (`sslmode=verify-full`).
- **Phương án B:** TLS Prefer/Require (`sslmode=require` hoặc `prefer`).
  _(Chi tiết mô tả xem tại [MANDATE-08-POSTGRESQL-ANALYSIS.md](./MANDATE-08-POSTGRESQL-ANALYSIS.md#quyết-định-5-cơ-chế-bảo-mật-đường-truyền-tls-mode-for-clients))_

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái     | Phương án     | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                                                                                                                      | Độ phức tạp cấu hình Client ứng dụng                                                                                                                           |
| :------------- | :------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **ĐÃ CHỌN**    | `Phương án A` | **Ưu điểm:** Đảm bảo an toàn tuyệt đối cho đường truyền mạng (encryption in-transit) và chống tấn công Man-in-the-Middle (MitM) bằng cách bắt buộc client kiểm tra danh tính chứng chỉ số của RDS Server.<br>**Nhược điểm:** Phải download, quản lý và mount certificate file (`global-bundle.pem`) vào bên trong tất cả các client Pods. | **Trung bình:** Cần tạo ConfigMap chứa cert bundle của AWS và mount vào Pod của client thông qua cấu hình volume trong Helm Chart; cập nhật connection string. |
| **BỊ LOẠI BỎ** | `Phương án B` | **Ưu điểm:** Rất đơn giản, không cần cấu hình mount tệp certificate CA vào client Pod.<br>**Nhược điểm:** Mặc dù đường truyền vẫn được mã hóa, nhưng client không xác thực thực sự RDS server là ai, mở ra nguy cơ bị tấn công giả mạo DNS/Endpoint (tấn công MitM).                                                                      | **Thấp:** Chỉ cần thay đổi tham số `sslmode=require` trong connection string hiện có của ứng dụng.                                                             |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:

- **Cách triển khai đề xuất:**
  1. Tải tệp AWS RDS CA Bundle certificate (`global-bundle.pem`) từ trang chủ AWS.
  2. Tạo một Kubernetes ConfigMap chứa cert này trong namespace của ứng dụng client.
  3. Cập nhật cấu hình Helm Chart của các client pods (`product-catalog`, `product-reviews`, `accounting`): Thiết lập mount volume từ ConfigMap trên thành file `/ssl/global-bundle.pem` bên trong container.
  4. Cấu hình connection string của các ứng dụng dạng:
     `postgresql://<user>:<password>@<rds-endpoint>:5432/otel?sslmode=verify-full&sslrootcert=/ssl/global-bundle.pem`
  5. Restart ứng dụng client và kiểm tra log xem kết nối thành công.
- **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Quyền hạn file cert:** Cần thiết lập `defaultMode: 0444` cho volume mount trong Kubernetes để đảm bảo ứng dụng chạy dưới quyền non-root user vẫn đọc được cert.
  - **Kiểm tra trước:** Thực hiện chạy thử nghiệm kết nối TLS Verify-Full từ một debug pod trong cluster trước khi cấu hình chính thức cho các ứng dụng core.

---

## QUYẾT ĐỊNH PG-06: PHẠM VI AN NINH MẠNG (SECURITY GROUP ACCESS SCOPE)

### 1. Mô tả Quyết định & Các Hướng đề xuất

- **Phương án A (SG-to-SG):** Giới hạn chỉ mở inbound port 5432 cho chính xác Security Group của các client Pod (`product-catalog`, `product-reviews`, `accounting`) và migration runner.
- **Phương án B (Node-to-SG):** Mở rộng port 5432 cho toàn bộ dải IP/Security Group của Worker Nodes EKS.
  _(Chi tiết mô tả xem tại [CDO08-REL-13-managed-data-migration-plan.md](./CDO08-REL-13-managed-data-migration-plan.md#41-network))_

### 2. Phân tích & Lựa chọn của Tech Lead

_(Quyết định này không phát sinh chi phí hạ tầng nên cột Chi phí được lược bỏ)_

| Trạng thái     | Phương án     | Phân tích Trade-offs (Ưu/Nhược điểm)                                                                                                                                                                                                                                                      | Mức độ kiểm soát an ninh (Least Privilege)                                                                                 | Độ phức tạp quản lý Terraform                                                                                                               |
| :------------- | :------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------ |
| **ĐÃ CHỌN**    | `Phương án B` | **Ưu điểm:** Cấu hình thực tế và đơn giản. Cho phép tất cả các Pod cần truy cập DB (bao gồm cả các service phụ, reporting, toolings) kết nối ổn định mà không bị block. Giảm thiểu rủi ro vận hành khi scaling.<br>**Nhược điểm:** Phạm vi truy cập rộng hơn (ở mức Node Level thay vì Pod Level). | **Trung bình:** Vẫn bảo đảm an toàn do RDS nằm trong private subnets, chỉ cho phép traffic nội bộ từ EKS Worker Node Security Group. | **Thấp:** Cấu hình IaC/Terraform cực kỳ đơn giản và ổn định, chỉ cần liên kết Security Group của RDS với Security Group chung của Worker Nodes. |
| **BỊ LOẠI BỎ** | `Phương án A` | **Ưu điểm:** Hạn chế tối đa phạm vi truy cập đến từng Pod chỉ định.<br>**Nhược điểm:** Quá phức tạp và rủi ro. Thực tế có nhiều Pod phụ trợ cần kết nối DB. Nếu chỉ mở cho 3 service core sẽ làm sập các luồng nghiệp vụ khác. Yêu cầu tính năng EKS Security Groups for Pods chưa sẵn sàng. | **Tối đa:** Tuân thủ Least Privilege ở mức cao nhất nhưng không thực tế cho hiện trạng hạ tầng hiện tại. | **Trung bình - Cao:** Yêu cầu khai báo phức tạp và dễ phát sinh lỗi thiếu quyền truy cập khi có Pod mới phát sinh. |
