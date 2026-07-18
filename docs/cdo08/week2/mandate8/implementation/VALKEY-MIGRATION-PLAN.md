# Kế hoạch Triển khai Di trú Valkey (EKS -> ElastiCache Valkey)
## CDO08-MANDATE-08 — Kịch bản chi tiết từ A đến Z cho Cache Engineer

Tài liệu này hướng dẫn chi tiết quy trình di trú Valkey lưu trữ giỏ hàng từ cụm EKS tự vận hành sang **Amazon ElastiCache for Valkey** (2-node Multi-AZ). Kế hoạch này được thiết kế để một kỹ sư có thể thực thi độc lập và tự kiểm tra kết quả thông qua các **Kết quả mong muốn (Expected Output)** đi kèm mỗi bước.

---

## 1. Thông số Kỹ thuật & Cấu hình Đích
* **Target ElastiCache Group:** `cache.t4g.micro` (Multi-AZ: 1 Primary + 1 Replica, tự động failover).
* **RAM:** 0.5 GiB per node (Dung lượng dư thừa lớn cho active keys của storefront).
* **Eviction Policy:** `maxmemory-policy = volatile-lru` (Tự động giải phóng các key có TTL khi đầy đĩa/RAM).
* **Phương thức đồng bộ:** AWS ElastiCache Online Migration (Replication link thời gian thực qua NLB).
* **SLO Downtime:** Dưới 3 phút (Downtime Write Pause thực tế dự kiến chỉ ~10 - 30 giây ở giai đoạn cutover connection string).

---

## 2. Quy trình Thực hiện từng bước (Step-by-Step)

### BƯỚC 1: Chuẩn bị Môi trường (Preparation)
- [ ] **1.1. Khởi tạo ElastiCache:** Sử dụng Terraform provision cụm ElastiCache for Valkey.
  - *Lưu ý quan trọng:* **Chưa kích hoạt mã hóa đường truyền (Transit Encryption/TLS)** ở bước này để AWS Online Migration có thể kéo dữ liệu (yêu cầu bắt buộc của AWS).
- [ ] **1.2. Mở thông cổng mạng:**
  - Cấu hình Security Group của ElastiCache cho phép nhận inbound port `6379` từ IP range của cụm EKS Worker Nodes.
- [ ] **1.3. Setup EKS Bridge:**
  - Tạo một Internal Network Load Balancer (NLB) trên cụm EKS trỏ endpoint về Service của Pod Valkey cũ đang chạy.
  - Cấu hình NLB lắng nghe cổng `6379`.
  - **Kết quả mong muốn (Expected Output):** 
    - Service LoadBalancer được tạo thành công trong K8s và nhận địa chỉ Internal DNS của NLB.
    - Trên AWS Console, Target Group của NLB hiển thị các pod IPs của EKS Valkey ở trạng thái `Healthy`.
    - Chạy thử lệnh kiểm tra kết nối từ một pod tạm thời khác trong cùng cụm EKS (cùng VPC) tới địa chỉ DNS nội bộ của NLB thành công:
      ```bash
      nc -zv <nlb-internal-dns> 6379
      # Output mong muốn: Connection to <nlb-internal-dns> 6379 port [tcp/redis] succeeded!
      ```

---

### BƯỚC 2: Cấu hình Đồng bộ AWS Online Migration (Live Replication)
- [ ] **2.1. Khởi chạy Replication Link:**
  - Chạy lệnh AWS CLI để liên kết cụm ElastiCache với NLB của EKS:
    ```bash
    aws elasticache start-migration \
      --replication-group-id valkey-cart-group \
      --customer-node-endpoint-list "Address='valkey-eks-internal-nlb.us-east-1.elb.amazonaws.com',Port=6379"
    ```
  - **Kết quả mong muốn (Expected Output):** Phản hồi JSON trả về thông tin migration link, trạng thái chuyển sang `migrating`.
- [ ] **2.2. Giám sát trạng thái sync:**
  - Theo dõi trạng thái migration qua AWS Console và metric `ReplicationLag` trên CloudWatch.
  - **Kết quả mong muốn (Expected Output):**
    - Trạng thái cụm trên AWS Console hiển thị `migrating`.
    - Chỉ số `ReplicationLag` trên CloudWatch giảm dần về `0` giây và giữ ổn định ở mức này.

---

### BƯỚC 3: Cắt chuyển Hệ thống (Cutover Window)
*Thực hiện vào khung giờ thấp điểm (02:00 AM - 04:00 AM) — Downtime Write Pause dự kiến: ~10 - 15 giây*

#### GIAI ĐOẠN 1: CHUẨN BỊ (Trước cutover 15-30 phút)
- [ ] **3.1. Triển khai Deployment Green (trỏ sang ElastiCache):**
  - Deploy Deployment mới của `cart` service (`cart-rds`) với connection string trỏ tới ElastiCache endpoint (dùng protocol `redis://` — TLS chưa bật trong giai đoạn migration).
  - Chờ Green pods vượt qua `readinessProbe` và đạt trạng thái `Running`.
  - *Lưu ý:* ElastiCache đang ở trạng thái `migrating` (read-only replica). Green pods có thể kết nối đọc data nhưng chưa ghi được — điều này bình thường và không ảnh hưởng readiness.
  - **Kết quả mong muốn (Expected Output):**
    - `kubectl get pods -l version=elasticache` hiển thị `Running` và `1/1 Ready`.
    - Log pod hiển thị kết nối thành công tới ElastiCache endpoint, không có lỗi TCP/authentication.

