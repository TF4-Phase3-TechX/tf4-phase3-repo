# Mandate 8 - Valkey Migration Decisions & ADR Record

* **Trạng thái:** Đã điền phân tích, chờ ký duyệt (Tech Lead: Quân)

Tài liệu này cung cấp khung mẫu quyết định thiết kế kiến trúc (ADR format) trống dạng bảng so sánh để cá nhân Tech Lead tự điền nghiên cứu độc lập. Khung hướng dẫn triển khai chỉ yêu cầu mô tả quy trình chung và các lưu ý phòng ngừa lỗi cho phương án được chọn ở các quyết định kỹ thuật phức tạp.

---

## QUYẾT ĐỊNH VK-01: LỰA CHỌN CHÍNH SÁCH DỮ LIỆU GIỎ HÀNG (CART DATA POLICY)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** Di trú giỏ hàng đang hoạt động (Active Cart Migration).
* **Phương án B:** Chuyển đổi lạnh (Cold Cutover / Discard Carts).
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-1-lựa-chọn-chính-sách-dữ-liệu-giỏ-hàng-cart-data-policy))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Ảnh hưởng Trải nghiệm Khách hàng (SLO) |
| :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `B` | Cart hiện chỉ lưu duy nhất 1 field (`"cart"`, protobuf) theo key `userId` và **luôn set TTL 60 phút mỗi lần ghi** (`ValkeyCartStore.cs`) — bản chất dữ liệu là tạm thời, không phải state cần bảo toàn dài hạn. Cold cutover không cần dual-write/migration tool, không đổi code `cart` service, rủi ro kỹ thuật thấp nhất, thời gian thực hiện ngắn — phù hợp deadline Mandate 8 (2026-07-20). Nhược điểm: user đang có cart hoạt động tại thời điểm cutover sẽ thấy giỏ trống, phải add lại item. | Không ảnh hưởng **success rate checkout** (metric SLO chính) một cách trực tiếp — checkout fail chỉ xảy ra khi *đang* thao tác giữa lúc repoint (ngắn, vài giây) chứ không phải do mất dữ liệu cart cũ tự nó. Cắt giảm blast radius bằng cách cutover trong **low-traffic window**: vì TTL là 60 phút, chỉ user thao tác trong ~1 giờ trước cutover bị ảnh hưởng — giỏ đã idle quá TTL vốn dĩ cũng đã tự hết hạn, không phải "mất thêm" so với hành vi bình thường của hệ thống. |
| **BỊ LOẠI BỎ** | `A` | Active Cart Migration cần dual-write hoặc export/import trong lúc hệ thống vẫn nhận traffic — phát sinh độ phức tạp (đồng bộ 2 chiều, xử lý race condition read-modify-write giữa 2 store) để bảo toàn dữ liệu vốn dĩ **tự thiết kế là ephemeral** (TTL 60 phút). Chi phí kỹ thuật không tương xứng với giá trị dữ liệu bảo toàn được — cart mất tự nhiên sau 1 giờ dù có migrate hay không. | N/A |

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
| **ĐÃ CHỌN** | `1` | Khác với Kafka (producer fire-and-forget, async), **`checkout` phụ thuộc đồng bộ vào Valkey qua `cart` service** để đọc item trước khi tạo đơn — Valkey unreachable = checkout fail ngay lập tức trên đường găng (critical path). `cart` service tuy chạy `replicas: 2` + PDB nhưng cả 2 pod đều trỏ về **cùng 1 backend Valkey** — redundancy ở tầng app không giúp gì nếu tầng cache chết. Hiện tại (in-cluster) đây vốn đã là 1 single point of failure (1 pod, `Recreate`); chuyển sang Multi-AZ ElastiCache là **cải thiện** so với hiện trạng, không phải thêm rủi ro mới. `cache.t4g.micro` có 512MiB RAM — gấp ~8 lần giới hạn 64Mi hiện tại của pod Valkey in-cluster, dư thừa headroom cho cart data. | **Verified qua AWS Price List API (2026-07-17):** `cache.t4g.micro` = **$0.0160/node-giờ** (SKU `GUTP43BSNHYMZJ57`) → Single-Node **$11.68/tháng (~$2.69/tuần)**; Multi-AZ (2 node) **$23.36/tháng (~$5.38/tuần)**. Chênh lệch chỉ **~$2.69/tuần** — khớp với ước tính ban đầu, nhỏ không đáng kể so với trần `$300/tuần` và cực nhỏ so với phần MSK (~$15.8-16.3/tuần, xem KF-01 — cấu phần đắt nhất của cả migration). **Worst-case cộng thêm** (chưa tính ở bản gốc): backup/snapshot storage `$0.085/GiB-tháng` và cross-AZ data transfer EC2↔ElastiCache `$0.01/GiB` — cả 2 đều không đáng kể với data cart nhỏ hiện tại (ước tính dưới $1/tuần kể cả bật backup + toàn bộ traffic cross-AZ). Chi phí không phải rào cản ở quyết định này. | Multi-AZ có automatic failover (ElastiCache tự phát hiện & chuyển sang replica, thường trong khoảng vài chục giây), giảm thời gian gián đoạn checkout khi node/AZ gặp sự cố so với chờ AWS tự phục hồi single-node (không có failover, downtime kéo dài hơn tới khi node được thay thế). |
| **BỊ LOẠI BỎ** | `2` | Rẻ nhất nhưng **không có failover** — một sự cố node/AZ sẽ làm checkout ngừng hoạt động hoàn toàn (tương tự rủi ro hiện tại) cho tới khi AWS tự phục hồi. Vì Valkey nằm trên đường găng checkout (không giống Kafka fire-and-forget), chấp nhận risk này chỉ để tiết kiệm ~$2.69/tuần là đánh đổi không hợp lý khi ngân sách còn nhiều headroom (baseline `$56.83/tuần` + RDS Single-AZ `~$3.2/tuần` + ElastiCache Multi-AZ `~$5.38/tuần` + MSK `~$15.8-16.3/tuần` ≈ `$81/tuần` tổng, headroom còn lại `~$219/tuần` so với trần `$300/tuần` — đã sửa lại theo số MSK verified ở KF-01, số cũ `$243/tuần` là tính sai). | **$11.68/tháng (~$2.69/tuần)** (verified, xem cột trước) — rẻ hơn Phương án 1 nhưng chênh lệch không đáng kể. | Không có auto-failover; RTO phụ thuộc AWS tự thay node — không kiểm soát được, rủi ro cao hơn cho 1 dependency nằm trên critical path checkout. |
| **BỊ LOẠI BỎ** | `3` | Cart hiện chỉ tiêu thụ **32-64Mi RAM** ở mức resource limit hiện tại (`values.yaml`), dữ liệu mỗi entry rất nhỏ (1 field protobuf/user, TTL 60 phút nên không tích luỹ). Instance lớn hơn (`cache.m7g.large`+) hoặc nhiều replica hơn không giải quyết vấn đề nào đang tồn tại — over-provision so với workload thực tế, tốn chi phí không cần thiết. | Đắt hơn đáng kể so với `t4g.micro` mà không có lợi ích tương xứng với quy mô dữ liệu cart hiện tại. | Không cải thiện gì thêm so với Phương án 1 cho khối lượng dữ liệu này — thừa capacity, không thừa an toàn. |

