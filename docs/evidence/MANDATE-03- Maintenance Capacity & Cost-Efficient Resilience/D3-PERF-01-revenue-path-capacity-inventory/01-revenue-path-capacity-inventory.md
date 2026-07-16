# D3-PERF-01 — Kiểm kê năng lực Revenue Path

**Directive:** MANDATE-03 — Maintenance Capacity & Cost-Efficient Resilience  
**Owner:** An — CDO-04 Performance Efficiency & Cost Optimization  
**Cluster:** `techx-tf4-cluster`  
**Cluster ARN:** `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`  
**Namespace:** `techx-tf4`  
**Region:** `us-east-1`  
**Thư mục evidence:** `./raw/`  
**Trạng thái:** Hoàn tất kiểm kê runtime và revalidation sau remediation; sẵn sàng cho controlled-drain rehearsal  

---

## 1. Mục tiêu

Task này kiểm kê trạng thái runtime của các service ảnh hưởng trực tiếp đến luồng doanh thu:

```text
frontend-proxy
→ frontend
→ product-catalog / cart
→ checkout
→ payment / shipping / currency / quote
```

Mục tiêu:

- Xác định replica desired, ready và available.
- Xác định CPU/memory requests và limits.
- Xác định HPA và PodDisruptionBudget.
- Xác định pod-to-node placement và serving endpoints.
- Kiểm tra redundancy của revenue path.
- Xác nhận remediation của `quote`.
- Đánh giá trạng thái pre-check trước controlled node drain.
- Phân loại synchronous/asynchronous.
- Ghi nhận node/pod utilization sau remediation.

Kết luận trong tài liệu dựa trên trạng thái Kubernetes live sau khi CDO-08 merge và apply remediation.

---

## 2. Bối cảnh và hai mốc evidence

Tài liệu giữ lại hai mốc:

1. **Initial inventory:** trạng thái cũ với hai worker nodes, nhiều service một replica, chưa có PDB cho `quote`.
2. **Post-remediation revalidation:** trạng thái mới với bốn worker nodes, các service revenue path đạt hai replicas, có PDB và placement phân tán.

