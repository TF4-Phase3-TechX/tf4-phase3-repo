# COST-01: Baseline Infrastructure Cost Estimate

## 1. Mục tiêu task

Task này dùng để validate các tài nguyên AWS/EKS đang chạy thực tế sau khi deploy và tạo baseline infrastructure cost estimate ban đầu cho EPIC-04: Cost Optimization.

Mục tiêu chính:

- Xác định các tài nguyên AWS đang tạo chi phí.
- Ghi nhận cost driver chính của hệ thống.
- Ước tính mức độ ảnh hưởng cost của từng thành phần.
- Chuẩn bị evidence để so sánh với Cost Explorer sau khi billing data đầy đủ.
- Tạo cơ sở cho các task tiếp theo như right-sizing, cost saving và cost guardrail.

---

## 2. Phạm vi task

Task này tập trung vào các tài nguyên đã validate được bằng AWS CLI và Kubernetes CLI:

- EKS Cluster
- EKS Managed Node Group
- EC2 Worker Nodes
- EBS Volumes
- NAT Gateway
- Application Load Balancer
- ECR Repository
- CloudWatch Log Groups
- Kubernetes workloads trong namespace `techx-tf4`
- Kubernetes services
- Kubernetes PVC status

Lưu ý: `kubectl get ns` bị giới hạn quyền cluster-scope, nhưng các lệnh namespace-scope trong `techx-tf4` đã chạy được. Vì vậy, Kubernetes runtime evidence trong bản này chỉ tính ở phạm vi namespace `techx-tf4`.

---

## 3. AWS Account & Region

| Item | Value |
|---|---|
| AWS Account ID | 511825856493 |
| Region | us-east-1 |
| EKS Cluster | techx-tf4-cluster |
| Kubernetes Version | 1.30 |
| Cluster Status | ACTIVE |

---

## 4. Assumptions

| Assumption ID | Nội dung | Ghi chú |
|---|---|---|
| COST-ASM-01 | Hệ thống chạy trên EKS | Baseline đã deploy lên AWS |
| COST-ASM-02 | Worker nodes nằm trong private subnets | Outbound traffic đi qua NAT Gateway |
| COST-ASM-03 | Week 1 dùng Single NAT Gateway | Đã validate có 1 NAT Gateway available |
| COST-ASM-04 | ALB được dùng làm entry point | Đã validate có 1 internet-facing Application Load Balancer |
| COST-ASM-05 | ECR dùng để lưu/pull container images | Đã validate repository `techx-corp` |
| COST-ASM-06 | Observability stack chạy trong cluster | Đã thấy Grafana, Jaeger, Prometheus, OpenSearch và OTel Collector trong namespace |
| COST-ASM-07 | Cost Explorer data có thể chưa đầy đủ ngay sau deploy | Actual cost sẽ cập nhật sau |
| COST-ASM-08 | Estimate là baseline ban đầu, chưa phải actual cost | Cần so sánh với Cost Explorer sau |

---

## 5. Baseline Cost Driver List

| Cost Driver | Service / Component | Vì sao tạo chi phí? | Mức độ ảnh hưởng | Evidence cần có |
|---|---|---|---|---|
| Worker Nodes | EC2 / EKS Managed Node Group | Chạy toàn bộ workload EKS | High | Node group config, instance type, node count |
| EBS Root Volume | EBS gp3 | Disk gắn với worker nodes | Medium | EC2 volume list |
| NAT Gateway | VPC NAT Gateway | Outbound traffic từ private subnets | High | NAT Gateway screenshot / route table |
| Application Load Balancer | ALB | Entry point cho user traffic | Medium | ALB screenshot |
| ECR | Elastic Container Registry | Lưu image và pull image | Low/Medium | ECR repo/image list |
| CloudWatch Logs | CloudWatch | Lưu log application/infrastructure nếu enabled | Medium | Log group screenshot |
| CloudWatch Metrics | CloudWatch | Custom metrics / dashboard / alarm | Low/Medium | Metric/dashboard screenshot |
| Observability Stack | Grafana, Jaeger, Prometheus, OpenSearch, OTel Collector | Tốn CPU/RAM trên worker nodes | High | `kubectl get pods`, `kubectl top pods` nếu có metrics-server |
| PVC / Data Volumes | PVC/EBS | Lưu data cho PostgreSQL/Valkey/Kafka/OpenSearch nếu có PVC | Medium/High | `kubectl get pvc` |
| Data Transfer | AWS networking | Traffic cross-AZ/outbound có thể phát sinh phí | Medium | VPC/route/data transfer evidence |

