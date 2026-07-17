# CloudTrail Status Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify CloudTrail đang active logging và multi-region enabled.
> **Test date:** 2026-07-17
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| CloudTrail name | `tf4-general-cloudtrail` |
| Command run | `aws cloudtrail get-trail-status --name tf4-general-cloudtrail` |

---

## CloudTrail Status Output

```json
{
    "IsLogging": true,
    "LatestDeliveryTime": "2026-07-17T08:59:58.728000+07:00",
    "StartLoggingTime": "2026-07-09T09:44:06.174000+07:00",
    "LatestCloudWatchLogsDeliveryTime": "2026-07-17T09:01:40.609000+07:00",
    "LatestDigestDeliveryTime": "2026-07-17T08:43:32.258000+07:00",
    "LatestDeliveryAttemptTime": "2026-07-17T01:59:58Z",
    "LatestNotificationAttemptTime": "",
    "LatestNotificationAttemptSucceeded": "",
    "LatestDeliveryAttemptSucceeded": "2026-07-17T01:59:58Z",
    "TimeLoggingStarted": "2026-07-09T02:44:06Z",
    "TimeLoggingStopped": ""
}
```

## Verification Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| IsLogging | true | true | ✅ PASS |
| LatestDeliveryTime | Recent (≤1h) | 2026-07-17T08:59:58+07:00 | ✅ PASS |
| StartLoggingTime | Not null | 2026-07-09T09:44:06+07:00 | ✅ PASS |
| CloudWatch Logs Delivery | Recent (≤1h) | 2026-07-17T09:01:40+07:00 | ✅ PASS |
| LatestDigestDeliveryTime | Recent (≤24h) | 2026-07-17T08:43:32+07:00 | ✅ PASS |
| TimeLoggingStopped | Empty (still logging) | "" | ✅ PASS |

## Timeline Analysis

| Event | Timestamp | Notes |
|---|---|---|
| Logging Started | 2026-07-09T09:44:06+07:00 | Started during initial deployment |
| Latest S3 Delivery | 2026-07-17T08:59:58+07:00 | Fresh delivery (current) |
| Latest CloudWatch Delivery | 2026-07-17T09:01:40+07:00 | CloudWatch stream active |
| Latest Digest Delivery | 2026-07-17T08:43:32+07:00 | Integrity verification active |

**Overall result:** ✅ **PASS** — CloudTrail đang active logging không có errors.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-17
**Status:** ✅ VERIFIED