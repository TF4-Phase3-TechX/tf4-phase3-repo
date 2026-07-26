# CDO08-REL-22 MSK Orders S3 Sink Runtime Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Deploy MSK Connect S3 Sink Connector for orders
**Ngày ghi nhận:** 2026-07-26

Tài liệu này ghi lại evidence runtime cho connector archive topic MSK `orders` sang S3. Evidence không chứa secret, credential hoặc payload dữ liệu production.

---

## 1. Output Của Subtask

Subtask này cần tạo ra các output sau:

- Connector/plugin/worker configuration phù hợp để consume topic `orders`.
- S3 Sink connector ghi dữ liệu sang bucket archive đã tạo ở subtask 2.
- Flush cadence <= 15 phút.
- IAM/IRSA, TLS/SASL-SCRAM và network path đủ để connector đọc MSK, ghi S3.
- Error handling/DLQ config.
- Connector status và delivery evidence.
- Restart connector không làm connector kẹt ngoài cửa sổ RPO.

Kết luận hiện tại:

| Hạng mục             | Trạng thái | Evidence chính                                                          |
| -------------------- | ---------- | ----------------------------------------------------------------------- |
| Kafka Connect worker | PASS       | Deployment `kafka-connect-orders-archive` đang `1/1 Running`            |
| S3 Sink connector    | PASS       | Connector `orders-s3-archive` state `RUNNING`                           |
| Connector task       | PASS       | Task `0` state `RUNNING`                                                |
| Topic source         | PASS       | `topics=orders`                                                         |
| S3 destination       | PASS       | `tf4-msk-orders-archive-511825856493-us-east-1`                         |
| Flush cadence        | PASS       | `rotate.schedule.interval.ms=600000` tương đương 10 phút                |
| Payload archive      | PASS       | `value.converter=StringConverter` để lưu raw value, không ép parse JSON |
| Error handling/DLQ   | PASS       | `errors.tolerance=all`, DLQ topic `orders-archive-dlq`                  |
| S3 object thật       | PASS       | Object đã xuất hiện trong prefix `orders/`                              |
| Restart connector    | PASS       | Connector/task chuyển `RESTARTING` rồi quay lại `RUNNING`               |

---

## 2. Hướng Triển Khai Thực Tế

Luồng archive đã triển khai:

```text
MSK topic orders
  -> Kafka Connect worker kafka-connect-orders-archive
  -> S3 Sink connector orders-s3-archive
  -> s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/
```

Ghi chú thay đổi so với hướng ban đầu:

- Task yêu cầu MSK Connect S3 Sink Connector cho topic `orders`.
- AWS managed MSK Connect bị block ở tầng account/service khi gọi `CreateConnector`, dù IAM simulate cho các quyền liên quan đã allowed.
- Hướng triển khai đã chuyển sang self-managed Kafka Connect chạy trong EKS, vẫn dùng Confluent S3 Sink Connector để đáp ứng mục tiêu archive `orders` sang S3.

Kết luận: thay đổi hướng triển khai không đổi mục tiêu kỹ thuật của subtask; connector vẫn là Kafka Connect S3 Sink và vẫn archive topic `orders` sang S3.

---

