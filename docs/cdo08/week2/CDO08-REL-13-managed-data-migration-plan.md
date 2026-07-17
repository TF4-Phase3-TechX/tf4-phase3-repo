# CDO08-REL-13 — Kế hoạch chuyển data layer sang dịch vụ AWS managed

| Thuộc tính | Giá trị |
|---|---|
| Owner | Phương |
| Pillar / Priority | Reliability / P0 |
| Mandate | Directive #8 |
| Deadline | Hết ngày 20/07/2026 |
| Trạng thái | Thiết kế chờ review |
| Giới hạn | Chỉ mô tả phương án. Không provision resource, không sửa application và không đổi production endpoint trong task này |

## 1. Tóm tắt cho người review

Mandate 8 yêu cầu thay toàn bộ data layer đang tự vận hành trong EKS bằng dịch vụ AWS managed:

- PostgreSQL trong cluster → Amazon RDS for PostgreSQL.
- Valkey của Cart → Amazon ElastiCache for Valkey.
- Kafka trong cluster → Amazon MSK.
- Sau khi cutover thành công và hết thời gian cho phép rollback, cluster không còn pod, PVC, Service hoặc endpoint cũ của PostgreSQL, Valkey và Kafka.

Kết quả bắt buộc:

1. Không mất dữ liệu trong quá trình chuyển đổi.
2. Checkout success rate duy trì **≥ 99%**.
3. Managed endpoint chỉ hoạt động trong private network, không public ra Internet.
4. Dữ liệu được mã hóa khi truyền và khi lưu trữ.
5. Credential được quản lý bằng AWS Secrets Manager và External Secrets Operator (ESO), không nằm trực tiếp trong Git hoặc Helm values.
6. Có bằng chứng data parity, cutover, rollback rehearsal và cleanup để mentor kiểm tra lại được.

Kế hoạch đề xuất là chuyển từng store trong một change window riêng theo thứ tự **Valkey → Kafka/MSK → PostgreSQL**. PM và Nguyên phải duyệt thứ tự cuối cùng trước khi triển khai.

## 2. Phạm vi và nguyên tắc

### 2.1 Trong phạm vi

- Ghi nhận hiện trạng và dependency của ba data store.
- Đề xuất target architecture, network, security và secret management.
- Chọn phương pháp migrate, kiểm tra data parity, cutover và rollback cho từng store.
- Xác định SLO guardrail, evidence, cost risk và trách nhiệm của REL-14 đến REL-19/SEC-13.

### 2.2 Ngoài phạm vi

- Tạo RDS, ElastiCache, MSK, subnet group, Security Group hoặc KMS key.
- Tạo hoặc thay đổi secret thật.
- Sửa application client, Helm values hoặc production endpoint.
- Xóa pod/PVC hiện tại.

Các thay đổi trên thuộc các implementation task ở mục 11.

### 2.3 Nguyên tắc an toàn

- Repository cho biết cấu hình mong muốn; runtime inventory mới là nguồn quyết định cho sizing và cutover.
- Không xóa hoặc scale down source khi vẫn còn trong rollback window.
- Không đổi đồng thời nhiều data store.
- Không rollback endpoint sau khi target đã nhận write mới nếu chưa reverse-sync hoặc reconcile dữ liệu.
- Mọi bước cutover và rollback phải có timestamp, người thực hiện và kết quả kiểm tra.

## 3. Hiện trạng xác nhận từ repository

Nguồn kiểm tra gồm `techx-corp-chart/values.yaml`, `techx-corp-chart/templates/_objects.tpl`, `techx-corp-chart/templates/component-pvcs.yaml`, `techx-corp-chart/postgresql/init.sql` và application configuration.

> Lưu ý: Có PVC hoặc AOF trong chart không chứng minh PVC đang Bound, dữ liệu đang an toàn hoặc backup đã restore được. Các nội dung đó phải được xác nhận bằng runtime evidence trước khi Go.

