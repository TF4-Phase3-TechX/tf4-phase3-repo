# MANDATE-03 Mentor Brief: Maintenance Capacity & Cost-Efficient Resilience

> Tài liệu này thay cho cách viết kiểu backlog. Mục tiêu là nộp mentor/review: giải thích MANDATE-03 là gì, liên quan thế nào đến hai trụ Performance Efficiency và Cost Optimization, team cần làm gì, đã làm gì, kết quả ra sao, vì sao chọn hướng đó, và task thuộc về ai.

## 1. Executive Summary

MANDATE-03 tập trung vào việc chứng minh hệ thống có thể duy trì SLO khi thực hiện controlled maintenance trên revenue path, đồng thời giữ năng lực phục hồi và cost trong giới hạn chấp nhận được.

| Nội dung | Kết luận hiện tại |
|---|---|
| Mandate | Maintenance Capacity & Cost-Efficient Resilience |
| Cluster | `techx-tf4-cluster` |
| Namespace | `techx-tf4` |
| Region | `us-east-1` |
| Maintenance window | `2026-07-15 11:05:00Z` → `2026-07-15 11:26:00Z` |
| Load | `200 concurrent Locust users` |
| Trụ liên quan | Performance Efficiency và Cost Optimization |
| Trạng thái tổng hợp | Ready for mentor review |
| Verdict ngắn gọn | Performance SLO đạt trong window bảo trì, controlled node-drain resilience đạt, cost estimate đã được mô hình hóa, post-maintenance verification đã được đóng gói |

Kết quả chính đã được tổng hợp trong file gốc:

| Tiêu chí | Quan sát | Verdict |
|---|---:|---|
| Storefront latency p95 | `~303 ms peak` | PASS |
| Browse/Search success rate | `100%` | PASS |
| Cart success rate | `100%` | PASS |
| Checkout success rate | `100%` | PASS |
| Concurrent users | `200` | PASS |
| Stable duration | `21 min total` | PASS |
| Controlled drain resilience | Pod được evict và workload tự phục hồi | PASS |
| Cost estimate | Worker/EBS model đã được tính | PASS |
| Post-maintenance verification | Capacity, placement, scale-down evidence đã đóng gói | PASS |

Kết luận cần nói thẳng với mentor:

- Maintenance SLO được giữ trong approved window.
- Workload tự phục hồi khi node bị drain.
- Karpenter bổ sung worker capacity khi cần.
- Cost model cho thấy capacity tạm thời có thể tính bằng node-hours và gp3 root cost.
- Bộ evidence đã sẵn sàng để mentor xem lại theo từng task owner.

## 2. MANDATE-03 là gì?

MANDATE-03 là bài kiểm chứng về maintenance resilience dưới tải thật, không chỉ là load test. Nó yêu cầu hệ thống giữ được customer-facing SLO khi một worker node được drain, pod phải reschedule, và capacity phải phục hồi mà không làm luồng doanh thu bị gián đoạn.

| Yêu cầu mandate | Ý nghĩa thực tế | Evidence/source |
|---|---|---|
| 200 concurrent users | Bảo đảm bài kiểm chứng chạy trên tải đủ lớn để lộ ra điểm yếu | `Maintenance SLO and Cost Evidence for Mentor Sign-Off.md` |
| Stable duration | Không chỉ spike ngắn; phải giữ được tải trong window bảo trì | `RUNBOOK`/evidence runtime |
| Controlled node drain | Chứng minh maintenance không làm customer flow đứt | `D3-PERF-04` runtime evidence |
| Revenue-path SLO | Browse/Cart/Checkout phải giữ target | `D3-PERF-03`, dashboard evidence |
| Capacity recovery | Pod phải reschedule và serving capacity quay lại | `D3-PERF-01`, `D3-PERF-04` |
| Cost-efficient resilience | Không để resilience đạt được bằng cách overprovision mù quáng | `D3-COST-01`, `D3-COST-02` |

Ràng buộc quan trọng:

- Revenue path là ưu tiên chính.
- `quote` là critical synchronous service và đã được remediation trước maintenance.
- PDB, topology spread, probes và replica redundancy phải được chứng minh bằng evidence.
- Cost ở đây là cost của capacity bền vững và temporary capacity, không chỉ là tổng bill.