---

## 6. Baseline Infrastructure Inventory

| Resource | Current Value | Cost Impact | Evidence |
|---|---|---|---|
| EKS Cluster | techx-tf4-cluster | Medium | `aws eks list-clusters`, `aws eks describe-cluster` |
| Cluster Status | ACTIVE | Medium | `aws eks describe-cluster` |
| Kubernetes Version | 1.30 | Low | `aws eks describe-cluster` |
| Region | us-east-1 | Medium | AWS CLI output |
| Node Group | techx-general-ng-20260707091432750200000017 | High | `aws eks list-nodegroups` |
| Node Group Status | ACTIVE | High | `aws eks describe-nodegroup` |
| Instance Type | t3.large | High | `aws eks describe-nodegroup` |
| Desired Nodes | 2 | High | `aws eks describe-nodegroup` |
| Min Nodes | 2 | High | `aws eks describe-nodegroup` |
| Max Nodes | 4 | High | `aws eks describe-nodegroup` |
| Node Subnets | subnet-0280b36e2249f33d8, subnet-0753e69d90fe8f820 | Medium | `aws eks describe-nodegroup` |
| EC2 Worker Nodes | 2 running nodes | High | `aws ec2 describe-instances` |
| Worker Node 1 | i-0991279b4d3194388 / t3.large / us-east-1a / 10.0.10.208 | High | `aws ec2 describe-instances` |
| Worker Node 2 | i-0a80b6979ff759588 / t3.large / us-east-1b / 10.0.11.249 | High | `aws ec2 describe-instances` |
| AZ Distribution | us-east-1a, us-east-1b | Medium | `aws ec2 describe-instances` |
| NAT Gateway Count | 1 NAT Gateway | High | `aws ec2 describe-nat-gateways` |
| NAT Gateway ID | nat-0f57f14c4e6039bf4 | High | `aws ec2 describe-nat-gateways` |
| NAT Gateway VPC | vpc-0a4e2abe9fbb70451 | Medium | `aws ec2 describe-nat-gateways` |
| NAT Gateway Subnet | subnet-023018dac76fc69f3 | Medium | `aws ec2 describe-nat-gateways` |
| NAT Gateway State | available | High | `aws ec2 describe-nat-gateways` |
| ALB Count | 1 application load balancer | Medium | `aws elbv2 describe-load-balancers` |
| ALB Name | k8s-techxtf4-techxalb-a25731d323 | Medium | `aws elbv2 describe-load-balancers` |
| ALB Type | application | Medium | `aws elbv2 describe-load-balancers` |
| ALB Scheme | internet-facing | Medium | `aws elbv2 describe-load-balancers` |
| ALB State | active | Medium | `aws elbv2 describe-load-balancers` |
| ALB VPC | vpc-0a4e2abe9fbb70451 | Medium | `aws elbv2 describe-load-balancers` |
| ALB DNS | k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com | Medium | `aws elbv2 describe-load-balancers` |
| EBS Volumes | 2 gp3 volumes | Medium | `aws ec2 describe-volumes` |
| Total EBS Size | 40 GiB | Medium | `aws ec2 describe-volumes` |
| EBS Volume 1 | vol-0b0d90c8d0f1c45a1 / 20 GiB / gp3 / us-east-1a | Medium | `aws ec2 describe-volumes` |
| EBS Volume 2 | vol-0eb7dff02f56a87b0 / 20 GiB / gp3 / us-east-1b | Medium | `aws ec2 describe-volumes` |
| ECR Repository | techx-corp | Low/Medium | `aws ecr describe-repositories` |
| ECR URI | 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp | Low/Medium | `aws ecr describe-repositories` |
| CloudWatch Log Groups | 8 log groups found | Medium | `aws logs describe-log-groups` |
| Kubernetes Namespace Scope | techx-tf4 | High | `kubectl -n techx-tf4 ...` |
| Kubernetes Pods | Around 28 application/observability pods visible, mostly `Running` | High | `kubectl -n techx-tf4 get pods -o wide` |
| Kubernetes Deployments | 25 deployments, all visible deployments have desired/available replicas | High | `kubectl -n techx-tf4 get deploy,sts` |
| Kubernetes StatefulSets | 1 StatefulSet: `opensearch`, ready 1/1 | Medium/High | `kubectl -n techx-tf4 get deploy,sts` |
| Kubernetes Services | ClusterIP services only in namespace output | Medium | `kubectl -n techx-tf4 get svc` |
| PVC Count | 0 PVC resources found in `techx-tf4` | Medium/High | `kubectl -n techx-tf4 get pvc` |
| Cluster-scope Namespace List | Forbidden | Low | `kubectl get ns` requires cluster-scope permission |

