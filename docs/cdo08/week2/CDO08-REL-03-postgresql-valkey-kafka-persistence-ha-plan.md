# PostgreSQL, Valkey and Kafka Persistence & High Availability Plan

**Backlog:** CDO08-REL-03  
**Owner:** Phương  
**Pillar:** Reliability  
**Priority:** P0  

---

# 1. Objective

Mục tiêu của tài liệu là:

- Xác nhận hiện trạng persistence và High Availability của PostgreSQL, Valkey và Kafka.
- Đề xuất phương án cải thiện persistence/HA.
- Đánh giá trade-off trước khi triển khai.
- Xây dựng roadmap, migration plan và rollback plan.

Không thực hiện thay đổi production trong task này.

---

# 2. Current State

| Component | Workload | Replica | PVC | HA | Dependent Services |
|-----------|----------|---------|-----|----|--------------------|
| PostgreSQL | Deployment | 1 | Yes | No | Product Catalog, Product Reviews, Accounting |
| Valkey | Deployment | 1 | No | No | Cart |
| Kafka | Deployment | 1 | No | No | Checkout, Accounting, Fraud Detection |

## Findings

- PostgreSQL đã có persistence thông qua `postgresql-pvc` nhưng vẫn là single replica nên chưa có High Availability.
- Valkey chưa có persistent storage và chưa có High Availability.
- Kafka chưa có persistent storage và chưa có High Availability.

---

# 3. Runtime Evidence

## PVC

```bash
kubectl get pvc -n techx-tf4
```

```text
NAME             STATUS   VOLUME                                     CAPACITY
postgresql-pvc   Bound    pvc-e0600223-7b8a-4bc6-ab58-bdb77e9653e0   10Gi 
```

## Deployment

```bash
kubectl get deployment,statefulset -n techx-tf4
```

```text
deployment.apps/postgresql    1/1
deployment.apps/valkey-cart   1/1
deployment.apps/kafka         1/1
```

## PostgreSQL Runtime

```bash
kubectl describe pod postgresql-879c5bd4-5fpq4 -n techx-tf4
```

Verified:

- Image: postgres:17.6
- Replica: 1
- PVC: postgresql-pvc
- Mount: /var/lib/postgresql/data
- Restart Count: 0

## Valkey Runtime

```bash
kubectl describe pod valkey-cart-5866fc4b85-ktkxq -n techx-tf4
```

Verified:

- Replica: 1
- No PersistentVolumeClaim
- No persistent storage mount

## Kafka Runtime

```bash
kubectl describe pod kafka-7f68655c75-l9fdf -n techx-tf4
```

Verified:

- Replica: 1
- Single broker/controller
- No PersistentVolumeClaim

## Restart Behavior

Đánh giá hành vi hiện tại của PostgreSQL, Valkey và Kafka khi Pod bị **restart**, **recreate** hoặc **reschedule**.

| Component | Current Behaviour | Risk |
|-----------|-------------------|------|
| **PostgreSQL** | Pod sử dụng `postgresql-pvc`. Khi Pod restart hoặc recreate, PVC sẽ được mount lại nên dữ liệu vẫn được giữ. Tuy nhiên do chỉ có **1 replica**, database sẽ bị downtime trong thời gian Pod khởi động lại và không có khả năng failover. | Medium |
| **Valkey** | Không sử dụng PersistentVolumeClaim. Khi Pod bị recreate hoặc reschedule sang node khác, dữ liệu trong bộ nhớ có thể bị mất. | High |
| **Kafka** | Chỉ có **1 broker** và chưa có persistent storage. Khi Pod hoặc node gặp sự cố, broker log và event có nguy cơ bị mất, đồng thời không có broker khác để tiếp tục xử lý. | High |

### Summary

- PostgreSQL đã có persistence thông qua PVC nhưng vẫn là **Single Point of Failure (SPOF)** do chỉ có một replica.
- Valkey chưa có persistence nên có nguy cơ mất **Cart State** khi Pod bị recreate hoặc node failure.
- Kafka chưa có persistence và High Availability nên có nguy cơ mất **Order Events** nếu broker gặp sự cố.
---

# 4. Chart Values Evidence

## PostgreSQL

**Source**

`techx-corp-chart/templates/postgresql-pvc.yaml`

Verified:

- Chart tạo PersistentVolumeClaim `postgresql-pvc`.

**Source**

`techx-corp-chart/values.yaml`

Verified:

- `replicas: 1`
- `PGDATA=/var/lib/postgresql/data/pgdata`
- PVC mount tới `postgresql-pvc`.

---

## Valkey

**Source**

`techx-corp-chart/values.yaml`

Verified:

- `replicas: 1`
- Không thấy PersistentVolumeClaim.
- Không thấy volume mount cho data.

---

## Kafka

**Source**

`techx-corp-chart/values.yaml`

Verified:

- `replicas: 1`
- Không thấy PersistentVolumeClaim.
- Không thấy volumeClaim cho broker log.

---

# 5. Persistence & HA Options

| Component | Current | Short-term | Long-term |
|-----------|---------|------------|-----------|
| PostgreSQL | Deployment + PVC | Backup/Restore | RDS Multi-AZ hoặc StatefulSet + Operator |
| Valkey | Deployment | PVC (nếu cần) | ElastiCache Multi-AZ |
| Kafka | Deployment | Review retention/replay | MSK hoặc StatefulSet Multi-Broker |

## PostgreSQL Recommendation

**Recommended**

- Giữ PostgreSQL hiện tại cùng `postgresql-pvc`.
- Ưu tiên hoàn thiện Backup/Restore trước.
- Sau khi CDO04 hoàn thành cost review sẽ đánh giá phương án migrate sang RDS Multi-AZ.

**Reason**

- Đã có persistence thông qua PVC.
- Migration ít rủi ro hơn so với thay đổi ngay sang kiến trúc HA.
- Không ảnh hưởng endpoint và application trong giai đoạn hiện tại.

---

## Valkey Recommendation

**Recommended**

- Giữ Valkey hiện tại.
- Chưa triển khai persistence ở giai đoạn này.
- Ưu tiên đánh giá Cart durability trước khi quyết định bật PVC hoặc chuyển sang ElastiCache.

**Reason**

- Cart state cần được đánh giá thêm để xác định có yêu cầu persistence hay không.
- Chưa đủ evidence để kết luận cần persistence ngay.
- Giảm migration risk trong giai đoạn hiện tại.

---

## Kafka Recommendation

**Recommended**

- Giữ Kafka hiện tại.
- Đánh giá retention, replay và event durability trước khi quyết định migrate.
- Sau khi hoàn thành cost review sẽ đánh giá phương án Amazon MSK hoặc Kafka StatefulSet nhiều broker.

**Reason**

- Migration Kafka có độ phức tạp cao hơn PostgreSQL.
- Chi phí triển khai và vận hành lớn hơn.
- Cần CDO04 review trước khi quyết định phương án triển khai.

---

# 6. Trade-off Analysis

| Component | Cost | Migration Risk | Data Loss Risk | Rollback Complexity |
|-----------|------|----------------|----------------|---------------------|
| PostgreSQL | Medium/High | Medium | Medium | Medium |
| Valkey | Medium | Medium | High | Medium |
| Kafka | High | High | High | High |

## Summary

### PostgreSQL

- Đã có persistence.
- Chưa có HA.
- Ưu tiên Backup/Restore trước.

### Valkey

- Chưa có persistence.
- Có nguy cơ mất Cart State khi Pod bị recreate.
- ElastiCache là production candidate.

### Kafka

- Single broker.
- Chưa có persistence.
- MSK hoặc multi-broker phù hợp hơn cho production.

---

# 7. Roadmap

## Phase 1 – Current State Assessment

- Verify replica.
- Verify PVC.
- Verify runtime.
- Verify dependent services.

## Phase 2 – Research

- Research persistence options.
- Research HA options.
- Compare StatefulSet và managed service.
- Đánh giá Backup/Restore requirement.

## Phase 3 – Review

- CDO04 review cost.
- Reliability review.
- Hoàn thiện migration plan.
- Hoàn thiện rollback plan.

## Phase 4 – Validation

- Staging validation.
- Failover test.
- Rollback test.

**Không triển khai production trong phạm vi task này.**

---

# 8. Migration Plan

## PostgreSQL

