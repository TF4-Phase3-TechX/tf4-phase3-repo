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

**Checked at:** 2026-07-14 Asia/Ho_Chi_Minh  
**Cluster/namespace:** EKS `techx-tf4-cluster`, namespace `techx-tf4`  
**Purpose:** Verify current runtime state. Pod names can change; deployment/PVC names are the durable evidence.

```bash
kubectl get pvc -n techx-tf4
```

```text
NAME             STATUS   VOLUME                                     CAPACITY
postgresql-pvc   Bound    pvc-e0600223-7b8a-4bc6-ab58-bdb77e9653e0   10Gi 
```

## Deployment

```bash
kubectl get deployment,statefulset -n techx-tf4 | grep -E "postgresql|valkey-cart|kafka"
```

```text
deployment.apps/postgresql    1/1
deployment.apps/valkey-cart   1/1
deployment.apps/kafka         1/1
```

## PostgreSQL Runtime

```bash
kubectl describe pod -n techx-tf4 -l opentelemetry.io/name=postgresql
```

Verified:

- Image: postgres:17.6
- Replica: 1
- PVC: postgresql-pvc
- Mount: /var/lib/postgresql/data
- Restart Count: 0

## Valkey Runtime

```bash
kubectl describe pod -n techx-tf4 -l opentelemetry.io/name=valkey-cart
```

Verified:

- Replica: 1
- No PersistentVolumeClaim
- No persistent storage mount

## Kafka Runtime

