# Báo cáo Bằng chứng Worker Node Autoscaling bằng Karpenter (CDO08)

Tài liệu này cung cấp bằng chứng runtime rằng Karpenter đã được triển khai thành công trên EKS cluster `techx-tf4-cluster` và đã tự động provision thêm worker node khi workload trong namespace `techx-tf4` gặp tình trạng thiếu CPU scheduler headroom.

Phạm vi của thay đổi này là baseline worker node autoscaling cho TF4. Tài liệu này xác nhận Karpenter controller, CRD, NodePool, EC2NodeClass và NodeClaim đã hoạt động. Tài liệu này không xác nhận HPA, application-level autoscaling, Spot capacity hoặc tối ưu chi phí dài hạn.

---

## 1. Xác thực Thành phần & Phạm vi

Karpenter được triển khai để xử lý bài toán pod `Pending` do thiếu CPU trên 2 worker nodes baseline.

- **Cluster**: `techx-tf4-cluster`
- **Region**: `us-east-1`
- **Application namespace**: `techx-tf4`
- **Karpenter namespace**: `kube-system`
- **NodePool**: `techx-general`
- **EC2NodeClass**: `techx-general`
- **Capacity type**: `on-demand`
- **Allowed instance types**: `t3.large`, `t3a.large`
- **NodePool CPU limit**: `4`

Karpenter được quản lý qua Terraform + CI/CD:

- Terraform tạo IAM/IRSA role, node role và Helm release `karpenter`.
- GitHub Actions apply `NodePool` và `EC2NodeClass` sau khi CRD Karpenter sẵn sàng.

---

## 2. Xác thực Karpenter Controller

Karpenter controller đã được deploy thành công trong namespace `kube-system`.

```bash
$ kubectl -n kube-system get deploy karpenter
NAME        READY   UP-TO-DATE   AVAILABLE   AGE
karpenter   2/2     2            2           46m
```

Trạng thái pod controller:

```bash
$ kubectl -n kube-system get pods -l app.kubernetes.io/name=karpenter -o wide
NAME                         READY   STATUS    RESTARTS   AGE   IP            NODE                          NOMINATED NODE   READINESS GATES
karpenter-5c5f54d586-rjssq   1/1     Running   0          46m   10.0.10.87    ip-10-0-10-231.ec2.internal   <none>           <none>
karpenter-5c5f54d586-wbv8x   1/1     Running   0          46m   10.0.11.250   ip-10-0-11-40.ec2.internal    <none>           <none>
```

Kết luận: Karpenter controller đang chạy ổn định, `READY 2/2`, hai pod controller được phân bố trên 2 worker nodes baseline.

---

## 3. Xác thực Karpenter CRD

Các CRD cần thiết của Karpenter đã được cài vào cluster.

```powershell
$ kubectl get crd | Select-String -Pattern "karpenter|nodepool|nodeclaim|ec2nodeclass"

ec2nodeclasses.karpenter.k8s.aws                2026-07-14T16:31:24Z
nodeclaims.karpenter.sh                         2026-07-14T16:31:24Z
nodeoverlays.karpenter.sh                       2026-07-14T16:31:24Z
nodepools.karpenter.sh                          2026-07-14T16:31:24Z
```

Kết luận: Cluster đã nhận các custom resources cần thiết để Karpenter quản lý capacity.

---

## 4. Xác thực NodePool và EC2NodeClass

NodePool `techx-general` đã được tạo và ở trạng thái `Ready=True`.

```bash
$ kubectl get nodepool
NAME            NODECLASS       NODES   READY   AGE
techx-general   techx-general   1       True    2m2s
```

EC2NodeClass `techx-general` cũng đã sẵn sàng.

```bash
$ kubectl get ec2nodeclass
NAME            READY   AGE
techx-general   True    2m9s
```

Ý nghĩa:

- `NodePool READY=True`: Karpenter có policy hợp lệ để provision node.
- `EC2NodeClass READY=True`: Karpenter tìm được cấu hình AWS hợp lệ, gồm subnet/security group/AMI/node role.
- `NODES=1`: NodePool đã provision ít nhất một node mới.

---

## 5. Xác thực NodeClaim và Worker Node Mới

Karpenter đã tạo `NodeClaim` mới để đáp ứng pod không schedule được vì thiếu CPU.

```bash
$ kubectl get nodeclaims
```

Kết quả runtime xác nhận có NodeClaim thuộc NodePool `techx-general`, instance type `t3a.large`, capacity `on-demand`, zone `us-east-1b`, trạng thái `READY=True`, gắn với node `ip-10-0-11-251.ec2.internal`.

Danh sách nodes sau khi Karpenter scale out:

```bash
$ kubectl get nodes
NAME                          STATUS   ROLES    AGE     VERSION
ip-10-0-10-231.ec2.internal   Ready    <none>   5d16h   v1.34.9-eks-7d6f6ec
ip-10-0-11-251.ec2.internal   Ready    <none>   40s     v1.34.9-eks-8f14419
ip-10-0-11-40.ec2.internal    Ready    <none>   5d16h   v1.34.9-eks-7d6f6ec
```

Kết luận: Cluster đã tăng từ 2 worker nodes baseline lên 3 worker nodes. Node mới `ip-10-0-11-251.ec2.internal` do Karpenter provision, thuộc NodePool `techx-general`, instance type `t3a.large`, capacity `on-demand`.

---

## 6. Xác thực Pod Pending do Thiếu CPU Được Karpenter Xử lý

Trước khi Karpenter provision node mới, workload không schedule được vì 2 nodes baseline thiếu CPU request headroom.

```text
Warning  FailedScheduling  default-scheduler
0/2 nodes are available: 2 Insufficient cpu.
```

Sau đó Karpenter tạo NodeClaim mới và node mới join cluster.

```text
NodeClaim Ready
Node ip-10-0-11-251.ec2.internal Ready
```

Các pod trước đó bị kẹt vì thiếu CPU được scheduler đặt lại và chuyển sang Running.

```text
load-generator-c95c8bbd5-ll9q6  1/1  Running
cart-586b7ddff6-qsnkv           1/1  Running
checkout-7ddf4fdbdc-2wr8x       1/1  Running
```

Kết luận: Đây là bằng chứng runtime chính cho thấy Karpenter đã phản ứng với tình trạng `Insufficient cpu`, tạo node mới và giúp các pod được schedule thành công.

---

## 7. Xác thực Trạng thái Workload Sau Scale Out

Sau khi node mới được tạo, toàn bộ pod trong namespace `techx-tf4` đều ở trạng thái `Running`.

```bash
$ kubectl -n techx-tf4 get pods
NAME                               READY   STATUS    RESTARTS   AGE
accounting-67d4d78bfb-5mqdz        1/1     Running   0          171m
ad-d4cbf46d7-99pq8                 1/1     Running   0          171m
cart-586b7ddff6-qsnkv              1/1     Running   0          30m
checkout-7ddf4fdbdc-2wr8x          1/1     Running   0          30m
currency-77cdc749f6-2njtl          1/1     Running   0          171m
email-b4dc94555-mpj8x              1/1     Running   0          171m
flagd-64c45658df-hwhrj             1/1     Running   0          11h
fraud-detection-576b88975f-2vkq5   1/1     Running   0          171m
frontend-b97bc56cb-296np           1/1     Running   0          30m
frontend-proxy-8f4796d4b-fwdgc     1/1     Running   0          171m
image-provider-58869f7796-ffpbr    1/1     Running   0          171m
kafka-c5c94b88c-n7qc7              1/1     Running   0          118m
llm-6c96948c64-dnz8f               1/1     Running   0          171m
load-generator-c95c8bbd5-ll9q6     1/1     Running   0          30m
payment-567ddfd8cd-jqj4x           1/1     Running   0          30m
postgresql-879c5bd4-gp45d          1/1     Running   0          14h
product-catalog-77b55f7bdc-fg9qm   1/1     Running   0          30m
product-reviews-5bb99b6c75-j296c   1/1     Running   0          30m
quote-74dd89d8df-gsq6d             1/1     Running   0          171m
recommendation-78948dd47d-zqjdv    1/1     Running   0          30m
shipping-95bcf4675-lwz4c           1/1     Running   0          106m
valkey-cart-6b478c4cf6-8w4vt       1/1     Running   0          155m
```

