# [REVIEW REQUEST] CDO04 - Cost Review cho CDO08-REL-28

| Thông tin     | Giá trị                                                      |
| ------------- | ------------------------------------------------------------ |
| Từ            | CDO08                                                        |
| Đến           | CDO04 (Cost/Infra)                                           |
| Backlog       | `CDO08-REL-28` - MSK Orders Archive (Firehose)               |
| Ngày gửi      | 2026-07-25                                                   |
| Deadline      | \_\_\_, trước khi implement Terraform (IAM auth + Multi-VPC) |
| Review result | \_\_\_                                                       |

## 1. Thay Đổi Đề Xuất

Mandate 20 yêu cầu archive MSK topic `orders` ra S3, RPO <= 15 phút, thay AWS MSK Connect S3 Sink đang bị block ở `CreateConnector`.

Tech Lead đã chọn Kinesis Data Firehose native MSK source. Cần bật trên MSK:

- IAM access control song song với SASL/SCRAM hiện tại (dual-auth).
- Multi-VPC private connectivity cho IAM access method.
- Cluster resource policy cho Firehose service principal.

Không đổi app config hiện tại. `checkout`, `accounting` và `fraud-detection` vẫn dùng SCRAM qua secret hiện có.

## 2. Cost Assumptions

| Assumption                                       |                                                 Giá dùng để tính |
| ------------------------------------------------ | ---------------------------------------------------------------: |
| Firehose ingest (MSK-as-source)                  | `$0.055/GB` tier đầu, tính theo `max(ingested, delivered bytes)` |
| Multi-VPC private connectivity - phí cố định     |                `$0.0225/connectivity-hour/authentication scheme` |
| Multi-VPC private connectivity - data processing |                                                      `$0.006/GB` |
| Traffic thật `orders` 7 ngày gần nhất            |                    `97,352,246.52 bytes` = `0.090666 GiB/7 ngày` |
| Estimate traffic tháng theo 7 ngày gần nhất      |                                          khoảng `0.417 GB/tháng` |

### Tính fixed cost

```text
Multi-VPC connectivity (1 scheme: IAM), 24x7
= 730 giờ x $0.0225
≈ $16.43/tháng cố định, không phụ thuộc traffic
```

| Traffic orders                                 | Firehose ingest | Multi-VPC cố định | Multi-VPC data processing | Tổng/tháng |
| ---------------------------------------------- | --------------: | ----------------: | ------------------------: | ---------: |
| Traffic thật 7 ngày gần nhất (~0.417 GB/tháng) |         `$0.02` |          `$16.43` |                   `$0.00` |  `~$16.45` |
| 1 GB/ngày (~30 GB/tháng)                       |         `$1.65` |          `$16.43` |                   `$0.18` |  `~$18.26` |
| 10 GB/ngày (~300 GB/tháng)                     |        `$16.50` |          `$16.43` |                   `$1.80` |  `~$34.73` |

Chưa gồm S3 storage/lifecycle, CloudWatch logs/alarms và KMS nếu đổi từ SSE-S3 sang SSE-KMS. Với traffic hiện tại, các khoản này dự kiến nhỏ hơn phần fixed cost Multi-VPC.

## 3. Trade-off

| Phương án                               |                                                                   Chi phí | Nhận xét                                                                             |
| --------------------------------------- | ------------------------------------------------------------------------: | ------------------------------------------------------------------------------------ |
| AWS MSK Connect                         |                              `~$80.30/tháng` (1 MCU x `$0.11/giờ` x 730h) | Đang bị AWS block, không chọn                                                        |
| Kinesis Data Firehose native MSK source | `~$16.45/tháng` theo traffic thật, `~$18.26-34.73/tháng` với 1-10 GB/ngày | Phương án chọn; managed, không vận hành pod, đổi lại có phí cố định Multi-VPC        |
| Self-managed Kafka Connect (EKS)        |                                                            `~$0-30/tháng` | Fallback nếu Firehose không được duyệt/không khả thi; cần vận hành thêm pod/workload |
| Custom consumer                         |                                          Infra thấp, engineering cost cao | Loại, không xét tiếp                                                                 |

Quyết định cost: chọn Firehose dù không phải phương án rẻ nhất, vì tránh vận hành thêm workload/pod trong EKS và không phụ thuộc AWS gỡ block MSK Connect (không có ETA).

## 4. Firehose Có Đủ Đáp Ứng Yêu Cầu Không

- [ ] RPO <= 15 phút - đo bằng CloudWatch metric `DeliveryToS3.DataFreshness`.

- [ ] S3 output format/partition khớp convention REL-22: `orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`.

- [ ] SCRAM app path không đổi; dual-auth SASL/SCRAM + IAM đã được Tech Lead confirm là hướng khả thi cần CDO04 duyệt trước khi implement.

## 5. CDO04 Review Result

Decision: \_\_\_

Điều kiện bắt buộc trước implementation:

- [ ] Duyệt cost cố định Multi-VPC khoảng `$16.43-35/tháng` theo traffic envelope 1-10 GB/ngày.

- [ ] Xác nhận rolling broker update khi bật IAM auth, maintenance window chấp nhận được.

- [ ] Xác nhận cluster resource policy cho Firehose không mở quyền quá mức cần thiết.

### CDO04 approval record

| Thông tin                        | Giá trị                                                                    |
| -------------------------------- | -------------------------------------------------------------------------- |
| Decision                         | \_\_\_                                                                     |
| Selected design                  | Kinesis Data Firehose (MSK native source) + Multi-VPC private connectivity |
| Projected cost theo traffic thật | `~$16.45/tháng`                                                            |
| Projected cost at 1 GB/ngày      | `~$18.26/tháng`                                                            |
| Projected cost at 10 GB/ngày     | `~$34.73/tháng`                                                            |
| Ngày duyệt                       | \_\_\_                                                                     |
| Người duyệt                      | \_\_\_                                                                     |
| Comment/Evidence link            | \_\_\_                                                                     |

## 6. Nguồn Tham Chiếu

- AWS Firehose pricing - MSK as a source ingestion: https://aws.amazon.com/firehose/pricing/
- AWS MSK pricing - Multi-VPC private connectivity hourly/data processing charges: https://aws.amazon.com/msk/pricing/
- AWS Firehose MSK source documentation: https://docs.aws.amazon.com/firehose/latest/dev/writing-with-msk.html
- AWS Firehose access control for private MSK: https://docs.aws.amazon.com/firehose/latest/dev/controlling-access.html
- AWS Firehose CloudWatch metrics: https://docs.aws.amazon.com/firehose/latest/dev/monitoring-with-cloudwatch-metrics.html
- AWS Firehose CloudWatch alarm best practices: https://docs.aws.amazon.com/firehose/latest/dev/firehose-cloudwatch-metrics-best-practices.html
