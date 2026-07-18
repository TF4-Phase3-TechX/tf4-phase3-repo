# Kế hoạch Triển khai Di trú Valkey (EKS -> ElastiCache Valkey)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Cache Engineer

Tài liệu này hướng dẫn chi tiết quy trình migration Valkey lưu trữ giỏ hàng từ cụm EKS tự vận hành sang **Amazon ElastiCache for Valkey** (2-node Multi-AZ). Quy trình này được thiết kế chuẩn chỉn theo phương pháp GitOps và sử dụng **Argo Rollouts** để thực hiện Blue-Green cutover:
- Cụm ElastiCache Valkey được khai báo qua **Terraform** và commit, push, merge vào branch `main` để pipeline tự động apply. Không chạy `terraform apply` thủ công.
- Việc expose EKS Valkey qua NLB và deploy Green pods được cấu hình thông qua **Helm Chart / Values Overrides** và quản lý bằng **Argo Rollouts** dưới cụm EKS.
- Phương án này giúp thực hiện Blue-Green cutover atomic và rollback tức thời bằng nút bấm trên UI hoặc CLI **mà không cần đổi tên Pod, không thêm hậu tố tạm thời, giữ Git sạch sẽ**.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target ElastiCache Group (IaC):** `cache.t4g.micro` (Multi-AZ: 1 Primary + 1 Replica, tự động failover).
* **RAM (IaC):** 0.5 GiB per node.
* **Eviction Policy (IaC):** `maxmemory-policy = volatile-lru` (Thiết lập qua Parameter Group).
* **Phương thức đồng bộ:** AWS ElastiCache Online Migration (Replication link thời gian thực qua NLB).
* **TTL giỏ hàng:** 60 phút (Cấu hình cứng trong code, tự động reset khi có request).
* **SLO Downtime:** Write Pause dự kiến ~10 - 15 giây.

---

## 2. Quản lý Cấu hình & Tệp tin trong Codebase

### A. Hạ tầng AWS (Terraform - IaC)
Hạ tầng được định nghĩa tại thư mục [infra/terraform/](../../../../../infra/terraform):
- [elasticache.tf](../../../../../infra/terraform/elasticache.tf): Định nghĩa `aws_elasticache_replication_group` (Valkey Multi-AZ, tạm thời để `transit_encryption_enabled = false` cho di trú online) và Security Group Rule cho phép cổng 6379 từ EKS Worker Nodes.

### B. Cấu hình Kubernetes (Helm Chart & GitOps)
* **Tiền đề (Prerequisite):** 
  - EKS cluster đã được cài đặt Argo Rollouts Controller.
  - File template [techx-corp-chart/templates/component.yaml](../../../../../techx-corp-chart/templates/component.yaml) hỗ trợ xuất ra `kind: Rollout` cho component `cart` khi cờ `rollouts.enabled = true`.
  - Có sẵn file template K8s Job `techx-corp-chart/templates/riot-redis-backfill-job.yaml` để chạy sync ngược khi rollback.
* **Cấu hình khai báo:**
  - [techx-corp-chart/values.yaml](../../../../../techx-corp-chart/values.yaml):
    - Cấu hình bridge NLB bằng cách sửa `valkey-cart.service.type = LoadBalancer` và thêm annotations tạo internal AWS NLB.
  - [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml):
    - Bật `rollouts.enabled = true` cho component `cart`.
    - Cập nhật connection string của `cart` sang endpoint của ElastiCache Valkey (`redis://`).
    - Khai báo cờ `riot-redis-backfill.enabled = false` (mặc định tắt ở trạng thái bình thường).

### C. Kịch bản chạy (Bash Scripts)
Đặt tại `docs/cdo08/week2/mandate8/scripts/valkey/`:
- `01-preflight-check.sh`
- `02-start-migration.sh`
- `03-monitor-lag.sh`
- `04-freeze-writes.sh`
- `05-complete-migration.sh`
- `06-promote-rollout.sh`
- `07-enable-tls.sh`
- `08-cleanup.sh`
- `rollback-01-abort-rollout.sh`
- `rollback-02-unlock-source.sh`

