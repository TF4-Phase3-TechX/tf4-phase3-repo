# CDO08-REL-20 (T1) - Truy vết Dependency Dữ liệu trên Luồng Ra Tiền

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20 (DR / Backup & Restore)
**Subtask:** T1 - "Trace luồng ra tiền" (xác định service và dữ liệu nào tham gia browse -> cart -> checkout)
**Trạng thái:** Research read-only, không đổi gì trên cluster/state.
**Owner:** Nguyên (Techlead)

---

## 1. Mục đích

Trước khi scope backup/restore, cần biết chính xác service nào chạm vào store nào. Tài liệu này trace toàn bộ `browse -> cart -> checkout -> payment -> order -> async event`, dựa trên chart (`techx-corp-chart/`), source code (`techx-corp-platform/src/`), và kiểm tra live trên cluster (`kubectl get deploy/secret/externalsecret`).

**Xác nhận quan trọng:** hệ thống hiện tại đã cutover xong sang managed service - `product-catalog`, `accounting` dùng RDS qua secret `rds-postgres-secret`; `cart` dùng ElastiCache Valkey qua secret `elasticache-valkey-secret`; `checkout`/`accounting`/`fraud-detection` dùng MSK qua secret `msk-kafka-secret`. Không còn Service/Deployment self-hosted `postgresql`, `valkey-cart`, `kafka` nào chạy trong cluster (`kubectl get svc -n techx-tf4` không ra kết quả cho 3 tên này).

## 2. Sơ đồ dependency luồng ra tiền

```text
Customer -> Frontend

Frontend -> product-catalog -----> RDS PostgreSQL (schema: catalog, read-only)
Frontend -> currency
Frontend -> recommendation (optional) -> product-catalog, currency
Frontend -> ad (optional)

Frontend -> cart --------------> ElastiCache Valkey (valkey-cart)

Frontend -> checkout
  checkout -> cart
  checkout -> shipping -> quote
  checkout -> payment
  checkout -> MSK Kafka (produce topic: orders)

MSK Kafka -> accounting --------> RDS PostgreSQL (schema: accounting)
MSK Kafka -> fraud-detection (chỉ đếm trong bộ nhớ, không ghi store nào)

--- Ngoài luồng browse -> cart -> checkout ---
product-reviews -> RDS PostgreSQL (schema: reviews)
```

Ghi chú:
- `currency`, `recommendation`, `ad`, `shipping`, `quote`, `payment`, `email` không có store nào - đã grep source từng service để tìm client DB/cache/queue, không có kết quả thật (1 match trong `payment/package-lock.json` chỉ là lockfile, không phải code dùng thật).
- `product-reviews` ghi vào RDS (schema `reviews`) nhưng không nằm trên luồng critical browse -> cart -> checkout (phục vụ tính năng AI review-summary). Vẫn liệt kê cho đủ, nhưng không tính critical.
- `fraud-detection` consume Kafka nhưng chỉ giữ 1 biến đếm trong bộ nhớ - không có gì cần backup.

## 3. Bảng service -> dependency -> dữ liệu -> mức độ quan trọng

