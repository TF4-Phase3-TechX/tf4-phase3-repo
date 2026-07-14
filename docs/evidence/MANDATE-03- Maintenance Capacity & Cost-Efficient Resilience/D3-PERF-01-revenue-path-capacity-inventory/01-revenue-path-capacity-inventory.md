# D3-PERF-01 — Kiểm kê năng lực Revenue Path

**Directive:** MANDATE-03 — Maintenance Capacity & Cost-Efficient Resilience  
**Owner:** An — CDO-04 Performance Efficiency & Cost Optimization  
**Cluster:** `techx-tf4-cluster`  
**Cluster ARN:** `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`  
**Namespace:** `techx-tf4`  
**Region:** `us-east-1`  
**Thư mục evidence:** `./raw/`  
**Trạng thái:** Hoàn tất kiểm kê runtime, đã phát hiện rủi ro năng lực bảo trì  

---

## 1. Mục tiêu

Task này kiểm kê trạng thái runtime hiện tại của các service ảnh hưởng trực tiếp đến luồng doanh thu:

```text
frontend-proxy
→ frontend
→ product-catalog / cart
→ checkout
→ payment / shipping / currency / quote
```

Mục tiêu:

- Xác định replica desired, current và ready.
- Xác định CPU/memory requests và limits.
- Xác định HPA.
- Xác định pod-to-node placement.
- Xác định service chỉ có một replica.
- Đánh giá khả năng chịu lỗi khi drain một worker node.
- Phân loại synchronous và asynchronous.
- Xác định tổng requested CPU/memory trên từng node.
- Đánh giá static capacity hiện tại có đủ cho planned maintenance hay không.

Kết luận trong tài liệu này dựa trên trạng thái runtime Kubernetes và cấu hình EKS, không dựa riêng vào Helm values.

---

## 2. Bối cảnh thu thập evidence

