# Scenario 05 — On-Call Action (SSM Bastion Access)
## AUD-17.2 · Forensic Drill Scenario Design

| Field | Giá trị |
|---|---|
| Scenario ID | AUD-17.2-S05 |
| Loại | On-call action — SSM StartSession (bastion access) |
| Nguồn log | CloudTrail — `tf4-general-cloudtrail` |
| Độ khó | Dễ |
| Target thời gian | ≤7 phút |
| Tác giả | Ty (CDO07) |
| Ngày | 2026-07-15 |

---

## Mô tả kịch bản

**Tình huống mentor đưa ra:**
> "Đêm qua có ai vào bastion không? Để làm gì?"

Hoặc:
> "Ai đã on-call lúc incident xảy ra? Họ có vào hệ thống không?"

**Loại event cần trace:**
- `StartSession` (SSM) — mở tunnel vào bastion EC2
- `ResumeSession` (SSM) — nối lại session đã tạm dừng
- `TerminateSession` (SSM) — đóng session

**Tại sao quan trọng:** On-call action phải traceable về người cụ thể. Nếu không trace được → không có accountability. SSM StartSession ghi `session name = username` → identity rõ ràng, không thể anonymous.

---

## Data thật đã có (từ incident 13–14/07)

> **Sự kiện thật:** 10 SSM StartSession events vào bastion `i-072084d1cf0b2f1c9` trong window 23:27 ngày 13/07 → 01:15 ngày 14/07 +07. Evidence đã commit tại `VERIFICATION-REPORT.md` (ST-3.3).

---

## Query cụ thể