---

## 7. CloudWatch Log Groups Inventory

| Log Group | Stored Bytes | Retention |
|---|---:|---|
| /aws/ecs/containerinsights/tf4-cdo04-sandbox-cluster/performance | 0 | 1 day |
| /aws/eks/techx-tf4-cluster/cluster | 0 | 90 days |
| /ec2/cloudwatch-agent/case1/nginx/access | 333 | Not set |
| /ec2/cloudwatch-agent/case1/nginx/error | 893 | Not set |
| /ec2/cloudwatch-agent/case2/nginx/access | 335 | Not set |
| /ec2/cloudwatch-agent/case2/nginx/error | 629 | Not set |
| /ec2/cloudwatch-agent/case2/system/cloud-init | 45299 | Not set |
| /ec2/cloudwatch-agent/case2/system/dnf | 9291 | Not set |

### CloudWatch Logs note

Có 8 log groups được phát hiện. Một số log groups chưa có retention rõ ràng (`Not set`). Đây là cost risk mức Medium vì log storage có thể tăng theo thời gian nếu workload ghi log nhiều.

---

## 8. Kubernetes Runtime Inventory

### 8.1. Pod runtime summary

Namespace `techx-tf4` đã có nhiều workload đang chạy, bao gồm application services, data/messaging services và observability stack.

Workloads tiêu biểu được validate:

- `accounting`
- `ad`
- `cart`
- `checkout`
- `currency`
- `email`
- `flagd`
- `fraud-detection`
- `frontend`
- `frontend-proxy`
- `grafana`
- `image-provider`
- `jaeger`
- `kafka`
- `llm`
- `load-generator`
- `opensearch-0`
- `otel-collector-agent`
- `payment`
- `postgresql`
- `product-catalog`
- `product-reviews`
- `prometheus`
- `quote`
- `recommendation`
- `shipping`
- `valkey-cart`

### 8.2. Deployment / StatefulSet summary

| Resource Type | Finding | Cost Impact | Notes |
|---|---|---|---|
| Deployments | 25 deployments visible, all showing available replicas | High | Many services increase aggregate CPU/memory demand on worker nodes |
| StatefulSets | `opensearch` StatefulSet ready 1/1 | Medium/High | Stateful observability component may need persistence review |
| Services | ClusterIP services visible, no External IP in namespace output | Low/Medium | External entry is handled by AWS ALB, not service type LoadBalancer in namespace output |
| PVC | No PVC resources found in `techx-tf4` | Medium/High | Lower immediate EBS/PVC cost, but creates data persistence risk for stateful components |

### 8.3. Kubernetes access note

`kubectl get ns` returned `Forbidden` because the current role cannot list namespaces at cluster scope. However, namespace-scoped commands such as `kubectl -n techx-tf4 get pods -o wide`, `kubectl -n techx-tf4 get deploy,sts`, `kubectl -n techx-tf4 get svc`, and `kubectl -n techx-tf4 get pvc` were able to return runtime evidence.

This means CDO04 has enough namespace-level access for current COST-01 inventory, but still does not have full cluster-scope read access.

---

## 9. Estimated Cost Table

