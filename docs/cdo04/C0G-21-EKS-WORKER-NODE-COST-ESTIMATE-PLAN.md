# C0G-21 — Ước tính chi phí EKS worker node và kế hoạch Cost Optimization với Karpenter

> **Trạng thái:** Đã hoàn tất static estimate và có runtime evidence cho Karpenter. Mọi thay đổi Managed Node Group, NodePool limit hoặc workload placement vẫn **BLOCKED** đến khi chốt budget guardrail và đủ live evidence.  
> **Phạm vi:** Đánh giá chi phí Managed Node Group, Karpenter dynamic capacity, các phương án instance type và roadmap Cost Optimization. Tài liệu này không thay đổi Terraform hoặc AWS runtime.  
> **Ngày:** 2026-07-16

## 1. Mục tiêu

Đánh giá các phương án đưa chi phí EKS worker node về trong budget guardrail mà không làm giảm an toàn vận hành:

- tính chi phí hiện tại của Managed Node Group và Karpenter dynamic capacity;
- so sánh `t3.large`, `t3a.large`, `t4g.large` và `t3.medium`;
- đánh giá tác động thực tế của việc giảm Managed Node Group `max_size`;
- ghi nhận các Cost Optimization controls Karpenter đang hoạt động;
- xác định evidence, entry gate, controlled trial và rollback plan.

## 2. Current baseline

| Hạng mục | Current configuration / evidence |
|---|---|
| AWS Region | `us-east-1` |
| Managed Node Group | `techx-general-ng` |
| Managed Node Group | `t3.large`, On-Demand, `min_size=2`, `desired_size=2`, `max_size=4` |
| Managed root volume | 20 GiB `gp3` mỗi node |
| Karpenter controller | Đã deploy, `2/2` Ready trên hai managed worker nodes |
| Karpenter NodePool | `techx-general`, `Ready=True`; AMD64, Linux, On-Demand, chỉ `t3.large` / `t3a.large` |
| Karpenter NodePool limit | `limits.cpu = 16` |
| Karpenter lifecycle | `expireAfter = 720h`, `WhenEmptyOrUnderutilized`, `consolidateAfter = 5m` |
| Karpenter AMI | pinned `al2023@v20260709` |
| Karpenter runtime | Đã provision `t3a.large` để giải quyết `Insufficient cpu`; đã quan sát consolidation từ 4 xuống 3 workers |
| Terraform AWS Budget | `$300/month` |
| Onboarding budget guardrail | khoảng `$300/week/TF` |

Terraform là source of truth duy nhất cho `techx-general`; các historical manifest trong `deploy/karpenter/` đã deprecated và **không được apply**.

Nguồn chính:

- `infra/terraform/eks.tf`
- `infra/terraform/karpenter-nodepool.tf`
- `infra/terraform/budgets.tf`
- `infra/terraform/variables.tf`
- `deploy/karpenter/README.md`
- `docs/cdo08/week2/output/karpenter_autoscaling_evidence.md`
- `docs/evidence/directive-03/cost/02-post-maintenance-cost-cleanup.md`

## 3. Budget guardrail blocker

Repository hiện có hai guardrail không khớp nhau:

| Nguồn | Guardrail |
|---|---:|
| Onboarding mandate | khoảng `$300/week/TF` |
| Terraform `aws_budgets_budget` | `$300/month` |

`$300/month` là limit đang được technical enforcement qua Terraform; `$300/week/TF` là mandate trong onboarding. Controlled trial làm thay đổi configuration chỉ được bắt đầu khi đã xác nhận guardrail áp dụng.

Nếu `$300/month` là guardrail chính thức, baseline known cost chỉ còn ít headroom cho Karpenter dynamic node và các chi phí chưa được Cost Explorer reconcile. Nếu `$300/week` là guardrail chính thức, AWS Budget Terraform phải được review riêng để tránh alert/decision không nhất quán.

## 4. Cost model

### 4.1 Managed Node Group EC2 estimate

Giá dưới đây là Linux, Shared Tenancy, On-Demand tại `us-east-1`, lấy từ AWS Price List API ngày 2026-07-16. Monthly estimate dùng 730 giờ. Đây là public-price estimate, không phải actual billing từ Cost Explorer; actual billing có thể khác nếu có Savings Plans hoặc Reserved Instances.

