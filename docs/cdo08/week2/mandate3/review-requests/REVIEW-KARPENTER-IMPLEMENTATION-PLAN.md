# [REVIEW REQUEST] CDO08 — Karpenter Implementation Plan cho Worker Node Autoscaling

| Thông tin                   | Giá trị                                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Từ                          | CDO08                                                                                                             |
| Đến                         | TF4 Leads / PM / CDO04                                                                                            |
| Backlog liên quan           | `CDO08-REL-01`, `CDO08-REL-12`, `MANDATE-03`                                                                      |
| Mục tiêu review             | Xác nhận hướng triển khai Karpenter bằng Terraform + CI/CD để xử lý scheduler headroom và worker node autoscaling |
| PR implementation liên quan | `feat(cdo08): add karpenter autoscaling baseline`                                                                 |
| Ngày gửi                    | 2026-07-14                                                                                                        |
| Deadline approve            | **2026-07-14 (trước mandate/load test tiếp theo)**                                                                |

---

## 1. Mục tiêu

Triển khai Karpenter cho EKS cluster `techx-tf4-cluster` để giải quyết vấn đề thiếu scheduler headroom khi rollout REL-01, PDB, load test hoặc mandate có workload tăng đột biến.

Hướng này được chọn vì production-like hơn so với scale Managed Node Group / ASG thủ công:

- Pod thiếu CPU/memory request thì Karpenter tự provision node phù hợp.
- Workload giảm thì có thể consolidate/scale down node dư nếu cấu hình disruption/consolidation đúng.
- Có thể đặt cost guardrail bằng `NodePool.limits`, instance type/family allowlist và capacity type.
- Giảm thao tác thủ công kiểu scale node lên rồi nhớ scale xuống.

Managed Node Group / ASG 2 -> 3 nodes vẫn là fallback nếu cần unblock rất nhanh, nhưng không phải hướng chính nếu mục tiêu là cải thiện vận hành.

## 2. Cơ chế hoạt động cần nắm

Karpenter không scale theo CPU usage trực tiếp như HPA. Karpenter quan sát các pod mà Kubernetes scheduler không schedule được, ví dụ `Pending` do `Insufficient cpu`, rồi tạo node mới phù hợp với yêu cầu của pod.

Luồng chính:

1. Workload tạo pod mới hoặc rollout tạo surge pod.
2. Scheduler không đặt được pod vì thiếu CPU/memory/request hoặc constraint.
3. Karpenter đọc unschedulable pod.
4. Karpenter chọn instance type phù hợp theo `NodePool` và `EC2NodeClass`.
5. Karpenter tạo EC2 node mới.
6. Node join cluster.
7. Pending pod được schedule lên node mới.
8. Khi workload giảm, Karpenter có thể consolidate node dư nếu policy cho phép.

## 3. Evidence hiện tại của TF4

Runtime đã có evidence thiếu scheduler headroom:

```text
FailedScheduling pod/load-generator-549dd99956-g6pdb
0/2 nodes are available: 2 Insufficient cpu.
```

Node allocatable hiện tại:

```text
ip-10-0-10-231.ec2.internal   CPU_ALLOC 1930m
ip-10-0-11-40.ec2.internal    CPU_ALLOC 1930m
```

Critical service baseline nếu tăng 7 services từ 1 lên 2 replicas cần thêm khoảng:

```text
+420m CPU request
+512Mi memory request
```

Vấn đề chính không phải actual CPU đang cao, mà là scheduler capacity theo `resources.requests` đã mỏng. Vì vậy Karpenter phù hợp hơn scale thủ công nếu muốn hệ thống tự phản ứng khi pod Pending.

## 4. Phạm vi triển khai

Triển khai Karpenter để xử lý worker node autoscaling cho namespace/app workload TF4.

Scope lần đầu đang được triển khai qua PR `feat(cdo08): add karpenter autoscaling baseline`:

- Dùng On-Demand trước, chưa bật Spot.
- Chỉ cho phép `t3.large` và `t3a.large`.
- Đặt `NodePool.limits` để tránh vượt ngân sách.
- Chỉ dùng Karpenter để add capacity mới, chưa migrate toàn bộ workload khỏi Managed Node Group cũ.
- Karpenter controller phải chạy trên node không do Karpenter quản lý, tức giữ Managed Node Group hiện tại làm baseline.
- Không cài tay bằng CLI trên máy cá nhân. IAM/controller/NodePool được đưa vào Terraform + GitHub Actions để có review, audit trail và rollback qua Git.

## 5. Điều kiện trước khi apply

### 5.1 Quyền AWS/IAM