> Lưu ý: Đây là **baseline estimate ban đầu**, chưa phải actual bill từ Cost Explorer. Estimate dùng 730 giờ/tháng và quy đổi tuần theo 4.345 tuần/tháng. Các phần usage-based như NAT data processing, ALB LCU thực tế, CloudWatch log ingestion, ECR image size và data transfer sẽ cần Cost Explorer để xác nhận.

### 9.1. Giả định đơn giá

| Hạng mục giá | Đơn giá sử dụng | Nguồn / Ghi chú |
|---|---:|---|
| EC2 `t3.large` Linux On-Demand, us-east-1 | `$0.0832/giờ` | Tham chiếu giá On-Demand công khai |
| NAT Gateway theo giờ | `$0.045/giờ` | Chưa bao gồm phí xử lý dữ liệu |
| NAT Gateway xử lý dữ liệu | `$0.045/GB` | Phụ thuộc traffic thực tế |
| Application Load Balancer theo giờ | `$0.0225/giờ` | Chưa bao gồm LCU usage |
| ALB LCU | `$0.008/LCU-giờ` | Phụ thuộc request, bandwidth, connection và rule evaluation |
| EBS gp3 storage | `$0.08/GB-tháng` | Chỉ tính storage gp3 baseline |
| ECR private storage | `$0.10/GB-tháng` | Chưa đo image size thực tế |

---

### 9.2. Ước tính baseline theo từng thành phần

| Thành phần | Số lượng / Giả định | Công thức | Ước tính theo tháng | Ước tính theo tuần | Ghi chú |
|---|---:|---|---:|---:|---|
| EC2 Worker Nodes | 2 x `t3.large` | `2 x $0.0832 x 730h` | `$121.47` | `$27.96` | Chi phí compute cố định chính |
| Kịch bản EC2 scale tối đa | 4 x `t3.large` | `4 x $0.0832 x 730h` | `$242.94` | `$55.91` | Không phải cost hiện tại; là risk nếu node group scale lên maxSize=4 |
| EBS Root Volumes | 40 GiB gp3 | `40 x $0.08` | `$3.20` | `$0.74` | 2 volumes x 20 GiB |
| NAT Gateway | 1 NAT Gateway | `1 x $0.045 x 730h` | `$32.85` | `$7.56` | Chưa bao gồm phí xử lý dữ liệu `$0.045/GB` |
| ALB base hourly | 1 ALB | `1 x $0.0225 x 730h` | `$16.43` | `$3.78` | Chưa bao gồm LCU usage |
| Ví dụ ALB LCU | Trung bình 1 LCU | `1 x $0.008 x 730h` | `$5.84` | `$1.34` | Chỉ là ví dụ; actual phụ thuộc traffic |
| ECR Storage | 1 repo `techx-corp` | `$0.10/GB-tháng x image size` | `Pending` | `Pending` | Cần kiểm tra image size/count |
| CloudWatch Logs | 8 log groups | ingest + storage | `Pending / hiện tại thấp` | `Pending / hiện tại thấp` | Stored bytes hiện thấp, nhưng chưa rõ log ingestion trend |
| CloudWatch Metrics/Alarms | Chưa validate đầy đủ | metric/alarm pricing | `Pending` | `Pending` | Cần kiểm tra dashboard/alarm inventory |
| PVC Storage | Không tìm thấy PVC | `0 GiB` | `$0.00` | `$0.00` | Không thấy PVC cost, nhưng vẫn có persistence risk |
| Observability Stack | Workloads chạy trong cluster | sử dụng EC2 gián tiếp | Đã bao gồm trong EC2 nodes | Đã bao gồm trong EC2 nodes | Cần `kubectl top` để right-size |
| Data Transfer | Có thể phát sinh qua NAT/ALB/cross-AZ | usage-based | `Pending` | `Pending` | Cần Cost Explorer / traffic data |

---

### 9.3. Tổng chi phí baseline

