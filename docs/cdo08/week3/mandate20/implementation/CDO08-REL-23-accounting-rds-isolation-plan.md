> **TRẠNG THÁI: DRAFT — CHƯA THỰC THI.** Tài liệu này chỉ là kế hoạch/runbook. Chưa tạo tài nguyên AWS,
> chưa sửa Terraform/chart/GitOps, chưa chạy script nào. Không dùng file này làm căn cứ nộp mentor cho
> tới khi có evidence thật (xem [CDO08-REL-23-accounting-rds-isolation-evidence.md](../evidence/CDO08-REL-23-accounting-rds-isolation-evidence.md)).

# CDO08-REL-23 — Kế hoạch tách schema `accounting` sang RDS instance riêng

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20, yêu cầu #3-4
**Subtask:** Hiện thực hoá [GAP-06](../scan/CDO08-REL-20-gap-register.md) — xem thêm quyết định RPO/RTO tại [CDO08-REL-21-rpo-rto-matrix.md](../adr/CDO08-REL-21-rpo-rto-matrix.md)
**Nguồn task:** `D:\REL-23.csv` — `[CDO08-REL-23][P0][RDS] Isolate accounting into a dedicated RDS recovery boundary`
**Owner:** CDO08 Reliability + Infra
**Trạng thái:** DRAFT

---

## 1. Mục tiêu

Tách schema `accounting` (sổ cái order — dữ liệu ra tiền, `Critical` theo
[RPO/RTO matrix](../adr/CDO08-REL-21-rpo-rto-matrix.md): RPO đề xuất 15 phút, RTO đề xuất 1 giờ) ra khỏi
RDS instance đang dùng chung với `catalog`/`reviews`, sang một **recovery boundary độc lập** — một RDS
instance riêng chỉ chứa `accounting`.

## 2. Vì sao cần tách

Theo [stateful-store-inventory](../scan/CDO08-REL-20-stateful-store-inventory.md) và
[gap register](../scan/CDO08-REL-20-gap-register.md) (GAP-06): PostgreSQL PITR hoạt động ở **cấp instance**,
không phải cấp schema. Cả 3 schema `catalog`/`accounting`/`reviews` hiện sống chung 1 instance
`techx-tf4-postgresql` (`techx-corp-chart/postgresql/init.sql`). Nếu cần restore `accounting` về một mốc
thời gian trước sự cố (VD: một bug ghi đè order), thao tác PITR sẽ đưa **toàn bộ instance** — bao gồm
`catalog` và `reviews` — về cùng timestamp đó, có nguy cơ làm mất dữ liệu review/catalog vừa ghi thật
trong khoảng thời gian đó mà không liên quan gì tới sự cố của `accounting`. Đây là gap trực tiếp vi phạm
yêu cầu #3 của Mandate 20 ("point-in-time restore chứng minh được" — restore phải ra môi trường tách biệt,
không kéo theo dữ liệu không liên quan).

## 3. Quyết định thiết kế — phương án, tradeoff, đề xuất

### 3.1 Phương pháp migrate dữ liệu

`accounting` là **writer duy nhất** ghi vào schema `accounting` (theo
[revenue-path-dependency-trace](../scan/CDO08-REL-20-revenue-path-dependency-trace.md) — không service
nào khác ghi/đọc 3 bảng `accounting."order"`/`orderitem`/`shipping`), và nó tiêu thụ dữ liệu order từ
**MSK Kafka topic `orders`** — nghĩa là dừng consumer không làm mất order: message vẫn nằm trong Kafka
(replication factor 2, retention còn hiệu lực), chỉ chờ được consume lại.

| | **PA-A: `pg_dump`/`restore` + tạm dừng consumer** | **PA-B: AWS DMS full-load + CDC** |
|---|---|---|
| Cơ chế | Scale `accounting` Deployment về 0 replica (= write-freeze tự nhiên vì nó là writer duy nhất) → `pg_dump` schema `accounting` từ instance cũ → `pg_restore` vào instance mới → cutover connection string → scale lại `accounting` → consumer tự động replay các message `orders` tích luỹ trong lúc dừng | Dựng lại toàn bộ hạ tầng DMS (giống REL-14/15): DMS replication instance, migration bridge NLB, DMS task `full-load-and-cdc`, rồi writer-freeze ngắn + parity gate trước cutover |
| Downtime ghi | Có, nhưng **không đồng nghĩa mất dữ liệu** — Kafka giữ order trong lúc `accounting` down, consume bù ngay khi bật lại | Gần như zero-downtime (CDC bắt kịp trước khi cutover) |
| Độ phức tạp | Thấp — chỉ 1 lần pg_dump/restore, không cần dựng lại DMS instance/bridge/task | Cao — phải tái tạo toàn bộ pipeline DMS đã dùng 1 lần cho REL-15 rồi bỏ, tốn thêm chi phí DMS instance + thời gian setup/parity gate |
| Rủi ro | Thời gian `accounting` down tỷ lệ thuận với lượng order dồn cần replay lúc bật lại (giám sát consumer lag) | Rủi ro vận hành DMS (đã từng có sự cố ghi nhận ở REL-15 evidence), cấu hình lại CDC cho 1 schema nhỏ là over-engineering |
| Phù hợp khi | Service là writer/consumer duy nhất, có message queue làm buffer tự nhiên (đúng case `accounting`) | Cần giữ zero-downtime cho service có traffic ghi trực tiếp từ nhiều client, không có buffer replay |

