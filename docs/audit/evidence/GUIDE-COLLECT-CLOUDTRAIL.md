# Hướng dẫn Thu thập Log Kiểm toán Di trú Dữ liệu (Mandate 08)

Tài liệu này hướng dẫn chi tiết cách thu thập bằng chứng kiểm toán (audit logs) từ cả AWS Console và Terminal (AWS CLI/kubectl) để phục vụ cho việc điền báo cáo tại file [MANDATE-08-CUTOVER-AUDIT-EVIDENCE.md](./MANDATE-08-CUTOVER-AUDIT-EVIDENCE.md).

---

## PHẦN 1: Thu thập Dòng thời gian Cutover (Timeline)

Chúng ta cần thu thập và chứng minh 3 mốc thời gian quan trọng của quá trình di trú:
1. **Mốc 1**: Thời điểm cấu hình flag `managedData.enabled=true`.
2. **Mốc 2**: Thời điểm dừng/xóa (terminate) các pod database self-hosted cũ.
3. **Mốc 3**: Thời điểm ứng dụng khởi chạy và kết nối sang các DB Managed (RDS, ElastiCache, MSK).

---

### Mốc 1: Thời điểm bật flag `managedData.enabled=true`

Vì toàn bộ cấu hình hạ tầng và ứng dụng được lưu vết trong Git (GitOps), cách chính xác nhất để lấy mốc này là kiểm tra lịch sử commit.

#### Cách 1: Sử dụng Terminal (Git CLI)
Chạy lệnh sau tại thư mục root của dự án để tìm commit thay đổi flag `managedData`:
```bash
git log -S "managedData" --oneline --format=fuller -n 5
```
* **Cách đọc kết quả:** Bạn sẽ tìm thấy commit hash (ví dụ: `05d39a9` cho Postgres, `352ac88` cho Valkey). Trường `CommitDate` chính là timestamp cần lấy.

#### Cách 2: Sử dụng AWS Console (CodeCommit)
1. Mở **AWS Console** ➔ **Developer Tools** ➔ **CodeCommit** ➔ **Repositories**.
2. Chọn repository `tf4-phase3-repo`.
3. Vào mục **Commits** để tìm commit/PR đã merge thay đổi flag này lên nhánh `main`.
4. Ghi lại timestamp và chụp màn hình trang chi tiết commit.

---

### Mốc 2: Thời điểm terminate Pod DB cũ (`postgresql`, `valkey-cart`, `kafka`)

Khi flag di trú được bật và đồng bộ, cụm EKS sẽ gửi tín hiệu `DELETE` để tắt các pod cũ. Do các event ngắn hạn của K8s nhanh bị xóa, ta dùng log audit của EKS lưu tại CloudWatch.

#### Cách 1: Sử dụng AWS Console (CloudWatch Logs Insights - Khuyên Dùng)
1. Mở **AWS Console** ➔ **CloudWatch** ➔ **Log groups**.
2. Chọn Log Group `/aws/eks/techx-tf4-cluster/cluster` (hoặc log group tương ứng với cụm EKS của bạn).
3. Click nút **Start Query** ở góc phải (để chuyển qua giao diện Insights).
4. Chọn khoảng thời gian diễn ra cutover (ví dụ: ngày 2026-07-21).
5. Paste câu truy vấn rút gọn dưới đây (sử dụng chuỗi ký tự đơn giản thay vì regex phức tạp để tránh lỗi gõ sai chính tả hoặc lỗi ký tự escape) và nhấn **Run query**:
   ```sql
   fields @timestamp, verb, requestURI, objectRef.name
   | filter @logStream like "kube-apiserver-audit"
   | filter objectRef.resource = "pods"
   | filter objectRef.namespace = "techx-tf4"
   | filter verb = "delete"
   | filter objectRef.name like "postgresql" or objectRef.name like "valkey" or objectRef.name like "kafka"
   | sort @timestamp desc
   | limit 20
   ```
6. Ghi nhận thời gian `@timestamp` khi các pod nhận lệnh `DELETE` và chụp màn hình bảng kết quả query.

#### Cách 2: Sử dụng Terminal (AWS CLI + jq)
Chạy lệnh sau để truy vấn qua CLI (sử dụng Unix epoch timestamp cho start/end time tương ứng ngày di trú):
```bash
aws logs start-query \
  --log-group-name "/aws/eks/techx-tf4-cluster/cluster" \
  --start-time 1784563200 \
  --end-time 1784649600 \
  --query-string 'fields @timestamp, @message | filter @logStream like "kube-apiserver-audit" | filter @message like "namespaces/techx-tf4/pods" | filter @message like "DELETE" | filter @message like "postgresql" or @message like "valkey" or @message like "kafka" | sort @timestamp desc | limit 20' \
  --region us-east-1
```
Lấy kết quả bằng lệnh:
```bash
aws logs get-query-results --query-id <QUERY_ID_TỪ_LỆNH_TRÊN> --region us-east-1
```

---

### Mốc 3: Thời điểm ứng dụng kết nối sang RDS/ElastiCache/MSK

Khi pod mới khởi chạy, chúng sẽ truy cập AWS Secrets Manager để lấy thông tin kết nối. Lịch sử này được CloudTrail ghi nhận qua sự kiện API `GetSecretValue`.