## 3. Connector Configuration

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/kafka-connect-orders-archive -- curl -s http://localhost:8083/connectors/orders-s3-archive/config
```

Output chính:

```json
{
    "name": "orders-s3-archive",
    "connector.class": "io.confluent.connect.s3.S3SinkConnector",
    "topics": "orders",
    "s3.bucket.name": "tf4-msk-orders-archive-511825856493-us-east-1",
    "topics.dir": "orders",
    "storage.class": "io.confluent.connect.s3.storage.S3Storage",
    "format.class": "io.confluent.connect.s3.format.json.JsonFormat",
    "key.converter": "org.apache.kafka.connect.storage.StringConverter",
    "value.converter": "org.apache.kafka.connect.storage.StringConverter",
    "partitioner.class": "io.confluent.connect.storage.partitioner.TimeBasedPartitioner",
    "path.format": "'topic=orders'/'year'=YYYY/'month'=MM/'day'=dd/'hour'=HH",
    "partition.duration.ms": "3600000",
    "rotate.schedule.interval.ms": "600000",
    "flush.size": "100",
    "errors.tolerance": "all",
    "errors.deadletterqueue.topic.name": "orders-archive-dlq",
    "errors.deadletterqueue.topic.replication.factor": "2"
}
```

Kết luận:

- Connector consume đúng topic `orders`.
- Connector ghi vào bucket `tf4-msk-orders-archive-511825856493-us-east-1`.
- Flush theo lịch 10 phút, nhỏ hơn yêu cầu RPO 15 phút.
- `StringConverter` được dùng cho value để archive raw order payload, tránh lỗi parse khi message không phải JSON object hợp lệ.
- DLQ/error handling đã có cấu hình cơ bản.

---

## 4. Connector Runtime Status

Lệnh kiểm tra:

```powershell
kubectl -n techx-tf4 exec deploy/kafka-connect-orders-archive -- curl -s http://localhost:8083/connectors/orders-s3-archive/status
```

Output:

```json
{
    "name": "orders-s3-archive",
    "connector": {
        "state": "RUNNING",
        "worker_id": "kafka-connect-orders-archive-7d948c46f7-cwnd9:8083",
        "version": "12.1.8"
    },
    "tasks": [
        {
            "id": 0,
            "state": "RUNNING",
            "worker_id": "kafka-connect-orders-archive-7d948c46f7-cwnd9:8083",
            "version": "12.1.8"
        }
    ],
    "type": "sink"
}
```

Kết luận:

- Connector `orders-s3-archive` đang `RUNNING`.
- Task `0` đang `RUNNING`.
- S3 Sink Connector version đang chạy là `12.1.8`.

---

## 5. S3 Archive Object Evidence

Lệnh kiểm tra:

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/ --recursive --profile tf4 --region us-east-1
```

Output mẫu:

```text
2026-07-26 17:21:19      27066 orders/orders/topic=orders/year=2026/month=07/day=17/hour=19/orders+0+0000120492.json
2026-07-26 17:21:20      11511 orders/orders/topic=orders/year=2026/month=07/day=17/hour=20/orders+0+0000120560.json
2026-07-26 17:21:20      39841 orders/orders/topic=orders/year=2026/month=07/day=17/hour=20/orders+0+0000120592.json
2026-07-26 17:21:20      38328 orders/orders/topic=orders/year=2026/month=07/day=17/hour=20/orders+0+0000120692.json
2026-07-26 17:21:20      40253 orders/orders/topic=orders/year=2026/month=07/day=17/hour=20/orders+0+0000120792.json
2026-07-26 17:21:20      24234 orders/orders/topic=orders/year=2026/month=07/day=17/hour=20/orders+0+0000120892.json
2026-07-26 17:21:20      15678 orders/orders/topic=orders/year=2026/month=07/day=17/hour=21/orders+0+0000120952.json
2026-07-26 17:21:21      39690 orders/orders/topic=orders/year=2026/month=07/day=17/hour=21/orders+0+0000120992.json
2026-07-26 17:21:21      38740 orders/orders/topic=orders/year=2026/month=07/day=17/hour=21/orders+0+0000121092.json
2026-07-26 17:21:21      38593 orders/orders/topic=orders/year=2026/month=07/day=17/hour=21/orders+0+0000121192.json
```

Kết luận:

- S3 archive bucket đã có object thật từ connector.
- Actual runtime prefix hiện tại là `orders/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`.
- Prefix này hơi khác convention ban đầu `orders/topic=orders/...` do cấu hình `topics.dir=orders` cộng với `path.format` cũng chứa `topic=orders`. Đây không block backup/replay, nhưng subtask 4 cần dùng đúng actual prefix này khi parse object.

