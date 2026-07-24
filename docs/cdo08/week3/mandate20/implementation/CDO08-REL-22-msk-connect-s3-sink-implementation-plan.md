# CDO08-REL-22 - MSK Orders S3 Sink Connector Implementation Plan

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Deploy MSK Connect S3 Sink Connector for orders
**Ngày ghi nhận:** 2026-07-23

## 1. Mục Tiêu

Subtask này triển khai cơ chế archive liên tục event `orders` từ Amazon MSK sang S3 để có bản sao ngoài Kafka cluster. Đây là gap chính của Mandate 20 vì MSK không có snapshot/backup native giống RDS PITR.

Mục tiêu vận hành:

- Connector consume topic `orders` trên MSK `techx-tf4-orders`.
- Ghi event ra bucket `tf4-msk-orders-archive-511825856493-us-east-1` dưới prefix `orders/`.
- Flush/rotate không vượt quá 15 phút để đáp ứng RPO.
- Không hardcode credential trong Terraform, manifest hoặc evidence.
- Connector có log, error handling và DLQ để điều tra record lỗi.
- Có bằng chứng connector `RUNNING` và S3 có object thật để subtask 4 validate đọc lại.

## 2. Trạng Thái Runtime Đã Scan

Thời điểm scan: 2026-07-23.

MSK Connect hiện chưa có resource runtime:

```text
connectors: []
customPlugins: []
workerConfigurations: []
```

MSK cluster hiện tại:

```text
Cluster name: techx-tf4-orders
State: ACTIVE
Kafka version: 3.9.x
Auth: SASL/SCRAM enabled
Encryption in transit: TLS
Bootstrap SASL/SCRAM port: 9096
Subnets:
- subnet-0280b36e2249f33d8
- subnet-0753e69d90fe8f820
Security group: sg-0b15c69a8c397e9d6
```

MSK secret metadata:

```text
Secret name: techx/tf4/msk-kafka
Secret ARN: arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/msk-kafka-W5RENp
Current version stage: AWSCURRENT
Previous version stage: AWSPREVIOUS
```

Archive bucket đã được tạo ở subtask 2:

```text
Bucket: tf4-msk-orders-archive-511825856493-us-east-1
Versioning: Enabled
Encryption: AES256
Lifecycle prefix: orders/
Transition: after 7 days to STANDARD_IA
Expiration: after 35 days
Current object count under orders/: 0
```

## 3. Hướng Triển Khai Theo PR

MSK Connect custom plugin phải trỏ tới ZIP/JAR đã tồn tại trên S3. Trong workflow hiện tại, Terraform apply chỉ chạy sau khi merge PR vào `main`, nên không nên nhét cả bucket plugin, upload artifact và connector vào cùng một PR.

Hướng triển khai được tách thành các PR nhỏ có checkpoint rõ ràng:

- PR1: Tạo plugin artifact foundation.
- Manual gate sau PR1: Upload S3 Sink plugin ZIP và ghi lại object version.
- PR2: Tạo MSK Connect runtime resources và connector.
- Runtime gate sau PR2: Verify connector `RUNNING`, có object trong S3, latency <= 15 phút.
- PR3: Ghi evidence cho subtask 3 và chuẩn bị input cho subtask 4.

Cách tách này giúp review dễ hơn, tránh apply fail do custom plugin object chưa tồn tại, và mỗi PR đều có output có thể kiểm chứng độc lập.

## 4. PR1 - Plugin Artifact Foundation

### 4.1. Việc Cần Làm

Tạo bucket riêng để lưu MSK Connect custom plugin artifact:

```text
s3://tf4-msk-connect-plugins-511825856493-us-east-1/plugins/
```

Terraform resources:

- S3 bucket private cho plugin artifacts.
- S3 versioning.
- SSE-S3 encryption.
- Block public access.
- Bucket policy deny non-TLS.
- Terraform outputs cho bucket name, ARN và prefix.

Thêm script build/upload plugin ZIP:

```text
scripts/cdo08/build-upload-msk-s3-sink-plugin.ps1
```

Script này tải và đóng gói:

- Confluent Kafka Connect S3 Sink Connector, pin version rõ ràng.
- AWS MSK config providers, để connector đọc credential từ AWS Secrets Manager.
- Dependency cần thiết trong ZIP.

Không commit ZIP vào git để tránh repo phình lớn và khó review supply chain.

### 4.2. Kết Quả Sau Khi Merge PR1

Sau khi PR1 merge và Terraform apply thành công, hệ thống có thêm bucket artifact cho MSK Connect plugin. Chưa có connector nào được tạo, chưa consume topic `orders`, chưa ảnh hưởng app/SLO.

Output cần lấy lại:

```powershell
terraform -chdir=infra/terraform output msk_connect_plugin_bucket_name
terraform -chdir=infra/terraform output msk_connect_plugin_prefix
terraform -chdir=infra/terraform output msk_connect_plugin_bucket_arn
```

