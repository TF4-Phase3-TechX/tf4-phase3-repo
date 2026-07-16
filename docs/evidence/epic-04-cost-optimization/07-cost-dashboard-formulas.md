# Cost Dashboard Formula Reference

## Mục tiêu

Tài liệu này liệt kê các công thức đang được dùng hoặc được diễn giải trong Grafana dashboard `Cost Overview and EKS Allocation`.

Dashboard hiện tại là dashboard estimate-first. Nghĩa là dashboard dùng baseline cost estimate và Prometheus runtime metrics để giúp team nhìn nhanh cost posture, chưa dùng Cost Explorer/CUR actual billing.

## Phạm vi

Nguồn dashboard:

- Dashboard JSON: `techx-corp-chart/grafana/provisioning/dashboards/cost-dashboard.json`
- Baseline estimate: `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- ADR quyết định estimate-first: `docs/audit/adr/016-cost-dashboard-estimate-first.md`

Dashboard đang bao phủ:

- Baseline fixed cost estimate.
- Weekly budget usage.
- Ready worker node count.
- EKS compute allocation theo CPU share.
- Workload memory và observability memory.
- Load-generator activity.
- Node CPU/memory pressure.
- Gap note cho storage và usage-based AWS cost chưa có actual billing.

Dashboard chưa bao phủ actual billing từ Cost Explorer/CUR.

## Nguồn đơn giá

| Thành phần | Đơn giá đang dùng | Nguồn | Ghi chú |
| --- | ---: | --- | --- |
| EKS standard support control plane | `$0.10/cluster-hour` | AWS EKS Pricing | Dùng cho cluster Kubernetes version thuộc standard support. |
| EC2 `t3.large` Linux On-Demand, us-east-1 | `$0.0832/instance-hour` | AWS Pricing API evidence: `docs/evidence/directive-03/cost/raw/40-pricing-t3-large-round2.json` | Output ghi `pricePerUnit.USD = 0.0832000000`, effective date `2026-07-01`. |
| NAT Gateway hourly | `$0.045/hour` | AWS VPC Pricing | Chưa tính data processing. |
| NAT Gateway data processing | `$0.045/GB` | AWS VPC Pricing | Chưa đưa vào baseline vì phụ thuộc traffic thực tế. |
| ALB hourly | `$0.0225/hour` | AWS Elastic Load Balancing Pricing | Chưa tính LCU usage trong fixed baseline. |
| ALB LCU | `$0.008/LCU-hour` | AWS Elastic Load Balancing Pricing | Chưa đưa vào fixed baseline vì phụ thuộc traffic thực tế. |
| EBS gp3 storage | `$0.08/GB-month` | AWS EBS Pricing | Dùng cho worker root EBS estimate. |
| Weekly budget | `$300/week` | Dashboard variable `weekly_budget_usd` | Budget target hiện dùng để tính phần trăm budget used. |

## Quy ước tính toán

| Quy ước | Giá trị | Mục đích |
| --- | ---: | --- |
| Hours per month | `730` | Quy đổi hourly AWS price sang monthly estimate. |
| Weeks per month | `4.345` | Quy đổi monthly estimate sang weekly estimate. |
| Days per week | `7` | Quy đổi hourly node cost sang weekly node compute estimate. |
| Hours per day | `24` | Quy đổi hourly node cost sang daily/weekly estimate. |

## Công thức baseline fixed cost

### 1. EKS control plane monthly cost

```txt
EKS monthly = cluster_count * eks_hourly_usd * 730
```

Với baseline hiện tại:

```txt
1 * 0.10 * 730 = 73.00 USD/month
```

Mục đích:

- Thể hiện chi phí cố định của EKS control plane.
- Giúp team thấy EKS vẫn phát sinh cost kể cả khi workload thấp.

Nguồn:

- AWS EKS Pricing.
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`

### 2. EC2 worker node monthly cost

```txt
EC2 worker monthly = ready_or_desired_node_count * node_hourly_usd * 730
```

Với baseline hiện tại:

```txt
2 * 0.0832 * 730 = 121.47 USD/month
```

Mục đích:

- Thể hiện compute cost chính của cụm EKS.
- Là nền để dashboard phân bổ estimated compute cost xuống workload.

Nguồn:

- AWS Pricing API evidence: `docs/evidence/directive-03/cost/raw/40-pricing-t3-large-round2.json`
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`

### 3. EBS worker root volume monthly cost

```txt
EBS monthly = total_gb * gp3_usd_per_gb_month
```

Với baseline hiện tại:

```txt
40 * 0.08 = 3.20 USD/month
```

Mục đích:

- Ghi nhận phần storage cố định đi kèm worker nodes.
- Tách storage baseline khỏi compute baseline để review dễ hơn.

Nguồn:

- AWS EBS Pricing.
- Runtime evidence trong `01-baseline-cost-estimate.md`: 2 gp3 volumes, tổng 40 GiB.

### 4. NAT Gateway hourly monthly cost

```txt
NAT monthly = nat_gateway_count * nat_hourly_usd * 730
```

Với baseline hiện tại:

```txt
1 * 0.045 * 730 = 32.85 USD/month
```

Mục đích:

- Thể hiện NAT Gateway là fixed cost driver dù traffic thấp.
- Giúp team phân biệt fixed NAT hourly cost với NAT data processing cost.

Nguồn:

- AWS VPC Pricing.
- Runtime evidence trong `01-baseline-cost-estimate.md`: 1 NAT Gateway.

### 5. ALB hourly monthly cost

```txt
ALB monthly = alb_count * alb_hourly_usd * 730
```

Với baseline hiện tại:

```txt
1 * 0.0225 * 730 = 16.43 USD/month
```

Mục đích:

- Thể hiện fixed entry-point cost cho application traffic.
- Tách ALB hourly cost khỏi ALB LCU usage cost.

Nguồn:

- AWS Elastic Load Balancing Pricing.
- Runtime evidence trong `01-baseline-cost-estimate.md`: 1 internet-facing ALB.

### 6. Monthly Fixed Baseline Estimate

```txt
Monthly fixed baseline =
  EKS monthly
  + EC2 worker monthly
  + EBS monthly
  + NAT hourly monthly
  + ALB hourly monthly
```

Với baseline hiện tại:

```txt
73.00 + 121.47 + 3.20 + 32.85 + 16.43 = 246.95 USD/month
```

Dashboard variable:

```txt
monthly_fixed_estimate_usd = 246.95
```

Mục đích:

- Là con số headline để team biết fixed baseline đang khoảng bao nhiêu tiền mỗi tháng.
- Chưa phải actual bill vì chưa tính usage-based cost và billing adjustment.

Nguồn:

- Dashboard JSON variable `monthly_fixed_estimate_usd`.
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`

### 7. Weekly Fixed Baseline Estimate

```txt
Weekly fixed baseline = monthly_fixed_estimate_usd / 4.345
```

Với baseline hiện tại:

```txt
246.95 / 4.345 = 56.83 USD/week
```

Dashboard variable:

```txt
weekly_fixed_estimate_usd = 56.83
```

Mục đích:

- Đưa monthly estimate về weekly view để so với budget `$300/week`.
- Phù hợp với nhịp review cost theo tuần của project.

Nguồn:

- Dashboard JSON variable `weekly_fixed_estimate_usd`.
- `01-baseline-cost-estimate.md`

## Công thức budget và runtime estimate trong dashboard

### 8. Weekly Budget Used

PromQL trong dashboard:

```promql
100 * vector(${weekly_fixed_estimate_usd}) / vector(${weekly_budget_usd})
```

Với baseline hiện tại:

```txt
100 * 56.83 / 300 = 18.94%
```

Mục đích:

- Cho biết fixed baseline đang dùng bao nhiêu phần trăm weekly budget.
- Dùng để cảnh báo sớm nếu baseline tiến gần 70%, 90%, hoặc 100% budget.

Nguồn:

- Dashboard JSON panel `Weekly Budget Used`.

### 9. Ready Worker Nodes

PromQL trong dashboard:

```promql
sum(k8s_node_condition{condition="Ready"}) or vector(0)
```

Mục đích:

- Đếm số worker node đang Ready.
- Nếu số node tăng, compute burn có thể tăng theo.
- Là input cho các công thức estimate node cost theo ngày/tuần.

Nguồn:

- Prometheus metric `k8s_node_condition`.
- Dashboard JSON panel `Ready Worker Nodes`.

### 10. Current Ready-Node EC2 Estimate

PromQL trong dashboard:

```promql
(sum(k8s_node_condition{condition="Ready"}) or vector(2)) * ${node_hourly_usd} * 24
```

Công thức:

```txt
Ready-node EC2 estimate per day =
  ready_node_count * node_hourly_usd * 24
```

Mục đích:

- Cho biết estimated EC2 compute burn theo ngày dựa trên node Ready hiện tại.
- Bắt được tình huống node count tăng so với baseline 2 nodes.

