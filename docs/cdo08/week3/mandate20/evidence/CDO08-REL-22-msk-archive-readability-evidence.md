# CDO08-REL-22 MSK Archive Completeness And Readability Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Validate MSK archive completeness and readability
**Ngày ghi nhận:** 2026-07-27

Tài liệu này ghi lại evidence cho batch marker mới của MSK topic `orders`, chứng minh archive không chỉ có object mà còn đọc và map lại được. Evidence không chứa secret hoặc credential.

---

## 1. Output Của Subtask

Subtask này cần tạo ra các output sau:

- Batch order markers được produce vào topic `orders`.
- So sánh marker produced với records/object archived trong S3.
- Parse object bằng script/tool độc lập.
- Ghi nhận duplicate/missing records và delivery latency.
- Lưu script/read command để tái sử dụng khi replay/drill.

Kết luận hiện tại:

| Hạng mục             | Trạng thái | Evidence chính                                                                                            |
| -------------------- | ---------- | --------------------------------------------------------------------------------------------------------- |
| Batch markers        | PASS       | 50 marker `rel22-marker-20260727122436-001..050`                                                          |
| Connector runtime    | PASS       | Connector/task `orders-s3-archive` đều `RUNNING`                                                          |
| S3 object mới        | PASS       | 50 object `.bin` mới trong prefix ngày `2026-07-27/hour=05`                                               |
| Parse object         | PASS       | 50/50 object parse được bằng script/tool độc lập                                                          |
| Produced vs archived | PASS       | Produced `50`, archived `50`, parsed `50`                                                                 |
| Missing records      | PASS       | `0` missing marker                                                                                        |
| Duplicate records    | PASS       | `0` duplicate `order_id`                                                                                  |
| Lossless/readability | PASS       | Không có UTF-8 replacement char trong 50/50 object                                                        |
| Delivery latency     | PASS       | Marker created `2026-07-27T05:24:36Z`, S3 objects visible `2026-07-27 12:24:49-59 +07`, khoảng 13-23 giây |

---

## 2. Batch Marker Produce

Batch marker được produce trực tiếp vào MSK topic `orders` bằng Kafka CLI trong pod Kafka Connect. Cách này dùng tool độc lập với checkout app để không phụ thuộc blocker hiện tại của checkout publish path.

Lệnh produce batch 50 đã chạy:

```powershell
$batch = "rel22-marker-$(Get-Date -Format yyyyMMddHHmmss)"
$now = Get-Date -AsUTC -Format o
$payloads = 1..50 | ForEach-Object {
  $id = "{0}-{1:D3}" -f $batch, $_
  "{`"marker_id`":`"$id`",`"order_id`":`"$id`",`"source`":`"rel22-subtask4-batch50`",`"created_at`":`"$now`"}"
}

$payloads -join "`n" | kubectl -n techx-tf4 exec -i deploy/kafka-connect-orders-archive -- bash -lc '
cat > /tmp/producer.properties <<EOF
security.protocol=$CONNECT_SECURITY_PROTOCOL
sasl.mechanism=$CONNECT_SASL_MECHANISM
sasl.jaas.config=$CONNECT_SASL_JAAS_CONFIG
EOF
/opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server "$CONNECT_BOOTSTRAP_SERVERS" \
  --command-config /tmp/producer.properties \
  --topic orders
'
"Batch=$batch Count=50 CreatedAt=$now"
```

Output runtime:

```text
Batch=rel22-marker-20260727122436 Count=50 CreatedAt=2026-07-27T05:24:36.2899364Z
```

Kết luận:

- Lệnh produce hoàn tất, không có error.
- Batch có 50 marker để drill kiểm tra missing/duplicate/readability có ý nghĩa hơn batch smoke test 3 record.

---

## 3. Connector Status

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

---

## 4. S3 Object Evidence

Lệnh kiểm tra:

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/ --profile tf4 --region us-east-1 | Select-Object -Last 60
```

