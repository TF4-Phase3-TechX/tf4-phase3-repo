# [REVIEW REQUEST] CDO04 - Cost/Capacity Review cho CDO08-REL-28 (MSK Orders Archive Firehose)

| Thông tin       | Giá trị                                                                                        |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Từ              | CDO08                                                                                          |
| Đến             | CDO04 (Cost/Capacity, MSK ownership)                                                           |
| Backlog ID      | `CDO08-REL-28`                                                                                 |
| Ngày gửi        | 2026-07-25                                                                                     |
| Mục tiêu review | Duyệt cost/capacity trước khi triển khai Firehose native MSK source cho archive topic `orders` |
| Trạng thái      | **Needs CDO04 Review**                                                                         |

---

## 1. Bối Cảnh & Yêu Cầu Review

CDO08-REL-22 subtask 3 ban đầu dùng AWS MSK Connect S3 Sink Connector để archive MSK topic `orders` ra S3. Hướng này đang bị block ở bước `CreateConnector`:

- IAM simulate cho thấy `kafkaconnect:CreateConnector`, `kafkaconnect:TagResource` và `iam:PassRole` đều `allowed`.
- Service-linked role `AWSServiceRoleForKafkaConnect` đã tồn tại.
- CloudTrail ghi nhận `CreateConnector` fail `AccessDenied` với cả GitHub Actions apply role và Admin/BreakGlass.
- CDO04 đã liên hệ AWS Support nhưng chưa có ETA gỡ restriction.
- Terraform đã gate connector bằng `msk_connect_connector_enabled=false` để CD apply xanh và giữ lại foundation resources.

Tech Lead đã chốt hướng thay thế chính thức cho REL-28 là **Kinesis Data Firehose native MSK source -> S3**. Self-managed Kafka Connect trên EKS giữ làm fallback chính thức nếu Firehose không được duyệt hoặc triển khai thực tế gặp blocker. Custom consumer không xét tiếp vì rủi ro tự xử lý offset/retry/replay cao hơn hai hướng còn lại.

Review request này gửi CDO04 để duyệt **cost/capacity** trước khi CDO08 được phép tạo PR Terraform bật IAM auth, Multi-VPC private connectivity và Firehose delivery stream.

---

## 2. Quyết Định Kỹ Thuật Đã Chốt

### 2.1 Hướng chính: Firehose native MSK source

Firehose sẽ đọc trực tiếp topic `orders` từ MSK và ghi xuống S3 archive bucket.

Yêu cầu giữ nguyên:

- Không public MSK.
- Không đổi app config.
- App hiện tại vẫn dùng `SASL/SCRAM`.
- Firehose dùng IAM path riêng để đọc MSK.
- S3 destination giữ đúng convention REL-22:

```text
Bucket: tf4-msk-orders-archive-511825856493-us-east-1
Prefix: orders/
Partition convention: orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
```

### 2.2 Điều kiện bắt buộc để Firehose đọc MSK private

Theo AWS docs, với MSK private source, Firehose cần:

- MSK cluster active.
- IAM access control enabled trên MSK.
- Multi-VPC private connectivity enabled cho IAM access method.
- Cluster resource policy cho phép Firehose service principal gọi `kafka:CreateVpcConnection`.

Runtime hiện tại đã verify:

```json
{
    "State": "ACTIVE",
    "ClientAuthentication": {
        "Sasl": {
            "Scram": {
                "Enabled": true
            },
            "Iam": {
                "Enabled": false
            }
        },
        "Unauthenticated": {
            "Enabled": false
        }
    },
    "ConnectivityInfo": null,
    "CurrentVersion": null
}
```

Diễn giải:

- Cluster đang `ACTIVE`.
- App path hiện tại đang dùng SCRAM.
- IAM auth chưa bật.
- Multi-VPC private connectivity chưa thấy trong output.

Vì vậy, để đi theo Firehose cần CDO04 duyệt việc bật IAM auth và Multi-VPC private connectivity trên MSK.

---

## 3. Vì Sao Chọn Firehose Dù Không Phải Phương Án Rẻ Nhất