Kết luận: Karpenter đã giải quyết phần worker node capacity. Tại thời điểm xác thực cuối, không còn pod `Pending`, `Init`, `CrashLoopBackOff` hoặc `ImagePullBackOff` trong namespace ứng dụng.

---

## 8. Rủi ro & Giới hạn Hiện tại

Karpenter baseline đã hoạt động, nhưng vẫn còn các giới hạn cần theo dõi:

- NodePool hiện chỉ giới hạn theo tổng CPU `4`, chưa có budget/cost alert riêng cho Karpenter.
- NodePool dùng On-Demand `t3.large` và `t3a.large`, chưa tối ưu Spot hoặc mixed capacity.
- EC2NodeClass hiện dùng `al2023@latest`; sau mandate nên pin AMI alias/version đã test để giảm drift.
- Karpenter xử lý node capacity, không thay thế HPA hoặc application-level scaling.
- Karpenter không tự sửa lỗi dependency như Valkey/Kafka/PostgreSQL readiness.
- Consolidation cần theo dõi với PDB để tránh disruption khi node dư bị thu gọn.

---

## 9. Rollback Plan

Nếu Karpenter gây scale ngoài ý muốn hoặc ảnh hưởng runtime:

1. Xóa NodePool để dừng việc provision node mới:

```bash
kubectl delete nodepool techx-general
```

2. Kiểm tra node do Karpenter tạo:

```bash
kubectl get nodes -l karpenter.sh/nodepool=techx-general
kubectl get nodeclaims
```

3. Nếu cần dọn node Karpenter, drain/delete node sau khi xác nhận workload an toàn:

```bash
kubectl drain <karpenter-node-name> --ignore-daemonsets --delete-emptydir-data
kubectl delete node <karpenter-node-name>
```

4. Nếu cần rollback controller, revert PR Karpenter hoặc uninstall Helm release:

```bash
helm -n kube-system uninstall karpenter
```

Ghi chú: không nên xóa node khi chưa kiểm tra pod đang chạy trên node đó, đặc biệt nếu PDB/replica chưa hoàn chỉnh.

---

## 10. Kết luận

Karpenter worker node autoscaling baseline đã được xác thực thành công trên runtime EKS:

- Karpenter controller chạy `2/2` trong namespace `kube-system`.
- CRD `NodePool`, `NodeClaim`, `EC2NodeClass` đã tồn tại.
- `NodePool techx-general` và `EC2NodeClass techx-general` đều `Ready=True`.
- Karpenter đã tạo NodeClaim mới cho NodePool `techx-general`.
- Cluster đã scale từ 2 lên 3 worker nodes bằng node mới `ip-10-0-11-251.ec2.internal`.
- Pod trước đó bị `FailedScheduling ... Insufficient cpu` đã được schedule thành công sau khi node mới xuất hiện.
- Toàn bộ pod trong namespace `techx-tf4` đã ở trạng thái `1/1 Running`.

Kết luận: thay đổi này đáp ứng mục tiêu baseline worker node autoscaling, giúp TF4 không còn phụ thuộc hoàn toàn vào thao tác scale node thủ công khi scheduler thiếu CPU headroom.
---
## 🛡️ CDO-07 Audit Approval Sign-Off
- **Trạng thái:** ✅ APPROVED / PASS
- **Người kiểm duyệt:** CDO-07 (Đội ngũ Auditability)
- **Ngày thực hiện:** 2026-07-16
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.