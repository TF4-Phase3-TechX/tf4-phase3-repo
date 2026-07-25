# CDO08-REL-22 - Self-Managed Kafka Connect Orders Archive Implementation Plan

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Deploy MSK orders archive mechanism
**Ngày ghi nhận:** 2026-07-25
**Trạng thái:** Draft gửi PM/Tech Lead review trước khi quyết định implement runtime

## 1. Mục Tiêu

Mandate 20 yêu cầu có cơ chế archive liên tục topic `orders` từ Amazon MSK ra S3, RPO <= 15 phút, để REL-25 có dữ liệu thật dùng cho restore/replay test.

Hướng ban đầu của REL-22 subtask 3 là AWS MSK Connect S3 Sink. Tuy nhiên runtime `CreateConnector` đang bị block ở tầng AWS account/service. Firehose native MSK source đã được review cost, nhưng để chạy theo hướng đó cần thêm điều kiện về MSK IAM/Multi-VPC và có thể kéo theo thay đổi broker instance type/cost lớn hơn.

Vì vậy cần trình thêm một hướng khả thi khác: self-managed Kafka Connect chạy trên EKS, dùng Confluent S3 Sink Connector chuẩn để archive `orders` ra S3. Đây không phải custom consumer tự code business logic; phần consume offset, retry, connector lifecycle và S3 sink vẫn dựa trên Kafka Connect/S3 Sink connector đã có sẵn. Phần "self-managed" là team vận hành runtime Kafka Connect worker trên EKS thay vì dùng AWS MSK Connect managed service.

## 2. Vì Sao Cần Tách Riêng Plan Này

Plan AWS MSK Connect cũ vẫn đúng về mục tiêu archive và S3 convention, nhưng không còn chắc chắn về khả năng triển khai trong account hiện tại vì `CreateConnector` bị AWS service từ chối.

Plan này dùng lại các phần đã làm được:

- MSK topic/source vẫn là `orders` trên cluster `techx-tf4-orders`.
- App path hiện tại vẫn dùng SASL/SCRAM, không đổi checkout/accounting/fraud-detection config.
- S3 archive bucket đã có: `tf4-msk-orders-archive-511825856493-us-east-1`.
- Prefix/convention đã duyệt: `orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`.
- Credential contract vẫn dùng Kubernetes secret `msk-kafka-secret`, sync từ AWS Secrets Manager `techx/tf4/msk-kafka`.
- Không copy secret value vào Terraform/GitOps/evidence.

Điểm thay đổi chính là runtime connector sẽ là workload trong EKS thay vì resource `aws_mskconnect_connector`.

## 3. Nguyên Tắc Triển Khai

- Không bật workload archive thật trong cùng PR tạo foundation.
- Không tạo thêm traffic lên MSK trước khi PM/Tech Lead duyệt hướng.
- Không cấp quyền delete object/bucket cho archive writer.
- Không dùng image public runtime trực tiếp trong GitOps production nếu chưa có digest/signature phù hợp Kyverno.
- Mỗi PR phải có output hoặc trạng thái có thể verify độc lập.
- Nếu bật runtime, bắt đầu với 1 replica để tránh duplicate/offset complexity, sau khi ổn mới xem xét HA/failover.

## 4. Kiến Trúc Đề Xuất

Luồng dữ liệu mục tiêu:

```text
checkout/payment flow
        |
        v
Amazon MSK topic orders
        |
        | consume bằng Kafka Connect consumer group riêng
        v
Kafka Connect worker trên EKS
        |
        | Confluent S3 Sink Connector
        v
s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
```

Các thành phần chính:

- EKS Deployment `kafka-connect-orders-archive` trong namespace `techx-tf4`.
- ServiceAccount `kafka-connect-orders-archive` dùng IRSA.
- IAM policy chỉ cho write/list cần thiết trên S3 archive prefix `orders/`.
- Kafka Connect worker dùng SCRAM credential từ `msk-kafka-secret`.
- Connector config ở PR sau để consume topic `orders` và ghi S3.
- CloudWatch/OTel/log runtime sẽ dùng theo cơ chế hiện có của cluster nếu image/runtime hỗ trợ.

