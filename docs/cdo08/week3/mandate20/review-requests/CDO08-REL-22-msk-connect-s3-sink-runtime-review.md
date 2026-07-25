# CDO08-REL-22 - MSK Connect S3 Sink Runtime Review Request

**Task:** CDO08-REL-22
**Subtask:** Deploy MSK Connect S3 Sink Connector for orders
**Ngày ghi nhận:** 2026-07-24
**Người gửi review:** Hoàng Nam / CDO08
**Người nhận review:** Tech Lead/PM
**PR scope:** MSK Connect runtime resources for `orders` archive

## 1. Mục Tiêu Review

Review request này mô tả thay đổi runtime trước khi merge PR triển khai MSK Connect S3 Sink Connector cho topic `orders`.

Mục tiêu của PR là tạo connector read-only consumer trên Amazon MSK để archive event `orders` sang S3, phục vụ backup/replay theo Mandate 20. PR không thay đổi application source, GitOps app values, checkout/payment/shipping path hoặc producer config.

## 2. Bối Cảnh Trước PR Này

Mandate 20 yêu cầu các store in-scope có recovery mechanism phù hợp. Với MSK orders, MSK không có snapshot native như RDS PITR. Vì vậy cần một bản archive ngoài Kafka cluster để giảm rủi ro mất topic hoặc mất cluster.

Các bước đã hoàn tất trước PR runtime:

- Subtask 2 đã tạo S3 archive bucket:
    - Bucket: `tf4-msk-orders-archive-511825856493-us-east-1`
    - Prefix: `orders/`
    - Versioning: enabled
    - Encryption: AES256
    - Lifecycle: transition after 7 days, expiration after 35 days
    - Public access: blocked
- PR1 của subtask 3 đã tạo plugin artifact bucket:
    - Bucket: `tf4-msk-connect-plugins-511825856493-us-east-1`
    - Prefix: `plugins/`
- Custom plugin ZIP đã được upload sau PR1:
    - Key: `plugins/confluent-s3-sink/12.1.0/confluent-s3-sink-msk-config-provider-0.4.0.zip`
    - VersionId: `hXtZCmoZg6tFgybk57jR400Kdf2CYHHh`
    - Sha256: `112225c1dff0620e4f4050551cc5a22191a8f231348350cf44dbf603e7c497ee`

## 3. PR Này Sẽ Tạo Gì

Terraform plan dự kiến:

```text
Plan: 12 to add, 0 to change, 0 to destroy
```

Resource chính được tạo:

- `aws_mskconnect_custom_plugin.orders_s3_sink`
- `aws_mskconnect_worker_configuration.orders_s3_sink`
- `aws_mskconnect_connector.orders_s3_sink`
- IAM service execution role/policy cho connector
- Security group riêng cho connector
- Security group ingress từ connector vào MSK port `9096`
- Security group egress từ connector tới MSK `9096`, HTTPS `443`, DNS `53`
- CloudWatch log group `/aws/mskconnect/techx-tf4-orders-s3-sink`
- Terraform outputs phục vụ evidence

Connector configuration chính:

```text
connector.class = io.confluent.connect.s3.S3SinkConnector
topics = orders
tasks.max = 1
worker_count = 1
mcu_count = 1
s3.bucket.name = tf4-msk-orders-archive-511825856493-us-east-1
topics.dir = orders
rotate.schedule.interval.ms = 600000
flush.size = 100
```

`rotate.schedule.interval.ms=600000` tương đương 10 phút, nhỏ hơn RPO 15 phút.

## 4. Khi Merge Thì Điều Gì Sẽ Xảy Ra

Sau khi merge, CD Terraform apply sẽ tạo connector thật. Khi `aws_mskconnect_connector` được tạo xong, AWS MSK Connect sẽ tự start connector.

Luồng runtime sau apply:

1. MSK Connect worker start.
2. Connector load custom plugin từ S3 artifact.
3. Connector đọc MSK credential từ AWS Secrets Manager thông qua config provider.
4. Connector kết nối MSK `techx-tf4-orders` qua SASL/SCRAM TLS port `9096`.
5. Connector tạo consumer group riêng để consume topic `orders`.
6. Connector ghi records vào S3 dưới prefix `orders/`.
7. Connector flush/rotate object theo cấu hình 10 phút hoặc khi đủ batch.

Không có bước chạy lệnh start riêng sau merge. Việc cần làm sau merge là verify runtime.

## 5. Runtime Impact Và Rủi Ro

Connector là read-only consumer, không nằm trực tiếp trong request path của checkout. PR không đổi app config và không đổi producer.

Rủi ro có thể có:

- Connector fail do auth/config provider/plugin class.
- Connector fail network nếu SG/NAT/DNS không đủ.
- Connector tạo thêm connection/read throughput trên MSK.
- Connector log lỗi lặp lại nếu không ghi được S3 hoặc DLQ.
- Nếu MSK đang sát ngưỡng, tải đọc thêm có thể ảnh hưởng gián tiếp tới service dùng Kafka.

Giảm rủi ro trong PR này:

- `tasks.max=1`
- `worker_count=1`
- `mcu_count=1`
- Connector chỉ ghi S3, không xoá archive object.
- Có CloudWatch log group riêng.
- Có DLQ `orders-archive-dlq`.
- Có thể rollback bằng Terraform revert hoặc emergency delete connector.

## 6. Verify Sau Khi CD Apply Thành Công

### 6.1. Lấy Connector ARN

```powershell
aws kafkaconnect list-connectors `
  --region us-east-1 `
  --profile tf4
```

Kỳ vọng thấy connector:

```text
techx-tf4-orders-s3-sink
```

### 6.2. Kiểm Tra Connector State

```powershell
aws kafkaconnect describe-connector `
  --connector-arn <connector-arn> `
  --region us-east-1 `
  --profile tf4 `
  --query '{Name:connectorName,State:connectorState,Version:currentVersion,Description:stateDescription}'
```

Kỳ vọng:

```text
State = RUNNING
```

Nếu state là `CREATING` hoặc `UPDATING`, đợi thêm và check lại. Nếu state là `FAILED`, đọc `stateDescription` và CloudWatch Logs.

### 6.3. Kiểm Tra CloudWatch Logs

```powershell
aws logs filter-log-events `
  --log-group-name /aws/mskconnect/techx-tf4-orders-s3-sink `
  --region us-east-1 `
  --profile tf4 `
  --filter-pattern "ERROR Exception Failed denied timeout AccessDenied"
```

Kỳ vọng: không có lỗi auth/network/plugin/S3 lặp lại.

### 6.4. Kiểm Tra S3 Có Object

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/ `
  --recursive `
  --summarize `
  --region us-east-1 `
  --profile tf4
```

Kỳ vọng sau khoảng 10-15 phút có object:

```text
Total Objects > 0
```

Nếu chưa có object ngay, cần kiểm tra có traffic/order mới trong topic không trước khi kết luận connector lỗi.

### 6.5. Kiểm Tra SLO Và Service Sanity

Theo dõi dashboard SLO sau merge:

- Browse non-5xx
- Storefront p95 latency
- Cart success
- Checkout success

Connector không nằm trong request path, nhưng nếu MSK bị ảnh hưởng gián tiếp thì checkout/accounting có thể biểu hiện lỗi. Nếu SLO tụt cùng thời điểm connector/log/MSK có lỗi, dừng connector và rollback.

## 7. Dấu Hiệu Tốt

Có thể xem PR pass runtime gate nếu:

- CD apply thành công.
- Connector state `RUNNING`.
- CloudWatch Logs không có lỗi nghiêm trọng lặp lại.
- S3 prefix `orders/` có object mới.
- SLO không tụt bất thường sau merge.

## 8. Dấu Hiệu Lỗi

Cần điều tra hoặc rollback nếu:

- CD apply fail khi tạo connector/custom plugin/worker config.
- Connector state `FAILED`.
- Log có `AccessDenied`, `SASL authentication failed`, `NoClassDefFoundError`, `S3Exception`, `ConnectException` hoặc timeout lặp lại.
- SLO tụt rõ cùng thời điểm connector/MSK báo lỗi.
- Connector chạy nhưng sau thời gian hợp lý vẫn không có object và xác nhận topic có order mới.

## 9. Rollback Chuẩn Bằng GitOps/Terraform

Nếu cần rollback sạch, revert merge commit của PR này:

```bash
git checkout main
git pull origin main
git checkout -b revert/rel22-msk-connect-s3-sink
git revert <PR2_MERGE_COMMIT_SHA>
git push -u origin revert/rel22-msk-connect-s3-sink
```

Tạo PR revert và merge để CD Terraform destroy resource runtime của PR này.

Rollback này sẽ destroy:

- MSK Connect connector
- Custom plugin resource
- Worker configuration
- Connector IAM role/policy
- Connector security group/rules
- Connector CloudWatch log group

Rollback này không xoá S3 archive bucket và không xoá object đã ghi vì bucket archive thuộc subtask 2.

## 10. Emergency Stop Nếu Runtime Có Vấn Đề

Nếu cần dừng nhanh connector trước khi PR revert kịp merge:

```powershell
aws kafkaconnect describe-connector `
  --connector-arn <connector-arn> `
  --region us-east-1 `
  --profile tf4 `
  --query '{State:connectorState,Version:currentVersion}'
```

Sau đó delete connector:

```powershell
aws kafkaconnect delete-connector `
  --connector-arn <connector-arn> `
  --current-version <current-version> `
  --region us-east-1 `
  --profile tf4
```

Lưu ý: delete thủ công sẽ làm Terraform state lệch. Sau emergency stop vẫn cần PR revert hoặc Terraform reconciliation để đưa state về đúng.

## 11. Điều Cần Review Trước Khi Approve

- Plugin artifact `Key`, `VersionId`, `Sha256` đúng với output upload.
- Plan chỉ add resource mới, không change/destroy resource hiện có.
- IAM role không có quyền xoá archive object.
- Connector dùng cấu hình conservative `1 worker / 1 task`.
- RPO config là 10 phút, đạt yêu cầu <= 15 phút.
- SG chỉ mở connector vào MSK port `9096` và AWS API egress cần thiết.
- Rollback path đã rõ.