### Query A — Tất cả SSM StartSession trong window

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time "2026-07-13T16:00:00Z" \
  --end-time "2026-07-14T02:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:    .EventTime,
      event:   .EventName,
      user:    .Username,
      userArn: (.CloudTrailEvent | fromjson | .userIdentity.arn),
      target:  (.CloudTrailEvent | fromjson | .requestParameters.target),
      session: (.CloudTrailEvent | fromjson | .responseElements.sessionId),
      srcIP:   (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

### Query B — SSM sessions của 1 user cụ thể

```bash
# Thay TÊN_USER bằng username cần tìm
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=Username,AttributeValue=TÊN_USER \
  --start-time "2026-07-09T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[]
        | select(.EventName == "StartSession" or .EventName == "TerminateSession")
        | {
            time:    .EventTime,
            event:   .EventName,
            target:  (.CloudTrailEvent | fromjson | .requestParameters.target // "N/A"),
            session: (.CloudTrailEvent | fromjson | .responseElements.sessionId // (.CloudTrailEvent | fromjson | .requestParameters.sessionId // "N/A"))
          }'
```

### Query C — Tất cả SSM activity trong 7 ngày (audit toàn diện)

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventSource,AttributeValue=ssm.amazonaws.com \
  --start-time "2026-07-09T00:00:00Z" \
  --end-time "2026-07-16T00:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[]
        | select(.EventName | IN("StartSession", "ResumeSession", "TerminateSession"))
        | {
            time:   .EventTime,
            event:  .EventName,
            user:   .Username,
            target: (.CloudTrailEvent | fromjson | .requestParameters.target // "N/A")
          }'
```

---

## Output thật từ hệ thống (Query A — đã verified tại VERIFICATION-REPORT.md ST-3.3)

```json
{ "time": "2026-07-14T01:15:20+07:00", "user": "hung.hoangkim",  "target": "i-072084d1cf0b2f1c9", "session": "hung.hoangkim-7jyzlso8gnvkyl7t4vgr28nu3a",  "srcIP": "42.118.54.254" }
{ "time": "2026-07-14T01:13:16+07:00", "user": "hung.hoangkim",  "target": "i-072084d1cf0b2f1c9", "session": "hung.hoangkim-...",                            "srcIP": "42.118.54.254" }
{ "time": "2026-07-14T00:16:40+07:00", "user": "huyhoang",       "target": "i-072084d1cf0b2f1c9", "session": "huyhoang-...",                                  "srcIP": "..." }
{ "time": "2026-07-14T00:16:21+07:00", "user": "anngo",          "target": "i-072084d1cf0b2f1c9", "session": "anngo-...",                                     "srcIP": "..." }
{ "time": "2026-07-14T00:13:46+07:00", "user": "cdo04-an",       "target": "i-072084d1cf0b2f1c9", "session": "cdo04-an-...",                                  "srcIP": "..." }
{ "time": "2026-07-14T00:12:53+07:00", "user": "anngo",          "target": "i-072084d1cf0b2f1c9", "session": "anngo-...",                                     "srcIP": "..." }
{ "time": "2026-07-14T00:03:49+07:00", "user": "cdo04-an",       "target": "i-072084d1cf0b2f1c9", "session": "cdo04-an-...",                                  "srcIP": "..." }
{ "time": "2026-07-14T00:02:58+07:00", "user": "cdo04-an",       "target": "i-072084d1cf0b2f1c9", "session": "cdo04-an-...",                                  "srcIP": "..." }
{ "time": "2026-07-13T23:28:39+07:00", "user": "nguyen",         "target": "i-072084d1cf0b2f1c9", "session": "nguyen-cqzlbzsh4onaob6vh2536k3vj4",            "srcIP": "..." }
{ "time": "2026-07-13T23:27:46+07:00", "user": "nguyen",         "target": "i-072084d1cf0b2f1c9", "session": "nguyen-...",                                    "srcIP": "..." }
```

---

## Trả lời forensic mẫu (dùng data thật)

```
WHO:   5 người trong window 23:27 (13/07) → 01:15 (14/07) +07:
       nguyen (CDO08), cdo04-an, anngo, huyhoang, hung.hoangkim (CDO07)

WHAT:  SSM StartSession vào bastion i-072084d1cf0b2f1c9 (tf4-portal-bastion)
       EventName = "StartSession", Source = ssm.amazonaws.com
       Tổng 10 sessions trong ~1h48m

WHEN:  Session đầu: 2026-07-13T23:27:46+07
       Session cuối: 2026-07-14T01:15:20+07

HOW:   AWS SSM Session Manager — không cần SSH key, không mở port 22
       Session ID traceable: session name = username (mỗi người có ID riêng)

CONTEXT:
       Window này ngay sau CDO08 deploy SEC-05 (23:28 ngày 13/07)
       → Team verify ingress hardening, vào bastion test private access
       Authorized activity — cross-confirmed với VERIFICATION-REPORT.md ST-3.3

IDENTITY ACCOUNTABILITY:
       Mỗi session có session ID riêng → không shared account
       Source IP riêng từng người → không shared machine
```

---

## Điểm cần lưu ý khi drill

1. **Session name = username** → SSM tự động ghi vào session ID → không cần thêm setup
2. **Không có SSH key** → không thể bypass audit trail qua direct SSH
3. **Target = instance ID** → biết chính xác bastion nào bị truy cập
4. **TerminateSession** cũng được ghi → có thể tính session duration nếu cần

---

## Chứng minh "truy về người" (yêu cầu DIRECTIVE #4)

SSM StartSession là ví dụ lý tưởng để chứng minh mọi on-call action quy về 1 danh tính:

```
Session ID: hung.hoangkim-7jyzlso8gnvkyl7t4vgr28nu3a
                ↑
           username = hung.hoangkim → mapped về người thật Hoàng Kim Hùng

Session ID: nguyen-cqzlbzsh4onaob6vh2536k3vj4
                ↑
           username = nguyen → CDO08 team member
```

→ **Không thể dùng anonymous access. Không thể dùng shared session.** Mỗi session có danh tính riêng, không thể xóa khỏi CloudTrail.

---

## Evidence liên quan

- Data thật: `docs/evidence/mandate-01-network-exposure/VERIFICATION-REPORT.md` (ST-3.3)
- CloudTrail table (screenshot): `docs/audit/postmortems/cloud_trail_detect.png`
- Drill log (thời gian thực tế): `docs/evidence/mandate-04-forensic/aud-17.2-drill-log.md` Scenario 3
