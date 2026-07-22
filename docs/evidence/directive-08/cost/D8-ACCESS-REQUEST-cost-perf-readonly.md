# [D8-ACCESS-REQUEST-01] Yêu cầu quyền đọc bổ sung cho D8-COST-02 / D8-COST-03

- Trạng thái: **PARTIALLY GRANTED (2026-07-22, kiểm tra lại sau khi đổi sang role `TF4-CostPerfReadOnlyAlerting`)** — `kafka:ListClusters`/`DescribeCluster` và RBAC `nodeclaims` (get/list) đã được cấp; `kafka:ListNodes`/`GetBootstrapBrokers` và RBAC `nodepools` **vẫn còn bị từ chối**; CUR (gap #3) vẫn chưa cấu hình, không đổi. Xem mục 3/4/7 để biết chi tiết phần nào đã xong, phần nào còn mở.
- Reporter: Tuấn — CDO-04 Performance Efficiency & Cost Optimization
- Owner cần điều phối: CDO-08 / Platform team (chủ sở hữu IAM Permission Set và Kubernetes RBAC của cluster `techx-tf4-cluster`)
- Priority: P1 — chặn acceptance criteria của `D8-COST-02` (C0G-71) và `D8-COST-03` (C0G-72)
- Ngày gửi: 2026-07-22
- AWS account/region: `511825856493` / `us-east-1`
- Cluster: `techx-tf4-cluster`, namespace `techx-tf4`
- Roles đã test: `TF4-BaseReadOnly`, `TF4-CostPerfReadOnlyAlerting`
- Principal: `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86/tuan` (và `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7/tuan` cho blocker #2)

---

## 1. Mục đích

Ticket này chỉ xin quyền **đọc** (list/describe/get) trong phạm vi CDO-04 (Performance Efficiency + Cost Optimization), phục vụ trực tiếp:

- `D8-COST-02` (C0G-71) — Verify EKS Capacity After Removing Self-Hosted Data Pods: cần đo Karpenter NodeClaim lifetime + consolidation evidence.
- `D8-COST-03` (C0G-72) — Reconcile Managed Data Migration Cost with AWS Billing: cần tách riêng cost MSK theo yêu cầu "Required Separation" của ticket.

Không yêu cầu quyền provisioning, network, security, write vào cluster, hay bất kỳ hành động nào ngoài phạm vi CDO-04 (theo đúng "Out of Scope" của `epic8-task.md`: CDO-04 không chịu trách nhiệm provisioning/networking/security).

---

## 2. Preflight đã thực hiện

```text
aws sts get-caller-identity
Account: 511825856493
Role:    AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86
User:    tuan
```

Các quyền read-only khác trong cùng phạm vi (Cost Explorer, AWS Budgets, RDS describe, ElastiCache describe, EC2 describe) đã hoạt động bình thường dưới role này — nghĩa là đây là gap có chủ đích/thiếu sót cụ thể, không phải lỗi SSO/token hết hạn.

---

## 3. Blocker #1 — MSK read-only (chặn `D8-COST-03`) — **PARTIALLY GRANTED**

**Cập nhật 2026-07-22 (sau khi đổi sang role `TF4-CostPerfReadOnlyAlerting`):**

| Action | Trạng thái | Evidence |
| --- | --- | --- |
| `kafka:ListClusters` | **Đã cấp** — trả về cluster thật `techx-tf4-orders` | `raw/22-msk-describe-cluster-confirmed.json` |
| `kafka:DescribeCluster`/`V2` | **Đã cấp — xác nhận trực tiếp** bằng cách gọi riêng `aws kafka describe-cluster` và `describe-cluster-v2` (không chỉ suy diễn từ response của `ListClusters` như bản nháp trước) | `raw/22-msk-describe-cluster-confirmed.json` |
| `kafka:ListNodes` | **Vẫn `AccessDeniedException`** | `raw/19-msk-partial-grant-still-denied.txt` |
| `kafka:GetBootstrapBrokers` | **Vẫn `AccessDeniedException`** | `raw/19-msk-partial-grant-still-denied.txt` |

Cluster thật tìm được (`raw/22-msk-describe-cluster-confirmed.json`): `techx-tf4-orders`, ARN `arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2`, `kafka.t3.small` × 2 broker, `State: ACTIVE`, tạo `2026-07-19T14:25:48Z`, tag `Owner: CDO_04`. Đủ để `D8-COST-03` cập nhật MSK vào Data Sources; **chưa đủ** để lấy broker-node-level detail hay bootstrap endpoint (2 action còn lại).

Phần dưới đây giữ nguyên làm hồ sơ gốc của yêu cầu ban đầu (trước khi được cấp một phần).

Lệnh đã chạy và bị từ chối:

```text
aws kafka list-clusters --output json
aws kafka list-clusters-v2 --output json
```

Lỗi thực tế (nguyên văn, ghi lại tại thời điểm phát hiện — `ListClusters`/`DescribeCluster` đã được cấp sau đó, xem bảng ở đầu mục này):

```text
aws: [ERROR]: An error occurred (AccessDeniedException) when calling the ListClusters operation: User: arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86/tuan is not authorized to perform: kafka:ListClusters on resource: arn:aws:kafka:us-east-1:511825856493:/v1/clusters because no identity-based policy allows the kafka:ListClusters action

aws: [ERROR]: An error occurred (AccessDeniedException) when calling the ListClustersV2 operation: User: arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86/tuan is not authorized to perform: kafka:ListClustersV2 on resource: arn:aws:kafka:us-east-1:511825856493:/api/v2/clusters because no identity-based policy allows the kafka:ListClustersV2 action
```

### Policy read-only đề nghị cấp

Đề nghị thêm vào Permission Set `TF4-CostPerfReadOnlyAlerting` (và `TF4-BaseReadOnly` nếu team muốn đồng bộ 2 role):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "D8Cost03ReadMSKForCostSeparation",
      "Effect": "Allow",
      "Action": [
        "kafka:ListClusters",
        "kafka:ListClustersV2",
        "kafka:DescribeCluster",
        "kafka:DescribeClusterV2",
        "kafka:ListNodes",
        "kafka:GetBootstrapBrokers"
      ],
      "Resource": "*"
    }
  ]
}
```

Ghi chú (bản gốc): các action `kafka:List*`/`kafka:Describe*` không hỗ trợ scope theo resource ARN cụ thể (không giống ECR) — MSK API yêu cầu `Resource: "*"` cho các action list-level này. Nếu team muốn siết chặt hơn, có thể giới hạn qua `Condition` theo tag của cluster khi CDO-08 xác nhận cluster đã được gắn tag.

**Cập nhật sau khi được cấp một phần:** giờ đã biết đúng ARN cluster (`arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2`), nên phần còn thiếu (`kafka:ListNodes`, `kafka:GetBootstrapBrokers`) có thể xin scoped theo đúng cluster ARN đó thay vì `Resource: "*"` — sát least-privilege hơn bản đề nghị ban đầu. **Lưu ý:** chưa tự xác nhận được AWS MSK có hỗ trợ resource-level permission cho `DescribeCluster`/`ListNodes`/`GetBootstrapBrokers` hay không (không có tài liệu AWS IAM MSK action reference trong phiên làm việc này) — đề nghị IAM/Platform owner xác minh trước khi áp dụng bản scoped dưới đây; nếu MSK không hỗ trợ resource-level cho action nào, giữ `Resource: "*"` cho action đó:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "D8Cost03ReadMSKRemainingActionsScoped",
      "Effect": "Allow",
      "Action": [
        "kafka:ListNodes",
        "kafka:GetBootstrapBrokers"
      ],
      "Resource": "arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2"
    }
  ]
}
```

