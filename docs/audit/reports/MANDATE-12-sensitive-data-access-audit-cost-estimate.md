# MANDATE-12 - Ước Tính Chi Phí Sensitive Data Access Audit

Ngày lập: 2026-07-18  
Phạm vi tài khoản: TF4 account `511825856493`, mặc định tại region `us-east-1`.  
Phạm vi task: bịt lỗ hổng "Làm hụt" cho audit truy cập dữ liệu nhạy cảm theo Task 42.

## 1. Phạm Vi Đã Triển Khai / Đã Xác Minh

### S3 CloudTrail data event selectors mới

Terraform change của task này chỉ bật CloudTrail S3 object-level data events trên các prefix dưới đây:

| Prefix | Event được ghi nhận |
|---|---|
| `arn:aws:s3:::tf4-aws-config-worm-archive-511825856493-us-east-1/aws-config/` | `GetObject`, `DeleteObject` |
| `arn:aws:s3:::tf4-aws-config-staging-511825856493-us-east-1/aws-config/` | `GetObject`, `DeleteObject` |
| `arn:aws:s3:::tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/` | `GetObject`, `DeleteObject` |
| `arn:aws:s3:::tf4-eks-audit-logs-511825856493/2026/` | `GetObject`, `DeleteObject` |
| `arn:aws:s3:::tf4-phase3-state-bucket-511825856493/eks/` | `GetObject`, `PutObject`, `DeleteObject` |

Lý do scope như trên:

- Các bucket/prefix log và evidence chỉ bật read/delete audit để tránh ghi nhận hàng loạt service write như CloudTrail, Firehose, AWS Config.
- Prefix Terraform state là dữ liệu nhạy cảm và tần suất ghi thấp, nên bật đủ 3 thao tác `GetObject`, `PutObject`, `DeleteObject`.
- Không bật data events toàn account hoặc toàn bucket, nhằm kiểm soát chi phí.

### Secrets Manager và KMS

Task này không cần tạo thêm hạ tầng cho Secrets Manager hoặc KMS.

Bằng chứng runtime đã xác minh:

- Secrets Manager `GetSecretValue` đã được CloudTrail ghi nhận dưới dạng management event.
- KMS `Decrypt`, `GenerateDataKey`, và `GenerateDataKeyWithoutPlaintext` đã được CloudTrail ghi nhận dưới dạng management event.

Vì vậy chi phí phát sinh thêm của task này tập trung vào S3 data events mới. Secrets Manager và KMS được tính là `0 USD` chi phí phát sinh thêm cho task này.

## 2. Nguồn Giá Và Công Thức Chính Thức

| Hạng mục chi phí | Giá / quy tắc sử dụng trong ước tính | Nguồn chính thức |
|---|---:|---|
| CloudTrail S3 data events delivered to S3 | `$0.10 / 100,000 data events delivered` | AWS CloudTrail Pricing: https://aws.amazon.com/cloudtrail/pricing/ |
| CloudTrail management events first copy delivered to S3 | Bản ghi management events đầu tiên được deliver vào S3 là miễn phí; bản copy bổ sung sẽ tính phí | AWS CloudTrail Pricing: https://aws.amazon.com/cloudtrail/pricing/ |
| CloudTrail data events | Data events không được log mặc định; S3 object-level API gồm `GetObject`, `DeleteObject`, `PutObject`; có tính phí bổ sung | AWS CloudTrail data events docs: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html |
| CloudTrail events delivered to CloudWatch Logs group | `$0.25 / GB events delivered` | AWS CloudTrail Pricing: https://aws.amazon.com/cloudtrail/pricing/ |
| Usage type để kiểm tra CloudTrail data event trong Cost Explorer | `<region>-DataEventsRecorded` | AWS CloudTrail cost docs: https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-costs.html |
| Amazon S3 Standard storage, US East example | `$0.023 / GB-month` | Amazon S3 Pricing: https://aws.amazon.com/s3/pricing/ |
| Amazon S3 Standard requests, US East example | `GET $0.0004 / 1,000`; `PUT/COPY/POST/LIST $0.005 / 1,000` | Amazon S3 Pricing: https://aws.amazon.com/s3/pricing/ |
| AWS KMS requests | Free tier 20,000 requests/month; symmetric requests example `$0.03 / 10,000 requests`; KMS key `$1 / month` | AWS KMS Pricing: https://aws.amazon.com/kms/pricing/ |
| KMS CloudTrail logging | KMS API calls có thể được ghi nhận trong CloudTrail | AWS KMS Pricing: https://aws.amazon.com/kms/pricing/ và KMS CloudTrail docs: https://docs.aws.amazon.com/kms/latest/developerguide/logging-using-cloudtrail.html |

Lưu ý: giá AWS có thể thay đổi theo region và thời điểm. Khi lập ngân sách chính thức, nên kiểm tra lại bằng AWS Pricing Calculator hoặc AWS pricing page tại thời điểm triển khai.

## 3. Công Thức Tính Chi Phí

### Phí CloudTrail S3 data events

```text
CloudTrailDataEventCost =
  S3DataEventsRecordedPerMonth / 100,000 * 0.10 USD
```

Trong đó `S3DataEventsRecordedPerMonth` là tổng số object-level events match các prefix đã scope:

```text
GetObject + DeleteObject cho log/evidence prefixes
GetObject + PutObject + DeleteObject cho Terraform state prefix
```

### Phí CloudTrail deliver events vào CloudWatch Logs

Trail hiện tại có deliver event vào CloudWatch Logs. Nếu S3 data events mới cũng được deliver vào log group này, ước tính thêm:

```text
CloudTrailToCloudWatchLogsDeliveryCost =
  AdditionalCloudTrailEventGBPerMonth * 0.25 USD
```

Kích thước CloudTrail event không cố định. Để ước tính bảo thủ, file này dùng giả định `3 KB/event`:

```text
AdditionalCloudTrailEventGBPerMonth =
  S3DataEventsRecordedPerMonth * 3 KB / 1,073,741,824
```

### Phí S3 storage cho log CloudTrail phát sinh thêm

CloudTrail sẽ ghi thêm các data event này vào S3 log bucket.

```text
AdditionalS3StorageCost =
  AdditionalCloudTrailEventGBPerMonth * 0.023 USD
```

Phí S3 request do CloudTrail ghi log được kỳ vọng rất nhỏ vì CloudTrail gom batch events thành log objects. File này không model S3 request cost theo từng data event.

### Chi phí phát sinh thêm của KMS và Secrets Manager

```text
IncrementalKmsSecretsCost = 0 USD
```

Lý do:

- Task này không tạo KMS key mới.
- Task này không làm tăng KMS API usage của workload.
- Task này không làm tăng Secrets Manager API usage của workload.
- Task này chỉ xác minh CloudTrail management event logging hiện có đã capture KMS và Secrets Manager access.

KMS request charge vẫn có thể tồn tại trong baseline workload hiện tại, nhưng đó không phải chi phí phát sinh từ task này.

## 4. Bảng Ước Tính Theo Tháng

Giả định: mỗi CloudTrail event phát sinh thêm có kích thước trung bình `3 KB/event`.

| Kịch bản | S3 data events/tháng | Phí CloudTrail data event | Phí deliver vào CloudWatch Logs | Phí S3 storage thêm | KMS/Secrets phát sinh thêm | Tổng tiền/tháng |
|---|---:|---:|---:|---:|---:|---:|
| Acceptance-only drill | 100 | `$0.0001` | `<$0.0001` | `<$0.0001` | `$0.0000` | `~$0.0002` |
| Normal audit usage | 10,000 | `$0.0100` | `~$0.0070` | `~$0.0006` | `$0.0000` | `~$0.0176` |
| Heavy forensic month | 100,000 | `$0.1000` | `~$0.0698` | `~$0.0064` | `$0.0000` | `~$0.1762` |
| Very heavy review | 1,000,000 | `$1.0000` | `~$0.6985` | `~$0.0643` | `$0.0000` | `~$1.7628` |

Ví dụ tính với `100,000` events/tháng:

```text
CloudTrail data events = 100,000 / 100,000 * $0.10 = $0.10
Additional GB = 100,000 * 3 KB / 1,073,741,824 = ~0.2794 GB
CloudWatch Logs delivery = 0.2794 * $0.25 = ~$0.0698
S3 storage = 0.2794 * $0.023 = ~$0.0064/month
KMS/Secrets incremental = $0.0000
Tổng tiền/tháng = ~$0.1762
```

## 5. Phân Tích Rủi Ro Chi Phí

### Điểm giúp giữ chi phí thấp

- Selector chỉ scope vào 5 prefix cụ thể, không bật toàn bộ S3 account.
- Các prefix log/evidence không bật `PutObject`, tránh log các service-generated writes từ CloudTrail, Firehose, AWS Config.
- Prefix Terraform state có bật `PutObject`, nhưng tần suất ghi state thấp.
- Secrets Manager và KMS không cần selector/alert mới trong scope task hiện tại.

### Rủi ro chi phí chính

Rủi ro lớn nhất là vô tình bật scope quá rộng, ví dụ:

```text
arn:aws:s3:::*
arn:aws:s3:::tf4-cloudtrail-logs-bucket-511825856493/
arn:aws:s3:::tf4-eks-audit-logs-511825856493/
```

Hoặc bật `PutObject` trên các prefix nhận log delivery. Khi đó các service write có thể tạo thêm lượng data events lớn và làm tăng chi phí.

### Chi phí query evidence

CloudWatch Logs Insights query có thể phát sinh query scan cost theo CloudWatch Logs pricing. Đây không phải chi phí chạy thường trực của CloudTrail selector; nó chỉ phát sinh khi operator chạy truy vấn evidence. Nên giới hạn query window, ví dụ 15-60 phút quanh thời điểm drill.

## 6. Khuyến Nghị Kiểm Soát Chi Phí

1. Giữ nguyên S3 selectors theo đúng prefix ở mục 1.
2. Không thêm `PutObject` cho CloudTrail, EKS audit, hoặc AWS Config log/evidence prefixes trừ khi mentor yêu cầu audit write delivery.
3. Khi query evidence bằng CloudWatch Logs Insights, dùng khoảng thời gian ngắn.
4. Sau khi deploy, kiểm tra Cost Explorer với CloudTrail usage type:

```text
<region>-DataEventsRecorded
```

5. Theo dõi CloudWatch Logs delivery volume nếu S3 data events được deliver vào `/aws/cloudtrail/tf4-general-cloudtrail`.

## 7. Kết Luận

Chi phí phát sinh hàng tháng của task này dự kiến rất thấp nếu giữ đúng targeted scope:

```text
Normal audit usage: <$0.02/tháng
Heavy forensic month: ~$0.18/tháng với 100,000 S3 data events
Very heavy review: ~$1.76/tháng với 1,000,000 S3 data events
```

Ước tính này có tính bảo thủ cho CloudWatch Logs delivery vì giả định mỗi S3 data event phát sinh thêm đều được deliver vào CloudWatch Logs group và mỗi event có kích thước `3 KB`.