## 3. Liên quan gì đến hai trụ Performance và Cost?

### 3.1 Performance Efficiency

MANDATE-03 là bài chứng minh trực tiếp cho Performance Efficiency vì nó kiểm tra hệ thống khi node bị drain trong lúc vẫn có 200 users đang chạy.

| Performance concern | Cách MANDATE-03 xử lý | Kết quả/evidence |
|---|---|---|
| Latency trong maintenance | Theo dõi storefront p95 trong controlled window | ~`303 ms peak`, dưới ngưỡng `1000 ms` |
| Success rate của flow chính | Đo Browse/Search, Cart, Checkout success | `100%` cho cả ba flow |
| Resilience khi node bị drain | Drain node mục tiêu và quan sát eviction/reschedule | Workload phục hồi thành công |
| Replica redundancy | Revenue path có hai replicas Ready | Runtime inventory PASS |
| Placement | Replica được spread trên nhiều node/AZ | Pod placement PASS |
| `quote` remediation | Bảo đảm service đồng bộ trên checkout path có PDB/probes/topology spread | `quote` remediation PASS |

### 3.2 Cost Optimization

MANDATE-03 cũng là bài cost vì resilience có thể bị giải sai bằng cách giữ quá nhiều worker hoặc provision thêm capacity không cần thiết.

| Cost concern | Cách MANDATE-03 xử lý | Kết quả/evidence |
|---|---|---|
| Không overprovision vô căn cứ | Dùng pricing model theo node-hour và gp3 | Có baseline, observed runtime và ceiling rõ ràng |
| Temporary capacity phải tính được | Ghi node-hours cho worker bổ sung | Có 4h/8h/24h estimate và scale-down criteria |
| Baseline phải rõ | Managed node group và Karpenter được tách bạch | Fixed baseline và dynamic capacity đều được đo |
| `quote` remediation phải chấp nhận được về cost | So sánh requests/limits và usage thực tế | Delta nhỏ, cost impact acceptable |
| Post-maintenance phải có reconciliation | Ghi lại scale-down/cost validation sau run | Có post-maintenance verification package |

## 4. Team cần làm gì cho MANDATE-03?

Để đáp ứng mandate, nhóm Performance và Cost phải hoàn thành bốn việc chính:

| Nhóm việc | Cần làm | Vì sao cần |
|---|---|---|
| Inventory revenue path | Kiểm kê replicas, requests/limits, HPA, PDB, placement và endpoints | Biết chính xác luồng doanh thu có đủ redundancy hay chưa |
| Remediate critical gaps | Sửa `quote` và các gap blocking maintenance | Không có remediation thì controlled drain chưa thể tin cậy |
| Run controlled maintenance | Drain node trong approved window và theo dõi SLO | Chứng minh system resilient thật dưới maintenance |
| Model cost & verify scale-down | Tính worker-hour cost, temporary capacity cost, và xác nhận scale-down sau maintenance | Chứng minh resilience đi cùng cost-efficient behavior |

## 5. Team đã làm gì?

### 5.1. Revenue-path capacity inventory

Nguồn: `D3-PERF-01-revenue-path-capacity-inventory/01-revenue-path-capacity-inventory.md`.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| Runtime inventory | Kiểm kê service revenue-critical | `frontend-proxy`, `frontend`, `product-catalog`, `cart`, `checkout`, `payment`, `currency`, `shipping`, `quote` đều có runtime evidence |
| Replica readiness | Xác nhận desired/ready/available | Critical services đạt `2/2 Ready` |
| HPA | Kiểm tra HPA runtime | `frontend` và `checkout` có HPA `min=2`, `max=3` |
| PDB | Kiểm tra PDB runtime | Critical services có `minAvailable=1` |
| Placement | Đo pod-to-node placement | Replica được spread trên nhiều node |
| `quote` remediation | Sửa singleton risk, probes, PDB, topology spread, requests/limits | `quote` remediation PASS |
| Capacity pre-check | Đánh giá trước controlled drain | Post-remediation capacity pre-check PASS |

### 5.2. Maintenance load profile và test contract

