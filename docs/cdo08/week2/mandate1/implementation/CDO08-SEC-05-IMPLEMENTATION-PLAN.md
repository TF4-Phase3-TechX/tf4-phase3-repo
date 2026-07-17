# CDO08-SEC-05 — Implementation plan

> Mục đích: hướng dẫn triển khai private operational portals theo thiết kế đã
> review. Đây là checklist thực hiện, không thay thế approval. Không apply
> Terraform, không merge/deploy Envoy và không cắt public route khi các ô trong
> Phase 0 chưa được xác nhận.

Tài liệu thiết kế gốc:
`docs/cdo08/week2/CDO08-SEC-05-INGRESS-HARDENING-RUNBOOK.md`.

## 1. Kết quả cần đạt

```text
Public Internet
  ├─ /                          → storefront, 200 OK
  └─ operational/internal path → explicit 404

Mentor/BTC dùng AWS SSO identity cá nhân
  → SSM Session Manager
  → EC2 Bastion private
  → kubectl port-forward trên Bastion
  → Grafana / Jaeger / Loadgen
```

Sáu public route phải chặn:

1. `/grafana` và `/grafana/…`
2. `/jaeger` và `/jaeger/…`
3. `/loadgen` và `/loadgen/…`
4. `/feature` và `/feature/…`
5. `/flagservice` và `/flagservice/…`
6. `/otlp-http` và `/otlp-http/…`

Không thay đổi `deploy/ingress.yaml`, flagd Service, OpenFeature hooks hoặc các
backend observability trong lần hardening này.

## 2. Nguyên tắc quyền truy cập

Phải có hai IAM role khác nhau:

| Role | Ai assume | Mục đích |
|---|---|---|
| Bastion instance role | EC2 service | Đăng ký SSM, đọc EKS cluster và xác thực Kubernetes |
| Operator SSO role/Permission Set | Mentor/BTC/operator | Start/terminate SSM session vào đúng Bastion |

Người dùng SSO không cần kubeconfig, EKS permission hoặc Kubernetes RBAC trên
laptop. EKS Access Entry chỉ map **Bastion instance role** vào Kubernetes group
`sec05-portal-bastion`.

Không cấp `AdministratorAccess`, `cluster-admin`, wildcard action/resource,
`iam:PassRole`, SSH hoặc EC2 Instance Connect cho người vận hành.

## 3. Phase 0 — Chốt thông tin trước khi code/apply

Điền các giá trị sau:

```text
AWS account ID:                    511825856493
AWS region:                        us-east-1
EKS cluster:                       techx-tf4-cluster
Mentor/BTC SSO role ARN:           arn:aws:iam::511825856493:role/AWSReservedSSO_TF4-Admin-BreakGlass_99a0fe2c9d050d5d
Operator SSO role ARN:             arn:aws:iam::511825856493:role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_d050f2302bbdb6d9
Người được Start/Stop Bastion:     Anh Nghĩa / Mentor
SSM shell log destination:         chưa bật
Log retention:                     0 ngày
Bastion runtime:                   manual on-demand
Projected total TF cost:           $3.5/tuần
Checkout smoke-test owner:         Anh Nghĩa
Deploy window:                     20:00 - 22:00
Current app Helm revision/image:   Helm Release: techx-corp
Current observability revision:    Helm Release: techx-observability
```

Approval checklist:

- [x] Nhân approve sáu route cần chặn.
- [x] Quyết xác nhận cách xử lý `/otlp-http`.
- [x] flagd/OpenFeature owner xác nhận không thay hook/service/config.
- [x] CDO04 xác nhận projected total TF cost và budget period.
- [x] CDO07 xác nhận logging/retention và residual audit risk.
- [x] Tech Lead chấp nhận phạm vi Kubernetes RBAC mô tả tại mục 6.4.
- [x] Mentor/BTC xác nhận SSO role/Permission Set sẽ sử dụng.
- [x] Deploy Operator xác nhận release strategy và rollback revision.

### Quyết định bắt buộc cho `/otlp-http`

