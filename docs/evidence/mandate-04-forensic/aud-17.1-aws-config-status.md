# AWS Config Status Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify AWS Config recorder đang active và recording configuration changes.
> **Test date:** 2026-07-17
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| Config recorder | `tf4-aws-config-recorder` |
| Command run | `aws configservice describe-configuration-recorder-status` |

---

## AWS Config Recorder Status

```json
{
    "ConfigurationRecordersStatus": [
        {
            "arn": "arn:aws:config:us-east-1:511825856493:configuration-recorder/tf4-aws-config-recorder/ndfp4r8tdcu1lgiq",
            "name": "tf4-aws-config-recorder",
            "lastStartTime": "2026-07-15T00:16:38.648000+07:00",
            "recording": true,
            "lastStatus": "SUCCESS",
            "lastStatusChangeTime": "2026-07-17T03:13:52.154000+07:00"
        }
    ]
}
```

## Delivery Channel Status

```bash
aws configservice describe-delivery-channel-status --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

```json
{
    "DeliveryChannelsStatus": [
        {
            "name": "tf4-aws-config-delivery",
            "configSnapshotDeliveryInfo": {
                "lastStatus": "SUCCESS",
                "lastAttemptTime": "2026-07-17T00:34:38.208000+07:00",
                "lastSuccessfulTime": "2026-07-17T00:34:38.208000+07:00",
                "nextDeliveryTime": "2026-07-18T00:34:37.260000+07:00"
            },
            "configHistoryDeliveryInfo": {
                "lastStatus": "SUCCESS",
                "lastAttemptTime": "2026-07-17T05:10:43.040000+07:00",
                "lastSuccessfulTime": "2026-07-17T05:10:43.040000+07:00"
            },
            "configStreamDeliveryInfo": {
                "lastStatus": "NOT_APPLICABLE",
                "lastStatusChangeTime": "2026-07-17T05:10:43.051000+07:00"
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
| Last Stop Time | null | null (Never stopped) | ✅ PASS |
| Config Snapshot Delivery | Success | SUCCESS | ✅ PASS |
| Config History Delivery | Success | SUCCESS | ✅ PASS |
| Recent Delivery | ≤24h | 2026-07-17T05:10:43+07:00 | ✅ PASS |

## Timeline Analysis

| Event | Timestamp | Notes |
|---|---|---|
| Recorder Started | 2026-07-15T00:16:38+07:00 | Started during initial deployment |
| Last Status Change | 2026-07-17T03:13:52+07:00 | SUCCESS status confirmed |
| Recent Snapshot | 2026-07-17T00:34:38+07:00 | Snapshot delivery confirmed |
| Recent History | 2026-07-17T05:10:43+07:00 | Config changes being tracked |

**Overall result:** ✅ **PASS** — AWS Config đang record configuration changes thành công.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-17
**Status:** ✅ VERIFIED