Output chính:

```text
2026-07-27 12:24:49        171 orders+2+0000000000.bin
2026-07-27 12:24:50        171 orders+2+0000000001.bin
...
2026-07-27 12:24:59        171 orders+2+0000000048.bin
2026-07-27 12:24:59        171 orders+2+0000000049.bin
```

Full prefix:

```text
s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/
```

Kết luận:

- 50 marker mới đã được archive thành 50 object `.bin`.
- Actual prefix runtime: `orders/orders/topic=orders/year=YYYY/month=MM/day=DD/hour=HH/`.
- Object extension `.bin` xác nhận connector đang dùng ByteArray archive path, không còn JSON/String archive cũ.

---

## 5. Independent Parse Evidence

Script tái sử dụng:

```text
scripts/cdo08/verify-msk-orders-s3-archive-readability.ps1
```

Với batch 50 object, để chạy nhanh có thể sync prefix về temp rồi parse local:

```powershell
$tmp = Join-Path $env:TEMP 'rel22-msk-archive-batch50'
Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

aws s3 sync s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/ $tmp `
  --exclude '*' `
  --include 'orders+2+*.bin' `
  --profile tf4 `
  --region us-east-1 `
  --no-progress
```

Output parse summary:

```text
DownloadedObjects      : 50
ParsedObjects          : 50
UniqueOrderIds         : 50
DuplicateOrderIds      : 0
MissingOrderIds        : 0
Utf8ReplacementObjects : 0
FirstMarker            : rel22-marker-20260727122436-001
LastMarker             : rel22-marker-20260727122436-050
```

Kết luận:

- 50/50 object parse thành công bằng tool độc lập ngoài Kafka Connect.
- `marker_id` và `order_id` map lại đúng 50 unique records.
- Không có object nào chứa UTF-8 replacement char.

---

## 6. Produced Vs Archived Report

| Metric                    | Giá trị |
| ------------------------- | ------: |
| Produced markers          |      50 |
| Archived objects          |      50 |
| Parsed objects            |      50 |
| Missing markers           |       0 |
| Duplicate order IDs       |       0 |
| UTF-8 replacement objects |       0 |

Delivery latency observed:

| Marker created_at      | S3 visible time           |        Latency |
| ---------------------- | ------------------------- | -------------: |
| `2026-07-27T05:24:36Z` | `2026-07-27 12:24:49 +07` | khoảng 13 giây |
| `2026-07-27T05:24:36Z` | `2026-07-27 12:24:59 +07` | khoảng 23 giây |

Kết luận:

- Không thiếu marker ngoài cửa sổ RPO 15 phút.
- Delivery latency observed nhỏ hơn 15 phút.
- Batch này có thể dùng làm input evidence cho REL-25 drill/readability validation.

---

## 7. Output Cung Cấp Cho Drill

Bucket:

```text
tf4-msk-orders-archive-511825856493-us-east-1
```

Prefix/time window:

```text
orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/
```

Object range:

```text
orders+2+0000000000.bin -> orders+2+0000000049.bin
```

Marker/order ID range:

```text
rel22-marker-20260727122436-001 -> rel22-marker-20260727122436-050
```

---

## 8. Ghi Chú Về Blocker Checkout Publish Path

Trong quá trình chuẩn bị subtask 4, checkout path chưa tạo record mới vào MSK `orders`, dù archive runtime vẫn chạy đúng. Để không block drill, batch marker được produce trực tiếp bằng Kafka CLI trong Kafka Connect pod.

Kết luận:

- Blocker checkout publish path không nằm ở S3 archive connector.
- Khi MSK có record mới, connector archive sinh object `.bin` đúng như kỳ vọng.
- Việc fix/soi checkout publish path là issue riêng, ngoài scope của REL-22 subtask validate archive completeness/readability; phần này có thể xử lý bằng task/PR riêng và không chặn evidence của archive pipeline.

