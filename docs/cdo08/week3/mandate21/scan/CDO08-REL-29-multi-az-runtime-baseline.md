# CDO08-REL-29 Multi-AZ Runtime Baseline

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-29
**Ngày ghi nhận:** 2026-07-28
**Scope tham chiếu:** `docs/cdo08/week3/mandate21/adr/CDO08-REL-28-revenue-path-scope.md`

Tài liệu này ghi lại baseline runtime hiện tại cho Mandate 21 trước khi quyết định scale, topology spread hoặc PDB. Đây là snapshot read-only, không thay đổi cấu hình runtime.

---

## 1. Output Của Task

Task này cần tạo ra các output sau:

- Node baseline theo AZ và capacity type.
- Karpenter `NodePool`/`NodeClaim` baseline.
- Pod placement theo service/AZ.
- Deployment strategy, desired/current replicas.
- HPA min/max/current replicas.
- PDB allowed disruptions.
- ResourceQuota/headroom.
- Pending/FailedScheduling/runtime readiness evidence.
- Argo runtime health liên quan readiness trước drill.

Kết luận hiện tại:

| Hạng mục                | Trạng thái | Evidence chính                                                                              |
| ----------------------- | ---------- | ------------------------------------------------------------------------------------------- |
| Node trải AZ            | PASS       | 5 node Ready, trải `us-east-1a` và `us-east-1b`                                             |
| Karpenter capacity      | PASS       | Spot nodepool có node ở `1a/1b`, protected on-demand node ở `1b`                            |
| Revenue-path 2 replicas | PARTIAL    | Nhiều service 2 replicas, nhưng `cart` đang dồn cả 2 pod vào `1a`                           |
| HPA baseline            | PASS       | HPA có cho `frontend`, `frontend-proxy`, `cart`, `checkout`, `currency`, `product-catalog`  |
| PDB baseline            | PARTIAL    | PDB đa số allowed disruptions `1`; `product-reviews` allowed disruptions `0`                |
| Quota/headroom          | PASS       | Pods `36/50`, requests CPU `2290m/4`, requests memory `4232Mi/9Gi`                          |
| Runtime health          | PARTIAL    | `techx-corp` Synced/Progressing; `techx-raw` OutOfSync/Healthy; `product-reviews` 1/2 Ready |

---

## 2. Commands Đã Chạy

```powershell
kubectl get nodes -L topology.kubernetes.io/zone,karpenter.sh/capacity-type,kubernetes.io/arch -o wide
kubectl get nodepool,nodeclaim -o wide
kubectl -n techx-tf4 get deploy,hpa,pdb -o wide
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get resourcequota -o wide
kubectl -n techx-tf4 describe resourcequota
kubectl -n techx-tf4 get events --sort-by=.lastTimestamp
kubectl -n argocd get application techx-corp techx-raw -o wide
```

---

## 3. Node Baseline Theo AZ

| Node                          | Status | AZ           | Capacity type | Arch  | Internal IP   | Age |
| ----------------------------- | ------ | ------------ | ------------- | ----- | ------------- | --- |
| `ip-10-0-10-182.ec2.internal` | Ready  | `us-east-1a` | spot          | arm64 | `10.0.10.182` | 26h |
| `ip-10-0-10-19.ec2.internal`  | Ready  | `us-east-1a` | not labeled   | arm64 | `10.0.10.19`  | 9h  |
| `ip-10-0-11-17.ec2.internal`  | Ready  | `us-east-1b` | spot          | arm64 | `10.0.11.17`  | 14h |
| `ip-10-0-11-192.ec2.internal` | Ready  | `us-east-1b` | on-demand     | arm64 | `10.0.11.192` | 20h |
| `ip-10-0-11-82.ec2.internal`  | Ready  | `us-east-1b` | not labeled   | arm64 | `10.0.11.82`  | 9h  |

Summary:

| AZ           | Nodes | Notes                                                      |
| ------------ | ----: | ---------------------------------------------------------- |
| `us-east-1a` |     2 | 1 spot-labeled, 1 not capacity-type labeled                |
| `us-east-1b` |     3 | 1 spot, 1 on-demand protected, 1 not capacity-type labeled |

Kết luận:

- Runtime hiện có node ở 2 AZ: `us-east-1a` và `us-east-1b`.
- Chưa thấy node ở AZ thứ ba trong snapshot này.
- Có 2 node không có label `karpenter.sh/capacity-type` trong command output, cần ghi nhận là observed runtime thay vì tự suy đoán loại capacity.

---

## 4. Karpenter NodePool/NodeClaim Baseline

NodePool:

| NodePool                | NodeClass       | Nodes | Ready | CPU |     Memory |
| ----------------------- | --------------- | ----: | ----- | --: | ---------: |
| `techx-arm64-canary`    | `techx-general` |     0 | True  |   0 |          0 |
| `techx-arm64-protected` | `techx-general` |     1 | True  |   2 |  7997348Ki |
| `techx-arm64-spot`      | `techx-general` |     2 | True  |   6 | 11849352Ki |
| `techx-general`         | `techx-general` |     0 | True  |   0 |          0 |

NodeClaim:

| NodeClaim                     | Type         | Capacity  | AZ           | Node                          | Ready | NodePool                |
| ----------------------------- | ------------ | --------- | ------------ | ----------------------------- | ----- | ----------------------- |
| `techx-arm64-protected-6zcgs` | `t4g.large`  | on-demand | `us-east-1b` | `ip-10-0-11-192.ec2.internal` | True  | `techx-arm64-protected` |
| `techx-arm64-spot-5wg4f`      | `c7g.xlarge` | spot      | `us-east-1b` | `ip-10-0-11-17.ec2.internal`  | True  | `techx-arm64-spot`      |
| `techx-arm64-spot-rv82s`      | `c7g.large`  | spot      | `us-east-1a` | `ip-10-0-10-182.ec2.internal` | True  | `techx-arm64-spot`      |

Kết luận:

- Karpenter-managed spot capacity đang trải `1a/1b`.
- Protected on-demand capacity hiện chỉ nằm ở `1b`.
- Tổng `kubectl get nodes` có 5 nodes, trong khi NodeClaim output hiển thị 3 NodeClaims; 2 node còn lại cần ghi nhận là runtime nodes không map vào NodeClaim output tại thời điểm scan.

---

## 5. Pod Placement Theo Service/AZ

| Service           | us-east-1a ready/total | us-east-1b ready/total | Placement note                                |
| ----------------- | ---------------------: | ---------------------: | --------------------------------------------- |
| `accounting`      |                    0/0 |                    1/1 | Single replica ở `1b`                         |
| `ad`              |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `aiops`           |                    0/0 |                    1/1 | Single replica ở `1b`, ngoài revenue path     |
| `cart`            |                    2/2 |                    0/0 | 2 replicas nhưng cùng `1a`                    |
| `checkout`        |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `currency`        |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `email`           |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `flagd`           |                    1/1 |                    0/0 | Single replica ở `1a`                         |
| `fraud-detection` |                    0/0 |                    1/1 | Single replica ở `1b`                         |
| `frontend`        |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `frontend-proxy`  |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `image-provider`  |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `kafka-connect`   |                    0/0 |                    1/1 | Single replica ở `1b`                         |
| `llm`             |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `load-generator`  |                    0/0 |                    1/1 | Single replica ở `1b`; ảnh hưởng drill driver |
| `payment`         |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `product-catalog` |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `product-reviews` |                    1/1 |                    0/1 | Pod `1b` Running nhưng not Ready              |
| `quote`           |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `recommendation`  |                    1/1 |                    1/1 | Trải 2 AZ                                     |
| `shipping`        |                    1/1 |                    1/1 | Trải 2 AZ                                     |

Kết luận:

- Core browse/checkout path đa số đã có 2 replicas và trải 2 AZ.
- `cart` là gap rõ trên revenue path vì cả 2 ready pods đang nằm ở `us-east-1a`.
- `accounting`, `fraud-detection`, `kafka-connect-orders-archive`, `load-generator` là single-replica workloads cần phân loại impact trước khi scale.
- `product-reviews` có desired 2 nhưng only 1 Ready tại thời điểm scan.

---

## 6. Revenue-Path Deployment/HPA/PDB Baseline

| Service                        | Desired replicas | Ready | Strategy      | HPA min/max   | PDB allowed disruptions | Placement summary        |
| ------------------------------ | ---------------: | ----- | ------------- | ------------- | ----------------------: | ------------------------ |
| `frontend-proxy`               |                2 | 2/2   | RollingUpdate | 2/4           |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `frontend`                     |                2 | 2/2   | RollingUpdate | 2/6           |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `cart`                         |                2 | 2/2   | RollingUpdate | 2/4           |                       1 | 2 pods `1a`, 0 pods `1b` |
| `checkout`                     |                2 | 2/2   | RollingUpdate | 2/3           |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `currency`                     |                2 | 2/2   | RollingUpdate | 2/3           |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `payment`                      |                2 | 2/2   | RollingUpdate | none observed |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `product-catalog`              |                2 | 2/2   | RollingUpdate | 2/4           |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `shipping`                     |                2 | 2/2   | RollingUpdate | none observed |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `email`                        |                2 | 2/2   | RollingUpdate | none observed |                       1 | 1 pod `1a`, 1 pod `1b`   |
| `accounting`                   |                1 | 1/1   | Recreate      | none observed |           none observed | single pod `1b`          |
| `fraud-detection`              |                1 | 1/1   | Recreate      | none observed |           none observed | single pod `1b`          |
| `kafka-connect-orders-archive` |                1 | 1/1   | RollingUpdate | none observed |           none observed | single pod `1b`          |
| `load-generator`               |                1 | 1/1   | RollingUpdate | none observed |           none observed | single pod `1b`          |

