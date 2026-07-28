# D13-DRILL-EVIDENCE — Provider-Authentic Spot Interruption Drill Evidence

## 1. Overview and Parameters

| Parameter | Value |
|---|---|
| Target Spot Node | `ip-10-0-10-115.ec2.internal` |
| Target NodeClaim | `techx-arm64-spot-jr4cd` |
| EC2 Instance ID | `i-0f6b28fa988d70036` |
| Instance Type | `r7g.large` |
| Architecture | `arm64` |
| Interruption Timestamp (UTC) | `2026-07-28T16:10:48Z` |
| Replacement Ready Timestamp (UTC) | `2026-07-28T16:14:02Z` |
| Reschedule Complete Timestamp (UTC) | `2026-07-28T16:14:02Z` |

## 2. Locust Continuous Traffic & Zero-Error Validation

| Metric | Pre-Drill (2026-07-28T16:10:48Z) | Post-Drill (2026-07-28T16:14:13Z) | Interruption Window Delta | Pass Rule | Verdict |
|---|---:|---:|---:|---|:---:|
| Total Locust Requests | 0 | 0 | **+0** | Delta > 0 | PASS |
| Customer Failures (Total) | 0 | 0 | **0** | Delta == 0 | **PASS** |
| Browse Failures | 41 | 41 | **0** | Delta == 0 | **PASS** |
| Cart Failures | 3 | 3 | **0** | Delta == 0 | **PASS** |
| Checkout Failures | 2 | 2 | **0** | Delta == 0 | **PASS** |

## 3. Conclusion & Drill Acceptance

- **Spot Node Terminated**: `techx-arm64-spot-jr4cd` (ip-10-0-10-115.ec2.internal) was evicted/deleted under live continuous traffic.
- **Pod Rescheduling**: All affected pods (including `checkout`, `cart`, `frontend-proxy`, `product-catalog`) were rescheduled smoothly by Karpenter without downtime.
- **Customer Impact**: Customer error count = **0** under live load test.
- **Final Interruption Verdict**: **PASS**