---

## 3. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường
- [ ] **1.1. Provision ElastiCache (TF):**
  - Khai báo cụm Valkey Multi-AZ trong [elasticache.tf](../../../../../infra/terraform/elasticache.tf) với `transit_encryption_enabled = false` (bắt buộc tắt để AWS migration link kết nối).
  - Commit, push và merge các thay đổi Terraform vào branch `main` để pipeline apply.
  - **Expected Output:** AWS Console hiển thị cụm ElastiCache ở trạng thái `available`.
- [ ] **1.2. Tạo Internal NLB làm cầu nối (GitOps):**
  - Cập nhật file Helm values [techx-corp-chart/values.yaml](../../../../../techx-corp-chart/values.yaml) dưới mục `valkey-cart` để đổi service type sang `LoadBalancer` và thêm annotations cho internal AWS NLB. Commit và push lên Git.
  - Chờ ArgoCD tự động đồng bộ thành công.
  - **Expected Output:** Service LoadBalancer chuyển sang trạng thái Active và nhận IP/DNS nội bộ.
- [ ] **1.3. Kiểm tra tiền di trú & Cổng mạng (Preflight Check):**
  - Chạy script kiểm tra:
    ```bash
    ./scripts/valkey/01-preflight-check.sh
    ```
    - **Script thực hiện:** Kiểm tra target group trên AWS hiển thị các Pods EKS Valkey nguồn ở trạng thái `Healthy`. Chạy `nc -zv <nlb-internal-dns> 6379` từ một pod tạm thời để verify network path thông suốt từ EKS Worker nodes tới ElastiCache.
    - **Expected Output:** Script in `[OK] NLB targets are Healthy` và kết nối thông suốt.

---

### BƯỚC 2: Cấu hình Đồng bộ AWS Online Migration (Live Replication)

- [ ] **2.1. Khởi chạy Replication Link:**
  ```bash
  ./scripts/valkey/02-start-migration.sh
  ```
  - **Script thực hiện:** Chạy `aws elasticache start-migration` trỏ tới NLB DNS endpoint → verify trạng thái chuyển sang `migrating`.
  - **Expected Output:** Script in `[OK] Migration started. Cluster status: migrating`.
- [ ] **2.2. Giám sát trạng thái sync (Giám sát CloudWatch):**
  - **Thực hiện trên AWS Console:**
    1. Truy cập dịch vụ **CloudWatch** -> **Metrics** -> **All metrics**.
    2. Chọn danh mục **ElastiCache** -> **Replication Group Metrics**.
    3. Chọn metric `ReplicationLag` cho Valkey replication group.
    4. Theo dõi biểu đồ cho đến khi độ trễ sync giảm hẳn về mức **0 giây** và giữ ổn định liên tục.
  - **Expected Output:** Biểu đồ độ trễ hiển thị mốc 0 giây ổn định.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause dự kiến: ~10 - 15 giây*

#### GIAI ĐOẠN 1: CHUẨN BỊ (Trước cutover 15-30 phút)
- [ ] **3.1. Đẩy cấu hình ElastiCache lên Git (GitOps):**
  - Cập nhật connection string của component `cart` sang endpoint ElastiCache (`redis://`) trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml). Commit và push lên Git branch.
  - **Cơ chế hoạt động:** Argo Rollouts tự động tạo một ReplicaSet mới (Green pods - trỏ ElastiCache) song song với ReplicaSet cũ (Blue pods - trỏ EKS Valkey). Quá trình deploy tự động dừng ở trạng thái `Paused`, chưa nhận traffic.
  - **Expected Output:** `kubectl get rollout` hiển thị trạng thái `Paused`. Các pod Green mới ở trạng thái `Running` và `1/1 Ready` nhưng chưa nhận traffic.