Frontend hiện dùng `/otlp-http/v1/traces` cho browser telemetry. Chặn route mà
không xử lý cấu hình frontend có thể làm mất `frontend-web` traces.

Chọn một phương án và attach approval:

- [x] Tắt browser telemetry tạm thời; giữ server-side telemetry và SLO metrics.
- [ ] Thay bằng ingestion endpoint có authentication/rate-limit đã được review.
- [ ] Phương án khác do Observability owner phê duyệt: (Đã duyệt tắt tạm thời).

Không giữ public anonymous OTLP chỉ để tránh thay đổi telemetry.

## 4. Phase 1 — Terraform cho Bastion

### 4.1 File dự kiến

```text
infra/terraform/sec05-bastion.tf
infra/terraform/sec05-bastion-user-data.sh.tftpl
infra/terraform/sec05-session-manager.tf  # chỉ khi CDO07 chốt logging
infra/terraform/variables.tf
infra/terraform/outputs.tf
infra/terraform/eks-access-entries.tf
```

Không đưa credential, kubeconfig hoặc token vào Terraform state/user-data.

### 4.2 EC2 instance role

Tạo role, instance profile và policy tối thiểu:

```text
Role name: tf4-sec05-bastion-role
Trust:     ec2.amazonaws.com
Managed:   AmazonSSMManagedInstanceCore
Custom:    eks:DescribeCluster trên techx-tf4-cluster
```

Policy `eks:DescribeCluster` phải giới hạn đúng cluster ARN:

```hcl
resource "aws_iam_role_policy" "sec05_bastion_eks_describe" {
  name = "tf4-sec05-bastion-eks-describe"
  role = aws_iam_role.sec05_bastion.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["eks:DescribeCluster"]
      Resource = module.eks.cluster_arn
    }]
  })
}
```

### 4.3 EC2 và Security Group

EC2 baseline:

- `t3.nano`, Amazon Linux 2023, kiến trúc phù hợp AMI.
- Private subnet; `associate_public_ip_address = false`.
- Không Elastic IP.
- Encrypted gp3 8 GiB.
- `metadata_options.http_tokens = "required"`.
- Security Group không có ingress rule.
- HTTPS egress phục vụ SSM, EKS API và tải artifact qua NAT hiện có.
- DNS egress đến VPC resolver.
- Tag tối thiểu: `Name`, `Project`, `Environment`, `SecurityFinding`, `ManagedBy`.

Ví dụ tag dùng để scope IAM:

```hcl
tags = merge(var.tags, {
  Name            = "tf4-sec05-ssm-bastion"
  SecurityFinding = "CDO08-SEC-05"
  AccessPurpose   = "OperationalPortals"
})
```

Không tạo NAT Gateway, SSM VPC Endpoint, Internal ALB hoặc inbound port 22.

### 4.4 Bootstrap

User-data chỉ làm các việc sau:

1. Xác nhận/start SSM Agent.
2. Cài AWS CLI và `kubectl` phiên bản pin tương thích EKS 1.34.
3. Verify checksum của binary trước khi install.
4. Tạo helper script/read-only instructions; không chứa credential.

Không tải `kubectl latest` không pin version/checksum. Pilot trên `t3.nano`; ghi
memory, swap, SSM registration time và kết quả chạy AWS CLI/`kubectl`.

Nếu `t3.nano` không ổn định, dừng tại đây và gửi CDO04 review trước khi đổi size.

### 4.5 EKS Access Entry

Thêm Access Entry cho **IAM role ARN**, không dùng instance-profile ARN:

```hcl
resource "aws_eks_access_entry" "sec05_bastion" {
  cluster_name      = module.eks.cluster_name
  principal_arn     = aws_iam_role.sec05_bastion.arn
  type              = "STANDARD"
  kubernetes_groups = ["sec05-portal-bastion"]
  tags              = var.tags
}
```

Không thêm `aws_eks_access_policy_association` kiểu admin/view cho role này;
authorization sẽ do namespaced Kubernetes Role/RoleBinding quản lý.

### 4.6 Cluster API network

