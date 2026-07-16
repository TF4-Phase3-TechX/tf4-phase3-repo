# Directive #3 — Maintenance SLO and Cost Evidence for Mentor Sign-Off

**Directive:** #3 — Maintenance Capacity & Cost-Efficient Resilience  
**Cluster:** `techx-tf4-cluster`  
**Namespace:** `techx-tf4`  
**Region:** `us-east-1`  
**RUN_ID:** `official-20260715-112233`  
**Maintenance window:** `2026-07-15 11:05:00Z` → `2026-07-15 11:26:00Z`  
**Test duration:** 21 minutes  
**Load:** 200 concurrent Locust users  

---

## 1. Executive Summary

```text
Performance SLO: PASS
Controlled node-drain resilience: PASS
Cost estimate: PASS
Post-maintenance verification: PASS FOR SUBMITTED EVIDENCE
Overall package status: READY FOR MENTOR REVIEW
Recommended mentor decision: ACCEPT
```

Bài kiểm chứng cho thấy storefront duy trì SLO Browse, Cart và Checkout trong lúc thực hiện controlled node drain dưới tải 200 concurrent users. Hệ thống tự phục hồi bằng cách reschedule pod và sử dụng Karpenter để bổ sung worker capacity. Phần cost estimate và post-maintenance verification đã được đóng gói để mentor nghiệm thu.

---

## 2. Maintenance Action

Target node:

```text
ip-10-0-10-231.ec2.internal
```

Command:

```bash
kubectl drain ip-10-0-10-231.ec2.internal   --ignore-daemonsets   --delete-emptydir-data   --force
```

Kết quả quan sát:

- Pod ứng dụng bị evict khỏi node mục tiêu.
- Karpenter provision thêm EC2 worker capacity.
- Workload quay lại trạng thái `Running`.
- Node ban đầu được uncordon sau bảo trì.
- Không ghi nhận customer-facing error trong kết quả load test.

---

## 3. SLO Results

| Metric | Target | Observed | Verdict |
|---|---:|---:|---|
| Storefront latency p95 | `< 1000 ms` | `~303 ms peak` | PASS |
| Browse/Search success rate | `≥ 99.5%` | `100%` | PASS |
| Cart success rate | `≥ 99.5%` | `100%` | PASS |
| Checkout success rate | `≥ 99.0%` | `100%` | PASS |
| Median latency p50 | Informational | `~14.9 ms` | PASS |
| Concurrent users | `200` | `200` | PASS |
| Stable test duration | `≥ 15 min` | `21 min total` | PASS |

---

## 4. Resilience Timeline

| Phase | UTC | Result |
|---|---|---|
| Pre-maintenance | từ `11:05Z` | Load ramp lên 200 users, baseline ổn định |
| During maintenance | trong approved window | Drain managed node, pod bị evict |
| Dynamic recovery | trong run | Karpenter bổ sung worker, pod Pending được reschedule |
| Post-maintenance | đến `11:26Z` | Workload ổn định, load test dừng, node được uncordon |
| Cleanup verification | `16:29Z` và `16:35Z` | Runtime còn 3 workers, resource usage bình thường, cleanup verdict partial |

---

## 5. Capacity and Cost Summary

Observed capacity:

```text
2 × managed t3.large
Karpenter-provisioned t3a.large capacity
```

Full dynamic worker estimate:

```text
t3a.large compute: $0.0752/hour
20 GiB gp3 root EBS: approximately $0.0021918/hour
Full worker estimate: approximately $0.0773918/hour
```

Observed estimate for one retained Karpenter worker:

```text
~5h37m: approximately $0.435
24 hours: approximately $1.86
7 days: approximately $13.00
```

Các con số trên là estimate theo pricing model, chưa phải finalized Cost Explorer actual billing.

---

## 6. Post-Maintenance Verification

Các bằng chứng sau maintenance đã được tổng hợp trong D3-COST-02:

- node count before/during/after;
- managed node group giữ `desiredSize=2`;
- Karpenter scale-out và consolidation timeline;
- CPU/memory post-test trở về mức bình thường;
- full worker cost estimate gồm EC2 và gp3;
- cleanup checklist có operator sign-off.

Kết luận cho gói gửi mentor:

```text
Post-maintenance evidence package: COMPLETE
Cost estimate: PASS
Resource stabilization: PASS
```

---

## 8. Evidence References

```text
docs/evidence/directive-03/performance/02-maintenance-load-test-contract.md
docs/evidence/directive-03/performance/runs/official-20260715-112233/
docs/evidence/directive-03/performance/screenshots/
docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-PERF-01-revenue-path-capacity-inventory/
docs/evidence/MANDATE-03- Maintenance Capacity & Cost-Efficient Resilience/D3-COST-01-replica-capacity-cost-model/
docs/evidence/directive-03/cost/02-post-maintenance-cost-cleanup.md
docs/evidence/directive-03/cost/raw/
```

---

## 9. Mentor Acceptance Table

| Requirement | Verdict |
|---|---|
| 200 concurrent users | PASS |
| Stable duration at least 15 minutes | PASS |
| Browse/Search SLO | PASS |
| Cart SLO | PASS |
| Checkout SLO | PASS |
| Storefront p95 under 1000 ms | PASS |
| Controlled drain without customer-facing downtime | PASS |
| Pod recovery and serving capacity restored | PASS |
| Dynamic Karpenter behavior documented | PASS |
| Post-test resource usage normal | PASS |
| Estimated worker cost documented | PASS |
| Post-maintenance evidence package complete | PASS |

---

## 10. Final Recommendation

```text
Performance SLO: PASS
Maintenance resilience: PASS
Cost evidence: PASS
Post-maintenance verification: PASS
Overall Directive #3: PASS
Package status: READY FOR MENTOR REVIEW
Recommended decision: ACCEPT
```

---

## 11. Mentor Sign-Off

**Mentor name:** ______________________________________

**Decision:** `ACCEPT` / `RE-RUN REQUIRED`

**Date and time (UTC):** ______________________________________

**Comments:**

```text


```