| Service | Dependency | Dữ liệu | Mức độ quan trọng | Evidence |
|---|---|---|---|---|
| **product-catalog** | RDS PostgreSQL, schema `catalog` (chỉ đọc) | Dữ liệu listing/search sản phẩm (id, tên, mô tả, giá, category) | **Trung bình, tái tạo được.** Là dữ liệu tham chiếu, không bị service này ghi/sửa lúc runtime (chỉ có quyền SELECT). Mất đi vẫn khôi phục được từ backup RDS hoặc seed lại. | `kubectl get deploy product-catalog -o json` (env `DB_CONNECTION_STRING` từ secret `rds-postgres-secret`); `techx-corp-chart/postgresql/init.sql:126-142` (`GRANT SELECT ... TO otelu`, không có quyền ghi); `techx-corp-platform/src/product-catalog/main.go:138-167,268-345` (chỉ SELECT). |
| **cart** | ElastiCache Valkey (`valkey-cart`) | Nội dung giỏ hàng đang hoạt động của từng user, TTL 60 phút | **Cao cho tính liên tục, thấp cho độ bền lâu dài.** Mất đi làm rỗng giỏ hàng đang thao tác, chặn checkout của khách đang mua - nhưng là session data tạm thời (TTL 60 phút), khách tự tái tạo được bằng cách thêm lại sản phẩm. | ExternalSecret `elasticache-valkey-secret` (nguồn `techx/tf4/elasticache-valkey` trong Secrets Manager); `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs:143-195` (`HashGetAsync`/`HashSetAsync` + `KeyExpireAsync(60 min)`). |
| **checkout** | MSK Kafka, topic `orders` (chỉ produce) | Publish `OrderResult` hoàn chỉnh (order id, items, shipping, cost) sau khi checkout thành công | **Cao.** Đây là event "order placed" mang tính authoritative. Checkout không giữ state cục bộ, nhưng nếu message này mất trước khi `accounting` ghi lại, khách có thể đã bị trừ tiền mà không có bản ghi order nào ở downstream. | ExternalSecret `msk-kafka-secret` (nguồn `techx/tf4/msk-kafka`); `techx-corp-platform/src/checkout/kafka/producer.go:16` (Sarama async producer, topic `orders`). |
| **accounting** | RDS PostgreSQL, schema `accounting` (đọc/ghi qua EF Core) + consume MSK Kafka topic `orders` | Bản ghi order cuối cùng, bền vững - order history / sổ cái doanh thu | **Critical - bắt buộc phải sống sót qua restore.** Đây là bản ghi duy nhất xác nhận order đã đặt và đã thanh toán; mất đi là mất doanh thu/audit-trail không thể khôi phục. | `kubectl get deploy accounting -o json` (env `DB_CONNECTION_STRING` từ `rds-postgres-secret`, `KAFKA_ADDR` từ `msk-kafka-secret`); `postgresql/init.sql:6-41` (schema `accounting`, `GRANT SELECT, INSERT, UPDATE`); `techx-corp-platform/src/accounting/Consumer.cs:12-24,86-139` (insert `OrderEntity`/`OrderItemEntity`/`ShippingEntity`, `SaveChanges()`). |
| **fraud-detection** | Consume MSK Kafka - không có DB, không có state bền vững | Biến đếm số message đã consume, chạy trong bộ nhớ, mất khi restart theo thiết kế | **Không có.** Chỉ là bộ đếm demo; không có gì cần backup. | `techx-corp-platform/src/fraud-detection/src/main/kotlin/frauddetection/main.kt:42-70` (chỉ KafkaConsumer, biến local `totalCount`, không ghi DB/file). |
| **product-reviews** *(ngoài luồng critical)* | RDS PostgreSQL, schema `reviews` (đọc/ghi) | Đánh giá sao + review dạng text của sản phẩm | **Thấp-trung bình**, là dữ liệu đọc/ghi thật, nhưng không nằm trên luồng browse->cart->checkout. | `postgresql/init.sql:44-60` (`GRANT SELECT, INSERT, UPDATE`); `techx-corp-platform/src/product-reviews/database.py:20-90`. |
| **currency, recommendation, ad, quote, shipping, payment, email** | Không có | Stateless - không có code client DB/cache/queue nào | **N/A - không có dữ liệu cần backup.** | Grep client redis/postgres/kafka/dynamodb trên từng `src/` của mỗi service = 0 kết quả thật (`payment/charge.js` đọc toàn file, chỉ mock validate thẻ, không đọc/ghi store nào). |

## 4. Kiểm tra store không tồn tại

- **DynamoDB không được dùng cho bất kỳ dữ liệu ứng dụng nào.** `grep -r "aws_dynamodb_table" infra/terraform/` cho 0 kết quả. Bảng DynamoDB duy nhất trong repo là `aws_dynamodb_table.terraform_locks` (`infra/bootstrap/main.tf:90`), chỉ dùng làm lock table cho Terraform S3 backend. Không có env var `DYNAMODB_*` nào trong chart.
- **MongoDB, object storage tự host, hay bất kỳ store nào khác** không xuất hiện trong chart lẫn source - không tồn tại.

## 5. Dependency GitOps / IaC / trạng thái cụm

- **ArgoCD** quản lý cluster, nhưng manifest `Application` không nằm trong repo này mà ở repo riêng `tf4-phase3-gitops-manifests` (`grep -r "kind: Application"` ở đây = 0 kết quả). Đã qua kiểm tra trực tiếp repo đó: host thật trên GitHub (`github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests`), có `main`, `CODEOWNERS`, CI validate - không phải single point of failure. `argocd/root-resources/` chứa đúng các Application (kyverno, techx-corp, ...), và `platform/secrets/managed-data-secrets.yaml` khai báo đúng 3 secret `rds-postgres-secret`, `elasticache-valkey-secret`, `msk-kafka-secret` đang chạy thật trên cluster.
- **Terraform state** ở remote (S3 + DynamoDB lock, `infra/terraform/providers.tf:25-31`) - hạ tầng dựng lại được từ state + repo này.
- **flagd**: định nghĩa flag chỉ là 1 file JSON trong chart (`techx-corp-chart/flagd/demo.flagd.json`), không phải dữ liệu runtime - deploy lại Helm là có lại, không cần DR riêng.

## 6. Tổng hợp đầu vào cho phần inventory (T2)

Store phải có mặt trong inventory ([CDO08-REL-20-stateful-store-inventory.md](CDO08-REL-20-stateful-store-inventory.md)) vì nằm trên luồng ra tiền:

1. RDS PostgreSQL (schema `catalog`, `accounting`).
2. ElastiCache Valkey (`valkey-cart`).
3. MSK Kafka (topic `orders`).
4. Terraform state (S3 + DynamoDB lock) và repo GitOps ArgoCD bên ngoài - trạng thái hạ tầng/cụm, bắt buộc để dựng lại hệ thống theo yêu cầu #1 của mandate.

Schema `product-reviews` và DynamoDB (chỉ dùng state-lock) ghi nhận cho đủ nhưng loại khỏi phạm vi cam kết RPO/RTO của luồng ra tiền.