| Store | Cách đang chạy trong EKS | Persistence và backup thấy trong repo | Service phụ thuộc |
|---|---|---|---|
| PostgreSQL 17.6 | Một replica, Kubernetes `Deployment`, Service `postgresql:5432`, database `otel`; client đang dùng credential plain text và có client tắt TLS | `persistence.enabled: true`, PVC `postgresql-pvc` 10 GiB, storage class `gp2`, mount tại `/var/lib/postgresql/data`. Chưa thấy automated backup hoặc restore test trong chart | Product Catalog đọc schema `catalog`; Product Reviews đọc/ghi schema `reviews`; Accounting ghi schema `accounting` |
| Valkey 9.0.1 | Một replica, `Deployment`, Service `valkey-cart:6379`; memory request 32 MiB, limit 64 MiB | `persistence.enabled: true`, PVC `valkey-cart-pvc` 5 GiB, storage class `gp2`, mount `/data`; AOF được bật bằng `--appendonly yes`. Chưa có bằng chứng runtime về AOF health, fsync policy, RDB hoặc restore test | Cart đọc/ghi giỏ hàng có TTL; Checkout phụ thuộc Cart trong checkout journey |
| Kafka KRaft | Một broker, `Deployment`, plaintext `kafka:9092`; heap 400 MiB | `persistence.enabled: true`, PVC `kafka-pvc` 10 GiB, storage class `gp2`; log directory nằm dưới `/tmp/kafka-data` được mount vào PVC. Chỉ có một broker nên không có broker replication/HA; chưa thấy backup/restore workflow | Topic được code định nghĩa là `orders`; Checkout produce; Accounting và Fraud Detection consume |

### 3.1 Khoảng trống chưa thể kết luận từ repository

Trước khi approve sizing hoặc Go, owner phải chụp runtime inventory sau:

| Store | Runtime discovery bắt buộc |
|---|---|
| PostgreSQL | Version thực tế, extension, collation, role/grant, schema/table/index/sequence/trigger/large object; dung lượng DB/table; row count; TPS; connection p95/max; CPU/RAM/IOPS; WAL rate; PVC status; backup gần nhất và restore test |
| Valkey | `INFO persistence`, `INFO memory`, `DBSIZE`; peak memory; key namespace/type; TTL distribution và TTL tối đa; eviction; ops/sec; AOF/RDB status; PVC status; restore test |
| Kafka | Broker version; toàn bộ topic, partition, replication factor, retention và config; consumer group, committed offset và lag; per-partition high watermark; bytes in/out; message-size p95; PVC status |
| Kubernetes/network | Namespace; manifest đã render; Deployment, Service và PVC thực tế; NetworkPolicy; source SG; subnet/AZ; DNS; dashboard baseline |

Nếu runtime khác repository, runtime evidence là nguồn quyết định. Tài liệu này phải được cập nhật và review lại trước khi Go.

## 4. Target architecture

| Managed service | Workload đích | Baseline ban đầu, chờ sizing và CDO04 duyệt |
|---|---|---|
| RDS for PostgreSQL | Product Catalog, Product Reviews và Accounting | PostgreSQL major tương thích source; `db.t4g.micro`; gp3 20 GiB và storage autoscaling; Multi-AZ; automated backup 7 ngày; deletion protection |
| ElastiCache for Valkey | Cart state | Cluster mode disabled; `cache.t4g.micro`; một primary và một replica ở hai AZ; automatic failover; snapshot retention 7 ngày |
| Amazon MSK | Checkout producer; Accounting và Fraud Detection consumer | Ưu tiên MSK Serverless, private access, IAM authentication và TLS. Nếu client không hỗ trợ IAM, đánh giá MSK Provisioned với ba broker phù hợp và SCRAM |

Baseline trên không phải cấu hình provision cuối cùng. CDO04 phải thay bằng sizing dựa trên runtime metrics và AWS Pricing Calculator tại region triển khai thực tế.

### 4.1 Network

- RDS DB subnet group, ElastiCache subnet group và MSK VPC configuration dùng private data subnet ở ít nhất hai AZ, hoặc số AZ mà managed service yêu cầu.
- Không bật public endpoint hoặc public connectivity.
- EKS phải resolve được private DNS và route được tới managed endpoint.
- Ưu tiên Security Groups for Pods. Nếu cluster chưa hỗ trợ, chỉ allow node/cluster SG cần thiết và bổ sung Kubernetes NetworkPolicy egress.
- Không allow `0.0.0.0/0`; không dùng toàn bộ VPC CIDR nếu có thể dùng SG-to-SG.

| Target SG | Inbound source được phép | Port/protocol |
|---|---|---|
| `rds-postgres-sg` | SG của Product Catalog, Product Reviews, Accounting và migration runner | TCP 5432 qua TLS |
| `elasticache-valkey-sg` | SG của Cart và migration runner | TCP 6379 qua TLS |
| `msk-sg` | SG của Checkout, Accounting, Fraud Detection và migration tooling | Bootstrap port TLS/IAM do MSK endpoint thực tế cung cấp, thường là 9098 với IAM |

