# ADR-004: In-Cluster Data Stores cho Week 1 Baseline (PostgreSQL, Kafka, Valkey)

**Ngày:** 2026-07-08
**Trạng thái:** Accepted — cần review Week 2
**Người quyết định:** CDO-04 (Infrastructure), CDO-08 (Reliability)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Reliability, Cost Optimization, Auditability
**Evidence:** `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`

---

## 1. Bối cảnh (Context)

Hệ thống TechX cần 3 data stores:

| Store | Dùng bởi | Vai trò |
|---|---|---|
| **PostgreSQL** | product-catalog, product-reviews, accounting | DB quan hệ chính |
| **Valkey** | cart | Key-value store cho giỏ hàng |
| **Kafka** | checkout → accounting, fraud-detection | Message queue cho đơn hàng |

Có hai lựa chọn triển khai:
- **Option A (đã chọn):** Chạy in-cluster như Kubernetes Deployment (Pod).
- **Option B:** Dùng AWS Managed Services (RDS, ElastiCache, MSK).

---

## 2. Quyết định (Decision)

**TF4 Week 1 chạy cả 3 data stores as in-cluster Deployments** — không có PVC, không có StatefulSet, không replication.

**Kết quả verify thực tế (2026-07-08):**
```
kubectl -n techx-tf4 get pvc → No resources found in techx-tf4 namespace.
```

- `postgresql` — Deployment, không có PVC.
- `valkey-cart` — Deployment, không có PVC.
- `kafka` — Deployment, KRaft quorum 1, không có PVC.

---

## 3. Lý do (Rationale)

| Lý do | Giải thích |
|---|---|
| Cost control | RDS (~$50-100/tuần) + ElastiCache (~$30/tuần) + MSK (~$50+/tuần) có thể vượt budget $300/tuần chỉ riêng data layer |
| Week 1 scope | Mục tiêu Week 1 là baseline deployment, không phải production-grade reliability |
| Speed of deployment | In-cluster đơn giản hơn, không cần cấu hình VPC endpoint, security group riêng cho managed services |
| Migrate sau khi có evidence | Quyết định managed vs in-cluster nên dựa trên runtime data, không phải giả định |

---

## 4. Rủi ro đã ghi nhận (Known Risks)

> ⚠️ **Đây là rủi ro CRITICAL đã được xác nhận.**

| Risk ID | Risk | Impact | Likelihood |
|---|---|---|---|
| K8S-04 | Pod restart / node drain → **mất toàn bộ data** | Critical | High |
| Accounting data loss | Nếu PostgreSQL pod restart, accounting records bị mất → không có audit trail | Critical | High |
| Cart loss | Valkey restart → mất giỏ hàng đang active (lặp lại INC-2) | High | High |
| Kafka offset loss | Kafka restart → mất uncommitted offsets → duplicate hoặc mất event | Critical | High |

**Với CDO-07 (Audit):** Rủi ro nghiêm trọng nhất là mất accounting records. Nếu PostgreSQL pod bị restart, không có cách nào recovery lại dữ liệu đơn hàng đã ghi. Điều này trực tiếp vi phạm audit trail integrity.

---

## 5. Điều kiện chấp nhận rủi ro (Risk Acceptance)

Team chấp nhận rủi ro này với điều kiện:

1. Hệ thống không được claim production-grade data durability trong Week 1.
2. Week 2 phải có kế hoạch rõ ràng: migrate sang managed service HOẶC thêm PVC/StatefulSet.
3. Mọi sự cố mất data phải được ghi nhận trong postmortem.

---

## 6. Plan cho Week 2 (Migration Path)

| Option | Chi phí ước tính | Complexity | Khi nào phù hợp |
|---|---|---|---|
| PVC + StatefulSet in-cluster | Thêm ~$8-16/tuần EBS | Medium | Nếu budget < $150/tuần còn lại |
| RDS PostgreSQL (Single-AZ) | ~$25-50/tuần | Medium | Nếu cần SQL reliability |
| ElastiCache (Valkey/Redis) | ~$20-30/tuần | Low | Nếu cart loss SLO bị vi phạm |
| MSK (Managed Kafka) | ~$50-100/tuần | High | Nếu event integrity là blocker |

**CDO-07 cần track:**
- [ ] CDO-04/08 phải quyết định migration path trước cuối Week 1 Pitch.
- [ ] Ghi ADR mới khi quyết định migrate.
- [ ] Verify data durability sau khi migrate.

---

## 7. Tham chiếu (References)

- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md` — PVC count = 0, cost impact
- `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` — K8S-04 (Critical)
- `docs/requirements/onboarding/INCIDENT_HISTORY.md` — INC-2: Cart loss incident
- `docs/epic-01-addressing-system-gap/GAP-TO-PILLAR-MAPPING.md` — K8S-04 owner: CDO-08
