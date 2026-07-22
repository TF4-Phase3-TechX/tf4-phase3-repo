# [AUDIT-017] Yêu cầu gán quyền Athena Forensics & CloudWatch Insights cho Audit Analysts (Mandate #4)

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO08 (Security/SSO/IAM)  
**Nhóm phối hợp**: Nhóm CDO07 (nghiệm thu query evidence)  
**Độ ưu tiên (Priority)**: P0 (Blocker nghiệm thu Athena Forensic Security Analytics - Mandate #4)  
**Epic**: Mandate-04 / Auditability - Athena Forensic Security Analytics & CW Insights  

---

## 1. Bối cảnh (Context)

Nhóm CDO07 đã hoàn tất triển khai cấu hình Terraform cho hệ thống **Athena Forensic Security Analytics** và **CloudWatch Logs Insights** trong file [athena-forensics.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/athena-forensics.tf) (Ref: AUDIT-015 / MANDATE-04).

Hệ thống cho phép truy vấn SQL tương tác trên 3 nguồn audit logs chính (CloudTrail, AWS Config, EKS Control Plane Audit Logs) phục vụ điều tra forensic security timeline ("AI làm GÌ, KHI NÀO, trên TÀI NGUYÊN NÀO").

Theo quy trình phân công trụ dự án TF4:
- CDO07 chịu trách nhiệm xây dựng bảng tra cứu Glue Catalog / Athena và viết kịch bản nghiệm thu audit query evidence.
- CDO08 chịu trách nhiệm quản lý Security/IAM/SSO permission sets.

Ticket này được khởi tạo để yêu cầu CDO08 gán 2 IAM Policy đã được định nghĩa trong Terraform vào SSO Permission Set / IAM Role của Chuyên viên Audit (`TF4-AuditReadOnlyAndAnalyze` hoặc role tương đương).

---

## 2. Danh sách IAM Policies cần gán

CDO08 vui lòng gán 2 IAM Policy ARN sau vào SSO Permission Set của Audit Analyst:

1. **`tf4-athena-audit-analyst-policy`**
   - **ARN Output**: `aws_iam_policy.athena_audit_analyst.arn` (`athena_analyst_policy_arn`)
   - **Chức năng**:
     - Cấp quyền chạy truy vấn Athena trong Workgroup `tf4-audit-forensics`.
     - Quyền đọc thông tin Glue Catalog database `tf4_audit_forensics` và các tables (`cloudtrail_events`, `aws_config_history`, `eks_audit_events`).
     - Quyền đọc (`s3:GetObject`, `s3:ListBucket`) trên 3 nguồn log buckets WORM (CloudTrail, AWS Config staging, EKS audit logs).
     - Quyền đọc/ghi kết quả truy vấn trên bucket `tf4-athena-query-results-*`.
     - Quyền giải mã KMS `kms:Decrypt` trên chìa khóa CloudTrail KMS CMK.

2. **`tf4-cloudwatch-insights-forensics-policy`**
   - **ARN Output**: `aws_iam_policy.cloudwatch_insights_forensics.arn` (`cloudwatch_insights_forensics_policy_arn`)
   - **Chức năng**: Cấp quyền chạy truy vấn CloudWatch Logs Insights real-time (< 1 giờ) đối với log group CloudTrail và EKS cluster audit log group.

---

## 3. Chính sách bảo mật & Least Privilege

- **Không có quyền ghi/sửa/xóa log gốc**: Cả 2 policy đều giới hạn ở các hành động `s3:GetObject`, `s3:ListBucket`, `glue:Get*`, `logs:StartQuery`. Tuyệt đối không cho phép `s3:DeleteObject` hay `s3:PutObject` trên các bucket lưu trữ log nguồn.
- **Giới hạn phạm vi (Scoped Resources)**: Các quyền Athena, Glue và CloudWatch Logs đều được trỏ chính xác tới ARN của Workgroup, Database và Log Group dành riêng cho TF4 Audit.

---

## 4. Kế hoạch nghiệm thu (Verification Plan)

Sau khi CDO08 đính kèm 2 policy trên:
1. CDO07 đăng nhập SSO bằng profile `TF4-AuditReadOnlyAndAnalyze`.
2. Thực thi kiểm tra các truy vấn mẫu qua Athena CLI / Console:
   - Truy vấn CloudTrail: `SELECT eventtime, eventname, useridentity.arn FROM cloudtrail_events LIMIT 10;`
   - Truy vấn AWS Config: `SELECT resourceid, resourcetype FROM aws_config_history LIMIT 10;`
   - Truy vấn EKS Audit: `SELECT verb, user.username, objectref.resource FROM eks_audit_events LIMIT 10;`
3. Lưu trữ kết quả nghiệm thu vào `docs/evidence/mandate-04-forensic/`.