```bash
kubectl describe pod -n techx-tf4 -l opentelemetry.io/name=kafka
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

### Replica Context

`replicas=1` là runtime state tại thời điểm kiểm tra, nhưng không nên hiểu là quyết định HA dài hạn của CDO08. Trong giai đoạn load-test/mandate hiện tại, một số baseline có thể tạm thời giảm replica để đo cost/performance. Vì vậy:

- Report này vẫn ghi nhận `replicas=1` là **no-HA risk tại runtime hiện tại**.
- Không tự tăng replica/stateful HA trong task này nếu chưa qua review.
- Sau khi mandate/load-test baseline kết thúc, cần revisit HA target cho PostgreSQL, Valkey và Kafka cùng REL-01/REL-02.
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

- **Short-term:** Giữ PostgreSQL hiện tại cùng `postgresql-pvc`, nhưng phải hoàn thiện backup/restore proof và pod recreation test trước khi coi persistence hiện tại là đủ dùng.
- **Week 2 action:** Tạo bằng chứng PostgreSQL có thể restart/recreate pod mà dữ liệu vẫn còn; sau đó chạy restore test từ backup.
- **Long-term candidate:** RDS Multi-AZ là phương án production tốt hơn nếu CDO04 xác nhận chi phí phù hợp và team chấp nhận migration endpoint/secret.

**Reason**

- Đã có persistence thông qua PVC.
- Rủi ro lớn hiện tại không phải mất dữ liệu khi pod restart thường, mà là single replica không có failover và chưa có backup/restore proof.
- Chuyển ngay sang RDS Multi-AZ có thể đúng về production reliability nhưng cần cost review, migration plan, rollback plan và secret/connection-string update.
- Không nên đổi endpoint database khi chưa có restore proof và staging validation.

---

## Valkey Recommendation

**Recommended**

- **Short-term:** Giữ Valkey hiện tại nếu business chấp nhận cart state là ephemeral, nhưng phải ghi rõ đây là accepted risk tạm thời.
- **Decision gate:** Xác nhận với PM/business xem mất cart khi pod/node restart có được chấp nhận không.
- **Nếu cart durability là bắt buộc:** chọn giữa Valkey StatefulSet + PVC hoặc ElastiCache Multi-AZ sau khi CDO04 review cost.

**Reason**

- Valkey hiện không có PVC, nên cart có thể mất khi pod recreate/reschedule.
- Cart loss ảnh hưởng checkout conversion nhưng không nhất thiết là data-of-record như order/payment.
- Vì vậy quyết định đúng phụ thuộc business tolerance: nếu mất cart không chấp nhận được thì phải đưa persistence/managed cache lên priority cao hơn.

---

## Kafka Recommendation

**Recommended**

- **Short-term:** Không tăng HA Kafka vội, nhưng phải xác nhận retention, topic, replay path và event durability gap.
- **Week 2 action:** Phối hợp REL-07 để verify khi Kafka unavailable/slow thì checkout producer và consumer behavior có bằng chứng rõ.
- **Long-term candidate:** Amazon MSK hoặc Kafka StatefulSet multi-broker + PVC, chỉ chọn sau cost review và technical review.

**Reason**

- Migration Kafka có độ phức tạp cao hơn PostgreSQL.
- Chi phí triển khai và vận hành lớn hơn.
- Kafka đang single broker/controller và không có PVC, nên broker restart/node failure có rủi ro mất event hoặc gián đoạn async processing.
- Nếu chọn sai phương án migration, rủi ro duplicate event, event gap và consumer offset inconsistency cao hơn lợi ích short-term.
- Cần CDO04 review trước khi quyết định phương án triển khai production.

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

- PostgreSQL: compare current PVC + backup/restore proof vs RDS Multi-AZ.
- Valkey: decide whether cart durability is business-required; compare ephemeral accepted risk vs PVC/ElastiCache.
- Kafka: compare short-term retention/replay proof vs StatefulSet multi-broker/MSK.
- Estimate migration risk, data-loss risk and rollback boundary for each option.

## Phase 3 – Review

- CDO04 review cost.
- Reliability review.
- Nguyên review migration/rollback risk.
- PM/business confirm Valkey cart durability tolerance.

## Phase 4 – Validation

- PostgreSQL backup/restore proof and pod recreation test.
- Valkey cart read/write smoke test against chosen target.
- Kafka producer/consumer event-flow test and offset/duplicate behavior.

**Không triển khai production trong phạm vi task này.**

---

# 8. Migration Plan

## PostgreSQL

### Pre-check

1. Xác nhận `postgresql-pvc` đang `Bound`.
2. Xác nhận backup hiện tại tồn tại và restore được trên môi trường test/staging.
3. Xác nhận connection secret/config đã sẵn sàng nếu endpoint thay đổi.
4. Xác nhận Product Catalog, Product Reviews và Accounting có smoke test đọc/ghi database.

### Migration steps

1. Backup PostgreSQL hiện tại.
2. Chuẩn bị môi trường đích (PVC hoặc RDS nếu được approve).
3. Restore dữ liệu vào môi trường mới.
4. Verify schema và dữ liệu sau khi restore.
5. Cập nhật database connection (Secret/Config).
6. Rollout lại Product Catalog, Product Reviews và Accounting.
7. Thực hiện smoke test các luồng đọc/ghi dữ liệu.
8. Thực hiện cutover sau khi staging validation thành công.

### Cutover acceptance

- PostgreSQL target healthy.
- Schema/data count khớp với source theo checklist đã thống nhất.
- Product Catalog, Product Reviews và Accounting rollout thành công.
- Smoke test app pass và không có database connection error trong log.

### Rollback boundary

- Rollback an toàn trước khi có write mới trên target.
- Nếu đã có write mới trên target, phải reconcile dữ liệu trước khi rollback về source cũ.

---

## Valkey

### Pre-check

1. Xác nhận business có chấp nhận mất cart state khi pod/node restart hay không.
2. Nếu không chấp nhận, chọn target: Valkey StatefulSet + PVC hoặc ElastiCache.
3. Xác nhận Cart service có smoke test add/view cart.
4. Xác nhận `VALKEY_ADDR` có thể đổi qua secret/config mà không hardcode.

### Migration steps

1. Chuẩn bị môi trường Valkey mới (PVC hoặc ElastiCache nếu được approve).
2. Cập nhật `VALKEY_ADDR`.
3. Rollout lại Cart service.
4. Verify Cart read/write hoạt động bình thường.
5. Theo dõi runtime sau khi cutover.

### Cutover acceptance

- Cart service kết nối target Valkey thành công.
- Add product to cart và view cart pass.
- Checkout dùng cart hiện tại pass.

### Rollback boundary

- Rollback được bằng cách revert `VALKEY_ADDR`.
- Cart state trong target mới có thể bị mất khi rollback; nếu cần giữ cart, phải có export/import hoặc chấp nhận data loss rõ ràng.

---

## Kafka

### Pre-check

1. Xác nhận topic/consumer/producer hiện tại.
2. Xác nhận retention policy mong muốn.
3. Xác nhận producer behavior từ REL-07 khi Kafka unavailable/slow.
4. Xác nhận consumer offset strategy và duplicate-event tolerance của Accounting/Fraud Detection.

### Migration steps

1. Chuẩn bị Kafka cluster mục tiêu (StatefulSet hoặc MSK nếu được approve).
2. Đồng bộ topic và retention policy.
3. Cập nhật `KAFKA_ADDR` cho Producer và Consumer.
4. Rollout Checkout, Accounting và Fraud Detection.
5. Verify producer publish và consumer xử lý event.
6. Smoke test luồng Checkout → Kafka → Accounting/Fraud Detection.

### Cutover acceptance

- Producer publish thành công.
- Accounting và Fraud Detection consume event đúng.
- Không có event gap hoặc duplicate không xử lý được trong test window.
- Consumer offset behavior được ghi lại.

### Rollback boundary

- Rollback an toàn nếu chưa có event mới quan trọng trên target.
- Nếu target đã nhận event và consumer đã xử lý một phần, rollback phải có event reconciliation plan; không rollback mù.
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

- PostgreSQL: hoàn thiện backup/restore proof và pod recreation test với `postgresql-pvc`.
- Valkey: PM/business xác nhận cart state có được phép ephemeral không. Nếu không, chọn PVC hoặc ElastiCache candidate sau CDO04 review.
- Kafka: phối hợp REL-07 để xác nhận event durability, retention/replay và producer/consumer behavior khi Kafka lỗi.
- CDO04: trả lời cost review theo `docs/cdo08/week2/review-request/REVIEW-REQUEST-CDO04-COST-REL03.md`.
- Không triển khai stateful HA/managed service trước khi migration/rollback plan được approve.

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