#### GIAI ĐOẠN 2: THỰC THI CUTOVER
- [ ] **3.2. Khóa ghi trên EKS Valkey (Freeze Writes):**
  - Chạy lệnh khóa ghi tạm thời trên cụm cũ để dữ liệu tĩnh tuyệt đối trong lúc sync nốt lag:
    ```bash
    redis-cli -h <eks-valkey-ip> CLIENT PAUSE 30000 WRITE
    ```
  - **Kết quả mong muốn (Expected Output):** Command trả về `OK`. Các lệnh `SET`, `HSET` gửi tới EKS Valkey sẽ bị treo xếp hàng trong tối đa 30 giây.
- [ ] **3.3. Promote ElastiCache (Complete Migration):**
  - Chờ `ReplicationLag` trên CloudWatch về `0`, sau đó chạy lệnh thăng cấp ElastiCache lên Read-Write:
    ```bash
    aws elasticache complete-migration --replication-group-id valkey-cart-group
    ```
  - **Kết quả mong muốn (Expected Output):** AWS API phản hồi thành công. Trạng thái migration đổi sang `completed`. ElastiCache bây giờ là Primary Read-Write độc lập.
- [ ] **3.4. Atomic Service Switch (chuyển traffic sang Green):**
  - Cập nhật Kubernetes Service selector trỏ traffic sang Deployment Green:
    ```bash
    kubectl patch service cart-service -p '{"spec":{"selector":{"version":"elasticache"}}}'
    ```
  - **Kết quả mong muốn (Expected Output):**
    - `kubectl get svc cart-service` hiển thị selector `version=elasticache`.
    - Thử thêm sản phẩm vào giỏ hàng thực tế trên storefront — thao tác thành công và data xuất hiện trên ElastiCache.
    - Log các Green pods hiển thị các lệnh `SET`/`GET` giỏ hàng thành công trên ElastiCache.

#### GIAI ĐOẠN 3: HOÀN TẤT & DỌN DẸP
- [ ] **3.5. Kích hoạt TLS sau cutover:**
  - Cập nhật cấu hình Terraform để kích hoạt **In-transit Encryption (TLS)** trên ElastiCache.
  - Cập nhật connection string của Deployment Green sang `rediss://` và rolling update lại pods.
  - **Kết quả mong muốn (Expected Output):** Log pod hiển thị kết nối `rediss://` thành công, không có lỗi TLS handshake.
- [ ] **3.6. Dọn dẹp:**
  - Xóa Deployment cũ (Blue pods trỏ EKS Valkey).
  - Xóa Service LoadBalancer NLB trung gian trên EKS.
  - Xóa StatefulSet Valkey cũ trên EKS.


---

## 3. Kịch bản ứng phó sự cố & Rollback (Rollback Playbook)

Nếu xảy ra lỗi mất kết nối giỏ hàng hàng loạt hoặc lỗi logic sau khi cutover:

- [ ] **Bước R.1 (Atomic Switch-Back — Ưu tiên số 1):**
  - Cập nhật ngay Kubernetes Service selector trỏ ngược về Blue Deployment (EKS Valkey cũ):
    ```bash
    kubectl patch service cart-service -p '{"spec":{"selector":{"version":"eks"}}}'
    ```
  - *Lý do làm trước:* Switch selector dừng ngay luồng write mới vào ElastiCache (atomic ~1 giây). ElastiCache không nhận write mới → trở thành nguồn dữ liệu đóng băng tự nhiên. Không cần CLIENT PAUSE.
  - **Kết quả mong muốn (Expected Output):** `kubectl get svc cart-service` hiển thị selector `version=eks`. Log Blue pods xác nhận write giỏ hàng thành công trên EKS Valkey.
- [ ] **Bước R.2 (Backfill dữ liệu mới từ ElastiCache về EKS Valkey):**
  - Chạy Kubernetes Job chứa công cụ **RIOT-Redis** để sync ngược các giỏ hàng mới (được tạo trong observation window) từ ElastiCache về lại EKS Valkey:
    ```bash
    riot-redis replicate \
      --source <elasticache-endpoint>:6379 \
      --target <eks-valkey-ip>:6379 \
      --mode snapshot
    ```
  - *Lý do dùng `--mode snapshot` thay vì `live`:* Vì ElastiCache đã ngừng nhận write mới (traffic đã về EKS Valkey ở R.1), dữ liệu trên ElastiCache là hữu hạn và cố định. RIOT chạy một lần duy nhất, drain hết rồi tự kết thúc. Lag về 0 tự nhiên.
  - **Kết quả mong muốn (Expected Output):** Log RIOT-Redis hiển thị tiến độ sync key count, kết thúc bằng thông báo hoàn thành. Số key trên EKS Valkey bằng hoặc lớn hơn ElastiCache (do EKS Valkey đã tiếp nhận write mới trong lúc RIOT chạy).
- [ ] **Bước R.3 (Verify):** Kiểm tra giỏ hàng hoạt động bình thường trên storefront. Thêm sản phẩm vào giỏ hàng và xác nhận data lưu thành công trên EKS Valkey.