**Đề xuất: PA-A (`pg_dump`/`restore` + tạm dừng consumer).** Lý do: bản chất `accounting` khác với cutover
RDS toàn hệ thống ở REL-15 (khi đó nhiều service ghi/đọc đồng thời, cần CDC để không mất giao dịch đang
chạy). Ở đây `accounting` là consumer Kafka đơn lẻ — dừng nó không mất order thật vì Kafka đã đóng vai trò
buffer bền vững. Dùng lại DMS cho 3 bảng nhỏ, 1 writer là chi phí/độ phức tạp không tương xứng với lợi ích.

### 3.2 Cách tách connection string sang host mới

Hiện tại cả 3 service `accounting`/`product-catalog`/`product-reviews` dùng **chung 1 K8s Secret**
`rds-postgres-secret` (nguồn AWS Secrets Manager `techx/tf4/rds-postgres`), chỉ khác nhau ở **key** theo
ngôn ngữ (`dotnet-conn-string`/`go-conn-string`/`python-conn-string`) — xem
[sec-13-managed-data-secret-contract.md](../../../sec-13-managed-data-secret-contract.md). Chart
(`techx-corp-chart/templates/_pod.tpl`, biến `$pgKeyMap`) áp **1 `secretName` chung** cho cả 3 service.

| | **PA-A: Secret riêng + sửa chart per-service** | **PA-B: Đổi giá trị trong secret chung** |
|---|---|---|
| Cơ chế | Tạo secret AWS Secrets Manager mới `techx/tf4/rds-accounting` (nằm trong prefix `techx/tf4/*` đã được IAM ESO cấp quyền đọc sẵn — không cần đổi IAM) → ExternalSecret mới `rds-accounting-secret` (namespace `techx-tf4`) → sửa `_pod.tpl`/`values.yaml` để `accounting` đọc `secretName` riêng thay vì dùng chung `$pgKeyMap` | Chỉ sửa property `connection_string_dotnet` bên trong secret `techx/tf4/rds-postgres` hiện có, trỏ sang host RDS mới; `connection_string_go`/`connection_string_python` giữ nguyên host cũ |
| Tách bạch | Rõ ràng — mỗi instance có secret riêng, đúng tinh thần "recovery boundary độc lập" của cả task này | Kém — 2 RDS instance khác nhau nhưng thông tin kết nối nằm chung 1 secret, dễ nhầm khi audit/rotate credential, vi phạm tinh thần tách boundary mà chính task này đang làm |
| Chi phí thay đổi | Cần 1 thay đổi chart (`_pod.tpl`) để hỗ trợ `secretName` theo từng service thay vì áp chung 1 secret cho cả `$pgKeyMap` | Không cần sửa chart — nhanh hơn để triển khai |
| Rủi ro vận hành | Rotate/xoá secret của `catalog`/`reviews` không còn ảnh hưởng tới `accounting` và ngược lại | Rotate secret `techx/tf4/rds-postgres` (VD sau khi xử lý GAP-01) phải cẩn thận không làm hỏng 2 property khác đang trỏ instance khác |

**Đề xuất: PA-A (secret riêng + sửa chart per-service).** Lý do: mục tiêu của cả REL-23 là tạo **recovery
boundary độc lập** — nếu vẫn giữ chung 1 secret cho 2 instance khác nhau thì boundary chỉ độc lập ở tầng
dữ liệu (RDS) nhưng không độc lập ở tầng vận hành/credential, làm giảm giá trị của việc tách. Chi phí thêm
(1 thay đổi chart nhỏ, có tiền lệ pattern per-component đã dùng cho `strategy:`/`rollouts:`) là hợp lý so
với lợi ích tách bạch lâu dài.

## 4. Codebase footprint (mô tả, CHƯA tạo ở lượt này)

