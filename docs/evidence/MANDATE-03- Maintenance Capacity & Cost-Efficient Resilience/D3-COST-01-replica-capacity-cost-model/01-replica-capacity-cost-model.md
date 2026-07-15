# D3-COST-01 — Mô hình chi phí replica và năng lực cụm

**Owner:** CDO-04 — Performance & Cost  
**Cluster:** `techx-tf4-cluster`  
**Namespace:** `techx-tf4`  
**Region:** `us-east-1`  
**Ngày thu thập và xác minh:** 2026-07-15  
**Trạng thái:** READY FOR REVIEW — PENDING `quote` SCOPE DECISION AND CONTROLLED-DRAIN VALIDATION

---

## 1. Mục tiêu

Tài liệu này xây dựng và kiểm chứng mô hình chi phí cho:

- năng lực nền cố định của EKS managed node group;
- năng lực động do Karpenter tạo;
- mở rộng replica của revenue path;
- target capacity phục vụ bảo trì;
- các cửa sổ capacity tạm thời 4 giờ, 8 giờ và 24 giờ;
- chi phí tạm thời so với duy trì lâu dài;
- trần chi phí lý thuyết theo cấu hình autoscaling;
- phương pháp đối chiếu estimate với chi phí thực tế sau maintenance.

Phạm vi chi phí gồm worker compute và root EBS của worker. Tài liệu không quy các khoản PVC ứng dụng, EKS control plane, data transfer, load balancer, log ingestion hoặc dịch vụ dùng chung vào chi phí tăng worker.

---

## 2. Nguồn dữ liệu và phương pháp tính

### 2.1 Nguồn đơn giá đã sử dụng

Đơn giá được lấy trực tiếp từ **AWS Price List API** và lưu dưới dạng raw JSON trong evidence:

| Thành phần | Đơn giá |
|---|---:|
| `t3.large`, Linux, Shared, On-Demand, `us-east-1` | `$0.0832/giờ` |
| `t3a.large`, Linux, Shared, On-Demand, `us-east-1` | `$0.0752/giờ` |
| gp3 storage, `us-east-1` | `$0.08/GB-tháng` |

Root volume của managed node và Karpenter node:

```text
20 GiB gp3
3000 IOPS
125 MiB/s
```

Trong cấu hình hiện tại, `3000 IOPS` và `125 MiB/s` nằm trong baseline gp3, nên mô hình không cộng phụ phí IOPS hoặc throughput.

### 2.2 Công thức tính

```text
Root EBS cost/node/tháng
= 20 GiB × $0.08
= $1.60/tháng
```

```text
Root EBS cost/node/giờ
= $1.60 / 730
≈ $0.0021918/giờ
```

```text
Full t3.large worker cost/node/giờ
= $0.0832 + $0.0021918
≈ $0.0853918/giờ
```

```text
Full t3a.large worker cost/node/giờ
= $0.0752 + $0.0021918
≈ $0.0773918/giờ
```

```text
Chi phí scenario
= Σ(số node × thời gian tồn tại × full worker hourly rate)
```

Replica Kubernetes không có đơn giá riêng. Chi phí replica được quy đổi theo chuỗi:

```text
Replica tăng
→ CPU/memory requests tăng
→ scheduler thiếu chỗ
→ Karpenter provision thêm worker
→ phát sinh EC2 node-hours và root EBS-hours
```

---

## 3. Baseline hạ tầng

### 3.1 Managed node group

| Thuộc tính | Giá trị |
|---|---|
| Node group | `techx-general-ng-20260707091432750200000017` |
| Instance type | `t3.large` |
| Capacity type | `ON_DEMAND` |
| `minSize` | `2` |
| `desiredSize` | `2` |
| `maxSize` | `4` |
| Root disk | `20 GiB gp3/node` |

Fixed financial baseline:

```text
2 × t3.large On-Demand
```

### 3.2 Karpenter

Karpenter đang hoạt động và đã provision node thực tế.

NodePool hiện:

- chỉ cho phép `t3.large` và `t3a.large`;
- capacity type là `on-demand`;
- `limits.cpu=16`;
- consolidation policy là `WhenEmptyOrUnderutilized`;
- `consolidateAfter=5m`;
- `expireAfter=720h`.

Managed node group `maxSize=4` không giới hạn số node Karpenter vì hai cơ chế scale độc lập.

---

## 4. Runtime validation cuối

Validation được thực hiện sau khi CDO-08 cung cấp reliability inputs.

### 4.1 Worker capacity tại thời điểm validation

Cluster có bốn worker Ready:

