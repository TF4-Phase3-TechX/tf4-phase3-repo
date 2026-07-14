# Yêu cầu CDO04 review Cost/Performance - REL-03 HA Options

**Backlog:** CDO08-REL-03  
**Bên yêu cầu:** CDO08  
**Bên review:** CDO04 Cost/Performance  
**Trạng thái:** Draft - xin CDO04 review phương án trước khi tạo implementation task HA

---

## Mục tiêu

CDO08 đã tách REL-03 thành 2 lớp:

1. **Persistence incremental:** thêm PVC cho Valkey/Kafka để giảm rủi ro mất dữ liệu khi pod recreate. Phần này được cover bởi `REVIEW-REQUEST-CDO04-COST-REL03-PVC.md`.
2. **High Availability thật sự:** cần replication/failover design cho PostgreSQL, Valkey và Kafka. File này xin CDO04 review các lựa chọn HA trước khi CDO08 chọn hướng implement.

Lưu ý: HA cho stateful service **không thể chỉ tăng `replicas: 2`**. Cần có cơ chế replication, failover, backup/restore, migration và rollback rõ ràng.

---

## Hiện trạng sau PR PVC

| Component | Trạng thái hiện tại | Đã có persistence? | Đã HA? | Ghi chú |
|-----------|---------------------|--------------------|--------|---------|
| PostgreSQL | 1 pod, `postgresql-pvc` | Có | Chưa | Có PVC nhưng không có standby/failover |
| Valkey | 1 pod, `valkey-cart-pvc`, AOF | Có sau PR PVC | Chưa | Giảm mất cart khi pod recreate, vẫn downtime nếu pod/node lỗi |
| Kafka | 1 broker/controller, `kafka-pvc` | Có sau PR PVC | Chưa | Giữ broker log qua pod recreate, vẫn single broker |

---

## Option cần CDO04 review

### PostgreSQL

| Option | Mô tả | Reliability benefit | Cost cần CDO04 estimate | Risk/Trade-off |
|--------|-------|---------------------|--------------------------|----------------|
| PG-A: Giữ in-cluster PostgreSQL + PVC + backup/restore proof | Không bật HA ngay, chỉ hoàn thiện backup/restore và pod recreation test | Giảm rủi ro mất dữ liệu, chi phí thấp | Backup storage/snapshot cost | Vẫn downtime khi pod/node lỗi; không có failover |
| PG-B: PostgreSQL operator/replication in-cluster | Primary/standby, failover trong Kubernetes | Có HA in-cluster, không cần managed DB | Thêm pod, EBS, CPU/memory, operational cost | Vận hành phức tạp, failover/restore phải tự quản |
| PG-C: RDS Multi-AZ | Chuyển DB sang managed RDS Multi-AZ | Managed failover, backup/restore tốt hơn | RDS instance + storage + backup + Multi-AZ cost | Cần migration endpoint/secret, cutover, rollback khó hơn |

**CDO08 leaning:** PG-C là production-correct nếu budget cho phép. Nếu budget không cho phép, PG-A là bước ngắn hạn an toàn hơn PG-B.

---

### Valkey Cart

| Option | Mô tả | Reliability benefit | Cost cần CDO04 estimate | Risk/Trade-off |
|--------|-------|---------------------|--------------------------|----------------|
| VK-A: Valkey single pod + PVC + AOF | Giữ PR PVC hiện tại | Cart còn sau pod recreate, chi phí thấp | EBS 5Gi + IO | Vẫn downtime, không có failover |
| VK-B: Valkey in-cluster master/replica + Sentinel/operator | Chạy replication/failover trong Kubernetes | Giảm downtime khi pod/node lỗi | Thêm pod, EBS nếu cần, CPU/memory | Operational complexity, failover cần test kỹ |
| VK-C: ElastiCache Valkey/Redis Multi-AZ | Managed cache Multi-AZ | Managed failover, ít vận hành hơn | Node cost, Multi-AZ, backup/snapshot nếu bật | Cần đổi endpoint/secret, cost cao hơn |

**CDO08 leaning:** VK-C nếu business yêu cầu cart no-downtime và budget cho phép. Nếu chưa đủ budget, VK-A là bước tạm chấp nhận được sau khi verify cart persistence.

---

### Kafka

| Option | Mô tả | Reliability benefit | Cost cần CDO04 estimate | Risk/Trade-off |
|--------|-------|---------------------|--------------------------|----------------|
| KF-A: Single broker + PVC | Giữ PR PVC hiện tại | Broker log còn qua pod recreate, chi phí thấp | EBS 10Gi + IO | Vẫn single broker/controller, không HA |
| KF-B: Kafka StatefulSet multi-broker + PVC | Nhiều broker, replication factor/min ISR | HA in-cluster, event durability tốt hơn | 3 broker pods, EBS per broker, CPU/memory | Rất phức tạp, cần topic/offset/replication migration |
| KF-C: Amazon MSK | Managed Kafka | Managed HA, broker/storage vận hành bởi AWS | MSK cluster cost, storage, data transfer | Cost cao, migration phức tạp |

**CDO08 leaning:** KF-C là production-correct nếu budget đủ. Nếu không, chỉ nên làm KF-B khi có technical owner đủ mạnh và staging/fault test rõ ràng. Không nên “tăng replicas” Kafka nếu chưa có replication/topic design.

---

## CDO04 cần quyết định gì?

CDO04 vui lòng review và trả lời theo format:

| Component | Option CDO04 đề xuất | Estimated monthly cost | Estimated weekly cost | Budget impact | Decision |
|-----------|----------------------|------------------------|-----------------------|---------------|----------|
| PostgreSQL | PG-A / PG-B / PG-C | ... | ... | Low/Medium/High | Approve / Defer / Reject |
| Valkey | VK-A / VK-B / VK-C | ... | ... | Low/Medium/High | Approve / Defer / Reject |
| Kafka | KF-A / KF-B / KF-C | ... | ... | Low/Medium/High | Approve / Defer / Reject |

---

## Decision rule đề xuất

- Nếu managed service nằm trong budget và giảm operational risk rõ ràng: ưu tiên **RDS Multi-AZ**, **ElastiCache Multi-AZ**, **MSK**.
- Nếu managed service vượt budget: giữ PVC incremental, bổ sung backup/restore/fault evidence, defer HA managed service.
- Không triển khai in-cluster replication nếu chưa có owner chịu vận hành, runbook failover, rollback và staging test.
- Không merge HA implementation nếu chưa có CDO04 cost approval và Nguyên technical review.

---

## Output CDO08 sẽ tạo sau khi CDO04 phản hồi

Sau khi CDO04 chọn option hoặc defer, CDO08 sẽ tạo task/PR riêng cho từng component:

- `[CDO08-REL-03A][PostgreSQL] ...`
- `[CDO08-REL-03B][Valkey] ...`
- `[CDO08-REL-03C][Kafka] ...`

Mỗi task implement phải có:

- Migration plan
- Rollback boundary
- Smoke/fault test
- Evidence runtime
- Cost approval link
- Technical review approval
