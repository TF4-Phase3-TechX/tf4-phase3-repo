# ADR-003: GitHub Actions Deploy Role dùng Cluster-Admin (Bootstrap Temporary Access)

**Ngày:** 2026-07-08
**Trạng thái:** Accepted — cần review khi baseline ổn định
**Người quyết định:** CDO-04 (Infrastructure Owner: Huy Hoàng)
**Người review:** CDO-07 (Audit), CDO-08 (Security)
**Pillar liên quan:** Security, Auditability
**Terraform file:** `infra/terraform/eks-access-entries.tf`

---

## 1. Bối cảnh (Context)

TF4 cần một role để CI/CD (GitHub Actions) có thể deploy Helm chart lên EKS cluster `techx-tf4-cluster`. Để deploy ban đầu hoạt động, role này cần đủ quyền tạo/update tất cả resource trong cluster.

Có hai hướng tiếp cận:
- **Option A (đã chọn):** Cấp `AmazonEKSClusterAdminPolicy` (cluster-admin) — đơn giản, chắc chắn hoạt động.
- **Option B:** Cấp namespace-scoped RBAC giới hạn trong `techx-tf4` và `techx-observability`.

---

## 2. Quyết định (Decision)

**Tạm thời cấp cluster-admin cho GitHub Actions role để CI/CD path hoạt động trong giai đoạn bootstrap.**

Được implement trong `infra/terraform/eks-access-entries.tf`:

```hcl
resource "aws_eks_access_policy_association" "github_actions_deploy_admin" {
  cluster_name  = module.eks.cluster_name
  principal_arn = "arn:aws:iam::511825856493:role/tf4-github-actions-eks-deploy"
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"

  access_scope {
    type = "cluster"   # cluster-wide admin
  }
}
```

**IAM Role ARN:** `arn:aws:iam::511825856493:role/tf4-github-actions-eks-deploy`

---

## 3. Lý do (Rationale)

| Lý do | Giải thích |
|---|---|
| Bootstrap simplicity | Tuần 1 cần deploy nhanh để có baseline — không thể bị block bởi RBAC config sai |
| Helm chart scope rộng | Chart deploy nhiều namespace và resource type — khó enumerate đủ permissions ngay từ đầu |
| Temporary by design | Comment trong Terraform ghi rõ: "Upgrade path: namespace-scoped RBAC after first deploy works" |
| Prove CI path first | Ưu tiên chứng minh CI/CD pipeline hoạt động, sau đó mới tighten permissions |

---

## 4. Rủi ro đã ghi nhận (Known Risks)

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| GitHub Actions secret leak → cluster full compromise | Critical | Low | Rotate secret ngay nếu có breach; audit GitHub Actions logs |
| Over-privileged CI role violates least privilege | High | Confirmed | Scope down sau Week 1 (xem Plan below) |
| Không có audit trail cho kubectl actions từ CI | Medium | Confirmed | EKS audit logs đã bật: `cluster_enabled_log_types = ["api","audit","authenticator"]` |

---

## 5. Plan để downscope (Upgrade Path)

Theo comment trong `eks-access-entries.tf`, CDO-04 đã ghi nhận kế hoạch upgrade:

```
Upgrade path: namespace-scoped RBAC for techx-tf4 and techx-observability
              after first deploy works.
```

**CDO-07 (Audit) cần track:**
- [ ] Tạo Jira task để CDO-04 implement namespace-scoped RBAC sau Week 1.
- [ ] Verify EKS audit logs có ghi lại actions từ role `tf4-github-actions-eks-deploy`.
- [ ] Set deadline cho việc downscope (đề xuất: cuối Week 2).

---

## 6. Audit Trail

Mọi hành động của GitHub Actions role đều được ghi lại trong:

```
AWS CloudWatch Log Group: /aws/eks/techx-tf4-cluster/cluster
Log Stream: kube-apiserver-audit-*
Filter: userAgent contains "kubectl" OR user.username = "arn:aws:iam::511825856493:role/tf4-github-actions-eks-deploy"
```

---

## 7. Tham chiếu (References)

- `infra/terraform/eks-access-entries.tf` — Terraform config thực tế
- `infra/terraform/eks.tf` — `cluster_enabled_log_types = ["api", "audit", "authenticator"]`
- `docs/audit/AUDIT_CHECKLIST.md` — Mục 4: Control Plane Audit (EKS)
- ADR-001 — Separation of Duties (CDO-07 verify, không tự sửa)
