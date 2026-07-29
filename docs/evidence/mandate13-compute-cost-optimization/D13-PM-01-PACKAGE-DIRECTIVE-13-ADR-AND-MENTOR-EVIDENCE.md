# D13-PM-01 — Gói ADR và bằng chứng nghiệm thu Directive 13

## 1. Mục tiêu và phạm vi

Tài liệu này là điểm vào duy nhất để mentor kiểm tra thiết kế và bằng chứng của Directive 13: chuyển compute EKS từ nền On-Demand AMD64 sang Graviton/ARM64 kết hợp Spot, giữ một On-Demand reliability floor, co giãn theo đường tải thấp → cao → thấp và bảo vệ SLO của luồng Browse → Cart → Checkout.

Nguồn bằng chứng trong gói này gồm tài liệu đã ký, cấu hình source of truth, raw output, ảnh Grafana/Locust/Cost Explorer và kết quả interruption drill có timestamp. Mọi đường dẫn nội bộ đều dùng relative link để có thể mở trực tiếp trên GitHub.

## 2. ADR đã ký

Nguồn quyết định: [ADR-013 — ARM64 và Spot Capacity Decision](./ADR-013-arm64-spot-capacity-decision.md).

### 2.1 Quyết định kiến trúc

| Hạng mục | Quyết định đã ghi nhận | Nguồn kiểm chứng |
|---|---|---|
| On-Demand reliability floor | Duy trì 2 Managed Node Group `t4g.large` On-Demand phân bổ trên `us-east-1a` và `us-east-1b`, cộng 1 protected `t4g.large` On-Demand cho OpenSearch/observability và EBS RWO AZ-bound | [ADR-013](./ADR-013-arm64-spot-capacity-decision.md), [execution plan](./M13-PM-01-safe-compute-optimization-execution-plan.md) |
| Spot Graviton | Workload stateless đủ điều kiện chạy trên ARM64 Spot; NodePool cho phép `c7g.large`, `m7g.large`, `r7g.large`, `c7g.xlarge`, `m7g.xlarge` | [`infra/terraform/karpenter-nodepool.tf`](../../../infra/terraform/karpenter-nodepool.tf) |
| AMD64 compatibility path | NodePool `techx-general` AMD64 `t3a.large` vẫn tồn tại trong desired state làm đường tương thích/fallback; không có AMD64 live node tại checkpoint ARM64 | [execution plan](./M13-PM-01-safe-compute-optimization-execution-plan.md), [`infra/terraform/karpenter-nodepool.tf`](../../../infra/terraform/karpenter-nodepool.tf) |
| Instance diversification | Spot ARM64 dùng allow-list nhiều family/kích thước; không khóa vào một instance type duy nhất | [`infra/terraform/karpenter-nodepool.tf`](../../../infra/terraform/karpenter-nodepool.tf) |
| Workload eligibility | Stateless có replica/probe/PDB/topology phù hợp mới được đưa lên Spot; PostgreSQL, Kafka, Valkey và OpenSearch không được coi là Spot workload | [Spot/ARM64 eligibility matrix](./jira-report/SPOT-ARM64-ELIGIBILITY-MATRIX.md) |
| PDB, replica và topology | Stateless service được bảo vệ bằng `minAvailable: 1`, replica dự phòng và spread theo zone/hostname | [interruption drill](./D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md), [low-high-low report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) |
| Graceful termination | Pod có `terminationGracePeriodSeconds: 30`, readiness probe; endpoint không Ready được loại khỏi Service trước khi pod kết thúc | [interruption drill](./D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md) |
| Karpenter limits | AMD64 On-Demand: `8` CPU; ARM64 canary On-Demand: `6` CPU; protected ARM64 On-Demand: `4` CPU; ARM64 Spot: `6` CPU | [`infra/terraform/karpenter-nodepool.tf`](../../../infra/terraform/karpenter-nodepool.tf) |
| Consolidation | `WhenEmptyOrUnderutilized`, `consolidateAfter: 5m`, disruption budget tối đa 1 node cho mỗi NodePool | [`infra/terraform/karpenter-nodepool.tf`](../../../infra/terraform/karpenter-nodepool.tf) |
| Interruption strategy | Karpenter Spot termination handling được bật; PDB, readiness, topology spread, reschedule và replacement capacity bảo vệ workload khi Spot node bị thu hồi | [`infra/terraform/karpenter.tf`](../../../infra/terraform/karpenter.tf), [interruption drill](./D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md) |

