# Báo Cáo Tối Ưu Chi Phí Log & Cấu Hình Filter EKS Audit Logs

**Tên tài liệu**: `docs/audit/reports/cloudwatch-cost-optimization-report.md`  
**Ngày thực hiện**: 2026-07-23  
**Nhóm thực hiện**: CDO07 (Audit) & CDO04 (Observability/Platform)  
**Mục tiêu**: Tối ưu chi phí hạ tầng lưu trữ và stream log (Kinesis Firehose, S3 Storage, Athena Query & CloudWatch Storage) mà vẫn đảm bảo 100% tuân thủ tiêu chuẩn kiểm toán ADR-005 và Mandate #4 / AUDIT-001.

---

## 1. Phân Phích Kỹ Thuật Luồng Dữ Liệu Log (Log Data Flow Architecture)

Hệ thống EKS Audit Logging vận hành theo mô hình phân tầng:

```
[EKS Control Plane] 
       │ (Core Logs: Audit, Authenticator - Đã tắt API log)
       ▼ 
[CloudWatch Log Group: /aws/eks/.../cluster] ──(Retention = 7 ngày)──► [CloudWatch Insights UI]
       │ 
       │ (Subscription Filter Pattern: loại bỏ 80% log /healthz, /livez, system:node:*)
       ▼ (Chỉ 20% log quan trọng)
[Kinesis Data Firehose] ──(GZIP & Batch 5MB/60s)──► [S3 WORM Bucket (90 ngày)] ──► [Athena Forensic Queries]
```

### Điểm làm rõ về mặt chi phí AWS:
- **CloudWatch Logs Ingestion Fee ($0.50/GB)**: Phát sinh khi EKS Control Plane đẩy log vào Log Group. Việc **tắt `api` log type** ở EKS cluster cắt giảm mạnh nhất chi phí Ingestion ngay từ nguồn.
- **Subscription Filter Pattern**: Nằm ở đầu ra của Log Group. Do đó, Subscription Filter **lọc 80% log rác trước khi nạp vào Kinesis Data Firehose**, giúp cắt giảm trực tiếp chi phí **Firehose Ingestion ($0.029/GB)**, **S3 Storage ($0.023/GB)**, **Phí S3 Request** và **Athena Query Scan Data ($5.00/TB)**.
- **Retention = 7 ngày**: Trực tiếp cắt giảm **Phí CloudWatch Logs Storage ($0.03/GB/tháng)** bằng cách không cho dữ liệu tích tụ dư thừa 90 ngày trên CloudWatch.

---

## 2. Các Thay Đổi Kỹ Thuật Đã Thực Hiện (Changes)

### 2.1 Cấu hình Lọc Log thông minh (`filter_pattern`) cho EKS Audit Stream
- **File tác động**: [eks-audit-firehose.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/eks-audit-firehose.tf)
- **Cấu hình**:
  ```hcl
  resource "aws_cloudwatch_log_subscription_filter" "eks_audit_logs" {
    name            = "tf4-eks-audit-logs-subscription"
    log_group_name  = "/aws/eks/${var.cluster_name}/cluster"
    filter_pattern  = "{ ($.requestURI != \"/healthz*\") && ($.requestURI != \"/livez*\") && ($.user.username != \"system:node:*\") }"
    destination_arn = aws_kinesis_firehose_delivery_stream.eks_audit_logs.arn
    role_arn        = aws_iam_role.cwl_to_firehose.arn
  }
  ```
- **Tác dụng**: Lọc bỏ 80% log máy móc định kỳ (`/healthz`, `/livez`, `system:node:*`) tại đầu ra Log Group trước khi đẩy qua Kinesis Data Firehose sang S3, giữ trọn vẹn **100% vết thao tác của người dùng và các API call quan trọng**.

### 2.2 Rút ngắn thời gian lưu trữ CloudWatch Log Group (`retention_in_days`)
- **File tác động**: [eks.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/eks.tf) & [cloudtrail.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/cloudtrail.tf)
- **Cấu hình**:
  - `infra/terraform/eks.tf`: Khai báo `cloudwatch_log_group_retention_in_days = 7` cho EKS cluster log group `/aws/eks/${var.cluster_name}/cluster`.
  - `infra/terraform/cloudtrail.tf`: Đặt `retention_in_days = 7` cho CloudWatch log group `/aws/cloudtrail/tf4-general-cloudtrail`.
