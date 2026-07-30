# Hướng dẫn Tìm hiểu và Kiểm chứng Hệ thống Audit Log Athena

Tài liệu này được biên soạn dành riêng cho nhóm CDO07 (Audit & Forensic Analytics) để làm cơ sở nghiên cứu và tự thực thi kiểm thử hệ thống log tập trung trên Amazon Athena.

---

# Phần 1: Tài liệu Tìm hiểu Chi tiết (Research Guide)

Để thực thi và đánh giá hệ thống audit log tập trung qua Amazon Athena, bạn cần nắm vững 5 khối kiến thức nền tảng sau:

### 1. Kiến trúc Schema-on-Read và Glue Data Catalog
* Khái niệm: Amazon Athena là một dịch vụ truy vấn serverless hoạt động theo cơ chế Schema-on-Read (áp cấu trúc khi đọc). Nó không lưu trữ dữ liệu. Dữ liệu thực tế là các file raw log (dạng JSON hoặc nén GZIP) nằm trên các S3 WORM Buckets.
* AWS Glue Data Catalog: Đóng vai trò như một cơ sở dữ liệu metadata. Glue định nghĩa tên bảng, kiểu dữ liệu của các cột và ánh xạ chúng tới đường dẫn S3 tương ứng.
* Cách hoạt động: Khi bạn chạy lệnh SELECT * FROM table, Athena sẽ gửi yêu cầu đến Glue Catalog để lấy schema, sau đó quét các file trên S3, parse nội dung theo schema đó rồi hiển thị lên màn hình dưới dạng bảng SQL. Nếu cấu trúc file JSON thay đổi hoặc bị lệch so với Glue schema, kết quả trả về sẽ bị NULL hoặc báo lỗi.

### 2. Phân vùng dữ liệu (Partition Projection) và Hạn mức Chi phí
* Tại sao cần Partition Projection?
  Nếu không phân vùng, mỗi khi truy vấn, Athena sẽ phải quét qua toàn bộ dữ liệu trong S3 bucket (có thể lên tới hàng TB hoặc PB), gây tốn chi phí cực lớn và thời gian truy vấn rất chậm.
  Partition Projection là cơ chế định nghĩa trước quy luật phân vùng thời gian (năm/tháng/ngày/giờ) cho Athena. Thay vì quét S3 để tìm partition, Athena sẽ tự động tính toán đường dẫn folder S3 dựa trên biểu thức và chỉ quét đúng folder đó.
* Quy tắc tính phí: AWS Athena tính phí $5.00 trên mỗi 1 TB dữ liệu quét.
* Hạn mức bảo vệ (Guardrail): Workgroup tf4-audit-forensics cấu hình bytes_scanned_cutoff_per_query = 10 GB (~ $0.05). Nếu query quét quá 10 GB, Athena sẽ tự động cancel. Do đó, bạn bắt buộc phải lọc theo thời gian (year, month, day) để giới hạn dung lượng quét thường dưới 500 MB.

### 3. Cấu trúc Schema OTLP JSON Envelope và Struct Lồng
* OTLP JSON Envelope: Log ứng dụng và log cuộc gọi AI (Mandate 14) được OpenTelemetry đóng gói thành định dạng Envelope chuẩn hóa. Các trường metadata chung nằm ở ngoài, còn các trường nghiệp vụ cụ thể được bọc gọn trong một đối tượng JSON (struct) tên là attributes.
* Cú pháp truy cập: Để lấy dữ liệu bên trong struct này, trong Athena SQL bạn sử dụng cú pháp dấu chấm: attributes.field_name (ví dụ: attributes.tool_name, attributes.safety_decision). Nếu bạn dùng cú pháp phẳng cũ (ví dụ: SELECT tool_name), query sẽ báo lỗi hoặc trả về NULL.

### 4. Kỹ thuật CROSS JOIN UNNEST cho Dữ liệu Dạng Array (AWS Config)
* Thách thức: AWS Config lưu log lịch sử thay đổi tài nguyên dưới dạng một đối tượng JSON lớn chứa một mảng các sự kiện thay đổi: {"configurationItems": [...]}. 
* Giải pháp: Trong SQL tiêu chuẩn, bạn không thể lọc trực tiếp các trường bên trong mảng JSON. Ta sử dụng cú pháp CROSS JOIN UNNEST(configurationitems) AS t(ci) để "trải phẳng" (flatten) từng item trong mảng thành các dòng riêng biệt. Sau đó, ta truy cập thuộc tính qua alias ci (ví dụ: ci.resourcetype, ci.configurationitemstatus).
* Lưu ý đặc biệt: Thư mục lưu log của AWS Config trên S3 đặt tên tháng không có số 0 ở đầu cho các tháng nhỏ hơn 10 (ví dụ: month=7 thay vì month=07). Do đó mệnh đề WHERE của bảng aws_config_history bắt buộc dùng month = '7'.