Nguồn: `Maintenance SLO and Cost Evidence for Mentor Sign-Off.md` và evidence runtime liên quan.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| Load contract | Cố định 200 concurrent users | Test contract rõ ràng |
| Maintenance window | Chốt window UTC | `2026-07-15 11:05:00Z` → `11:26:00Z` |
| Runtime observation | Theo dõi during/after maintenance | SLO giữ được trong window |
| Evidence package | Thu dashboard, runtime, cost model, post-maintenance verification | Package ready for review |

### 5.3. Dashboard và alert window

Nguồn: `D3-PERF-03 — Maintenance Dashboard and Alert Window` trong evidence tổng hợp sign-off.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| SLO dashboard | Ghi storefront latency và success rate | PASS |
| Alert window | Quan sát alert state trong maintenance window | Alert window có evidence để review |
| Post-maintenance panel | Kiểm tra sau drain | Workload phục hồi và ổn định |

### 5.4. Execute maintenance performance validation

Nguồn: `D3-PERF-04 — Execute Maintenance Performance Validation`.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| Controlled drain | Drain node mục tiêu | Pod bị evict như mong đợi |
| Recovery | Karpenter bổ sung capacity và pod reschedule | Workload quay lại Running |
| Customer SLO | Theo dõi browse/cart/checkout | Tất cả đạt target |
| Cleanup | Uncordon và post-run verification | Runtime ổn định sau maintenance |

### 5.5. Replica and capacity cost model

Nguồn: `D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md`.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| AWS pricing | Lấy đơn giá `t3.large`, `t3a.large`, gp3 | Đơn giá có evidence raw |
| Fixed baseline | Tính 2 managed nodes | `~$124.67/tháng` |
| Observed runtime | Tính 3 nodes | `~$181.17/tháng` nếu duy trì liên tục |
| Incremental capacity | Tính 1/2 node dynamic cho 4h, 8h, 24h | Có bảng cost theo cửa sổ |
| Ceiling | Tính trần autoscaling theo NodePool limits | Có configuration ceiling rõ ràng |
| `quote` cost impact | Đánh giá cost delta sau remediation | Acceptable |

### 5.6. Post-maintenance scale-down and cleanup

Nguồn: `D3-COST-02` và sign-off summary.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| Scale-down | Ghi nhận worker trở về baseline vận hành | PASS |
| Node utilization | So sánh sau maintenance | Usage bình thường |
| Cost verification | Ghi node-hours và temporary capacity | Có estimate và cleanup package |
| Mentor package | Đóng gói evidence cuối | Ready for mentor review |

## 6. Kết quả như thế nào?

### 6.1. Performance result

| Khu vực | Kết quả | Diễn giải |
|---|---|---|
| Storefront p95 | PASS | Khoảng `303 ms peak` |
| Browse/Search success | PASS | `100%` |
| Cart success | PASS | `100%` |
| Checkout success | PASS | `100%` |
| Controlled drain resilience | PASS | Pod evict, reschedule, workload phục hồi |
| Revenue-path inventory | PASS | Hai replicas Ready trên các service critical |

### 6.2. Cost result

| Khu vực | Kết quả | Diễn giải |
|---|---|---|
| Fixed baseline | PASS | `2 × t3.large` On-Demand rõ ràng |
| Observed runtime cost | PASS | `2 × t3.large + 1 × t3a.large` được model hóa |
| Temporary capacity | PASS | Có 4h/8h/24h estimate |
| `quote` remediation cost impact | PASS | Delta nhỏ, chấp nhận được |
| Actual billing reconciliation | Pending follow-up | Có thể gắn thêm nếu mentor yêu cầu |

### 6.3. Post-maintenance result

| Requirement | Kết quả | Evidence |
|---|---|---|
| Pod recovery | PASS | Workload quay lại Running |
| Node readiness | PASS | Worker nodes healthy |
| Scale-down | PASS | Runtime trở lại baseline |
| Cleanup verification | PASS | Có evidence summary |

## 7. Task ownership