```text
2 × managed t3.large
2 × Karpenter t3a.large
```

CPU requests:

| Node | Loại | CPU requests | Allocatable |
|---|---|---:|---:|
| `ip-10-0-10-17` | Karpenter `t3a.large` | `1925m` | `1930m` |
| `ip-10-0-10-231` | Managed `t3.large` | `880m` | `1930m` |
| `ip-10-0-11-40` | Managed `t3.large` | `1930m` | `1930m` |
| `ip-10-0-11-89` | Karpenter `t3a.large` | `980m` | `1930m` |
| **Tổng** |  | **`5715m`** | **`7720m`** |

Aggregate request headroom:

```text
7720m - 5715m = 2005m
```

Nếu một node unavailable, aggregate allocatable còn:

```text
3 × 1930m = 5790m
```

Chênh lệch lý thuyết so với current requests:

```text
5790m - 5715m = 75m
```

Phép tính này bảo thủ vì một phần DaemonSet request trên node bị drain không cần reschedule như workload thông thường. Tuy vậy, `75m` không phải surge buffer đủ rộng. Vì thế bốn node được xem là **minimum maintenance target**, không phải target dư dả.

Actual CPU usage tại thời điểm validation thấp hơn requests, nhưng quyết định scheduling và khả năng reschedule phải dựa trên requests.

### 4.2 Replica và readiness

Các revenue-path service tại thời điểm validation:

| Service | Desired/Ready | Ghi chú |
|---|---:|---|
| `frontend-proxy` | `2/2` | critical stateless |
| `frontend` | `2/2` tại lần xác minh cuối | HPA min 2, max 3 |
| `product-catalog` | `2/2` | critical stateless |
| `cart` | `2/2` | critical stateless |
| `checkout` | `2/2` | HPA min 2, max 3 |
| `payment` | `2/2` | critical stateless |
| `currency` | `2/2` | có PDB |
| `shipping` | `2/2` | critical stateless |
| `quote` | `1/1` | singleton; scope đang chờ xác nhận |

Tất cả Deployment được quan sát đều đạt `READY = DESIRED` tại thời điểm final validation.

### 4.3 HPA

| Workload | Min | Max | Current tại lần xác minh cuối |
|---|---:|---:|---:|
| `frontend` | 2 | 3 | 2 |
| `checkout` | 2 | 3 | 2 |

Trong một lần thu thập trước đó, `frontend` đã scale lên 3; HPA sau đó scale xuống 2. Hai pod còn lại đều Ready và được spread trên hai node/AZ khác nhau. Chênh lệch giữa ba Deployment replicas và hai serving endpoints trước đó đã được giải thích và đóng.

### 4.4 PDB

PDB `minAvailable=1` đã được xác nhận cho:

- `cart`;
- `checkout`;
- `currency`;
- `frontend`;
- `frontend-proxy`;
- `payment`;
- `product-catalog`;
- `shipping`.

Runtime ghi nhận `allowedDisruptions` từ 1 đến 2 tùy số replica hiện tại.

`quote` chưa có PDB.

### 4.5 Pod placement và endpoints

Critical replicas đã được quan sát trên nhiều node. Các Service critical có serving endpoints tương ứng với số replica Ready.

Frontend final state:

```text
2 Ready pods
2 serving endpoints
2 nodes khác nhau
2 Availability Zones khác nhau
```

`quote` chỉ có một endpoint, phù hợp với trạng thái singleton.

---

## 5. Reliability input từ CDO-08

CDO-08 đã xác nhận:

- `cart`, `checkout`, `frontend`, `frontend-proxy`, `payment`, `product-catalog`, `shipping` được tăng lên tối thiểu 2 replica;
- `frontend` và `checkout` dùng HPA `minReplicas=2`, `maxReplicas=3`;
- critical stateless services có PDB `minAvailable=1`;
- critical services có readiness và liveness probes;
- chưa dùng startup probe;
- Deployment dùng RollingUpdate mặc định `maxSurge=25%`, `maxUnavailable=25%`;
- `terminationGracePeriodSeconds=30`;
- chart đã có topology spread cho critical services;
- critical services có resource requests/limits;
- pre-flight phải kiểm tra replica, HPA, PDB, pod Ready, endpoints và observability;
- không drain node chứa stateful singleton khi chưa có kế hoạch di chuyển phù hợp.

Dependency tổng thể từ CDO-08 được xem là **RESOLVED**.

Quyết định còn lại chỉ là scope của `quote`.

---

## 6. Mô hình chi phí

### 6.1 Fixed baseline — 2 managed nodes

