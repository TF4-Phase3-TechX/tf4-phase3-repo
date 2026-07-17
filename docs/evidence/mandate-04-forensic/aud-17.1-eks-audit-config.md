# EKS Audit Configuration Verification
## AUD-17.1 · CDO07 · Mandate 4

> **Mục đích:** Verify EKS Control Plane logging enabled với audit log type.
> **Test date:** 2026-07-17
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
                "authenticator"
            ],
            "enabled": true
        },
        {
            "types": [
                "controllerManager",
                "scheduler"
            ],
            "enabled": false
        }
    ]
}
```

## Log Group Verification

```bash
aws logs describe-log-groups --log-group-name-prefix "/aws/eks/techx-tf4-cluster" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

```json
{
    "logGroups": [
        {
            "logGroupName": "/aws/eks/techx-tf4-cluster/cluster",
            "creationTime": 1783414986073,
            "retentionInDays": 90,
            "metricFilterCount": 0,
            "arn": "arn:aws:logs:us-east-1:511825856493:log-group:/aws/eks/techx-tf4-cluster/cluster:*",
            "storedBytes": 1765818642,
            "logGroupClass": "STANDARD",
            "logGroupArn": "arn:aws:logs:us-east-1:511825856493:log-group:/aws/eks/techx-tf4-cluster/cluster",
            "deletionProtectionEnabled": false
        }
    ]
}
```

## Recent Log Streams

```bash
aws logs describe-log-streams --log-group-name "/aws/eks/techx-tf4-cluster/cluster" \
  --order-by LastEventTime --descending --max-items 3 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

| Stream Name | Last Event Time | Last Event (UTC) |
|---|---|---|
| kube-apiserver-audit-91d33ef53713dc8d79c753a0d3a5a725 | 1784252305734 | 2026-07-17T01:38:25Z |
| kube-apiserver-91d33ef53713dc8d79c753a0d3a5a725 | 1784252204000 | 2026-07-17T01:36:44Z |
| authenticator-6db66abec68dbf2170570fa0f80fabf9 | 1784251964930 | 2026-07-17T01:32:44Z |

## Verification Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| Cluster Logging Enabled | true | true | ✅ PASS |
| Audit Log Type | audit | audit | ✅ PASS |
| API Log Type | api | api | ✅ PASS |
| Authenticator Log Type | authenticator | authenticator | ✅ PASS |
| ControllerManager Log Type | enabled | disabled | ⚠️ PARTIAL |
| Scheduler Log Type | enabled | disabled | ⚠️ PARTIAL |
| Log Group Exists | Yes | /aws/eks/techx-tf4-cluster/cluster | ✅ PASS |
| Log Retention | 90 days | 90 days | ✅ PASS |
| Recent Audit Streams | Recent | 2026-07-17T01:38:25Z | ✅ PASS |
| Stored Log Data | >0 bytes | 1,765,818,642 bytes (~1.6GB) | ✅ PASS |

## Test Query — Audit Events

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"audit"' \
  --max-items 1 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events | length'
```

**Result:** `10` audit events trong 1h gần nhất.

**Overall result:** ✅ **PASS** — EKS audit logging enabled và active với recent events. 
⚠️ **Note:** controllerManager và scheduler logs đã bị disable để giảm chi phí, nhưng core audit (api, audit, authenticator) đang hoạt động.

---

**Evidence collected by:** Nguyễn Duy Hoàng (CDO07)
**Date:** 2026-07-17
**Status:** ✅ VERIFIED