Cần người có quyền IAM/EKS/EC2 hỗ trợ:

- Tạo IAM role/policy cho Karpenter controller.
- Tạo IAM role cho node do Karpenter provision.
- Cho phép Karpenter gọi EC2 APIs để launch/terminate instance.
- Gắn role/node identity để node mới join EKS cluster.
- Nếu dùng IRSA thì cần OIDC provider của cluster.
- Nếu dùng EKS Pod Identity thì cần `eks-pod-identity-agent` và association tương ứng.

### 5.2 Tag hoặc selector cho subnet/security group

Karpenter cần biết subnet và security group nào được phép dùng cho node mới.

Có hai hướng:

- Tag subnet/security group bằng `karpenter.sh/discovery: techx-tf4-cluster`.
- Hoặc dùng selector cụ thể theo tag hiện có trong `EC2NodeClass`.

Cần xác nhận với CDO04/IAM trước khi tag resource, vì tag discovery ảnh hưởng đến resource mà Karpenter có thể chọn.

### 5.3 Baseline node group

Phải giữ ít nhất một Managed Node Group hoặc Fargate profile để chạy Karpenter controller. Không nên để Karpenter controller chạy trên node do chính Karpenter quản lý.

Với TF4 hiện tại có 2 worker nodes từ baseline node group, có thể dùng node group này để chạy controller.

## 6. Thiết kế NodePool đang triển khai

### 6.1 Nguyên tắc

- Ưu tiên `on-demand` để ổn định trong mandate.
- Chỉ dùng Linux/amd64.
- Giới hạn instance family/type để tránh cost bất ngờ.
- Đặt tổng CPU limit nhỏ trước, ví dụ chỉ đủ cho 1-2 node mới.
- Bật consolidation để node dư có thể được thu gọn.
- AMI hiện dùng `al2023@latest` để tương thích nhanh với EKS 1.34 và AL2023 node hiện tại; sau mandate nên pin AMI alias/version đã test để giảm drift.

### 6.2 NodePool trong PR

File: `deploy/karpenter/nodepool.yaml`

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
    name: techx-general
spec:
    template:
        spec:
            requirements:
                - key: kubernetes.io/arch
                  operator: In
                  values: ["amd64"]
                - key: kubernetes.io/os
                  operator: In
                  values: ["linux"]
                - key: karpenter.sh/capacity-type
                  operator: In
                  values: ["on-demand"]
                - key: node.kubernetes.io/instance-type
                  operator: In
                  values: ["t3.large", "t3a.large"]
            nodeClassRef:
                group: karpenter.k8s.aws
                kind: EC2NodeClass
                name: techx-general
            expireAfter: 720h
    limits:
        cpu: "4"
    disruption:
        consolidationPolicy: WhenEmptyOrUnderutilized
        consolidateAfter: 5m
```

Giải thích nhanh:

- `capacity-type: on-demand`: ổn định hơn Spot cho mandate.
- `t3.large`, `t3a.large`: bắt đầu gần với node hiện tại để dễ kiểm soát cost.
- `limits.cpu: "4"`: giới hạn Karpenter không provision quá nhiều CPU ngoài baseline.
- `consolidateAfter: 5m`: tránh scale down quá nhanh khi rollout/load test còn dao động.

Nếu CDO04 muốn tiết kiệm hơn, có thể mở rộng instance family/type sau khi test, nhưng nên giữ allowlist rõ ràng.

## 7. EC2NodeClass đang triển khai

File: `deploy/karpenter/ec2nodeclass.yaml`

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
    name: techx-general
spec:
    role: karpenter-node-techx-tf4-cluster
    amiSelectorTerms:
        - alias: al2023@latest
    subnetSelectorTerms:
        - tags:
              karpenter.sh/discovery: techx-tf4-cluster
    securityGroupSelectorTerms:
        - tags:
              karpenter.sh/discovery: techx-tf4-cluster
```

Role `karpenter-node-techx-tf4-cluster` được tạo bởi Terraform module Karpenter. Subnet và security group được chọn bằng discovery tag `karpenter.sh/discovery: techx-tf4-cluster`.

Ghi chú: `al2023@latest` là lựa chọn nhanh cho mandate để khớp AL2023/EKS 1.34 hiện tại. Sau khi mandate ổn, nên pin AMI alias/version đã test.

## 8. Các bước triển khai qua CI/CD

### Step 0 - Precheck

```bash
kubectl get ns
kubectl get nodes -o wide
kubectl get pods -A | Select-String -Pattern "Pending|FailedScheduling|CrashLoopBackOff|ImagePullBackOff|Error"
kubectl get events -A --sort-by=.lastTimestamp | Select-String -Pattern "Insufficient cpu|FailedScheduling|Pending"
aws sts get-caller-identity
aws eks describe-cluster --name techx-tf4-cluster --region us-east-1
```