```text
Cluster: techx-tf4-cluster
Namespace: techx-tf4
Region: us-east-1
Kube context: arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Đã xác minh quyền read-only cho Deployments, Pods, HPA, Nodes và PodDisruptionBudgets.

Timestamp, kube context, namespace và collector được lưu tại:

[raw/00-collection-metadata.txt](raw/00-collection-metadata.txt)

---

## 3. Danh sách evidence

| Nội dung | File |
|---|---|
| Timestamp và collection context | [raw/00-collection-metadata.txt](raw/00-collection-metadata.txt) |
| Replica state | [raw/02-replica-summary.txt](raw/02-replica-summary.txt) |
| Pod-to-node placement | [raw/03-pod-placement-summary.txt](raw/03-pod-placement-summary.txt) |
| HPA runtime state | [raw/04-hpa-wide.txt](raw/04-hpa-wide.txt) |
| Node `ip-10-0-10-231` allocated resources | [raw/06-node-10-0-10-231-allocated.txt](raw/06-node-10-0-10-231-allocated.txt) |
| Node `ip-10-0-11-40` allocated resources | [raw/06-node-10-0-11-40-allocated.txt](raw/06-node-10-0-11-40-allocated.txt) |
| Worker node inventory | [raw/06-nodes-wide.txt](raw/06-nodes-wide.txt) |
| CPU/memory requests và limits | [raw/10-resource-requests-limits.txt](raw/10-resource-requests-limits.txt) |
| Node-group scaling configuration | [raw/12-nodegroup-scaling-config.json](raw/12-nodegroup-scaling-config.json) |
| Autoscaler và scale-out assessment | [raw/13-cluster-autoscaler-and-scaleout-status.txt](raw/13-cluster-autoscaler-and-scaleout-status.txt) |
| Cluster Autoscaler lookup | [raw/13-cluster-autoscaler-status.txt](raw/13-cluster-autoscaler-status.txt) |

Kết quả kiểm tra PDB:

```text
No resources found in techx-tf4 namespace.
```

Nên lưu kết quả này tại [raw/05-pdb-wide.txt](raw/05-pdb-wide.txt).

---

## 4. Revenue-path runtime inventory

| Service | Desired / Current / Ready | CPU request | CPU limit | Memory request | Memory limit | HPA | Runtime node | Loại luồng | Rủi ro chính |
|---|---:|---:|---:|---:|---:|---|---|---|---|
| `frontend-proxy` | `1 / 1 / 1` | `50m` | `200m` | `64Mi` | `128Mi` | Không thấy | `ip-10-0-10-231.ec2.internal` | Synchronous | Một Ready replica |
| `frontend` | `1 / 1 / 1` | `100m` | `400m` | `192Mi` | `320Mi` | Min `1`, max `3` | `ip-10-0-10-231.ec2.internal` | Synchronous | HPA min vẫn là một |
| `product-catalog` | `1 / 1 / 1` | `50m` | `200m` | `32Mi` | `64Mi` | Không thấy | `ip-10-0-10-231.ec2.internal` | Synchronous | Một Ready replica |
| `cart` | `1 / 1 / 1` | `75m` | `300m` | `96Mi` | `192Mi` | Không thấy | `ip-10-0-10-231.ec2.internal` | Synchronous | Một Ready replica |
| `checkout` | `1 / 1 / 1` | `75m` | `300m` | `48Mi` | `96Mi` | Min `1`, max `3` | `ip-10-0-11-40.ec2.internal` | Synchronous | HPA min vẫn là một |
| `payment` | `1 / 1 / 1` | `50m` | `200m` | `64Mi` | `128Mi` | Không thấy | `ip-10-0-11-40.ec2.internal` | Synchronous | Một Ready replica |
| `currency` | `1 / 1 / 1` | `20m` | `75m` | `24Mi` | `48Mi` | Không thấy | `ip-10-0-11-40.ec2.internal` | Synchronous | Một Ready replica |
| `shipping` | `1 / 1 / 1` | `20m` | `75m` | `16Mi` | `32Mi` | Không thấy | `ip-10-0-11-40.ec2.internal` | Synchronous | Một Ready replica |
| `quote` | `1 / 1 / 1` | Thiếu | Thiếu | Thiếu | `40Mi` | Không thấy | `ip-10-0-10-231.ec2.internal` | Synchronous candidate | Thiếu requests và một replica |

> Nếu runtime thay đổi trước review hoặc mentor witness, phải thu thập lại evidence.

---

## 5. Pod-to-node placement

### Node `ip-10-0-10-231.ec2.internal`

- `frontend`
- `frontend-proxy`
- `product-catalog`
- `cart`
- `quote`

### Node `ip-10-0-11-40.ec2.internal`

- `checkout`
- `payment`
- `currency`
- `shipping`

### Kết luận placement

Revenue path hiện được chia trên hai worker node, nhưng mỗi critical service chỉ có một pod Ready.

- Drain node `ip-10-0-10-231` có thể làm mất frontend, product catalog, cart và quote cho đến khi pod mới Ready.
- Drain node `ip-10-0-11-40` có thể làm mất checkout, payment, currency và shipping cho đến khi pod mới Ready.
- Mỗi node đều chứa service bắt buộc cho customer transaction.
- Không có replica redundancy sẵn cho từng revenue-path service.

Kết luận phù hợp:

> Runtime evidence cho thấy mỗi revenue-path service chỉ có một Ready replica. Khi node bị drain hoặc pod restart, service có nguy cơ mất endpoint tạm thời trong thời gian reschedule và readiness recovery.

Không kết luận “confirmed SPOF” chỉ từ Helm values hoặc replica count.

---

## 6. Cấu hình HPA

| HPA target | Current CPU | Target CPU | Min replicas | Max replicas | Current replicas |
|---|---:|---:|---:|---:|---:|
| `Deployment/checkout` | Khoảng `2%` | `70%` | `1` | `3` | `1` |
| `Deployment/frontend` | Khoảng `21%` | `70%` | `1` | `3` | `1` |

Không thấy HPA cho:

- `frontend-proxy`
- `product-catalog`
- `cart`
- `payment`
- `currency`
- `shipping`
- `quote`

Hai HPA hiện tại không tạo sẵn redundancy cho planned disruption vì `minReplicas = 1` và runtime vẫn chỉ có một replica. HPA không thay thế pre-scale hoặc minimum availability configuration.

---

## 7. Review CPU/memory requests và limits

### Node `ip-10-0-10-231.ec2.internal`

| Service | CPU request | Memory request |
|---|---:|---:|
| `frontend` | `100m` | `192Mi` |
| `frontend-proxy` | `50m` | `64Mi` |
| `product-catalog` | `50m` | `32Mi` |
| `cart` | `75m` | `96Mi` |
| `quote` | Thiếu | Thiếu |
| **Tổng đã biết** | **`275m`** | **`384Mi`** |

### Node `ip-10-0-11-40.ec2.internal`

| Service | CPU request | Memory request |
|---|---:|---:|
| `checkout` | `75m` | `48Mi` |
| `payment` | `50m` | `64Mi` |
| `currency` | `20m` | `24Mi` |
| `shipping` | `20m` | `16Mi` |
| **Tổng** | **`165m`** | **`152Mi`** |

`quote` thiếu CPU request, CPU limit và memory request. Điều này làm scheduler reservation và drain-headroom analysis kém chính xác, đồng thời tạo rủi ro tranh chấp tài nguyên.

---

## 8. Tổng requested resources theo node

| Node | CPU requests | CPU limits | Memory requests | Memory limits |
|---|---:|---:|---:|---:|
| `ip-10-0-10-231.ec2.internal` | `1800m` (`93%`) | `3460m` (`176%`) | `1736Mi` (`66%`) | `7846Mi` (`110%`) |
| `ip-10-0-11-40.ec2.internal` | `1555m` (`80%`) | `750m` (`38%`) | `2739Mi` (`38%`) | `5387Mi` (`76%`) |

Kubernetes scheduler chủ yếu sử dụng requests khi quyết định placement.

Approximate CPU request headroom:

| Node | Headroom |
|---|---:|
| `ip-10-0-10-231.ec2.internal` | Khoảng `135m` |
| `ip-10-0-11-40.ec2.internal` | Khoảng `390m` |

CPU reservation là giới hạn chính cho node drain. CPU limits trên 100% thể hiện overcommit nhưng không trực tiếp block scheduling.

---

## 9. Đánh giá capacity khi drain node

### Drain `ip-10-0-10-231.ec2.internal`

```text
CPU requests cần reschedule: khoảng 1800m
CPU headroom node còn lại: khoảng 390m
```

**Verdict: FAIL — không đủ CPU request headroom.**

Revenue-path service bị ảnh hưởng:

- `frontend`
- `frontend-proxy`
- `product-catalog`
- `cart`
- `quote`

### Drain `ip-10-0-11-40.ec2.internal`

```text
CPU requests cần reschedule: khoảng 1555m
CPU headroom node còn lại: khoảng 135m
```

**Verdict: FAIL — không đủ CPU request headroom.**

Revenue-path service bị ảnh hưởng:

- `checkout`
- `payment`
- `currency`
- `shipping`

### Kết luận static capacity

```text
Current static node-drain capacity: FAIL
```

Không worker node nào có đủ CPU request headroom để hấp thụ toàn bộ workload từ node còn lại.

Kết luận này phản ánh current static capacity, không khẳng định cluster không thể phục hồi nếu chủ động thêm node trước maintenance.

---

## 10. Khả năng scale-out của EKS node group

| Setting | Value |
|---|---:|
| `minSize` | `2` |
| `desiredSize` | `2` |
| `maxSize` | `4` |

Node group cho phép bổ sung tối đa hai node so với trạng thái hiện tại.

Không quan sát thấy Cluster Autoscaler Deployment hoặc Pod trong `kube-system`.

```text
Automatic node scale-out: NOT OBSERVED
Manual node-group scale-out: AVAILABLE
```

`maxSize > desiredSize` chỉ chứng minh node group cho phép scale-out, không chứng minh cluster sẽ tự thêm node khi pod Pending.

Trước official maintenance test, CDO-08 nên:

1. Pre-scale từ hai lên ít nhất ba worker node.
2. Chờ node mới `Ready`.
3. Thu thập lại allocatable và requested resources.
4. Xác minh pod placement.
5. Xác minh critical service có redundancy phù hợp.
6. Chạy controlled dry-run.
7. Chỉ scale down sau khi post-check PASS.

---

## 11. Trạng thái PodDisruptionBudget

Runtime query không tìm thấy PodDisruptionBudget trong namespace `techx-tf4`.

> Hiện không có PDB-based minimum availability guarantee cho voluntary disruption trên revenue-path workloads.

Không có PDB không tự động chứng minh tất cả service chắc chắn bị rớt. Ảnh hưởng thực tế còn phụ thuộc replica count, placement, readiness, rescheduling duration, remaining capacity và rollout strategy.

Tuy nhiên, kết hợp với một Ready replica mỗi service, đây là reliability gap đáng kể.

---

## 12. Phân loại synchronous và asynchronous

| Service | Phân loại | Lý do |
|---|---|---|
| `frontend-proxy` | Synchronous | Điểm vào customer-facing request |
| `frontend` | Synchronous | Điều phối customer-facing traffic |
| `product-catalog` | Synchronous | Cần cho browse/product detail |
| `cart` | Synchronous | Cần cho cart operations |
| `checkout` | Synchronous | Điều phối order placement |
| `payment` | Synchronous | Cần để hoàn tất checkout |
| `currency` | Synchronous | Có thể cần trong browse hoặc checkout |
| `shipping` | Synchronous | Cần cho shipping option/cost |
| `quote` | Synchronous candidate | Cần trace xác nhận |

Các workload như `email`, `fraud-detection`, `recommendation`, `product-reviews` và Kafka-related workloads có thể thuộc post-order hoặc async flow, nhưng phải xác minh bằng Jaeger, source code hoặc architecture diagram.

Không phân loại async chỉ vì workload dùng Kafka. Nếu customer request phải chờ kết quả, service vẫn thuộc synchronous path.

---

## 13. Single-replica risk register

| Service | Runtime state | Rủi ro | Severity |
|---|---|---|---|
| `frontend-proxy` | Một Ready replica | Entry-point endpoint có thể mất khi drain | Critical |
| `frontend` | Một Ready replica, HPA min 1 | Endpoint có thể mất trước khi HPA phản ứng | Critical |
| `product-catalog` | Một Ready replica | Browse/product path có nguy cơ gián đoạn | High |
| `cart` | Một Ready replica | Cart operations có nguy cơ gián đoạn | Critical |
| `checkout` | Một Ready replica, HPA min 1 | Order placement có nguy cơ gián đoạn | Critical |
| `payment` | Một Ready replica | Payment completion có nguy cơ gián đoạn | Critical |
| `currency` | Một Ready replica | Pricing/checkout dependency có nguy cơ gián đoạn | High |
| `shipping` | Một Ready replica | Shipping calculation có nguy cơ gián đoạn | High |
| `quote` | Một Ready replica, thiếu requests | Availability và scheduling reservation risk | Critical |

---

## 14. Tổng hợp rủi ro

| Risk | Evidence | Severity | Owner đề xuất |
|---|---|---|---|
| Node còn lại không đủ CPU headroom | CPU requests `93%` và `80%` | Critical | CDO-04 + CDO-08 |
| Revenue-path service chỉ có một Ready pod | Replica và placement evidence | Critical | CDO-08 |
| Không có PDB | Runtime PDB query | High | CDO-08 |
| Frontend/checkout HPA min bằng một | HPA evidence | High | CDO-04 + CDO-08 |
| Phần lớn service không có HPA | HPA evidence | Medium/High | CDO-04 + CDO-08 |
| Quote thiếu requests | Deployment resource evidence | High | CDO-04 |
| Không thấy Cluster Autoscaler | `kube-system` lookup | High | CDO-08 |
| Node group chỉ chứng minh manual scale-out | EKS scaling config | Medium | CDO-08 |
| Không có replica redundancy sẵn | Replica/placement evidence | Critical | CDO-08 |

---

## 15. Current verdict

| Hạng mục | Verdict |
|---|---|
| Runtime inventory | PASS |
| Replica evidence | PASS |
| Requests và limits evidence | PASS |
| HPA evidence | PASS |
| Pod-to-node placement | PASS |
| Node requested-resource evidence | PASS |
| Single-replica risk identification | PASS |
| Static node-drain capacity | FAIL |
| Manual pre-scale capability | AVAILABLE |
| Automatic node scale-out | NOT OBSERVED |
| PDB protection | NOT PRESENT |
| Official maintenance readiness | NOT READY |
| Controlled maintenance validation | PENDING CDO-08 remediation và dry-run |

---

## 16. Follow-up cần thực hiện

### CDO-04 Performance và Cost

- Bổ sung requests/limits cho `quote`.
- Tính cost delta của temporary third worker node.
- Thu thập lại requested resources sau pre-scale.
- Kiểm tra lại requests sau right-sizing.
- Validate SLO trong controlled maintenance test.
- Ghi nhận post-maintenance scale-down và cost delta.

### CDO-08 Reliability

- Review minimum replicas cho revenue-path services.
- Review HPA `minReplicas` của `frontend` và `checkout`.
- Bổ sung hoặc giải trình PDB.
- Review readiness, rolling update và graceful termination.
- Pre-scale trước official maintenance.
- Xác minh node mới `Ready`.
- Thực hiện drain/rolling restart theo runbook.
- Công bố maintenance timestamps.
- Xác nhận admission policy không block pod recreation.

---

## 17. Acceptance Criteria assessment

- [x] Có inventory cho từng service revenue-critical.
- [x] Có desired/current/ready replica runtime.
- [x] Có CPU/memory requests và limits.
- [x] Có HPA configuration.
- [x] Có pod-to-node placement.
- [x] Có tổng requested CPU/memory theo node.
- [x] Có danh sách single-replica risk.
- [x] Có current static node-drain capacity assessment.
- [x] Không kết luận chỉ từ Helm values.
- [x] Có timestamp và source evidence.
- [x] Có preliminary synchronous/async classification.
- [ ] Có Jaeger hoặc source-code evidence để xác nhận final path classification.
- [ ] Reliability remediation hoàn tất.
- [ ] Controlled node-drain dry-run hoàn tất.
- [ ] Official maintenance SLO validation hoàn tất.

D3-PERF-01 hoàn tất ở phạm vi runtime inventory và capacity-risk assessment.

Official Directive #3 maintenance validation vẫn phụ thuộc reliability remediation, pre-scaling và controlled maintenance test.

---

## 18. Kết luận cuối

Tại collection timestamp, namespace `techx-tf4` đang chạy chín revenue-path service với một pod Running và Ready cho mỗi service trên hai EKS worker node.

```text
Node ip-10-0-10-231: CPU requests 93%
Node ip-10-0-11-40: CPU requests 80%
```

Node còn lại không đủ CPU request headroom để hấp thụ toàn bộ pod từ node bị drain.

```text
Current two-node static maintenance capacity: FAIL
Manual pre-scale: AVAILABLE
Automatic scale-out: NOT OBSERVED
```

Các rủi ro chính:

- Mỗi revenue-path service chỉ có một Ready replica.
- Không có PDB.
- HPA min replica của frontend và checkout bằng một.
- Phần lớn revenue service không có HPA.
- `quote` thiếu CPU request, CPU limit và memory request.
- Static two-node capacity không đủ cho node drain.

Môi trường hiện chưa sẵn sàng cho official node-drain maintenance test trong trạng thái hai node hiện tại.

CDO-08 cần pre-scale và xử lý reliability gaps trước controlled maintenance session.

CDO-04 cần revalidate capacity, SLO và temporary cost sau khi pre-scale.