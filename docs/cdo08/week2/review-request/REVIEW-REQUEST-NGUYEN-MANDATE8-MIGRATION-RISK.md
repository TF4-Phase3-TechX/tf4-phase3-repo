# Review request — Nguyên duyệt technical risk cho Mandate 8

| Thuộc tính | Giá trị |
|---|---|
| Requester | Phương / CDO08-REL-13 |
| Reviewer | Nguyên |
| Trạng thái | Pending technical approval |
| Thời điểm cần quyết định | Trước khi REL-14 apply infrastructure hoặc REL-15/REL-16/REL-17 migrate/cutover |
| SLO guardrail | Checkout success rate phải duy trì **≥ 99%** trong cutover |

## 1. Nguyên cần quyết định gì?

Review này cần chốt năm quyết định kỹ thuật:

1. Có approve thứ tự **Valkey → Kafka/MSK → PostgreSQL** không?
2. PostgreSQL dùng full load + CDC/replication hay chỉ dump/restore?
3. Active cart trong Valkey được migrate hay cold cutover và bỏ cart?
4. Kafka topic, record và consumer offset được mirror/cutover như thế nào?
5. Observation/rollback window kéo dài bao lâu và khi nào REL-18 được xóa pod/PVC self-hosted?

**Technical gate:** Không cutover khi một quyết định còn `Pending`, runtime inventory chưa đủ, parity/rollback rehearsal chưa pass hoặc checkout baseline không đạt 99%.

## 2. Phạm vi review

Mandate 8 yêu cầu chuyển ba data store đang tự vận hành trong EKS sang dịch vụ AWS managed:

- PostgreSQL → Amazon RDS for PostgreSQL.
- Valkey → Amazon ElastiCache for Valkey.
- Kafka → Amazon MSK.

Review này chỉ duyệt migration order, data-loss risk, rollback boundary, SLO guardrail và cleanup gate. Review này không tự cấp quyền provision resource hoặc thay production endpoint. CDO04 vẫn phải duyệt cost; Thuỷ/SEC-13 vẫn phải duyệt secret, TLS và authentication.

## 3. Baseline cần biết trước khi đánh giá risk

Repository hiện cho thấy:

| Store | Baseline trong repository | Điểm chưa biết cho đến khi kiểm tra runtime |
|---|---|---|
| PostgreSQL 17.6 | Một `Deployment`; Service `postgresql:5432`; PVC `postgresql-pvc` 10 GiB; database `otel`; schema `catalog`, `reviews`, `accounting`; một số client dùng credential plain text và tắt TLS | Dung lượng thật, TPS, extension, WAL rate, backup gần nhất, PVC/backup health và restore duration |
| Valkey 9.0.1 | Một `Deployment`; Service `valkey-cart:6379`; PVC `valkey-cart-pvc` 5 GiB; AOF bật; Cart lưu customer state có TTL | Key count/type, TTL distribution/max, AOF health, peak memory, eviction và restore khả năng thực tế |
| Kafka KRaft | Một broker `Deployment`; plaintext `kafka:9092`; PVC `kafka-pvc` 10 GiB; baseline topic `orders`; Checkout produce, Accounting/Fraud Detection consume | Danh sách topic authoritative, partition/config/retention, group offset/lag, high watermark và message throughput |

PVC/AOF trong chart không chứng minh dữ liệu runtime an toàn hoặc backup restore được. Nếu runtime khác repository, runtime evidence là nguồn quyết định và kế hoạch phải được cập nhật trước approval.

## 4. Migration order đề xuất

1. **Valkey → ElastiCache**
   - Dependency trực tiếp là Cart.
   - Cart journey dễ canary và rollback hơn hai store còn lại.
   - Dùng để xác minh sớm private DNS, Security Group, TLS, secret và observability.
2. **Kafka → MSK**
   - Hoàn tất topic, record, offset và idempotency trước khi chuyển PostgreSQL system of record.
   - Xác minh end-to-end flow Checkout → Accounting/Fraud Detection.
3. **PostgreSQL → RDS**
   - Thực hiện cuối vì có nhiều application phụ thuộc và data integrity risk cao nhất.
4. **Cleanup qua REL-18**
   - Chỉ thực hiện sau observation/rollback window, data parity và approval.
   - REL-19 gom và lập index evidence sau mỗi change window và sau cleanup.

Mỗi store phải có một change window riêng. Không bắt đầu store tiếp theo khi store trước chưa hết observation period hoặc còn unresolved data/SLO issue.

