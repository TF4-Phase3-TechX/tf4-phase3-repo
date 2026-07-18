# Kế hoạch Triển khai Di trú Valkey (EKS -> ElastiCache Valkey)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Cache Engineer

Tài liệu này hướng dẫn chi tiết quy trình migration Valkey lưu trữ giỏ hàng từ cụm EKS tự vận hành sang **Amazon ElastiCache for Valkey** (2-node Multi-AZ). Quy trình này được thiết kế chuẩn theo phương pháp GitOps và sử dụng **Argo Rollouts** để thực hiện Blue-Green cutover.

> [!IMPORTANT]
> **Tài liệu Tiền đề Chung:**
> Trước khi thực hiện kế hoạch này, bạn bắt buộc phải đọc và hoàn thành các bước thiết lập trong tài liệu [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md). Tài liệu này chứa hướng dẫn cài đặt Argo Rollouts, cấu hình bảo mật mạng, và định nghĩa các điều kiện ràng buộc hạ tầng.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target ElastiCache Group:** `cache.t4g.micro` (Multi-AZ: 1 Primary + 1 Replica, tự động failover).
* **RAM:** 0.5 GiB per node.
* **Eviction Policy:** `maxmemory-policy = volatile-lru` (Thiết lập qua Parameter Group).
* **Phương thức đồng bộ:** AWS ElastiCache Online Migration (Replication link thời gian thực qua NLB).
* **TTL giỏ hàng:** 60 phút (Cấu hình trong code, tự động reset khi có request).
* **Mục tiêu SLO Downtime (Có điều kiện):** Write Pause dự kiến ~10 - 15 giây.

---

## 2. Quản lý Cấu hình & Tệp tin trong Codebase

> [!WARNING]
> **Trạng thái Codebase:** Các tệp tin cấu hình và script dưới đây **CHƯA TỒN TẠI** trong repo hiện tại. Chúng được lập lịch để **tạo trong Pull Request (PR) triển khai sau khi bản kế hoạch này được phê duyệt**.

### A. Hạ tầng AWS (Terraform - IaC)
Sẽ được định nghĩa tại thư mục [infra/terraform/](../../../../../infra/terraform) trong PR triển khai:
- `elasticache.tf`: Định nghĩa `aws_elasticache_replication_group` (Valkey Multi-AZ, tạm thời để `transit_encryption_enabled = false` phục vụ online migration) và Security Group Rule cho phép cổng 6379 từ EKS Worker Nodes / NLB.

### B. Cấu hình Kubernetes (Helm Chart & GitOps)
Sẽ được bổ sung/chỉnh sửa trong PR triển khai:
- `techx-corp-chart/templates/valkey-migration-bridge.yaml`: Định nghĩa Service `LoadBalancer` nội bộ (Internal NLB) trỏ tới Pod Valkey tự vận hành hiện tại để ElastiCache Online Migration có thể kéo dữ liệu.
- `techx-corp-chart/templates/riot-redis-backfill-job.yaml`: Bản mẫu K8s Job để chạy sync ngược dữ liệu sử dụng công cụ `riot-redis` khi xảy ra sự cố cần rollback.
- `techx-corp-chart/templates/component.yaml`: Cập nhật hỗ trợ xuất ra tài nguyên `kind: Rollout` khi cờ `rollouts.enabled = true`.
- `deploy/values-app-stamp.yaml`:
  - Bật `rollouts.enabled = true` cho component `cart`.
  - Cập nhật connection string của `cart` sang endpoint của ElastiCache Valkey (`redis://`).
  - Khai báo cờ `riot-redis-backfill.enabled = false` (mặc định tắt ở trạng thái bình thường).

### C. Kịch bản chạy (Bash Scripts)
Sẽ được tạo tại `docs/cdo08/week2/mandate8/scripts/valkey/` trong PR triển khai:
- `01-preflight-check.sh` (Verify kết nối mạng, chạy thử ping)
- `test-migration-connection.sh` (Chạy thử nghiệm liên kết kiểm tra cổng mạng trước khi bắt đầu)
- `02-start-migration.sh` (Bắt đầu gọi API start-migration của ElastiCache)
- `03-monitor-lag.sh` (Giám sát lag đồng bộ)
- `04-freeze-writes.sh` (Khóa ghi trên EKS Valkey bằng CLIENT PAUSE)
- `05-complete-migration.sh` (Thăng cấp ElastiCache, ngắt link)
- `06-promote-rollout.sh` (Thăng cấp Argo Rollout chuyển traffic)
- `07-enable-tls.sh` (Pha 3 bước nâng cấp bảo mật TLS preferred -> required)
- `08-cleanup.sh` (Dọn dẹp tài nguyên cũ)
- `rollback-01-abort-rollout.sh` / `rollback-02-unlock-source.sh`

---

## 3. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường

- [ ] **1.1. Cài đặt Argo Rollouts:** Đảm bảo bước **P1.1** và **P1.2** trong [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md) đã hoàn thành.
- [ ] **1.2. Tạo Internal NLB làm cầu nối (GitOps):**
  - Triển khai `valkey-migration-bridge.yaml` để tạo AWS NLB nội bộ trỏ tới Valkey Pod hiện tại (xem chi tiết tại phần **2.2.B** của [COMMON-PREREQUISITES.md](./COMMON-PREREQUISITES.md)).
  - Chờ Service nhận IP/DNS nội bộ của AWS.
- [ ] **1.3. Provision ElastiCache (TF):**
  - Khai báo cụm Valkey Multi-AZ trong `elasticache.tf` với `transit_encryption_enabled = false` (bắt buộc tắt để AWS migration link kết nối).
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline apply.
  - **Expected Output:** AWS Console hiển thị cụm ElastiCache ở trạng thái `available`.
- [ ] **1.4. Cổng Kiểm duyệt: Chạy Thử nghiệm Kết nối (Test Migration Gateway):**
  - Trước khi gọi lệnh di trú chính thức, chạy script test để đảm bảo cổng kết nối mạng thông suốt:
    ```bash
    ./scripts/valkey/test-migration-connection.sh
    ```
    - **Thực hiện:** Script spin-up debug pod kết nối thử tới NLB DNS endpoint từ VPC Subnet ngoài EKS, đồng thời gọi lệnh dry-run API của AWS ElastiCache.
    - **Expected Output:** Script trả về `[OK] Port 6379 on internal NLB is reachable from VPC subnets.`

---

### BƯỚC 2: Cấu hình Đồng bộ AWS Online Migration (Live Replication)

- [ ] **2.1. Khởi chạy Replication Link:**
  ```bash
  ./scripts/valkey/02-start-migration.sh
  ```
  - **Script thực hiện:** Chạy `aws elasticache start-migration` trỏ tới NLB DNS endpoint → verify trạng thái chuyển sang `migrating`.
- [ ] **2.2. Giám sát trạng thái sync (Giám sát CloudWatch):**
  - Theo dõi trực tiếp metrics `ReplicationLag` trên CloudWatch cho đến khi độ trễ sync giảm hẳn về mức **0 giây** và giữ ổn định liên tục.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause dự kiến: ~10 - 15 giây*

#### GIAI ĐOẠN 1: CHUẨN BỊ (Trước cutover 15-30 phút)
- [ ] **3.1. Đẩy cấu hình ElastiCache lên Git (GitOps):**
  - Cập nhật connection string của component `cart` sang endpoint ElastiCache (`redis://`) trong `deploy/values-app-stamp.yaml`. Commit và push lên Git branch.
  - **Cơ chế hoạt động:** Argo Rollouts tự động tạo một ReplicaSet mới (Green pods - trỏ ElastiCache) song song với ReplicaSet cũ (Blue pods - trỏ EKS Valkey) và tạm dừng ở trạng thái `Paused`, chưa nhận traffic.
  - **Expected Output:** `kubectl get rollout` hiển thị trạng thái `Paused`. Các pod Green mới ở trạng thái `Running` và `1/1 Ready` nhưng chưa nhận traffic.

#### GIAI ĐOẠN 2: THỰC THI CUTOVER
- [ ] **3.2. Khóa ghi trên EKS Valkey cũ:**
  ```bash
  ./scripts/valkey/04-freeze-writes.sh
  ```
  - **Script thực hiện:** Gửi lệnh `CLIENT PAUSE 300000 WRITE` (5 phút) tới EKS Valkey cũ để khóa ghi dữ liệu. 
- [ ] **3.3. Thực hiện Đối soát Dữ liệu Trước Cutover:**
  - Thực hiện kiểm tra theo **Mục 5.1: Đối soát Dữ liệu Trước Cutover (Pre-Cutover Parity Check)** bên dưới để đảm bảo dữ liệu 2 bên khớp hoàn toàn trước khi promote.
- [ ] **3.4. Promote cụm ElastiCache:**
  ```bash
  ./scripts/valkey/05-complete-migration.sh
  ```
  - **Script thực hiện:** Chạy `aws elasticache complete-migration` thăng cấp ElastiCache làm Primary R/W (Ngắt replication link từ EKS).
- [ ] **3.5. Thăng cấp Rollout chuyển traffic (Promote):**
  - Kích hoạt promote trên giao diện ArgoCD UI (nút **Promote**), hoặc chạy script CLI:
    ```bash
    ./scripts/valkey/06-promote-rollout.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts promote cart` và gửi lệnh `CLIENT UNPAUSE` giải phóng kết nối ghi trên EKS Valkey cũ.
- [ ] **3.6. Thực hiện Đối soát Dữ liệu Sau Cutover:**
  - Thực hiện kiểm tra theo **Mục 5.2: Đối soát Dữ liệu Sau Cutover (Post-Cutover Parity Check)** bên dưới.

#### GIAI ĐOẠN 3: HOÀN TẤT & DỌN DẸP
- [ ] **3.7. Kích hoạt bảo mật TLS không gây gián đoạn kết nối (Zero-Downtime TLS):**
  - Cập nhật theo quy trình 3 pha bảo mật nêu tại **Mục 3.5** trong file kế hoạch cũ để kích hoạt an toàn TLS trên ElastiCache.