| Option | Calculation | EC2/month | Delta so với current |
|---|---:|---:|---:|
| Current: 2 × `t3.large` | `2 × $0.0832 × 730` | **$121.47** | baseline |
| Same shape, AMD64: 2 × `t3a.large` | `2 × $0.0752 × 730` | **$109.79** | **-$11.68 (-9.6%)** |
| Same shape, ARM64: 2 × `t4g.large` | `2 × $0.0672 × 730` | **$98.11** | **-$23.36 (-19.2%)** |
| Smaller: 2 × `t3.medium` | `2 × $0.0416 × 730` | **$60.74** | **-$60.74 (-50.0%)** |

Bảng này không gồm EBS, EKS, NAT Gateway, load balancer, logs, transfer, ECR và các chi phí ngoài EC2 compute.

### 4.2 Known all-in baseline

| Cost component | Estimated monthly cost |
|---|---:|
| 2 × `t3.large` Managed Node Group | $121.47 |
| EKS control plane | $73.00 |
| One NAT Gateway | $32.85 |
| NAT public IPv4 | $3.65 |
| Managed-node root `gp3` volumes | $3.20 |
| Application/data `gp2` volumes | $3.30 |
| **Known subtotal** | **$237.47** |

| Managed Node Group option | Known all-in/month | Headroom so với `$300/month` |
|---|---:|---:|
| Current: 2 × `t3.large` | **$237.47** | **$62.53** |
| 2 × `t3a.large` | **$225.79** | **$74.21** |
| 2 × `t4g.large` | **$214.11** | **$85.89** |
| 2 × `t3.medium` | **$176.73** | **$123.27** |

Known subtotal chưa gồm Karpenter actual node-hours/root volumes, ALB/NLB/LCU, CloudWatch log ingestion và storage, AWS Config/CloudTrail, ECR, NAT data processing, internet/cross-AZ data transfer, snapshots, S3 hoặc public IPv4 khác.

### 4.3 Karpenter dynamic capacity — runtime evidence

Karpenter đã provision `t3a.large` dynamic node để xử lý Pending pod do `Insufficient cpu`. Runtime cleanup evidence ghi nhận:

```text
Full t3a.large worker cost/node/hour
= $0.0752 compute + ($1.60 / 730) root gp3
≈ $0.0773918/hour
```

| Quan sát | Estimate |
|---|---:|
| Một `t3a.large` chạy ~5.617 giờ | ~$0.435 tích lũy |
| Một `t3a.large` chạy 24 giờ | ~$1.86/day |
| Một `t3a.large` chạy 168 giờ | ~$13.00/week |

Các số trên là estimate theo observed runtime hours × full worker cost, **không phải Cost Explorer actual billing**. Cost Explorer có thể cần 24–48 giờ để xử lý usage; actual cost phải được reconcile sau khi bucket usage không còn `Estimated`.

Karpenter cũng đã tự consolidation từ 4 workers (2 managed + 2 Karpenter) về 3 workers (2 managed + 1 Karpenter). Điều này xác nhận `WhenEmptyOrUnderutilized` đang tạo scale-down effect, nhưng không chứng minh final resting baseline đã được phê duyệt.

### 4.4 Karpenter cost ceiling

Managed Node Group `max_size` không giới hạn Karpenter. `techx-general` có `limits.cpu = 16`; với instance 2 vCPU, ceiling lý thuyết là tối đa 8 dynamic nodes:

```text
8 × t3a.large compute/month
= 8 × $0.0752 × 730
= ~$439.17/month
```

Đây là **capacity/cost ceiling**, không phải expected steady state. Actual NodeClaim count, node-hours, Pending pods và Cost Explorer data phải quyết định việc có hạ `limits.cpu` hay không. Không được hạ limit chỉ để giảm estimate nếu nó khiến required pod bị Pending.

## 5. Capacity assessment

Static repository analysis ước tính:

| Metric | Estimate |
|---|---:|
| Known CPU requests | ~4.425 vCPU, chưa gồm một phần system add-ons |
| Known memory requests | ~7.30 GiB, chưa gồm system add-ons |
| Current managed raw capacity | 4 vCPU / 16 GiB |
| 2 × `t3.medium` raw capacity | 4 vCPU / 8 GiB |

Hai `t3.medium` có raw CPU không đủ so với known CPU requests và memory headroom gần như không còn sau Kubernetes system overhead. Allocatable capacity luôn thấp hơn raw capacity. Vì vậy `t3.medium` là **NO-GO** cho controlled trial với evidence hiện tại.