- **(A) Terraform** (`infra/terraform/`): clone khối resource trong `rds.tf` (SG + subnet group + parameter
  group + `aws_db_instance`) thành instance mới, ví dụ `techx-tf4-accounting-postgresql` — mirror mọi
  thuộc tính của instance hiện tại: `postgres 17.9`, `db.t4g.micro`, `multi_az=true`,
  `storage_encrypted=true`, `backup_retention_period=7`, `deletion_protection=true`,
  `manage_master_user_password=true`, final snapshot, `monitoring_interval=0`. Có thể clone thêm
  `postgresql-migration-backup.tf` (đổi prefix `rel15/` → `rel23/`) nếu cần một bản S3 dump pre-cutover
  riêng cho migration này.
- **(B) Kubernetes/GitOps**: ExternalSecret mới (theo PA-A §3.2) trong
  `[gitops] platform/secrets/managed-data-secrets.yaml`; sửa `techx-corp-chart/templates/_pod.tpl`
  (`$pgKeyMap`) + `techx-corp-chart/values.yaml` để `accounting` trỏ `secretName` riêng;
  `[gitops] environments/production/app-values.yaml` (`managedData.postgresql` block) cập nhật tương ứng.
- **(C) Scripts** (`docs/cdo08/week3/mandate20/scripts/postgres/` — mới, theo PA-A §3.1): script scale
  `accounting` về 0, `pg_dump`/`pg_restore` schema `accounting`, script cutover secret, script parity-check
  (row count 3 bảng), script rollback. Đặt số thứ tự khi thực thi thật, chưa tạo ở lượt này.

## 5. Quy trình theo 4 subtask (từ `REL-23.csv`)

### Subtask 1 — Provision dedicated accounting RDS instance

- [ ] Private subnet/security group riêng (mirror `techx-tf4-rds-postgresql` SG, ingress từ EKS node SG).
  **Lệnh:** `terraform plan -target=aws_db_instance.accounting_postgresql` (tên resource dự kiến).
  **Expected:** plan chỉ thêm mới, không đổi resource hiện có.
- [ ] Encryption (`storage_encrypted=true`), TLS bắt buộc, `deletion_protection=true`.
- [ ] Automated backup + PITR, `backup_retention_period=7`.
- [ ] Parameter group/monitoring baseline phù hợp (mirror parameter group hiện tại nếu không cần
  `rds.logical_replication` — chỉ cần nếu chọn PA-B ở §3.1).

**Acceptance Criteria (từ CSV):** instance private và healthy · PITR enabled · không expose public
endpoint · có evidence `terraform plan`/`apply` lưu lại.

### Subtask 2 — Migrate accounting schema and data safely

- [ ] Chọn migration method (theo §3.1 — đề xuất PA-A) và cutover window (khung giờ thấp tải).
- [ ] Scale `accounting` Deployment về 0 (write-freeze tự nhiên).
  **Lệnh:** `kubectl scale deployment/accounting -n techx-tf4 --replicas=0`.
