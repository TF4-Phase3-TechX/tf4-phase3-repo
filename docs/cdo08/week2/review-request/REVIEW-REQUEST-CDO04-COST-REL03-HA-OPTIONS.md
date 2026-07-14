# Yêu cầu CDO04 review Cost/Performance - REL-03 HA Options

**Backlog:** CDO08-REL-03  
**Bên yêu cầu:** CDO08  
**Bên review:** CDO04 Cost/Performance  
**Trạng thái:** CDO04 đã phản hồi - chốt hướng persistence hiện tại, defer HA managed service

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

## CDO04 Decision Summary

| Component | Decision | Lý do |
|-----------|----------|-------|
| PostgreSQL | **Approve PG-A**: in-cluster PostgreSQL + PVC + backup/restore proof | Chi phí thấp, dữ liệu đã an toàn trên EBS gp3/PVC + backup; chấp nhận downtime ngắn khi restart |
| PostgreSQL Alt | **Approve dự phòng PG-C**: RDS Multi-AZ | Chỉ dùng nếu sau này cần DB managed failover/backup hoàn chỉnh; vẫn nằm trong budget nhưng chưa cần làm ngay |
| PostgreSQL | **Reject PG-B**: operator/replication in-cluster | Vận hành replication/failover phức tạp, có rủi ro lag/split-brain và tốn thêm CPU/RAM |
| Valkey | **Approve VK-A**: single pod + PVC + AOF | Cart là dữ liệu tạm thời; PVC + AOF là cân bằng tốt giữa chi phí và độ bền |
| Valkey | **Reject VK-B**: Sentinel/operator in-cluster | Vận hành master election/failover phức tạp, rủi ro split-brain |
| Valkey | **Reject VK-C**: ElastiCache Multi-AZ | Chi phí quá cao so với giá trị cart state |
| Kafka | **Approve KF-A**: single broker + PVC | Tối ưu chi phí, giữ broker log/event qua restart |
| Kafka Alt | **Approve dự phòng KF-C**: Amazon MSK | Chỉ dùng nếu business bắt buộc HA Kafka; cost cao hơn |
| Kafka | **Reject KF-B**: StatefulSet 3 broker | Tốn CPU/RAM, có nguy cơ node pressure và phát sinh chi phí ẩn do phải scale thêm node |

Kết luận: **REL-03 hiện triển khai persistence incremental, chưa triển khai HA full.** Full HA/managed service được defer cho task riêng nếu business yêu cầu và sau khi có cost/technical approval mới.

---

### PostgreSQL

| Option | Mô tả | Reliability benefit | Cost cần CDO04 estimate | Risk/Trade-off |
|--------|-------|---------------------|--------------------------|----------------|
| PG-A: Giữ in-cluster PostgreSQL + PVC + backup/restore proof | Không bật HA ngay, chỉ hoàn thiện backup/restore và pod recreation test | Giảm rủi ro mất dữ liệu, chi phí thấp | Backup storage/snapshot cost | **Approved / Recommended** |
| PG-B: PostgreSQL operator/replication in-cluster | Primary/standby, failover trong Kubernetes | Có HA in-cluster, không cần managed DB | Thêm pod, EBS, CPU/memory, operational cost | **Rejected** vì vận hành phức tạp, rủi ro lag/split-brain |
| PG-C: RDS Multi-AZ | Chuyển DB sang managed RDS Multi-AZ | Managed failover, backup/restore tốt hơn | RDS instance + storage + backup + Multi-AZ cost | **Approved dự phòng / Defer** |

**Chốt:** Làm PG-A trước. Không triển khai PG-B. PG-C để dự phòng nếu sau này business yêu cầu managed DB HA.

---

### Valkey Cart

| Option | Mô tả | Reliability benefit | Cost cần CDO04 estimate | Risk/Trade-off |
|--------|-------|---------------------|--------------------------|----------------|
| VK-A: Valkey single pod + PVC + AOF | Giữ PR PVC hiện tại | Cart còn sau pod recreate, chi phí thấp | EBS 5Gi + IO | **Approved / Recommended** |
| VK-B: Valkey in-cluster master/replica + Sentinel/operator | Chạy replication/failover trong Kubernetes | Giảm downtime khi pod/node lỗi | Thêm pod, EBS nếu cần, CPU/memory | **Rejected** vì vận hành phức tạp, rủi ro split-brain |
| VK-C: ElastiCache Valkey/Redis Multi-AZ | Managed cache Multi-AZ | Managed failover, ít vận hành hơn | Node cost, Multi-AZ, backup/snapshot nếu bật | **Rejected** vì cost cao so với giá trị cart state |

**Chốt:** Làm VK-A. Không triển khai VK-B/VK-C trong phase này.

---

### Kafka

| Option | Mô tả | Reliability benefit | Cost cần CDO04 estimate | Risk/Trade-off |
|--------|-------|---------------------|--------------------------|----------------|
| KF-A: Single broker + PVC | Giữ PR PVC hiện tại | Broker log còn qua pod recreate, chi phí thấp | EBS 10Gi + IO | **Approved / Recommended** |
| KF-B: Kafka StatefulSet multi-broker + PVC | Nhiều broker, replication factor/min ISR | HA in-cluster, event durability tốt hơn | 3 broker pods, EBS per broker, CPU/memory | **Rejected** vì node pressure và cost ẩn |
| KF-C: Amazon MSK | Managed Kafka | Managed HA, broker/storage vận hành bởi AWS | MSK cluster cost, storage, data transfer | **Approved dự phòng / Defer** nếu business bắt buộc HA Kafka |

**Chốt:** Làm KF-A. Không triển khai KF-B. KF-C để dự phòng nếu sau này business bắt buộc HA Kafka.

---

## CDO04 cần quyết định gì?

CDO04 vui lòng review và trả lời theo format:

| Component | Option CDO04 đề xuất | Estimated monthly cost | Estimated weekly cost | Budget impact | Decision |
|-----------|----------------------|------------------------|-----------------------|---------------|----------|
| PostgreSQL | **PG-A** | `~$1.30/tháng` | `~$0.30/tuần` | Low | **Approve / Recommended** |
| PostgreSQL Alt | **PG-C** | `~$26.08/tháng` | `~$6.02/tuần` | Medium | **Approve dự phòng / Defer** |
| Valkey | **VK-A** | `~$0.40/tháng` | `~$0.09/tuần` | Low | **Approve / Recommended** |
| Kafka | **KF-A** | `~$0.80/tháng` | `~$0.18/tuần` | Low | **Approve / Recommended** |
| Kafka Alt | **KF-C** | `~$61.04/tháng` | `~$14.09/tuần` | High | **Approve dự phòng / Defer** |

---

## Decision rule đề xuất

- Phase này triển khai **PG-A / VK-A / KF-A**.
- Không triển khai **PG-B / VK-B / KF-B** vì rủi ro vận hành và chi phí tài nguyên.
- Không triển khai **VK-C** vì cost cao so với giá trị cart state.
- **PG-C / KF-C** chỉ là phương án dự phòng nếu business bắt buộc HA managed service.
- Không merge HA implementation mới nếu chưa có CDO04 cost approval và Nguyên technical review.

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