### 2.2 Đánh đổi và rủi ro đã biết

- Ba node On-Demand được giữ làm reliability floor nên Spot ratio ở steady state là khoảng 40%, thấp hơn tỷ lệ tại high-load.
- Khả năng cấp Spot phụ thuộc capacity pool của AWS; allow-list nhiều family/kích thước giảm nhưng không loại bỏ rủi ro thiếu capacity.
- Workload stateful hoặc gắn EBS RWO không được đặt lên Spot tùy ý; OpenSearch được ghim vào protected On-Demand capacity.
- AMD64 NodePool còn trong desired state để giữ đường tương thích trong trường hợp image hoặc dependency ARM64 gặp lỗi.
- Khi tăng replica, tổng connection pool của workload phải tiếp tục nằm trong giới hạn downstream; việc tăng node không tự động đồng nghĩa downstream có thêm capacity.

### 2.3 Chủ sở hữu và phê duyệt

| Vai trò | Đơn vị | Trạng thái trong ADR |
|---|---|---|
| Cost & Performance Lead | CDO-04 | Đã duyệt |
| Platform & Reliability Lead | CDO-08 / Reliability | Đã duyệt |

ADR ghi trạng thái `ACCEPTED / SIGNED`, ngày `28/07/2026`.

## 3. Hợp đồng đo

Hợp đồng chuẩn: [D13-PERF-01 — Variable Load Curve and SLO Contract](../epic-09-compute-cost-optimization/D13-PERF-01-variable-load-curve-slo-contract.md).

Các điều kiện dùng để đọc evidence:

- đường tải `25 → 200 → 25 users`;
- có low baseline, ramp-up, high peak, ramp-down và low observation;
- request denominator và endpoint mix giữ nhất quán;
- đánh giá Browse, Cart và Checkout bằng success/error cùng p95;
- node-hour tính theo tích phân node count theo thời gian;
- Spot ratio và kiến trúc CPU lấy từ EC2/Kubernetes inventory;
- kiểm tra interruption bằng cumulative counters trước/sau cùng một UTC window.

