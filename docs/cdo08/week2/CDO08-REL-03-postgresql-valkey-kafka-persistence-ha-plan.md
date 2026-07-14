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

- PostgreSQL đã sử dụng PVC (`postgresql-pvc`) nhưng vẫn chỉ có 1 replica.
- Valkey chưa có persistent storage.
- Kafka chưa có persistent storage.
- Cả ba component đều chưa có High Availability.

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

# 4. Persistence & HA Options

| Component | Current | Short-term | Long-term |
|-----------|---------|------------|-----------|
| PostgreSQL | Deployment + PVC | Backup/Restore | RDS Multi-AZ hoặc StatefulSet + Operator |
| Valkey | Deployment | PVC (nếu cần) | ElastiCache Multi-AZ |
| Kafka | Deployment | Review retention/replay | MSK hoặc StatefulSet Multi-Broker |

---

# 5. Trade-off Analysis

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

# 6. Roadmap

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

# 7. Migration Plan

## PostgreSQL

- Backup.
- Deploy target.
- Restore.
- Update connection.
- Verify.

## Valkey

- Deploy target.
- Update VALKEY_ADDR.
- Restart Cart.
- Verify.

## Kafka

- Deploy cluster mới.
- Chuyển producer.
- Chuyển consumer.
- Verify topic và offset.

---

# 8. Rollback Plan

## PostgreSQL

- Restore backup.
- Revert connection string.
- Restart services.

## Valkey

- Revert VALKEY_ADDR.
- Restart Cart.
- Verify Cart.

## Kafka

- Revert KAFKA_ADDR.
- Restart producer/consumer.
- Verify topic và consumer offsets.

---

# 9. Coordination

# 9. Coordination

## CDO04

Review

- RDS cost
- ElastiCache cost
- MSK cost
- Storage cost
- Managed service cost

---

## Nguyên (Reliability Review)

Review

- Migration risk
- Rollback risk
- Data consistency
- Technical approval trước khi implement.

---

# 10. Conclusion

Current runtime verification cho thấy:

- PostgreSQL đã có PVC nhưng vẫn là single replica.
- Valkey và Kafka chưa có persistent storage.
- Cả ba component chưa đạt High Availability.

Đề xuất trước mắt là hoàn thiện backup/restore plan, đánh giá yêu cầu persistence của Valkey và Kafka, sau đó review các phương án managed service hoặc StatefulSet. Không triển khai thay đổi production trước khi có migration plan, rollback plan, staging validation và CDO04 cost review.


# 11. Definition of Done

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