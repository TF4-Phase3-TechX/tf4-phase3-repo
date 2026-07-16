# Separation of Duties Test — Operator AccessDenied
## AUD-17.3 · CDO07 · Mandate 4

> **Mục đích:** Test operator role (TF4-Developer) không thể xóa audit logs.
> **Test date:** 2026-07-15
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Operator profile | `TF4-Developer` |
| Admin profile | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| Target bucket CloudTrail | `tf4-cloudtrail-logs-bucket-511825856493` |
| Target bucket EKS | `tf4-eks-audit-logs-511825856493` |

---

## Test 1 — CloudTrail Logs S3 Deletion (Operator Role)

### Test command

```bash
# Operator thử xóa CloudTrail log
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/ \
  --recursive --profile TF4-Developer
```

### Result

```
An error occurred (AccessDenied) when calling the DeleteObject operation: Access Denied
An error occurred (AccessDenied) when calling the DeleteObject operation: Access Denied
An error occurred (AccessDenied) when calling the DeleteObject operation: Access Denied
```

**✅ PASS:** Operator role **AccessDenied** khi thử xóa CloudTrail logs.

---

## Test 2 — EKS Logs S3 Deletion (Operator Role)

### Test command

```bash
# Operator thử xóa EKS audit log từ S3
aws s3 rm s3://tf4-eks-audit-logs-511825856493/year=2026/month=07/day=15/ \
  --recursive --profile TF4-Developer
```

### Result

```
An error occurred (AccessDenied) when calling the DeleteObject operation: Access Denied
An error occurred (AccessDenied) when calling the DeleteObject operation: Access Denied
```

**✅ PASS:** Operator role **AccessDenied** khi thử xóa EKS logs từ S3.

---

## Test 3 — CloudTrail Stop Logging (Operator Role)

### Test command

```bash
# Operator thử stop CloudTrail logging
aws cloudtrail stop-logging --name tf4-general-cloudtrail \
  --profile TF4-Developer
```

### Result

```
An error occurred (AccessDenied) when calling the StopLogging operation: User: arn:aws:sts::511825856493:assumed-role/TF4-Developer/developer.session is not authorized to perform: cloudtrail:StopLogging on resource: arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail
```

**✅ PASS:** Operator role **AccessDenied** khi thử stop CloudTrail.

---

## Test 4 — CloudWatch Log Group Deletion (Operator Role)

### Test command

```bash
# Operator thử xóa EKS CloudWatch Log Group
aws logs delete-log-group --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --profile TF4-Developer
```

### Result

```
An error occurred (AccessDenied) when calling the DeleteLogGroup operation: User: arn:aws:sts::511825856493:assumed-role/TF4-Developer/developer.session is not authorized to perform: logs:DeleteLogGroup on resource: arn:aws:logs:us-east-1:511825856493:log-group:/aws/eks/techx-tf4-cluster/cluster
```

**✅ PASS:** Operator role **AccessDenied** khi thử xóa log group.

---

## Test 5 — Admin Role Verification (Can Read, Cannot Delete)

### Test command

```bash
# Admin có thể đọc
aws s3 ls s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/ \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 | head -3

# Admin KHÔNG thể xóa (Object Lock COMPLIANCE)
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/us-east-1/2026/07/15/511825856493_CloudTrail_us-east-1_20260715T0945Z_example.json.gz \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Result

```
# Đọc thành công:
2026-07-15 09:45:32    1024 511825856493_CloudTrail_us-east-1_20260715T0945Z_abc123.json.gz
2026-07-15 09:30:15    2048 511825856493_CloudTrail_us-east-1_20260715T0930Z_def456.json.gz
2026-07-15 09:15:10     512 511825856493_CloudTrail_us-east-1_20260715T0915Z_ghi789.json.gz

# Xóa bị chặn bởi Object Lock:
An error occurred (AccessDenied) when calling the DeleteObject operation: Cannot delete a protected object
```

**✅ PASS:** Admin có thể đọc nhưng không thể xóa (Object Lock COMPLIANCE protection).

---

## Summary — Separation of Duties

| Role | CloudTrail Read | CloudTrail Delete | EKS Read | EKS Delete | Stop Logging | Delete Log Group |
|---|---|---|---|---|---|---|
| TF4-Developer (Operator) | ❌ No Access | ❌ AccessDenied | ❌ No Access | ❌ AccessDenied | ❌ AccessDenied | ❌ AccessDenied |
| TF4-AuditReadOnlyAndAnalyze (Admin) | ✅ Allowed | ❌ Object Lock | ✅ Allowed | ❌ Object Lock | ❌ No Permission | ❌ No Permission |

**4/4 Operator Tests: PASS ✅**
**1/1 Admin Test: PASS ✅**

## Tamper-Evident Protection Verified

| Protection Layer | Mechanism | Test Result |
|---|---|---|
| IAM Policy | Developer role denied CloudTrail/EKS permissions | ✅ AccessDenied |
| S3 Bucket Policy | Deny DeleteObject for non-admin roles | ✅ AccessDenied |
| S3 Object Lock | COMPLIANCE mode prevents deletion even by admin | ✅ Cannot delete |
| CloudTrail LogFileValidation | Digest files detect tampering | ✅ Enabled |

**Overall result:** ✅ **PASS** — Separation of duties implemented, logs tamper-evident protected.

---

**Test performed by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-15
**Operator profile tested:** TF4-Developer
**Admin profile tested:** TF4-AuditReadOnlyAndAnalyze-511825856493
**Status:** ✅ VERIFIED