- [ ] `pg_dump` schema `accounting` từ instance cũ → `pg_restore` vào instance mới.
- [ ] Đối chiếu row count 3 bảng (`accounting."order"`, `accounting.orderitem`, `accounting.shipping`) +
  order ID + tổng số tiền giữa 2 instance — xem [§7 Data parity checklist](#7-data-parity-checklist).
- [ ] Ghi lại rollback checkpoint (thời điểm dump, snapshot instance cũ) trước cutover.

**Acceptance Criteria (từ CSV):** schema và data integrity pass · row/order reconciliation không thiếu ·
có rollback checkpoint trước cutover.

### Subtask 3 — Update accounting secret and application connection

- [ ] Theo PA-A §3.2: tạo AWS Secrets Manager secret mới + ExternalSecret mới cho `accounting`.
- [ ] Xác nhận ExternalSecret sync `Ready=True`, K8s Secret mới xuất hiện trong `techx-tf4`.
  **Lệnh:** `kubectl get externalsecret rds-accounting-secret -n techx-tf4`.
- [ ] Rollout `accounting` có kiểm soát (Deployment `strategy: Recreate` — pod cũ dừng hẳn trước khi pod
  mới start, khớp cơ chế write-freeze ở Subtask 2).
- [ ] Không ghi connection string thật vào Git/log — mọi evidence phải mask (`Password=***`).

**Acceptance Criteria (từ CSV):** accounting kết nối instance mới · secret sync Healthy · không có
plaintext credential trong Git/evidence · rollout không làm mất Kafka consumption kéo dài (consumer group
`accounting` phải resume đúng offset, không reset).

### Subtask 4 — Validate order processing and stabilize cutover

- [ ] Produce test order qua luồng checkout thật (môi trường tách biệt/staging nếu có, tránh production
  thật nếu chưa đủ tự tin).
- [ ] Verify `accounting` consume và persist đúng vào instance mới.
- [ ] Theo dõi consumer lag / error rate / DB connection count trong giai đoạn stabilization.
- [ ] Giữ nguyên schema cũ trên instance cũ trong suốt thời gian stabilization — **không xoá ngay**.

**Acceptance Criteria (từ CSV):** test order xuất hiện đúng trên instance mới · không duplicate/missing
order · không còn write mới vào schema `accounting` cũ · chỉ cleanup schema cũ sau khi có approval.

## 6. Rollback playbook

- **Bước R.1** — Nếu phát hiện lỗi sau cutover secret (Subtask 3) nhưng **trước khi** có ghi mới vào
  instance mới: repoint ExternalSecret/ `accounting` về secret cũ (instance cũ vẫn còn nguyên schema —
  chưa xoá theo Subtask 4), scale lại `accounting`, consumer tự resume từ offset cũ. Không mất dữ liệu vì
  chưa có ghi nào tách rời trên instance mới.
- **Bước R.2** — Nếu phát hiện lỗi **sau khi** đã có order mới ghi vào instance mới (giai đoạn Subtask 4):
  không rollback bằng cách xoá dữ liệu instance mới; thay vào đó `pg_dump` bổ sung phần chênh lệch từ
  instance mới về lại instance cũ trước khi repoint, tương tự tinh thần "reverse-CDC"/riot-redis backfill
  đã dùng cho REL-16 — chi tiết cụ thể cần thiết kế thêm khi thực thi thật, không suy đoán trước ở đây.
- **Bước R.3** — Trong mọi trường hợp, không xoá schema `accounting` trên instance cũ cho tới khi Subtask
  4 xác nhận ổn định và có approval — đây chính là điều kiện "giữ schema cũ trong stabilization" của CSV.

## 7. Data parity checklist

Mọi query dưới đây chạy trên cả 2 instance để đối chiếu, không có credential thật trong evidence.

| ID | Giai đoạn | Query đối chiếu | Tiêu chuẩn đạt |
|---|---|---|---|
| P-1 | Trước cutover (baseline) | `SELECT count(*) FROM accounting."order";` | Ghi lại baseline count trên instance cũ trước khi dump |
| P-2 | Trước cutover (baseline) | `SELECT count(*) FROM accounting.orderitem;` và `SELECT count(*) FROM accounting.shipping;` | Ghi lại baseline count |
| P-3 | Trước cutover (baseline) | `SELECT max(order_id) FROM accounting."order";` (hoặc tổng hợp theo thời gian ghi nhận nếu có cột timestamp) | Xác định mốc order cuối cùng trước freeze |
| A-1 | Sau restore, trước cutover connection | `SELECT count(*) FROM accounting."order";` trên instance mới | Bằng đúng P-1 (0 lệch) |
| A-2 | Sau restore, trước cutover connection | So `orderitem`/`shipping` count trên instance mới với P-2 | Bằng đúng P-2 (0 lệch), FK giữa 3 bảng còn nguyên (không orphan `orderitem`/`shipping` thiếu `order_id` cha) |
| A-3 | Sau khi bật lại consumer (Subtask 4) | So sánh số order mới consume được với số order thật đã checkout trong khoảng thời gian `accounting` bị scale 0 | Không thiếu, không trùng đơn nào — đối chiếu qua log/metric checkout thật |

## 8. PM Approval Gate

| Field | Value |
|---|---|
| Task | `[CDO08-REL-23][P0][RDS] Isolate accounting into a dedicated RDS recovery boundary` |
| Chi phí phát sinh | 1 RDS instance mới (`db.t4g.micro`, Multi-AZ) — cần PM xác nhận nằm trong ngân sách ~$300/tuần/TF theo ràng buộc Mandate 20 |
| Trạng thái | **PENDING** |
| Gate | Không chạy bất kỳ script/thao tác tạo tài nguyên/migrate nào cho tới khi PM (Hải) duyệt kế hoạch này |

## 9. Chưa làm ở lượt này (out of scope)

Tài liệu này chỉ là **kế hoạch**. Chưa: tạo RDS instance mới, tạo/sửa secret AWS, sửa Terraform/chart/GitOps,
chạy bất kỳ script pg_dump/restore nào, produce test order, tạo PR. Việc thực thi thật sẽ theo đúng 4 subtask
và 2 quyết định thiết kế (đã chọn PA-A cho cả 2, chờ PM duyệt ở §8) khi được yêu cầu ở lượt sau.
