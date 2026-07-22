# REL-17 Kafka -> MSK Cutover Evidence

## 1. Phạm vi

Tài liệu này ghi lại bằng chứng runtime cutover luồng event sau checkout từ Kafka self-hosted sang Amazon MSK.

Các component trong phạm vi:

- Producer: `checkout`
- Consumers: `accounting`, `fraud-detection`
- Migration bridge: `KafkaMirrorMaker2/orders-mirrormaker2`
- Namespace: `techx-tf4`

Thời gian kiểm tra:

- Pre-check, promote và post-check được thực hiện trong ngày 2026-07-22 ICT.

## 2. Trạng thái trước cutover

Trước khi promote, rollout `checkout` đang ở trạng thái blue/green pause.

Lệnh kiểm tra:

```text
kubectl argo rollouts get rollout checkout -n techx-tf4
```

Kết quả quan sát:

```text
Rollout: checkout
Status: Paused
Message: BlueGreenPause
Desired replicas: 2
Current replicas: 4
Updated replicas: 2
Ready replicas: 2

revision 7: checkout-6bfcbcdb7d, Healthy, preview
revision 6: checkout-54ff8fcc6c, Healthy, stable, active
```

Service selector trước cutover:

```text
kubectl -n techx-tf4 get svc checkout checkout-preview -o jsonpath='{range .items[*]}{.metadata.name}{" selector="}{.spec.selector}{"\n"}{end}'
```

Kết quả:

```text
checkout selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"54ff8fcc6c"}
checkout-preview selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"6bfcbcdb7d"}
```

Active revision của `checkout` vẫn dùng Kafka self-hosted:

```text
checkout-54ff8fcc6c
KAFKA_ADDR=kafka:9092
```

Preview revision của `checkout` đã dùng cấu hình MSK qua Kubernetes Secret:

```text
checkout-6bfcbcdb7d
KAFKA_ADDR=msk-kafka-secret:kafka-address
KAFKA_SECURITY_PROTOCOL=msk-kafka-secret:security-protocol
KAFKA_SASL_MECHANISM=msk-kafka-secret:sasl-mechanism
KAFKA_USERNAME=msk-kafka-secret:username
KAFKA_PASSWORD=msk-kafka-secret:password
```

Các consumer đã chuyển sang cấu hình MSK trước khi promote producer:

```text
accounting ready=1/1
KAFKA_ADDR=msk-kafka-secret:kafka-address
KAFKA_SECURITY_PROTOCOL=msk-kafka-secret:security-protocol
KAFKA_SASL_MECHANISM=msk-kafka-secret:sasl-mechanism
KAFKA_USERNAME=msk-kafka-secret:username
KAFKA_PASSWORD=msk-kafka-secret:password

fraud-detection ready=1/1
KAFKA_ADDR=msk-kafka-secret:kafka-address
KAFKA_SECURITY_PROTOCOL=msk-kafka-secret:security-protocol
KAFKA_SASL_MECHANISM=msk-kafka-secret:sasl-mechanism
KAFKA_USERNAME=msk-kafka-secret:username
KAFKA_PASSWORD=msk-kafka-secret:password
```

MirrorMaker2 đang sẵn sàng trong rollback window:

```text
kubectl -n techx-tf4 get kafkamirrormaker2 orders-mirrormaker2 -o jsonpath='{.metadata.name}{" conditions="}{range .status.conditions[*]}{.type}{":"}{.status}{" "}{end}{"\n"}'
```

Kết quả:

```text
orders-mirrormaker2 conditions=Ready:True
```

## 3. Hành động cutover

Promote `checkout` producer từ active revision dùng Kafka self-hosted sang revision dùng MSK.

Lệnh thực hiện:

```text
kubectl argo rollouts promote checkout -n techx-tf4
```

Kết quả:

```text
rollout 'checkout' promoted
```

## 4. Trạng thái sau cutover

Sau promote, `checkout` Healthy và active service đã trỏ sang revision dùng MSK.

Lệnh kiểm tra:

```text
kubectl argo rollouts get rollout checkout -n techx-tf4
```

