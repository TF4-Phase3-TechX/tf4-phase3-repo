# Runbook: Athena Forensic Security Analytics (MANDATE-04 & MANDATE-14)

Người phụ trách: CDO07 (Auditability & Security Analytics)  
Cập nhật lần cuối: 2026-07-29  
SLO liên quan: SLO-AUD-01 (100% Forensic Audit Trail Queryable & Immutable)  
Dashboard liên quan: AWS Athena Query Editor (Database: `tf4_audit_forensics`, Workgroup: `tf4-audit-forensics`)  
Jira liên quan: AUDIT-015, AUDIT-017  
IaC Source: [infra/terraform/athena-forensics.tf](file:///d:/AWS/Ethena/tf4-phase3-repo/infra/terraform/athena-forensics.tf)

---

## 💡 1. Tổng Quan & Cơ Chế Hoạt Động Của Athena

### 1.1. Amazon Athena Hoạt Động Như Thế Nào?
Khác với các cơ sở dữ liệu truyền thống (MySQL, PostgreSQL) phải nạp dữ liệu vào bảng trước khi query, **Amazon Athena** là một dịch vụ truy vấn theo cơ chế **Schema-on-Read**:
1. Dữ liệu thô (Raw Logs dạng JSON/GZIP) được lưu trực tiếp trên **S3 WORM Buckets**.
2. **AWS Glue Data Catalog** (database `tf4_audit_forensics`) đóng vai trò như một "cuốn từ điển" chứa Metadata (định nghĩa cấu trúc các cột và đường dẫn thư mục S3).
3. Khi bạn thực hiện câu lệnh SQL, Athena sẽ đọc trực tiếp các file JSON từ S3, áp cấu trúc từ Glue Catalog vào và trả về kết quả dưới dạng bảng.

### 1.2. Cơ Chế Partition Projection (Tối Ưu Tốc Độ & Chi Phí)
* Để Athena không phải quét hàng triệu file trên S3, hệ thống sử dụng **Partition Projection**. Athena tự động tính toán đường dẫn folder S3 dựa trên mốc thời gian (`year/month/day/hour`).
* Ví dụ: Khi gõ `WHERE year = '2026' AND month = '07' AND day = '29'`, Athena chỉ quét duy nhất folder `s3://.../2026/07/29/` thay vì quét toàn bộ bucket.

### 1.3. Luồng Dữ Liệu End-to-End (Data Flow Pipeline)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. AI Tool Audit: App ──► OTel Collector ──► CW Logs ──► Firehose ──► S3    │
│ 2. EKS Control Plane: K8s API Server ──────► CW Logs ──► Firehose ──► S3    │
│ 3. AWS Infrastructure: CloudTrail ─────────────────────────────────► S3     │
│ 4. AWS Config Timeline: AWS Config Service ────────────────────────► S3     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ (Định dạng JSON / GZIP)
                                       ▼
                     [ S3 WORM Buckets (Bảo mật 90 ngày) ]
                                       │
                                       ▼ (Schema-on-Read)
                   [ Glue Database: tf4_audit_forensics ]
                                       │
                                       ▼
                [ Athena Workgroup: tf4-audit-forensics ]
```

---

## 🛡️ 2. Quy Tắc An Toàn & Bảo Vệ Chi Phí (Safety Guardrails)

Workgroup `tf4-audit-forensics` được cấu hình tính năng bảo vệ chi phí nghiêm ngặt:
* **Max Bytes Scanned / Query**: `10737418240 bytes` (**tối đa 10 GB / query**).
* **Cơ chế cắt tự động**: Nếu một câu lệnh truy vấn quét vượt quá 10 GB dữ liệu, Athena sẽ **tự động hủy (Cancel)** query đó ngay lập tức để tránh phát sinh chi phí ngoài ý muốn ($0.05 / query max).
* **Quy tắc vàng khi query**: Mọi câu lệnh SQL **BẮT BUỘC** phải có điều kiện khoanh vùng theo ngày (`WHERE year = '...' AND month = '...' AND day = '...'`).

---

## 📊 3. Danh Mục 4 Bảng Dữ Liệu Audit & Quy Ước Cấu Trúc

| Bảng / View Catalog | Nguồn Dữ Liệu Gốc | Đặc Điểm Cấu Trúc JSON | Quy Ước Khoanh Vùng S3 |
|---|---|---|---|
| **`ai_tool_audit_events`** | Log gọi AI Model & Tool (Mandate 14) | Dạng OTLP JSON Envelope. Các thuộc tính nằm trong struct `attributes.*` | `month` 2 chữ số (`'07'`) |
| **`cloudtrail_events`** | Nhật ký thao tác API trên AWS Infrastructure | Dạng CloudTrail JSON. Thông tin danh tính nằm trong `useridentity.arn` | `month` 2 chữ số (`'07'`), `day` 2 chữ số (`'29'`) |
| **`aws_config_history`** | Lịch sử thay đổi cấu hình tài nguyên AWS | Dạng JSON bọc (`{"configurationItems": [...]}`). Cần `UNNEST` | **`month` 1 chữ số (`'7'`)** (Do S3 folder AWS Config không có số 0 ở đầu) |
| **`eks_audit_events_parsed`** | View giải mã EKS API Server & Authenticator Log | Dạng View giải mã sẵn các trường `username`, `verb`, `resource_name`... | **BẮT BUỘC** filter `day = 'DD'` (Dung lượng log rất lớn) |

---

## 🔍 4. Hướng Dẫn Chi Tiết Các Kịch Bản Truy Vết Forensic (Step-by-Step)

### 4.1. Thao Tác Ban Đầu Trên AWS Console
1. Truy cập **AWS Management Console** > Tìm dịch vụ **Amazon Athena**.
2. Tại góc trên bên phải thanh Athena, chọn Workgroup: **`tf4-audit-forensics`**.
3. Tại menu bên trái (**Data**):
   - **Data source**: `AwsDataCatalog`
   - **Database**: `tf4_audit_forensics`

---

### 4.2. Kịch Bản MANDATE-14: AI Tool Audit & Redaction Compliance

#### ❓ Tại sao dùng cú pháp `attributes.tool_name`?
Do OpenTelemetry Exporter đóng gói dữ liệu dưới dạng OTLP JSON Envelope, nên toàn bộ thuộc tính audit được lồng bên trong đối tượng `attributes`.

```sql
-- QUERY 1A: Xem 10 nhật ký gọi AI Tool mới nhất
SELECT 
  trace_id,
  attributes.surface AS surface,                           -- Ứng dụng gọi (ví dụ: product-reviews)
  attributes.model_id AS model_id,                         -- ID mô hình AI
  attributes.tool_name AS tool_name,                       -- Tên tool AI sử dụng
  attributes.safety_decision AS safety_decision,           -- Quyết định an toàn (ALLOW / BLOCK)
  attributes.confirmation_status AS confirmation_status,   -- Trạng thái xác nhận
  attributes.tool_input_redacted.redacted AS is_redacted,  -- Đã Redact chưa (Phải là true)
  attributes.tool_input_redacted.content_logged AS content_logged -- Có ghi nội dung không (Phải là false)
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '2026' AND month = '07'
LIMIT 10;

-- QUERY 1B: Kiểm tra vi phạm an toàn Redaction (Kỳ vọng kết quả trả về: 0 ROWS)
SELECT trace_id, attributes.tool_name, attributes.tool_input_redacted
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '2026' AND month = '07'
  AND (attributes.tool_input_redacted.redacted = false 
       OR attributes.tool_input_redacted.content_logged = true);

-- QUERY 1C: Thống kê số lượt sử dụng AI Tool & Quyết định an toàn (Safety Decision Aggregation)
SELECT 
  attributes.tool_name AS tool_name,
  attributes.safety_decision AS safety_decision,
  attributes.confirmation_status AS confirmation_status,
  COUNT(*) AS total_calls
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '2026' AND month = '07'
GROUP BY 
  attributes.tool_name, 
  attributes.safety_decision, 
  attributes.confirmation_status
ORDER BY total_calls DESC;
```

---

### 4.3. Kịch Bản MANDATE-04: Truy Vết Danh Tính Thao Tác Hạ Tầng AWS (CloudTrail)

```sql
-- QUERY 2A: Nhật ký thao tác thay đổi hạ tầng AWS (Write Operations & Principal Identity)
SELECT 
  eventtime,                            -- Thời điểm diễn ra sự kiện (UTC)
  useridentity.arn AS principal_arn,     -- Danh tính ARN người thực hiện (IAM User / Role)
  eventsource,                          -- Dịch vụ AWS bị tác động (ví dụ: ec2.amazonaws.com)
  eventname,                            -- Tên hành động API (ví dụ: RunInstances, DeleteSecurityGroup)
  awsregion,                            -- Region xảy ra thao tác (us-east-1)
  sourceipaddress,                      -- Địa chỉ IP nguồn gọi API
  errorcode,                            -- Mã lỗi (nếu có, ví dụ: AccessDenied)
  errormessage                          -- Thông báo lỗi chi tiết
FROM tf4_audit_forensics.cloudtrail_events
WHERE year = '2026' 
  AND month = '07' 
  AND day = '29'
  AND readonly = 'false'                -- Chỉ lọc các thao tác thay đổi (Ghi/Xóa), bỏ qua thao tác Đọc
ORDER BY eventtime DESC
LIMIT 15;

-- QUERY 2B: Truy vết các truy cập thất bại / Bị từ chối quyền (Unauthorized & Access Denied Audit)
SELECT 
  eventtime,
  useridentity.arn AS principal_arn,
  eventsource,
  eventname,
  sourceipaddress,
  errorcode,
  errormessage
FROM tf4_audit_forensics.cloudtrail_events
WHERE year = '2026' 
  AND month = '07' 
  AND day = '29'
  AND errorcode IS NOT NULL             -- Lọc các lệnh gặp lỗi permission hoặc từ chối
ORDER BY eventtime DESC
LIMIT 15;
```

---

### 4.4. Kịch Bản MANDATE-04: Dựng Timeline Biến Động Cấu Hình Tài Nguyên (AWS Config)

#### ❓ Tại sao dùng `CROSS JOIN UNNEST(configurationitems)`?
Dịch vụ AWS Config ghi log xuống S3 theo cấu trúc một mảng chứa nhiều sự kiện `{"configurationItems": [...]}`. Cú pháp `CROSS JOIN UNNEST` giúp "trải phẳng" từng phần tử trong mảng ra thành từng dòng riêng biệt để dễ truy vấn.

#### ⚠️ Lưu ý quan trọng về tháng:
S3 folder của AWS Config lưu tháng dưới dạng **1 chữ số** đối với các tháng < 10 (ví dụ folder `7/` thay vì `07/`). Do đó mệnh đề WHERE **BẮT BUỘC** dùng `month = '7'`.

```sql
-- QUERY 3A: Lịch sử biến động cấu hình tài nguyên AWS
SELECT 
  year,
  month,
  day,
  ci.awsaccountid AS account_id,                  -- AWS Account ID
  ci.awsregion AS region,                          -- Region của tài nguyên
  ci.resourcetype AS resource_type,                -- Loaị tài nguyên (AWS::EC2::Instance, AWS::EC2::SecurityGroup...)
  ci.resourceid AS resource_id,                    -- ID tài nguyên (ví dụ: i-0ff6e1da5680e4be4)
  ci.resourcename AS resource_name,                -- Tên tài nguyên
  ci.configurationitemstatus AS status,            -- Trạng thái (ResourceDiscovered, ResourceDeleted...)
  ci.configurationitemcapturetime AS capture_time  -- Thời điểm AWS Config ghi nhận biến động
FROM tf4_audit_forensics.aws_config_history
CROSS JOIN UNNEST(configurationitems) AS t(ci)
WHERE year = '2026' 
  AND month = '7'  -- BẮT BUỘC: Dùng '7' (không dùng '07') để khớp thư mục S3 của AWS Config
  AND day = '29'
ORDER BY ci.configurationitemcapturetime DESC
LIMIT 15;

-- QUERY 3B: Truy vết tài nguyên AWS vừa bị XÓA (Resource Deletion Audit)
SELECT 
  ci.awsregion AS region,
  ci.resourcetype AS resource_type,
  ci.resourceid AS resource_id,
  ci.configurationitemcapturetime AS deleted_time
FROM tf4_audit_forensics.aws_config_history
CROSS JOIN UNNEST(configurationitems) AS t(ci)
WHERE year = '2026' 
  AND month = '7' 
  AND day = '29'
  AND ci.configurationitemstatus = 'ResourceDeleted'
ORDER BY ci.configurationitemcapturetime DESC;
```

---

### 4.5. Kịch Bản MANDATE-04: Truy Vết Thao Tác Trên Cụm Kubernetes EKS (EKS Audit Logs)

```sql
-- QUERY 4A: Truy vết thao tác làm thay đổi tài nguyên K8s (Create / Update / Delete / Patch)
SELECT 
  event_time,     -- Thời điểm diễn ra thao tác trên EKS
  log_source,     -- Nguồn log ('audit' từ K8s API Server hoặc 'authenticator' từ IAM Auth)
  username,       -- Username / IAM ARN gọi vào EKS cluster
  verb,           -- Hành động K8s (get, list, create, update, delete, patch...)
  namespace,      -- Kubernetes Namespace bị tác động
  resource_name,  -- Tên tài nguyên K8s (Pod name, Deployment name, Service name...)
  response_code   -- Mã HTTP response (200, 201, 403 Forbidden...)
FROM tf4_audit_forensics.eks_audit_events_parsed
WHERE year = '2026' 
  AND month = '07' 
  AND day = '29'  -- BẮT BUỘC: Phải chọn ngày cụ thể để tránh bị quá mốc 10GB scan
  AND verb IN ('create', 'update', 'patch', 'delete')
ORDER BY event_time DESC
LIMIT 15;

-- QUERY 4B: Truy vết xác thực IAM vào Cụm EKS (IAM Authenticator Login Audit)
-- 💡 LƯU Ý: Log 'authenticator' có định dạng Text Key-Value (logfmt), không phải JSON.
-- Do đó cần dùng regexp_extract() để tách IAM ARN và IP nguồn từ raw_message.
SELECT 
  event_time,
  regexp_extract(raw_message, 'arn="([^"]+)"', 1) AS iam_arn,        -- Tách IAM Role / User ARN
  regexp_extract(raw_message, 'client="([^"]+)"', 1) AS client_ip,   -- Tách Client IP
  regexp_extract(raw_message, 'msg="([^"]+)"', 1) AS status_msg,     -- Tách kết quả (access granted / denied)
  raw_message
FROM tf4_audit_forensics.eks_audit_events_parsed
WHERE year = '2026' 
  AND month = '07' 
  AND day = '29'
  AND log_source = 'authenticator'
ORDER BY event_time DESC
LIMIT 15;
```

---

## 🛠️ 5. Bảng Tra Cứu Xử Lý Sự Cố Khi Query (Troubleshooting Guide)

| Hiện Tượng / Lỗi | Nguyên Nhân Gốc | Cách Xử Lý Chi Tiết |
|---|---|---|
| **`Bytes scanned limit was exceeded`** (10 GB) | Truy vấn quên không khoanh vùng ngày (`day`), khiến Athena phải quét toàn bộ log S3 của cả tháng. | Thêm điều kiện `AND day = 'DD'` vào mệnh đề `WHERE` để giới hạn phạm vi scan xuống dưới 500 MB. |
| **Results (0)** và `Data scanned: -` tại bảng AWS Config | Điền `month = '07'` trong khi thư mục S3 của AWS Config lưu dạng 1 chữ số (`7/`). | Đổi điều kiện thành `WHERE month = '7'` hoặc dùng `WHERE CAST(month AS integer) = 7`. |
| Cột trả về toàn giá trị **`NULL`** tại AI Audit | Query dạng phẳng top-level cũ (`SELECT tool_name...`). Log OTel thực tế được lồng trong `attributes`. | Sử dụng cú pháp lồng struct: `attributes.tool_name`, `attributes.surface`, `attributes.model_id`. |
| Cột `username`, `source_ip` bị **`NULL`** khi query EKS Authenticator | Log `authenticator` có định dạng Text Key-Value (logfmt), không phải JSON như `audit` log. | Dùng hàm `regexp_extract(raw_message, 'arn="([^"]+)"', 1)` để tách ARN và IP trực tiếp từ `raw_message`. |
| Lỗi **Double Gzip** khi đọc file S3 EKS cũ (trước 15/07) | Cấu hình Firehose cũ nén GZIP lần 2 trên payload đã nén GZIP của CloudWatch. | Toàn bộ dữ liệu mới từ ngày 15/07 đã được sửa tự động giải nén qua Lambda Processor và ghi dạng Plain JSON. |

---

## 📞 6. Phân Cấp Trách Nhiệm & Chuyển Tuyến (Escalation Path)

- **Đơn vị phụ trách chính**: Team **CDO07** (Auditability & Security Analytics).
- **Phản ứng sự cố an ninh**: Khi phát hiện thao tác bất thường qua Athena, trích xuất mã **Query ID** và danh tính ARN gửi sang nhóm SecOps / On-call Lead.
- **Quy trình Rollback IaC**: Nếu cấu hình Glue Table Schema trong Terraform bị lỗi, chạy:
  ```bash
  git checkout origin/main -- infra/terraform/athena-forensics.tf
  terraform apply -target=aws_glue_catalog_table.aws_config_history
  ```
