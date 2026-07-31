# Kế hoạch Kiểm thử (Test Plan) và Test Cases Hệ thống Audit Log Tập trung Athena
## Database: tf4_audit_forensics | Workgroup: tf4-audit-forensics

Tài liệu này cung cấp kế hoạch kiểm thử End-to-End và các Test Case cốt lõi để đánh giá tính tuân thủ Mandate 04 (AWS/EKS Audit) và Mandate 14 (AI Audit Redaction) trên Amazon Athena.

---

## 1. Mục tiêu (Objective)
1. Xác nhận dữ liệu thô (raw JSON/GZIP logs) từ S3 được ánh xạ chính xác qua Glue Data Catalog.
2. Kiểm tra tính tuân thủ an toàn PII của AI Tool Audit: toàn bộ input của tool phải được redact (redacted = true) và không lưu prompt/response nhạy cảm (content_logged = false).
3. Chứng minh hiệu quả tối ưu chi phí thông qua Partition Projection (quét dữ liệu < 500 MB thay vì quét toàn bộ bucket).
4. Phục dựng lịch sử thay đổi hạ tầng AWS (CloudTrail và AWS Config) và hoạt động của cụm EKS Kubernetes (K8s API và IAM Authenticator).

---

## 2. Phạm vi Kiểm thử (Scope và Target Tables)

Hệ thống kiểm toán tập trung bao gồm 4 đối tượng bảng/view trong Catalog:
* ai_tool_audit_events (Mandate 14): Chứa log gọi AI Model và AI Tool dạng OTLP JSON Envelope.
* cloudtrail_events (Mandate 04): Chứa nhật ký thao tác trên hạ tầng AWS (IAM, EC2, S3...).
* aws_config_history (Mandate 04): Chứa lịch sử cấu hình trạng thái của các tài nguyên AWS.
* eks_audit_events_parsed (Mandate 04): View đã được parse sẵn của K8s API server và EKS Authenticator events.

---

## 3. Danh mục các Test Case Chi tiết (Test Cases Breakdown)

### TC-ATHENA-01: OTLP Envelope Mapping Check
* Mô tả: Kiểm tra việc ánh xạ cấu trúc OTLP lồng struct attributes.* trên bảng ai_tool_audit_events.
* SQL Query:
  ```sql
  SELECT 
    trace_id,
    attributes.surface AS surface,
    attributes.model_id AS model_id,
    attributes.tool_name AS tool_name,
    attributes.safety_decision AS safety_decision,
    attributes.confirmation_status AS confirmation_status
  FROM tf4_audit_forensics.ai_tool_audit_events
  WHERE year = '2026' AND month = '07' AND day = '28'
  LIMIT 10;
  ```
* Kết quả kỳ vọng (Expected Output): Các cột surface, model_id, tool_name hiển thị đầy đủ thông tin (ví dụ: product-reviews, claude-3-5-sonnet, get_review_details), không bị NULL.

---

### TC-ATHENA-02: AI Redaction và PII Safety Verification
* Mô tả: Quét toàn bộ dữ liệu log AI Tool Call để xác thực tính tuân thủ an toàn dữ liệu nhạy cảm (PII).
* SQL Query:
  ```sql
  SELECT trace_id, attributes.tool_name, attributes.tool_input_redacted
  FROM tf4_audit_forensics.ai_tool_audit_events
  WHERE year = '2026' AND month = '07'
    AND (attributes.tool_input_redacted.redacted = false 
         OR attributes.tool_input_redacted.content_logged = true);
  ```
* Kết quả kỳ vọng (Expected Output): Trả về 0 dòng (0 rows). Chứng minh toàn bộ log của AI Tool Call đều đã được redact và đáp ứng chính sách bảo mật của Mandate 14.

---

### TC-ATHENA-03: Partition Projection và Cost Cutoff Validation
* Mô tả: Xác thực cơ chế phân vùng tự động của Athena và kiểm soát chi phí quét dữ liệu.
* SQL Query:
  ```sql
  SELECT COUNT(*) AS total_events
  FROM tf4_audit_forensics.eks_audit_events
  WHERE year = '2026' AND month = '07' AND day = '29';
  ```
* Kết quả kỳ vọng (Expected Output): Dung lượng dữ liệu quét (Data Scanned) phải nhỏ hơn 500 MB (nằm dưới mốc cutoff 10 GB cấu hình tại Workgroup).

---

### TC-ATHENA-04: CloudTrail Infrastructure Forensic Query
* Mô tả: Điều tra vết các hành vi ghi/xóa tài nguyên hạ tầng AWS và các lỗi AccessDenied.
* SQL Query:
  ```sql
  SELECT 
    eventtime,
    useridentity.arn AS principal_arn,
    eventsource,
    eventname,
    awsregion,
    sourceipaddress,
    errorcode,
    errormessage
  FROM tf4_audit_forensics.cloudtrail_events
  WHERE year = '2026' AND month = '07' AND day = '29'
    AND readonly = 'false'
  ORDER BY eventtime DESC
  LIMIT 15;
  ```