### 5. regexp_extract và Logfmt parsing (EKS Authenticator)
* Thách thức: Khác với log API server là dạng JSON, EKS Authenticator Log (log ghi nhận ai authenticate vào cụm) được ghi dưới dạng văn bản phẳng Key-Value ngăn cách bởi khoảng trắng (logfmt), ví dụ: arn="arn:aws:iam::..." client="127.0.0.1" msg="access granted".
* Giải pháp: Ta sử dụng hàm regexp_extract(raw_message, 'key="([^"]+)"', 1) để bóc tách giá trị tương ứng của key đó từ chuỗi text thô raw_message thành các cột hiển thị đẹp mắt trên Athena.

---

# Phần 2: Hướng dẫn Tự kiểm chứng (Verification Tutorial)

Môi trường kiểm thử:
* Database: tf4_audit_forensics
* Workgroup: tf4-audit-forensics
* Thời gian test mẫu: Ngày 29 tháng 07 năm 2026 (Tháng AWS Config dùng '7')
* AWS Profile sử dụng: cdo07-tf4-auditreadonly

---

## TC-ATHENA-01: OTLP Envelope Mapping Check

### 1. Mục tiêu
Xác nhận bảng log gọi AI (ai_tool_audit_events) ánh xạ đúng cấu trúc OTLP, truy vấn các trường lồng trong attributes.* hiển thị đúng giá trị chuỗi, hoàn toàn không bị lỗi Schema Mismatch trả về NULL.

### 2. Cách thực hiện
1. Truy cập dịch vụ Amazon Athena trên AWS Console.
2. Đảm bảo góc trên bên phải đã chọn Workgroup tf4-audit-forensics.
3. Chọn database tf4_audit_forensics ở menu bên trái.
4. Chạy câu lệnh SQL sau:
```sql
SELECT 
  trace_id,
  attributes.surface AS surface,
  attributes.model_id AS model_id,
  attributes.tool_name AS tool_name,
  attributes.safety_decision AS safety_decision
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '2026' AND month = '07' AND day = '29'
LIMIT 10;
```

### 3. Kết quả mong muốn (Desired Outcome)
* Query chạy thành công (Status: SUCCEEDED).
* Kết quả trả về danh sách 10 dòng dữ liệu.
* Các cột surface, model_id, tool_name, safety_decision hiển thị giá trị chuỗi rõ ràng (ví dụ: product-reviews, gemini-pro, verify-image, ALLOW), không có trường nào bị NULL.

---

## TC-ATHENA-02: AI Redaction và PII Safety Verification

### 1. Mục tiêu
Chứng minh hệ thống tuân thủ Mandate 14 (AI Redaction): không lộ lọt dữ liệu nhạy cảm hoặc PII trong log gọi AI. Quét toàn bộ log để tìm xem có trường hợp nào vi phạm chính sách bảo vệ dữ liệu hay không.

### 2. Cách thực hiện
Chạy câu lệnh SQL quét toàn bộ sự kiện của ngày test để tìm các dòng log vi phạm (chưa che hoặc ghi log nội dung thô):
```sql
SELECT 
  trace_id, 
  attributes.tool_name AS tool_name, 
  attributes.tool_input_redacted.redacted AS is_redacted,
  attributes.tool_input_redacted.content_logged AS content_logged
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '2026' AND month = '07' AND day = '29'
  AND (attributes.tool_input_redacted.redacted = false 
       OR attributes.tool_input_redacted.content_logged = true);
```

### 3. Kết quả mong muốn (Desired Outcome)
* Athena trả về 0 dòng dữ liệu (No results / 0 rows).
* Kết quả này chứng minh 100% dữ liệu cuộc gọi AI đều đã được che chắn (redacted = true) và không ghi lại nội dung thô (content_logged = false).

---

## TC-ATHENA-03: Partition Projection và Cost Cutoff Validation

### 1. Mục tiêu
Xác minh cơ chế phân vùng tự động (Partition Projection) hoạt động chuẩn xác giúp tối ưu hóa chi phí và đảm bảo dung lượng quét thấp hơn giới hạn cảnh báo an toàn (< 500 MB).

### 2. Cách thực hiện
1. Thực hiện câu lệnh SQL đếm tổng số sự kiện trong ngày:
```sql
SELECT COUNT(*) AS total_events
FROM tf4_audit_forensics.ai_tool_audit_events
WHERE year = '2026' AND month = '07' AND day = '29';
```
2. Sau khi query chạy xong, quan sát tab Query metrics hoặc góc dưới bên phải màn hình kết quả query trên Athena Console.
3. Tìm thông số "Data scanned" (hoặc dung lượng dữ liệu quét).