Các request trên là static value từ configuration; cần đối chiếu bằng `kubectl top nodes`, `kubectl top pods -A --containers`, `ResourceQuota`, HPA behavior và workload SLO. `t3`, `t3a` và `t4g` đều là burstable; cần kiểm tra `CPUUtilization`, `CPUCreditBalance`, `CPUSurplusCreditBalance` và `CPUSurplusCreditsCharged` trong representative load window.

## 6. Option comparison và recommendation

| Option | Cost impact | Đánh giá |
|---|---|---|
| Reduce MNG `max_size` từ 4 xuống 2 | Không giảm baseline vì `desired_size=2` | Không áp dụng chỉ để tiết kiệm; có thể chặn HPA/surge capacity. |
| Reduce MNG `max_size` từ 4 xuống 3 | Không giảm baseline | Chỉ cân nhắc sau khi HPA/load evidence chứng minh node thứ tư không cần thiết. |
| `t3.large` → `t3.medium` | Giảm ~$60.74/month EC2 | **NO-GO:** CPU deficit và memory headroom không đủ. |
| `t3.large` → `t3a.large` | Giảm ~$11.68/month EC2 | **First trial candidate:** cùng 2 vCPU/8 GiB, AMD64; Karpenter đã có runtime evidence provision `t3a.large`. |
| `t3.large` → `t4g.large` | Giảm ~$23.36/month EC2 | **Second-phase candidate:** cùng capacity shape, saving lớn hơn; yêu cầu platform-wide ARM64 validation. |
| Lower Karpenter `limits.cpu` | Giới hạn dynamic-cost ceiling, không giảm static baseline | Chỉ đánh giá sau khi có NodeClaim/node-hour/load evidence. |

### Recommendation

1. Không trial `t3.medium` và không coi giảm `max_size` là cost saving trực tiếp.
2. Ưu tiên controlled trial cô lập `t3.large` → `t3a.large` cho Managed Node Group: cùng capacity shape và không đổi AMD64 compatibility.
3. Cân nhắc `t4g.large` là phase 2 sau khi ARM64 evidence pass; đây không phải like-for-like swap vì Managed Node Group đang host system components, observability, stateful/singleton workloads và Karpenter controller.
4. Không đổi instance type, `max_size`, Karpenter limit, workload requests hoặc observability configuration trong cùng một trial.

## 7. Karpenter Cost Optimization roadmap và best practices

### 7.1 Giữ Managed Node Group làm system và rollback floor

Giữ minimum hai managed nodes trải trên hai AZ trong mọi Karpenter pilot. Controller đã chạy hai replicas trên managed capacity. Không giảm xuống một node để đổi lấy saving vì sẽ tạo single-node/single-AZ failure domain và làm rollback yếu đi.

### 7.2 Terraform là source of truth

Chỉ thay đổi `infra/terraform/karpenter-nodepool.tf`. Không apply historical YAML trong `deploy/karpenter/`; chúng dùng configuration cũ và không còn là owner của `techx-general`.

### 7.3 Dùng NodePool limit như cost guardrail

Giữ `limits.cpu = 16` trong Estimate-only phase. Hàng tuần đối chiếu NodeClaim, node-hours, requested/allocatable CPU-memory, Pending pod và Cost Explorer. Chỉ đề xuất limit thấp hơn sau khi evidence cho thấy peak demand cộng replacement buffer vẫn nằm dưới limit mới.

### 7.4 Consolidation theo điều kiện drainable workload

`WhenEmptyOrUnderutilized` và `consolidateAfter = 5m` đang hoạt động, đã có evidence 4→3 workers. Trước khi mở rộng Karpenter admission hoặc thay đổi consolidation, phải xác nhận workload có requests đúng, ít nhất hai replicas khi cần HA, PDB, readiness/liveness probes và topology spread. Theo dõi `Unconsolidatable`, eviction, PDB violation, provisioning duration, Pending pod và replacement time.

### 7.5 Giữ AMI pinning và explicit security-group selection

Giữ `al2023@v20260709` pinned; review phiên bản AL2023 mới theo change riêng và pin bản đã test, không dùng `@latest`. Giữ `karpenter.sh/node-security-group` selector thay vì shared discovery tag để tránh attach nhiều security group và gây AWS Load Balancer Controller reconciliation issue.

### 7.6 Tách pool theo workload class khi mở rộng