| Loại tổng | Bao gồm | Ước tính theo tháng | Ước tính theo tuần | Ghi chú |
|---|---|---:|---:|---|
| **Tổng baseline cố định hiện tại** | EC2 worker nodes + EBS gp3 + NAT Gateway hourly + ALB hourly | **`$173.95/tháng`** | **`$40.03/tuần`** | Chưa bao gồm NAT data processing, ALB LCU, ECR storage, CloudWatch ingest, data transfer |
| **Tổng baseline cố định + trung bình 1 ALB LCU** | Tổng baseline cố định hiện tại + trung bình 1 LCU | **`$179.79/tháng`** | **`$41.38/tuần`** | Thực tế hơn nếu ALB có traffic đều |
| **Kịch bản node scale tối đa** | 4 x `t3.large` EC2 + EBS + NAT hourly + ALB hourly | **`$295.42/tháng`** | **`$68.00/tuần`** | Chỉ là scenario nếu node group scale từ desired=2 lên max=4; chưa bao gồm usage-based charges |

---

### 9.4. Kiểm tra so với budget

Target budget:

$300/tuần

Kết quả estimate ban đầu:
- Tổng baseline cố định hiện tại: ~$40.03/tuần
- Tổng baseline cố định + trung bình 1 ALB LCU: ~$41.38/tuần
- Kịch bản node scale tối đa: ~$68.00/tuần

Đánh giá:
- Estimate baseline hiện tại đang thấp hơn budget $300/tuần.
- Cost driver cố định chính là EC2 worker nodes.
- NAT Gateway và ALB là các fixed cost driver quan trọng, kể cả khi traffic thấp.
- Nếu node group scale từ 2 nodes lên 4 nodes, chi phí EC2 compute có thể tăng gần gấp đôi.
- Actual cost vẫn cần được xác nhận bằng Cost Explorer vì estimate này chưa bao gồm NAT data processing, ALB LCU usage thực tế, - - CloudWatch ingestion, ECR image storage và data transfer.


---

## 10. Initial Cost Driver Assessment

| Cost Driver | Current Finding | Cost Risk | Notes |
|---|---|---|---|
| EKS Worker Nodes / EC2 | 2 running `t3.large` nodes | High | Đây là fixed compute cost chính của baseline |
| Node Group Scaling | min=2, desired=2, max=4 | High | Nếu scale lên max=4, compute cost có thể tăng khoảng 2x so với desired hiện tại |
| Multi-AZ Compute | Nodes chạy ở `us-east-1a` và `us-east-1b` | Medium | Tốt cho compute resilience, nhưng không đồng nghĩa full HA cho stateful workloads |
| Instance Type | `t3.large` | Medium/High | Cần so sánh CPU/memory usage sau khi có `kubectl top` để right-size |
| NAT Gateway | 1 NAT Gateway, state `available` | High | Fixed cost đáng chú ý; đã validate Single NAT Gateway |
| Application Load Balancer | 1 internet-facing ALB, active | Medium | Có hourly cost và LCU cost |
| EBS Volumes | 2 gp3 volumes, tổng 40 GiB | Medium | Storage cost cơ bản của worker nodes |
| ECR | 1 repository `techx-corp` | Low/Medium | Cần kiểm tra image count/size nếu muốn estimate sâu |
| CloudWatch Logs | 8 log groups, một số không set retention | Medium | Có risk tăng cost nếu log volume tăng và retention không giới hạn |
| Kubernetes Workloads | Around 25 deployments plus observability/data components | High | Nhiều workload cùng chạy trên 2 nodes nên node cost/pressure cần theo dõi |
| Observability Stack | Grafana, Jaeger, Prometheus, OpenSearch, OTel Collector visible | High | Có thể là workload tiêu thụ tài nguyên đáng kể trên node |
| PVC / Stateful Storage | No PVC found | Medium/High | Ít storage cost hơn, nhưng persistence risk cao cho stateful workloads |

---

## 11. Cost Risk Analysis