---

## QUYẾT ĐỊNH VK-03: LỰA CHỌN KỸ THUẬT DI TRÚ (MIGRATION TECHNIQUE)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án A:** RDB Export & Import.
* **Phương án B:** Application Dual-Write & SCAN Backfill.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-3-lựa-chọn-kỹ-thuật-di-trú-migration-technique))*

### 2. Phân tích & Lựa chọn của Tech Lead

> Vì VK-01 đã chọn **Cold Cutover** (không bảo toàn cart đang hoạt động), quyết định này thực chất chỉ còn ý nghĩa **dự phòng/kiểm thử** (vd seed dữ liệu mẫu để smoke-test kết nối ElastiCache trước cutover), không phải để di trú cart thật của khách hàng.

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Yêu cầu sửa đổi Code ứng dụng | Độ phức tạp Vận hành |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `A` | RDB export/import là thao tác vận hành thuần (dump từ pod `valkey-cart` → restore vào ElastiCache), không đụng tới code `cart` service — nhất quán với triết lý cold-cutover ở VK-01 (không cần pipeline sống). Chỉ dùng để: (1) kiểm thử kết nối/permission trước cutover thật (pre-flight), (2) tuỳ chọn seed vài key mẫu để smoke test end-to-end (add→get→checkout) trên ElastiCache trước khi repoint traffic thật. | Không cần — hoàn toàn ở tầng vận hành/hạ tầng. | Thấp — 1 lệnh dump + 1 lệnh restore, chạy 1 lần trong 1 Job ngắn hạn (VAP-compliant: non-root, pinned tag, requests+limits, drop ALL). |
| **BỊ LOẠI BỎ** | `B` | Dual-Write & SCAN Backfill chỉ có giá trị nếu VK-01 chọn Active Cart Migration (bảo toàn cart sống) — nhưng quyết định đó đã bị loại. Áp dụng phương án này ở đây là over-engineering: đòi sửa code `cart` service để ghi song song 2 backend, thêm rủi ro (race condition, backend nào là source of truth trong lúc chuyển tiếp), tốn thời gian implement/test không cần thiết cho dữ liệu TTL 60 phút. | Có — phải sửa `ValkeyCartStore.cs` để ghi đồng thời 2 nơi, thêm logic backfill SCAN. | Cao — cần vận hành 2 backend song song, theo dõi đồng bộ, rollback phức tạp hơn nếu backfill lỗi giữa chừng. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** (1) Provision ElastiCache (Multi-AZ theo VK-02) trong private subnet, security group chỉ mở từ EKS node SG. (2) Chạy Job pre-flight (VAP-compliant) test connectivity/TLS/auth từ trong `techx-tf4` tới endpoint mới. (3) Tuỳ chọn: `redis-cli --rdb` dump từ `valkey-cart` pod, restore vào ElastiCache để smoke-test (không phải để bảo toàn cart thật). (4) Trong low-traffic window, repoint `VALKEY_ADDR` sang ElastiCache + credential/TLS mới qua Secret, rolling restart `cart` (giữ `replicas: 2`). (5) Chạy cart smoke test end-to-end (add item → get cart → checkout) qua trace Jaeger để verify.
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không bao giờ repoint khi chưa pass pre-flight connectivity test. Giữ pod + PVC `valkey-cart` cũ **warm** (không xoá) cho tới khi bake xong (24-48h ổn định) — theo `resource-policy: keep` sẵn có. Thông báo trước cho PM/business về việc user online sẽ mất cart tại thời điểm cutover (cần sign-off, không tự quyết).

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
| **ĐÃ CHỌN** | `C` | Nhất quán với VK-01/VK-03 (cold cutover, không có pipeline dual-write) — pod + PVC `valkey-cart` cũ vẫn còn giữ nguyên (`resource-policy: keep`), nên rollback chỉ là repoint env về lại `valkey-cart:6379` + rolling restart `cart`. Đơn giản, nhanh, rủi ro vận hành thấp nhất — đúng tinh thần "đã chấp nhận mất cart 1 lần khi cutover forward, thì rollback cũng chấp nhận mất cart 1 lần theo chiều ngược lại" thay vì cố bảo toàn 1 chiều mà không bảo toàn chiều kia. | **Rất nhanh** — chỉ là thay đổi 1 biến môi trường (`VALKEY_ADDR`) + rolling restart Deployment `cart`, tính bằng phút (không cần chờ data sync). | Cart được tạo/sửa trên ElastiCache trong khoảng thời gian giữa cutover và rollback sẽ mất — chấp nhận được vì (1) dữ liệu vốn ephemeral TTL 60 phút, (2) đã có business sign-off cho việc mất cart ở VK-01, (3) window cutover→rollback thường ngắn (phát hiện lỗi qua observability gate gần như ngay lập tức). |
| **BỊ LOẠI BỎ** | `A` | Chỉ khả thi nếu đã triển khai dual-write (VK-03 phương án B) — nhưng dual-write đã bị loại vì over-engineering so với giá trị dữ liệu. Chọn A ở đây sẽ mâu thuẫn với quyết định VK-03. | N/A (phụ thuộc dual-write chưa có) | N/A |
| **BỊ LOẠI BỎ** | `B` | Về mặt kỹ thuật khả thi (SCAN toàn bộ key trên ElastiCache, ghi ngược vào Valkey cũ) nhưng tốn effort xây script + thời gian chạy scan/backfill — không tương xứng với giá trị dữ liệu ephemeral cần bảo toàn (cart TTL 60 phút, phần lớn key backfill xong cũng gần hết hạn). Làm rollback **chậm hơn** đúng lúc cần nhanh nhất (rollback nghĩa là đang có sự cố). | Chậm hơn C — phụ thuộc số lượng key cần SCAN + backfill. | Thấp hơn C về lý thuyết, nhưng lợi ích không đáng kể so với chi phí thời gian rollback tăng thêm khi hệ thống đang gặp sự cố. |