PR hợp đồng: [#312 — define variable load curve and SLO contract](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/312).  
Commit cập nhật review: [`1e4ddb9`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/1e4ddb9ea6aeef8f29f5392305feb76b654870fb).

## 4. Before — baseline On-Demand

Nguồn chính: [D13-COST-01 — On-Demand baseline](./D13-COST-01-ondemand-baseline/D13-COST-01-ondemand-baseline.md).

| Chỉ số | Baseline đã ghi nhận | Evidence |
|---|---:|---|
| Purchase option | 100% On-Demand | [EC2 inventory](./D13-COST-01-ondemand-baseline/raw/10-ec2-instances-table.txt), [Cost Explorer raw JSON](./D13-COST-01-ondemand-baseline/raw/13-ce-usage-quantity-daily.json) |
| Kiến trúc | 100% `x86_64` | [EC2 inventory](./D13-COST-01-ondemand-baseline/raw/10-ec2-instances-table.txt) |
| EC2 instances tại snapshot | 5 | [EC2 inventory](./D13-COST-01-ondemand-baseline/raw/10-ec2-instances-table.txt), [node inventory](./D13-COST-01-ondemand-baseline/raw/01-nodes-wide.txt) |
| Checkout | 7,608 requests; 59 failures; success 99.22% | [Locust requests JSON](./D13-COST-01-ondemand-baseline/locust/locust-stats-requests.json), [Locust HTML](./D13-COST-01-ondemand-baseline/locust/locust-report.html) |
| HPA snapshot | Có raw snapshot theo namespace/workload | [HPA raw output](./D13-COST-01-ondemand-baseline/raw/05-hpa-wide.txt) |

Cost Explorer baseline bao phủ chuỗi ngày `2026-07-15` đến `2026-07-22`, dùng `UsageQuantity` và cho thấy usage On-Demand, không có Spot usage trong baseline. PR baseline: [#515](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/515).

## 5. After — ARM64/Graviton kết hợp Spot

Nguồn chính:

- [D13 Managed ARM64 Migration Verdict](./D13-MANAGED-ARM64-MIGRATION-VERDICT.md)
- [D13 Full Low-High-Low Run Evidence](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md)
- [Low-high-low telemetry CSV](./lowhighlow_telemetry.csv)

### 5.1 Capacity và placement

| Chỉ số | Optimized checkpoint | Evidence |
|---|---:|---|
| Live worker architecture | 100% ARM64/Graviton | [ARM64 migration verdict](./D13-MANAGED-ARM64-MIGRATION-VERDICT.md) |
| Steady-state topology | 3 On-Demand + 2 Spot, tổng 5 nodes | [ADR-013](./ADR-013-arm64-spot-capacity-decision.md), [execution plan](./M13-PM-01-safe-compute-optimization-execution-plan.md) |
| Steady-state Spot ratio | 40% | [ADR-013](./ADR-013-arm64-spot-capacity-decision.md) |
| High-load topology | 3 On-Demand + 3 Spot, tổng 6 nodes | [low-high-low report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) |
| High-load Spot ratio | 50% | [low-high-low report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) |
| AZ placement checkpoint | `us-east-1a`: managed OD + Spot; `us-east-1b`: managed OD + protected OD + Spot | [ARM64 migration verdict](./D13-MANAGED-ARM64-MIGRATION-VERDICT.md) |

Source change đã merge cho ARM64 managed capacity: PR [#719](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/719), commit [`acd947f3`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/acd947f3).

### 5.2 Node-hour calculation trên load profile

Bảng dưới đây giữ nguyên mẫu tính trong report 45 phút để mentor có thể tính lại:

| Phase | Thời lượng | Baseline node count | Baseline node-hours | Optimized node count | Optimized node-hours |
|---|---:|---:|---:|---:|---:|
| Low baseline | 0.0833 h | 5 | 0.4167 | 5 | 0.4167 |
| Ramp-up | 0.0833 h | 5 | 0.4167 | 5 | 0.4167 |
| High peak | 0.2500 h | 6 | 1.5000 | 6 | 1.5000 |
| Ramp-down | 0.0833 h | 6 | 0.5000 | 5 | 0.4167 |
| Low observation | 0.2500 h | 5 | 1.2500 | 5 | 1.2500 |
| **Tổng** | **0.7500 h** |  | **4.0834** |  | **4.0000** |

Phép tính: `node-hours = Σ(node_count_phase × phase_duration_hours)`.

Trong optimized run, `4.0000 node-hours` gồm `2.2500 On-Demand hours + 1.7500 Spot hours`. Đây là số modeled theo phase table của [báo cáo low-high-low](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md); Cost Explorer Usage Quantity và raw node timeline là nguồn đối soát độc lập.

### 5.3 Load curve và dashboard

UTC run window trong evidence: `2026-07-28T16:14:06Z` đến `2026-07-28T17:08:27Z`.

| Phase | Locust | Grafana |
|---|---|---|
| Ramp-up | [ảnh Locust](./screenshots/02-ramp-up-locust.png) | [panel 1](./screenshots/02-ramp-up-grafana-1.png), [panel 2](./screenshots/02-ramp-up-grafana-2.png) |
| High peak 200 users | [ảnh Locust](./screenshots/03-high-peak-locust.png) | [panel tải](./screenshots/03-high-peak-grafana-1.png), [panel latency/SLO](./screenshots/03-high-peak-grafana-2.png) |
| Ramp-down | [ảnh Locust](./screenshots/04-ramp-down-locust.png) | [panel 1](./screenshots/04-ramp-down-grafana-1.png), [panel HPA](./screenshots/04-ramp-down-grafana-2.png) |
| Low observation | [ảnh Locust](./screenshots/05-low-observation-locust-rest.png) | [panel 1](./screenshots/05-low-observation-grafana-rest-1.png), [panel 2](./screenshots/05-low-observation-grafana-rest-2.png) |

Checkout success được ghi nhận trong report theo từng phase ở khoảng `99.96%–99.98%`. Số liệu phase và node timeline có thể kiểm lại trong [report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) và [telemetry CSV](./lowhighlow_telemetry.csv).

### 5.4 Cost Explorer Usage Quantity

- [Cost Explorer trend ngày 27/07](./screenshots/06-cost-explorer-trend-jul27.jpg)
- [Cost Explorer trend ngày 28/07](./screenshots/06-cost-explorer-trend-jul28.jpg)
- [Baseline UsageQuantity raw JSON](./D13-COST-01-ondemand-baseline/raw/13-ce-usage-quantity-daily.json)

Hai ảnh Cost Explorer thể hiện quá trình chuyển instance usage từ `t3/t3a` sang các family Graviton `t4g/c7g/m7g`; raw baseline cung cấp denominator On-Demand trước tối ưu. Verdict compute dùng Usage Quantity/node-hour và purchase option, không dùng số tiền sau credit làm bằng chứng chính.

## 6. Workload eligibility, HPA và quota

### 6.1 Workload eligibility và ARM64

[Spot/ARM64 eligibility matrix](./jira-report/SPOT-ARM64-ELIGIBILITY-MATRIX.md) ghi nhận:

- nhóm có thể cân nhắc cho Spot gồm `cart`, `checkout`, `currency`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `quote`, `shipping`;
- workload single-replica hoặc thiếu PDB/probe phải hoàn tất điều kiện bảo vệ trước khi đặt lên Spot;
- PostgreSQL, Kafka, Valkey và OpenSearch không phù hợp với Spot theo thiết kế này;
- custom images đã được kiểm tra build ARM64 và public dependency images được kiểm tra manifest ARM64.

PR ma trận: [#326](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/326).

### 6.2 HPA và ResourceQuota

- HPA source: [`techx-corp-chart/templates/hpa.yaml`](../../../techx-corp-chart/templates/hpa.yaml)
- HPA workload values: [`techx-corp-chart/values.yaml`](../../../techx-corp-chart/values.yaml)
- ResourceQuota source: [`deploy/quota.yaml`](../../../deploy/quota.yaml)
- Baseline HPA raw output: [`05-hpa-wide.txt`](./D13-COST-01-ondemand-baseline/raw/05-hpa-wide.txt)
- Resource validation report: [`02-measured-resource-matrix.md`](../directive-05/performance/02-measured-resource-matrix.md)
- Enforcement/cost impact: [`02-resource-enforcement-cost-impact.md`](../directive-05/cost/02-resource-enforcement-cost-impact.md)

PR cấu hình và validation: [#498](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/498).

## 7. NodeClaim lifecycle và interruption drill

Nguồn chính: [D13 Spot Interruption Drill Evidence](./D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md).

| Mốc | UTC / giá trị |
|---|---|
| Spot node | `ip-10-0-10-115.ec2.internal` |
| NodeClaim | `techx-arm64-spot-jr4cd` |
| EC2 instance | `i-0f6b28fa988d70036` |
| Instance type | `r7g.large`, ARM64 |
| Interruption bắt đầu | `2026-07-28T16:10:48Z` |
| Replacement Ready | `2026-07-28T16:14:02Z` |
| Reschedule hoàn tất | `2026-07-28T16:14:02Z` |
| Drill kết thúc | `2026-07-28T16:14:13Z` |
| Thời gian replacement/reschedule | 3 phút 14 giây |
| Request delta trong cửa sổ | +60,349 |
| Customer-visible errors | 0 |

Chuỗi bảo vệ đã được kiểm chứng trong report: PDB → endpoint removal/readiness → graceful termination → Karpenter replacement → scheduler reschedule → workload tiếp tục nhận traffic.

## 8. Ma trận before/after đã có bằng chứng

| Hạng mục | Before | After | Verdict | Evidence |
|---|---|---|:---:|---|
| Purchase option | 100% On-Demand | 40% Spot steady state; 50% Spot tại high-load | PASS | [baseline](./D13-COST-01-ondemand-baseline/D13-COST-01-ondemand-baseline.md), [optimized report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) |
| Worker architecture | 100% x86_64 | 100% live ARM64/Graviton tại checkpoint | PASS | [EC2 baseline](./D13-COST-01-ondemand-baseline/raw/10-ec2-instances-table.txt), [ARM64 verdict](./D13-MANAGED-ARM64-MIGRATION-VERDICT.md) |
| Checkout success | 99.22% baseline | 99.96%–99.98% theo phase optimized | PASS | [baseline Locust](./D13-COST-01-ondemand-baseline/locust/locust-stats-requests.json), [optimized report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) |
| Scale-down/consolidation | Nền On-Demand cố định | Peak 6 nodes, sau tải quay về reliability floor/topology steady | PASS | [telemetry CSV](./lowhighlow_telemetry.csv), [Grafana ramp-down](./screenshots/04-ramp-down-grafana-2.png) |
| Spot interruption | Không áp dụng trong baseline | Replacement và reschedule hoàn tất trong 3m14s; 0 customer-visible error | PASS | [interruption drill](./D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md) |
| Workload eligibility | Chưa phân loại Spot/ARM64 | Có ma trận stateless/stateful, probe, PDB và ARM64 | PASS | [eligibility matrix](./jira-report/SPOT-ARM64-ELIGIBILITY-MATRIX.md) |
| ADR/sign-off | Chưa có quyết định ARM64/Spot | ADR trạng thái `ACCEPTED / SIGNED` | PASS | [ADR-013](./ADR-013-arm64-spot-capacity-decision.md) |

## 9. Bản đồ mentor tự xác minh

| Câu hỏi kiểm tra | Mở evidence | Cách đối soát |
|---|---|---|
| Baseline có thật sự 100% On-Demand/x86 không? | [EC2 inventory](./D13-COST-01-ondemand-baseline/raw/10-ec2-instances-table.txt), [CE JSON](./D13-COST-01-ondemand-baseline/raw/13-ce-usage-quantity-daily.json) | Kiểm `Architecture`, instance type, purchase option/usage type |
| Optimized có thật sự dùng Graviton và Spot không? | [ARM64 verdict](./D13-MANAGED-ARM64-MIGRATION-VERDICT.md), [Cost Explorer 28/07](./screenshots/06-cost-explorer-trend-jul28.jpg) | Đối chiếu family `t4g/c7g/r7g`, capacity type và AZ |
| Tải có đúng thấp → cao → thấp không? | [report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md), [telemetry CSV](./lowhighlow_telemetry.csv), [screenshots](./screenshots/) | Đối chiếu timestamp, users, node count và HPA theo phase |
| Node-hour được tính thế nào? | [mục 5.2](#52-node-hour-calculation-trên-load-profile), [report gốc](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md) | Tính lại `Σ(nodes × hours)` cho từng phase |
| SLO/correctness của Checkout có giữ không? | [baseline Locust](./D13-COST-01-ondemand-baseline/locust/locust-report.html), [optimized report](./D13-FULL-LOWHIGHLOW-RUN-EVIDENCE.md), [Grafana high peak](./screenshots/03-high-peak-grafana-2.png) | Đối chiếu request/failure denominator và success theo phase |
| HPA/Quota có source of truth không? | [HPA template](../../../techx-corp-chart/templates/hpa.yaml), [values](../../../techx-corp-chart/values.yaml), [quota](../../../deploy/quota.yaml) | Render chart hoặc đọc min/max/requests/limits |
| Karpenter có giới hạn và diversification không? | [NodePool Terraform](../../../infra/terraform/karpenter-nodepool.tf) | Kiểm requirements, allow-list, CPU limits, disruption và consolidation |
| Interruption có phải runtime drill không? | [drill report](./D13-SPOT-INTERRUPTION-DRILL-EVIDENCE.md) | Đối chiếu NodeClaim, EC2 ID, UTC timeline và cumulative request/error counters |
| Ai phê duyệt quyết định? | [ADR-013](./ADR-013-arm64-spot-capacity-decision.md) | Kiểm status, ngày ký và hai vai trò phê duyệt |

## 10. Change records

| Phạm vi | Change record |
|---|---|
| Load/SLO contract | [PR #312](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/312), commit [`1e4ddb9`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/1e4ddb9ea6aeef8f29f5392305feb76b654870fb) |
| On-Demand baseline | [PR #515](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/515) |
| HPA/ResourceQuota validation | [PR #498](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/498) |
| Spot/ARM64 eligibility | [PR #326](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/326) |
| Karpenter NodePool research/checklist | [PR #740](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/740) |
| Operator execution plan | commit [`101a6de`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/101a6deafd4764f38ae71e6e4d44b755ac76601f), [PR #746](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/746) |
| Mandate 13 evidence package | [PR #742](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/742) |
| Managed ARM64 migration | [PR #719](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/719), commit [`acd947f3`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/acd947f3) |