## 5. Security và secret management

### 5.1 Yêu cầu chung

- Mã hóa at rest bằng AWS-owned key hoặc customer-managed KMS key theo quyết định của SEC/CDO04.
- Mọi client connection phải dùng TLS và verify certificate/hostname.
- Không lưu password, auth token, bootstrap credential hoặc connection string trong Git, Helm values, ConfigMap hay plain environment value do manifest quản lý trực tiếp.
- Không ghi secret hoặc connection string đầy đủ vào application log, migration log hoặc evidence.
- Bật engine/audit log phù hợp, CloudWatch metrics/alarms và backup/snapshot retention tối thiểu 7 ngày.

### 5.2 Theo từng service

- **RDS:** bắt buộc TLS; client dùng `sslmode=verify-full` hoặc cơ chế tương đương và trust RDS CA bundle.
- **ElastiCache:** bật encryption at rest và in transit; dùng auth token/RBAC phù hợp topology; client verify hostname và certificate.
- **MSK:** dùng TLS với `SASL_SSL`; ưu tiên IAM, fallback SCRAM nếu compatibility test không đạt. Producer bật `acks=all`, idempotence và retry hữu hạn.

### 5.3 Secrets Manager và ESO

AWS Secrets Manager là source of truth. ESO đồng bộ secret vào đúng namespace bằng IRSA và least privilege. Thuỷ/SEC-13 chịu trách nhiệm chốt naming, JSON keys, ownership, rotation, refresh interval và quyền truy cập trước app cutover.

Path gợi ý để Thuỷ review:

- `/techx/<env>/data/rds`
- `/techx/<env>/data/valkey`
- `/techx/<env>/data/msk`

Đây mới là naming proposal, không phải secret path đã được approve.

## 6. Kế hoạch migration theo từng store

### 6.1 PostgreSQL → RDS

**Phương án đề xuất:** full load kết hợp CDC/logical replication cho production để thời gian dừng write ngắn nhất. Chỉ dùng `pg_dump`/`pg_restore` đơn thuần nếu rehearsal chứng minh database đủ nhỏ và PM + Nguyên duyệt maintenance window vẫn bảo đảm RPO 0.

#### Chuẩn bị và đồng bộ

1. Inventory version, extension, collation, role/grant, schema, table, index, sequence, trigger và large object; xác nhận tất cả tương thích RDS.
2. Tạo logical backup bằng `pg_dump` custom format. Lưu checksum file, thời gian bắt đầu/kết thúc và restore duration.
3. Restore thử vào môi trường rehearsal và chứng minh application có thể đọc/ghi.
4. REL-14 provision target đã duyệt. Restore full load sang RDS.
5. Nếu dùng CDC, bật logical replication hoặc AWS DMS và theo dõi replication lag/LSN đến khi bằng 0.

#### Kiểm tra trước cutover

- Schema và table list trước/sau giống nhau.
- Row count của từng table giống nhau tại cùng cut-off point.
- Deterministic checksum theo chunk giống nhau.
- Sequence/identity value, index, constraint và grant đúng.
- Một canary instance của từng application dùng RDS để chạy read smoke và isolated write smoke.
- Kết nối dùng private DNS, TLS verify-full và secret từ luồng SEC-13.

#### Cutover

1. Drain traffic hoặc tạm đóng write trong khoảng đã duyệt.
2. Chờ CDC lag/LSN về 0 và ghi timestamp final sync.
3. Đổi application config qua secret/config rollout của implementation task.
4. Rollout lần lượt Product Catalog, Product Reviews và Accounting; sau mỗi workload phải chạy smoke test.
5. Resume traffic và theo dõi tối thiểu 60 phút.

### 6.2 Valkey → ElastiCache

**Quyết định business bắt buộc:** Cart là customer state có TTL, không được tự động coi là cache có thể bỏ. Phương án mặc định là migrate active cart và giữ TTL. Chỉ được cold cutover và bỏ cart khi PM/business phê duyệt bằng văn bản, ghi rõ customer impact và thời điểm toàn bộ TTL hiện tại đã hết.

#### Chọn phương pháp