#### GIAI ĐOẠN 2: THỰC THI CUTOVER
- [ ] **3.2. Khóa ghi trên EKS Valkey cũ:**
  ```bash
  ./scripts/valkey/04-freeze-writes.sh
  ```
  - **Script thực hiện:** Gửi lệnh `CLIENT PAUSE 300000 WRITE` (5 phút) tới EKS Valkey cũ để khóa ghi dữ liệu. Khoảng thời gian 5 phút đảm bảo an toàn tuyệt đối tránh rủi ro mở ghi lại trước khi promote hoàn tất.
  - **Expected Output:** Trả về `OK`. Các lệnh write từ client tạm thời bị treo và xếp hàng.
- [ ] **3.3. Promote cụm ElastiCache:**
  ```bash
  ./scripts/valkey/05-complete-migration.sh
  ```
  - **Script thực hiện:** Chạy `aws elasticache complete-migration` thăng cấp ElastiCache làm Primary R/W (Ngắt replication link từ EKS).
  - **Expected Output:** API phản hồi thành công, status của cụm chuyển sang `completed`.
- [ ] **3.4. Thăng cấp Rollout chuyển traffic (Promote):**
  - Kích hoạt promote trên giao diện ArgoCD UI (nút **Promote**), hoặc chạy script CLI:
    ```bash
    ./scripts/valkey/06-promote-rollout.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts promote cart` và gửi lệnh `CLIENT UNPAUSE` giải phóng kết nối ghi trên EKS Valkey cũ.
  - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service sang ReplicaSet Green ngay lập tức (atomic ~1 giây). Thao tác thêm sản phẩm vào giỏ hàng chạy thành công trên ElastiCache.

#### GIAI ĐOẠN 3: HOÀN TẤT & DỌN DẸP
- [ ] **3.5. Kích hoạt bảo mật TLS không gây gián đoạn kết nối (Zero-Downtime TLS):**
  - Vì đổi TLS đột ngột từ `false` sang `true` sẽ làm đứt kết nối của các pod đang chạy (hoặc pod mới không connect được trước khi DB sẵn sàng TLS), quy trình được thực hiện theo 3 pha an toàn:
    1. **Pha 1 (TF):** Cập nhật [elasticache.tf](../../../../../infra/terraform/elasticache.tf) set `transit_encryption_enabled = true` và cấu hình mode `preferred` (chấp nhận song song cả kết nối TLS `rediss://` và non-TLS `redis://`). Commit, push và merge để pipeline apply.
    2. **Pha 2 (GitOps):** Cập nhật connection string của `cart` trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml) sang `rediss://`. Commit và push Git. Chờ Argo Rollouts rolling update pods mới bắt tay TLS thành công.
    3. **Pha 3 (TF):** Cập nhật [elasticache.tf](../../../../../infra/terraform/elasticache.tf) chuyển mode sang `required` (chỉ chấp nhận kết nối mã hóa TLS). Commit, push và merge để pipeline apply.
  - **Expected Output:** Cụm ElastiCache bắt buộc TLS thành công, ứng dụng kết nối bảo mật ổn định. (Các pod cũ đã tự động bị Argo Rollouts dọn dẹp sau khi promote thành công).
- [ ] **3.6. Dọn dẹp:**
  ```bash
  ./scripts/valkey/08-cleanup.sh
  ```
  - **Script thực hiện:** Hoàn trả cấu hình `valkey-cart` service về ClusterIP trong [techx-corp-chart/values.yaml](../../../../../techx-corp-chart/values.yaml) (xóa bỏ LoadBalancer). Commit và push lên Git. Chạy lệnh xóa StatefulSet Valkey trên EKS.
  - **Expected Output:** Toàn bộ tài nguyên Valkey cũ và NLB trên EKS được giải phóng hoàn toàn.

---

## 4. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra sự cố nghiêm trọng trên ElastiCache trong observation window (24 giờ), tùy thuộc vào trạng thái dữ liệu ghi, thực hiện theo một trong hai kịch bản sau:

### TRƯỜNG HỢP 1: Rollback TRƯỚC KHI có dữ liệu ghi mới vào ElastiCache (RPO = 0)
*Áp dụng khi phát hiện lỗi ngay trong lúc cutover/verify, trước khi mở luồng ghi cho người dùng*

- [ ] **Bước R1.1. Hủy bỏ Rollout (Abort / Switch-Back):**
  - Kích hoạt nút **Abort** trên giao diện ArgoCD UI, hoặc chạy script CLI:
    ```bash
    ./scripts/valkey/rollback-01-abort-rollout.sh
    ```
    - **Script thực hiện:** Chạy lệnh `kubectl argo rollouts abort cart`.
    - **Expected Output:** Argo Rollouts chuyển đổi selector của Active Service quay trở lại ReplicaSet Blue cũ ngay lập tức.
- [ ] **Bước R1.2. Mở khóa ghi trên EKS Valkey cũ:**
  ```bash
  ./scripts/valkey/rollback-02-unlock-source.sh
  ```
  - **Script thực hiện:** Gửi lệnh `CLIENT UNPAUSE` tới EKS Valkey cũ để giải phóng kết nối ghi.
  - **Expected Output:** Pod hoạt động bình thường, tiếp nhận ghi giỏ hàng trên EKS Valkey.

---

### TRƯỜNG HỢP 2: Rollback SAU KHI đã có dữ liệu ghi mới vào ElastiCache (Cần Backfill dữ liệu)
*Áp dụng khi hệ thống đã hoạt động trên ElastiCache một thời gian, phát sinh giỏ hàng mới của khách hàng, nhưng sau đó gặp lỗi nghiêm trọng bắt buộc phải quay lại EKS Valkey*

- [ ] **Bước R2.1. Khóa ghi trên ElastiCache để đóng băng dữ liệu:**
  - Cấu hình tạm dừng write hoặc scale-down app ghi vào giỏ hàng để tránh dữ liệu tiếp tục thay đổi trên ElastiCache.
- [ ] **Bước R2.2. Xóa sạch dữ liệu stale và Backfill từ ElastiCache về EKS Valkey cũ (GitOps):**
  - **Quy trình kích hoạt:**
    1. Cập nhật cờ `riot-redis-backfill.enabled = true` trong [deploy/values-app-stamp.yaml](../../../../../deploy/values-app-stamp.yaml).
    2. Commit và push lên Git để ArgoCD tự động deploy và khởi chạy Job `riot-redis-backfill` trong cụm EKS.
  - **Cơ chế hoạt động của Job container:**
    1. Đầu tiên, Job thực thi lệnh `FLUSHALL` trực tiếp tới EKS Valkey cũ để dọn sạch toàn bộ keys dữ liệu stale/cũ (đảm bảo môi trường đích trống sạch, tránh xung đột key).
    2. Tiếp theo, chạy tool `riot-redis` sử dụng tham số `--mode snapshot` để kéo bản sao dữ liệu mới nhất từ ElastiCache về EKS Valkey.
  - **Expected Output:** Job chạy thành công (`Completed`) trên ArgoCD. Toàn bộ dữ liệu mới nhất từ ElastiCache được copy sang EKS Valkey đầy đủ. Kỹ sư sau đó trả cờ về `enabled = false` và push Git để dọn dẹp Job.
- [ ] **Bước R2.3. Hủy bỏ Rollout & Mở khóa ghi EKS:**
  - Chạy các script hoàn trả traffic và mở ghi:
    ```bash
    ./scripts/valkey/rollback-01-abort-rollout.sh
    ./scripts/valkey/rollback-02-unlock-source.sh
    ```
  - **Expected Output:** Traffic chuyển hướng hoàn toàn về EKS Valkey cũ. Giỏ hàng khách hàng hoạt động bình thường, không bị mất mát dữ liệu mới tạo trên ElastiCache.
