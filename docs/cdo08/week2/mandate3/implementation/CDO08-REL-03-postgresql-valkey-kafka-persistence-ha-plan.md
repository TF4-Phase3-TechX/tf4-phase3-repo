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
- Valkey đã được đề xuất bật PVC trong PR này, nhưng chưa có High Availability.
- Kafka đã được đề xuất bật PVC trong PR này, nhưng chưa có High Availability.

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
| **Valkey** | PR này bật `valkey-cart-pvc` và append-only persistence. Trước khi PR deploy, runtime chưa có PVC. Sau deploy, pod recreate/reschedule sẽ mount lại PVC nhưng vẫn không có failover. | Medium |
| **Kafka** | PR này bật `kafka-pvc` cho broker log dir. Trước khi PR deploy, runtime chưa có PVC. Sau deploy, pod recreate/reschedule sẽ mount lại PVC nhưng vẫn chỉ có 1 broker/controller. | Medium/High |

### Summary

- PostgreSQL đã có persistence thông qua PVC nhưng vẫn là **Single Point of Failure (SPOF)** do chỉ có một replica.
- Valkey được giảm data-loss risk bằng PVC + append-only persistence trong PR này, nhưng vẫn chưa có HA/failover.
- Kafka được giảm data-loss risk bằng PVC cho broker log dir trong PR này, nhưng vẫn chưa có HA/failover và vẫn cần REL-07 verify producer/consumer behavior.

### Replica Context

`replicas=1` là runtime state tại thời điểm kiểm tra, nhưng không nên hiểu là quyết định HA dài hạn của CDO08. Trong giai đoạn load-test/mandate hiện tại, một số baseline có thể tạm thời giảm replica để đo cost/performance. Vì vậy:

- Report này vẫn ghi nhận `replicas=1` là **no-HA risk tại runtime hiện tại**.
- Không tự tăng replica/stateful HA trong task này nếu chưa qua review.
- Sau khi mandate/load-test baseline kết thúc, cần revisit HA target cho PostgreSQL, Valkey và Kafka cùng REL-01/REL-02.
---

# 4. Chart Values Evidence

## Implementation Scope

Trong PR này CDO08 chọn **incremental persistence** cho stateful runtime hiện tại:

- Giữ `postgresql` với PVC hiện có.
- Bật PVC `gp3` cho `valkey-cart` để giảm rủi ro mất cart khi pod recreate/reschedule.
- Bật PVC `gp3` cho `kafka` để giữ broker log/event data qua pod recreate/reschedule.
- Không đổi `postgresql-pvc` hiện có từ `gp2` sang `gp3` trong PR này vì `storageClassName` của PVC đã tạo là immutable; cần migration riêng nếu muốn đổi.
- Giữ cả ba workload ở `replicas: 1`. Đây **chưa phải HA multi-replica** và không thay thế RDS/ElastiCache/MSK.
- Dùng `strategy: Recreate` cho Valkey/Kafka vì PVC hiện là `ReadWriteOnce`; không cho phép hai pod cùng mount volume trong rolling update.

Mục tiêu của PR là giảm data-loss risk trước, không triển khai full HA/failover.

## PostgreSQL

**Source**

`techx-corp-chart/templates/component-pvcs.yaml`

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
- `persistence.enabled: true`
- Chart tạo `valkey-cart-pvc` với `storageClassName: gp3`, `size: 5Gi`
- Mount PVC vào `/data`
- Chạy `valkey-server --appendonly yes --dir /data`
- `strategy: Recreate` để tránh RWO PVC mount conflict trong rollout.

---

## Kafka

**Source**

`techx-corp-chart/values.yaml`

Verified:

- `replicas: 1`
- `persistence.enabled: true`
- Chart tạo `kafka-pvc` với `storageClassName: gp3`, `size: 10Gi`
- Set `KAFKA_LOG_DIRS=/tmp/kraft-combined-logs`
- Mount PVC vào `/tmp/kraft-combined-logs`
- `strategy: Recreate` để tránh RWO PVC mount conflict trong rollout.

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
- **Long-term candidate:** RDS Multi-AZ là phương án dự phòng nếu sau này cần managed DB failover/backup hoàn chỉnh. Không triển khai trong phase này.

**Reason**

- Đã có persistence thông qua PVC.
- Rủi ro lớn hiện tại không phải mất dữ liệu khi pod restart thường, mà là single replica không có failover và chưa có backup/restore proof.
- Chuyển ngay sang RDS Multi-AZ có thể đúng về production reliability nhưng cần cost review, migration plan, rollback plan và secret/connection-string update.
- Không nên đổi endpoint database khi chưa có restore proof và staging validation.