Kết luận:

- `frontend`, `frontend-proxy`, `checkout`, `currency`, `product-catalog`, `cart` có HPA baseline.
- `payment`, `shipping`, `email` có 2 replicas/PDB và spread, nhưng không có HPA observed.
- `accounting` và `fraud-detection` dùng `Recreate` strategy và 1 replica; đây là important data/async path gap cần phân loại.
- `kafka-connect-orders-archive` là backup/archive path, không trực tiếp request path nhưng liên quan MSK archive RPO.

---

## 7. Topology/Strategy Notes

Observed topology spread:

- Nhiều 2-replica services có topology spread theo `topology.kubernetes.io/zone` với `maxSkew=1` và `whenUnsatisfiable=ScheduleAnyway`.
- Nhiều services cũng có hostname spread/anti-affinity.
- Vì zone spread đang `ScheduleAnyway`, scheduler có thể vẫn đặt nhiều pod cùng AZ khi có ràng buộc khác; `cart` hiện là ví dụ thực tế.

Services không thấy topology/affinity trong scan:

- `accounting`
- `aiops`
- `flagd`
- `fraud-detection`
- `kafka-connect-orders-archive`
- `load-generator`

Kết luận:

- Baseline đã có hướng topology spread cho nhiều service.
- Với Mandate 21, các service revenue/data path cần phân loại xem `ScheduleAnyway` có đủ cho AZ-loss readiness hay cần policy chặt hơn trong task implement sau.

---

## 8. ResourceQuota / Headroom

ResourceQuota `techx-quota`:

| Resource        |   Used | Hard |     Headroom |
| --------------- | -----: | ---: | -----------: |
| pods            |     36 |   50 |           14 |
| requests.cpu    |  2290m |    4 |        1710m |
| requests.memory | 4232Mi |  9Gi | khoảng 4.9Gi |
| limits.cpu      |  9400m |   14 |        4600m |
| limits.memory   | 7883Mi | 12Gi | khoảng 4.3Gi |

Kết luận:

- Namespace còn pod headroom để tăng một số replica có chọn lọc.
- CPU request headroom không quá lớn; cần tính kỹ nếu REL32 muốn tăng replica nhiều service cùng lúc.
- REL-29 không scale ngay, chỉ ghi baseline/headroom.

---

## 9. Runtime Health / Events

Argo:

| Application  | Sync      | Health      | Operation                                        |
| ------------ | --------- | ----------- | ------------------------------------------------ |
| `techx-corp` | Synced    | Progressing | Succeeded, `successfully synced (all tasks run)` |
| `techx-raw`  | OutOfSync | Healthy     | Succeeded, `successfully synced (no more tasks)` |

Events đáng chú ý:

| Component         | Event                             | Evidence                                                       |
| ----------------- | --------------------------------- | -------------------------------------------------------------- |
| `product-reviews` | BackOff/restart/readiness timeout | Pod in `1b` Running but not Ready; PDB allowed disruptions `0` |

Kết luận:

- Argo/runtime health chưa hoàn toàn clean trước drill.
- `product-reviews` issue cần được phân loại vì không nằm trên core browse/cart/checkout path trực tiếp, nhưng ảnh hưởng broader app readiness/Argo health.

---

## 10. Baseline Summary

Các điểm đã ổn:

- Cluster có node ở `us-east-1a` và `us-east-1b`.
- Nhiều service quan trọng đã có 2 replicas, PDB và pod spread across AZ.
- HPA đã có cho nhiều thành phần core path.
- Quota còn headroom để xử lý một số gap có chọn lọc.

Các điểm cần đưa sang gap register:

- `cart` đang dồn cả 2 pods vào `us-east-1a`.
- `accounting`, `fraud-detection`, `kafka-connect-orders-archive`, `load-generator` chỉ có 1 replica.
- `product-reviews` unhealthy/not Ready ở 1 pod và PDB allowed disruptions `0`.
- `techx-corp` Progressing và `techx-raw` OutOfSync cần ghi nhận trước drill.
- Chỉ observed 2 AZ; Mandate yêu cầu chịu mất 1 AZ, nên 2 AZ có thể đủ nếu workload thực sự trải đều, nhưng không có margin AZ thứ ba trong snapshot này.