Nguồn:

- Dashboard JSON panel `Current Ready-Node EC2 Estimate (USD/day)`.
- Prometheus metric `k8s_node_condition`.
- Dashboard variable `node_hourly_usd = 0.0832`.

### 11. CPU Share by Workload

PromQL trong dashboard:

```promql
100 * sum by (namespace, container) (
  rate(container_cpu_usage_seconds_total{
    namespace=~"techx-tf4|techx-observability",
    container!="",
    container!="POD"
  }[$__rate_interval])
) / scalar(sum(rate(container_cpu_usage_seconds_total{
  namespace=~"techx-tf4|techx-observability",
  container!="",
  container!="POD"
}[$__rate_interval])))
```

Công thức:

```txt
CPU share by workload =
  workload_cpu_usage_rate / total_cpu_usage_rate * 100
```

Mục đích:

- Xác định workload nào đang dùng tỷ trọng CPU lớn nhất.
- Là cơ sở để phân bổ estimated EC2 compute cost theo workload.
- Hỗ trợ right-sizing và tìm workload gây cost pressure.

Nguồn:

- Prometheus/cAdvisor metric `container_cpu_usage_seconds_total`.
- Dashboard JSON panel `CPU Share by Workload`.

### 12. CPU-Weighted Estimated Compute Cost by Workload

PromQL trong dashboard:

```promql
(
  sum by (namespace, container) (
    rate(container_cpu_usage_seconds_total{
      namespace=~"techx-tf4|techx-observability",
      container!="",
      container!="POD"
    }[$__rate_interval])
  )
  / scalar(sum(rate(container_cpu_usage_seconds_total{
    namespace=~"techx-tf4|techx-observability",
    container!="",
    container!="POD"
  }[$__rate_interval])))
)
* scalar((sum(k8s_node_condition{condition="Ready"}) or vector(2)) * ${node_hourly_usd} * 24 * 7)
```

Công thức:

```txt
Workload estimated compute cost per week =
  workload_cpu_share
  * ready_node_count
  * node_hourly_usd
  * 24
  * 7
```

Mục đích:

- Phân bổ estimated EC2 worker node cost cho từng workload theo CPU share.
- Giúp team biết workload nào đang chiếm nhiều phần compute cost nhất.
- Đây là allocation estimate, không phải Cost Explorer actual billing.

Nguồn:

- Dashboard JSON panel `CPU-Weighted Estimated Compute Cost by Workload (USD/week)`.
- Prometheus/cAdvisor metric `container_cpu_usage_seconds_total`.
- Prometheus metric `k8s_node_condition`.
- Dashboard variable `node_hourly_usd = 0.0832`.

### 13. Memory Usage by Workload

PromQL trong dashboard:

```promql
sum by (namespace, container) (
  container_memory_working_set_bytes{
    namespace=~"techx-tf4|techx-observability",
    container!="",
    container!="POD"
  }
) / 1024 / 1024
```

Công thức:

```txt
Memory MiB = container_memory_working_set_bytes / 1024 / 1024
```

Mục đích:

- Cho biết memory footprint của từng workload.
- Memory cao có thể ép cluster phải dùng node lớn hơn hoặc nhiều node hơn.
- Hỗ trợ right-sizing request/limit và kiểm tra observability overhead.

Nguồn:

- Prometheus/cAdvisor metric `container_memory_working_set_bytes`.
- Dashboard JSON panel `Memory Usage by Workload`.

### 14. Observability Stack Memory

PromQL trong dashboard:

```promql
sum by (container) (
  container_memory_working_set_bytes{
    namespace=~"techx-tf4|techx-observability",
    container=~"grafana|prometheus|jaeger|opensearch|otel-collector|otel-collector-agent"
  }
) / 1024 / 1024
```

Mục đích:

- Tách riêng memory cost driver của observability stack.
- Giúp đánh giá Grafana, Prometheus, Jaeger, OpenSearch, OTel Collector có đang tiêu thụ tài nguyên quá cao không.

Nguồn:

- Prometheus/cAdvisor metric `container_memory_working_set_bytes`.
- Dashboard JSON panel `Observability Stack Memory`.

### 15. Load Generator Activity

PromQL trong dashboard:

```promql
sum(rate(traces_span_metrics_calls_total{service_name="load-generator"}[5m])) or vector(0)
```

Mục đích:

- Phát hiện load-generator đang tạo synthetic traffic hay không.
- Synthetic traffic có thể làm tăng trace/log volume và làm cost allocation bị lệch.

