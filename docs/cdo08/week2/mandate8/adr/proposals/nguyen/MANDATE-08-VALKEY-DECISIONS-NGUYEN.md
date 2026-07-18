# Mandate 8 - Valkey Migration Decisions & ADR Record

- **Trạng thái:** Đã hoàn thiện thiết kế độc lập (Approved - Pending review)

Tài liệu này cung cấp khung mẫu quyết định thiết kế kiến trúc (ADR format) dạng bảng so sánh đã được Tech Lead hoàn thiện độc lập. Khung hướng dẫn triển khai mô tả chi tiết quy trình thực hiện và các lưu ý phòng ngừa lỗi cho phương án được chọn ở các quyết định kỹ thuật phức tạp.

---

## QUYẾT ĐỊNH VK-01: LỰA CHỌN CHÍNH SÁCH DỮ LIỆU GIỎ HÀNG (CART DATA POLICY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Di trú giỏ hàng đang hoạt động (Active Cart Migration).
* **Phương án B:** Chuyển đổi lạnh (Cold Cutover / Discard Carts).
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-1-lựa-chọn-chính-sách-dữ-liệu-giỏ-hàng-cart-data-policy))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Ảnh hưởng Trải nghiệm Khách hàng (SLO) |
| :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án A: Active Cart Migration` | **Ưu điểm:** Bảo toàn 100% giỏ hàng của người dùng đang hoạt động trong hệ thống. Khách hàng không bị mất sản phẩm đã chọn khi hệ thống chuyển đổi.<br>**Nhược điểm:** Tăng độ phức tạp của quy trình di trú dữ liệu, đòi hỏi đồng bộ dữ liệu động (live migration) và quản lý chặt chẽ TTL của keys. | **Tốt nhất:** Đảm bảo trải nghiệm mua sắm mượt mà, không làm gián đoạn hành trình khách hàng và bảo vệ SLO đặt hàng (Order Success Rate). |
| **BỊ LOẠI BỎ** | `Phương án B: Cold Cutover / Discard Carts` | **Ưu điểm:** Cực kỳ đơn giản về mặt vận hành, chỉ cần chuyển hướng endpoint sang Valkey mới mà không cần di trú dữ liệu.<br>**Nhược điểm:** Xóa sạch toàn bộ giỏ hàng hiện tại của khách hàng. Khách hàng đang online sẽ thấy giỏ hàng bị trống rỗng đột ngột. | **Kém:** Gây trải nghiệm xấu cho người dùng, làm mất các đơn hàng tiềm năng đang chờ thanh toán, ảnh hưởng tiêu cực đến doanh thu và vi phạm SLO. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Inventory & Phân tích cấu trúc key:** Khảo sát cấu trúc key của giỏ hàng hiện tại trong EKS Valkey (ví dụ: định dạng key `cart:<session_id>` hoặc `cart:<user_id>`). Xác định các kiểu dữ liệu sử dụng (Hash, String, v.v.).
  2. **Thiết lập hạ tầng đích:** Provision instance ElastiCache Valkey đích (theo cấu hình ở VK-02) và đảm bảo thông luồng mạng (network path) từ EKS Worker Nodes tới target.
  3. **Đồng bộ hóa dữ liệu giỏ hàng động (Active Sync):**
     * Kết hợp với kỹ thuật di trú ở VK-03 (sử dụng AWS ElastiCache Online Migration).
     * AWS tự động thiết lập replication link để đồng bộ toàn bộ keys hiện có và keys ghi nhận mới trong thời gian thực sang ElastiCache target.
  4. **Bảo toàn TTL (Time-To-Live):** AWS Online Migration tự động bảo toàn TTL còn lại của các key từ nguồn sang đích trong quá trình replication.
  5. **Cutover (Chuyển đổi endpoint):** Cập nhật cấu hình connection string của `cart` service sang endpoint ElastiCache Valkey mới bằng cơ chế Blue-Green Pod deployment (hoặc atomic update config/secret).
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Tránh tràn bộ nhớ (OOM) target:** Trước khi import, kiểm tra dung lượng RAM sử dụng thực tế của Valkey nguồn để đảm bảo target instance có đủ tài nguyên chứa toàn bộ dữ liệu kèm overhead khi vận hành.
  - **Giám sát Key Eviction:** Cần cấu hình CloudWatch Alarm và monitor số lượng key bị xoá do hết hạn (evicted) trên cả nguồn và đích trong suốt quá trình di trú.

---

## QUYẾT ĐỊNH VK-02: CẤU HÌNH TARGET ELASTICACHE (HA, SIZING INSTANCE & REPLICAS)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Cấu hình 2-node Multi-AZ (`cache.t4g.micro`, 1 primary + 1 replica, tự động failover).
* **Phương án 2:** Cấu hình Single-Node (`cache.t4g.micro`, chỉ chạy duy nhất 1 node đơn lẻ).
* **Phương án 3:** Cấu hình instance lớn hơn (`cache.m7g.large` trở lên) hoặc tăng số lượng replica.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-2-cấu-hình-target-elasticache-ha-vs-single-node))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Phân tích Chi phí (Cost) | Khả năng Sẵn sàng (HA) |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án 1: Cấu hình 2-node Multi-AZ` | **Ưu điểm:** Đảm bảo High Availability (HA) cấp độ Production. Sử dụng chip Graviton2 (`cache.t4g.micro`) tối ưu hiệu năng/chi phí.<br>**Nhược điểm:** Chi phí gấp đôi so với Single-Node. | **Phù hợp:** Chi phí khoảng **$23.36/tháng** (khoảng **$5.4/tuần**) cho 2 nodes (`cache.t4g.micro`). Rất rẻ và nằm trong ngân sách. | **Rất cao (RTO < 60s):** Failover tự động sang replica ở AZ khác khi node Primary bị lỗi nhờ cơ chế AWS ElastiCache. |
| **BỊ LOẠI BỎ** | `Phương án 2: Cấu hình Single-Node` | **Ưu điểm:** Tiết kiệm tối đa chi phí.<br>**Nhược điểm:** Không có khả năng HA. Nếu node gặp sự cố, hệ thống sẽ bị gián đoạn hoàn toàn (Single Point of Failure). | **Rẻ nhất:** Chi phí khoảng **$11.68/tháng** (khoảng **$2.7/tuần**). | **Thấp:** Phải chờ node tự khởi động lại hoặc recreate thủ công nếu lỗi phần cứng vật lý. |
| **BỊ LOẠI BỎ** | `Phương án 3: Cấu hình instance lớn hơn` | **Ưu điểm:** Dư thừa hiệu năng lớn.<br>**Nhược điểm:** Lãng phí tài nguyên và ngân sách cho DB giỏ hàng có lượng dữ liệu nhỏ (hiện trạng nguồn chỉ dùng PVC 5GB và dữ liệu thực tế rất nhỏ). | **Đắt/Lãng phí:** Chi phí lớn (ví dụ `cache.m7g.large` Multi-AZ tốn khoảng **$130+/tháng**). | **Tương đương:** Giống Phương án 1 (RTO < 60s, RPO gần 0). |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Provisioning via IaC (Terraform):** Tạo `aws_elasticache_replication_group` trong Terraform với `node_type = "cache.t4g.micro"`, `num_cache_clusters = 2` (1 primary + 1 replica), và bật `multi_az_enabled = true`.
  2. **Cấu hình Parameter Group:** Thiết lập `maxmemory-policy = volatile-lru` (hoặc `allkeys-lru`) để tự động thu hồi bộ nhớ từ các key có thiết lập TTL khi bộ nhớ đầy.
  3. **Network & Security:** Cấu hình Security Group cho ElastiCache chỉ nhận inbound port `6379` từ Security Group của Worker Nodes EKS. Đặt các subnet của ElastiCache trong Private Subnet Group.
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Sự cố AZ:** Luôn chắc chắn rằng 2 node được phân bổ trên 2 Availability Zones (AZs) khác nhau để đạt tiêu chuẩn Multi-AZ thực sự.
  - **Overhead bộ nhớ:** Instance `cache.t4g.micro` có 0.5 GB RAM. Cần giám sát chặt chẽ tham số `reserved-memory-percent` (mặc định của AWS thường là 25%) để đảm bảo Valkey luôn có bộ nhớ trống cho quá trình failover/sync mà không bị OOM.