| Risk ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| COST-RISK-01 | Worker nodes `t3.large` có thể quá lớn hoặc quá nhỏ so với tải thực tế | Tăng fixed cost hoặc thiếu performance | Medium | Right-size sau khi có CPU/memory từ `kubectl top` |
| COST-RISK-02 | Node group có maxSize = 4 | Compute cost có thể tăng nếu autoscale/manual scale lên max | Medium | Theo dõi scale event và Cost Explorer |
| COST-RISK-03 | NAT Gateway tạo fixed cost cao | Tăng baseline cost ngay cả khi traffic thấp | Medium | Dùng Single NAT trong Week 1, monitor Cost Explorer |
| COST-RISK-04 | ALB là fixed entry cost | Tăng baseline cost | Low/Medium | Theo dõi ALB LCU và request volume |
| COST-RISK-05 | CloudWatch log groups chưa set retention | Log storage cost có thể tăng theo thời gian | Medium | Set retention phù hợp cho log groups non-critical |
| COST-RISK-06 | Observability stack có nhiều components | Có thể ép node phải lớn hơn | Medium/High | Dùng `kubectl top pods` để xem CPU/RAM và right-size |
| COST-RISK-07 | Không có PVC trong namespace | Có thể giảm storage cost hiện tại nhưng tăng data loss risk | High | Ghi nhận risk; cần ADR/follow-up cho stateful persistence |
| COST-RISK-08 | Cost Explorer chưa có đủ billing data | Actual cost chưa đối chiếu được ngay | Medium | Dùng estimate trước, cập nhật actual sau |
| COST-RISK-09 | `load-generator` đang chạy trong namespace | Có thể tạo traffic/cost/nhiễu metric nếu autostart | Medium | Kiểm tra cấu hình load-generator, chỉ bật khi test |

---

## 12. Baseline Findings

1. Hệ thống đang chạy trên EKS cluster `techx-tf4-cluster`, trạng thái `ACTIVE`, Kubernetes version `1.30`.
2. Node group hiện tại là `techx-general-ng-20260707091432750200000017`, trạng thái `ACTIVE`.
3. Cluster có 2 worker nodes `t3.large`, chạy ở 2 AZ khác nhau: `us-east-1a` và `us-east-1b`.
4. Node group có scaling config `min=2`, `desired=2`, `max=4`.
5. Có 1 NAT Gateway đang `available`, phù hợp với quyết định Single NAT Gateway cho Week 1 baseline.
6. Có 1 internet-facing Application Load Balancer đang `active`.
7. Có 2 EBS gp3 volumes, tổng dung lượng 40 GiB, gắn với 2 worker nodes.
8. Có 1 ECR repository `techx-corp`.
9. Có 8 CloudWatch log groups, trong đó một số log groups chưa có retention rõ ràng.
10. Namespace `techx-tf4` có nhiều application workloads và observability workloads đang chạy.
11. Tất cả deployments visible đều có available replica, cho thấy baseline application đã deploy thành công ở mức runtime inventory.
12. `opensearch` chạy dưới dạng StatefulSet 1/1, nhưng `kubectl get pvc` trả về không có PVC trong namespace `techx-tf4`.
13. Không có PVC trong namespace `techx-tf4`, do đó storage cost từ PVC chưa xuất hiện trong inventory hiện tại, nhưng data persistence risk cần được ghi nhận riêng.
14. Cluster-scope command `kubectl get ns` bị `Forbidden`, nhưng namespace-scope commands cho `techx-tf4` đã chạy được.

---

## 13. Cost Estimate Method

Cách estimate:

1. Xác định tài nguyên đang chạy thực tế.
2. Xác định số lượng và cấu hình tài nguyên.
3. Map từng resource với pricing model tương ứng.
4. Tính estimated daily/weekly/monthly cost bằng AWS Pricing Calculator hoặc bảng giá AWS.
5. So sánh với budget mục tiêu.
6. Sau khi Cost Explorer có data, cập nhật actual cost và daily burn rate.

Công thức đơn giản:

```txt
Monthly EC2 cost = instance hourly price x number of nodes x 730 hours
```

```txt
Weekly EC2 cost = monthly EC2 cost / 4.345
```

```txt
Daily burn rate = monthly estimated cost / 30
```

---

## 14. Budget Reference

Target budget hiện tại:

```txt
$300/week
```

Cost estimate cần trả lời được:

1. Baseline hiện tại có khả năng vượt budget không?
2. Cost driver lớn nhất là gì?
3. Có tài nguyên nào tạo cost cố định cao không?
4. Có workload nào nên right-size sau khi có runtime metrics không?
5. Có cần cảnh báo 70%, 90%, 100% không?

Initial answer:

- Cost driver chính hiện tại là EC2 worker nodes `2 x t3.large`.
- NAT Gateway là fixed cost đáng chú ý.
- ALB là fixed entry cost.
- Observability stack có thể tạo indirect cost do tiêu thụ CPU/RAM trên node.
- Không có PVC hiện tại nên PVC storage cost chưa thấy, nhưng stateful persistence risk cao.
- Cần Cost Explorer để xác nhận actual daily/weekly burn rate.

---

## 15. Runtime Validation Commands

### 15.1. Kiểm tra EKS cluster

```bash
aws eks list-clusters --output table
```

```bash
aws eks describe-cluster \
  --name techx-tf4-cluster \
  --query "cluster.[name,status,version,endpoint]" \
  --output table
```
# Evidence: 
![Kiểm tra EKS cluster](./runtime/screenshots/Kiểm%20tra%20EKS%20cluster.jpg)
### 15.2. Kiểm tra node group

```bash
aws eks list-nodegroups \
  --cluster-name techx-tf4-cluster \
  --output table
```

```bash
aws eks describe-nodegroup \
  --cluster-name techx-tf4-cluster \
  --nodegroup-name techx-general-ng-20260707091432750200000017 \
  --query "nodegroup.[nodegroupName,status,instanceTypes[0]]" \
  --output table
```

```bash
aws eks describe-nodegroup \
  --cluster-name techx-tf4-cluster \
  --nodegroup-name techx-general-ng-20260707091432750200000017 \
  --query "nodegroup.scalingConfig" \
  --output table
```

```bash
aws eks describe-nodegroup \
  --cluster-name techx-tf4-cluster \
  --nodegroup-name techx-general-ng-20260707091432750200000017 \
  --query "nodegroup.subnets" \
  --output table
```
![Kiểm tra node group](./runtime/screenshots/Kiểm%20tra%20node%20group.jpg)
### 15.3. Kiểm tra EC2 instances

```bash
aws ec2 describe-instances \
  --filters "Name=tag:eks:cluster-name,Values=techx-tf4-cluster" "Name=instance-state-name,Values=running" \
  --query "Reservations[*].Instances[*].[InstanceId,InstanceType,Placement.AvailabilityZone,State.Name,PrivateIpAddress]" \
  --output table
```
![Kiểm tra EC2 instances](./runtime/screenshots/Kiểm%20tra%20EC2%20instances.jpg)
### 15.4. Kiểm tra EBS volumes

```bash
aws ec2 describe-volumes \
  --filters "Name=status,Values=in-use" \
  --query "Volumes[*].[VolumeId,Size,VolumeType,State,AvailabilityZone,Attachments[0].InstanceId]" \
  --output table
```
![Kiểm tra EBS volumes](./runtime/screenshots/Kiểm%20tra%20EBS%20volumes.jpg)
### 15.5. Kiểm tra NAT Gateway

```bash
aws ec2 describe-nat-gateways \
  --filter "Name=state,Values=available" \
  --query "NatGateways[*].[NatGatewayId,VpcId,SubnetId,State]" \
  --output table
```
![Kiểm tra NAT Gateway](./runtime/screenshots/Kiểm%20tra%20NAT%20Gateway.jpg)
### 15.6. Kiểm tra ALB

```bash
aws elbv2 describe-load-balancers \
  --query "LoadBalancers[*].[LoadBalancerName,Type,Scheme,State.Code,VpcId,DNSName]" \
  --output table
```
![Kiểm tra ALB](./runtime/screenshots/Kiểm%20tra%20ALB.jpg)
### 15.7. Kiểm tra ECR repositories

```bash
aws ecr describe-repositories \
  --query "repositories[*].[repositoryName,repositoryUri]" \
  --output table
```
![ECR repositories](./runtime/screenshots/ECR%20repositories.jpg)
### 15.8. Kiểm tra CloudWatch log groups

```bash
aws logs describe-log-groups \
  --query "logGroups[*].[logGroupName,storedBytes,retentionInDays]" \
  --output table
```
![Kiểm tra CloudWatch log groups](./runtime/screenshots/Kiểm%20tra%20CloudWatch%20log%20groups.jpg)
### 15.9. Kiểm tra Kubernetes workload