Bastion phải kết nối được private EKS endpoint TCP 443. Nếu cluster Security
Group chưa cho phép, thêm ingress TCP 443 từ Bastion Security Group vào cluster
Security Group. Không mở EKS API cho một CIDR public mới.

Lưu ý ngoài scope: repo hiện vẫn cấu hình EKS public endpoint CIDR
`0.0.0.0/0`. Không tự sửa trong SEC-05; tạo finding/PR riêng nếu owner yêu cầu.

### 4.7 Operator SSO permission

Permission Set/role của Mentor/BTC cần tối thiểu:

- `ssm:StartSession` vào EC2 có tag `SecurityFinding=CDO08-SEC-05`.
- Chỉ document shell được approve và `AWS-StartPortForwardingSession`.
- `ssm:ResumeSession`/`ssm:TerminateSession` cho session của chính principal.
- `ssm:DescribeSessions`, `ssm:GetConnectionStatus`,
  `ssm:DescribeInstanceInformation` theo nhu cầu CLI.
- `ec2:DescribeInstances`.
- `ec2:StartInstances`/`ec2:StopInstances` chỉ khi operator được giao vận hành
  on-demand, giới hạn đúng Bastion ARN/tag.

Không gắn policy này vào Bastion instance role. Không cấp EKS permission cho
Mentor/BTC.

### 4.8 Terraform validation

```bash
cd infra/terraform
terraform fmt -check -recursive
terraform init
terraform validate
terraform plan -out=sec05.tfplan
terraform show -no-color sec05.tfplan > sec05-plan.txt
```

Review plan phải xác nhận:

- [ ] Một private EC2, một instance role/profile và Security Group không ingress.
- [ ] Không public IP/EIP/port 22.
- [ ] Không NAT/VPC Endpoint/Internal ALB mới.
- [ ] Không admin EKS access policy.
- [ ] EBS encrypted 8 GiB.
- [ ] Không replace ngoài SEC-05 resources.
- [ ] Không có secret trong plan output.

## 5. Phase 2 — Session logging và audit

CDO07 phải chốt cấu hình trước khi apply Session Manager preferences.

Audit coverage:

| Log | Có thể chứng minh | Không chứng minh |
|---|---|---|
| CloudTrail | SSO principal, thời gian, IP, Bastion target, SSM document/port | HTTP action trong portal |
| SSM shell log Terminal A | Lệnh `kubectl port-forward`, nếu logging bật | Nội dung tunnel Terminal B |
| EKS audit | Bastion role gọi `pods/portforward` | AWS SSO principal trực tiếp và HTTP action |

Không gọi S3 Versioning là WORM. Bucket CloudTrail hiện có `force_destroy = true`
và chưa thấy Object Lock; mọi tuyên bố immutability phải do CDO07 xác nhận bằng
runtime evidence.

Checklist:

- [ ] CloudTrail ghi management events `StartSession`/`TerminateSession`.
- [ ] Log destination và retention đã chốt.
- [ ] Log group/bucket encryption và delete permission đã review.
- [ ] Evidence không chứa token/cookie/credential.
- [ ] Residual risk không có application-level audit đã được accept.

## 6. Phase 3 — Kubernetes RBAC cho hai Helm release

### 6.1 Tại sao cần file riêng?

Chart được render/deploy hai lần:

```text
Release techx-observability → namespace techx-observability
Release techx-corp          → namespace techx-tf4
```

Không đặt SEC-05 RBAC ngoài namespace guard vì cả hai release có thể cùng render
resource và gây sai namespace/Helm ownership conflict.

Tạo file:

```text
techx-corp-chart/templates/sec05-portal-rbac.yaml
```

Không sửa quyền hiện tại trong `team-rbac.yaml` nếu chưa có approval riêng.

### 6.2 Values

Thêm default vào `techx-corp-chart/values.yaml`:

```yaml
sec05PortalAccess:
  enabled: false
  groupName: sec05-portal-bastion
```

Bật trong cả `deploy/values-observability.yaml` và
`deploy/values-app-stamp.yaml`:

```yaml
sec05PortalAccess:
  enabled: true
  groupName: sec05-portal-bastion
```