## 5. Chia PR Đề Xuất

### 5.1. PR1 - Foundation, Chưa Bật Runtime

Mục tiêu PR1 là chuẩn bị nền tảng an toàn, merge được mà không tạo workload mới.

Nội dung PR1 đã chuẩn bị trên nhánh:

```text
cdo08/week3/rel22/self-managed-kafka-connect-foundation
```

Thay đổi dự kiến:

- Thêm Terraform IRSA role `techx-tf4-orders-kafka-connect-archive`.
- Thêm IAM policy `techx-tf4-orders-kafka-connect-archive-s3-write`.
- Policy chỉ có quyền:
    - `s3:GetBucketLocation` trên archive bucket.
    - `s3:ListBucket`, `s3:ListBucketMultipartUploads` giới hạn prefix `orders/`.
    - `s3:PutObject`, `s3:AbortMultipartUpload`, `s3:ListMultipartUploadParts` trên `orders/*`.
- Không có quyền `s3:DeleteObject`, `s3:DeleteObjectVersion`, `s3:DeleteBucket`.
- Thêm output `msk_orders_kafka_connect_archive_irsa_role_arn`.
- Thêm Helm values/template `kafkaConnectArchive` nhưng `enabled: false` mặc định.
- Template khi bật sẽ tạo ServiceAccount/Deployment/Service, nhưng PR1 chưa render workload trong runtime mặc định.

Kết quả sau khi merge PR1:

- Có IRSA role/policy sẵn cho Kafka Connect archive writer.
- Chart có khả năng render workload Kafka Connect khi GitOps bật flag sau này.
- Không tạo pod mới.
- Không consume topic `orders`.
- Không ảnh hưởng checkout/cart/SLO.

Validation đã chạy local:

```text
terraform fmt -check: pass
helm lint techx-corp-chart: pass
helm template default: không render kafka-connect-orders-archive
helm template enabled=true: render được ServiceAccount/Deployment/Service với IRSA annotation giả lập
```

`terraform validate` local cần `terraform init` do module IRSA mới, CI sẽ init trước khi validate.

### 5.1.1. Vì Sao Pod Nằm Ở PR Sau

PR1 chưa tạo pod vì runtime Kafka Connect phụ thuộc image production-ready. Image cần được build/push vào ECR nội bộ, scan CVE, ký/attest và pin digest để không bị Kyverno chặn khi rollout. Tách pod sang PR2 giúp review rõ hơn: PR1 chỉ tạo quyền và template an toàn, còn PR2 mới bật workload sau khi có image digest/signature và GitOps values cụ thể.

### 5.2. PR2 - Runtime Image Và GitOps Enable Có Kiểm Soát

PR2 chỉ nên làm sau khi PM/Tech Lead chốt chọn self-managed Kafka Connect.

Nội dung cần chuẩn bị:

- Build/publish Kafka Connect image vào ECR nội bộ `techx-corp`.
- Image phải chứa Kafka Connect runtime và Confluent S3 Sink Connector.
- Image phải đi qua CI security gate, cosign signing và digest promotion như các service khác.
- GitOps values bật `kafkaConnectArchive.enabled=true`.
- Set `image.tag`, `image.digest` từ promotion output.
- Set ServiceAccount annotation:

```yaml
eks.amazonaws.com/role-arn: arn:aws:iam::511825856493:role/techx-tf4-orders-kafka-connect-archive
```

- Deploy 1 replica trước.
- Có thể chỉ bật worker trước để verify pod Ready và REST API `/connectors`, rồi mới nạp connector ở PR3.

Kết quả sau PR2:

- Kafka Connect worker chạy trong EKS.
- Worker kết nối được MSK bằng SCRAM.
- Worker có AWS permission để ghi archive bucket.
- Chưa có hoặc mới có connector tùy quyết định tách gate.

Rủi ro PR2:

- Tạo thêm pod trong EKS, dùng CPU/memory theo resource request.
- Nếu image thiếu plugin hoặc config SCRAM sai, pod/worker có thể CrashLoop hoặc NotReady.
- Nếu worker Ready nhưng connector chưa tạo, chưa có archive traffic.
- Nếu connector tạo trong PR2, sẽ có thêm consumer group đọc topic `orders`.

Rollback PR2:

- Revert GitOps enable hoặc set `kafkaConnectArchive.enabled=false`.
- Pod dừng, không còn consumer mới đọc MSK.
- S3 archive object đã ghi vẫn giữ lại theo lifecycle/retention.

### 5.3. PR3 - Connector Config Orders -> S3

Nếu PR2 chỉ bật worker, PR3 sẽ tạo connector config.

Connector config cần đáp ứng:

- `topics=orders`.
- S3 bucket `tf4-msk-orders-archive-511825856493-us-east-1`.
- Prefix/path theo convention đã duyệt.
- Flush/rotate <= 15 phút.
- JSON output parse được cho subtask 4.
- Error handling/DLQ hoặc error log policy rõ ràng.
- Consumer group riêng để không ảnh hưởng app consumer group.

Kết quả sau PR3:

- Worker consume topic `orders`.
- Object xuất hiện trong S3 archive.
- Có metric/log để kiểm tra delivery latency.
- Có thể chuyển sang subtask 4 để validate marker/completeness/readability.

Rollback PR3:

- Delete/disable connector config qua Kafka Connect REST hoặc GitOps config nếu connector được quản lý bằng manifest/script.
- Worker vẫn có thể giữ chạy để debug hoặc tắt tiếp bằng rollback PR2.
- Không ảnh hưởng app config.

### 5.4. PR4 - Evidence Và Operational Runbook

Sau khi connector chạy ổn:

- Ghi evidence connector/worker status.
- Ghi S3 object evidence.
- Ghi latency/RPO evidence.
- Ghi rollback steps.
- Ghi input cho subtask 4: command/script parse S3 object và đối chiếu marker.

Nếu PR evidence cần gom cùng PR3 thì vẫn được, nhưng nên tách nếu runtime cần quan sát thêm.

## 6. Vì Sao Không Làm Tất Cả Trong Một PR

Không nên nhét foundation, image, enable workload và connector config vào một PR vì:

- CI/CD hiện apply Terraform sau khi merge, nếu fail sẽ khó biết fail ở IAM, image, workload hay connector config.
- Kafka Connect image phải đi qua build/sign/promotion riêng để tránh Kyverno chặn pod mới.
- Khi bật worker/connector sẽ tạo consumer mới đọc topic `orders`; cần có cửa monitor riêng.
- Nếu connector config sai, worker foundation vẫn có thể đúng; tách PR giúp rollback chính xác hơn.
- PR1 merge không tạo runtime nên có thể review/approve sớm mà không gây áp lực SLO.

## 7. Ảnh Hưởng Runtime Dự Kiến

PR1:

```text
Ảnh hưởng SLO: Không.
Lý do: không tạo pod, không consume MSK, không đổi app config.
```

PR2 worker only:

```text
Ảnh hưởng SLO trực tiếp: Thấp.
Lý do: chỉ thêm pod Kafka Connect, chưa đọc topic nếu chưa tạo connector.
Rủi ro gián tiếp: dùng thêm EKS CPU/memory; nếu node thiếu capacity thì cần theo dõi scheduling/HPA/Karpenter.
```

PR3 connector enabled:

```text
Ảnh hưởng SLO trực tiếp: Thấp đến trung bình.
Lý do: app path không đổi, nhưng MSK có thêm consumer group đọc topic orders.
Rủi ro cần monitor: MSK broker CPU/network, consumer lag, connector error/retry, S3 delivery latency.
```

## 8. So Sánh Nhanh Với Hai Hướng Khác

