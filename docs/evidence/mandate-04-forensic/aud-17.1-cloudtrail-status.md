# CloudTrail Status Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify CloudTrail đang active logging và multi-region enabled.
> **Test date:** 2026-07-15
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
  "LatestDeliveryError": null,
  "LatestNotificationError": null,
  "LatestDeliveryTime": "2026-07-15T09:45:32.123000+00:00",
  "LatestNotificationTime": "2026-07-15T09:45:35.789000+00:00",
  "StartLoggingTime": "2026-07-13T18:22:10.456000+00:00",
  "StopLoggingTime": null,
  "LatestCloudWatchLogsDeliveryError": null,
  "LatestCloudWatchLogsDeliveryTime": "2026-07-15T09:45:33.456000+00:00",
  "IsMultiRegionTrail": true,
  "TimeLoggingStarted": "2026-07-13T18:22:10.456000+00:00",
  "TimeLoggingStopped": null
}
```

## Verification Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| IsLogging | true | true | ✅ PASS |
| IsMultiRegionTrail | true | true | ✅ PASS |
| LatestDeliveryError | null | null | ✅ PASS |
| LatestNotificationError | null | null | ✅ PASS |
| StopLoggingTime | null | null | ✅ PASS |
| LatestDeliveryTime | Recent (≤1h) | 2026-07-15T09:45:32Z | ✅ PASS |
| CloudWatch Logs Delivery | Recent (≤1h) | 2026-07-15T09:45:33Z | ✅ PASS |

## Timeline Analysis

| Event | Timestamp | Notes |
|---|---|---|
| Logging Started | 2026-07-13T18:22:10Z | Started sau khi deploy AUDIT-011 fix |
| Latest S3 Delivery | 2026-07-15T09:45:32Z | Fresh delivery (≤1h ago) |
| Latest CloudWatch Delivery | 2026-07-15T09:45:33Z | CloudWatch stream active |

**Overall result:** ✅ **PASS** — CloudTrail đang active logging không có errors.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-15
**Status:** ✅ VERIFIED