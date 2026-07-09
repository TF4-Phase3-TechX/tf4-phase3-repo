# [IAM] Yêu cầu kích hoạt IAM Access Analyzer (AUDIT-004)

## 1. Mục đích
Để nhóm Audit (CDO07) có thể đánh giá rủi ro từ các IAM Role/Policy bị cấp quá quyền (over-privileged) hoặc bị expose ra ngoài, hệ thống cần bật tính năng **IAM Access Analyzer**.
Hiện tại qua kiểm tra (Task 1) thì tính năng này chưa được bật ở region `us-east-1`.

## 2. Yêu cầu cho DevOps (CDO08)
Nhóm Audit đã commit file `infra/terraform/iam.tf` chứa cấu hình Terraform:

```hcl
resource "aws_accessanalyzer_analyzer" "main" {
  analyzer_name = "tf4-iam-analyzer"
  type          = "ACCOUNT"
}
```

Do nhóm Audit chỉ có quyền `TF4-AuditReadOnlyAndAnalyze` (không có quyền Create/Update resource), nhờ team DevOps (CDO08):
1. Review code Terraform trên.
2. Chạy `terraform apply` để tạo resource này.

## 3. Tiêu chí nghiệm thu (DoD)
- Resource được apply thành công trên AWS.
- Nhóm Audit có thể chạy lệnh `aws accessanalyzer list-findings` để ra báo cáo rủi ro.
