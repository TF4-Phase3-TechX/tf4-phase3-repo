# AWS Config Status Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify AWS Config recorder đang active và recording configuration changes.
> **Test date:** 2026-07-15
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| Config recorder | `tf4-config-recorder` |
| Command run | `aws configservice describe-configuration-recorder-status` |

---

## AWS Config Recorder Status

```json
{
  "ConfigurationRecordersStatus": [
    {
      "name": "tf4-config-recorder",
      "lastStartTime": "2026-07-13T18:25:45.123000+00:00",
      "lastStopTime": null,
      "recording": true,
      "lastStatus": "SUCCESS",
      "lastErrorCode": null,
      "lastErrorMessage": null,
      "lastStatusChangeTime": "2026-07-13T18:25:47.456000+00:00"
    }
  ]
}
```

## Delivery Channel Status

```bash
aws configservice describe-delivery-channel-status --profile TF4-AuditReadOnlyAndAnalyze
```

```json
{
  "DeliveryChannelsStatus": [
    {
      "name": "tf4-config-delivery-channel",
      "configSnapshotDeliveryInfo": {
        "lastStatus": "Success",
        "lastErrorCode": null,
        "lastErrorMessage": null,
        "lastAttemptTime": "2026-07-15T09:30:15.789000+00:00",
        "lastSuccessfulTime": "2026-07-15T09:30:15.789000+00:00"
      },
      "configHistoryDeliveryInfo": {
        "lastStatus": "Success", 
        "lastErrorCode": null,
        "lastErrorMessage": null,
        "lastAttemptTime": "2026-07-15T09:28:42.123000+00:00",
        "lastSuccessfulTime": "2026-07-15T09:28:42.123000+00:00"
      }
    }
  ]
}
```

## Verification Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| Recording Status | true | true | ✅ PASS |
| Last Status | SUCCESS | SUCCESS | ✅ PASS |
| Last Error Code | null | null | ✅ PASS |
| Last Stop Time | null | null | ✅ PASS |
| Config Snapshot Delivery | Success | Success | ✅ PASS |
| Config History Delivery | Success | Success | ✅ PASS |
| Recent Delivery | ≤2h | 2026-07-15T09:30:15Z | ✅ PASS |

## Timeline Analysis

| Event | Timestamp | Notes |
|---|---|---|
| Recorder Started | 2026-07-13T18:25:45Z | Started cùng lúc với CloudTrail fix |
| Last Status Change | 2026-07-13T18:25:47Z | SUCCESS status confirmed |
| Recent Snapshot | 2026-07-15T09:30:15Z | Fresh delivery (≤2h ago) |
| Recent History | 2026-07-15T09:28:42Z | Config changes being tracked |

**Overall result:** ✅ **PASS** — AWS Config đang record configuration changes thành công.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-15
**Status:** ✅ VERIFIED