* Kết quả kỳ vọng (Expected Output): Trả về danh sách các thao tác làm biến đổi hạ tầng (như AssumeRole, PutSecretValue, CreateSecurityGroup...).

---

### TC-ATHENA-05: AWS Config và EKS Audit Reconstruction
* Mô tả: Phục dựng lịch sử xóa tài nguyên trên AWS Config và hoạt động xóa/thay đổi RBAC trên Kubernetes EKS Cluster.
* SQL Queries:
  * Query 5A (AWS Config - Xóa tài nguyên AWS):
    ```sql
    SELECT 
      ci.awsregion AS region,
      ci.resourcetype AS resource_type,
      ci.resourceid AS resource_id,
      ci.configurationitemcapturetime AS deleted_time
    FROM tf4_audit_forensics.aws_config_history
    CROSS JOIN UNNEST(configurationitems) AS t(ci)
    WHERE year = '2026' AND month = '7' AND day = '29'
      AND ci.configurationitemstatus = 'ResourceDeleted'
    ORDER BY ci.configurationitemcapturetime DESC
    LIMIT 15;
    ```
  * Query 5B (EKS - Hành vi thay đổi tài nguyên K8s API):
    ```sql
    SELECT 
      event_time,
      username,
      verb,
      namespace,
      resource_name,
      response_code
    FROM tf4_audit_forensics.eks_audit_events_parsed
    WHERE year = '2026' AND month = '07' AND day = '29'
      AND verb IN ('create', 'update', 'patch', 'delete')
    ORDER BY event_time DESC
    LIMIT 15;
    ```
  * Query 5C (EKS Authenticator - Parse log authenticator IAM):
    ```sql
    SELECT 
      event_time,
      regexp_extract(raw_message, 'arn="([^"]+)"', 1) AS iam_arn,
      regexp_extract(raw_message, 'client="([^"]+)"', 1) AS client_ip,
      regexp_extract(raw_message, 'msg="([^"]+)"', 1) AS status_msg
    FROM tf4_audit_forensics.eks_audit_events_parsed
    WHERE year = '2026' AND month = '07' AND day = '29'
      AND log_source = 'authenticator'
    ORDER BY event_time DESC
    LIMIT 10;
    ```
* Kết quả kỳ vọng (Expected Output): Phục dựng thành công lịch sử các tài nguyên bị xóa (ResourceDeleted), các lệnh EKS APIs thay đổi trạng thái cluster, và thông tin IAM ARN đăng nhập vào EKS qua Authenticator log.

---

## 4. Hướng dẫn Thực hiện Thủ công (Manual Verification Guide)

Bạn hãy thực hiện theo các bước sau trực tiếp trên AWS Console để kiểm tra:

### Bước 4.1: Cấu hình Môi trường Athena
1. Đăng nhập vào AWS Console của tài khoản 511825856493.
2. Mở dịch vụ Amazon Athena > Vào tab Query editor.
3. Tại góc phải phía trên, ở mục Workgroup, chọn tf4-audit-forensics (Bắt buộc để áp dụng cấu hình cutoff 10 GB và phân quyền).
4. Tại phần bảng điều khiển bên trái:
   - Data source: AwsDataCatalog
   - Database: tf4_audit_forensics

### Bước 4.2: Thực thi các câu lệnh SQL
Lần lượt copy các câu lệnh SQL từ Section 3 ở trên dán vào Query Editor và click Run.

### Bước 4.3: Thu thập bằng chứng kết quả (Runtime Evidence)
Với mỗi Test Case chạy thành công:
1. Lưu dữ liệu: Chụp lại ảnh màn hình kết quả trên Console làm bằng chứng.
2. Thu thập Dung lượng quét (Data Scanned): Nhìn ở góc phải của tab kết quả để lấy dung lượng dữ liệu quét.

---

## 5. Hướng dẫn Lưu File Bằng chứng (Evidence Files Structure)

Sau khi chạy xong, bạn hãy lưu các file ảnh kết quả vào thư mục docs/audit/evidence/athena-forensics/image/ trên máy của bạn với cấu trúc tên file đề xuất như sau:

1. tc-athena-01-otlp-mapping.png (Ảnh kết quả chạy TC-01)
2. tc-athena-02-ai-redaction.png (Ảnh kết quả chạy TC-02)
3. tc-athena-03-partition-scan.png (Ảnh kết quả chạy TC-03)
4. tc-athena-04-cloudtrail-forensic.png (Ảnh kết quả chạy TC-04)
5. tc-athena-05-aws-config-deletion.png (Ảnh AWS Config của TC-05)
6. tc-athena-05-eks-deletion.png (Ảnh EKS của TC-05)
