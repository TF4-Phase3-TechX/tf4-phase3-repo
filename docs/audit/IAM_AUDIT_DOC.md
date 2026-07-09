# IAM Audit Report

## 1. Danh sách IAM Policies / Roles hiện hành

### 1.1. Các Custom Policies (AWS Local Scope)
Hệ thống hiện có 12 custom policies:
- `tf4-github-actions-eks-deploy`
- `techx-tf4-cluster-cluster-ClusterEncryption...`
- `tf4-github-actions-plan`
- `AWSLoadBalancerControllerIAMPolicy`
- `cdo04-tin-test-policy`
- `techx-tf4-cluster-cluster-...`
- `cdo04-infra-iam-admin`
- `cdo04-terraform-state-access`
- `tf4-github-actions-ecr-build`
- `cdo04-budgets-full-access`
- `tf4-cdo04-github-deploy-policy`
- `cdo04-self-manage-credentials`

### 1.2. IAM Roles/Permission Sets (Các nhóm CDO & AI)
Đối chiếu tài liệu trong `docs/iam/group` và thực tế Access Analyzer, các nhóm đã định nghĩa các SSO Roles (Permission Sets) sau:
- **Team CDO08 (Security & Reliability)**: `TF4-BaseReadOnly` và `TF4-SecReliabilityReadOnlyAudit`
- **Team CDO07 (Audit & Verify)**: `TF4-AuditReadOnlyAndAnalyze`
- **Team CDO04 (Cost & Performance)**: `TF4-CostPerfReadOnlyAlerting`
- **Team AIO01 (AI Operations)**: `TF4-AIReadOnlyOrLimitedInvoke`

*(Tất cả các roles trên đều đang active trên AWS dưới dạng AWSReservedSSO_... qua SAML Federation)*

## 2. Phân tích báo cáo IAM Access Analyzer
- Đang bật 1 Analyzer: `tf4-iam-analyzer` (us-east-1).

- Kết quả: **9 findings** (Liên quan đến External Access via OIDC & SAML).

## 3. Danh sách tài khoản/policy vi phạm (Over-privileged)
- Theo Access Analyzer: Các role GitHub Actions và AWS SSO đang cho phép Federated Access. Đây là by-design nhưng cần review định kỳ.
- Nhận định nhanh: Các policy mang tên `cdo04-infra-iam-admin` và `cdo04-budgets-full-access` có rủi ro thừa quyền cao, cần CDO08 review lại.

## 4. Evidence (Đính kèm Jira)
- **Danh sách Policy hiện hành**: [iam_policies.json](evidence/epic-06/iam_policies.json).
- **Báo cáo rủi ro Access Analyzer**: [findings.json](evidence/epic-06/findings.json) (Chi tiết 9 external access findings).
- **File Evidence Ticket Jira**: [001-iam-audit-task-1.md](evidence/epic-06/001-iam-audit-task-1.md)
*(Các file JSON evidence này đã được dời vào thư mục `evidence/epic-06/`)*