## QUYẾT ĐỊNH VK-03: LỰA CHỌN KỸ THUẬT DI TRÚ (MIGRATION TECHNIQUE)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** RDB Export & Import (Offline Migration).
* **Phương án B:** AWS ElastiCache Online Migration (Online Replication - thay thế cho phương án Dual-write tự viết).
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-3-lựa-chọn-kỹ-thuật-di-trú-migration-technique))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu sửa đổi Code ứng dụng | Độ phức tạp Vận hành |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án B: AWS ElastiCache Online Migration` | **Ưu điểm:** Di trú online thời gian thực. Không yêu cầu sửa đổi code ứng dụng (API compatibility). Quá trình đồng bộ được AWS quản lý tự động dưới dạng replication link. Downtime tối thiểu (chỉ dừng ghi 1-3 phút trong lúc rolling update ứng dụng trỏ sang endpoint mới).<br>**Nhược điểm:** Phải mở thông luồng mạng từ EKS tới ElastiCache qua internal NLB. Yêu cầu tắt tạm thời TLS trên ElastiCache target trong lúc migration (sau cutover sẽ bật lại). | **Không có:** Chỉ cần cập nhật connection string trong cấu hình Helm values/ConfigMap của `cart` service. | **Trung bình:** Cần quản lý vòng đời migration qua CLI/Console và điều phối bước cutover. |
| **BỊ LOẠI BỎ** | `Phương án A: RDB Export & Import` | **Ưu điểm:** Đơn giản về mặt kỹ thuật, không cần giữ kết nối đồng bộ trực tiếp giữa EKS và RDS.<br>**Nhược điểm:** Yêu cầu dừng toàn bộ luồng ghi ứng dụng từ lúc bắt đầu export RDB đến khi import xong trên ElastiCache. Với dung lượng 5GB, downtime có thể kéo dài từ 5-15 phút, gây ảnh hưởng nghiêm trọng đến trải nghiệm người dùng (SLO đặt hàng). | **Không có** | **Thấp** |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Chuẩn bị Network Path:** Tạo một Internal Network Load Balancer (NLB) trong EKS trỏ tới Pod EKS Valkey nguồn. Cấu hình Security Group của EKS Node/NLB cho phép IP của cụm ElastiCache đích kết nối đến port `6379`.
  2. **Khởi tạo ElastiCache Target:** Khởi tạo cụm ElastiCache Valkey mới (tạm thời không bật In-transit Encryption/TLS ở bước này để đáp ứng yêu cầu kỹ thuật của AWS Online Migration).
  3. **Bắt đầu đồng bộ dữ liệu (Start Migration):** Sử dụng AWS CLI để bắt đầu quá trình di trú:
     ```bash
     aws elasticache start-migration --replication-group-id valkey-cart-group --customer-node-endpoint-list "Address='valkey-eks-internal-nlb',Port=6379"
     ```
  4. **Theo dõi đồng bộ:** Giám sát chỉ số `ReplicationLag` và trạng thái migration (`migrating`) trên CloudWatch. Chờ đến khi lag ổn định về mức ~0 giây.
  5. **Thực thi Cutover (Dừng ghi 1-3 phút vào khung giờ thấp điểm):**
     * **Bước 5.1 (Freeze Writes):** Khóa ghi tạm thời trên EKS Valkey bằng lệnh: `CLIENT PAUSE 5000 WRITE`.
     * **Bước 5.2 (Promote Target):** Gọi lệnh hoàn tất di trú trên AWS để thăng cấp ElastiCache làm Primary (chuyển sang Read-Write):
       ```bash
       aws elasticache complete-migration --replication-group-id valkey-cart-group
       ```
     * **Bước 5.3 (Force Reconnect):** Ngắt kết nối cũ trên EKS Valkey cũ để ép client tự động kết nối lại: `CLIENT KILL TYPE normal`.
     * **Bước 5.4 (Redirection):** Cập nhật Kubernetes Service/Secret của `cart` service để trỏ sang endpoint mới của ElastiCache Valkey.
     * **Bước 5.5 (Rolling Update):** Thực hiện rolling update `cart` service pod để các container mới nhận endpoint ElastiCache và hoàn tất các transaction ghi đang xếp hàng chờ.
  6. **Bảo mật sau Migration:** Thực hiện kích hoạt lại tính năng mã hóa đường truyền (TLS) trên cụm ElastiCache và cập nhật connection string sang `rediss://` (chế độ bảo mật TLS).
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Kiểm định khả năng tự động reconnect:** Thư viện client của ứng dụng (ví dụ Go-redis, Jedis) phải được kiểm tra trước về cấu hình retry và auto-reconnection để đảm bảo không bị crash khi kết nối bị ngắt ở Bước 5.3.
  - **Giám sát dung lượng RAM:** Đảm bảo cụm ElastiCache target có dung lượng RAM trống tối thiểu bằng dung lượng sử dụng thực tế của EKS Valkey + 25% reserved memory cho việc đồng bộ.
  - **Rollback trong lúc sync:** Nếu phát hiện lỗi trong quá trình đồng bộ (trước khi chạy complete-migration), ta có thể hủy bỏ di trú an toàn bằng lệnh `Stop Data Migration` qua AWS console/CLI mà không gây ảnh hưởng đến hệ thống đang chạy.

