# CDO08-REL-25 - Evidence drill replay MSK orders archive

Video evidence: <https://drive.google.com/file/d/1Y128WqLHrLTd4oXJ1JCCOZVcLfD2YYBN/view?usp=sharing>

## Phạm vi an toàn của drill

Đây là MSK replay drill ở môi trường có kiểm soát. Script không produce vào topic production `orders`, không xóa archive trên S3 và không sửa Kafka Connect connector đang chạy.

Trong quá trình drill, script chỉ tạo một topic tạm:

```text
orders-replay-drill-rel25-20260727-msk-demo
```

Topic này dùng để replay dữ liệu đọc từ S3 archive, validate record count/hash/marker, rồi bị xóa ở cleanup. Production topic `orders` vẫn tồn tại sau drill.

## Kết luận

REL-25 MSK replay drill đã PASS.

Drill chứng minh archive của topic `orders` trên S3 có thể được đọc lại theo time window, parse/normalize, replay vào topic cô lập, consume lại để đối chiếu và cleanup sau khi hoàn tất.

Kết quả cuối từ log:

```text
REL25_MSK_REPLAY_DRILL=PASS
drill_id=rel25-20260727-msk-demo
target_topic=orders-replay-drill-rel25-20260727-msk-demo
source_window=2026-07-27T05:00:00Z->2026-07-27T06:00:00Z
validation=PASS
failed=0
replayed=53
drill_topic_present=false
production_topic_present=true
```

Ý nghĩa:

- `REL25_MSK_REPLAY_DRILL=PASS`: toàn bộ demo preflight, guardrail, replay, validate và cleanup đã chạy thành công.
- `validation=PASS`: consumed records khớp manifest replay, không thiếu record, không duplicate target id, không mismatch hash.
- `failed=0`: không có record lỗi trong quá trình parse hoặc validate.
- `replayed=53`: replay thành công 53 source records từ archive.
- `drill_topic_present=false`: topic drill đã được cleanup.
- `production_topic_present=true`: topic production `orders` vẫn tồn tại sau drill.

## Thông tin drill

| Field | Value |
|---|---|
| Ngày chạy | 2026-07-27 |
| AWS account | `511825856493` |
| Region | `us-east-1` |
| MSK cluster | `techx-tf4-orders` |
| Production topic | `orders` |
| Archive bucket | `tf4-msk-orders-archive-511825856493-us-east-1` |
| Archive prefix | `orders/orders` |
| Archive window | `2026-07-27T05:00:00Z` -> `2026-07-27T06:00:00Z` |
| Drill ID | `rel25-20260727-msk-demo` |
| Drill topic | `orders-replay-drill-rel25-20260727-msk-demo` |
| Kafka Connect deployment | `techx-tf4/kafka-connect-orders-archive` |
| Kafka Connect connector | `orders-s3-archive` |
| Objects read | `53` |
| Records read | `53` |
| Records replayed | `53` |
| Failed records | `0` |
| Validation | `PASS` |
| Cleanup | PASS |

## Thời gian chạy

| Stage | Thời gian |
|---|---:|
| Preflight archive window | `30s` |
| Live replay tới khi write report PASS | `77s` |
| Cleanup topic/group/temp files | `28s` |
| Tổng live drill gồm cleanup | `105s` |

Lưu ý: đây là thời gian của MSK archive replay drill vào topic cô lập. Nó không phải failover AZ và không thay thế RDS PITR RTO.

## Flow đã thực hiện

### 1. `demo_summary`

Mục đích: in rõ phạm vi drill để người quay video và mentor thấy drill đang làm gì.

Stage này xác nhận:

- production topic là `orders`;
- drill topic là `orders-replay-drill-rel25-20260727-msk-demo`;
- source archive window là `2026-07-27T05:00:00Z` đến `2026-07-27T06:00:00Z`;
- drill không produce vào topic production `orders`.

Evidence:

```text
Purpose: prove MSK orders archive can be replayed into an isolated drill topic.
Production topic: orders
Drill topic: orders-replay-drill-rel25-20260727-msk-demo
Archive window: 2026-07-27T05:00:00Z -> 2026-07-27T06:00:00Z
Production safety: this demo never produces to topic orders.
```

### 2. `local_syntax_check`

Mục đích: kiểm tra script có thể chạy được trước khi đụng AWS/Kubernetes/MSK.

Stage này chạy:

- `bash -n` cho shell scripts;
- `python3 -m py_compile` cho Python archive parser.

Evidence:

```text
syntax_check=PASS
```

### 3. `runtime_baseline`

Mục đích: xác nhận đang thao tác đúng account/cluster và Kafka Connect archive đang khỏe.

Stage này xác nhận:

- AWS account là `511825856493`;
- kube context là `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`;
- deployment `kafka-connect-orders-archive` rollout thành công;
- connector `orders-s3-archive` và task `0` đều `RUNNING`.

Evidence:

```text
Account: 511825856493
deployment "kafka-connect-orders-archive" successfully rolled out
connector.state=RUNNING
task 0 state=RUNNING
```

### 4. `production_topic_before`

Mục đích: chụp baseline MSK trước drill.

Stage này list topic và describe topic production `orders`.

Evidence:

```text
orders
Topic: orders
PartitionCount: 3
ReplicationFactor: 2
Isr: 1,2
```