### 6.3 Template pattern

Observability release:

```yaml
{{- if and .Values.sec05PortalAccess.enabled (eq .Release.Namespace "techx-observability") }}
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: sec05-portal-portforward
  namespace: {{ .Release.Namespace }}
rules:
  - apiGroups: [""]
    resources: ["services"]
    resourceNames: ["grafana", "jaeger"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/portforward"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: sec05-portal-portforward-binding
  namespace: {{ .Release.Namespace }}
subjects:
  - kind: Group
    name: {{ .Values.sec05PortalAccess.groupName | quote }}
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: sec05-portal-portforward
  apiGroup: rbac.authorization.k8s.io
{{- end }}
```

App release dùng guard `techx-tf4`, service `load-generator` và resource name
khác, ví dụ `sec05-loadgen-portforward`.

Không tạo SEC-05 `ClusterRole`/`ClusterRoleBinding`. Không cấp `secrets`,
`deployments`, `exec`, `proxy`, delete/update/patch hoặc wildcard.

### 6.4 Residual RBAC risk

`kubectl port-forward svc/...` cuối cùng tạo API request `pods/portforward` vào
Pod có tên động. Kubernetes RBAC thuần túy không giới hạn ổn định quyền này theo
Service label. Vì vậy role có `pods/portforward` trong `techx-tf4` về kỹ thuật có
thể forward Pod khác trong namespace, không chỉ Loadgen.

Trước deploy phải chọn:

- [ ] Chấp nhận namespaced port-forward như residual risk cho operator đã được
  SSO/SSM authorize.
- [ ] Yêu cầu enforcement bổ sung bằng admission policy/dedicated access proxy;
  khi đó dừng implementation và review lại scope.

Ngoài ra, `ai-readers` hiện đã có `pods/portforward` trong observability. Nếu SSM
Bastion phải là đường duy nhất, cần owner approve việc bỏ quyền cũ trong một thay
đổi được review riêng.

### 6.5 Render và CI checks

```bash
helm dependency build ./techx-corp-chart
helm lint ./techx-corp-chart

helm template techx-observability ./techx-corp-chart \
  --namespace techx-observability \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml \
  > rendered-observability.yaml

helm template techx-corp ./techx-corp-chart \
  --namespace techx-tf4 \
  --set default.image.tag=preview \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  > rendered-app.yaml
```

Xác nhận:

- [ ] Observability manifest có SEC-05 Role ở `techx-observability`.
- [ ] Observability manifest không có Loadgen Role.
- [ ] App manifest có Loadgen Role ở `techx-tf4`.
- [ ] App manifest không có Grafana/Jaeger Role.
- [ ] Không có SEC-05 ClusterRole/ClusterRoleBinding.
- [ ] Group luôn là `sec05-portal-bastion`.

Bổ sung assertions tương ứng vào hai bước render trong `.github/workflows/ci.yaml`.

## 7. Phase 4 — Apply private access trước

Thứ tự bắt buộc:

1. Merge/apply Terraform sau approval.
2. Start Bastion.
3. Xác nhận Bastion xuất hiện trong SSM Managed Nodes.
4. Deploy Role/RoleBinding cho hai Helm release.
5. Test RBAC bằng Bastion role.
6. Test cả ba portal qua hai SSM session.
7. Thu audit evidence.
8. Chỉ khi tất cả pass mới sang Envoy cutover.

RBAC checks trên Bastion:

```bash
aws eks update-kubeconfig --region us-east-1 --name techx-tf4-cluster

kubectl auth can-i get service/grafana -n techx-observability
kubectl auth can-i create pods/portforward -n techx-observability
kubectl auth can-i get secrets -n techx-observability
kubectl auth can-i create pods/exec -n techx-observability
kubectl auth can-i create pods/portforward -n techx-tf4
```

Mong đợi:

```text
service get / pods portforward: yes
secrets / pods exec:             no
```

Port baseline:

| Bastion Port | Kubernetes Target | Laptop Port | Source/Runtime Mapping (Daemon on Bastion) |
| :---: | :--- | :---: | :--- |
| `13000` | `techx-observability/svc/grafana:80` | `3000` | `kubectl port-forward svc/grafana 13000:80 -n techx-observability` |
| `16686` | `techx-observability/svc/jaeger:16686` | `16686` | `kubectl port-forward svc/jaeger 16686:16686 -n techx-observability` |
| `18089` | `techx-tf4/svc/load-generator:8089` | `8089` | `kubectl port-forward svc/load-generator 18089:8089 -n techx-tf4` |

Pass khi Mentor/BTC dùng identity cá nhân truy cập được cả ba portal và đóng
Terminal A hoặc B thì đường truy cập bị ngắt.

## 8. Phase 5 — Envoy hardening

Sửa:

```text
techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml
```

Đặt direct responses trước route proxy hiện tại và trước storefront catch-all:

```yaml
- match: { path: "/grafana" }
  direct_response: { status: 404 }
- match: { prefix: "/grafana/" }
  direct_response: { status: 404 }

- match: { path: "/jaeger" }
  direct_response: { status: 404 }
- match: { prefix: "/jaeger/" }
  direct_response: { status: 404 }

- match: { path: "/loadgen" }
  direct_response: { status: 404 }
- match: { prefix: "/loadgen/" }
  direct_response: { status: 404 }

- match: { path: "/feature" }
  direct_response: { status: 404 }
- match: { prefix: "/feature/" }
  direct_response: { status: 404 }

- match: { path: "/flagservice" }
  direct_response: { status: 404 }
- match: { prefix: "/flagservice/" }
  direct_response: { status: 404 }

- match: { path: "/otlp-http" }
  direct_response: { status: 404 }
- match: { prefix: "/otlp-http/" }
  direct_response: { status: 404 }
```

Giữ cluster definitions trong lần thay đổi đầu để giảm blast radius. Không
redirect path trần và không giữ WebSocket upgrade cho `/feature`.

Validation:

- [ ] Envoy config validate thành công bằng đúng image/version.
- [ ] Exact path và subpath đều direct response.
- [ ] Route deny đứng trước catch-all `/`.
- [ ] `/`, `/api/...`, `/images/...` không bị chặn nhầm.
- [ ] Query string không bypass deny.
- [ ] Không thay flagd/OpenFeature config.

## 9. Phase 6 — Build và deploy

Workflow hiện tại build/push toàn bộ service images rồi deploy cả app release.
Deploy Operator phải chọn một cách:

### Cách A — Khuyến nghị: rollout riêng frontend-proxy

Build immutable image:

```text
<ECR_REPOSITORY>:<GIT_SHA>-frontend-proxy
```

Chart hỗ trợ:

```yaml
components:
  frontend-proxy:
    imageOverride:
      repository: <ECR_REPOSITORY>
      tag: <GIT_SHA>-frontend-proxy
```

Deploy chỉ override component này và giữ nguyên tag của các service khác. Ghi lại
Helm values/revision trước và sau. Nếu cần sửa workflow để hỗ trợ targeted build,
phần sửa phải được Deploy Operator review.

### Cách B — Dùng workflow hiện tại

Chỉ dùng khi Deploy Operator approve rollout toàn app trong maintenance window.
Phải build đủ image cùng tag, kiểm tra checkout trước/sau và chuẩn bị Helm rollback.

Không tự chạy một lệnh Helm ad-hoc nếu release ownership/values chưa được xác
nhận.

Pre-deploy evidence:

```bash
date -Iseconds
helm -n techx-tf4 history techx-corp
helm -n techx-observability history techx-observability
kubectl -n techx-tf4 get deploy frontend-proxy -o wide
kubectl -n techx-tf4 get deploy frontend-proxy \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

## 10. Phase 7 — Verification

```bash
export ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
date -Iseconds