**Nguyên quyết định:** `<Approve order / Change order + reason / Conditions>`

## 5. Risk assessment theo từng store

| Store | Rủi ro mất hoặc sai dữ liệu | Rủi ro khi rollback | Control bắt buộc đề xuất |
|---|---|---|---|
| PostgreSQL | Write phát sinh sau full dump; CDC lag chưa về 0; thiếu extension/schema/index/sequence/trigger/grant; collation khác; backup không restore được | Nếu RDS đã nhận write mới mà đổi thẳng về source, write mới sẽ mất; hai phía cùng nhận write có thể gây split-brain | Compatibility inventory; backup/restore rehearsal; full load + CDC; write-drain ở lag/LSN = 0; schema/table/row/checksum/sequence parity; chỉ reverse-sync/reconcile trước rollback sau first write |
| Valkey | Mất active cart hoặc TTL; sai key type/serialization; write xảy ra trong lúc backfill; eviction do target thiếu memory | Target-only write không có ở source; rollback có thể làm cart quay về trạng thái cũ hoặc TTL bị kéo dài/rút ngắn | PM decision; giữ key type/value/TTL; compatible online migration/snapshot hoặc `SCAN` backfill + dual-write; sampled hash/TTL check; zero unexpected eviction; cart journey trước/sau migration |
| Kafka | Thiếu topic/config/record; committed offset không được mirror; cutover vào sai offset; rebalance tạo gap hoặc duplicate | Offset namespace khác giữa cluster; hai consumer cùng tạo business effect; producer ghi hai cluster nhưng không reconcile được | Inventory runtime; pre-create topic; MM2/MSK Replicator hoặc controlled drain; checkpoint/translated offset; per-partition watermark; event ID; idempotent producer; consumer dedupe/business idempotency; consumer-first then producer switch |

## 6. Checkout SLO risk trong cutover

Checkout có thể bị ảnh hưởng ngay cả khi store không được Checkout gọi trực tiếp:

- **Valkey:** Cart add/view/update lỗi sẽ chặn hoặc làm sai checkout journey.
- **Kafka/MSK:** Checkout producer lỗi có thể làm PlaceOrder fail hoặc làm order thiếu Accounting/Fraud event, tùy application behavior.
- **PostgreSQL/RDS:** Product Catalog, Product Reviews và Accounting có thể gặp lỗi DNS/TLS/connection hoặc query latency; downstream latency có thể kéo giảm checkout success.

### 6.1 Điều kiện được Go

- Checkout rolling 24 giờ ≥ 99% và error budget còn đủ.
- Synthetic checkout pass và không có active incident.
- Runtime inventory, backup/restore và rollback rehearsal pass.
- Private DNS, SG, NetworkPolicy, TLS, IAM/SCRAM và secret path pass.
- Data parity command/query đã rehearsal và có pass/fail threshold rõ.
- Grafana/Prometheus và CloudWatch dashboard đã mở.
- Có incident commander, store owner, application owner, observer và rollback decision maker.

### 6.2 Cách giảm SLO risk

- Canary hoặc progressive rollout.
- Không đổi ba store trong cùng change window.
- Theo dõi checkout/cart success, p95, 5xx, pod restart, DB connection/lag, cache error/eviction, Kafka produce error/consumer lag.
- Ghi timestamp mọi action và metric vào cutover log.
- PostgreSQL cần write-drain ngắn nếu CDC không thể bảo đảm final sync khi còn write.

### 6.3 Abort/rollback trigger

Rollback decision maker phải dừng rollout nếu có một trong các điều kiện:

- Checkout success rate < 99% liên tục 5 phút.
- Error hoặc latency tăng rõ so với baseline đã duyệt.
- Schema/row/checksum/key/event parity fail.
- PostgreSQL CDC lag/LSN không về 0 hoặc connection/write không ổn định.
- Cart journey fail, mất cart, TTL sai nghiêm trọng hoặc có unexpected eviction.
- Kafka lag không hồi phục, có missing record hoặc duplicate business effect.
- Private network, TLS, authentication hoặc secret gate fail.

## 7. Các quyết định kỹ thuật cần Nguyên chốt

### 7.1 PostgreSQL: dump/restore hay replication?

**Đề xuất:** full load + logical replication hoặc AWS DMS CDC cho production.

Lý do:

- Repository không chứng minh database đủ nhỏ để dump/restore nằm trong maintenance/error budget.
- CDC giảm write pause và cho phép chờ final lag/LSN về 0.
- Dump vẫn cần để làm backup/recovery artifact và restore rehearsal.