```text
Cluster: techx-tf4-cluster
Namespace: techx-tf4
Region: us-east-1
Kube context: arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Initial collection metadata:

[raw/00-collection-metadata.txt](raw/00-collection-metadata.txt)

---

## 3. Danh sách evidence

### Initial inventory

| Nội dung | File |
|---|---|
| Timestamp và collection context | [raw/00-collection-metadata.txt](raw/00-collection-metadata.txt) |
| Replica state ban đầu | [raw/02-replica-summary.txt](raw/02-replica-summary.txt) |
| Pod placement ban đầu | [raw/03-pod-placement-summary.txt](raw/03-pod-placement-summary.txt) |
| HPA runtime state | [raw/04-hpa-wide.txt](raw/04-hpa-wide.txt) |
| Node allocated resources | [raw/06-node-10-0-10-231-allocated.txt](raw/06-node-10-0-10-231-allocated.txt) |
| Node allocated resources | [raw/06-node-10-0-11-40-allocated.txt](raw/06-node-10-0-11-40-allocated.txt) |
| Worker node inventory ban đầu | [raw/06-nodes-wide.txt](raw/06-nodes-wide.txt) |
| Requests và limits ban đầu | [raw/10-resource-requests-limits.txt](raw/10-resource-requests-limits.txt) |
| Node-group scaling configuration | [raw/12-nodegroup-scaling-config.json](raw/12-nodegroup-scaling-config.json) |
| Autoscaler/scale-out assessment | [raw/13-cluster-autoscaler-and-scaleout-status.txt](raw/13-cluster-autoscaler-and-scaleout-status.txt) |
| Cluster Autoscaler lookup | [raw/13-cluster-autoscaler-status.txt](raw/13-cluster-autoscaler-status.txt) |

### Post-remediation

| Nội dung | File |
|---|---|
| Deployment replica/readiness state | [raw/14-post-remediation-deployments.txt](raw/14-post-remediation-deployments.txt) |
| Pod readiness và placement | [raw/15-post-remediation-pods-wide.txt](raw/15-post-remediation-pods-wide.txt) |
| PDB runtime state | [raw/16-post-remediation-pdb-wide.txt](raw/16-post-remediation-pdb-wide.txt) |
| `quote` EndpointSlice | [raw/17-quote-endpointslice.txt](raw/17-quote-endpointslice.txt) |
| `quote` live Deployment | [raw/18-quote-live-deployment.yaml](raw/18-quote-live-deployment.yaml) |
| Worker node utilization | [raw/19-post-remediation-node-top.txt](raw/19-post-remediation-node-top.txt) |
| Pod utilization | [raw/20-post-remediation-pod-top.txt](raw/20-post-remediation-pod-top.txt) |

---

## 4. Revenue-path runtime inventory sau remediation

| Service | Desired / Ready | HPA | PDB | Placement | Loại luồng | Verdict |
|---|---:|---|---|---|---|---|
| `frontend-proxy` | `2 / 2` | Không thấy | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `frontend` | `2 / 2` | Min `2`, max `3` | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `product-catalog` | `2 / 2` | Không thấy | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `cart` | `2 / 2` | Không thấy | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `checkout` | `2 / 2` | Min `2`, max `3` | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `payment` | `2 / 2` | Không thấy | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `currency` | `2 / 2` | Min `2`, max `3` | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `shipping` | `2 / 2` | Không thấy | `minAvailable=1` | Nhiều node | Synchronous | PASS |
| `quote` | `2 / 2` | Không | `minAvailable=1` | 2 node, 2 AZ | Synchronous | PASS |

> Replica/readiness state phải được thu lại nếu runtime thay đổi trước mentor witness.

---

## 5. Xác nhận remediation của `quote`

CDO-08 xác nhận `quote` thuộc mandatory drain/SLO scope vì nằm trên critical synchronous path:

```text
checkout → shipping GetQuote → quote /getquote
```

Trước remediation, `quote` là singleton và chưa có đầy đủ PDB, topology spread, probes và requests.

### Cấu hình live đã xác minh

```text
replicas: 2
PDB minAvailable: 1
PDB allowedDisruptions: 1
topologyKey: kubernetes.io/hostname
maxSkew: 1
livenessProbe: tcpSocket:8080
readinessProbe: tcpSocket:8080
CPU request/limit: 10m / 50m
Memory request/limit: 20Mi / 40Mi
```

TCP probe được sử dụng thay vì `/getquote` vì `/getquote` là POST nghiệp vụ có side effect và không phù hợp làm health check.

### Endpoint và placement

| Pod | IP | Node | Zone | Ready |
|---|---|---|---|---|
| `quote-dfd7f7bb7-fbq6z` | `10.0.10.23` | `ip-10-0-10-231.ec2.internal` | `us-east-1a` | `true` |
| `quote-dfd7f7bb7-26jkn` | `10.0.11.53` | `ip-10-0-11-207.ec2.internal` | `us-east-1b` | `true` |

### Verdict

```text
Quote singleton risk: RESOLVED
Quote resource-request gap: RESOLVED
Quote PDB gap: RESOLVED
Quote topology-spread gap: RESOLVED
Quote health-probe gap: RESOLVED
Quote runtime remediation: PASS
```

---

## 6. Pod-to-node placement sau remediation

Revenue-path replicas được phân bố trên bốn worker nodes:

```text
ip-10-0-10-17.ec2.internal
ip-10-0-10-231.ec2.internal
ip-10-0-11-207.ec2.internal
ip-10-0-11-40.ec2.internal
```

Các service critical có hai pod Running và Ready. Evidence cho thấy các cặp replica được phân tán trên nhiều node.

Ví dụ:

- `cart`: `ip-10-0-10-17` và `ip-10-0-11-207`
- `checkout`: `ip-10-0-10-231` và `ip-10-0-11-207`
- `frontend`: `ip-10-0-10-17` và `ip-10-0-10-231`
- `frontend-proxy`: `ip-10-0-10-231` và `ip-10-0-11-207`
- `payment`: `ip-10-0-10-17` và `ip-10-0-11-207`
- `product-catalog`: `ip-10-0-10-231` và `ip-10-0-11-207`
- `quote`: `ip-10-0-10-231` và `ip-10-0-11-207`
- `shipping`: `ip-10-0-11-40` và `ip-10-0-11-207`

### Kết luận placement

```text
Replica redundancy: PASS
Multi-node placement: PASS
Quote multi-AZ placement: PASS
Controlled-drain behavior: PENDING REHEARSAL
```

Placement hiện tại loại bỏ phần lớn singleton risk, nhưng chỉ controlled drain mới chứng minh được availability thực tế trong voluntary disruption.

---

## 7. Cấu hình HPA

Runtime hiện có HPA cho:

| HPA target | Current CPU | Target CPU | Min replicas | Max replicas | Current replicas |
|---|---:|---:|---:|---:|---:|
| `Deployment/checkout` | Khoảng `2%` | `70%` | `2` | `3` | `2` |
| `Deployment/currency` | Khoảng `2%` | `70%` | `2` | `3` | `2` |
| `Deployment/frontend` | Khoảng `18%` | `70%` | `2` | `3` | `2` |

Không thấy HPA cho:

- `frontend-proxy`
- `product-catalog`
- `cart`
- `payment`
- `shipping`
- `quote`

HPA không thay thế PDB và topology spread, nhưng `minReplicas=2` của các workload có HPA hiện tạo sẵn redundancy tốt hơn trạng thái ban đầu.

---

## 8. Review CPU/memory requests và limits

Riêng `quote` hiện có:

| Resource | Request | Limit |
|---|---:|---:|
| CPU | `10m` | `50m` |
| Memory | `20Mi` | `40Mi` |

Pod metrics quan sát được:

| Pod | CPU | Memory |
|---|---:|---:|
| `quote-dfd7f7bb7-26jkn` | `1m` | `15Mi` |
| `quote-dfd7f7bb7-fbq6z` | `1m` | `15Mi` |

Kết luận:

```text
Quote scheduler reservation: PRESENT
Quote current usage below limits: YES
Right-sizing concern blocking maintenance: NOT OBSERVED
```

---

## 9. Trạng thái PodDisruptionBudget

Runtime có PDB cho toàn bộ revenue-path service được kiểm tra:

| Service | Min available | Allowed disruptions |
|---|---:|---:|
| `cart` | `1` | `1` |
| `checkout` | `1` | `1` |
| `currency` | `1` | `1` |
| `frontend` | `1` | `1` |
| `frontend-proxy` | `1` | `1` |
| `payment` | `1` | `1` |
| `product-catalog` | `1` | `1` |
| `quote` | `1` | `1` |
| `shipping` | `1` | `1` |

### Kết luận PDB

```text
PDB protection: PASS
One voluntary disruption currently allowed: YES
```

PDB bảo vệ minimum availability cho voluntary disruption, nhưng không tự chứng minh checkout SLO. Controlled-drain validation vẫn bắt buộc.

---

## 10. Node utilization sau remediation

| Node | CPU | CPU % | Memory | Memory % |
|---|---:|---:|---:|---:|
| `ip-10-0-10-17.ec2.internal` | `326m` | `16%` | `4088Mi` | `57%` |
| `ip-10-0-10-231.ec2.internal` | `159m` | `8%` | `2791Mi` | `39%` |
| `ip-10-0-11-207.ec2.internal` | `247m` | `12%` | `1066Mi` | `15%` |
| `ip-10-0-11-40.ec2.internal` | `194m` | `10%` | `3945Mi` | `55%` |

Observed range:

```text
CPU: 8%–16%
Memory: 15%–57%
```

Runtime utilization cho thấy cluster không bị saturation tại thời điểm collection.

Tuy nhiên:

- `kubectl top` phản ánh usage, không phải scheduler requests.
- Usage thấp không đủ để tự kết luận drain sẽ PASS.
- Drain vẫn phải kiểm tra PDB behavior, rescheduling và SLO.

---

## 11. Đánh giá capacity trước controlled drain

### Initial state

Snapshot ban đầu với hai nodes có CPU requests cao và không đủ static headroom để hấp thụ toàn bộ workload của node còn lại:

```text
Initial two-node static drain capacity: FAIL
```

### Post-remediation state

Sau remediation:

- Cluster có bốn worker nodes.
- Critical revenue-path services có hai replicas.
- PDB cho phép một disruption.
- Pod replicas được phân tán trên nhiều node.
- Node CPU/memory usage không ở trạng thái saturation.
- `quote` có hai serving endpoints trên hai node và hai AZ.

### Verdict

```text
Post-remediation capacity pre-check: PASS
Ready for controlled-drain rehearsal: YES
Controlled node-drain capacity: PENDING EXECUTION
```

Không ghi “node drain PASS” trước khi có actual drain evidence.

---

## 12. Khả năng scale-out

Initial evidence cho thấy managed node group:

| Setting | Value |
|---|---:|
| `minSize` | `2` |
| `desiredSize` | `2` |
| `maxSize` | `4` |

Post-remediation runtime đã có bốn worker nodes. Điều này xác nhận capacity đã được pre-scale/provision thêm so với initial snapshot.

```text
Current worker nodes: 4
Manual/pre-provisioned scale-out: OBSERVED
Automatic Cluster Autoscaler: NOT OBSERVED IN INITIAL CHECK
```

Tài liệu này không khẳng định bốn node đều thuộc cùng một managed node group; source node/instance evidence phải được dùng khi cần phân biệt managed nodes và Karpenter nodes.

---

## 13. Phân loại synchronous và asynchronous

| Service | Phân loại | Lý do |
|---|---|---|
| `frontend-proxy` | Synchronous | Điểm vào customer-facing request |
| `frontend` | Synchronous | Điều phối customer-facing traffic |
| `product-catalog` | Synchronous | Cần cho browse/product detail |
| `cart` | Synchronous | Cần cho cart operations |
| `checkout` | Synchronous | Điều phối order placement |
| `payment` | Synchronous | Cần để hoàn tất checkout |
| `currency` | Synchronous | Pricing/checkout dependency |
| `shipping` | Synchronous | Shipping option/cost dependency |
| `quote` | Synchronous | Được `shipping GetQuote` gọi đồng bộ trên checkout path |

Các workload như `email`, `fraud-detection`, `recommendation`, `product-reviews` và Kafka-related workloads nằm ngoài mandatory inventory này trừ khi trace/source evidence cho thấy customer request chờ kết quả của chúng.

---

## 14. Risk register sau remediation

| Risk | Trạng thái | Severity hiện tại | Follow-up |
|---|---|---|---|
| `quote` chỉ có một replica | RESOLVED | Closed | Không |
| `quote` thiếu requests/limits | RESOLVED | Closed | Không |
| `quote` không có PDB | RESOLVED | Closed | Không |
| `quote` không có topology spread | RESOLVED | Closed | Không |
| `quote` không có probes | RESOLVED | Closed | Không |
| Revenue path thiếu replica redundancy | RESOLVED trong snapshot hiện tại | Low | Theo dõi trước witness |
| PDB behavior khi drain | PENDING | High | Controlled drain |
| Pod reschedule time | PENDING | High | Controlled drain |
| Checkout success rate trong drain | PENDING | Critical | SLO dashboard |
| Checkout p95 latency trong drain | PENDING | High | SLO dashboard |
| Post-maintenance scale-down/cost | PENDING | Medium | Cost evidence |

---

## 15. Current verdict

| Hạng mục | Verdict |
|---|---|
| Runtime inventory | PASS |
| Post-remediation deployment replicas | PASS |
| Requests và limits evidence | PASS |
| HPA evidence | PASS |
| Pod-to-node placement | PASS |
| PDB protection | PASS |
| `quote` remediation | PASS |
| `quote` 2 serving endpoints | PASS |
| `quote` probes | PASS |
| `quote` topology spread | PASS |
| Four-node runtime capacity pre-check | PASS |
| Official controlled-drain readiness | READY |
| Controlled maintenance execution | PENDING |
| Controlled maintenance SLO validation | PENDING |

---

## 16. Follow-up cần thực hiện

### CDO-04 Performance và Cost

- Chụp dashboard trước, trong và sau controlled drain.
- Theo dõi checkout success rate, error rate và p95 latency.
- Xác minh `quote` luôn còn ít nhất một serving endpoint.
- Thu thập pod placement và resource usage sau reschedule.
- Ghi nhận maintenance start/end timestamps.
- Ghi nhận node-hours và cost delta của temporary capacity.
- Xác minh scale-down sau maintenance.

### CDO-08 Reliability

- Thực hiện controlled drain hoặc rolling restart theo runbook.
- Xác nhận PDB không block ngoài dự kiến.
- Theo dõi pod eviction, reschedule và readiness recovery.
- Công bố node target và maintenance timestamps.
- Xác nhận admission policy không block pod recreation.

---

## 17. Acceptance Criteria assessment

- [x] Có inventory cho từng service revenue-critical.
- [x] Có desired/ready replica runtime.
- [x] Có CPU/memory requests và limits.
- [x] Có HPA configuration.
- [x] Có pod-to-node placement.
- [x] Có PDB runtime evidence.
- [x] Có serving-endpoint evidence.
- [x] Có final synchronous classification cho `quote`.
- [x] Có remediation verification cho `quote`.
- [x] Có node và pod utilization sau remediation.
- [x] Reliability remediation hoàn tất.
- [x] Sẵn sàng cho controlled-drain rehearsal.
- [ ] Controlled node-drain rehearsal hoàn tất.
- [ ] Official maintenance SLO validation hoàn tất.
- [ ] Post-maintenance scale-down và cost validation hoàn tất.

D3-PERF-01 hoàn tất ở phạm vi runtime inventory, remediation verification và pre-drain capacity readiness.

Directive #3 chỉ được kết luận PASS sau controlled maintenance và SLO validation.

---

## 18. Kết luận cuối

Sau remediation, revenue path hiện có hai replicas Ready cho các service critical trên bốn worker nodes.

Riêng `quote` đã được xác minh:

- Deployment `2/2 Ready`.
- Hai pod Running trên hai worker nodes khác nhau.
- Hai pod nằm ở hai Availability Zones khác nhau.
- PDB `minAvailable=1`, `allowedDisruptions=1`.
- Hai EndpointSlice endpoints đều `ready=true`.
- Topology spread theo `kubernetes.io/hostname`.
- Readiness và liveness probes qua `tcpSocket:8080`.
- CPU request/limit là `10m/50m`.
- Memory request/limit là `20Mi/40Mi`.

Node utilization sau remediation:

```text
CPU: 8%–16%
Memory: 15%–57%
```

Final status:

```text
Initial two-node static capacity: FAIL
Post-remediation inventory: PASS
Quote runtime remediation: PASS
PDB protection: PASS
Ready for controlled-drain rehearsal: YES
Controlled-drain SLO validation: PENDING
```

D3-PERF-01 có thể được chuyển sang **Done** với ghi chú rằng controlled drain thuộc bước validation kế tiếp, không phải evidence còn thiếu của inventory task.