```bash
kubectl -n techx-tf4 get pods -o wide
```
![Kiểm tra Kubernetes workload-1](./runtime/screenshots/Kiểm%20tra%20Kubernetes%20workload-1.jpg)

```bash
kubectl -n techx-tf4 get deploy,sts
```
![Kiểm tra Kubernetes workload-2](./runtime/screenshots/Kiểm%20tra%20Kubernetes%20workload-2.jpg)
```bash
kubectl -n techx-tf4 get svc
```
![Kiểm tra Kubernetes workload-3](./runtime/screenshots/Kiểm%20tra%20Kubernetes%20workload-3.jpg)
```bash
kubectl -n techx-tf4 get pvc
```

Optional after metrics-server access is available:

```bash
kubectl -n techx-tf4 top pods
```

```bash
kubectl top nodes
```

---

## 16. Evidence Checklist

| Evidence | Status | Location |
|---|---|---|
| EKS cluster/nodegroup info | Done | screenshots / CLI output |
| EC2 instance type/node count | Done | screenshots / CLI output |
| NAT Gateway count | Done | screenshots / CLI output |
| ALB count | Done | screenshots / CLI output |
| EBS volume list | Done | screenshots / CLI output |
| ECR repo list | Done | screenshots / CLI output |
| CloudWatch log group size | Done | screenshots / CLI output |
| Kubernetes pods/deployments/services | Done | screenshots / CLI output |
| PVC count | Done - no resources found | screenshots / CLI output |
| Kubernetes CPU/memory usage | Pending | Requires `kubectl top pods` / metrics-server access |
| Cost Explorer screenshot | Pending | runtime/cost-explorer-baseline |
| Baseline cost estimate table | Done | this file |
| Cost risk analysis | Done | this file |

---

## 17. Expected Output

Sau khi hoàn thành task này, team đã có:

1. Danh sách cost driver chính.
2. Inventory tài nguyên baseline.
3. Bảng estimate cost ban đầu.
4. Danh sách risk về cost.
5. Evidence CLI/screenshot cho tài nguyên đang chạy.
6. Follow-up task để cập nhật actual cost từ Cost Explorer.
7. Recommendation ban đầu cho Cost Optimization.

---

## 19. Jira Evidence Comment

```txt
EVIDENCE UPDATE

1. Đã làm gì?

Đã hoàn thành baseline infrastructure cost estimate cho EPIC-04: Cost Optimization.

2. Kết quả hiện tại

Team đã validate các cost driver chính của baseline gồm EKS cluster, EKS managed node group, EC2 worker nodes, EBS volumes, NAT Gateway, ALB, ECR repository, CloudWatch log groups và Kubernetes workloads trong namespace techx-tf4.

Kết quả chính:
- EKS cluster: techx-tf4-cluster, ACTIVE, Kubernetes 1.30
- Node group: techx-general-ng-20260707091432750200000017
- Instance type: t3.large
- Scaling: min=2, desired=2, max=4
- Worker nodes: 2 nodes across us-east-1a and us-east-1b
- NAT Gateway: 1 available NAT Gateway
- ALB: 1 internet-facing Application Load Balancer, active
- EBS: 2 gp3 volumes, total 40 GiB
- ECR: 1 repository techx-corp
- CloudWatch Logs: 8 log groups found
- Kubernetes workloads: namespace techx-tf4 has application, data, and observability workloads running
- PVC: no PVC resources found in namespace techx-tf4

Initial assessment:
- Main cost driver is EC2 worker nodes.
- NAT Gateway and ALB are fixed baseline cost drivers.
- Observability stack may increase node resource pressure.
- No PVC cost is visible from namespace evidence, but this creates a stateful persistence risk.

3. Bằng chứng nằm ở đâu?

- Baseline cost estimate:
docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md

- Runtime screenshots:
docs/evidence/epic-04-cost-optimization/runtime/screenshots/

- Runtime evidence folder:
docs/evidence/epic-04-cost-optimization/runtime/

4. Ghi chú / Follow-up

Actual cost from Cost Explorer is still pending until billing data is available. Next steps are to capture Cost Explorer, compare estimate vs actual cost, run kubectl top for CPU/memory evidence, and prepare right-sizing/cost saving recommendations.
```
