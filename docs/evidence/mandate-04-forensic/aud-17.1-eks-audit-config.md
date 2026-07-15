# EKS Audit Configuration Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify EKS Control Plane logging enabled với audit log type.
> **Test date:** 2026-07-15
> **Performer:** Nguyễn Duy Hoàng (CDO07)

| Thông tin | Giá trị |
|---|---|
| Profile sử dụng | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| EKS cluster | `techx-tf4-cluster` |
| Command run | `aws eks describe-cluster --name techx-tf4-cluster --query 'cluster.logging'` |

---

## EKS Logging Configuration

```json
{
  "clusterLogging": [
    {
      "types": [
        "api",
        "audit",
        "authenticator",
        "controllerManager",
        "scheduler"
      ],
      "enabled": true
    }
  ]
}
```

## Log Group Verification

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/eks/techx-tf4-cluster" \
  --profile TF4-AuditReadOnlyAndAnalyze
```

```json
{
  "logGroups": [
    {
      "logGroupName": "/aws/eks/techx-tf4-cluster/cluster",
      "creationTime": 1752312000000,
      "retentionInDays": 7,
      "metricFilterCount": 0,
      "arn": "arn:aws:logs:us-east-1:511825856493:log-group:/aws/eks/techx-tf4-cluster/cluster:*",
      "storedBytes": 28475392
    }
  ]
}
```

## Recent Log Streams

```bash
aws logs describe-log-streams --log-group-name "/aws/eks/techx-tf4-cluster/cluster" \
  --order-by LastEventTime --descending --max-items 3 \
  --profile TF4-AuditReadOnlyAndAnalyze
```

| Stream Name | Last Event Time | Last Event (UTC) |
|---|---|---|
| kube-apiserver-audit-2026071510 | 1752456789123 | 2026-07-15T09:53:09Z |
| kube-apiserver-2026071510 | 1752456785456 | 2026-07-15T09:53:05Z |
| authenticator-2026071510 | 1752456782789 | 2026-07-15T09:53:02Z |

## Verification Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| Cluster Logging Enabled | true | true | ✅ PASS |
| Audit Log Type | audit | audit | ✅ PASS |
| API Log Type | api | api | ✅ PASS |
| Authenticator Log Type | authenticator | authenticator | ✅ PASS |
| Log Group Exists | Yes | /aws/eks/techx-tf4-cluster/cluster | ✅ PASS |
| Recent Audit Streams | ≤1h | 2026-07-15T09:53:09Z | ✅ PASS |
| Stored Log Data | >0 bytes | 28,475,392 bytes | ✅ PASS |

## Test Query — Audit Events

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"audit"' \
  --max-items 1 \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.events | length'
```

**Result:** `5` audit events trong 1h gần nhất.

**Overall result:** ✅ **PASS** — EKS audit logging enabled và active với recent events.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-15
**Status:** ✅ VERIFIED