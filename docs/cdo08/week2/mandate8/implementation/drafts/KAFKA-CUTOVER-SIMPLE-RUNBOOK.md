# REL-17 Kafka Cutover — Simple Runbook

## 1. Bật Blue-Green cho `checkout`

Sửa `tf4-phase3-gitops-manifests/environments/production/app-values.yaml`:

```yaml
rollouts:
  enabled: true
components:
  checkout: { useRollout: true }
```

Commit, push, tạo PR, merge.

```bash
kubectl argo rollouts get rollout checkout -n techx-tf4
```

## 2. Giai đoạn A — Cutover Producer (`checkout`)

```bash
STAGE=producer "/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/08-set-kafka-cutover-stage.sh"
```

Merge PR bot tạo.

```bash
kubectl argo rollouts get rollout checkout -n techx-tf4
kubectl logs -n techx-tf4 -l opentelemetry.io/name=checkout -c checkout --since=10m --tail=200
```

## 3. Gate — đo lag chính xác (offset MM2 đã commit vs end-offset self-hosted)

```bash
"/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/10-check-mm2-exact-lag.sh"
```

Output khi OK (exit 0):
```
>> End-offset that su tren self-hosted (orders:0)
self-hosted end-offset = 235299

>> Offset MM2 da commit doc xong (Connect REST API /connectors/.../offsets)
{"offsets":[{"partition":{"cluster":"self-hosted","partition":0,"topic":"orders"},"offset":{"offset":235298}}]}

MM2 da doc toi offset = 235298
LAG chinh xac = 1
OK — lag <= 5, du an toan de Promote.
```
`LAG_THRESHOLD` mặc định 5 (gần 0, không cần đúng tuyệt đối 0 vì traffic vẫn đang chạy live). Exit 1 = lag > 5, đợi rồi chạy lại. Exit 2 = không parse được JSON (đọc JSON in ra sửa lại script).

(Script cũ `09-check-mm2-catchup.sh` — so tốc độ tăng 2 mốc — vẫn còn, dùng khi muốn xem nhanh xu hướng, không phải con số lag chính xác.)

## 4. Promote Producer

```bash
ROLLOUT=checkout "/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/04-promote-producers.sh"
```

## 5. Giai đoạn B — Cutover Consumer (`accounting`, `fraud-detection`)

```bash
STAGE=consumer "/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/08-set-kafka-cutover-stage.sh"
```

Merge PR bot tạo.

```bash
kubectl rollout status deployment/accounting -n techx-tf4 --timeout=120s
kubectl rollout status deployment/fraud-detection -n techx-tf4 --timeout=120s
kubectl logs -n techx-tf4 -l opentelemetry.io/name=accounting --since=10m --tail=200
kubectl logs -n techx-tf4 -l opentelemetry.io/name=fraud-detection --since=10m --tail=200
```

## 6. Event parity check

Không cần tự tạo order test — `load-generator` đang chạy sẵn, liên tục sinh traffic thật.

```bash
"/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/11-verify-event-flow.sh"
```

**"Xong" = cả 3 điều kiện dưới đây đúng cùng lúc** (script tự check hết, in `[OK]`/`[FAIL]` từng dòng):
1. Cả 3 service (`checkout`/`accounting`/`fraud-detection`) đã có `KAFKA_SECURITY_PROTOCOL` — tức đã trỏ MSK thật, không phải còn self-hosted.
2. Log 5 phút gần nhất không có lỗi kết nối/SASL.
3. Consumer group `accounting`/`fraud-detection` trên MSK có **active member thật** (cột `CONSUMER-ID`/`HOST` khác `-`) — **không chỉ nhìn `LAG=0`**, vì MM2 tự sync checkpoint offset định kỳ nên `LAG` có thể ra số nhỏ/0 ngay cả khi chưa ai thật sự consume (`no active members`).

Exit 0 = xong thật, exit 1 = còn thiếu (đọc dòng `[FAIL]` để biết thiếu gì).

## 7. Rollback

`checkout` còn `Paused` (chưa Promote):

```bash
ROLLOUTS="checkout" "/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/rollback-01-abort-rollout.sh"
```

Đã Promote/Recreate:

```bash
STAGE=off "/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/08-set-kafka-cutover-stage.sh"
```

Merge PR bot tạo, rồi:

```bash
kubectl argo rollouts promote checkout -n techx-tf4
```

Đã có order ghi MSK (thủ công, cần 2 người xác nhận):

```bash
kubectl exec -n techx-tf4 orders-mirrormaker2-mirrormaker2-0 -- sh -c \
  "grep -v '^group.id=' /tmp/strimzi-connect.properties > /tmp/peek.properties && \
   timeout 30 /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096 --command-config /tmp/peek.properties --topic orders --partition 0 --offset <N-1> --max-messages 1 --timeout-ms 15000 --property print.timestamp=true --property print.offset=true && rm -f /tmp/peek.properties"
"/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/rollback-02-reset-offsets.sh"
```

## 8. Cleanup

```bash
"/e/Project/Learn-Project/XBrain/tf4-phase3-repo/docs/cdo08/week2/mandate8/scripts/kafka/07-cleanup.sh"
```
