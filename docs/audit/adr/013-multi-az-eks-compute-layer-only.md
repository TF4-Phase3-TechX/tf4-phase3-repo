# ADR-013: Multi-AZ Chỉ Áp Dụng cho EKS Compute Layer

**Ngày:** 2026-07-09
**Trạng thái:** Accepted
**Người quyết định:** CDO-04 (Infrastructure)
**Người review:** CDO-07 (Audit), CDO-08 (Reliability)
**Pillar liên quan:** Reliability, Auditability
**Source:** `infra/terraform/vpc.tf`, `infra/terraform/eks.tf`
**Refs:** `docs/evidence/epic-02-baseline-architecture/04-architecture-assumptions.md` (Assumption 1), ARCH-RISK-01

---

## 1. Bối cảnh (Context)

TF4 triển khai EKS trên 2 Availability Zones. Điều này có thể bị hiểu nhầm là hệ thống đã có **full High Availability**. ADR này ghi nhận rõ phạm vi thực tế của Multi-AZ trong Week 1.

---

## 2. Quyết định (Decision)

**Multi-AZ trong TF4 Week 1 CHỈ áp dụng cho EKS compute layer.**

Được implement trong `infra/terraform/eks.tf` và `vpc.tf`:

```hcl
# vpc.tf — 2 AZ
azs = ["us-east-1a", "us-east-1b"]
private_subnets = [...]   # Private subnet mỗi AZ
public_subnets  = [...]   # Public subnet mỗi AZ

# eks.tf — Worker nodes across 2 AZ
eks_managed_node_groups = {
  general = {
    min_size     = 2   # 1 node mỗi AZ
    desired_size = 2
  }
}
```

**Runtime đã xác nhận:**
- Worker Node 1: `i-0991279b4d3194388` / `us-east-1a`
- Worker Node 2: `i-0a80b6979ff759588` / `us-east-1b`

---

## 3. Phạm vi Multi-AZ (Scope)

| Layer | Multi-AZ? | Ghi chú |
|---|---|---|
| EKS Worker Nodes | ✅ Yes | 2 nodes across 2 AZ |
| Application pods (stateless) | ⚠️ Depends | Scheduler có thể spread, nhưng không đảm bảo |
| PostgreSQL | ❌ No | Single Deployment, 1 replica, no PVC |
| Kafka | ❌ No | Single Deployment, KRaft quorum 1 |
| Valkey (cart) | ❌ No | Single Deployment, no persistence |
| NAT Gateway | ❌ No | Single NAT — ADR-002 |
| ALB | ✅ Yes | AWS managed, multi-AZ tự động |
| Observability stack | ❌ No | Single replica mỗi component |

---

## 4. Lý do chỉ claim compute layer (Rationale)

| Lý do | Giải thích |
|---|---|
| Cost control | Multi-AZ cho stateful services (~$100-200/tuần thêm) vượt budget $300/tuần |
| Week 1 scope | Mục tiêu là baseline deployment, không production-grade HA |
| Data store complexity | PostgreSQL/Kafka Multi-AZ cần leader election, replication, backup — scope lớn |
| Single NAT | Network path không full HA dù compute có 2 AZ |

---

## 5. Câu mô tả chuẩn cho Pitch

> *"TF4 Week 1 triển khai 2 EKS worker nodes trên 2 Availability Zones để tăng compute-layer resilience. Tuy nhiên, stateful workloads (PostgreSQL, Kafka, Valkey) chưa có replication hay persistence — chưa được claim là full HA. Network path dùng Single NAT Gateway theo ADR-002."*

---

## 6. Rủi ro (Known Risks)

| Risk | ARCH-RISK # | Mitigation |
|---|---|---|
| Stakeholder hiểu nhầm Multi-AZ = full HA | ARCH-RISK-01 | Ghi rõ trong ADR, diagram notes, pitch |
| Stateful workload restart mất data | ARCH-RISK-02 | ADR-004 — plan migrate Week 2 |
| Single NAT gateway là network SPOF | ARCH-RISK-03 | ADR-002 — deferred hardening |

---

## 7. Tham chiếu (References)

- `infra/terraform/eks.tf` — node group config
- `infra/terraform/vpc.tf` — AZ và subnet config
- `docs/evidence/epic-02-baseline-architecture/01-aws-high-level-architecture.md` — diagram
- `docs/evidence/epic-02-baseline-architecture/04-architecture-assumptions.md` — Assumption 1
- `docs/evidence/epic-02-baseline-architecture/05-architecture-risk-register.md` — ARCH-RISK-01, 02
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md` — Worker node AZ evidence
- ADR-004 — In-cluster data stores (liên quan trực tiếp)
