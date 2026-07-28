# CDO08-REL-25 - MSK Orders Archive Replay Evidence

**Subtask:** Build MSK orders archive replay procedure
**Ngày kiểm tra:** 2026-07-27
**AWS account:** `511825856493`
**Region:** `us-east-1`

## 1. Mục tiêu evidence

Chứng minh:

- orders archive thật đọc được theo time window;
- protobuf hoặc JSON marker payload được parse/normalize và key theo
  `order_id/correlation_id`;
- duplicate được kiểm soát;
- replay có đủ start/end batch markers;
- report có `read/replayed/failed`;
- không produce vào production topic `orders`;
- topic/group/file tạm được cleanup sau drill.

Evidence không chứa database/Kafka password, AWS session token hoặc order payload.

## 2. Trạng thái trước drill

### AWS và MSK

```text
AWS account: 511825856493
MSK cluster: techx-tf4-orders
Cluster state: ACTIVE
Cluster type: PROVISIONED
Production topic: orders
```

### Archive writer

```text
Deployment: techx-tf4/kafka-connect-orders-archive
Deployment ready: 1/1
Connector: orders-s3-archive
Connector state: RUNNING
Task 0 state: RUNNING
Connector version: 12.1.8
```

Runtime connector format:

```text
format.class=io.confluent.connect.s3.format.bytearray.ByteArrayFormat
value.converter=org.apache.kafka.connect.converters.ByteArrayConverter
key.converter=org.apache.kafka.connect.storage.StringConverter
topics.dir=orders
path.format='topic=orders'/'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH
rotate.schedule.interval.ms=600000
flush.size=1
```

### S3 archive

```text
Bucket: tf4-msk-orders-archive-511825856493-us-east-1
Observed prefix: orders/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/
Archive objects present: YES
Live drill object classification: lossless raw JSON batch marker `.bin`
```

### Topic baseline

Các topic quan sát trước implementation:

```text
__amazon_msk_canary
__consumer_offsets
mm2-configs
mm2-offsets
mm2-status
orders
orders-archive-connect-configs
orders-archive-connect-offsets
orders-archive-connect-status
orders-archive-dlq
self-hosted.checkpoints.internal
```

Không có topic `orders-replay-drill-rel25-*`.

## 3. Thay đổi được triển khai

```text
docs/cdo08/week3/mandate20/scripts/msk/rel25-replay-orders-archive.sh
docs/cdo08/week3/mandate20/scripts/msk/lib/rel25-replay-common.sh
docs/cdo08/week3/mandate20/scripts/msk/rel25-orders-archive-tool.py
docs/cdo08/week3/mandate20/implementation/CDO08-REL-25-msk-orders-archive-replay-runbook.md
docs/cdo08/week3/mandate20/evidence/CDO08-REL-25-MSK-ORDERS-REPLAY-EVIDENCE.md
```

## 4. Safety evidence trước live run

| Kiểm tra | Kết quả |
| --- | --- |
| Target naming chỉ cho `orders-replay-drill-rel25-*` | PASS |
| Negative test với target `orders` | PASS, exit `1` trước AWS/Kafka |
| Target topic chưa tồn tại | PASS |
| `bash -n` entrypoint/common | PASS |
| Python compile | PASS |
| Secret pattern scan | PASS |
| `git diff --check` | PASS |
| Preflight-only không tạo topic | PASS, exit `0`, objects `53` |

Synthetic byte-safe fixture test:

```text
objects_read=1
records_read=3
replay_candidates=2
duplicates_skipped=1
failed=0
start_markers=1
end_markers=1
replayed=2
missing=0
payload_mismatches=0
duplicate_target_ids=0
validation=PASS
```

Fixture chỉ dùng UUID giả, được tạo trong temporary directory và đã xóa sau
test. Test này chứng minh parser/dedup/marker/verifier hoạt động khi input
byte-safe; nó không thay thế live archive evidence.

## 5. Live drill input

```text
RESTORE_DRILL_ID: rel25-20260727-msk-live-c
START_TIME: 2026-07-27T05:00:00Z
END_TIME: 2026-07-27T06:00:00Z
TARGET_TOPIC: orders-replay-drill-rel25-20260727-msk-live-c
ARCHIVE OBJECT TYPE: lossless JSON batch marker .bin
```

Topic drill được tạo với:

```text
PartitionCount: 1
ReplicationFactor: 2
cleanup.policy=delete
retention.ms=21600000
```

## 6. Live replay result