1. Inventory key namespace/type, TTL distribution, TTL tối đa, memory, eviction, ops/sec và AOF/RDB status.
2. Kiểm tra compatibility source/target rồi chọn một trong các phương án:
   - online migration/replication nếu được hỗ trợ;
   - export/import RDB tương thích;
   - application dual-write kết hợp backfill nếu hai phương án trên không phù hợp.
3. Nếu export/import: tạo RDB, import vào target, kiểm tra key type, sampled value hash và TTL delta.
4. Nếu backfill: dùng `SCAN`, không dùng `KEYS` trên production; serialize value đúng type và giữ TTL còn lại.
5. Khi dual-write, ghi source trước trong giai đoạn hội tụ. Failure phải observable, retryable và không được trả success giả cho client.

#### Kiểm tra và cutover

- So sánh key count theo namespace/type tại cùng timestamp.
- Kiểm tra sampled value hash và TTL delta nằm trong tolerance đã duyệt.
- Canary Cart đọc target và chạy add/view/update/remove.
- Chạy checkout với cart tạo trước migration và cart tạo sau migration.
- Chuyển Cart sang ElastiCache theo từng bước; theo dõi success rate, p95, connection, memory và eviction.

### 6.3 Kafka → MSK

**Mục tiêu:** không mất record, không xử lý trùng business effect và không đặt consumer vào sai offset.

#### Chuẩn bị và đồng bộ

1. Inventory toàn bộ topic/partition/config/retention, consumer group, committed offset, lag và per-partition high watermark. `orders` là baseline từ source; runtime inventory mới là danh sách authoritative.
2. Tạo topic trên MSK với partition/config phù hợp và replication theo target. Tắt uncontrolled auto-topic creation.
3. Kiểm tra Checkout, Accounting và Fraud Detection có hỗ trợ IAM authentication. Nếu không, chốt phương án SCRAM trước REL-14.
4. Dùng MirrorMaker 2 hoặc MSK Replicator khi compatibility cho phép để mirror record và checkpoint/translate offset. Không chỉ đổi bootstrap server.
5. Bổ sung event ID, idempotent producer và consumer deduplication, hoặc cung cấp bằng chứng business effect hiện tại đã idempotent.

#### Kiểm tra và cutover

1. Publish canary event có correlation ID lên MSK.
2. Consume bằng verifier group và so sánh payload hash.
3. Đối chiếu source-target high watermark theo từng partition.
4. Cutover consumer theo group plan và translated offset; bảo đảm không có hai consumer tạo cùng business effect.
5. Cutover Checkout producer sau khi consumer đã sẵn sàng.
6. Chứng minh Accounting ghi đúng order vào PostgreSQL và Fraud Detection xử lý đúng event.
7. Ghi nhận committed offset, lag, missing count và duplicate business-effect count.

## 7. Cutover, SLO và điều kiện dừng

### 7.1 Thứ tự đề xuất

1. **Valkey:** blast radius hẹp hơn, dùng để kiểm tra network, TLS, secret và observability path.
2. **Kafka/MSK:** ổn định event flow trước khi chuyển PostgreSQL system of record.
3. **PostgreSQL:** chuyển cuối cùng vì có nhiều workload phụ thuộc và rủi ro write lớn nhất.

Mỗi store có change window riêng. Không bắt đầu store tiếp theo cho đến khi store trước hết observation period và được sign-off.

### 7.2 Điều kiện được bắt đầu

- Checkout success rate rolling 24 giờ ≥ 99% và error budget còn đủ.
- Runtime inventory, sizing và approval đã đầy đủ.
- Backup/restore test, migration rehearsal và rollback rehearsal pass.
- Data parity query/script đã chuẩn bị và thử trước.
- Private DNS, SG, NetworkPolicy, TLS và secret gate pass.
- Grafana/Prometheus và CloudWatch dashboard đã mở.
- Có incident commander, store owner, app owner, observer và rollback decision maker.

### 7.3 Maintenance window

- Valkey và Kafka dùng online sync/dual-run nên mục tiêu là không cần customer maintenance window.
- PostgreSQL có thể cần write-drain ngắn. Nếu rehearsal không đạt zero-customer-downtime, PM phải duyệt maintenance window và communication plan trước khi Go.

### 7.4 Metrics phải theo dõi trong window

- Checkout success rate và p95 latency.
- Cart success rate, p95 latency và functional journey.
- HTTP/gRPC error, 5xx và pod restart.
- RDS connection, query latency/error, CPU/IO và replication lag.
- ElastiCache connection/error, memory, replication và eviction.
- MSK produce error, consumer lag, partition watermark và duplicate/missing verifier.