```text
Hourly
= 2 × $0.0853918
≈ $0.1707836/giờ
```

```text
Monthly equivalent
= $0.1707836 × 730
≈ $124.67/tháng
```

### 6.2 Runtime validation — 4 nodes

Runtime validation có:

```text
2 × managed t3.large
2 × Karpenter t3a.large
```

```text
Hourly
= 2 × $0.0853918 + 2 × $0.0773918
≈ $0.3255672/giờ
```

```text
Monthly equivalent nếu duy trì liên tục
= $0.3255672 × 730
≈ $237.66/tháng
```

Increment so với fixed baseline:

```text
$237.66 - $124.67
≈ $112.99/tháng
```

Đây là monthly equivalent, không phải forecast rằng hai Karpenter nodes sẽ tồn tại cả tháng.

### 6.3 Incremental dynamic capacity

| Dynamic capacity | 1 giờ | 4 giờ | 8 giờ | 24 giờ | 730 giờ |
|---|---:|---:|---:|---:|---:|
| 1 × `t3a.large` | `$0.0774` | `$0.3096` | `$0.6191` | `$1.8574` | `$56.50` |
| 2 × `t3a.large` | `$0.1548` | `$0.6191` | `$1.2383` | `$3.7148` | `$112.99` |
| 1 × `t3.large` | `$0.0854` | `$0.3416` | `$0.6831` | `$2.0494` | `$62.34` |
| 2 × `t3.large` | `$0.1708` | `$0.6831` | `$1.3663` | `$4.0988` | `$124.67` |

Karpenter có thể chọn `t3.large` hoặc `t3a.large`. Vì vậy:

- dùng `t3a.large` làm observed/expected case;
- dùng `t3.large` làm conservative case.

---

## 7. Capacity scenarios

### Scenario A — 3 total workers

```text
2 managed nodes + 1 dynamic node
```

Evidence trước đó cho thấy ba node đạt khoảng `96.8%` aggregate CPU requests.

**Đánh giá:** không maintenance-safe. Drain một node sẽ để lại hai node không đủ aggregate request capacity cho workload hiện tại.

### Scenario B — 4 total workers

```text
2 managed nodes + 2 dynamic nodes
```

Current validation chứng minh:

- bốn node Ready;
- critical Deployments Ready;
- PDB tồn tại;
- critical replicas được spread;
- serving endpoints tồn tại;
- aggregate CPU requests vừa đủ cho giả định một node unavailable.

**Đánh giá:** chọn làm **minimum maintenance target** cho controlled-drain rehearsal.

Biên capacity nhỏ, vì sau khi loại một node chỉ còn khoảng `75m` aggregate request margin trước khi điều chỉnh DaemonSet overhead và pod placement. Vì thế không được kết luận bốn node luôn đủ cho mọi surge hoặc mọi node drain.

### Scenario C — 5 total workers

```text
2 managed nodes + 3 dynamic nodes
```

Một dynamic `t3a.large` bổ sung so với four-node target có chi phí:

| Cửa sổ | Increment |
|---:|---:|
| 4 giờ | `$0.3096` |
| 8 giờ | `$0.6191` |
| 24 giờ | `$1.8574` |

**Đánh giá:** là phương án dự phòng khi controlled-drain pre-flight phát hiện không đủ pod placement, rollout surge hoặc stateful constraints. Không chọn làm mặc định nếu four-node rehearsal PASS.

---

## 8. Trần chi phí autoscaling

NodePool có `limits.cpu=16`. Với instance được phép đều có 2 vCPU:

```text
16 vCPU / 2 vCPU mỗi node ≈ 8 Karpenter nodes
```

Conservative Karpenter-only ceiling, giả sử tám node là `t3.large`:

```text
8 × $0.0853918
≈ $0.6831/giờ
≈ $498.69/tháng
```

Managed node group có `maxSize=4`, độc lập với Karpenter. Trần lý thuyết toàn cluster:

```text
4 managed + khoảng 8 Karpenter
≈ 12 workers
```

Conservative full-worker ceiling:

```text
12 × $0.0853918
≈ $1.0247/giờ
≈ $748.03/tháng
```

Đây là configuration ceiling, không phải forecast.

---

## 9. Temporary capacity, scale-down và actual cost

Capacity tạm thời phải có:

- start timestamp;
- end timestamp;
- instance type;
- NodeClaim lifecycle;
- số node-hours;
- xác nhận scale-down sau maintenance.

Estimated incremental cost:

```text
Σ(actual dynamic node duration × full worker hourly rate)
```

Scale-down PASS khi:

- worker count trở về baseline vận hành đã phê duyệt;
- không còn NodeClaim không cần thiết;
- không có critical pod Pending;
- revenue path vẫn giữ target replica và endpoints;
- timestamp kết thúc node-hour được lưu.

Actual billing reconciliation dùng Cost Explorer hoặc CUR sau maintenance. Phần này là post-run verification, không thay đổi công thức estimate trong tài liệu.

---

## 10. Quyết định còn chờ: `quote`

CDO-04 xác nhận `quote` đang được liệt kê trong revenue-path inventory.

Runtime hiện tại của `quote`:

```text
replicas: 1
serving endpoints: 1
CPU request/limit: 10m/50m
memory request/limit: 20Mi/40Mi
PDB: không có
readinessProbe: không có
livenessProbe: không có
startupProbe: không có
topology spread: không có
```

CDO-04 đề nghị CDO-08 xác nhận một trong hai phương án:

1. **`quote` thuộc mandatory drain/SLO scope**  
   Cần remediation trước controlled-drain rehearsal: tối thiểu hai replica, health probes, PDB và placement/topology policy.

2. **`quote` không thuộc mandatory drain/SLO scope**  
   Ghi rõ exclusion trong phạm vi demo và acceptance criteria trước khi rehearsal.

Controlled drain chưa được thực hiện cho đến khi quyết định này được chốt.

---

## 11. Trạng thái task

### Hoàn thành

- managed baseline và Karpenter discovery;
- EC2/EBS runtime evidence;
- official AWS Price List API evidence;
- công thức full worker node-hour;
- replica/HPA/PDB inventory;
- pod placement validation;
- endpoint validation;
- frontend discrepancy investigation và resolution;
- three-node và four-node capacity analysis;
- recommendation bốn node làm minimum maintenance target;
- temporary/permanent capacity scenarios;
- autoscaling cost ceiling.

### Chờ review hoặc validation

- CDO-08 xác nhận mandatory scope của `quote`;
- controlled-drain rehearsal;
- post-drain pod/PDB/endpoint/SLO evidence;
- scale-down timestamps;
- actual billing reconciliation sau maintenance.

### Trạng thái cuối

```text
CDO-08 general dependency: RESOLVED
Cost model: COMPLETE
Pricing evidence: COMPLETE
Runtime pre-flight evidence: COMPLETE
Frontend validation: PASS
Capacity recommendation: COMPLETE — 4 WORKERS MINIMUM FOR REHEARSAL
Quote scope decision: PENDING CDO-08 REVIEW
Controlled drain rehearsal: PENDING QUOTE DECISION
Actual-cost reconciliation: POST-RUN FOLLOW-UP
Overall D3-COST-01: READY FOR REVIEW — NOT YET CLOSED
```

---
## Evidence index