---

## 6. Restart Connector Evidence

Lệnh restart:

```powershell
kubectl -n techx-tf4 exec deploy/kafka-connect-orders-archive -- curl -s -X POST "http://localhost:8083/connectors/orders-s3-archive/restart?includeTasks=true"
```

Output restart:

```json
{
    "name": "orders-s3-archive",
    "connector": {
        "state": "RESTARTING",
        "worker_id": "kafka-connect-orders-archive-7d948c46f7-cwnd9:8083",
        "version": "12.1.8"
    },
    "tasks": [
        {
            "id": 0,
            "state": "RESTARTING",
            "worker_id": "kafka-connect-orders-archive-7d948c46f7-cwnd9:8083",
            "version": "12.1.8"
        }
    ],
    "type": "sink"
}
```

Lệnh kiểm tra sau restart:

```powershell
kubectl -n techx-tf4 exec deploy/kafka-connect-orders-archive -- curl -s http://localhost:8083/connectors/orders-s3-archive/status
```

Output sau restart:

```json
{
    "name": "orders-s3-archive",
    "connector": {
        "state": "RUNNING",
        "worker_id": "kafka-connect-orders-archive-7d948c46f7-cwnd9:8083",
        "version": "12.1.8"
    },
    "tasks": [
        {
            "id": 0,
            "state": "RUNNING",
            "worker_id": "kafka-connect-orders-archive-7d948c46f7-cwnd9:8083",
            "version": "12.1.8"
        }
    ],
    "type": "sink"
}
```

Kết luận:

- Restart request được nhận.
- Connector/task chuyển sang `RESTARTING`.
- Connector/task quay lại `RUNNING` ngay sau đó.
- Evidence này chứng minh connector không bị kẹt sau restart. Kiểm chứng không thiếu marker sau restart sẽ được thực hiện sâu hơn ở subtask 4.

---

## 7. Acceptance Criteria Mapping

| Acceptance Criteria                                      | Evidence                                                                 | Kết quả                                                                  |
| -------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| Connector RUNNING                                        | Kafka Connect REST status shows connector `RUNNING`                      | PASS                                                                     |
| Orders xuất hiện trong S3                                | `aws s3 ls .../orders/ --recursive` shows archive objects                | PASS                                                                     |
| Độ trễ archive <= 15 phút trong test                     | Connector config `rotate.schedule.interval.ms=600000`                    | PASS cho runtime config; đo marker latency chi tiết ở subtask 4          |
| Payload giữ đủ order ID, timestamp và dữ liệu cần replay | Connector archives raw value using `StringConverter`; S3 objects present | PASS cho raw archive path; field-level parse và marker check ở subtask 4 |
| Restart connector không tạo mất dữ liệu vượt RPO         | Restart test shows connector/task return to `RUNNING`                    | PASS cho restart readiness; no-missing marker validation ở subtask 4     |

---

## 8. Ghi Chú Vận Hành

- Connector hiện dùng self-managed Kafka Connect trên EKS, không dùng AWS managed MSK Connect vì account/service restriction với `CreateConnector`.
- Không thay đổi app traffic path. Checkout/accounting/fraud-detection vẫn dùng MSK SCRAM connection hiện có.
- Connector dùng `StringConverter` vì runtime từng ghi nhận `JsonParseException` khi dùng `JsonConverter` với payload `orders` không phải JSON object hợp lệ.
- Actual S3 prefix `orders/orders/topic=orders/...` cần được dùng làm input cho script đọc/parse ở subtask 4.

---

## 9. Bước Tiếp Theo

Chuyển sang subtask 4:

- Tạo batch order markers.
- Đọc S3 object bằng script/tool độc lập.
- So sánh order IDs produce với records archived.
- Ghi nhận duplicate/missing records và delivery latency.