- [ ] **3.8. Dọn dẹp:**
  ```bash
  ./scripts/valkey/08-cleanup.sh
  ```
  - Hoàn trả cấu hình `valkey-cart` service về ClusterIP trong `techx-corp-chart/values.yaml` (xóa bỏ LoadBalancer). Commit và push lên Git. Chạy lệnh xóa StatefulSet Valkey trên EKS.

---

## 4. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng trên ElastiCache trong observation window (24 giờ), thực hiện theo một trong hai kịch bản sau:

### TRƯỜNG HỢP 1: Rollback TRƯỚC KHI có dữ liệu ghi mới vào ElastiCache (RPO = 0)
- [ ] **Bước R1.1. Hủy bỏ Rollout (Abort / Switch-Back):**
  - Chạy script:
    ```bash
    ./scripts/valkey/rollback-01-abort-rollout.sh
    ```
- [ ] **Bước R1.2. Mở khóa ghi trên EKS Valkey cũ:**
  ```bash
  ./scripts/valkey/rollback-02-unlock-source.sh
  ```

### TRƯỜNG HỢP 2: Rollback SAU KHI đã có dữ liệu ghi mới vào ElastiCache (Cần Backfill dữ liệu)
- [ ] **Bước R2.1. Khóa ghi trên ElastiCache để đóng băng dữ liệu:** Dừng ghi luồng giỏ hàng mới vào ElastiCache.
- [ ] **Bước R2.2. Xóa dữ liệu stale & Backfill ngược từ ElastiCache về EKS Valkey cũ:**
  1. Cập nhật cờ `riot-redis-backfill.enabled = true` trong `deploy/values-app-stamp.yaml`.
  2. Commit và push Git để ArgoCD tự deploy và chạy Job `riot-redis-backfill`.
  3. Job tự động gọi `FLUSHALL` trên EKS Valkey cũ, sau đó sử dụng công cụ `riot-redis` kéo snapshot dữ liệu mới nhất từ ElastiCache về EKS Valkey.
- [ ] **Bước R2.3. Hủy bỏ Rollout & Mở khóa ghi EKS:**
  - Chạy các script `rollback-01-abort-rollout.sh` và `rollback-02-unlock-source.sh` để trả traffic về EKS Valkey.

---

## 5. Quy trình Kiểm thử và Đối soát Dữ liệu (Data Parity Checklist)

### 5.1. Đối soát Dữ liệu Trước Cutover (Pre-Cutover Parity Check)
Thực hiện ngay sau khi EKS Valkey đã được khóa ghi (Bước 3.2) và trước khi thăng cấp ElastiCache (Bước 3.4):

- [ ] **K-1. Đối soát Số lượng Keys (Keyspace Size Verification):**
  * Kết nối vào EKS Valkey và target ElastiCache, chạy lệnh `DBSIZE` hoặc `INFO keyspace` để đối chiếu số lượng key hiện tại.
  * **Tiêu chuẩn đạt:** Tổng số lượng key trên target ElastiCache khớp ít nhất 99.9% so với EKS Valkey (một số ít key có thể đã hết hạn TTL trong quá trình đồng bộ và tự động bị xóa).
- [ ] **K-2. Kiểm tra Trạng thái Replication Link trên AWS Console:**
  * Truy cập dịch vụ ElastiCache, kiểm tra trạng thái replication group.
  * **Tiêu chuẩn đạt:** Trạng thái liên kết di trú hiển thị `synchronizing` hoặc `active`, và `ReplicationLag` trên CloudWatch bằng 0.

---

### 5.2. Đối soát Dữ liệu Sau Cutover (Post-Cutover Parity Check)
Thực hiện sau khi đã chuyển traffic thành công sang ElastiCache (Bước 3.5):

- [ ] **A-1. Kiểm tra Tính năng Ghi Giỏ Hàng (Cart Write Verification):**
  * Đóng vai trò client, thử thêm một sản phẩm mới vào giỏ hàng.
  * **Tiêu chuẩn đạt:** Yêu cầu API trả về thành công (HTTP 200/201). Chạy `GET cart:<user_id>` trên ElastiCache trả về đúng thông tin giỏ hàng vừa thêm.
- [ ] **A-2. Kiểm tra TTL đồng bộ:**
  * Verify các key giỏ hàng mới tạo trên ElastiCache có đúng TTL (60 phút) hay không.
  * *Lệnh kiểm tra:*
    ```bash
    redis-cli -h <elasticache_endpoint> TTL cart:<user_id>
    ```
    *Expected Output:* Số giây còn lại phải lớn hơn 0 và nhỏ hơn hoặc bằng 3600.
- [ ] **A-3. Kiểm tra Tính năng Backfill phục vụ Rollback (Dry-run):**
  * Chạy thử Job `riot-redis-backfill` trong môi trường staging/test để đảm bảo script `riot-redis` hoạt động tốt, có thể copy chính xác cấu trúc key từ ElastiCache về lại EKS Valkey mà không gặp lỗi phân tích schema.

