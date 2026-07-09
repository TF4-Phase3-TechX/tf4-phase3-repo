# Evidence Task 1: Kiểm tra quyền IAM & Access Analyzer

## 1. Mục tiêu
Phát hiện user/role dư thừa quyền (over-privileged) dựa trên báo cáo Access Analyzer.

## 2. Kết quả & Dữ liệu chứng minh (Evidence)
- **Danh sách policy hiện hành từ AWS IAM**: Đã xuất thành công. 
  👉 [iam_policies.json](iam_policies.json)
- **Báo cáo rủi ro từ IAM Access Analyzer**: Quét được 1 analyzer và 9 findings liên quan OIDC/SAML. 
  👉 [findings.json](findings.json)
  👉 [analyzers.json](analyzers.json)
- **Danh sách tài khoản vi phạm (over-privileged)**: Đã lập danh sách và ghi nhận các policy thừa quyền (như `cdo04-infra-iam-admin`, `cdo04-budgets-full-access`).
  👉 Xem chi tiết tại [IAM_AUDIT_DOC.md](../../IAM_AUDIT_DOC.md)

## 3. Trạng thái Task
- **Status**: Done (Đã hoàn thành toàn bộ Sub-tasks).