Chỉ chọn dump/restore không CDC khi runtime size và rehearsal chứng minh:

- Restore và parity hoàn tất trong maintenance window được PM duyệt.
- Write được dừng hoàn toàn trong window.
- RPO = 0 tại final cut-off.
- Rollback boundary trước/sau first write được ghi rõ.

**Nguyên quyết định:** `<Full load + CDC / Dump-restore only / Conditions>`

### 7.2 Valkey: migrate cart hay cold cutover?

**Đề xuất:** migrate active cart và giữ TTL.

Cart là customer state, không phải cache thuần. Phương án ưu tiên:

1. Online migration/replication nếu source-target compatibility cho phép.
2. RDB export/import nếu format tương thích và restore rehearsal pass.
3. `SCAN` backfill giữ type/value/TTL kết hợp dual-write nếu hai phương án trên không phù hợp.

Cold cutover và bỏ cart chỉ được phép khi PM/business approve bằng văn bản, ghi rõ customer impact, thời điểm TTL tối đa đã hết và communication plan.

**Nguyên quyết định:** `<Migrate active cart / Cold cutover with PM approval / Conditions>`

### 7.3 Kafka: topic, record và consumer offset xử lý thế nào?

**Đề xuất:** inventory runtime, pre-create topic/config trên MSK, sau đó mirror record và checkpoint/translate offset bằng MirrorMaker 2 hoặc MSK Replicator nếu compatibility cho phép.

Cutover sequence:

1. Chờ record/high watermark hội tụ theo từng partition.
2. Dừng hoặc kiểm soát source consumer theo group plan.
3. Chuyển consumer sang translated offset trên MSK.
4. Xác nhận Accounting/Fraud consumer sẵn sàng và không tạo duplicate business effect.
5. Chuyển Checkout producer sang MSK.
6. Verify canary correlation ID, payload hash, committed offset, missing count và duplicate count.

Không reset offset về `earliest` hoặc `latest` tùy tiện. Nếu không dùng được MM2/MSK Replicator, phải có controlled drain plan chứng minh source high watermark đã được consume và target start offset không tạo gap/duplicate.

**Nguyên quyết định:** `<MM2 / MSK Replicator / Controlled drain / Conditions>`

### 7.4 Khi nào được remove self-hosted workload?

**Đề xuất:** REL-18 chỉ xóa source sau khi tất cả điều kiện sau pass:

- Managed target ổn định trong observation/rollback window và checkout ≥ 99%.
- Data parity, backup/restore, failover và rollback rehearsal được sign-off.
- PostgreSQL không còn unresolved target-only write.
- Valkey key/value/type/TTL và cart journey pass.
- Kafka source được giữ tối thiểu bằng retention lớn nhất + 48 giờ và offset/event parity pass.
- Application manifests không còn endpoint `postgresql:5432`, `valkey-cart:6379` hoặc `kafka:9092`.
- CDO04, Thuỷ, Nguyên và PM approval đã được ghi nhận.
- Có recovery artifact và evidence trước khi xóa `postgresql-pvc`, `valkey-cart-pvc`, `kafka-pvc`, Deployment và Service cũ.

Cleanup phải bao gồm pod, Deployment/StatefulSet nếu có, Service, PVC, ConfigMap/Secret reference và endpoint cũ trong rendered manifests. Không chỉ scale replica về 0 rồi coi là Done.

**Nguyên quyết định observation/rollback window:** `<duration + start/end condition>`

## 8. Rollback sequence dễ thực hiện

| Store | Nếu target chưa nhận write mới | Nếu target đã nhận write mới |
|---|---|---|
| PostgreSQL | Dừng rollout và đổi config về `postgresql:5432` | Dừng write; reverse-sync/reconcile RDS → source; chứng minh parity; sau đó mới đổi endpoint |
| Valkey | Đổi Cart read về `valkey-cart:6379` khi source còn đồng bộ | Backfill/reconcile target → source, giữ TTL còn lại; chạy cart journey rồi mới đổi read |
| Kafka | Dừng target producer; map consumer về source offset đã ghi nhận | Reverse mirror/reconcile record; ngăn hai consumer tạo cùng business effect; chuyển consumer về source trước và producer sau |

Nguyên cần xác nhận các sequence này đủ an toàn hoặc ghi rõ control bổ sung.

## 9. Checklist Nguyên approve trước implementation