Mục đích từng action:

- `kafka:ListClusters`/`ListClustersV2`: liệt kê cluster để lấy ARN.
- `kafka:DescribeCluster`/`DescribeClusterV2`: đọc broker type, số broker, storage, cấu hình — input cho `D8-COST-03` §Required Separation và `D8-PERF-02` §MSK sizing.
- `kafka:ListNodes`: đọc chi tiết từng broker node (phục vụ đối chiếu node-hour nếu cần).
- `kafka:GetBootstrapBrokers`: chỉ để xác nhận endpoint đang hoạt động, không dùng để kết nối/produce/consume dữ liệu.

---

## 4. Blocker #2 — Kubernetes RBAC đọc `nodeclaims.karpenter.sh` (chặn `D8-COST-02`) — **PARTIALLY GRANTED**

**Cập nhật 2026-07-22 (sau khi đổi sang role `TF4-CostPerfReadOnlyAlerting`):**

| Resource | Trạng thái | Evidence |
| --- | --- | --- |
| `nodeclaims.karpenter.sh` (get/list) | **Đã cấp** — `kubectl get nodeclaims -o wide` trả về 2 NodeClaim thật | `raw/20-nodeclaims-granted.txt` |
| `nodepools.karpenter.sh` (get/list) | **Vẫn `Forbidden`** | `raw/21-nodepools-still-denied.txt` |

Dữ liệu NodeClaim thật (`raw/20-nodeclaims-granted.txt`): 2 NodeClaim, cả hai đều nodepool `techx-general`, `t3a.large`:

- `techx-general-djg4k` — node `ip-10-0-11-217.ec2.internal` (khớp instance `i-0b9df4a4ec1d03c16`), `AGE 6d1h` tại thời điểm thu thập.
- `techx-general-jchb5` — node `ip-10-0-10-19.ec2.internal` (khớp instance `i-0662168fdb18c47d4`), `AGE 3d9h` tại thời điểm thu thập.

