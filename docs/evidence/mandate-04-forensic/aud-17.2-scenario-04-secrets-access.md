# Scenario 04 — Secrets Access
## AUD-17.2 · Forensic Drill Scenario Design

| Field | Giá trị |
|---|---|
| Scenario ID | AUD-17.2-S04 |
| Loại | Secrets access — KMS Decrypt / SSM GetParameter |
| Nguồn log | CloudTrail — `tf4-general-cloudtrail` |
| Độ khó | Trung bình |
| Target thời gian | ≤8 phút |
| Tác giả | Ty (CDO07) |
| Ngày | 2026-07-15 |

---

## Mô tả kịch bản

**Tình huống mentor đưa ra:**
> "Tuần vừa rồi có ai decrypt secret không? Ai đọc parameter từ SSM?"

Hoặc:
> "Ai đã truy cập KMS key của chúng ta? Vào lúc mấy giờ?"

**Loại event cần trace:**
- `Decrypt` (KMS) — giải mã data dùng KMS key → secret đang được đọc
- `GenerateDataKey` (KMS) — tạo data key → có thể là app đang encrypt/decrypt dữ liệu
- `GetParameter` / `GetParameters` (SSM Parameter Store) — đọc secret/config từ SSM
- `GetSecretValue` (Secrets Manager) — đọc secret từ AWS Secrets Manager

**Tại sao quan trọng:** Secrets access trace cho thấy ai đang đọc credentials. Nếu không authorized → đây là data breach indicator.

---

## Query cụ thể

### Query A — KMS Decrypt

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=Decrypt \
  --start-time "2026-07-09T00:00:00Z" \
  --end-time "2026-07-16T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:    .EventTime,
      event:   .EventName,
      user:    .Username,
      userArn: (.CloudTrailEvent | fromjson | .userIdentity.arn),
      keyId:   (.CloudTrailEvent | fromjson | .resources[0].ARN // "N/A"),
      srcIP:   (.CloudTrailEvent | fromjson | .sourceIPAddress),
      region:  (.CloudTrailEvent | fromjson | .awsRegion)
    }'
```

### Query B — SSM GetParameter

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetParameter \
  --start-time "2026-07-09T00:00:00Z" \
  --end-time "2026-07-16T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:        .EventTime,
      event:       .EventName,
      user:        .Username,
      userArn:     (.CloudTrailEvent | fromjson | .userIdentity.arn),
      paramName:   (.CloudTrailEvent | fromjson | .requestParameters.name),
      withDecrypt: (.CloudTrailEvent | fromjson | .requestParameters.withDecryption),
      srcIP:       (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

### Query C — Secrets Manager GetSecretValue

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetSecretValue \
  --start-time "2026-07-09T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:       .EventTime,
      user:       .Username,
      userArn:    (.CloudTrailEvent | fromjson | .userIdentity.arn),
      secretName: (.CloudTrailEvent | fromjson | .requestParameters.secretId),
      srcIP:      (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

### Query D — Tất cả KMS operations (scan rộng khi không biết event cụ thể)

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=kms.amazonaws.com \
  --start-time "2026-07-14T07:00:00Z" \
  --end-time "2026-07-14T08:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:  .EventTime,
      event: .EventName,
      user:  .Username,
      keyId: (.CloudTrailEvent | fromjson | .resources[0].ARN // "N/A")
    }'
```

---

## Output thật từ hệ thống (đã verified 2026-07-15)

```
EventTime                  EventName   Username          SrcIP
2026-07-15T21:13:23+07:00  Decrypt     hoang.nguyenduy   fas.s3.amazonaws.com
2026-07-15T21:12:46+07:00  Decrypt     hoang.nguyenduy   fas.s3.amazonaws.com
```

Chi tiết từ CloudTrailEvent:
```json
{
  "time":    "2026-07-15T21:13:23+07:00",
  "event":   "Decrypt",
  "user":    "hoang.nguyenduy",
  "userArn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/hoang.nguyenduy",
  "keyId":   "arn:aws:kms:us-east-1:511825856493:key/4f20f498-949c-4970-9a79-7f34f1497d98",
  "srcIP":   "fas.s3.amazonaws.com"
}
```

> **Ghi chú:** Query chạy lúc 2026-07-15 bằng profile `TF4-AuditReadOnlyAndAnalyze-511825856493`.
> `srcIP = fas.s3.amazonaws.com` → đây là S3 service dùng KMS key để decrypt S3 object
> (S3 Server-Side Encryption với KMS — SSE-KMS). Không phải human decrypt thủ công.

---

## Trả lời forensic (dùng data thật)

```
WHO:   hoang.nguyenduy (role: TF4-AuditReadOnlyAndAnalyze)
       ARN = assumed-role → traceable về người thật qua session name

WHAT:  KMS Decrypt — giải mã S3 object dùng key 4f20f498-...
       srcIP = fas.s3.amazonaws.com → S3 service tự động decrypt khi đọc object
       (S3 SSE-KMS: S3 gọi KMS mỗi lần read object được encrypt)

WHEN:  2026-07-15T21:13:23+07:00

HOW:   S3 GetObject trigger KMS Decrypt tự động — không phải CLI decrypt thủ công
       User đọc file từ S3, S3 service decrypt key → user nhận plaintext

GHI CHÚ QUAN TRỌNG:
       Đây là pattern bình thường của S3 SSE-KMS
       KMS key /4f20f498-... → là key encrypt CloudTrail logs bucket
       → hoang.nguyenduy đang đọc CloudTrail log file qua S3
       Authorized activity — role AuditReadOnly có quyền đọc logs
```

---

## Điểm cần lưu ý khi drill

1. **KMS Decrypt thường do service account / pod** — không phải human. Đọc `userIdentity.type` để phân biệt: `AssumedRole` = người, `AWSService` = AWS internal
2. **`withDecryption=true`** trong GetParameter — có nghĩa là đọc SecureString (secret thật)
3. **Volume bất thường** — nếu 1 user Decrypt hàng trăm lần trong 1 phút → có thể đang bulk extract secrets
4. **Key ID** trong output → so với danh sách KMS keys của TF4 để biết secret nào đang bị truy cập

---

## Evidence liên quan

- Identity mapping table: `docs/evidence/mandate-04-forensic/aud-17.4-identity-mapping.md` (nếu có)
- Framework: `docs/audit/tickets/AUDIT-CDO07-MANDATE04-FORENSIC-FRAMEWORK.md` (Section 3.4)
- Drill log: `docs/evidence/mandate-04-forensic/aud-17.2-drill-log.md`