### 9.1 Trước REL-14 apply infrastructure

- [ ] Migration order và target compatibility được approve.
- [ ] Runtime sizing input đủ cho RDS, ElastiCache và MSK.
- [ ] CDO04 cost approval đã hoàn tất.
- [ ] Thuỷ/SEC-13 đã approve secret path, ESO/IRSA, TLS và IAM/SCRAM design.
- [ ] Private subnet, SG, DNS, route và NetworkPolicy design pass technical review.

REL-14 có thể chuẩn bị/review IaC trước các approval trên nhưng không được `apply`.

### 9.2 Trước REL-15 PostgreSQL migration/cutover

- [ ] PostgreSQL size/TPS/extensions/WAL/connection inventory đầy đủ.
- [ ] Migration method, write gate, parity query/checksum và reverse-sync boundary rõ.
- [ ] Backup/restore và rollback rehearsal pass; source PVC/backup recoverable.
- [ ] Maintenance window được PM duyệt nếu cần write pause.

### 9.3 Trước REL-16 Valkey migration/cutover

- [ ] Key/type/TTL/memory/persistence inventory đầy đủ.
- [ ] PM approve migrate cart hoặc cold cutover impact.
- [ ] TTL/value/type verification và dual-write/backfill semantics rõ.
- [ ] Cart add/view/update/remove/checkout rehearsal pass.

### 9.4 Trước REL-17 Kafka migration/cutover

- [ ] Topic/partition/config/retention/group/offset/lag inventory đầy đủ.
- [ ] Mirror/offset mapping và consumer-first/producer-second sequence đã test.
- [ ] Producer ack/idempotence và consumer duplicate protection pass.
- [ ] Accounting/Fraud end-to-end canary và missing/duplicate verifier pass.

### 9.5 Gate chung trước mọi cutover

- [ ] TLS/IAM/SCRAM client compatibility pass trong staging/canary.
- [ ] Dashboard, alert threshold, abort trigger và rollback decision maker sẵn sàng.
- [ ] Synthetic checkout và rolling SLO baseline pass.
- [ ] Không có task nào remove source trước rollback window và parity sign-off.
- [ ] REL-14/15/16/17 scope, owner và dependency không overlap; SEC-13 là prerequisite của app cutover.

## 10. Review decision record

Nguyên điền `Approved`, `Approved with conditions`, `Rejected` hoặc `Needs changes` cho từng gate.

| Gate | Decision | Conditions/evidence | Reviewer/date |
|---|---|---|---|
| Migration order | Pending | `<điền>` | `Nguyên / <date>` |
| PostgreSQL method và rollback boundary | Pending | `<điền>` | `Nguyên / <date>` |
| Valkey cart migration method | Pending | `<điền>` | `Nguyên + PM / <date>` |
| Kafka mirror/offset strategy | Pending | `<điền>` | `Nguyên / <date>` |
| Checkout SLO và rollback gates | Pending | `<điền>` | `Nguyên / <date>` |
| Observation/rollback window | Pending | `<duration + conditions>` | `Nguyên + PM / <date>` |
| Self-hosted removal gate | Pending | `<điền>` | `Nguyên + PM / <date>` |

### Final decision

- [ ] **Approved:** Tất cả technical gate pass; implementation task có thể bắt đầu theo dependency.
- [ ] **Approved with conditions:** Điều kiện, owner, deadline và evidence được ghi rõ; task liên quan chưa được qua gate cho đến khi điều kiện pass.
- [ ] **Needs changes:** CDO08 phải cập nhật design/rehearsal rồi gửi review lại.
- [ ] **Rejected:** Không triển khai phương án hiện tại.

- **Reviewer:** `Nguyên`
- **Decision date:** `<YYYY-MM-DD>`
- **Approval link:** `<link>`
- **Comment/conditions:** `<điền>`

## 11. Quy tắc mở task

- REL-14 được chuẩn bị IaC nhưng không được `apply` trước khi cost, security và technical gates liên quan hoàn tất.
- REL-15/REL-16/REL-17 không được migrate hoặc cutover khi gate riêng của store hoặc gate chung còn `Pending`.
- REL-18 không được cleanup khi observation window, parity hoặc approval chưa hoàn tất.
- REL-19 lập index evidence xuyên suốt, nhưng chỉ đóng evidence pack sau cleanup verification.

Nếu bất kỳ điều kiện nào chưa đạt, task liên quan giữ trạng thái **Blocked by technical approval**.
