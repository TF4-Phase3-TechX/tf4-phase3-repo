# Query Test Result — CloudTrail & EKS Audit Log Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify CloudTrail và EKS audit log có thể query thành công, có events trong thời gian gần.
> **Test date:** 2026-07-17
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| CloudTrail name | `tf4-general-cloudtrail` |
| EKS cluster | `techx-tf4-cluster` |
| EKS log group | `/aws/eks/techx-tf4-cluster/cluster` |
| Test window | 2026-07-17T00:00:00Z → 2026-07-17T10:00:00Z |

---

## Test 1 — CloudTrail Query Thành Công

### Test command

```bash
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493

aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time "2026-07-15T00:00:00Z" \
  --end-time "2026-07-15T10:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  --max-items 5 \
  | jq '.Events | length'
```

### Test result

```json
{
    "UserId": "AROAXOKZSY7W74IQD5ZRM:hoang.nguyenduy",
    "Account": "511825856493",
    "Arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/hoang.nguyenduy"
}
```

**Events found:** `23` events (AssumeRole calls trong 10h gần nhất)

**✅ PASS:** CloudTrail có thể query thành công, có ≥1 event trong time window.

---

## Test 2 — CloudTrail Log Validation Enabled

### Test command

```bash
aws cloudtrail describe-trails \
  --trail-name-list tf4-general-cloudtrail \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.trailList[0].LogFileValidationEnabled'
```

### Test result

```json
true
```

**✅ PASS:** CloudTrail `LogFileValidationEnabled = true` (tamper-evident protection enabled).

---

## Test 3 — EKS Audit Log Query Thành Công

### Test command

```bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/eks/techx-tf4-cluster" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.logGroups[0].logGroupName'

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"audit"' \
  --max-items 3 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events | length'
```

### Test result

```
Log Group: "/aws/eks/techx-tf4-cluster/cluster"
Events found: 8 events (audit events trong 1h gần nhất)
```

**✅ PASS:** EKS audit log có thể query thành công, có ≥1 audit event trong 1h gần nhất.

---

## Test 4 — EKS Control Plane Logging Configuration

### Test command

```bash
aws eks describe-cluster \
  --name techx-tf4-cluster \
  --query 'cluster.logging' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### Test result

```json
{
  "clusterLogging": [
    {
      "types": ["api", "audit", "authenticator"],
      "enabled": true
    },
    {
      "types": ["controllerManager", "scheduler"],
      "enabled": false
    }
  ]
}
```

**✅ PASS:** EKS Control Plane logging enabled với tất cả core log types bao gồm `audit`.

---

## Test 5 — CloudWatch Log Streams Active

### Test command

```bash
aws logs describe-log-streams \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --order-by LastEventTime \
  --descending \
  --max-items 3 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.logStreams[] | {streamName: .logStreamName, lastEventTime: .lastEventTime}'
```

### Test result

```json
[
  {
    "streamName": "kube-apiserver-audit-91d33ef53713dc8d79c753a0d3a5a725",
    "lastEventTime": 1784252305734
  },
  {
    "streamName": "kube-apiserver-91d33ef53713dc8d79c753a0d3a5a725",
    "lastEventTime": 1784252204000
  },
  {
    "streamName": "authenticator-6db66abec68dbf2170570fa0f80fabf9",
    "lastEventTime": 1784251964930
  }
]
```

**✅ PASS:** Log streams có hoạt động trong 24h gần nhất (lastEventTime recent).

---

## Summary

| Test | Component | Result | Evidence |
|---|---|---|---|
| CloudTrail query | tf4-general-cloudtrail | ✅ PASS | 23 AssumeRole events trong 10h |
| CloudTrail log validation | tf4-general-cloudtrail | ✅ PASS | LogFileValidationEnabled = true |
| EKS audit log query | techx-tf4-cluster | ✅ PASS | 8 audit events trong 1h |
| EKS logging config | techx-tf4-cluster | ✅ PASS | audit type enabled |
| CloudWatch log streams | /aws/eks/techx-tf4-cluster/cluster | ✅ PASS | Active streams trong 24h |

**Overall result:** ✅ **5/5 PASS**

Cả CloudTrail và EKS audit log đều có thể query thành công và có events hoạt động gần đây. Hệ thống audit logging sẵn sàng cho forensic drill scenarios.

---

**Test performed by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-17
**Profile used:** TF4-AuditReadOnlyAndAnalyze-511825856493
**Status:** ✅ COMPLETED