Nguồn:

- Prometheus span metrics `traces_span_metrics_calls_total`.
- Dashboard JSON panel `Load Generator Activity`.

### 16. Node CPU Usage %

PromQL trong dashboard:

```promql
(
  max by (k8s_node_name) (k8s_node_cpu_usage)
  / on (k8s_node_name)
  label_replace(
    max by (instance) (machine_cpu_cores{job="kubernetes-nodes-cadvisor"}),
    "k8s_node_name",
    "$1",
    "instance",
    "(.*)"
  )
) * 100
```

Công thức:

```txt
Node CPU usage percent =
  node_cpu_usage_cores / node_total_cpu_cores * 100
```

Mục đích:

- Kiểm tra node CPU pressure.
- Nếu CPU usage cao kéo dài, cluster có thể cần scale out hoặc right-size workload.

Nguồn:

- Prometheus metric `k8s_node_cpu_usage`.
- cAdvisor metric `machine_cpu_cores`.
- Dashboard JSON panel `Node CPU Usage %`.

### 17. Node Memory Usage %

PromQL trong dashboard:

```promql
max by (k8s_node_name) (
  k8s_node_memory_usage_bytes
  / (k8s_node_memory_usage_bytes + k8s_node_memory_available_bytes)
) * 100
```

Công thức:

```txt
Node memory usage percent =
  used_memory_bytes / (used_memory_bytes + available_memory_bytes) * 100
```

Mục đích:

- Kiểm tra node memory pressure.
- Nếu memory usage cao, cluster có thể phải giữ node lớn hơn hoặc thêm node, làm tăng compute cost.

Nguồn:

- Prometheus metrics `k8s_node_memory_usage_bytes`, `k8s_node_memory_available_bytes`.
- Dashboard JSON panel `Node Memory Usage %`.

## Những phần chưa tính trong dashboard

| Hạng mục | Vì sao chưa tính | Cần gì để tính tiếp |
| --- | --- | --- |
| Cost Explorer actual service cost | Phase hiện tại chưa có billing sync/IAM | Cần `ce:GetCostAndUsage` và sync 1 lần/ngày. |
| CUR/Athena actual billing | Scope lớn hơn, có storage/query cost | Cần CUR export, S3 bucket, Athena table, query budget. |
| NAT data processing | Phụ thuộc GB traffic thực tế | Cần Cost Explorer hoặc network metric đủ tin cậy. |
| ALB LCU usage | Phụ thuộc request, bandwidth, connection, rule evaluation | Cần ALB CloudWatch metrics hoặc Cost Explorer. |
| ECR storage | Chưa đo image size/count trong dashboard | Cần ECR inventory hoặc Cost Explorer. |
| CloudWatch ingest/storage | Phụ thuộc log volume và retention | Cần CloudWatch log group usage hoặc Cost Explorer. |
| Data transfer | Phụ thuộc hướng traffic và cross-AZ/internet | Cần Cost Explorer và network traffic evidence. |
| EBS/PVC actual billing | Dashboard mới ghi nhận gap, chưa reconcile actual bill | Cần AWS inventory hoặc Cost Explorer. |

## Cách sử dụng tài liệu khi nghiệm thu

- Đối chiếu từng panel trong dashboard với công thức tương ứng trong tài liệu này.
- Nếu reviewer hỏi số `$246.95/month` hoặc `$56.83/week` đến từ đâu, dùng phần `Monthly Fixed Baseline Estimate` và `Weekly Fixed Baseline Estimate`.
- Nếu reviewer hỏi tại sao cost theo workload chỉ là estimate, dùng phần `CPU-Weighted Estimated Compute Cost by Workload`.
- Nếu reviewer hỏi vì sao chưa có actual billing, dùng phần `Những phần chưa tính trong dashboard` và ADR-016.

## References

- `techx-corp-chart/grafana/provisioning/dashboards/cost-dashboard.json`
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- `docs/audit/adr/016-cost-dashboard-estimate-first.md`
- AWS EKS Pricing: https://aws.amazon.com/eks/pricing/
- AWS VPC Pricing: https://aws.amazon.com/vpc/pricing/
- AWS Elastic Load Balancing Pricing: https://aws.amazon.com/elasticloadbalancing/pricing/
- AWS EBS Pricing: https://aws.amazon.com/ebs/pricing/
- AWS Pricing API evidence for EC2 `t3.large`: `docs/evidence/directive-03/cost/raw/40-pricing-t3-large-round2.json`