Kết quả quan sát:

```text
Rollout: checkout
Status: Healthy
Desired replicas: 2
Current replicas: 2
Updated replicas: 2
Ready replicas: 2
Available replicas: 2

revision 7: checkout-6bfcbcdb7d, Healthy, stable, active
revision 6: checkout-54ff8fcc6c, ScaledDown
```

Service selector sau cutover:

```text
checkout selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"6bfcbcdb7d"}
checkout-preview selector={"opentelemetry.io/name":"checkout","rollouts-pod-template-hash":"6bfcbcdb7d"}
```

## 5. Evidence producer/consumer

Sau khi promote, `accounting` tiếp tục consume order event:

```text
kubectl -n techx-tf4 logs deployment/accounting --since=3m --tail=100
```

Kết quả đại diện:

```text
Order details: { "orderId": "a9676f24-8575-11f1-bb7a-e6c3e69d57b7", ... }
Order details: { "orderId": "b2463f0d-8575-11f1-bb7a-e6c3e69d57b7", ... }
Order details: { "orderId": "f0815f45-8575-11f1-ab2f-8a2288188d13", ... }
```

Sau khi promote, `fraud-detection` tiếp tục consume order event:

```text
kubectl -n techx-tf4 logs deployment/fraud-detection --since=3m --tail=100
```

Kết quả đại diện:

```text
Consumed record with orderId: a9676f24-8575-11f1-bb7a-e6c3e69d57b7, and updated total count to: 361
Consumed record with orderId: b2463f0d-8575-11f1-bb7a-e6c3e69d57b7, and updated total count to: 363
Consumed record with orderId: f0815f45-8575-11f1-ab2f-8a2288188d13, and updated total count to: 372
```

Kết luận: luồng MSK producer/consumer đã active cho post-checkout order event flow.

## 6. Trạng thái sau REL-18 cleanup

Sau khi cleanup được merge và sync/prune qua Argo CD, các runtime resource Kafka self-hosted và MirrorMaker2 không còn chạy trong namespace `techx-tf4`.

Lệnh kiểm tra:

```text
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get svc
```

Kết quả:

```text
Không còn pod kafka
Không còn pod orders-mirrormaker2
Không còn service kafka
Không còn service orders-mirrormaker2-*
```

PVC `kafka-pvc` vẫn được giữ lại tạm thời:

```text
kafka-pvc   Bound   10Gi   gp2
```

PVC này chỉ phục vụ rollback/data-retention tạm thời, không còn phục vụ traffic runtime.

## 7. Trạng thái hiện tại

Runtime cutover status:

```text
PASS
```

Các điểm đã đạt:

- `checkout` active service đã target revision MSK-backed `6bfcbcdb7d`.
- `checkout` rollout Healthy.
- `accounting` Ready và consume order event qua cấu hình MSK.
- `fraud-detection` Ready và consume order event qua cấu hình MSK.
- Kafka self-hosted đã được tắt khỏi runtime sau cleanup.
- MirrorMaker2 đã được tắt khỏi runtime sau cleanup.
- `kafka-pvc` được giữ lại tạm thời cho rollback/data-retention.

## 8. Ranh giới rollback

Nếu cần rollback trong rollback window:

1. Revert GitOps app values để `checkout`, `accounting` và `fraud-detection` quay lại cấu hình Kafka self-hosted.
2. Khôi phục Kafka/MirrorMaker2 từ GitOps nếu rollback cần replay/sync event.
3. Dùng `kafka-pvc` đang được giữ lại để hỗ trợ rollback/data investigation.
4. Không xóa `kafka-pvc` trước khi PM/owner xác nhận rollback window đã đóng.

## 9. Việc còn lại sau observation window

Các việc sau không chặn Mandate 08 runtime cutover:

1. Theo dõi SLO checkout và consumer lag MSK trong observation window.
2. Chốt thời điểm archive hoặc xóa `kafka-pvc`.
3. Cập nhật GitOps/Argo sau khi rollback window đóng để loại bỏ orphan warning liên quan resource Kafka cũ.