| Evidence | Mô tả | Kết luận được hỗ trợ |
|---|---|---|
| [`raw/01-nodegroups.json`](raw/01-nodegroups.json) | Danh sách EKS managed node groups của cluster | Cluster có một managed node group chính |
| [`raw/02-nodegroup-description.json`](raw/02-nodegroup-description.json) | Cấu hình node group: instance type, capacity type, min/desired/max | Baseline `2 × t3.large`, On-Demand, `maxSize=4` |
| [`raw/03-nodes-wide.txt`](raw/03-nodes-wide.txt) | Danh sách worker nodes tại lần thu thập ban đầu | Xác nhận managed nodes và Karpenter node |
| [`raw/04-node-capacity-allocated.txt`](raw/04-node-capacity-allocated.txt) | Capacity, allocatable và resource requests theo node | Đánh giá CPU headroom và maintenance capacity |
| [`raw/05-karpenter-nodepools.yaml`](raw/05-karpenter-nodepools.yaml) | NodePool limits, instance allowlist, consolidation và expiration | Karpenter active, `limits.cpu=16`, chỉ dùng `t3.large/t3a.large` |
| [`raw/06-karpenter-ec2nodeclasses.yaml`](raw/06-karpenter-ec2nodeclasses.yaml) | EC2NodeClass và cấu hình provision worker | Xác nhận cấu hình node do Karpenter quản lý |
| [`raw/08-karpenter-nodeclaims.yaml`](raw/08-karpenter-nodeclaims.yaml) | NodeClaim runtime đầy đủ | Xác nhận node động được Karpenter provision |
| [`raw/09-karpenter-nodeclaim-cost-baseline.txt`](raw/09-karpenter-nodeclaim-cost-baseline.txt) | Instance type, capacity type, creation timestamp và node name | Baseline dynamic capacity `t3a.large` On-Demand |
| [`raw/10-karpenter-controller-rendered.yaml`](raw/10-karpenter-controller-rendered.yaml) | Deployment runtime của Karpenter controller | Karpenter controller healthy và đang hoạt động |
| [`raw/11-worker-instances.json`](raw/11-worker-instances.json) | EC2 instance metadata của managed và Karpenter workers | Xác nhận instance type, launch time và mapping instance/node |
| [`raw/12-worker-volumes.json`](raw/12-worker-volumes.json) | EBS volumes gắn với workers | Root disk `20 GiB gp3`, `3000 IOPS`, `125 MiB/s` |
| [`raw/13-replica-resource-baseline.txt`](raw/13-replica-resource-baseline.txt) | Replica và requests theo Deployment | Cơ sở tính replica expansion và capacity demand |
| [`raw/14-hpa-baseline.txt`](raw/14-hpa-baseline.txt) | HPA runtime của frontend và checkout | Xác nhận `min=2`, `max=3` |
| [`raw/15-t3-large-price-list.json`](raw/15-t3-large-price-list.json) | AWS Price List API cho `t3.large` | Đơn giá chính thức `$0.0832/giờ` |
| [`raw/16-t3a-large-price-list.json`](raw/16-t3a-large-price-list.json) | AWS Price List API cho `t3a.large` | Đơn giá chính thức `$0.0752/giờ` |
| [`raw/17-gp3-price-list.json`](raw/17-gp3-price-list.json) | AWS Price List API cho gp3 | Đơn giá storage `$0.08/GB-tháng` |
| [`raw/17-final-validation-metadata.txt`](raw/17-final-validation-metadata.txt) | Timestamp và context của final validation | Xác nhận thời điểm validation và CDO-08 dependency resolved |
| [`raw/18-final-replica-readiness.txt`](raw/18-final-replica-readiness.txt) | Desired, Ready và Available replicas | Xác nhận workload readiness tại pre-flight |
| [`raw/19-final-pdb-status.txt`](raw/19-final-pdb-status.txt) | PDB runtime và allowed disruptions | Xác nhận critical services có `minAvailable=1` |
| [`raw/20-final-pod-placement.txt`](raw/20-final-pod-placement.txt) | Pod-to-node placement | Xác nhận critical replicas được spread qua nhiều node |
| [`raw/21-final-endpoints.txt`](raw/21-final-endpoints.txt) | Service endpoints tại final validation | Xác nhận serving endpoints của revenue-path services |
| [`raw/22-quote-runtime.yaml`](raw/22-quote-runtime.yaml) | Runtime Deployment của `quote` | Xác nhận singleton, chưa có probes/PDB/topology spread |
| [`raw/23-final-node-capacity.txt`](raw/23-final-node-capacity.txt) | Capacity và allocated resources của 4-node runtime | Cơ sở chốt 4 workers là minimum maintenance target |
| [`raw/24-final-node-usage.txt`](raw/24-final-node-usage.txt) | Actual CPU/memory usage theo node | Phân biệt usage thực tế với scheduler requests |
| [`raw/25-frontend-endpointslice.yaml`](raw/25-frontend-endpointslice.yaml) | EndpointSlice của frontend tại lần kiểm tra đầu | Phát hiện chênh lệch 3 replicas và 2 endpoints |
| [`raw/26-frontend-current-pods.txt`](raw/26-frontend-current-pods.txt) | Final frontend pods và node placement | Xác nhận 2 pod Ready trên hai node |
| [`raw/27-frontend-current-hpa.txt`](raw/27-frontend-current-hpa.txt) | Final HPA state của frontend | Xác nhận HPA đã scale xuống 2 |
| [`raw/28-frontend-service.yaml`](raw/28-frontend-service.yaml) | Selector của Service frontend | Loại trừ lỗi selector |
| [`raw/29-frontend-endpointslice-recheck.yaml`](raw/29-frontend-endpointslice-recheck.yaml) | EndpointSlice frontend sau recheck | Xác nhận 2 endpoints Ready và discrepancy đã resolved |
## 12. Review request

CDO-04 yêu cầu CDO-08 xác nhận:

> `quote` hiện được liệt kê trong revenue-path inventory nhưng vẫn là singleton, chưa có health probes, PDB hoặc topology spread. Vui lòng xác nhận `quote` thuộc mandatory drain/SLO scope và cần remediation trước rehearsal, hoặc được loại khỏi demo scope và ghi nhận exclusion chính thức.

Sau khi quyết định được ghi nhận, CDO-04 sẽ thực hiện controlled-drain rehearsal theo four-node target và cập nhật kết luận cuối.