### 7.5 Abort và rollback trigger

Rollback decision maker phải dừng rollout khi có một trong các điều kiện:

- Checkout success rate < 99% liên tục 5 phút.
- Error hoặc latency tăng rõ so với baseline đã duyệt.
- Schema/row/checksum/key/event parity fail.
- PostgreSQL replication, write hoặc connection không ổn định.
- Cart journey fail, mất cart, TTL sai nghiêm trọng hoặc có eviction ngoài dự kiến.
- Kafka lag không hồi phục, có missing record hoặc duplicate business effect.
- Private network, TLS, authentication hoặc secret gate fail.

## 8. Rollback plan

| Store | Cách rollback | Ranh giới an toàn |
|---|---|---|
| PostgreSQL | Dừng rollout/traffic tới RDS. Nếu RDS chưa nhận write mới, đổi config về `postgresql:5432`. Nếu đã nhận write, dừng write, reverse-sync hoặc reconcile RDS → source, chứng minh parity rồi mới switch back | Không đổi endpoint về source một cách mù quáng sau first write vì sẽ làm mất write mới. Giữ source, PVC và backup đến khi hết rollback window và được sign-off |
| Valkey | Chuyển Cart read về `valkey-cart:6379` khi source vẫn nhận đủ write từ dual-write. Nếu target đã có target-only write, backfill/reconcile target → source và khôi phục TTL trước khi switch | Không xóa hoặc scale down source. Rollback ngay khi cart journey, key/value/TTL parity hoặc eviction gate fail |
| Kafka | Dừng producer tới MSK; reverse mirror hoặc reconcile record; map consumer offset về source; chuyển consumer về source trước, producer về `kafka:9092` sau | Không để hai consumer tạo duplicate business effect. Giữ source ít nhất bằng retention lớn nhất + 48 giờ và đến khi offset/event parity được sign-off |

REL-18 chỉ được cleanup sau khi rollback window kết thúc, parity pass, SLO ổn định và PM + Nguyên approve. Trước thời điểm đó, source được cô lập khỏi traffic không cần thiết nhưng phải còn recoverable.

## 9. Data parity và evidence phải nộp

| Area | Evidence bắt buộc |
|---|---|
| Baseline | Runtime inventory; manifest đã render; dependency/endpoint map; Deployment/Service/PVC status; backup status; dashboard screenshot trước cutover |
| RDS | Schema/table diff; row count từng table; deterministic checksum theo chunk; sequence/identity; backup checksum và restore log; CDC lag/LSN = 0; private/TLS/KMS/backup evidence; app read/write smoke |
| ElastiCache | PM decision về cart; key count theo namespace/type tại cùng timestamp; sampled value hash; TTL delta; zero unexpected eviction; cart add/view/update/remove/checkout smoke |
| MSK | Topic/partition/config map; source-target high watermark; group/offset/lag; canary correlation ID và payload hash; Accounting/Fraud evidence; missing = 0 và duplicate business effect = 0 hoặc idempotency proof |
| SLO/cutover | Timestamped cutover log; checkout ≥ 99% trong window; Grafana/CloudWatch screenshot; abort decision nếu có; rollback rehearsal/result |
| Cleanup | `kubectl get deploy,statefulset,pod,pvc,svc` và rendered-manifest search chứng minh không còn PostgreSQL/Valkey/Kafka self-hosted, PVC hoặc endpoint cũ |

Evidence phải ghi rõ environment, timestamp, command/query đã chạy, người thực hiện và kết quả. Log/screenshot phải che secret và connection string.

## 10. Cost estimate, câu hỏi cho CDO04 và risks

### 10.1 Planning estimate

Giả định workload nhỏ và chạy khoảng 168 giờ/tuần. Đây chỉ là khoảng ước tính để nhận diện cost risk; chưa gồm tax, data transfer, CloudWatch và KMS. CDO04 phải thay bằng AWS Pricing Calculator export tại đúng region và đúng thời gian chạy trước REL-14.