Trước drill chưa có topic `orders-replay-drill-rel25-20260727-msk-demo`.

### 5. `archive_window_preflight`

Mục đích: kiểm tra archive window có dữ liệu và target topic an toàn trước khi chạy replay thật.

Stage này:

- kiểm tra S3 bucket archive đọc được;
- kiểm tra Kafka Connect deployment vẫn rollout thành công;
- kiểm tra target topic hợp lệ;
- kiểm tra target topic chưa tồn tại;
- phát hiện 53 archive objects trong window;
- dừng trước bước download/create topic/produce vì `PREFLIGHT_ONLY=true`.

Evidence:

```text
archive_window_discovered prefixes=1 objects=53
preflight_only_passed no_topic_created=true objects=53
```

### 6. `negative_guardrail_production_topic`

Mục đích: chứng minh script không thể replay nhầm vào topic production `orders`.

Stage này cố tình set `TARGET_TOPIC=orders`. Script phải fail trước khi gọi replay.

Evidence:

```text
TARGET_TOPIC must match orders-replay-drill-rel25-*.
negative_guardrail=PASS target_topic_orders_rejected=true exit_code=1
```

### 7. `live_replay_to_isolated_topic`

Mục đích: chạy replay thật từ S3 archive sang topic drill cô lập.

Stage này thực hiện:

1. kiểm tra lại environment preflight;
2. kiểm tra guardrail target topic;
3. discover archive window;
4. download archive objects;
5. parse/normalize/deduplicate records;
6. tạo topic drill;
7. produce batch start marker, 53 source records và batch end marker;
8. consume lại toàn bộ 55 messages;
9. verify manifest/hash/counter;
10. ghi report;
11. cleanup consumer group, topic và file tạm.

Evidence parse/normalize:

```text
objects_read=53
records_read=53
replay_candidates=53
failed=0
duplicates_skipped=0
source_marker_candidates=53
```

Evidence topic drill:

```text
Created topic orders-replay-drill-rel25-20260727-msk-demo.
PartitionCount: 1
ReplicationFactor: 2
retention.ms=21600000
```

Evidence produce:

```text
batch_produced start_markers=1 replayed=53 end_markers=1
```

Evidence consume/validate:

```text
Processed a total of 55 messages
validation=PASS
replayed=53
failed=0
missing=0
unexpected=0
duplicate_target_ids=0
payload_mismatches=0
start_markers=1
end_markers=1
source_markers_replayed=53
```

Evidence complete:

```text
replay_passed objects_read=53 records_read=53 replayed=53 failed=0 duplicates_skipped=0 source_markers_replayed=53 control_markers_replayed=2
```

### 8. `report`

Mục đích: ghi lại kết quả machine-readable để attach vào evidence hoặc kiểm tra lại sau này.

Report runtime:

```json
{
  "drill_id": "rel25-20260727-msk-demo",
  "target_topic": "orders-replay-drill-rel25-20260727-msk-demo",
  "source_window": {
    "start": "2026-07-27T05:00:00Z",
    "end": "2026-07-27T06:00:00Z"
  },
  "completed_at": "2026-07-27T08:22:29Z",
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

Evidence:

```text
report_validation=PASS validation=PASS failed=0 replayed=53
```

### 9. `cleanup_verification`

Mục đích: xác minh không còn tài nguyên drill và production vẫn ổn.

Stage này xác nhận:

- drill topic đã bị xóa;
- production topic `orders` vẫn tồn tại;
- Kafka Connect connector và task vẫn `RUNNING`.

Evidence:

```text
drill_topic_present=false
production_topic_present=true
connector=RUNNING
task 0 state=RUNNING
```

### 10. `final_result`

Mục đích: in dòng kết luận cuối để quay video dễ nhìn.

Evidence:

```text
REL25_MSK_REPLAY_DRILL=PASS
drill_id=rel25-20260727-msk-demo
target_topic=orders-replay-drill-rel25-20260727-msk-demo
source_window=2026-07-27T05:00:00Z->2026-07-27T06:00:00Z
```

## Mapping với Mandate 20

| Mandate 20 requirement | Evidence từ drill |
|---|---|
| Có backup/archive cho stateful store trên revenue path | MSK `orders` được archive sang S3 bucket `tf4-msk-orders-archive-511825856493-us-east-1` |
| Restore/replay vào môi trường tách biệt | Replay vào topic `orders-replay-drill-rel25-20260727-msk-demo`, không replay vào `orders` |
| Có drill thật | Script đọc 53 archive objects và produce/consume/validate 55 messages trên MSK |
| Có đo kết quả read/replayed/failed | `objects_read=53`, `records_read=53`, `replayed=53`, `failed=0` |
| Không phá production | Guardrail chặn `TARGET_TOPIC=orders`; sau drill `production_topic_present=true` |
| Cleanup sau drill | `drill_topic_present=false`, consumer group/temp files được cleanup |

## Kết luận cuối

MSK orders archive replay drill **PASS** cho phạm vi REL-25/REL-26 liên quan đến Kafka/MSK.

Drill này chứng minh dữ liệu orders đã archive trên S3 có thể được replay lại vào topic cô lập, verify đầy đủ bằng counters/hash/markers và không ảnh hưởng topic production `orders`.