Không mở rộng `techx-general` thành pool chung cho mọi architecture/capacity type. Khi đủ evidence, tạo pool loại trừ nhau bằng `workload-class` label/selector:

| Pool tương lai | Architecture / capacity | Admission |
|---|---|---|
| `apps-amd64-ondemand` | AMD64, On-Demand | Replicated stateless workload đã đo requests |
| `apps-arm64-ondemand` | ARM64, On-Demand | Chỉ workload có verified `linux/arm64` manifest |
| `apps-flex-spot` | Diversified Spot + On-Demand fallback | Chỉ workload đã pass PDB, topology và interruption drill |

### 7.7 ARM64 / `t4g.large` readiness

`2 × t4g.large` có cùng raw capacity 4 vCPU / 16 GiB như current MNG và tiết kiệm khoảng 19.2% Managed Node Group EC2 cost. Trước trial, phải verify `linux/arm64` cho primary container, init container, sidecar, CoreDNS, VPC CNI, EBS CSI, Karpenter, observability và stateful services. Nếu bất kỳ dependency nào không tương thích, giữ MNG AMD64.

### 7.8 Spot là phase cuối

Spot chưa nằm trong current NodePool và không được dùng để chứng minh saving ban đầu. Chỉ thêm Spot NodePool sau khi stateless workload có PDB, replicas, graceful termination, topology spread, interruption handling và replacement drill pass. Không pre-claim percentage saving; chỉ compare blended Spot + On-Demand fallback cost trên billing-complete window.

## 8. Estimate-only / evidence plan — Week 2

Không thay đổi node type, node count, Karpenter limit, workload placement hoặc Terraform resource trong phase này.

1. **Chốt budget guardrail**
   - Xác nhận `$300/week` hoặc `$300/month` là guardrail áp dụng.
   - Ghi rõ technical enforcement và mandate nếu chưa thể đồng nhất ngay.

2. **Capture live cluster và Karpenter evidence**

   ```bash
   kubectl get nodes \
     -L node.kubernetes.io/instance-type,karpenter.sh/nodepool,topology.kubernetes.io/zone
   kubectl top nodes
   kubectl top pods -A --containers
   kubectl get pods -A -o wide
   kubectl get hpa -A
   kubectl get nodepool,ec2nodeclass,nodeclaim -o wide
   kubectl get events -A --sort-by=.lastTimestamp
   ```

3. **Capture AWS cost và burstable-instance evidence**
   - Cost Explorer daily cost theo service và usage type; reconcile lại sau 24–48 giờ nếu bucket còn `Estimated`.
   - EC2 instance-hours theo `t3.large`/`t3a.large`, EBS, NAT, load balancer, logging và transfer.
   - CloudWatch `CPUUtilization`, `CPUCreditBalance`, `CPUSurplusCreditBalance`, `CPUSurplusCreditsCharged`.
   - Karpenter NodeClaim lifecycle, dynamic node-hours, consolidation events và root-volume usage.

4. **Validate ARM64 readiness**
   - Inspect image manifest theo digest cho mọi workload chạy trên Managed Node Group, gồm primary/init/sidecar container.
   - Xác nhận ARM64 support cho EKS add-ons, Karpenter, observability và stateful dependencies.
   - Ghi rõ blocker cho `t4g.large` nếu thiếu `linux/arm64`.

5. **Tạo comparable cost calculation**
   - Tách fixed cost, Managed Node Group EC2/EBS, Karpenter EC2/EBS, NAT/transfer và observability.
   - Report node-hours, requested/allocatable CPU-memory và Karpenter dynamic node-hours.
   - Tính `variable EC2 + EBS cost / 1,000 successful requests` và `variable EC2 + EBS cost / 1,000 successful checkouts`.

6. **Ghi decision**
   - **PASS:** budget confirmed, accounting stable, capacity headroom an toàn và trial gate pass.
   - **BLOCKED:** budget conflict, thiếu Cost Explorer/runtime/ARM64/observability/smoke-test evidence.
   - **NO-GO:** option không đáp ứng CPU, memory, reliability, performance hoặc cost criterion.

## 9. Controlled-trial entry gates

Controlled trial chỉ bắt đầu khi tất cả điều kiện sau đúng:

- `LOCUST_AUTOSTART=false` ngoài approved measurement window.
- Budget guardrail được chốt và Cost Explorer/accounting ổn định.
- Jaeger, Grafana và Prometheus healthy; có CPU/memory, restart, throttling, p95 và checkout success/error data.
- Có live evidence cho workload, system add-ons và Karpenter capacity.
- Smoke test pass trước khi thay đổi.
- Có approval rõ ràng trước Terraform apply.
- Không có unexplained CPU-credit depletion hoặc surplus-credit charge.
- Có T0 evidence package, rollback window và rollback procedure đã review.

## 10. First controlled trial — Managed Node Group `t3.large` sang `t3a.large`

1. Capture T0: node type/count/AZ, pod placement, CPU/memory, CPU credits, p95 browse latency, checkout success/error rate, restarts, throttling, Karpenter node-hours và daily cost.
2. Chuẩn bị một Terraform change cô lập:

   ```hcl
   instance_types = ["t3a.large"]
   ```

3. Không kết hợp với thay đổi `max_size`, Karpenter `limits.cpu`, workload requests, HPA hoặc observability configuration.
4. Review Terraform plan và lấy approval trước apply.
5. Apply Managed Node Group rolling replacement; sau mỗi replacement xác nhận node `Ready`, workload healthy và vẫn phân bố qua hai AZ.
6. Chạy approved smoke/load test, quan sát 48–72 giờ và đối chiếu T1 với T0.
7. Chỉ giữ thay đổi nếu success criteria pass; nếu fail thì rollback về `t3.large`.

## 11. Optional second-phase trial — Managed Node Group `t3.large` sang `t4g.large`

Chỉ thực hiện sau khi ARM64 validation pass và có approval độc lập.

1. Xác nhận verified `linux/arm64` manifest cho toàn bộ managed-node workload, init container, sidecar và required platform dependency.
2. Capture AMD64 T0 cùng load profile, bao gồm CPU-credit metrics.
3. Chuẩn bị một Terraform change cô lập:

   ```hcl
   instance_types = ["t4g.large"]
   ```

4. Apply rolling replacement; sau mỗi node xác minh architecture, `Ready`, system components, observability, stateful services và smoke test.
5. Chạy cùng load profile, quan sát 48–72 giờ, compare T1 với AMD64 T0.
6. Giữ thay đổi khi tất cả success criteria pass và measured cost benefit khớp estimate; nếu không, rollback về `t3.large`.

## 12. Trial success criteria

| Dimension | Required result |
|---|---|
| Performance | Browse p95 dưới existing 1-second SLO ở equivalent load. |
| Checkout | Successful checkouts ít nhất 99.0%. |
| Reliability | Không có material OOM, restart, throttling hoặc Pending-pod regression. |
| Capacity | Không có unexpected Karpenter node-hours chỉ để bù cho instance-type change. |
| Observability | Jaeger/Grafana/Prometheus healthy trong toàn bộ trial. |
| Cost | Variable EC2/EBS cost per request và per successful checkout không xấu hơn T0; projected all-in spend nằm trong confirmed guardrail. |
| Safety | Hai managed nodes available qua hai AZ; smoke test pass. |
| ARM64 | Với `t4g.large`, mọi scheduled image/platform dependency verified ARM64 và không có `exec format error`. |

Cost per request/checkouts chỉ được coi là reconciled sau khi Cost Explorer hoàn tất xử lý. Trước thời điểm đó, chỉ ghi `estimated` theo AWS Price List API và observed node-hours.

## 13. Rollback plan

Nếu capacity, SLO, reliability, smoke test, observability hoặc cost gate fail:

1. Revert Managed Node Group về:

   ```hcl
   instance_types = ["t3.large"]
   ```

2. Run Terraform plan và apply rolling replacement về `t3.large`.
3. Chờ replacement node `Ready` và workload replicas healthy trước khi drain old node.
4. Xác nhận hai managed `t3.large` nodes `Ready` qua hai AZ.
5. Xác nhận critical workload, observability, Karpenter state và smoke test healthy.
6. Lưu evidence **FAIL / ROLLED_BACK** gồm test window, raw metrics, cost inputs, calculation, failure reason và rollback result.

## 14. Evidence package

Lưu estimate/trial evidence trong dated folder. Mỗi package phải có:

- exact configuration before/after;
- decision: **PASS**, **FAIL**, **BLOCKED** hoặc **ROLLED_BACK**;
- measurement window và load profile;
- raw Kubernetes metrics, NodeClaim/events và AWS cost inputs;
- cost calculation, assumptions và trạng thái `estimated`/reconciled;
- remaining risks;
- rollback decision/result nếu có.
