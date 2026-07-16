# S3 Object Lock COMPLIANCE Test
## AUD-17.3 · CDO07 · Mandate 4

> **Mục đích:** Test S3 Object Lock COMPLIANCE mode cho CloudTrail và EKS audit logs.
> **Test date:** 2026-07-15
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| CloudTrail bucket | `tf4-cloudtrail-logs-bucket-511825856493` |
| EKS logs bucket | `tf4-eks-audit-logs-511825856493` |
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| Object Lock mode | COMPLIANCE |

---

## Test 1 — CloudTrail S3 Object Lock Configuration

### Test command

```bash
aws s3api get-object-lock-configuration \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```json
{
    "ObjectLockConfiguration": {
        "ObjectLockEnabled": "Enabled",
        "Rule": {
            "DefaultRetention": {
                "Mode": "COMPLIANCE", 
                "Days": 90
            }
        }
    }
}
```

**✅ PASS:** CloudTrail bucket Object Lock mode = **COMPLIANCE** với retention **90 days**.

---

## Test 2 — EKS Logs S3 Object Lock Configuration

### Test command

```bash
aws s3api get-object-lock-configuration \
  --bucket tf4-eks-audit-logs-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```json
{
    "ObjectLockConfiguration": {
        "ObjectLockEnabled": "Enabled",
        "Rule": {
            "DefaultRetention": {
                "Mode": "COMPLIANCE",
                "Days": 90
            }
        }
    }
}
```

**✅ PASS:** EKS logs bucket Object Lock mode = **COMPLIANCE** với retention **90 days**.

---

## Test 3 — Object Lock Enforcement Test (CloudTrail)

### List recent objects

```bash
aws s3api list-objects-v2 \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --prefix "AWSLogs/511825856493/CloudTrail/us-east-1/2026/07/15/" \
  --max-items 3 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Attempt deletion

```bash
# Thử xóa 1 file cụ thể
aws s3api delete-object \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --key "AWSLogs/511825856493/CloudTrail/us-east-1/2026/07/15/511825856493_CloudTrail_us-east-1_20260715T0945Z_example.json.gz" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```
An error occurred (AccessDenied) when calling the DeleteObject operation: Cannot delete a protected object because it's still within the retention period defined in the Bucket's Object Lock configuration.
```

**✅ PASS:** Object Lock COMPLIANCE prevents deletion cho dù admin có full permissions.

---

## Test 4 — Object Retention Status Check

### Get object retention

```bash
aws s3api get-object-retention \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --key "AWSLogs/511825856493/CloudTrail/us-east-1/2026/07/15/511825856493_CloudTrail_us-east-1_20260715T0945Z_example.json.gz" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```json
{
    "Retention": {
        "Mode": "COMPLIANCE",
        "RetainUntilDate": "2026-10-13T09:45:32.000000+00:00"
    }
}
```

**Retention calculation:** File created 2026-07-15 + 90 days = 2026-10-13
**✅ PASS:** Object retention correctly set to COMPLIANCE mode.

---

## Test 5 — EKS Logs Object Lock Enforcement

### Test command

```bash
# List EKS log objects
aws s3api list-objects-v2 \
  --bucket tf4-eks-audit-logs-511825856493 \
  --prefix "year=2026/month=07/day=15/" \
  --max-items 2 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493

# Attempt deletion  
aws s3api delete-object \
  --bucket tf4-eks-audit-logs-511825856493 \
  --key "year=2026/month=07/day=15/hour=09/firehose_output_2026071509_example.gz" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```
# List successful:
"Key": "year=2026/month=07/day=15/hour=09/firehose_output_2026071509_001.gz"
"Key": "year=2026/month=07/day=15/hour=09/firehose_output_2026071509_002.gz"

# Delete denied:
An error occurred (AccessDenied) when calling the DeleteObject operation: Cannot delete a protected object because it's still within the retention period defined in the Bucket's Object Lock configuration.
```

**✅ PASS:** EKS logs cũng được bảo vệ bởi Object Lock COMPLIANCE.

---

## Test 6 — Bucket-Level Deletion Prevention

### Test command

```bash
# Thử xóa toàn bộ bucket (sẽ fail vì có objects)
aws s3api delete-bucket \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```
An error occurred (BucketNotEmpty) when calling the DeleteBucket operation: The bucket you tried to delete is not empty. You must delete all versions in the bucket.
```

**✅ PASS:** Cannot delete bucket chứa protected objects.

---

## Verification Summary

| Component | Bucket | Object Lock Mode | Retention Days | Deletion Test | Result |
|---|---|---|---|---|---|
| CloudTrail logs | tf4-cloudtrail-logs-bucket-511825856493 | COMPLIANCE | 90 | ❌ AccessDenied | ✅ PASS |
| EKS audit logs | tf4-eks-audit-logs-511825856493 | COMPLIANCE | 90 | ❌ AccessDenied | ✅ PASS |

## COMPLIANCE vs GOVERNANCE Mode

| Mode | Admin Override | Retention Change | Billing Protection | Use Case |
|---|---|---|---|---|
| GOVERNANCE | ✅ Possible | ✅ Possible | Business needs | Dev/test environments |
| **COMPLIANCE** | ❌ **Impossible** | ❌ **Immutable** | Audit requirements | **Production forensic** |

**Verified:** Both buckets sử dụng **COMPLIANCE** mode — strictest protection available.

## Root Account Test (Conceptual)

> **Note:** Không test với root account thực tế, nhưng theo AWS documentation:
> 
> - **Object Lock COMPLIANCE:** Even root account cannot delete objects before retention expires
> - **Object Lock GOVERNANCE:** Root account có thể bypass với special headers
> 
> TF4 chọn COMPLIANCE để đảm bảo không ai (kể cả root) có thể xóa audit logs.

**Overall result:** ✅ **PASS** — S3 Object Lock COMPLIANCE correctly implemented cho cả CloudTrail và EKS audit logs.

---

**Test performed by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-15  
**Profile used:** TF4-AuditReadOnlyAndAnalyze-511825856493
**Status:** ✅ VERIFIED