| Hướng                               | Ưu điểm                                                                                                     | Rủi ro / trade-off                                                                                         | Trạng thái                                 |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| AWS MSK Connect managed             | Managed, không vận hành pod                                                                                 | `CreateConnector` bị account/service restriction, không có ETA                                             | Đang block                                 |
| Firehose native MSK source          | Managed, không vận hành Kafka Connect                                                                       | Cần điều kiện IAM/Multi-VPC; broker hiện `kafka.t3.small` không support Multi-VPC; nâng instance tăng cost | Chờ quyết định/cost review                 |
| Self-managed Kafka Connect trên EKS | Dùng connector chuẩn, tận dụng S3 bucket/MSK SCRAM hiện có, không phụ thuộc MSK Connect account restriction | Team tự vận hành worker pod/image/sizing/upgrade; cần kiểm soát resource và rollout                        | Plan này đề xuất làm fallback có kiểm soát |
| Custom consumer tự code             | Linh hoạt tối đa                                                                                            | Engineering cost cao: offset, retry, duplicate, DLQ, schema, replay, backpressure phải tự làm              | Không nên chọn nếu Kafka Connect khả thi   |

## 9. Sizing Ban Đầu Đề Xuất

Bắt đầu với 1 replica:

```yaml
replicas: 1
resources:
    requests:
        cpu: 250m
        memory: 768Mi
    limits:
        cpu: 1000m
        memory: 1536Mi
heapOpts: -Xms256m -Xmx512m
```

Lý do bắt đầu 1 replica:

- Đây là archive pipeline, không phải request path synchronous.
- 1 worker giúp giảm complexity lúc đầu: rebalance, duplicate, task assignment, plugin/image issue.
- Sau khi có metric throughput/lag thật, mới quyết định tăng replica hoặc tasks.
- Nếu cần HA hơn, có thể tăng worker replica và cấu hình connector/task phù hợp ở PR sau.

## 10. Open Questions Cần PM/Tech Lead Chốt

- Có chấp nhận chọn self-managed Kafka Connect làm fallback chính nếu Firehose không đi tiếp không?
- Có yêu cầu bật worker và connector trong cùng PR hay tách worker/connector thành hai gate?
- Image Kafka Connect sẽ build trong repo chính hay dùng image nội bộ khác đã có pipeline ký số?
- Có cần 2 replica ngay từ đầu không, hay bắt đầu 1 replica rồi tăng sau khi có evidence?
- Connector config nên được quản lý bằng GitOps manifest/job/script hay thao tác REST có evidence?
- DLQ topic `orders-archive-dlq` có cần tạo trước trong scope REL-22 không?
- Có cần yêu cầu CDO04 review capacity EKS/MSK trước PR2 không?

## 11. Quyết Định Cần Xin Review

Đề xuất gửi PM/Tech Lead review theo hướng:

```text
CDO08 đề xuất giữ Firehose là hướng managed nếu cost/instance upgrade được duyệt.
Nếu Firehose không được duyệt vì cost hoặc broker instance change, chọn self-managed Kafka Connect trên EKS thay vì custom consumer tự code.
PR1 foundation đã chuẩn bị theo hướng an toàn, disabled mặc định, không ảnh hưởng runtime.
Sau khi có quyết định, CDO08 sẽ làm PR2 để build/sign image và bật worker có kiểm soát, rồi PR3 để tạo connector orders -> S3 và verify RPO.
```

## 12. Review Checklist

- [ ] PM/Tech Lead xác nhận self-managed Kafka Connect là fallback được chấp nhận nếu Firehose không đi tiếp.
- [ ] PM/Tech Lead xác nhận PR1 foundation có thể merge trước vì không bật runtime.
- [ ] CDO04/Platform xác nhận EKS capacity đủ cho worker request ban đầu.
- [ ] Security xác nhận IRSA policy chỉ write archive prefix, không có delete permission.
- [ ] CI xác nhận Helm/Terraform pass.
- [ ] Trước PR2 có image digest/signature rõ ràng để tránh Kyverno deny.
- [ ] Trước PR3 có kế hoạch monitor SLO, MSK broker metric, connector log và S3 object latency.
