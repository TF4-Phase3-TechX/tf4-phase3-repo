# CloudTrail Configuration Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify CloudTrail configuration và log validation enabled.
> **Test date:** 2026-07-17
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| CloudTrail name | `tf4-general-cloudtrail` |
| Command run | `aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze` |

---

## CloudTrail Configuration Output

```json
{
    "trailList": [
        {
            "Name": "tf4-general-cloudtrail",
            "S3BucketName": "tf4-cloudtrail-logs-bucket-511825856493",
            "IncludeGlobalServiceEvents": true,
            "IsMultiRegionTrail": true,
            "HomeRegion": "us-east-1",
            "TrailARN": "arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail",
            "LogFileValidationEnabled": true,
            "CloudWatchLogsLogGroupArn": "arn:aws:logs:us-east-1:511825856493:log-group:/aws/cloudtrail/tf4-general-cloudtrail:*",
            "CloudWatchLogsRoleArn": "arn:aws:iam::511825856493:role/tf4-cloudtrail-to-cloudwatch-role",
            "KmsKeyId": "arn:aws:kms:us-east-1:511825856493:key/4f20f498-949c-4970-9a79-7f34f1497d98",
            "HasCustomEventSelectors": false,
            "HasInsightSelectors": false,
            "IsOrganizationTrail": false
        }
    ]
}
```

## Verification Checklist

| Check | Expected | Actual | Result |
|---|---|---|---|
| CloudTrail Name | tf4-general-cloudtrail | tf4-general-cloudtrail | ✅ PASS |
| LogFileValidationEnabled | true | true | ✅ PASS |
| IsMultiRegionTrail | true | true | ✅ PASS |
| IncludeGlobalServiceEvents | true | true | ✅ PASS |
| S3 Bucket | tf4-cloudtrail-logs-bucket-511825856493 | tf4-cloudtrail-logs-bucket-511825856493 | ✅ PASS |
| CloudWatch Integration | Enabled | Enabled | ✅ PASS |

**Overall result:** ✅ **PASS** — CloudTrail configured correctly với log validation enabled.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-17
**Status:** ✅ VERIFIED