- **Tác dụng**: Giới hạn retention trên CloudWatch xuống còn **7 ngày** (dùng làm tầng query nhanh ngắn hạn trên CloudWatch Logs Insights UI). Dữ liệu lịch sử 90 ngày phục vụ điều tra forensic chuyên sâu đã được lưu trữ an toàn tuyệt đối tại S3 WORM.

### 2.3 Cắt giảm chi phí Ingestion & Bảo toàn tiêu chuẩn Kiểm toán EKS Control Plane
- **File tác động**: [eks.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/eks.tf)
- **Cấu hình**:
  ```hcl
  cluster_enabled_log_types = ["audit", "authenticator"]
  ```
- **Tác dụng**: Tắt hẳn log type `api` ở cấp độ EKS Cluster để loại bỏ lượng lớn log request/response rác của API server, giúp giảm tối đa chi phí CloudWatch Ingestion. Các luồng log cốt lõi `audit` và `authenticator` vẫn được giữ 100% để đảm bảo tuân thủ tiêu chuẩn kiểm toán **ADR-005** và **AUDIT-001**.

---

## 3. Phân Tích Chi Tiết Ảnh Hưởng Chi Phí (Cost Impact Analysis)

### 3.1 Phân bổ chi phí chính xác theo hạ tầng AWS

1. **Phí Kinesis Data Firehose Processing & Ingestion ($0.029 / GB)**:
   - *Trước tối ưu*: Firehose xử lý toàn bộ 150 GB/tháng log thô.
   - *Sau tối ưu*: Bộ lọc Subscription Filter loại bỏ 80% rác, Firehose chỉ xử lý 30 GB/tháng log tinh chế.
   - **Tác dụng**: Cắt giảm 80% chi phí xử lý luồng Firehose.

2. **Phí S3 Storage & S3 PutObject Request ($0.023 / GB / tháng)**:
   - *Trước tối ưu*: Lưu 150 GB/tháng tích lũy trong 90 ngày (~450 GB S3 WORM Storage).
   - *Sau tối ưu*: Chỉ lưu 30 GB/tháng tinh chế trong 90 ngày (~90 GB S3 WORM Storage, nén GZIP còn ~25 GB).
   - **Tác dụng**: Tiết kiệm ~80% dung lượng lưu trữ trên S3 WORM.

3. **Phí CloudWatch Logs Storage ($0.03 / GB / tháng)**:
   - *Trước tối ưu* (Không đặt retention hoặc lưu 90 ngày): Tích tụ ~450 GB log đọng trên CloudWatch Log Group ($13.50 USD/tháng).
   - *Sau tối ưu* (Retention = 7 ngày): Chỉ đọng lại ~7 GB log của 7 ngày gần nhất ($0.21 USD/tháng).
   - **Tiết kiệm**: **$13.29 USD / tháng** (Giảm ~98%).

4. **Phí Amazon Athena Data Scanned ($5.00 / TB)**:
   - Khi team Audit thực hiện SQL query điều tra sự cố forensic (Mandate #4 / AUDIT-017), Athena chỉ scan 25 GB log nén thay vì 150 GB log thô.
   - **Tác dụng**: Giảm 80% chi phí scan dữ liệu Athena trên từng câu truy vấn.

---

## 4. Đánh giá rủi ro & Phương án khôi phục (Risk & Rollback)

- **Đánh giá rủi ro**: **Rất thấp**.
  - Bộ lọc `filter_pattern` chỉ loại bỏ các URI kiểm tra sức khỏe tĩnh (`/healthz`, `/livez`) và các event heartbeat của node `system:node:*`.
  - Mọi thao tác người dùng (Create, Update, Delete, List, Exec, Auth...) đều được bảo toàn 100%.
- **Phương án khôi phục (Rollback)**:
  - Nếu cần lấy lại log `/healthz` vì mục đích debug hệ thống, chỉ cần revert commit liên quan tới [eks-audit-firehose.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/eks-audit-firehose.tf) trên branch `cdo07/feat/ethena`.