| Task/Jira | Work | Assignee | Status | Evidence/Output |
|---|---|---|---|---|
| `COG-41` | D3-PERF-01 — Revenue Path Capacity Inventory | Truong An | Done | `D3-PERF-01-revenue-path-capacity-inventory/01-revenue-path-capacity-inventory.md` |
| `COG-42` | D3-PERF-02 — Maintenance Load Profile and Test Contract | Tín Văn Phú (Văn Phú Tín) | Done | maintenance load profile / test contract evidence |
| `COG-43` | D3-PERF-03 — Maintenance Dashboard and Alert Window | Huy Tạ Hoàng | Done | dashboard and alert window evidence |
| `COG-44` | D3-PERF-04 — Execute Maintenance Performance Validation | Nguyen Huy Hoang | Done | maintenance runtime evidence, drain validation |
| `COG-45` | D3-COST-01 — Replica and Capacity Cost Model | Truong An | Done | `D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md` |
| `COG-46` | D3-COST-02 — Post-Maintenance Scale-Down and Cost Verification | Phan Minh Tuấn | Done | post-maintenance verification and scale-down evidence |
| `COG-47` | Package maintenance SLO and cost evidence for mentor sign-off | Truong An | Done | `Maintenance SLO and Cost Evidence for Mentor Sign-Off.md` |

## 8. Vì sao team làm ra được kết quả này?

Team đạt được kết quả này vì không xử lý maintenance bằng cách phóng to tài nguyên vô điều kiện, mà theo một chuỗi kiểm soát rõ ràng:

1. Kiểm kê revenue path trước để biết service nào thực sự critical.
2. Remediate `quote` vì đây là synchronous dependency trên checkout path.
3. Chỉ dùng PDB, topology spread, probes và replica redundancy khi có evidence.
4. Dùng controlled drain thay vì giả định node failure.
5. Theo dõi SLO trong cùng maintenance window để có before/during/after.
6. Tính cost bằng node-hours và gp3 thay vì đoán theo tổng bill chung.
7. Ghi scale-down và cleanup sau run để mentor thấy resilience đi cùng cost discipline.

## 9. Evidence map cho mentor

| Evidence | Vai trò |
|---|---|
| `Maintenance SLO and Cost Evidence for Mentor Sign-Off.md` | Gói tổng hợp cho mentor |
| `D3-PERF-01-revenue-path-capacity-inventory/01-revenue-path-capacity-inventory.md` | Inventory, remediation verification, placement, PDB, HPA |
| `D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md` | Baseline cost model, dynamic capacity, ceiling, `quote` cost impact |
| `raw/` files | Nguồn thô cho node, pod, HPA, price list, endpoints, placement và usage |

## 10. Suggested wording nộp mentor

```text
MANDATE-03 đã được chuẩn bị và thực thi như một bài kiểm chứng maintenance capacity và cost-efficient resilience.

Trong maintenance window 2026-07-15 11:05:00Z đến 11:26:00Z, revenue-path SLO được giữ khi thực hiện controlled node drain dưới tải 200 concurrent users. Browse, Cart và Checkout đều duy trì 100% success rate, storefront p95 ở mức khoảng 303 ms peak.

Về Performance Efficiency, team đã kiểm kê revenue path, remediated quote, thiết lập replica redundancy, PDB, topology spread và probes trước khi chạy controlled drain.

Về Cost Optimization, team xây mô hình chi phí từ AWS Price List cho managed nodes, Karpenter nodes và gp3 root volumes. Baseline, observed runtime và temporary capacity đều được tính ra node-hours rõ ràng, thay vì chỉ nhìn tổng bill.

Post-maintenance evidence cho thấy workload phục hồi, scale-down được ghi nhận, và bộ evidence đã sẵn sàng cho mentor review.
```

## 11. Final Verdict

| Area | Verdict | Ghi chú |
|---|---|---|
| Revenue-path inventory | PASS | Critical services, replicas, placement, HPA, PDB đã được kiểm kê |
| `quote` remediation | PASS | Singleton risk, probes, topology spread và PDB đã được giải quyết |
| Controlled maintenance SLO | PASS | 200 users trong window bảo trì vẫn giữ target |
| Controlled drain resilience | PASS | Pod evict, reschedule và workload phục hồi |
| Cost model | PASS | Baseline, observed runtime và dynamic capacity đều có estimate |
| Post-maintenance scale-down | PASS | Runtime trở lại baseline |
| Mentor submission readiness | Ready for mentor review | Có thể nộp với evidence, owner mapping và suggested wording ở trên |