| Component | Baseline | Ước tính/tháng | Ước tính/tuần |
|---|---|---:|---:|
| RDS PostgreSQL | `db.t4g.micro`, Multi-AZ, gp3 20 GiB | $40–70 | $9–16 |
| ElastiCache Valkey | 2 × `cache.t4g.micro` | $22–43 | $5–10 |
| MSK Serverless | Cluster-hour và capacity/data processing | $545–800 | $126–185 |
| Backup/log/KMS headroom | Retention 7 ngày và monitoring | $15–40 | $4–9 |
| **Tổng managed estimate** | | **$622–953** | **$144–220** |

Dual-run làm chi phí tăng tạm thời. Trần TF khoảng $300/tuần cho toàn bộ AWS infrastructure, nên MSK là cost gate lớn nhất.

### 10.2 Câu hỏi CDO04 phải trả lời

- Region và số giờ chạy thực tế là gì?
- RDS Multi-AZ và ElastiCache replica có bắt buộc cho tất cả environment không?
- MSK Serverless hay Provisioned/SCRAM phù hợp hơn về compatibility và ngân sách?
- Phần ngân sách còn lại sau EKS, NAT, observability và các service khác là bao nhiêu?
- Chi phí dual-run, backup, log, KMS và data transfer đã được tính chưa?
- Calculator export và cost owner nào được dùng làm approval record?

### 10.3 Risk chính

| Store | Risk lớn nhất | Mitigation |
|---|---|---|
| PostgreSQL | Mất write hoặc schema/extension không tương thích | Compatibility scan; backup/restore rehearsal; CDC lag = 0; checksum; sequence check; reverse-sync boundary |
| Valkey | Mất active cart, sai TTL hoặc eviction | PM decision; giữ TTL; dual-write/backfill; cart journey; memory headroom và zero-eviction alarm |
| Kafka | Sai offset gây missing/duplicate business effect; MSK vượt budget | Mirror/checkpoint; event ID/idempotency; per-partition reconciliation; CDO04 option gate |

## 11. Implementation breakdown

| Task | Owner | Scope | Exit evidence |
|---|---|---|---|
| REL-14 | Nam | Provision private RDS, ElastiCache, MSK, subnet/SG/KMS/backup/monitoring theo option đã duyệt | Resource healthy; private/TLS/encryption/HA/backup evidence; chưa đổi app endpoint |
| SEC-13 | Thuỷ | Wire Secrets Manager + ESO/IRSA; loại plain credential khỏi values/env | Secret path, rotation, least privilege và pod consumption pass |
| REL-15 | Phương | Migrate PostgreSQL, parity, cutover, observe và rollback rehearsal | Schema/row/checksum/sequence, restore và SLO evidence |
| REL-16 | Quân | Migrate Valkey/Cart, giữ TTL, cutover và rollback | PM decision, key/value/TTL và cart journey evidence |
| REL-17 | Quân | Migrate Kafka/MSK topic, record, offset, producer/consumer và rollback | Không missing/duplicate business effect; Accounting/Fraud pass |
| REL-18 | Nam | Sau approval và rollback window, remove self-hosted workload/PVC/config cũ | Cluster và rendered-manifest cleanup evidence |
| REL-19 | Quyết | Gom, lập index và attach toàn bộ evidence vào Jira | Mentor-verifiable evidence pack và approval links |

## 12. Approval gates và Definition of Done

- [ ] Runtime inventory của PostgreSQL, Valkey, Kafka và Kubernetes đã đầy đủ; mọi khác biệt với repository đã được cập nhật vào tài liệu.
- [ ] CDO04 approve từng managed service, sizing, HA option, Calculator export, dual-run cost và budget headroom.
- [ ] Nguyên approve migration order, migration method, data-loss/rollback risk và cleanup gate.
- [ ] Thuỷ approve secret path/schema, ESO/IRSA, TLS/auth, rotation và secret ownership.
- [ ] PM approve migration order, maintenance window và quyết định migrate/discard active cart.
- [ ] Target architecture không có public endpoint/connectivity; SG, DNS, route và NetworkPolicy đã được review.
- [ ] Cutover và rollback runbook cho từng store đã rehearsal; evidence checklist có owner.
- [ ] Data parity method đã thử và có tiêu chí pass/fail rõ ràng.
- [ ] Scope REL-14 đến REL-19 và SEC-13 không overlap; không task nào remove source trước approval.
- [ ] Tài liệu, CDO04 review request, Nguyên technical review và các approval link đã được attach vào Jira CDO08-REL-13.

Khi tất cả checkbox trên hoàn tất, thiết kế mới đủ điều kiện chuyển từ **Design for review** sang **Approved for implementation**.
