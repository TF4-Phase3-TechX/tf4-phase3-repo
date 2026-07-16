# [REVIEW REQUEST] CDO04 — Runtime Capacity Review cho CDO08-REL-01 (Replica Availability)

| Thông tin       | Giá trị                                                         |
| --------------- | --------------------------------------------------------------- |
| Từ              | CDO08                                                           |
| Đến             | CDO04 (Cost/Capacity)                                           |
| Backlog ID      | `CDO08-REL-01`                                                  |
| Ngày gửi        | 2026-07-14                                                      |
| Mục tiêu review | Xác nhận capacity/node scaling strategy trước khi tăng replicas |
| Trạng thái      | **Needs CDO04 Review**                                          |

---

## 1. Bối cảnh & Yêu cầu thay đổi

CDO08 đang chuẩn bị nâng số lượng replicas từ **1 lên 2** cho 7 critical stateless services trong customer/checkout path:

`frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog`.

Mục tiêu là giảm Single Point of Failure khi pod restart, rollout, node drain hoặc maintenance. Tuy nhiên sau feedback từ CDO04 và các lần kiểm tra runtime mới nhất, CDO08 cần CDO04 review thêm về **scheduler headroom** và **worker node scaling strategy** trước khi coi rollout này là production-safe.

Điểm quan trọng: cluster hiện tại không thiếu CPU theo actual usage, nhưng CPU requests đã sát ngưỡng scheduler capacity. Vì Kubernetes scheduler quyết định pod placement theo `resources.requests`, rủi ro `Insufficient cpu` là có thật khi tăng replicas, rollout surge hoặc chạy load-generator.

---

## 2. Runtime Evidence Mới Nhất

### 2.1 Node actual usage

Command:

```powershell
kubectl top nodes
```

Output:

```text
NAME                          CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
ip-10-0-10-231.ec2.internal   319m         16%      3793Mi          53%
ip-10-0-11-40.ec2.internal    166m         8%       4388Mi          62%
```

Nhận xét:

- Actual CPU hiện tại thấp.
- Memory usage ở mức trung bình, khoảng 53-62%.
- Nếu chỉ nhìn `kubectl top`, cluster có vẻ còn dư.
- Nhưng đây không phải dữ liệu chính để scheduler quyết định pod có fit hay không.

### 2.2 Node allocatable

Command:

```powershell
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU_ALLOC:.status.allocatable.cpu,MEM_ALLOC:.status.allocatable.memory
```

Output:

```text
NAME                          CPU_ALLOC   MEM_ALLOC
ip-10-0-10-231.ec2.internal   1930m       7248300Ki
ip-10-0-11-40.ec2.internal    1930m       7248304Ki
```

Nhận xét:

- Mỗi node có khoảng `1930m` CPU allocatable.
- Tổng 2 worker nodes có khoảng `3860m` CPU allocatable.

### 2.3 Allocated resources theo scheduler

Command:

```powershell
kubectl describe nodes | Select-String -Pattern "Name:|Allocated resources:|Resource|cpu |memory " -Context 0,5
```

Output quan trọng:

```text
Node: ip-10-0-10-231.ec2.internal
cpu                1800m (93%)   3400m (176%)
memory             4736Mi (66%)  7846Mi (110%)

Node: ip-10-0-11-40.ec2.internal
cpu                1555m (80%)   750m (38%)
memory             2739Mi (38%)  5387Mi (76%)
```

Nhận xét:

- Node `ip-10-0-10-231` đã dùng **93% CPU requests**.
- Node `ip-10-0-11-40` đã dùng **80% CPU requests**.
- Tổng CPU request headroom còn khoảng:

```text
Node 10-231: 1930m - 1800m = 130m
Node 11-40: 1930m - 1555m = 375m
Total headroom: ~505m CPU requests
```

CPU requests mới là dữ liệu scheduler dùng để quyết định pod placement. Vì vậy dù actual CPU thấp, cluster vẫn có thể gặp `Pending` nếu không còn đủ CPU request headroom.

---

## 3. Impact Nếu Tăng 7 Critical Services Lên 2 Replicas

Requests hiện tại của 7 critical services:

| Service                                   | CPU request/pod | Memory request/pod |
| ----------------------------------------- | --------------- | ------------------ |
| `frontend-proxy`                          | 50m             | 64Mi               |
| `frontend`                                | 100m            | 192Mi              |
| `checkout`                                | 75m             | 48Mi               |
| `cart`                                    | 75m             | 96Mi               |
| `payment`                                 | 50m             | 64Mi               |
| `shipping`                                | 20m             | 16Mi               |
| `product-catalog`                         | 50m             | 32Mi               |
| **Tổng tăng thêm nếu +1 replica/service** | **420m**        | **512Mi**          |

Nhận xét:

- Nếu tăng từ 1 lên 2 replicas cho cả 7 services, scheduler cần thêm khoảng **420m CPU request** và **512Mi memory request**.
- Tổng CPU request headroom hiện tại khoảng **505m**.
- Về lý thuyết có thể fit nếu scheduler phân phối đều.
- Tuy nhiên margin chỉ còn khoảng **85m**, chưa tính rolling update surge pod, load-generator, observability workload hoặc các deployment khác.

Vì vậy CDO08 đánh giá: tăng replicas có thể fit trong trạng thái tĩnh, nhưng chưa đủ an toàn cho rollout/load test/mandate nếu không có thêm node headroom.

---

## 4. Evidence Scheduling Failure Thực Tế

Command:

```powershell
kubectl get events -A --sort-by=.lastTimestamp | Select-String -Pattern "Insufficient cpu|FailedScheduling|Pending|NotTriggerScaleUp"
```

Output:

```text
techx-tf4   Warning   FailedScheduling    pod/load-generator-549dd99956-g6pdb
0/2 nodes are available: 2 Insufficient cpu. no new claims to deallocate,
preemption: 0/2 nodes are available: 2 No preemption victims found for incoming pod.
```

Nhận xét:

- Đây là bằng chứng runtime trực tiếp cho thấy cluster đã có lúc không schedule được pod do **Insufficient cpu**.
- Pod hiện tại có thể đã Running trở lại, nhưng event này xác nhận scheduler headroom đang mỏng.
- Vấn đề nằm ở scheduler requests/capacity, không phải actual CPU usage tại thời điểm `kubectl top`.

---

## 5. Load-Generator & Other Workload Impact

Load-generator hiện có request:

```text
cpu: 500m
memory: 768Mi
```

Với tổng CPU request headroom chỉ khoảng 505m, một pod load-generator mới hoặc surge trong rollout có thể chạm ngưỡng scheduler rất nhanh.

Ngoài 7 critical services, capacity còn bị ảnh hưởng bởi:

- `load-generator`
- stateful workloads như `kafka`, `postgresql`, `valkey-cart`
- observability stack như `grafana`, `prometheus`, `jaeger`, `opensearch`, `otel-collector`
- system pods trong `kube-system`

Do đó review capacity cần tính toàn cluster, không chỉ 7 services trong REL-01.

---

## 6. Recommendation Từ CDO08

CDO08 đề xuất CDO04 review theo hướng quyết định **node scaling strategy** trước khi rollout lại REL-01/PDB/load test. Các phương án thực tế như sau.

### Option A - Scale Managed Node Group / ASG từ 2 lên 3 nodes

Đây là option ngắn hạn, ít thay đổi kiến trúc và có thể dùng nếu cần unblock mandate/load test nhanh.

**Lợi ích:**

- Tăng thêm khoảng `+1930m CPU allocatable` và khoảng `+7Gi memory allocatable`.
- Giảm rủi ro `Pending / Insufficient cpu` khi rollout, tăng replicas, chạy load-generator hoặc apply PDB.
- Ít đụng app logic; pod cũ không bị restart chỉ vì thêm node.
- Dễ rollback hơn Karpenter: giảm desired capacity từ 3 về 2 sau khi hết test window nếu cần.

**Rủi ro / trade-off:**

- Tăng fixed EC2/EBS cost trong thời gian node thứ 3 chạy.
- Node mới vẫn chạy thêm DaemonSet như `aws-node`, `otel-collector-agent`, nên không trống 100%.
- Cần verify node join, subnet/IP, security group/IAM và scheduling sau khi scale.

**Cost estimate cho 1 node `t3.large` thêm trong `us-east-1`:**

| Hạng mục                       | Công thức                         | Estimate         |
| ------------------------------ | --------------------------------- | ---------------- |
| EC2 `t3.large` Linux On-Demand | `$0.0832/hour * 168h`             | `~$13.98/week`   |
| EBS root volume gp3 20GiB      | `$0.08/GB-month * 20GB * 168/730` | `~$0.37/week`    |
| **Tổng thêm 1 node**           | EC2 + root EBS                    | **~$14.35/week** |

Nguồn pricing cần CDO04 xác nhận lại tại thời điểm duyệt:

- AWS EC2 On-Demand Pricing: https://aws.amazon.com/ec2/pricing/on-demand/
- AWS EBS Pricing: https://aws.amazon.com/ebs/pricing/

Ghi chú: estimate chưa gồm usage-based cost như CloudWatch/telemetry/log/trace, data transfer, T3 surplus CPU credits hoặc thay đổi cấu hình root volume thực tế.

### Option B - Dùng Karpenter để autoscale worker nodes

Đây cũng là một hướng xử lý CPU headroom, nhưng phức tạp hơn Option A. Karpenter phù hợp nếu TF4 muốn node scaling tự động thay vì tăng fixed node count thủ công.

**Karpenter giúp gì:**

