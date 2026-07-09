# IAM Audit Report

## 1. Danh sách IAM Policies hiện hành (Local Scope)
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

## 2. Phân tích báo cáo IAM Access Analyzer
- Không có Access Analyzer nào đang bật ở `us-east-1`. 
- Kết quả rủi ro: 0 finding.

## 3. Danh sách tài khoản/policy vi phạm (Over-privileged)
- Theo Access Analyzer: **Không có dữ liệu**.
- Nhận định nhanh: Các policy mang tên `cdo04-infra-iam-admin` và `cdo04-budgets-full-access` có rủi ro thừa quyền cao, cần CDO08 review lại.
