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

**Bằng chứng kiểm tra thực tế (Runtime Evidence):**
Khi đăng nhập bằng profile SSO `TF4-AuditReadOnlyAndAnalyze` (`hoang.nguyenduy`) trên AWS Console, hệ thống báo lỗi `AccessDenied`:
- `athena:GetWorkGroup` trên Workgroup `tf4-audit-forensics` bị từ chối.
- `glue:GetDatabases` trên Catalog `arn:aws:glue:us-east-1:511825856493:catalog` bị từ chối do chưa được gán Identity-based Policy.

Ticket này được khởi tạo để yêu cầu CDO08 gán 2 IAM Policy đã được định nghĩa trong Terraform vào SSO Permission Set / IAM Role của Chuyên viên Audit (`TF4-AuditReadOnlyAndAnalyze`).

---

## 2. Danh sách IAM Policies cần gán

CDO08 vui lòng gán 2 IAM Policy ARN sau vào SSO Permission Set của Audit Analyst:

1. **`tf4-athena-audit-analyst-policy`**
   - **ARN Output**: `aws_iam_policy.athena_audit_analyst.arn` (`athena_analyst_policy_arn`)
   - **Chức năng chi tiết**:
     - **Điều hướng Athena Console UI**: Cấp quyền `athena:ListWorkGroups`, `athena:ListDataCatalogs`, `athena:GetDataCatalog` (`Resource: "*"`) để hiển thị danh sách Workgroup và Data Catalog trên giao diện web.
     - **Thực thi truy vấn Athena**: Cấp quyền `athena:StartQueryExecution`, `athena:StopQueryExecution`, `athena:GetQueryExecution`, `athena:GetQueryResults`, `athena:GetQueryResultsStream`, `athena:GetWorkGroup`, `athena:ListQueryExecutions` trên Workgroup `tf4-audit-forensics`.
     - **Đọc Glue Data Catalog**: Cấp quyền `glue:GetDatabase`, `glue:GetDatabases`, `glue:GetTable`, `glue:GetTables`, `glue:GetPartition`, `glue:GetPartitions`, `glue:BatchGetPartition` trên Catalog và Database `tf4_audit_forensics` cùng các bảng (`cloudtrail_events`, `aws_config_history`, `eks_audit_events`).
     - **Đọc dữ liệu nguồn S3 WORM**: Quyền đọc (`s3:GetObject`, `s3:ListBucket`, `s3:GetBucketLocation`) trên 3 nguồn log buckets WORM (CloudTrail, AWS Config staging, EKS audit logs).
     - **Ghi kết quả truy vấn**: Quyền ghi (`s3:PutObject`, `s3:GetObject`, `s3:ListBucket`, `s3:GetBucketLocation`, `s3:AbortMultipartUpload`, `s3:DeleteObject`) trên bucket `tf4-athena-query-results-*`.
     - **Giải mã KMS Log**: Quyền `kms:Decrypt`, `kms:DescribeKey` trên chìa khóa CloudTrail KMS CMK (`aws_kms_key.cloudtrail.arn`).

2. **`tf4-cloudwatch-insights-forensics-policy`**
   - **ARN Output**: `aws_iam_policy.cloudwatch_insights_forensics.arn` (`cloudwatch_insights_forensics_policy_arn`)
   - **Chức năng chi tiết**:
     - **Liệt kê Log Groups trên Console**: Cấp quyền `logs:DescribeLogGroups` (`Resource: "*"`) để hiển thị danh sách Log Groups trên giao diện CloudWatch Logs Insights Console.
     - **Chạy truy vấn Real-time Insights**: Cấp quyền `logs:StartQuery`, `logs:StopQuery`, `logs:GetQueryResults`, `logs:GetLogEvents`, `logs:FilterLogEvents`, `logs:DescribeLogStreams` trên Log Group CloudTrail (`tf4-cloudtrail-logs`) và EKS Audit Log Group (`/aws/eks/*/cluster`).

---

## 3. Chính sách bảo mật & Least Privilege

- **Không có quyền ghi/sửa/xóa log gốc**: Cả 2 policy đều tuân thủ chặt chẽ nguyên tắc Least Privilege, chỉ cho phép các hành động đọc (`s3:GetObject`, `s3:ListBucket`, `glue:Get*`, `logs:StartQuery`). Tuyệt đối không cho phép `s3:DeleteObject` hay `s3:PutObject` trên các bucket lưu trữ log nguồn.
- **Giới hạn phạm vi (Scoped Resources)**: ngoại trừ các quyền liệt kê danh mục cấp Console bắt buộc (`athena:ListWorkGroups`, `athena:ListDataCatalogs`, `glue:GetDatabases`, `logs:DescribeLogGroups`), tất cả các quyền thực thi Athena, Glue metadata và CloudWatch Logs đều được trỏ chính xác tới ARN của Workgroup, Database và Log Group dành riêng cho TF4 Audit.

---

## 4. Kế hoạch nghiệm thu (Verification Plan)

Sau khi CDO08 đính kèm 2 policy trên:
1. CDO07 đăng nhập SSO bằng profile `TF4-AuditReadOnlyAndAnalyze`.
2. Mở AWS Console (web UI) kiểm tra:
   - Truy cập Athena Query Editor: Xác nhận Workgroup `tf4-audit-forensics` và Database `tf4_audit_forensics` hiển thị thành công trong menu dropdown mà không bị lỗi `AccessDenied`.
   - Truy cập CloudWatch Logs Insights: Xác nhận hiển thị danh sách Log Groups audit.
3. Thực thi kiểm tra các truy vấn mẫu qua Athena CLI / Console:
   - Truy vấn CloudTrail: `SELECT eventtime, eventname, useridentity.arn FROM cloudtrail_events LIMIT 10;`
   - Truy vấn AWS Config: `SELECT resourceid, resourcetype FROM aws_config_history LIMIT 10;`
   - Truy vấn EKS Audit: `SELECT verb, user.username, objectref.resource FROM eks_audit_events LIMIT 10;`
4. Lưu trữ kết quả nghiệm thu vào `docs/evidence/mandate-04-forensic/`.