### 3. Kết quả mong muốn (Desired Outcome)
* Athena hiển thị tổng số dòng đếm được.
* Dung lượng Data scanned hiển thị nhỏ hơn 500 MB (Ví dụ thực tế thường chỉ từ vài KB đến vài MB tùy thuộc dung lượng file log nén trên S3 trong ngày đó), chứng minh Athena chỉ quét đúng thư mục ngày 29/07/2026 chứ không quét toàn bộ S3 bucket.

---

## TC-ATHENA-04: CloudTrail Infrastructure Forensic Query

### 1. Mục tiêu
Truy vết vết dầu loang (Forensic) trên hạ tầng AWS: xác định các hành vi ghi/xóa tài nguyên bất thường hoặc các lỗi truy cập trái phép bị từ chối (AccessDenied).

### 2. Cách thực hiện
Chạy SQL truy vết các hành động ghi/xóa hạ tầng hoặc các lỗi bảo mật xảy ra trong ngày:
```sql
SELECT 
  eventtime,
  useridentity.arn AS principal_arn,
  eventsource,
  eventname,
  sourceipaddress,
  errorcode,
  errormessage
FROM tf4_audit_forensics.cloudtrail_events
WHERE year = '2026' AND month = '07' AND day = '29'
  AND readonly = 'false'  -- Lọc các thao tác ghi/xóa thay đổi tài nguyên
  AND (errorcode IS NOT NULL OR eventname LIKE '%Delete%' OR eventname LIKE '%Remove%')
ORDER BY eventtime DESC
LIMIT 15;
```

### 3. Kết quả mong muốn (Desired Outcome)
* Trả về bảng danh sách các hành vi sửa/xóa tài nguyên.
* Cột principal_arn chỉ ra chính xác danh tính người thực hiện (IAM User/Role cụ thể, ví dụ: arn:aws:sts::511825856493:assumed-role/.../hoang.nguyenduy).
* Nếu có lỗi bảo mật, hiển thị rõ mã lỗi ví dụ AccessDenied và thông báo đi kèm tại cột errormessage cùng với IP nguồn tại sourceipaddress.

---

## TC-ATHENA-05: AWS Config và EKS Audit Reconstruction

### 1. Mục tiêu
Tái dựng lịch sử thay đổi tài nguyên hạ tầng AWS (Resource Timeline) và truy vết các hành vi sửa đổi tài nguyên Kubernetes (Pod, Deployment, Service, Configmap) cùng danh tính đăng nhập cụ thể qua IAM.

### 2. Cách thực hiện
 
#### Bước A: Dựng timeline xóa tài nguyên AWS (AWS Config)
Chạy câu lệnh SQL trải phẳng dữ liệu để lọc ra các tài nguyên vừa bị xóa:
```sql
SELECT 
  ci.awsregion AS region,
  ci.resourcetype AS resource_type,
  ci.resourceid AS resource_id,
  ci.resourcename AS resource_name,
  ci.configurationitemstatus AS status,
  ci.configurationitemcapturetime AS capture_time
FROM tf4_audit_forensics.aws_config_history
CROSS JOIN UNNEST(configurationitems) AS t(ci)
WHERE year = '2026' AND month = '7'  -- Bắt buộc tháng là '7'
  AND day = '29'
  AND ci.configurationitemstatus = 'ResourceDeleted'
ORDER BY ci.configurationitemcapturetime DESC
LIMIT 15;
```

#### Bước B: Truy vết thao tác thay đổi Kubernetes (EKS Audit Logs)
Chạy SQL tìm các thao tác làm thay đổi cụm K8s (create, update, delete, patch):
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
LIMIT 10;
```

#### Bước C: Phân tích danh tính đăng nhập IAM vào K8s (EKS Authenticator)
Chạy SQL phân tích các bản ghi đăng nhập để trích xuất IAM Role và Client IP từ log dạng Key-Value:
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

### 3. Kết quả mong muốn (Desired Outcome)
* Đối với AWS Config: Trả về danh sách tài nguyên bị xóa, chỉ rõ loại tài nguyên (ví dụ: AWS::EC2::SecurityGroup, AWS::EC2::Subnet) và thời điểm Config ghi nhận.
* Đối với EKS API: Trả về danh sách các thao tác làm thay đổi K8s, hiển thị rõ username (ví dụ: arn:aws:iam::...:role/ops-admin), hành động (verb), namespace và mã HTTP (ví dụ: 200, 201).
* Đối với EKS Authenticator: Trả về dữ liệu trích xuất thành công: cột iam_arn chứa ARN của IAM User/Role đăng nhập cụ thể, client_ip chứa IP của máy client, và status_msg hiển thị access granted hoặc lý do bị từ chối. Không bị lỗi parse thành NULL.