- Tự tạo node mới khi pod bị `Pending` vì thiếu CPU/memory request.
- Chọn instance type phù hợp với nhu cầu thực tế của pod, thay vì cố định toàn bộ node group một loại instance.
- Có thể scale down hoặc consolidate node dư khi workload giảm, tránh giữ node rỗng chạy lâu.
- Có thể đặt giới hạn tổng CPU/memory hoặc instance family để tránh autoscale vượt ngân sách.

**Cost có thể tối ưu hơn như nào:**

- Với Managed Node Group / ASG, nếu scale từ 2 lên 3 nodes thì node thứ 3 thường chạy cố định trong toàn bộ test window hoặc cho đến khi team giảm lại desired capacity.
- Với Karpenter, node có thể chỉ được tạo khi thật sự có pod cần schedule và được thu gọn khi không còn pod cần node đó.
- Nếu workload spike ngắn, Karpenter có thể giảm thời gian trả tiền cho node dư so với việc giữ fixed 3 nodes nhiều giờ.
- Karpenter cũng có thể chọn instance vừa đủ hơn cho workload nếu cấu hình `NodePool` cho phép nhiều instance type phù hợp, thay vì chỉ dùng một size cố định.

**Ý tưởng áp dụng:**

1. Cài Karpenter controller vào namespace riêng, ví dụ `karpenter`.
2. Tạo IAM role/service account cho Karpenter quản lý EC2 node lifecycle.
3. Tạo `EC2NodeClass` để chỉ định subnet, security group, AMI family, instance profile.
4. Tạo `NodePool` với guardrail:
    - chỉ cho phép instance family/type đã được CDO04 duyệt,
    - ưu tiên `on-demand` trước; `spot` chỉ dùng khi có policy rõ,
    - đặt tổng CPU/memory limit để tránh vượt ngân sách,
    - bật consolidation/disruption policy để tự thu gọn node dư.
5. Test bằng workload Pending có request rõ ràng.
6. Verify node claim, pod scheduling, cost và scale-down behavior.

**Trade-off:**

- Linh hoạt hơn fixed node count và có thể tối ưu cost tốt hơn nếu cấu hình đúng.
- Phức tạp hơn scale Managed Node Group / ASG vì cần review IAM, subnet/security group, NodePool limits, disruption policy và cost guardrail.
- Nếu mandate đang gấp, cần cân nhắc thời gian implement/review trước khi chọn hướng này.

**CDO08 recommendation:**

- Option A nhanh hơn để unblock REL-01/PDB/load test: scale Managed Node Group / ASG từ 2 lên 3 nodes.
- Option B linh hoạt hơn và có thể tối ưu cost tốt hơn: dùng Karpenter, nhưng cần nhiều thời gian review/implement hơn.

---

## 7. Quyết Định Cần CDO04 Xác Nhận

CDO04 vui lòng chọn hướng xử lý capacity trước khi CDO08 rollout lại REL-01:

```text
CDO04 decision:
[ ] Approve scale Managed Node Group / ASG từ 2 lên 3 nodes trước rollout.
[ ] Giữ 2 nodes, chấp nhận rủi ro scheduler headroom mỏng.
[ ] Needs Info: cần thêm evidence trước khi quyết định.
[ ] Hướng khác: ______________________________

Ghi chú / điều kiện approve:
- Người duyệt:
- Ngày duyệt:
- Điều kiện:
```

CDO08 cần CDO04 xác nhận thêm nếu chọn scale node:

- Thời gian được phép giữ node thứ 3.
- Cost budget cho node thứ 3 trong test/mandate window.
- Có cần scale down về 2 nodes sau khi test xong không.

---

## 8. Final Summary

```md
Actual CPU hiện tại thấp, nhưng scheduler capacity đang căng do CPU requests. Node `ip-10-0-10-231` đã dùng 93% CPU requests, node `ip-10-0-11-40` dùng 80%. Event gần đây xác nhận pod load-generator từng bị `FailedScheduling` do `Insufficient cpu`.

Tăng 7 critical services từ 1 lên 2 replicas dự kiến thêm khoảng 420m CPU request và 512Mi memory request. Tổng CPU request headroom hiện chỉ khoảng 505m, nên có thể fit trong điều kiện phân phối đều nhưng margin rất mỏng. Rolling update, surge pod, load-generator hoặc observability workload có thể làm pod Pending.

CDO08 đề xuất hướng ngắn hạn là scale worker node từ 2 lên 3 bằng Managed Node Group / ASG để có scheduler headroom trước khi rollout REL-01/PDB/load test. Cost estimate cho 1 node `t3.large` thêm trong `us-east-1` khoảng ~$14.35/week, chưa gồm usage-based cost. Karpenter là phương án linh hoạt hơn, nhưng cần cân nhắc thời gian review/implement nếu mandate đang gấp.
```
