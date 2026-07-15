# Scenario 03 — Unauthorized Access Attempt
## AUD-17.2 · Forensic Drill Scenario Design

| Field | Giá trị |
|---|---|
| Scenario ID | AUD-17.2-S03 |
| Loại | Unauthorized access — AccessDenied / AssumeRole failure |
| Nguồn log | CloudTrail — `tf4-general-cloudtrail` |
| Độ khó | Trung bình–Cao |
| Target thời gian | ≤8 phút |
| Tác giả | Ty (CDO07) |
| Ngày | 2026-07-15 |

---

## Mô tả kịch bản

**Tình huống mentor đưa ra:**
> "Có ai đó cố truy cập S3 nhưng bị chặn — ai, khi nào, bucket nào?"

Hoặc:
> "Có attempt AssumeRole thất bại trong tuần này không?"

**Loại event cần trace:**
- S3 `GetObject` với `errorCode = "AccessDenied"` — đọc object không có quyền
- `AssumeRole` với `errorCode = "AccessDenied"` — cố escalate privilege thất bại
- Bất kỳ event nào có `errorCode` — phát hiện pattern attack/misconfiguration

**Tại sao quan trọng:** Unauthorized access attempt là dấu hiệu sớm nhất của security incident. Nếu không trace được → không phát hiện được attack in progress.

---

## Data thật đã có

> **Sự kiện thật từ incident 14/07:** Bastion `i-072084d1cf0b2f1c9` liên tục gửi `RegisterContainerInstance` → `AccessDenied` ×4 trong window 14:24–14:29 +07. Evidence đã có trong CloudTrail cloud_trail_detect.png.

---

## Query cụ thể

### Query A — S3 AccessDenied (generic)

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time "2026-07-09T00:00:00Z" \
  --end-time "2026-07-16T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[]
        | select((.CloudTrailEvent | fromjson | .errorCode) == "AccessDenied")
        | {
            time:    .EventTime,
            user:    .Username,
            userArn: (.CloudTrailEvent | fromjson | .userIdentity.arn),
            bucket:  (.CloudTrailEvent | fromjson | .requestParameters.bucketName),
            key:     (.CloudTrailEvent | fromjson | .requestParameters.key),
            srcIP:   (.CloudTrailEvent | fromjson | .sourceIPAddress),
            error:   (.CloudTrailEvent | fromjson | .errorCode),
            msg:     (.CloudTrailEvent | fromjson | .errorMessage)
          }'
```

### Query B — Tất cả AccessDenied trong window (bất kỳ event nào)

```bash
# Dùng khi không biết EventName cụ thể — scan rộng
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=ErrorCode,AttributeValue=AccessDenied \
  --start-time "2026-07-14T07:00:00Z" \
  --end-time "2026-07-14T08:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:     .EventTime,
      event:    .EventName,
      user:     .Username,
      source:   .EventSource,
      error:    (.CloudTrailEvent | fromjson | .errorCode),
      resource: (.CloudTrailEvent | fromjson | .resources[0].ARN // "N/A")
    }'
```

### Query C — AssumeRole failures

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time "2026-07-09T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[]
        | select((.CloudTrailEvent | fromjson | .errorCode) != null)
        | {
            time:   .EventTime,
            user:   .Username,
            role:   (.CloudTrailEvent | fromjson | .requestParameters.roleArn),
            error:  (.CloudTrailEvent | fromjson | .errorCode),
            srcIP:  (.CloudTrailEvent | fromjson | .sourceIPAddress)
          }'
```

### Query D — RegisterContainerInstance AccessDenied (data thật từ incident 14/07)

```bash
# Window: 14:20–14:35 +07 = 07:20–07:35 UTC
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=RegisterContainerInstance \
  --start-time "2026-07-14T07:20:00Z" \
  --end-time "2026-07-14T07:35:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:     .EventTime,
      user:     .Username,
      instance: (.CloudTrailEvent | fromjson | .requestParameters.instanceIdentityDocument.instanceId // "unknown"),
      error:    (.CloudTrailEvent | fromjson | .errorCode),
      msg:      (.CloudTrailEvent | fromjson | .errorMessage),
      srcIP:    (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

---

## Output thật từ hệ thống — Data từ incident 14/07 (đã verified)

```json
{ "time": "2026-07-14T07:24:40+07:00", "user": "i-072084d1cf0b2f1c9", "instance": "i-072084d1cf0b2f1c9", "error": "AccessDenied", "msg": "User is not authorized to perform: ecs:RegisterContainerInstance" }
{ "time": "2026-07-14T07:26:55+07:00", "user": "i-072084d1cf0b2f1c9", "instance": "i-072084d1cf0b2f1c9", "error": "AccessDenied", "msg": "User is not authorized to perform: ecs:RegisterContainerInstance" }
{ "time": "2026-07-14T07:29:41+07:00", "user": "i-072084d1cf0b2f1c9", "instance": "i-072084d1cf0b2f1c9", "error": "AccessDenied", "msg": "User is not authorized to perform: ecs:RegisterContainerInstance" }
```

---

## Trả lời forensic mẫu

```
WHO:   Bastion instance i-072084d1cf0b2f1c9 (tf4-portal-bastion)
       ECS Agent trên bastion tự động gửi request — không phải human action

WHAT:  RegisterContainerInstance → AccessDenied ×3
       ECS Agent trên bastion cố đăng ký với ECS cluster nhưng bastion không phải ECS node
       → Đây là misconfiguration của ECS Agent, không phải attack

WHEN:  2026-07-14T07:24:40Z → 07:29:41Z UTC = 14:24 → 14:29 +07
       Trong window incident — CONCURRENT, không phải nguyên nhân

HOW:   ECS Agent daemon trên bastion EC2 instance tự động retry
       Source: internal AWS API, không phải external actor

ĐÁNH GIÁ:
       Unauthorized access attempt = TRUE (AccessDenied có trong log)
       Threat level = LOW (misconfiguration, not malicious actor)
       Action needed: CDO04 fix ECS Agent config trên bastion
```

---

## Điểm cần lưu ý khi drill

1. **`AttributeKey=ErrorCode,AttributeValue=AccessDenied`** là cách scan rộng nhất — không cần biết EventName trước
2. **Phân biệt nguồn:** AccessDenied từ instance profile (EC2) khác với từ human user
3. **Pattern burst** — nhiều AccessDenied trong 5 phút từ cùng 1 actor → retry loop, không phải human attack
4. **Đừng kết luận vội "attack"** — đọc `errorMessage` để hiểu context trước khi trả lời

---

## Evidence liên quan

- CloudTrail screenshot: `docs/audit/postmortems/cloud_trail_detect.png`
- Incident context: `docs/audit/postmortems/incident-20260714-checkout-payment.md` (Section 3)
- Drill log: `docs/evidence/mandate-04-forensic/aud-17.2-drill-log.md`