---

## Valkey Recommendation

**Recommended**

- **Short-term:** Bật PVC + append-only persistence cho Valkey hiện tại để không còn phụ thuộc hoàn toàn vào memory state.
- **Decision gate còn lại:** Sau khi deploy, verify cart còn sau pod recreation. Không triển khai Valkey Sentinel/operator hoặc ElastiCache Multi-AZ trong phase này theo feedback CDO04.
- **Rejected options:** Valkey Sentinel/operator và ElastiCache Multi-AZ bị reject cho phase này vì operational risk/cost không phù hợp với giá trị cart state.

**Reason**

- Valkey runtime trước PR không có PVC, nên cart có thể mất khi pod recreate/reschedule.
- Cart loss ảnh hưởng checkout conversion nhưng không nhất thiết là data-of-record như order/payment.
- PM không chấp nhận mất cart trong normal restart/reschedule, nên PR này chọn incremental PVC trước khi cân nhắc managed cache.

---

## Kafka Recommendation

**Recommended**

- **Short-term:** Bật PVC cho Kafka broker log dir, không tăng HA Kafka vội, và phải xác nhận retention, topic, replay path và event durability gap.
- **Week 2 action:** Phối hợp REL-07 để verify khi Kafka unavailable/slow thì checkout producer và consumer behavior có bằng chứng rõ.
- **Long-term candidate:** Amazon MSK chỉ là phương án dự phòng nếu business bắt buộc HA Kafka. Không triển khai Kafka StatefulSet multi-broker trong phase này.

**Reason**

- Migration Kafka có độ phức tạp cao hơn PostgreSQL.
- Chi phí triển khai và vận hành lớn hơn.
- Kafka runtime trước PR là single broker/controller và không có PVC, nên broker restart/node failure có rủi ro mất event hoặc gián đoạn async processing.
- PVC giảm rủi ro mất broker log khi pod recreate/reschedule, nhưng không xử lý được node/AZ/storage failure hoặc broker failover.
- Nếu chọn sai phương án migration, rủi ro duplicate event, event gap và consumer offset inconsistency cao hơn lợi ích short-term.
- CDO04 reject Kafka StatefulSet multi-broker vì 3 broker JVM có thể gây node pressure và chi phí ẩn do phải scale thêm node.
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

1. PM xác nhận không chấp nhận mất cart trong normal pod restart/reschedule.
2. Target được chọn trong PR này: Valkey hiện tại + PVC + append-only persistence.
3. Xác nhận Cart service có smoke test add/view cart.
4. Xác nhận `VALKEY_ADDR` không đổi (`valkey-cart:6379`) để tránh cutover endpoint.

### Migration steps

1. Render chart tạo `valkey-cart-pvc`.
2. Mount `valkey-cart-pvc` vào `/data`.
3. Chạy `valkey-server --appendonly yes --dir /data`.
4. Deploy bằng Helm; `strategy: Recreate` sẽ recreate Valkey pod.
5. Verify Cart read/write hoạt động bình thường.
6. Recreate Valkey pod và verify cart state vẫn còn nếu test data/TTL cho phép.

### Cutover acceptance

- Cart service kết nối target Valkey thành công.
- Add product to cart và view cart pass.
- Checkout dùng cart hiện tại pass.
- `kubectl -n techx-tf4 get pvc valkey-cart-pvc` trả `Bound`.
- Valkey pod Running sau recreate.

### Rollback boundary

- Rollback bằng Helm rollback/revert chart về cấu hình không mount PVC.
- Dữ liệu cart đã ghi vào AOF trên PVC có thể không được đọc nếu rollback về ephemeral mode; chỉ rollback khi chấp nhận cart state loss hoặc đã export/import.

---

## Kafka

### Pre-check

1. Xác nhận topic/consumer/producer hiện tại.
2. Xác nhận retention policy mong muốn.
3. Xác nhận producer behavior từ REL-07 khi Kafka unavailable/slow.
4. Xác nhận consumer offset strategy và duplicate-event tolerance của Accounting/Fraud Detection.
5. Target được chọn trong PR này: single-broker Kafka hiện tại + PVC cho broker log dir, chưa bật multi-broker.

### Migration steps