| Phương án                           | Trạng thái                                     | Lý do                                                                                                                                               |
| ----------------------------------- | ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| AWS MSK Connect S3 Sink             | Không chọn làm hướng tiếp theo lúc này         | Đúng plan ban đầu và managed hơn self-managed, nhưng đang bị account/service-side restriction ở `CreateConnector`, không có ETA                     |
| Firehose native MSK source          | Hướng chính thức cần CDO04 duyệt cost/capacity | Managed service, không tạo pod trong EKS, không tự vận hành Kafka Connect worker, RPO có CloudWatch metric chuẩn để monitor                         |
| Self-managed Kafka Connect trên EKS | Fallback chính thức                            | Tận dụng được SCRAM hiện tại và Confluent S3 Sink chuẩn, nhưng phải tạo thêm pod/workload và tự vận hành image/plugin/resources/probes/consumer lag |
| Custom consumer                     | Loại khỏi hướng chính                          | Rủi ro tự xử lý offset, retry, DLQ, duplicate, schema và replay cao nhất                                                                            |

Firehose không phải phương án rẻ nhất nếu so với self-managed Kafka Connect dùng capacity EKS hiện có. Tuy nhiên Firehose giảm operational risk vì không tạo thêm runtime worker trong cluster, không cần quản lý Kafka Connect internal topics, không cần tự vận hành connector image/plugin và có metric `DeliveryToS3.DataFreshness` để kiểm soát RPO.

---

## 4. Cost Components Cần CDO04 Duyệt

Nguồn pricing chính thức:

- Firehose MSK as source ingestion: `0.055 USD/GB`.
- MSK Multi-VPC private connectivity fixed charge: `0.0225 USD/private-connectivity-hour/authentication scheme`.
- MSK Multi-VPC private connectivity data processing: `0.006 USD/GB`.

Giả định tính toán:

- Region: `us-east-1`.
- Authentication scheme cần bật cho Firehose: `IAM`.
- 1 tháng tính theo `730` giờ.
- Traffic thật của topic `orders` lấy từ CloudWatch metric `AWS/Kafka BytesInPerSec` với dimension `Topic=orders`.
- Bảng scenario vẫn được giữ để CDO04 duyệt capacity envelope nếu traffic tăng sau khi load-generator hoặc checkout flow chạy lại.

### 4.1 Traffic Thật Của Topic `orders`

Command kiểm tra metric:

```powershell
aws cloudwatch list-metrics `
  --region us-east-1 `
  --profile tf4 `
  --namespace AWS/Kafka `
  --metric-name BytesInPerSec `
  --dimensions Name=Topic,Value=orders `
  --query 'Metrics[*].{MetricName:MetricName,Dimensions:Dimensions}' `
  --output json
```

Kết quả: CloudWatch có topic-level metric `BytesInPerSec` cho `Topic=orders`.

Tính traffic 24h gần nhất:

```text
MetricSeries: 1
Datapoints: 224
WindowHours: 24
TotalBytes: 0
TotalMiB: 0
TotalGiB: 0
GBPerDayDecimal: 0
EstimatedFirehoseIngestPerDayUSD: 0
EstimatedMultiVpcDataPerDayUSD: 0
```

Tính traffic 7 ngày gần nhất:

```text
MetricSeries: 1
Datapoints: 93
WindowDays: 7
TotalBytes: 97,352,246.52
TotalMiB: 92.842
TotalGiB: 0.090666
AvgGBPerDayDecimal: 0.013907
MaxBytesInPerSec: 893,451.485
EstimatedMonthlyGBDecimal: 0.417224
EstimatedFirehoseIngestMonthlyUSD: 0.022947
EstimatedMultiVpcDataMonthlyUSD: 0.002503
EstimatedMultiVpcFixedMonthlyUSD: 16.425
EstimatedSubtotalMonthlyUSD: 16.45
```

Diễn giải:

- Traffic thật hiện tại của `orders` đang rất thấp.
- Với dữ liệu 7 ngày gần nhất, monthly estimate theo traffic thật khoảng `0.417 GB/tháng`.
- Cost theo usage gần như không đáng kể; fixed cost của MSK Multi-VPC private connectivity là phần chính.
- Estimate theo traffic thật hiện tại: khoảng **16.45 USD/tháng**, chưa gồm S3/log/KMS phụ phí.

### 4.2 Công thức

```text
Firehose ingest monthly cost
= OrdersArchiveGBPerMonth * 0.055

MSK Multi-VPC fixed monthly cost
= 730 hours * 0.0225 * 1 authentication scheme
= 16.425 USD/month

MSK Multi-VPC data processing monthly cost
= OrdersArchiveGBPerMonth * 0.006