1. Backup PostgreSQL hiện tại.
2. Chuẩn bị môi trường đích (PVC hoặc RDS nếu được approve).
3. Restore dữ liệu vào môi trường mới.
4. Verify schema và dữ liệu sau khi restore.
5. Cập nhật database connection (Secret/Config).
6. Rollout lại Product Catalog, Product Reviews và Accounting.
7. Thực hiện smoke test các luồng đọc/ghi dữ liệu.
8. Thực hiện cutover sau khi staging validation thành công.

---

## Valkey

1. Chuẩn bị môi trường Valkey mới (PVC hoặc ElastiCache nếu được approve).
2. Cập nhật `VALKEY_ADDR`.
3. Rollout lại Cart service.
4. Verify Cart read/write hoạt động bình thường.
5. Theo dõi runtime sau khi cutover.

---

## Kafka

1. Chuẩn bị Kafka cluster mục tiêu (StatefulSet hoặc MSK nếu được approve).
2. Đồng bộ topic và retention policy.
3. Cập nhật `KAFKA_ADDR` cho Producer và Consumer.
4. Rollout Checkout, Accounting và Fraud Detection.
5. Verify producer publish và consumer xử lý event.
6. Smoke test luồng Checkout → Kafka → Accounting/Fraud Detection.
---

# 9. Rollback Plan

## PostgreSQL

- Nếu chưa cutover traffic, có thể revert database connection về môi trường cũ.
- Nếu đã có dữ liệu mới trên môi trường đích, cần đánh giá và reconcile dữ liệu trước khi rollback.
- Restore backup nếu cần.
- Rollout lại các service sử dụng PostgreSQL.
- Verify application sau rollback.

---

## Valkey

- Revert `VALKEY_ADDR`.
- Rollout lại Cart service.
- Chấp nhận Cart State có thể bị mất nếu rollback.
- Verify Cart read/write sau rollback.

---

## Kafka

- Revert `KAFKA_ADDR`.
- Rollout lại Producer và Consumer.
- Kiểm tra event duplicate hoặc event gap trước khi rollback.
- Không rollback nếu Accounting/Fraud Detection đã xử lý một phần event.
- Verify consumer offset sau rollback.
---

# 10. Dependencies

| Item | Purpose |
|------|---------|
| CDO08-REL-11 | Backup/Restore proof cho PostgreSQL, Valkey và Kafka |
| CDO08-REL-07 | Đánh giá Kafka event reliability và publish failure |
| CDO08-SEC-01 | Review Secret/Connection String khi thay đổi endpoint |
| CDO04 | Cost review cho RDS, ElastiCache, MSK và storage |
| Technical Lead (Nguyên) | Review technical risk trước khi triển khai |

---

# 11. Coordination

## CDO04

### Cost Review

Các nội dung cần CDO04 đánh giá:

- RDS Multi-AZ cost
- ElastiCache cost
- Amazon MSK cost
- EBS/PVC storage cost
- Budget impact
- Recommendation phù hợp với ngân sách hiện tại

**Status:** ⏳ Pending CDO04 Review

**Reference:**

`docs/cdo08/week2/review-request/REVIEW-REQUEST-CDO04-COST-REL03.md`

---

## Nguyên (Reliability Review)

Review:

- Migration risk
- Rollback risk
- Data consistency
- Technical approval trước khi implement.
---

# 12. Conclusion

Current runtime verification cho thấy:

- PostgreSQL đã có PVC nhưng vẫn là single replica.
- Valkey và Kafka chưa có persistent storage.
- Cả ba component chưa đạt High Availability.

Đề xuất trước mắt là hoàn thiện backup/restore plan, đánh giá yêu cầu persistence của Valkey và Kafka, sau đó review các phương án managed service hoặc StatefulSet. Không triển khai thay đổi production trước khi có migration plan, rollback plan, staging validation và CDO04 cost review.

## Recommended Next Step

Week 2

- Hoàn thiện Backup/Restore proof.
- Chờ CDO04 cost review.
- Không triển khai Persistence/HA trước khi migration plan được approve.

---
# 13. Definition of Done

Task được xem là hoàn thành khi:

- Có runtime evidence.
- Có chart values evidence.
- Có persistence & HA plan.
- Có trade-off analysis.
- Có migration plan.
- Có rollback plan.
- Có CDO04 cost review request.
- Evidence được attach vào Jira.
- Không triển khai stateful change trước khi được review và approve.