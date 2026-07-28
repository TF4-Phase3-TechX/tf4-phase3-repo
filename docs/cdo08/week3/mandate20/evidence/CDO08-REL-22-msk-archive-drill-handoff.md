# CDO08-REL-22 MSK Archive Drill Handoff

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Validate MSK archive completeness and readability
**Ngày ghi nhận:** 2026-07-27
**Recipient:** REL-25 drill owner/team

Tài liệu này cung cấp batch S3 archive mới để REL-25 dùng cho read/replay drill. Batch này là marker có kiểm soát, được produce trực tiếp vào MSK topic `orders` bằng Kafka CLI trong pod Kafka Connect, sau đó được connector archive sang S3.

---

## 1. Drill Input Package

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

Full S3 prefix:

```text
s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/
```

Marker/order ID range:

```text
rel22-marker-20260727122436-001 -> rel22-marker-20260727122436-050
```

---

## 2. Runtime Verification Summary

| Check                     | Result                      |
| ------------------------- | --------------------------- |
| Connector                 | `orders-s3-archive` RUNNING |
| Task                      | task `0` RUNNING            |
| Produced markers          | 50                          |
| Archived objects          | 50                          |
| Parsed objects            | 50                          |
| Unique order IDs          | 50                          |
| Missing markers           | 0                           |
| Duplicate order IDs       | 0                           |
| UTF-8 replacement objects | 0                           |
| Object format             | `.bin` ByteArray lossless   |

Observed delivery latency:

```text
CreatedAt: 2026-07-27T05:24:36Z
S3 visible: 2026-07-27 12:24:49-59 +07
Latency: khoảng 13-23 giây
```

---

## 3. S3 Object Listing Command

```powershell
aws s3 ls s3://tf4-msk-orders-archive-511825856493-us-east-1/orders/orders/topic=orders/year=2026/month=07/day=27/hour=05/ `
  --profile tf4 `
  --region us-east-1 | Select-Object -Last 60
```

Expected range:

```text
2026-07-27 12:24:49        171 orders+2+0000000000.bin
...
2026-07-27 12:24:59        171 orders+2+0000000049.bin
```

---

## 4. Readability Verification Command

Reusable script in this PR:

```text
scripts/cdo08/verify-msk-orders-s3-archive-readability.ps1
```

For the batch 50 object range, sync the prefix and parse locally:

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

Parse summary already observed:

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

---

## 5. Notes

- Batch này là marker test có kiểm soát, không phải order thật từ checkout.
- Lý do dùng marker trực tiếp: checkout publish path hiện chưa tạo record mới vào MSK `orders`; đây là issue riêng ngoài scope của batch archive validation. Archive runtime vẫn hoạt động đúng khi có input mới.
- Batch này dùng `.bin` ByteArray lossless, không dùng archive `.json` cũ vì archive cũ không preserve protobuf bytes.