#### Cách 1: Sử dụng Terminal (AWS CLI - Nhanh nhất)
Chạy lệnh sau để tìm kiếm các sự kiện gọi Secrets Manager liên quan đến `techx/tf4`:
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue \
  --region us-east-1 \
  --query "Events[?contains(CloudTrailEvent, 'techx/tf4')].{Time:EventTime,Username:Username,SecretName:Resources[0].ResourceName}" \
  --output table
```
* **Cách đọc kết quả:** Cột `Time` chính là mốc thời gian ứng dụng bắt đầu kéo secret để kết nối cơ sở dữ liệu mới.

#### Cách 2: Sử dụng AWS Console (CloudTrail Event History)
1. Mở **AWS Console** ➔ **CloudTrail** ➔ **Event history**.
2. Chọn filter **Lookup attributes**: `Event name` = `GetSecretValue`.
3. Lọc thêm theo **Event source** = `secretsmanager.amazonaws.com` nếu danh sách quá dài.
4. Tìm các sự kiện có **Resource name** khớp với secret của bạn (ví dụ: `techx/tf4/rds-postgres`).
5. Ghi lại trường `eventTime` ở tab chi tiết và chụp màn hình sự kiện này.

---

## PHẦN 2: Chứng minh Nhật ký Kiểm toán là Tamper-Evident (Chống sửa/xóa)

Để đáp ứng tiêu chuẩn an toàn kiểm toán, bạn cần chứng minh CloudTrail log được bảo mật toàn vẹn tuyệt đối qua 3 cơ chế.

---

### Cơ chế 1: Xác thực tính toàn vẹn của Log (Log File Validation)

CloudTrail tự động tính toán hash SHA-256 kèm chữ ký số RSA cho log file. Lệnh `validate-logs` sẽ kiểm tra lại tính toàn vẹn của log.

#### Cách 1: Sử dụng Terminal (AWS CLI)
Chạy lệnh sau để xác thực toàn bộ log file trong khoảng thời gian cutover:
```bash
aws cloudtrail validate-logs \
  --trail-arn arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail \
  --start-time 2026-07-21T00:00:00Z \
  --end-time 2026-07-22T10:00:00Z \
  --region us-east-1
```
* **Kết quả hợp lệ:** Lệnh phải hiển thị `100% of log files verified` và `0 modified/deleted log files detected`. Copy output này dán trực tiếp vào báo cáo.

#### Cách 2: Sử dụng AWS Console
1. Vào **CloudTrail** ➔ **Trails** ➔ click `tf4-general-cloudtrail`.
2. Kiểm tra phần **General details** và tìm dòng **Log file validation**.
3. Xác nhận nó đang hiển thị trạng thái **Enabled** và chụp màn hình lại.

---

### Cơ chế 2: Kiểm tra Object Lock Compliance Mode (WORM) trên S3

Nhật ký kiểm toán lưu trữ trên S3 bucket được bảo vệ bằng Object Lock chế độ `COMPLIANCE`. Ở chế độ này, tệp tin không thể bị sửa đổi hay xóa bởi bất kỳ ai (kể cả root account) trong suốt thời gian retention (90 ngày).

#### Cách 1: Sử dụng Terminal (AWS CLI)
Chạy lệnh lấy cấu hình Object Lock của bucket:
```bash
aws s3api get-object-lock-configuration \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --region us-east-1
```
* **Kết quả hợp lệ:** Trả về JSON có trường `"ObjectLockEnabled": "Enabled"` và `"Mode": "COMPLIANCE"`.

#### Cách 2: Sử dụng AWS Console
1. Truy cập **AWS Console** ➔ **S3** ➔ click bucket `tf4-cloudtrail-logs-bucket-511825856493`.
2. Chọn tab **Properties** ➔ Cuộn xuống mục **Object Lock**.
3. Xác nhận Object Lock đang ở trạng thái **Enabled**, mode **COMPLIANCE**, retention **90 days**. Chụp màn hình để đính kèm báo cáo.

---

### Cơ chế 3: Kiểm thử Tamper Test (Separation of Duties)

Chúng ta có Bucket Policy chặn tuyệt đối quyền xóa object của người dùng/operator.

#### Bước 1: Đọc chính sách Bucket Policy bằng CLI
```bash
aws s3api get-bucket-policy \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --region us-east-1 \
  --query Policy --output text | jq '.Statement[] | select(.Sid=="DenyNonAdminDeleteObject")'
```
* **Kết quả hợp lệ:** Trả về khối JSON chứa `Effect: Deny` cho hành động `s3:DeleteObject` và `s3:DeleteObjectVersion`.

#### Bước 2: Chạy thử nghiệm xóa log (Tamper Test)
Thử thực hiện lệnh xóa một file log bất kỳ trong bucket bằng quyền developer/operator của bạn:
```bash
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/ap-northeast-1/2026/07/22/511825856493_CloudTrail_ap-northeast-1_20260722T0345Z_ctgew0ArMfpQQTse.json.gz\
  --region us-east-1
```
* **Kết quả hợp lệ:** Terminal trả về lỗi:
  `An error occurred (AccessDenied) when calling the DeleteObject operation: Access Denied`
  Copy dòng thông báo lỗi này để làm bằng chứng thực nghiệm cho báo cáo.