curl -I "$ALB/"
curl -I "$ALB/grafana"
curl -I "$ALB/grafana/"
curl -I "$ALB/jaeger"
curl -I "$ALB/jaeger/ui/"
curl -I "$ALB/loadgen"
curl -I "$ALB/loadgen/"
curl -I "$ALB/feature"
curl -I "$ALB/flagservice/"
curl -I "$ALB/otlp-http/v1/traces"
```

Pass criteria:

- [ ] Storefront `/` trả `200 OK`.
- [ ] Sáu route và subpath trả explicit `404`.
- [ ] Không redirect, storefront SPA fallback hoặc WebSocket upgrade.
- [ ] Checkout smoke test pass.
- [ ] Checkout success/p95 không xấu đi.
- [ ] flagd Pod Ready và OpenFeature hooks hoạt động.
- [ ] Server-side telemetry vẫn hoạt động.
- [ ] Browser telemetry đúng quyết định tại Phase 0.
- [ ] Mentor/BTC private access pass.
- [ ] CloudTrail có hai SSM `StartSession` cùng principal/Bastion/test window.
- [ ] SSM/EKS evidence khớp port baseline nếu các log này được bật.

Không tạo giao dịch thật nếu checkout smoke test chưa có cleanup/idempotency được
approve.

## 11. Phase 8 — Rollback

Rollback infrastructure và application tách riêng:

### Bastion/IAM/RBAC lỗi

- Không cắt public route.
- Revert/apply Terraform plan đã review.
- Helm rollback Role/RoleBinding nếu chúng gây lỗi release.
- Storefront không được bị ảnh hưởng.

### Envoy rollout lỗi

- Dừng rollout nếu readiness/config validation fail.
- Ưu tiên fix-forward bằng image hardening-only đã test.
- Không mặc định rollback về image làm portal public trở lại.
- Nếu bắt buộc rollback, cần mitigation public deny khác đã được approve.

Lệnh tham khảo sau khi đã xác nhận đúng revision:

```bash
helm -n techx-tf4 history techx-corp
helm -n techx-tf4 rollback techx-corp <PREVIOUS_SAFE_REVISION> --wait
kubectl -n techx-tf4 rollout status deployment/frontend-proxy --timeout=5m
```

`PREVIOUS_SAFE_REVISION` phải là revision vẫn giữ public deny hoặc có mitigation
tương đương; không chọn chỉ vì đó là revision gần nhất.

## 12. Evidence và Definition of Done

Attach Jira:

1. Approval links của Nhân, Quyết, flagd owner, CDO04, CDO07, Mentor/BTC và
   Deploy Operator.
2. Terraform plan/apply và resource inventory, không chứa secret.
3. IAM role/policy summary, EKS Access Entry và rendered RBAC.
4. Before/after public curl có timestamp.
5. Private access screenshot/output cho Grafana, Jaeger và Loadgen.
6. CloudTrail, SSM shell và EKS audit correlation theo mức log đã bật.
7. Storefront, checkout, SLO, flagd và telemetry verification.
8. Immutable image tag, Helm revision và rollback record.
9. Projected/actual Cost Explorer evidence và giải thích variance.

Hoàn thành khi:

- [ ] Storefront public vẫn `200`.
- [ ] Checkout smoke pass và SLO không giảm.
- [ ] Sáu operational/internal routes không còn public.
- [ ] Mentor/BTC private access được kiểm chứng.
- [ ] flagd/OpenFeature không bị thay đổi hoặc vô hiệu hóa.
- [ ] Audit limitation được ghi đúng, không overclaim.
- [ ] Nhân sign-off Acceptance Criteria.
- [ ] PM cập nhật backlog.

## 13. Kế hoạch PR và Evidence

Để đơn giản hóa quá trình kiểm thử và tích hợp nhanh:

1. **Gộp vào 1 PR duy nhất:** Tất cả các thành phần (Terraform Bastion, EKS Access Entry, Helm RBAC template, cấu hình Envoy proxy chặn 6 routes và xử lý `/otlp-http`) sẽ được gom chung và triển khai trong **1 PR duy nhất** lên nhánh PR của bạn.
2. **Nộp Evidence sau:** Sau khi PR được merge và CD chạy thành công, chúng ta sẽ tiến hành kiểm thử thực tế và tạo tài liệu chứng cứ (Evidence) để cập nhật lên Jira sau.