---

## QUYẾT ĐỊNH VK-04: CHIẾN LƯỢC ROLLBACK SAU KHI CÓ DỮ LIỆU GHI MỚI

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Rollback tức thì sử dụng dữ liệu ghi nhận song song.
* **Phương án B:** Quét ngược dữ liệu (Reconcile / Backfill).
* **Phương án C:** Chấp nhận mất giỏ hàng mới (Big Bang Revert).
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-4-chiến-lược-rollback-sau-khi-có-dữ-liệu-ghi-mới))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Thời gian Rollback (RTO) | Mức độ mất mát dữ liệu giỏ hàng |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án B: Quét ngược dữ liệu (Reconcile / Backfill)` | **Ưu điểm:** Bảo toàn 100% dữ liệu giỏ hàng của khách hàng (bao gồm cả các giỏ hàng tạo mới/cập nhật trên ElastiCache).<br>**Nhược điểm:** Tăng độ phức tạp vận hành. Cần chuẩn bị sẵn K8s Job chạy RIOT-Redis để đồng bộ ngược dữ liệu. | **Trung bình (RTO ~ 2 - 5 phút):** Cần thời gian chạy Job RIOT để quét và đồng bộ ngược dữ liệu trước khi chuyển hướng traffic. | **Zero Data Loss (0%):** Hoàn toàn không mất mát dữ liệu giỏ hàng của người dùng. |
| **BỊ LOẠI BỎ** | `Phương án C: Chấp nhận mất giỏ hàng mới (Big Bang Revert)` | **Ưu điểm:** Thao tác cực nhanh và đơn giản.<br>**Nhược điểm:** Mất toàn bộ các giỏ hàng mới hoặc cập nhật trên ElastiCache kể từ lúc cutover. Vi phạm yêu cầu bảo toàn dữ liệu của nghiệp vụ. | **Cực nhanh (RTO < 60s)** | **Cao (mất giỏ hàng mới trong Observation Window)** |
| **BỊ LOẠI BỎ** | `Phương án A: Rollback tức thì dùng dữ liệu song song` | **Nhược điểm:** Không khả thi vì chúng ta đã loại bỏ phương án Dual-write ở VK-03. | **N/A** | **N/A** |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Chuẩn bị công cụ Reverse Sync:** Định nghĩa sẵn một Kubernetes Job chạy **RIOT-Redis** trong EKS cluster. Cấu hình Job này kết nối tới cả ElastiCache endpoint (Source của luồng rollback) và EKS Valkey (Target của luồng rollback).
  2. **Quy trình thực hiện Rollback khi kích hoạt Abort Trigger:**
     * **Bước 1 (Freeze Writes on Target):** Gửi lệnh khóa ghi tạm thời tới ElastiCache đang chạy bằng: `CLIENT PAUSE 10000 WRITE`.
     * **Bước 2 (Trigger Reverse Sync):** Start Kubernetes Job chạy RIOT-Redis để đồng bộ toàn bộ keys từ ElastiCache về EKS Valkey:
       ```bash
       riot-redis replicate --source <elasticache-endpoint>:6379 --target <eks-valkey-ip>:6379 --mode live
       ```
     * **Bước 3 (Verify):** Chạy kiểm tra nhanh số lượng key (Key count) giữa 2 DB để xác nhận đồng bộ thành công.
     * **Bước 4 (Redirect):** Cập nhật Kubernetes Service selector của `cart` service trỏ ngược về IP của EKS Valkey cũ.
     * **Bước 5 (Release):** Gửi lệnh `CLIENT KILL TYPE normal` tới ElastiCache để ngắt toàn bộ kết nối cũ, ép các app pods kết nối lại và nhận endpoint EKS Valkey cũ.
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Cấu hình ghi đè (Overwrite):** Phải cấu hình RIOT-Redis ở chế độ cho phép ghi đè key (`--mode live` hoặc set key replacement policy) để dữ liệu mới từ ElastiCache cập nhật đè lên dữ liệu cũ trên EKS Valkey.
  - **Tăng RTO để đổi lấy Data Integrity:** Quá trình sync ngược 5GB dữ liệu bằng RIOT qua mạng nội bộ AWS sẽ mất khoảng **1 đến 2 phút**. Chấp nhận downtime luồng ghi (Write Pause) trong khoảng thời gian này để đảm bảo dữ liệu không bị lệch.

---

## QUYẾT ĐỊNH VK-05: CẢNH BÁO TRÀN BỘ NHỚ (EVICTION MANAGEMENT)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 80% bộ nhớ.
* **Phương án 2:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 90% bộ nhớ.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-5-cảnh-báo-tràn-bộ-nhớ-eviction-management))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Thời gian Phản ứng của Platform | Rủi ro mất key do Eviction |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `Phương án 1: Thiết lập cảnh báo ở mức 80% bộ nhớ` | **Ưu điểm:** Cảnh báo sớm giúp team vận hành có thêm thời gian (thường là 15-30 phút) để phân tích hoặc scale-up instance khi bộ nhớ tăng bất thường trước khi xảy ra OOM hoặc Eviction.<br>**Nhược điểm:** Có thể có cảnh báo ảo nếu dung lượng tăng đột biến trong thời gian ngắn nhưng tự động giải phóng (bởi TTL). | **Đủ (15-30 phút):** Cho phép team có đủ thời gian phản ứng, chạy kiểm tra và đưa ra quyết định tăng kích thước instance (Sizing). | **Thấp:** Eviction chỉ xảy ra khi bộ nhớ chạm ngưỡng 100%. Cảnh báo ở 80% giúp ngăn chặn từ xa. |
| **BỊ LOẠI BỎ** | `Phương án 2: Thiết lập cảnh báo ở mức 90% bộ nhớ` | **Ưu điểm:** Hạn chế tối đa các cảnh báo giả.<br>**Nhược điểm:** Thời gian phản ứng quá ngắn. Với instance nhỏ như `cache.t4g.micro` (0.5 GB RAM), từ 90% lên 100% (bị OOM/Eviction) chỉ mất vài giây khi có spike traffic. | **Quá ngắn (< 5 phút):** Rất khó để team vận hành can thiệp kịp thời trước khi hệ thống tự động loại bỏ key hoặc crash. | **Cao:** Nguy cơ cao bị mất giỏ hàng của người dùng do eviction tự động khi ram đạt đỉnh 100%. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:**
  1. **Tạo CloudWatch Alarm:** Sử dụng Terraform để định nghĩa một `aws_cloudwatch_metric_alarm` dựa trên metric `DatabaseMemoryUsagePercentage` của cụm ElastiCache Valkey.
  2. **Cấu hình ngưỡng:** Thiết lập `comparison_operator = "GreaterThanOrEqualToThreshold"`, `threshold = 80`, và `evaluation_periods = 2` (đánh giá trong 2 phút liên tiếp).
  3. **Notification:** Liên kết Alarm với AWS SNS Topic để bắn thông báo cảnh báo về kênh Slack/PagerDuty của đội vận hành.
* **Lưu ý & Biện pháp phòng ngừa lỗi:**
  - **Đảm bảo maxmemory-policy:** Phải chắc chắn tham số `maxmemory-policy` trong Parameter Group được thiết lập là `volatile-lru` để khi bộ nhớ đạt 100%, hệ thống tự giải phóng các key có TTL đã hết hạn thay vì từ chối lệnh ghi mới.