1. Render chart tạo `kafka-pvc`.
2. Set `KAFKA_LOG_DIRS=/tmp/kraft-combined-logs`.
3. Mount `kafka-pvc` vào `/tmp/kraft-combined-logs`.
4. Deploy bằng Helm; `strategy: Recreate` sẽ recreate Kafka pod.
5. Không đổi `KAFKA_ADDR`; producer/consumer vẫn dùng `kafka:9092`.
6. Verify producer publish và consumer xử lý event.
7. Recreate Kafka pod và verify broker lên lại với cùng PVC.

### Cutover acceptance

- Producer publish thành công.
- Accounting và Fraud Detection consume event đúng.
- Không có event gap hoặc duplicate không xử lý được trong test window.
- Consumer offset behavior được ghi lại.
- `kubectl -n techx-tf4 get pvc kafka-pvc` trả `Bound`.
- Kafka pod Running sau recreate.

### Rollback boundary

- Rollback bằng Helm rollback/revert chart về cấu hình không mount PVC.
- Nếu Kafka đã nhận event sau deploy, rollback có thể làm mất broker log mới nếu quay về ephemeral mode; cần reconciliation với Accounting/Fraud Detection trước khi rollback.
---

# 8.1 Implementation Verification Commands

```bash
helm template techx-corp ./techx-corp-chart -n techx-tf4 \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  > /tmp/rel03-rendered.yaml

grep -n "name: kafka-pvc\\|name: valkey-cart-pvc\\|KAFKA_LOG_DIRS\\|mountPath: /data\\|mountPath: /tmp/kraft-combined-logs" /tmp/rel03-rendered.yaml
```

Sau deploy:

```bash
kubectl -n techx-tf4 get pvc postgresql-pvc valkey-cart-pvc kafka-pvc
kubectl -n techx-tf4 rollout status deploy/valkey-cart --timeout=180s
kubectl -n techx-tf4 rollout status deploy/kafka --timeout=180s
kubectl -n techx-tf4 get pods -l opentelemetry.io/name=valkey-cart
kubectl -n techx-tf4 get pods -l opentelemetry.io/name=kafka
```

Persistence smoke:

```bash
# Valkey: add/view cart qua app smoke test trước và sau khi recreate pod.
kubectl -n techx-tf4 delete pod -l opentelemetry.io/name=valkey-cart
kubectl -n techx-tf4 rollout status deploy/valkey-cart --timeout=180s

# Kafka: verify checkout publish và consumer logs trước và sau khi recreate pod.
kubectl -n techx-tf4 delete pod -l opentelemetry.io/name=kafka
kubectl -n techx-tf4 rollout status deploy/kafka --timeout=180s
```

> Không dùng `kubectl exec` làm default evidence nếu reviewer chỉ có CDO08 read-only. Nếu cần inspect file trong mounted volume, nhờ Deploy Operator/Admin chạy và attach evidence.

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
- Valkey và Kafka trước PR chưa có persistent storage; PR này bổ sung PVC cho cả hai.
- Cả ba component vẫn chưa đạt High Availability vì vẫn single replica/single broker.

Đề xuất trước mắt là triển khai incremental persistence bằng PVC cho Valkey/Kafka, sau đó hoàn thiện backup/restore proof và đánh giá HA/managed service ở bước riêng. Không triển khai full HA hoặc managed service trước khi có migration plan, rollback plan, staging validation và CDO04 cost review.

## Recommended Next Step

Week 2

- PostgreSQL: hoàn thiện backup/restore proof và pod recreation test với `postgresql-pvc`.
- Valkey: deploy `valkey-cart-pvc`, verify cart state sau pod recreation, sau đó mới đánh giá ElastiCache/HA nếu cần no-downtime.
- Kafka: deploy `kafka-pvc`, phối hợp REL-07 để xác nhận event durability, retention/replay và producer/consumer behavior khi Kafka lỗi.
- CDO04: đã approve PVC mới với điều kiện dùng `gp3`; xem `docs/cdo08/week2/review-request/REVIEW-REQUEST-CDO04-COST-REL03-PVC.md`.
- HA/managed service: defer theo decision trong `docs/cdo08/week2/review-request/REVIEW-REQUEST-CDO04-COST-REL03-HA-OPTIONS.md`.
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
- Helm render/lint pass.
- `valkey-cart-pvc` và `kafka-pvc` render đúng.
- Evidence được attach vào Jira.
- Không triển khai stateful change trước khi được review và approve.
---
## 🛡️ CDO-07 Audit Approval Sign-Off
- **Trạng thái:** ✅ APPROVED / PASS
- **Người kiểm duyệt:** CDO-07 (Đội ngũ Auditability)
- **Ngày thực hiện:** 2026-07-16
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.