Mục tiêu:

- Xác nhận cluster reachable.
- Xác nhận baseline node group đang chạy.
- Xác nhận có evidence thiếu CPU nếu cần demo Karpenter.

### Step 1 - Chuẩn bị IAM/role/tag bằng Terraform

File liên quan:

- `infra/terraform/karpenter.tf`
- `infra/terraform/providers.tf`
- `infra/terraform/vpc.tf`
- `infra/terraform/eks.tf`
- `infra/terraform/outputs.tf`

Terraform thực hiện:

- Tạo IAM role cho Karpenter controller qua IRSA.
- Tạo IAM role cho node do Karpenter provision.
- Tạo EKS access entry cho node role để node mới join cluster.
- Thêm discovery tag cho private subnets.
- Thêm discovery tag cho cluster security group.
- Cấu hình Helm provider dùng EKS cluster auth.

### Step 2 - Cài Karpenter controller bằng Terraform Helm release

File: `infra/terraform/karpenter.tf`

Terraform cài Helm chart:

- Chart: `oci://public.ecr.aws/karpenter/karpenter`
- Version: `1.14.0`
- Namespace: `kube-system`
- ServiceAccount annotation: `eks.amazonaws.com/role-arn = module.karpenter.iam_role_arn`
- Controller requests: `500m CPU`, `512Mi memory`
- Controller limits: `1 CPU`, `1Gi memory`

### Step 3 - Apply EC2NodeClass và NodePool bằng GitHub Actions

File workflow: `.github/workflows/terraform-apply.yaml`

Workflow chạy khi có thay đổi:

- `infra/terraform/**`
- `deploy/karpenter/**`
- `.github/workflows/terraform-apply.yaml`

Sau `terraform apply`, workflow:

```bash
aws eks update-kubeconfig --region "${AWS_REGION}" --name "$(terraform output -raw cluster_name)"
kubectl wait --for condition=Established crd/nodepools.karpenter.sh --timeout=120s
kubectl wait --for condition=Established crd/ec2nodeclasses.karpenter.k8s.aws --timeout=120s
kubectl apply -f ../../deploy/karpenter
```

Lý do không dùng Terraform `kubernetes_manifest` cho NodePool ngay trong cùng apply: `NodePool` và `EC2NodeClass` là CRD mới được Helm chart tạo ra. Nếu Terraform plan/apply manifest trước khi CRD tồn tại, có thể lỗi schema/resource mapping. Vì vậy workflow đợi CRD `Established` rồi mới apply manifest.

### Step 4 - Test scale-up bằng workload có request rõ ràng

Tạo workload test nhỏ để ép Pending nếu cluster thiếu CPU:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
    name: karpenter-inflate
    namespace: techx-tf4
spec:
    replicas: 0
    selector:
        matchLabels:
            app: karpenter-inflate
    template:
        metadata:
            labels:
                app: karpenter-inflate
        spec:
            terminationGracePeriodSeconds: 0
            containers:
                - name: pause
                  image: public.ecr.aws/eks-distro/kubernetes/pause:3.7
                  resources:
                      requests:
                          cpu: "1"
                          memory: 128Mi