Cả hai NodeClaim đều được tạo **trước** cutover `2026-07-22`, khớp với kết luận "không có node mới/consolidation" đã ghi trong `D8-COST-02-eks-capacity-verification-plan.md`. Đủ để cập nhật "NodeClaim lifetime" trong `D8-COST-02`; **chưa đủ** để có "Karpenter consolidation evidence" — cần Pass 2 (quan sát 2 NodeClaim này biến mất/giảm số lượng theo thời gian) để chứng minh consolidation thật sự xảy ra.

Phần dưới đây giữ nguyên làm hồ sơ gốc của yêu cầu ban đầu.

Lệnh đã chạy và bị từ chối, dưới **cả hai** role:

```text
kubectl get nodeclaims -o wide
```

```text
Attempt 1 (TF4-BaseReadOnly, 2026-07-22T03:31Z):
Error from server (Forbidden): nodeclaims.karpenter.sh is forbidden: User
"arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7/tuan"
cannot list resource "nodeclaims" in API group "karpenter.sh" at the cluster scope

Attempt 2 (TF4-CostPerfReadOnlyAlerting, retry sau khi đổi role):
Error from server (Forbidden): nodeclaims.karpenter.sh is forbidden: User
"arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86/tuan"
cannot list resource "nodeclaims" in API group "karpenter.sh" at the cluster scope
```

(Ghi lại tại thời điểm phát hiện — quyền `nodeclaims` đã được cấp sau đó, xem bảng ở đầu mục này; evidence hiện tại của trạng thái đã cấp là `raw/20-nodeclaims-granted.txt`.)

### RBAC read-only đề nghị cấp