Estimated monthly subtotal
= Firehose ingest + Multi-VPC fixed + Multi-VPC data processing
```

### 4.3 Scenario Estimate

| Traffic `orders`             | GB/tháng | Firehose ingest (`0.055/GB`) | Multi-VPC fixed | Multi-VPC data (`0.006/GB`) | Tổng ước tính/tháng |
| ---------------------------- | -------: | ---------------------------: | --------------: | --------------------------: | ------------------: |
| Traffic thật 7 ngày gần nhất | 0.417 GB |                     0.02 USD |       16.43 USD |                    0.00 USD |       **16.45 USD** |
| 1 GB/ngày                    |    30 GB |                     1.65 USD |       16.43 USD |                    0.18 USD |       **18.26 USD** |
| 5 GB/ngày                    |   150 GB |                     8.25 USD |       16.43 USD |                    0.90 USD |       **25.58 USD** |
| 10 GB/ngày                   |   300 GB |                    16.50 USD |       16.43 USD |                    1.80 USD |       **34.73 USD** |
| 50 GB/ngày                   | 1,500 GB |                    82.50 USD |       16.43 USD |                    9.00 USD |      **107.93 USD** |

Ghi chú:

- Bảng trên chưa gồm S3 storage, S3 request, lifecycle transition, CloudWatch logs/alarms, KMS nếu sau này đổi từ SSE-S3 sang SSE-KMS, và data transfer nếu phát sinh ngoài path dự kiến.
- Với traffic nhỏ, fixed cost Multi-VPC private connectivity là phần chi phí chính.
- Với traffic lớn, Firehose ingest mới trở thành phần chi phí chính.

### 4.4 So Sánh Với Hai Hướng Còn Lại

| Phương án                  | Cost estimate                                                                                               | Nhận xét                                                                              |
| -------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| AWS MSK Connect S3 Sink    | Khoảng `730h * 1 MCU * 0.11 USD/h = 80.30 USD/tháng`, chưa gồm S3/logs                                      | Đang bị block, không có ETA; cost cao hơn Firehose ở các scenario 1-10 GB/ngày        |
| Firehose native MSK source | Khoảng `16.45 USD/tháng` theo traffic thật 7 ngày gần nhất; khoảng `18.26-34.73 USD/tháng` với 1-10 GB/ngày | Có fixed cost Multi-VPC nhưng không tạo pod trong EKS                                 |
| Self-managed Kafka Connect | Nếu dùng capacity EKS hiện có thì marginal thấp; nếu scale thêm node cỡ `t3.medium` khoảng `30 USD/tháng`   | Có thể rẻ hơn Firehose trong một số scenario, nhưng tăng operational burden trong EKS |

---

## 5. Capacity / Runtime Impact

### 5.1 MSK

Thay đổi cần có:

- Bật IAM auth song song với SCRAM.
- Bật Multi-VPC private connectivity cho IAM.
- Thêm cluster resource policy cho Firehose.

Tech Lead đã xác nhận về mặt quyết định:

- MSK hỗ trợ dual-auth SCRAM + IAM.
- App hiện tại tiếp tục dùng SCRAM, không cần đổi config.
- Rolling broker update được chấp nhận nếu schedule ngoài giờ cao điểm và thông báo on-call trước.

CDO04 cần confirm:

- Cost/capacity cho Multi-VPC private connectivity.
- Có điều kiện bổ sung nào trước khi bật IAM/Multi-VPC trên MSK không.
- Có yêu cầu change window cụ thể không.

### 5.2 EKS

Firehose path không tạo thêm pod trong EKS.

So với self-managed Kafka Connect fallback, Firehose tránh được:

- Kafka Connect worker pod.
- Connector image/plugin lifecycle.
- Pod CPU/memory requests/limits.
- Pod restart/OOM/probe tuning.
- Kafka Connect internal topics.

### 5.3 S3

Destination tiếp tục dùng archive bucket đã provision ở REL-22:

```text
s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/
```

Yêu cầu giữ nguyên:

- Bucket private.
- Encryption enabled.
- Versioning enabled.
- Lifecycle theo ADR.
- Không cấp delete object/version cho normal operator.

---

## 6. RPO / Monitoring

RPO mục tiêu của orders archive là `<= 15 phút`.

Với Firehose, không dùng cách đo marker timestamp thủ công làm metric chính. Metric chính cần dùng là:

```text
DeliveryToS3.DataFreshness
```

Theo AWS docs, `DeliveryToS3.DataFreshness` thể hiện tuổi của record cũ nhất trong Firehose chưa được delivery xong tới S3. Firehose cũng khuyến nghị alarm khi metric freshness vượt buffering limit, tối đa 15 phút.

Acceptance monitor đề xuất:

- `DeliveryToS3.DataFreshness < 900 seconds`.
- `DeliveryToS3.Success` không tụt bất thường.
- Delivery errors/throttling không tăng.
- S3 object xuất hiện dưới prefix đã chốt.

---

## 7. Guardrail Và Rollback

Guardrail trước khi implement:

- Chưa tạo PR Terraform bật IAM/Multi-VPC/Firehose nếu CDO04 chưa duyệt bằng văn bản.
- Schedule ngoài giờ cao điểm.
- Thông báo on-call/team trước khi apply.
- Plan phải thể hiện không đổi app service config.
- Firehose destination không được public bucket hoặc mở quyền delete.

Rollback nếu Firehose triển khai lỗi:

- Revert PR Terraform tạo Firehose delivery stream/resource policy.
- Disable/delete Firehose delivery stream qua Terraform.
- Không xoá S3 archive object đã ghi.
- Không đổi SCRAM app path.
- Nếu IAM/Multi-VPC connectivity gây vấn đề, rollback theo plan MSK connectivity được CDO04 duyệt trước khi apply.

---

## 8. Quyết Định Cần CDO04 Xác Nhận

CDO04 vui lòng xác nhận trước khi CDO08 tạo task/PR implementation:

```text
CDO04 decision:
[ ] Approve Firehose native MSK source path với Multi-VPC private connectivity cost/capacity như trên.
[ ] Needs Info: cần traffic metric thật của topic orders trước khi approve.
[ ] Không approve Firehose lúc này, dùng self-managed Kafka Connect fallback.
[ ] Hướng khác: ______________________________

