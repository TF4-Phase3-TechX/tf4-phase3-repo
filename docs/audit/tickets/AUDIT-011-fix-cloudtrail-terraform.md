[AUDIT-011] Yêu cầu sửa cấu hình CloudTrail Terraform để đạt chuẩn tamper-evident cho Mandate #4

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Nguyễn Duy Hoàng - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO04 (DevOps/IaC Owner)  
**Nhóm phối hợp**: Nhóm CDO07 (nghiệm thu evidence), Nhóm CDO08 (Security, nếu cần review IAM role cho CloudWatch Logs)  
**Độ ưu tiên (Priority)**: P0 (Blocker nghiệm thu Mandate #4 forensic audit)  
**Epic**: Mandate-04 / Auditability - forensic audit, log integrity, change trail

---

## 1. Bối cảnh (Context)

Mandate #4 yêu cầu TF4 chứng minh được: **"Bản ghi toàn tin (tamper-evident). Chứng minh audit log không sửa / xóa được tùy tiện - quyền ghi tách khỏi người vận hành."**

Theo file phân công trụ:

- `docs/epic-01-addressing-system-gap/GAP-TO-PILLAR-MAPPING.md`: CDO07 là owner trụ Auditability, chịu trách nhiệm K8s audit, CloudTrail, change management, log integrity và evidence collection.
- CDO04 là owner DevOps/IaC và Reliability, chịu trách nhiệm về Terraform, infrastructure hardening và deployment automation.
- CDO08 là owner trụ Security, chịu trách nhiệm hardening, least-privilege, credentials và access control.
- `docs/audit/TEAM_ASSIGNMENT.md`: Team Audit chỉ làm audit/evidence/change trace; các vấn đề thiết lập IaC, Reliability, Security thuộc về CDO04 và CDO08.

Vì vậy, ticket này do CDO07 tạo để yêu cầu CDO04 sửa lại Terraform configuration cho CloudTrail. CDO07 sẽ nghiệm thu lại bằng AWS CLI và lưu evidence cho Mandate #4.

Trong lần kiểm tra bằng AWS CLI ngày 2026-07-14, CloudTrail trail `tf4-general-cloudtrail` đã được xác nhận:
- `IsLogging = true`
- `IsMultiRegionTrail = true`
- S3 bucket `tf4-cloudtrail-logs-bucket-511825856493` có versioning `Enabled`

Tuy nhiên, phát hiện **3 vấn đề critical** vi phạm yêu cầu tamper-evident:

1. **`LogFileValidationEnabled = false`** - Không có digital signature để verify log integrity
2. **`force_destroy = true`** (trong Terraform) - Bucket có thể bị xóa khi `terraform destroy`
3. **S3 bucket chưa có explicit Deny cho operator delete** - Operator có thể xóa audit logs

Các vấn đề này đã xuất hiện trong ticket cũ:
- `AUDIT-007-fix-security-findings.md` đã nêu thiếu log file validation
- Nhưng chưa có ticket nào yêu cầu fix đầy đủ cả 3 issues trong Terraform code

Ticket này yêu cầu CDO04 sửa lại Terraform để đạt chuẩn tamper-evident cho Mandate #4.

---

## 2. Yêu cầu từ CDO04 (The What)

Team CDO04 vui lòng cập nhật Terraform code cho CloudTrail và S3 bucket để fix 3 issues sau:

### 2.1. Critical (Bắt Buộc - P0)

| Issue | File | Fix | Lý do |
|-------|------|-----|-------|
| Log File Validation Disabled | `infra/terraform/cloudtrail.tf` | `enable_log_file_validation = true` | Không có digital signature → không detect được tamper |
| Force Destroy Enabled | `infra/terraform/cloudtrail.tf` | `force_destroy = false` | Bucket có thể bị xóa khi terraform destroy → mất audit logs |
| S3 Bucket Policy thiếu Deny | `infra/terraform/cloudtrail.tf` | Thêm explicit Deny cho operator `DeleteObject`, `DeleteObjectVersion` | Operator có thể xóa audit logs của chính mình |

### 2.2. Recommended (Bảo mật tăng cường)

| Feature | File | Add | Lý do | Cost Impact |
|---------|------|-----|-------|-------------|
| S3 Object Lock GOVERNANCE | `infra/terraform/cloudtrail.tf` | `object_lock_enabled = true` + retention 90 days | WORM protection - log không thể sửa/xóa trong 90 ngày | $0 (included) |
| Lifecycle prevent_destroy | `infra/terraform/cloudtrail.tf` | `lifecycle { prevent_destroy = true }` | Ngăn terraform destroy vô tình | $0 |
| KMS CMK riêng | `infra/terraform/cloudtrail.tf` | `kms_key_id` + dedicated KMS key | Tách biệt encryption key, key rotation enabled | ~$1/tháng |

### 2.3. Optional (Nice to have - Nếu chi phí cho phép)

| Feature | File | Add | Lý do | Cost Impact |
|---------|------|-----|-------|-------------|
| CloudWatch Logs Integration | `infra/terraform/cloudtrail.tf` | `cloud_watch_logs_group_arn` + `cloud_watch_logs_role_arn` | Query real-time bằng CloudWatch Logs Insights | ~$2-7/tuần baseline, ~$15/tuần peak |

---

## 3. Evidence từ kiểm tra bằng AWS CLI

### 3.1. Checks đã pass
```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
# Output: IsLogging = true, IsMultiRegionTrail = true ✅

aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-511825856493
# Output: Status = Enabled ✅
```

### 3.2. Checks bị fail (Cần fix)
```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.trailList[0].LogFileValidationEnabled'
# Output: false ❌ (PHẢI LÀ true)

# Terraform state (kiểm tra thủ công)
terraform state show aws_s3_bucket.cloudtrail_logs | grep force_destroy
# Output: force_destroy = true ❌ (PHẢI LÀ false)
```

---

## 4. Terraform code changes đề xuất

### 4.1. Fix #1: CloudTrail Log File Validation (P0)

**File:** `infra/terraform/cloudtrail.tf`

**Before:**
```hcl
resource "aws_cloudtrail" "main" {
  name                          = "tf4-general-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  
  # enable_log_file_validation = true  # THIẾU DÒNG NÀY
}
```

**After:**
```hcl
resource "aws_cloudtrail" "main" {
  name                          = "tf4-general-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  
  enable_log_file_validation    = true  # ✅ THÊM DÒNG NÀY
}
```

### 4.2. Fix #2: S3 Bucket Force Destroy (P0)

**File:** `infra/terraform/cloudtrail.tf`

**Before:**
```hcl
resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket        = "tf4-cloudtrail-logs-bucket-511825856493"
  force_destroy = true  # ❌ NGUY HIỂM
}
```

**After:**
```hcl
resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket        = "tf4-cloudtrail-logs-bucket-511825856493"
  force_destroy = false  # ✅ SỬA THÀNH FALSE
  
  lifecycle {
    prevent_destroy = true  # ✅ BONUS: Ngăn terraform destroy
  }
}
```

### 4.3. Fix #3: S3 Bucket Policy Explicit Deny (P0)

**File:** `infra/terraform/cloudtrail.tf`

**Thêm vào `aws_s3_bucket_policy` resource:**

```hcl
resource "aws_s3_bucket_policy" "cloudtrail_logs_policy" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ... existing Allow statements ...
      
      # ✅ THÊM STATEMENT NÀY: Deny operator xóa log
      {
        Sid    = "DenyNonAdminDeleteObject"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action = [
          "s3:DeleteObject",
          "s3:DeleteObjectVersion"
        ]
        Resource = "${aws_s3_bucket.cloudtrail_logs.arn}/*"
        Condition = {
          StringNotEquals = {
            "aws:PrincipalArn" = [
              "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root",
              "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/tf4-github-actions-terraform-apply"
            ]
          }
        }
      },
      
      # ✅ BONUS: Deny xóa bucket
      {
        Sid    = "DenyDeleteBucket"
        Effect = "Deny"
        Principal = {
          AWS = "*"
        }
        Action   = "s3:DeleteBucket"
        Resource = aws_s3_bucket.cloudtrail_logs.arn
        Condition = {
          StringNotEquals = {
            "aws:PrincipalArn" = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
          }
        }
      }
    ]
  })
}
```

### 4.4. Recommended: S3 Object Lock GOVERNANCE

**File:** `infra/terraform/cloudtrail.tf`

```hcl
# Bước 1: Enable Object Lock khi tạo bucket (BREAKING CHANGE - forces new resource)
resource "aws_s3_bucket" "cloudtrail_logs" {
  bucket              = "tf4-cloudtrail-logs-bucket-${data.aws_caller_identity.current.account_id}"
  force_destroy       = false
  object_lock_enabled = true  # ✅ THÊM DÒNG NÀY
}

# Bước 2: Cấu hình Object Lock retention
resource "aws_s3_bucket_object_lock_configuration" "cloudtrail_logs" {
  bucket = aws_s3_bucket.cloudtrail_logs.id

  rule {
    default_retention {
      mode = "GOVERNANCE"  # Operator không xóa được, admin vẫn có thể override
      days = 90
    }
  }
}
```

### 4.5. Optional: CloudWatch Logs Integration

**File:** `infra/terraform/cloudtrail.tf`

```hcl
resource "aws_cloudtrail" "main" {
  name                          = "tf4-general-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.cloudtrail_logs.id
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  
  # Optional: Tích hợp CloudWatch Logs
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.cloudtrail_cloudwatch.arn
}

resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/cloudtrail/tf4-general-cloudtrail"
  retention_in_days = 14
}

resource "aws_iam_role" "cloudtrail_cloudwatch" {
  name = "tf4-cloudtrail-cloudwatch-logs"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "cloudtrail.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "cloudtrail_cloudwatch" {
  name = "cloudtrail-cloudwatch-logs"
  role = aws_iam_role.cloudtrail_cloudwatch.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
      Effect = "Allow"
      Resource = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
    }]
  })
}
```

---

## 5. Cost Impact

| Component | Cost | Notes |
|-----------|------|-------|
| **P0 Fixes (Critical)** | | |
| Log File Validation | **$0** | Free feature của CloudTrail ✅ |
| Force Destroy = false | **$0** | Chỉ là protection flag ✅ |
| S3 Bucket Policy Deny | **$0** | Free feature của S3 ✅ |
| **Recommended** | | |
| S3 Object Lock | **$0** | Free feature của S3 ✅ |
| Lifecycle prevent_destroy | **$0** | Terraform config ✅ |
| KMS CMK riêng | **~$1/tháng** | $1/key/month + $0.03/10k requests |
| **Optional** | | |
| CloudWatch Logs | ~$2-7/tuần baseline | Xem breakdown bên dưới |

**CloudWatch Logs Cost Breakdown (Optional):**
- Ingestion: ~50 MB/day × $0.50/GB = **~$1.75/tuần**
- Storage (90 days): ~4.5 GB × $0.03/GB/month = **~$0.30/tuần**
- **Total baseline:** ~$2/tuần
- **Peak (load test):** ~$7/tuần (200 MB/day)

**Total cho tất cả fixes:**
- **P0 only:** $0 ✅
- **P0 + Recommended:** ~$0.25/tuần ✅
- **Full (bao gồm CloudWatch Logs):** ~$2.25/tuần ✅

✅ **Vẫn trong budget $300/tuần/TF**

---

## 6. Ranh giới trách nhiệm

- **CDO04 owns:** Cập nhật Terraform code và apply changes vì đây là phần Infrastructure, IaC management và Reliability hardening.
- **CDO07 owns:** Audit/evidence - chạy lại AWS CLI checks, xác nhận `LogFileValidationEnabled = true`, `force_destroy = false`, lưu evidence cho Mandate #4.
- **CDO08 chỉ phối hợp:** Nếu cần review IAM role cho CloudWatch Logs integration (security best practices).
- Ticket này không yêu cầu CDO07 tự thay đổi Terraform, đúng với ranh giới "Audit chỉ đọc và nghiệm thu".

---

## 7. Tiêu chí nghiệm thu (Acceptance Criteria / Evidence)

### 7.1. P0 Fixes (Bắt Buộc)
- [ ] Terraform code đã sửa: `enable_log_file_validation = true`
- [ ] Terraform code đã sửa: `force_destroy = false`
- [ ] Terraform code đã thêm: S3 bucket policy với `DenyNonAdminDeleteObject` statement
- [ ] `terraform plan` không có unexpected changes
- [ ] `terraform apply` thành công
- [ ] CDO07 chạy lại được AWS CLI checks:
  ```bash
  # Test 1: Log file validation
  aws cloudtrail describe-trails | jq '.trailList[0].LogFileValidationEnabled'
  # Expected: true ✅
  
  # Test 2: Terraform state
  terraform state show aws_s3_bucket.cloudtrail_logs | grep force_destroy
  # Expected: force_destroy = false ✅
  
  # Test 3: Bucket policy có Deny statement
  aws s3api get-bucket-policy --bucket tf4-cloudtrail-logs-bucket-511825856493 \
    | jq '.Policy | fromjson | .Statement[] | select(.Sid=="DenyNonAdminDeleteObject")'
  # Expected: có statement với Effect = "Deny" ✅
  ```

### 7.2. Recommended (Nếu implement)
- [ ] S3 Object Lock enabled: `object_lock_enabled = true`
- [ ] Object Lock configuration: GOVERNANCE mode, 90 days
- [ ] Lifecycle prevent_destroy = true
- [ ] KMS CMK riêng tạo thành công

### 7.3. Optional (CloudWatch Logs)
- [ ] CloudWatch Logs integration working nếu implement
- [ ] Log streams có data trong 24h gần nhất

### 7.4. Evidence Files
- [ ] CDO07 lưu evidence: `docs/evidence/aud-17.1-cloudtrail-status-after-fix.json`
- [ ] CDO07 lưu evidence: `docs/evidence/aud-17.1-s3-bucket-policy.json`
- [ ] CDO07 test separation of duties: operator thử xóa log → AccessDenied
- [ ] Mandate #4 forensic runbook có đủ evidence về log integrity

---

## 8. Terraform Apply Steps (Cho CDO04)

```bash
# 1. Backup state
terraform state pull > backup-state-$(date +%Y%m%d).json

# 2. Edit files
# - infra/terraform/cloudtrail.tf: Thêm enable_log_file_validation = true
# - infra/terraform/s3.tf: Sửa force_destroy = false

# 3. Plan changes
cd infra/terraform
terraform plan -out=mandate04-cloudtrail.tfplan

# 4. Review output
# Đảm bảo chỉ update CloudTrail và S3 bucket, không có destroy ngoài ý muốn

# 5. Apply
terraform apply mandate04-cloudtrail.tfplan

# 6. Verify
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.trailList[0].LogFileValidationEnabled'
# Expected: true ✅
```

---

## 9. Ghi chú cho implementation sau khi được approve

Sau khi CDO04 apply Terraform changes, CDO07 sẽ chạy lại các checks sau:

### 9.1. CloudTrail Log File Validation
```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-cloudtrail-status-after-fix.json

# Verify LogFileValidationEnabled = true
jq '.trailList[0].LogFileValidationEnabled' docs/evidence/aud-17.1-cloudtrail-status-after-fix.json
```

### 9.2. S3 Bucket Force Destroy + Policy
```bash
# Test 1: CDO04 cung cấp Terraform state output:
terraform state show aws_s3_bucket.cloudtrail_logs > docs/evidence/aud-17.1-s3-bucket-state.txt

# CDO07 verify force_destroy = false
grep force_destroy docs/evidence/aud-17.1-s3-bucket-state.txt

# Test 2: CDO07 verify S3 bucket policy có Deny statement
aws s3api get-bucket-policy \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-s3-bucket-policy.json

# Verify có DenyNonAdminDeleteObject
jq '.Policy | fromjson | .Statement[] | select(.Sid=="DenyNonAdminDeleteObject")' \
  docs/evidence/aud-17.1-s3-bucket-policy.json
# Expected: Effect = "Deny", Action = ["s3:DeleteObject", "s3:DeleteObjectVersion"]
```

### 9.3. Live Test: Operator không xóa được log
```bash
# CDO07 test với operator role (TF4-Developer)
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/<any-log-file> \
  --profile TF4-Developer 2>&1 | tee docs/evidence/aud-17.3-separation-test-log.md
# Expected: "Access Denied" error ✅
```

### 9.3. Live Test: Operator không xóa được log
```bash
# CDO07 test với operator role (TF4-Developer)
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/<any-log-file> \
  --profile TF4-Developer 2>&1 | tee docs/evidence/aud-17.3-separation-test-log.md
# Expected: "Access Denied" error ✅
```

### 9.4. Optional: S3 Object Lock
```bash
# Nếu implement Object Lock, verify:
aws s3api get-object-lock-configuration \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze
# Expected: Mode = "GOVERNANCE", Days = 90 ✅
```

### 9.5. Optional: CloudWatch Logs Integration
```bash
# Nếu implement, verify log stream mới:
aws logs describe-log-streams \
  --log-group-name /aws/cloudtrail/tf4-general-cloudtrail \
  --order-by LastEventTime --descending --max-items 1 \
  --profile TF4-AuditReadOnlyAndAnalyze
# Expected: stream mới trong 24h ✅
```

Kết quả pass/fail sẽ được lưu làm evidence cho Mandate #4. Nếu vẫn có issue, CDO07 sẽ mở ticket bổ sung hoặc cập nhật ticket này.

*(Sau khi hoàn thành, vui lòng tag CDO07 - Nguyễn Duy Hoàng để nghiệm thu evidence Mandate #4.)*