```

Test:

```bash
kubectl -n techx-tf4 apply -f karpenter-inflate.yaml
kubectl -n techx-tf4 scale deploy/karpenter-inflate --replicas=3
kubectl -n techx-tf4 get pods -o wide
kubectl get nodes -o wide
kubectl get nodeclaims
kubectl -n kube-system logs -l app.kubernetes.io/name=karpenter -c controller --tail=100
```

Expected:

- Ban đầu có thể có pod Pending.
- Karpenter tạo NodeClaim.
- EC2 node mới join cluster.
- Pod Pending chuyển sang Running trên node mới.

### Step 5 - Test consolidation/scale-down

```bash
kubectl -n techx-tf4 scale deploy/karpenter-inflate --replicas=0
kubectl -n techx-tf4 get pods
kubectl get nodeclaims
kubectl get nodes -o wide
kubectl -n kube-system logs -l app.kubernetes.io/name=karpenter -c controller --tail=100
```

Expected:

- Sau `consolidateAfter`, node dư có thể bị terminate nếu không còn workload cần giữ.
- Việc terminate phải tôn trọng PDB, pod eviction và disruption policy.

### Step 6 - Apply lại REL-01 / PDB sau khi Karpenter ổn

Sau khi Karpenter scale-up/scale-down OK:

1. Rollout lại critical services lên 2 replicas.
2. Verify `2/2 READY`.
3. Check pod spread.
4. Apply PDB nếu đã được approve.
5. Chạy mandate/load test.
6. Theo dõi Karpenter node claims, node count, pending pods, cost.

## 9. Verification checklist

### Karpenter controller

```bash
kubectl -n kube-system get deploy karpenter
kubectl -n kube-system get pods -l app.kubernetes.io/name=karpenter
kubectl -n kube-system logs -l app.kubernetes.io/name=karpenter -c controller --tail=100
```

### NodePool / NodeClaim

```bash
kubectl get nodepool
kubectl describe nodepool techx-general
kubectl get nodeclaims
kubectl describe nodeclaim <nodeclaim-name>
```

### Node scale-up

```bash
kubectl get nodes -o wide
kubectl get events -A --sort-by=.lastTimestamp | Select-String -Pattern "karpenter|NodeClaim|Launched|Registered|Insufficient cpu|FailedScheduling"
```

### App safety

```bash
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get deploy frontend-proxy frontend checkout cart payment shipping product-catalog
kubectl -n techx-tf4 rollout status deploy/frontend-proxy
kubectl -n techx-tf4 rollout status deploy/frontend
kubectl -n techx-tf4 rollout status deploy/checkout
kubectl -n techx-tf4 rollout status deploy/cart
kubectl -n techx-tf4 rollout status deploy/payment
kubectl -n techx-tf4 rollout status deploy/shipping
kubectl -n techx-tf4 rollout status deploy/product-catalog
```

### Resource/cost signal

```bash
kubectl top nodes
kubectl -n techx-tf4 top pods
aws ec2 describe-instances --region us-east-1 --filters "Name=tag:karpenter.sh/nodepool,Values=techx-general"
```

## 10. Rollback / safety

Nếu Karpenter install lỗi:

```bash
helm -n kube-system uninstall karpenter
```

Nếu NodePool gây scale ngoài ý muốn:

```bash
kubectl delete nodepool techx-general
```

Nếu cần xóa node do Karpenter tạo:

```bash
kubectl get nodes -l karpenter.sh/nodepool
kubectl delete node <karpenter-node-name>
```

Lưu ý: chỉ xóa node Karpenter sau khi hiểu pod nào đang chạy trên node đó. Karpenter sẽ drain node và terminate instance theo cơ chế của nó, nhưng vẫn cần kiểm tra PDB/disruption để tránh gián đoạn service.

Nếu mandate cần fallback nhanh:

- Tạm scale Managed Node Group / ASG lên 3 nodes.
- Giữ Karpenter implementation lại sau khi hết window gấp.
- Ghi rõ lý do fallback trong Jira/GitHub evidence.

## 11. Rủi ro cần chú ý

- IAM quá rộng có thể gây rủi ro security/cost.
- Tag subnet/security group sai có thể làm Karpenter chọn sai network path.
- NodePool limit quá cao có thể vượt ngân sách.
- Consolidation quá aggressive có thể gây disruption không mong muốn.
- PDB quá chặt có thể làm Karpenter không drain được node dư.
- AMI `@latest` có thể đưa AMI chưa test vào production-like cluster.
- Controller không nên chạy trên node do Karpenter quản lý.

## 12. Kết luận

Karpenter là hướng phù hợp nếu TF4 muốn xử lý capacity theo cách production-like hơn scale node thủ công. Với evidence `Insufficient cpu`, bài toán hiện tại không chỉ là thêm một node, mà là cần cơ chế tự động provision capacity khi scheduler không còn đủ chỗ đặt pod.

Đề xuất triển khai theo hướng an toàn:

1. Giữ Managed Node Group hiện tại làm baseline và nơi chạy Karpenter controller.
2. Cài Karpenter với IAM/tag/guardrail rõ ràng.
3. Tạo NodePool On-Demand giới hạn nhỏ trước.
4. Test scale-up bằng workload có request rõ ràng.
5. Test scale-down/consolidation.
6. Sau khi ổn mới rollout lại REL-01/PDB/load test.

## 13. Official references

- Karpenter Getting Started: https://karpenter.sh/docs/getting-started/getting-started-with-karpenter/
- Karpenter NodePools: https://karpenter.sh/docs/concepts/nodepools/
- Karpenter NodeClasses / EC2NodeClass: https://karpenter.sh/docs/concepts/nodeclasses/
- Karpenter Disruption: https://karpenter.sh/docs/concepts/disruption/
- AWS EKS Karpenter Best Practices: https://docs.aws.amazon.com/eks/latest/best-practices/karpenter.html