Ghi chú / điều kiện approve:
- Người duyệt:
- Ngày duyệt:
- Điều kiện:
- Change window yêu cầu:
```

CDO08 cần CDO04 xác nhận thêm:

- Có chấp nhận fixed cost khoảng `16.43 USD/tháng` cho Multi-VPC private connectivity IAM không.
- Có cần giới hạn traffic/cost alarm trước khi bật Firehose không.
- Có yêu cầu CDO04 review trực tiếp Terraform plan trước khi merge implementation không.

---

## 9. Final Summary

```md
Tech Lead đã chốt Firehose native MSK source là hướng chính thức để thay AWS MSK Connect S3 Sink đang bị block ở CreateConnector. Hướng này vẫn cần CDO04 duyệt cost/capacity vì Firehose private MSK source yêu cầu bật IAM auth và Multi-VPC private connectivity trên MSK.

Cost chính gồm Firehose ingest 0.055 USD/GB, MSK Multi-VPC private connectivity fixed 0.0225 USD/hour/auth scheme (~16.43 USD/month), và data processing 0.006 USD/GB. CloudWatch `AWS/Kafka BytesInPerSec` cho topic `orders` cho thấy 7 ngày gần nhất có khoảng 92.842 MiB, tương đương 0.417 GB/tháng nếu giữ cùng tốc độ, nên estimate theo traffic thật hiện tại khoảng 16.45 USD/tháng. Với scenario 1-10 GB/ngày, tổng estimate khoảng 18.26-34.73 USD/tháng, chưa gồm S3/log/KMS phụ phí. Firehose không phải phương án rẻ nhất trong mọi trường hợp, nhưng giảm operational risk vì không tạo pod Kafka Connect trong EKS và có CloudWatch metric DeliveryToS3.DataFreshness để monitor RPO <= 15 phút.

CDO08 chưa implement trong PR này. Sau khi CDO04 duyệt bằng văn bản, CDO08 mới tạo task/PR Terraform riêng để bật IAM auth, Multi-VPC private connectivity, cluster policy và Firehose delivery stream.
```

---

## 10. References

- AWS Firehose pricing - MSK as a source ingestion: https://aws.amazon.com/firehose/pricing/
- AWS MSK pricing - Multi-VPC private connectivity hourly/data processing charges: https://aws.amazon.com/msk/pricing/
- AWS Firehose MSK source documentation: https://docs.aws.amazon.com/firehose/latest/dev/writing-with-msk.html
- AWS Firehose access control for private MSK: https://docs.aws.amazon.com/firehose/latest/dev/controlling-access.html
- AWS Firehose CloudWatch metrics: https://docs.aws.amazon.com/firehose/latest/dev/monitoring-with-cloudwatch-metrics.html
- AWS Firehose CloudWatch alarm best practices: https://docs.aws.amazon.com/firehose/latest/dev/firehose-cloudwatch-metrics-best-practices.html