#### Kế hoạch Triển khai cho Phương án Đã Chọn:
* **Cách triển khai đề xuất:** Trigger rollback khi chạm 1 trong các ngưỡng ở §6.3 (checkout success rate < 99%, cart smoke test fail, ElastiCache lỗi kết nối/TLS): (1) repoint `VALKEY_ADDR` env về `valkey-cart:6379` trong `values.yaml`/overlay, (2) rollout `cart` deployment (rolling, giữ `replicas: 2` luôn có bản phục vụ), (3) verify lại cart smoke test trên Valkey in-cluster, (4) thông báo Slack/incident channel + ghi nhận trong evidence (REL-19).
* **Lưu ý & Biện pháp phòng ngừa lỗi:** Không debug trên production khi đã chạm ngưỡng — repoint ngay, điều tra sau (pattern REL-09 runbook). Không xoá pod/PVC `valkey-cart` cũ cho tới khi đã bake ổn định 24-48h trên ElastiCache (REL-18 chỉ chạy sau mốc này).

---

## QUYẾT ĐỊNH VK-05: CẢNH BÁO TRÀN BỘ NHỚ (EVICTION MANAGEMENT)

### 1. Mô tả Quyết định & Các Hướng đề xuất
* **Phương án 1:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 80% bộ nhớ.
* **Phương án 2:** Thiết lập cảnh báo (CloudWatch Alert) ở mức 90% bộ nhớ.
*(Chi tiết mô tả xem tại [MANDATE-08-VALKEY-ANALYSIS.md](./MANDATE-08-VALKEY-ANALYSIS.md#quyết-định-5-cảnh-báo-tràn-bộ-nhớ-eviction-management))*

### 2. Phân tích & Lựa chọn của Tech Lead

| Trạng thái | Phương án | Phân tích Trade-offs (Ưu/Nhược điểm) | Thời gian Phản ứng của Platform | Rủi ro mất key do Eviction |
| :--- | :--- | :--- | :--- | :--- |
| **ĐÃ CHỌN** | `1` | Cache chứa dữ liệu **user-facing** (giỏ hàng đang hoạt động) — nếu bị evict *trước* khi TTL 60 phút tự nhiên hết hạn (do memory pressure, vd traffic spike bất thường hoặc key size tăng đột biến), khách hàng mất giỏ hàng **sớm hơn dự kiến** một cách không kiểm soát được — khác về bản chất với việc mất cart do cutover đã được thông báo/chấp nhận trước (VK-01/VK-04). Cảnh báo sớm ở 80% cho platform team nhiều thời gian phản ứng hơn (điều tra nguyên nhân tăng memory, scale instance nếu cần) trước khi chạm ngưỡng eviction thật. Đánh đổi: nhiều cảnh báo hơn Phương án 2 (bao gồm một số false alarm khi có traffic spike ngắn hạn tự nhiên, vd Locust load-generator test). | Nhanh hơn — có buffer ~20% dung lượng để platform xử lý trước khi bắt đầu evict. | Thấp hơn — do được cảnh báo sớm, có thời gian scale/điều tra trước khi ElastiCache bắt đầu evict key theo policy (`volatile-lru`/`allkeys-lru` tuỳ cấu hình `maxmemory-policy`), giảm rủi ro khách hàng mất giỏ hàng ngoài ý muốn. |
| **BỊ LOẠI BỎ** | `2` | Ít cảnh báo giả hơn (đỡ nhiễu cho platform team), nhưng chỉ còn ~10% buffer để phản ứng trước khi bắt đầu evict — với dữ liệu ảnh hưởng trực tiếp tới trải nghiệm khách hàng (không phải cache thuần kỹ thuật, không quan trọng), đánh đổi giảm nhiễu lấy rủi ro cao hơn là hợp lý ngược lại. | Chậm hơn — ít thời gian phản ứng hơn trước ngưỡng eviction thật. | Cao hơn — buffer hẹp hơn đồng nghĩa nhiều khả năng bắt đầu evict trước khi platform kịp scale, ảnh hưởng trực tiếp tới khách hàng đang có giỏ hàng hoạt động (khác cart timeout tự nhiên mà khách đã ngầm chấp nhận). |

---

## Ghi chú chung

* **Fact-check cost (2026-07-17):** số ElastiCache ở VK-02 đã được verify trực tiếp qua AWS Price List API (`pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonElastiCache/...`, SKU `GUTP43BSNHYMZJ57` cho `cache.t4g.micro`/Redis engine) — số ước lượng ban đầu (`~$12/tháng` Single-Node, `~$24/tháng` Multi-AZ) khớp với số verified (`$11.68/tháng`, `$23.36/tháng`), không cần điều chỉnh. Đã bổ sung worst-case backup/snapshot storage (`$0.085/GiB-tháng`) và cross-AZ transfer (`$0.01/GiB`, nguồn: trang pricing chính thức AWS ElastiCache) — cả 2 không đáng kể với data cart hiện tại.