Kỳ vọng:

```text
msk_connect_plugin_bucket_name = "tf4-msk-connect-plugins-511825856493-us-east-1"
msk_connect_plugin_prefix = "plugins/"
```

### 4.3. Gate Sau PR1 - Upload Plugin Artifact

Sau khi có bucket, chạy script upload plugin:

```powershell
.\scripts\cdo08\build-upload-msk-s3-sink-plugin.ps1 `
  -Bucket tf4-msk-connect-plugins-511825856493-us-east-1 `
  -Region us-east-1 `
  -Profile tf4
```

Output cần giữ để dùng trong PR2:

```text
Bucket
Key
VersionId
ConnectorVersion
ConfigProviderVersion
Sha256
```

Verify object:

```powershell
aws s3api head-object `
  --bucket tf4-msk-connect-plugins-511825856493-us-east-1 `
  --key <plugin-object-key> `
  --version-id <plugin-object-version-id> `
  --region us-east-1 `
  --profile tf4 `
  --query '{Size:ContentLength,VersionId:VersionId,SSE:ServerSideEncryption,Metadata:Metadata}'
```

Chỉ chuyển sang PR2 khi đã có `Key`, `VersionId` và `Sha256`.

## 5. PR2 - MSK Connect Runtime Resources

### 5.1. Việc Cần Làm

PR2 tạo các resource runtime cho connector:

- `aws_mskconnect_custom_plugin` trỏ tới plugin ZIP trên S3.
- `aws_mskconnect_worker_configuration`.
- MSK Connect service execution role least-privilege.
- Security group riêng cho connector.
- Ingress từ connector SG vào MSK broker SG port `9096`.
- CloudWatch log group `/aws/mskconnect/techx-tf4-orders-s3-sink`.
- `aws_mskconnect_connector` consume topic `orders` và ghi sang S3 archive bucket.

Connector là read-only consumer trên MSK, không thay đổi app producer/consumer config.

### 5.2. IAM Dự Kiến

Service execution role chỉ cần các quyền tối thiểu:

- Đọc plugin ZIP từ plugin artifact bucket.
- Ghi object vào `s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/*`.
- List archive bucket trong phạm vi prefix cần thiết.
- Đọc secret `techx/tf4/msk-kafka` từ Secrets Manager.
- Ghi CloudWatch Logs cho connector.

Không cấp quyền xoá archive object cho connector role.

### 5.3. Network Dự Kiến

Connector cần:

- Egress tới MSK broker port `9096`.
- MSK security group ingress từ connector security group vào port `9096`.
- Egress HTTPS `443` để gọi S3, Secrets Manager và CloudWatch Logs.

MSK hiện đang dùng SASL/SCRAM và TLS, nên connector dùng port `9096`.

### 5.4. Worker Configuration Dự Kiến

Worker configuration mục tiêu là không để MSK credential trong Terraform state:

```properties
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false
connector.client.config.override.policy=All
offset.flush.interval.ms=60000
config.providers=secretsmanager
config.providers.secretsmanager.class=<AWS Secrets Manager Config Provider class>
config.providers.secretsmanager.param.region=us-east-1
config.action.reload=none
```

Tên class provider và syntax reference secret sẽ được xác nhận từ plugin bundle trước khi code PR2.

### 5.5. Connector Configuration Dự Kiến

Core connector:

```properties
connector.class=io.confluent.connect.s3.S3SinkConnector
tasks.max=1
topics=orders
s3.region=us-east-1
s3.bucket.name=tf4-msk-orders-archive-511825856493-us-east-1
topics.dir=orders
storage.class=io.confluent.connect.s3.storage.S3Storage
format.class=io.confluent.connect.s3.format.json.JsonFormat
schema.compatibility=NONE
key.converter=org.apache.kafka.connect.storage.StringConverter
value.converter=org.apache.kafka.connect.json.JsonConverter
value.converter.schemas.enable=false
```

Partition path để replay theo thời gian/topic:

```properties
partitioner.class=io.confluent.connect.storage.partitioner.TimeBasedPartitioner
path.format='topic'=orders/'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH
partition.duration.ms=3600000
locale=en
timezone=UTC
timestamp.extractor=Record
```

RPO/flush:

```properties
rotate.schedule.interval.ms=600000
flush.size=100
s3.part.size=5242880
```

`rotate.schedule.interval.ms=600000` là 10 phút, nhỏ hơn yêu cầu RPO 15 phút. `flush.size=100` giúp môi trường traffic thấp không phải đợi batch quá lớn.

Error handling/DLQ:

```properties
errors.tolerance=all
errors.deadletterqueue.topic.name=orders-archive-dlq
errors.deadletterqueue.context.headers.enable=true
errors.log.enable=true
errors.log.include.messages=false
```

DLQ giúp connector không dừng vì một record lỗi format, nhưng DLQ vẫn nằm trong MSK nên chỉ là error handling runtime, không thay thế S3 archive.

### 5.6. Kết Quả Sau Khi Merge PR2

Sau khi PR2 merge/apply thành công, kỳ vọng:

```text
Custom plugin: ACTIVE
Worker configuration: created
Connector: RUNNING
CloudWatch log group: exists
S3 archive prefix orders/: starts receiving objects
```

Nếu connector không `RUNNING`, dùng log group và `describe-connector` để debug trước khi sang subtask 4.

## 6. Gate Sau PR2 - Runtime Verification

### 6.1. Connector Status

```powershell
aws kafkaconnect list-connectors `
  --region us-east-1 `
  --profile tf4

aws kafkaconnect describe-connector `
  --connector-arn <connector-arn> `
  --region us-east-1 `
  --profile tf4
```

Kỳ vọng:

```text
connectorState: RUNNING
```

### 6.2. CloudWatch Logs

```powershell
aws logs filter-log-events `
  --log-group-name /aws/mskconnect/techx-tf4-orders-s3-sink `
  --region us-east-1 `
  --profile tf4 `
  --filter-pattern "ERROR Exception Failed denied timeout"
```

Kỳ vọng: không có auth/network/delivery error nghiêm trọng lặp lại.

### 6.3. S3 Object Xuất Hiện

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/ `
  --recursive `
  --summarize `
  --region us-east-1 `
  --profile tf4
```

Kỳ vọng:

```text
Total Objects > 0
```

### 6.4. RPO Latency Check

Sau khi có order marker hoặc order thật:

- Ghi timestamp lúc order được tạo.
- Đợi connector flush/rotate.
- Ghi timestamp object xuất hiện trong S3.
- Kỳ vọng latency <= 15 phút.

Phần marker order và parse object chi tiết sẽ làm ở subtask 4.

### 6.5. Restart Connector Check

Restart connector hoặc trigger update nhỏ có kiểm soát, sau đó verify:

- Connector quay lại `RUNNING`.
- Không có delivery error kéo dài.
- Object mới tiếp tục xuất hiện trong S3.
- Không mất dữ liệu vượt RPO 15 phút.

## 7. PR3 - Evidence Cho Subtask 3

PR3 chỉ viết evidence sau khi runtime verify pass.

Evidence cần ghi:

- Connector ARN và status `RUNNING`.
- Custom plugin ARN/revision và S3 object key/version của plugin ZIP.
- Worker configuration ARN/revision.
- Service execution role ARN.
- Connector log group name.
- S3 object path có record `orders` thật.
- Flush/rotate setting chứng minh <= 15 phút.
- CloudWatch log check không có delivery error nghiêm trọng.
- DLQ topic và error handling behavior.

Sau PR3, subtask 3 có thể xem là xong và chuyển sang subtask 4.

## 8. Chuyển Sang Subtask 4

Subtask 4 sẽ validate archive đọc lại được và không thiếu marker ngoài cửa sổ RPO:

- Tạo batch order markers.
- Đối chiếu produced order IDs với records trong S3.
- Parse object bằng script/tool độc lập.
- Ghi duplicate/missing và latency.

Subtask 3 không cần hoàn tất phần parse đầy đủ, chỉ cần connector chạy và có object orders thật trong S3.

## 9. Rollback Và Safety

Nếu PR1 lỗi:

- Chỉ ảnh hưởng bucket plugin artifact.
- Chưa có connector, chưa có traffic, chưa ảnh hưởng SLO.
- Rollback bằng revert Terraform bucket nếu cần.

Nếu upload plugin lỗi:

- Không tạo PR2.
- Xoá artifact lỗi nếu cần, upload lại object version mới.
- Không ảnh hưởng runtime.

Nếu PR2 connector lỗi nhưng app/SLO bình thường:

- Stop/delete connector để dừng archive.
- Không xoá archive bucket hoặc object đã ghi.
- Giữ plugin, worker config, IAM role để debug nếu cần.
- Không thay đổi producer/consumer app config trong subtask này.

Nếu connector gây áp lực lên MSK:

- Disable connector trước.
- Kiểm tra CloudWatch Logs, MSK broker metrics và consumer lag.
- Giảm tasks/flush hoặc điều chỉnh worker capacity trong PR follow-up.

## 10. Rủi Ro Cần Xác Nhận Trước PR2

- Version chính xác của Confluent S3 Sink connector để pin.
- Class name và syntax chính xác của AWS Secrets Manager config provider trong plugin bundle.
- Terraform provider schema cho `aws_mskconnect_connector` trong version hiện tại của repo.
- MSK Connect có cần VPC endpoint hoặc NAT route để gọi S3/Secrets Manager/CloudWatch không.
- DLQ topic `orders-archive-dlq` có cần tạo trước hay MSK cho auto-create topic.