Đề nghị Platform team tạo (hoặc mở rộng ClusterRole hiện có ánh xạ tới 2 role trên qua `aws-auth`/access entry) một `ClusterRole` + `ClusterRoleBinding` dạng:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cdo04-cost-perf-readonly-karpenter
rules:
  - apiGroups: ["karpenter.sh"]
    resources: ["nodeclaims", "nodepools"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cdo04-cost-perf-readonly-karpenter-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cdo04-cost-perf-readonly-karpenter
subjects:
  - kind: Group
    name: <group ánh xạ với TF4-BaseReadOnly và TF4-CostPerfReadOnlyAlerting trong aws-auth/access entry — Platform team điền>
    apiGroup: rbac.authorization.k8s.io
```

Chỉ xin `get`/`list`/`watch`, không xin `create`/`update`/`patch`/`delete` trên `nodeclaims`/`nodepools`.

Mục đích: đo `NodeClaim lifetime` và `Karpenter consolidation evidence` — 2 acceptance criteria còn mở của `D8-COST-02`.

---

## 5. Gap #3 — CUR (Cost and Usage Report) chưa được cấu hình (không phải IAM, là setup)

Lệnh đã chạy, **không có lỗi permission** — quyền gọi API đã có sẵn, nhưng account chưa có report nào:

```text
aws cur describe-report-definitions --output json
→ {"ReportDefinitions": []}
```

Evidence: `docs/evidence/directive-08/cost/raw/17-cur-report-definitions.txt`

### Đề nghị

Đây không phải là một IAM policy cần cấp cho Tuấn, mà là việc billing owner/CDO-08 cần **tạo một CUR export** (thường đổ vào S3 bucket riêng). Đề nghị:

1. Billing owner tạo CUR report (Athena/S3-compatible format) cho account `511825856493`.
2. Sau khi có, cấp thêm quyền đọc S3 bucket chứa CUR đó cho `TF4-CostPerfReadOnlyAlerting` (chỉ `s3:GetObject`, `s3:ListBucket` trên đúng bucket/prefix CUR — không xin quyền ghi/xóa). Gộp luôn vào policy delta ở Blocker #1 nếu Platform muốn xử lý một lần, để tránh phải xin lại lần hai.

Mục đích: `D8-COST-03` liệt kê CUR là một trong các nguồn dữ liệu bắt buộc để đối chiếu billing; hiện tại chỉ có Cost Explorer (luôn `Estimated: true` trong vài ngày đầu), CUR mới cho số liệu "settled" đáng tin cậy hơn.

---

## 6. Quyền tuyệt đối không yêu cầu

Không xin, và không cần, cho bất kỳ blocker nào ở trên:

- Bất kỳ action ghi nào trên MSK (`kafka:CreateCluster`, `kafka:DeleteCluster`, `kafka:UpdateBrokerCount`, v.v.)
- `create`/`update`/`patch`/`delete` trên `nodeclaims`/`nodepools` hoặc bất kỳ resource Karpenter nào khác
- `pods/exec`, Kubernetes Secret read, quyền tạo/sửa Deployment/Rollout
- Quyền ghi vào S3 bucket CUR (chỉ đọc)
- Terraform apply, GitOps write trên production
- Quyền IAM tự cấp quyền (`iam:PutRolePolicy`, v.v.)
- Bất kỳ quyền nào thuộc phạm vi Secrets Manager/KMS (out-of-scope của CDO-04 theo `epic8-task.md`)

---

## 7. Acceptance criteria

- [x] IAM owner đã áp dụng một phần policy delta ở mục 3 vào `TF4-CostPerfReadOnlyAlerting` (`ListClusters`, `DescribeCluster`/`DescribeClusterV2` — xác nhận `2026-07-22`, `raw/22-msk-describe-cluster-confirmed.json`). Còn thiếu `ListNodes`/`GetBootstrapBrokers`.
- [x] Platform team đã cấp một phần RBAC ở mục 4 (`nodeclaims` get/list — xác nhận `2026-07-22`, `raw/20-nodeclaims-granted.txt`). Còn thiếu `nodepools`.
- [ ] Billing owner xác nhận có/không có kế hoạch tạo CUR (mục 5) — nếu không, D8-COST-03 sẽ chỉ dùng Cost Explorer + AWS Budgets làm nguồn chính, cần ghi rõ trong evidence.
- [x] `aws kafka list-clusters` chạy được, trả về ARN cluster MSK thật. — xác nhận `2026-07-22`.
- [x] `kubectl get nodeclaims -o wide` chạy được, trả về danh sách NodeClaim thật. — xác nhận `2026-07-22`.
- [ ] `kafka:ListNodes`/`kafka:GetBootstrapBrokers` chạy được — **vẫn `AccessDeniedException`**, xem policy scoped bổ sung ở mục 3.
- [ ] `kubectl get nodepools -o wide` chạy được — **vẫn `Forbidden`**, xem RBAC ở mục 4 (cần bổ sung `nodepools` vào cùng ClusterRole).
- [x] Không có quyền write nào bị cấp thừa (đối chiếu với mục 6) — mọi quyền mới nhận được đều là `list`/`get`/`describe`.
- [ ] Re-run và cập nhật `D8-COST-02-eks-capacity-verification-plan.md` (NodeClaim lifetime, consolidation) và `D8-COST-03-billing-reconciliation.md` (MSK cost breakdown) với dữ liệu mới — **việc còn lại tiếp theo trong task này.**

---

## 8. Cách kiểm tra sau khi được cấp quyền

```bash
aws sts get-caller-identity

aws kafka list-clusters --output json
aws kafka describe-cluster --cluster-arn <arn trả về ở lệnh trên> --output json

kubectl get nodeclaims -o wide
kubectl get nodepools -o wide

# chỉ chạy nếu CUR đã được tạo (mục 5)
aws s3 ls s3://<cur-bucket>/<cur-prefix>/
```

---

## 9. Trách nhiệm

- IAM/Platform owner: áp dụng policy delta tối thiểu ở mục 3 và 4, xác nhận effective permission trước khi báo lại CDO-04.
- CDO-04 (Tuấn): cung cấp raw AccessDenied/Forbidden (đã đính kèm ở mục 3, 4), re-run verify sau khi cấp quyền, cập nhật evidence tương ứng.
- Billing owner (CDO-08 hoặc Finance/Platform, tuỳ tổ chức): quyết định có tạo CUR hay không (mục 5).
- CDO-04 không nhận thêm bất kỳ quyền write/provisioning nào ngoài phạm vi liệt kê ở mục 6.

---

## 10. Kết luận tạm thời

**Cập nhật 2026-07-22:** 2/3 gap đã được cấp **một phần**:

- MSK: `ListClusters`/`DescribeCluster` hoạt động (đủ cho phần lớn nhu cầu `D8-COST-03`), `ListNodes`/`GetBootstrapBrokers` vẫn bị chặn.
- Karpenter: `nodeclaims` hoạt động (đủ cho "NodeClaim lifetime" của `D8-COST-02`), `nodepools` vẫn bị chặn.
- CUR: không đổi, vẫn chưa được cấu hình — chờ billing owner.

Ticket này **không đóng ngay** dù đã cấp một phần — vẫn còn 2 action MSK + 1 resource Karpenter chưa được cấp theo đúng đề nghị ban đầu, và CUR vẫn treo. Bước tiếp theo: (1) dùng ngay dữ liệu mới nhận được để cập nhật `D8-COST-02`/`D8-COST-03` (không chờ phần còn thiếu), (2) tiếp tục theo dõi 2 action/resource còn thiếu, (3) chờ billing owner quyết định về CUR.