| Counter | Kết quả |
| --- | --- |
| Objects read | `53` |
| Records read | `53` |
| Replay candidates | `53` |
| Replayed | `53` |
| Failed | `0` |
| Duplicates skipped | `0` |
| Conflicting duplicates | `0` |
| Source batch markers replayed | `53` |
| Replay control start markers | `1` |
| Replay control end markers | `1` |
| Missing | `0` |
| Unexpected | `0` |
| Duplicate target IDs | `0` |
| Payload hash mismatch | `0` |
| Diagnostic lines ignored | `2` |
| Validation | `PASS` |
| Script exit code | `0` |

Hai diagnostic lines là Kafka CLI status text bị `kubectl exec` trộn vào captured
stream. Chúng không phải Kafka records. Validation vẫn yêu cầu chính xác 55
messages: 53 source markers, một `BATCH_START` và một `BATCH_END`.

Runtime PASS report được gom trực tiếp vào evidence:

```json
{
  "drill_id": "rel25-20260727-msk-live-c",
  "target_topic": "orders-replay-drill-rel25-20260727-msk-live-c",
  "source_window": {
    "start": "2026-07-27T05:00:00Z",
    "end": "2026-07-27T06:00:00Z"
  },
  "counters": {
    "objects_read": 53,
    "records_read": 53,
    "replayed": 53,
    "failed": 0,
    "duplicates_skipped": 0,
    "source_markers_replayed": 53,
    "control_markers_replayed": 2
  },
  "validation": "PASS"
}
```

Log quyết định:

```text
batch_produced start_markers=1 replayed=53 end_markers=1
Processed a total of 55 messages
validation=PASS
replay_passed objects_read=53 records_read=53 replayed=53 failed=0
source_markers_replayed=53 control_markers_replayed=2
live_exit=0
```

## 7. Trạng thái sau drill và cleanup

| Resource/check | Trước drill | Sau drill |
| --- | --- | --- |
| MSK `techx-tf4-orders` | `ACTIVE` | `ACTIVE`, không thay đổi |
| Production topic `orders` | 3 partitions, RF 2 | Vẫn tồn tại |
| Archive connector/task | `RUNNING` | `RUNNING` |
| S3 orders archive | 53 `.bin` trong window | Không bị sửa/xóa |
| Topic `orders-replay-drill-rel25-20260727-msk-live-c` | Không tồn tại | `drill_topic_present=False` |
| Drill consumer group | Không tồn tại | `drill_group_present=False` |
| Temporary payload files | Không tồn tại | `temp_remnant_count=0` |
| JSON PASS report | Chưa có | Đã tạo |

Independent cleanup:

```text
drill_topic_present=False
production_topic_present=True
drill_group_present=False
connector state=RUNNING
task 0 state=RUNNING
temp_remnant_count=0
```

## 8. Legacy integrity attempt

Trước khi có `.bin`, script đã thử window legacy
`2026-07-22T02:00:00Z` đến `03:00:00Z`:

```text
objects_read=2
records_read=50
replay_candidates=0
failed=50
```

50/50 JSON string records chứa `U+FFFD`, nên script dừng trước tạo topic. Failure
report được giữ ngay trong file này để chứng minh integrity gate:

```json
{
  "batch_id": "rel25-20260727-msk",
  "conflicting_duplicates": 0,
  "duplicates_skipped": 0,
  "failed": 50,
  "objects_read": 2,
  "records_read": 50,
  "replay_candidates": 0
}
```

## 9. Acceptance Criteria mapping

| Acceptance Criteria | Cơ chế | Evidence |
| --- | --- | --- |
| Đọc object theo time window | Hourly S3 prefix, start inclusive/end exclusive | PASS, 53 objects |
| Parse/normalize payload | JSON marker/protobuf detection, base64 envelope và SHA-256 | PASS |
| Produce theo order/correlation ID | Kafka key và `correlation_id` dùng marker `order_id` | PASS, 53 |
| Duplicate/idempotency | SHA-256 dedup, fresh topic và idempotent producer | PASS, duplicate 0 |
| Replay batch markers | 53 source markers + start/end control markers | PASS |
| Có read/replayed/failed | Runtime JSON report | PASS, 53/53/0 |
| Không replay production topic | Strict topic regex và negative test | PASS |
| Procedure đủ dùng trong drill | Runbook có preflight/live/cleanup/recovery | PASS |

## 10. Kết luận

Subtask **PASS** cho archive batch-marker replay procedure. Live drill đã đọc 53
lossless S3 objects, replay 53/53 markers vào topic cô lập, validation không có
missing/duplicate/hash mismatch, và cleanup độc lập xác nhận không còn topic,
consumer group hoặc temporary payload.
