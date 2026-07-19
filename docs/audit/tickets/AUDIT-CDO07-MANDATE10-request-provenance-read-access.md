# [AUDIT-CDO07-MANDATE10-01] Bổ sung quyền đọc provenance cho Directive #10

**Trạng thái:** DRAFT — chỉ gửi khi preflight sau SSO trả `AccessDenied`  
**Reporter:** CDO07 Audit — Task 10  
**Primary owner đề nghị:** CDO08 Security/IAM  
**Co-owner đề nghị:** CDO04 Platform/Infra (EKS RBAC và namespace test)  
**Priority:** P0 — blocker nghiệm thu Directive #10  
**Deadline:** trước 12:00 ngày 20/07/2026  
**AWS account/region:** `511825856493` / `us-east-1`  
**ECR/EKS:** `techx-corp` / `techx-tf4-cluster`

## 1. Bối cảnh

Directive #10 yêu cầu auditor chọn một Pod bất kỳ và tự truy được resolved image digest,
Cosign signature, SLSA provenance, SBOM, vulnerability scan, source PR/approvers và
GitOps promotion PR/approvers.

Static config trong repo cho thấy:

- Permission Set nền đã có `ecr:Describe*`, `ecr:List*`,
  `ecr:GetAuthorizationToken`, nhưng chưa có hai data-plane action cần để tải OCI
  manifest/layer là `ecr:BatchGetImage` và `ecr:GetDownloadUrlForLayer`;
- `infra/terraform/eks-access-entries.tf` đã map
  `TF4-AuditReadOnlyAndAnalyze` vào `AmazonEKSViewPolicy` cluster-wide.

Vì vậy ticket này **không xin lại cluster-wide read**. Owner chỉ cần kiểm tra quyền
đang hiệu lực và bổ sung đúng phần preflight chứng minh còn thiếu. CDO07 cần:

1. đọc image/referrer trong đúng ECR repository;
2. đọc Pod/admission runtime;
3. tạo một Pod negative-test trong namespace cô lập.

Ticket không yêu cầu push/delete image, đọc Kubernetes Secret, exec vào production
Pod hoặc sửa Deployment production.

## 2. Điều kiện mở ticket

CDO07 refresh SSO rồi chạy preflight:

```powershell
aws sso login --profile <cdo07-profile>
aws sts get-caller-identity --profile <cdo07-profile>
aws eks update-kubeconfig `
  --name techx-tf4-cluster `
  --region us-east-1 `
  --profile <cdo07-profile>

kubectl auth can-i get pods -n techx-tf4
kubectl auth can-i get imagevalidatingpolicies.policies.kyverno.io
kubectl auth can-i create pods -n techx-supply-chain-test
```

Sau đó thử `cosign verify` trên một image digest đã biết. Chỉ mở ticket nếu có
`AccessDenied` hoặc `kubectl auth can-i` trả `no`, và đính kèm raw output đã redact.

- `ExpiredToken`, tunnel đóng hoặc sai kube-context là lỗi session/kết nối, không phải
  bằng chứng thiếu quyền.
- Nếu toàn bộ preflight PASS thì đóng draft này là `NOT REQUIRED`, không xin thêm quyền.

## 3. Đối chiếu AWS permissions

### 3.1. EKS discovery đã có — không yêu cầu cấp lại

`eks:DescribeCluster` đã nằm trong Permission Set hiện có. Terraform và runtime evidence
cũng xác nhận `TF4-AuditReadOnlyAndAnalyze` đã có EKS Access Entry với
`AmazonEKSViewPolicy`. Ticket không yêu cầu cấp lại quyền này.

`eks:AccessKubernetesApi` chỉ cần khi xem Kubernetes resources qua AWS Console; luồng
nghiệm thu dùng `kubectl`, EKS Access Entry và Kubernetes RBAC nên không xin action này.

### 3.2. ECR authentication đã có — chỉ kiểm tra hiệu lực

Permission Set nền đã khai báo `ecr:GetAuthorizationToken`. Không thêm statement trùng
nếu preflight PASS. Nếu effective policy khác tài liệu và action này thực sự bị deny,
owner bổ sung statement dưới đây; action không hỗ trợ resource-level scope.

```json
{
  "Sid": "Mandate10EcrAuthentication",
  "Effect": "Allow",
  "Action": [
    "ecr:GetAuthorizationToken"
  ],
  "Resource": "*"
}
```

### 3.3. Chỉ bổ sung hai ECR data-plane actions nếu preflight fail

```json
{
  "Sid": "Mandate10EcrEvidenceRead",
  "Effect": "Allow",
  "Action": [
    "ecr:BatchGetImage",
    "ecr:GetDownloadUrlForLayer"
  ],
  "Resource": "arn:aws:ecr:us-east-1:511825856493:repository/techx-corp"
}
```

`ecr:BatchGetImage` lấy manifest và cũng là IAM action AWS dùng cho
`ListImageReferrers`; `ecr:GetDownloadUrlForLayer` tải payload của signature và
attestations. `ecr:Describe*`/`ecr:List*` hiện có không thay thế hai action này.

Không xin `ecr:DescribeImageScanFindings`: ECR scan-on-push không phải scan gate được
Directive #10 công nhận. Không xin lifecycle/repository policy, upload, put hoặc delete.

## 4. EKS Access Entry và Kubernetes RBAC nếu preflight fail

Ưu tiên tái sử dụng EKS Access Entry hiện có của `TF4-AuditReadOnlyAndAnalyze`.
Không tạo thêm principal hoặc cấp cluster-admin. Nếu managed view policy chưa đọc được
Kyverno CRD thì bổ sung custom read-only ClusterRole/Binding cho đúng principal.

### 4.1. Cluster-scoped read bổ sung

- `get/list`:
  - `ValidatingAdmissionPolicy`;
  - `ValidatingAdmissionPolicyBinding`;
  - `ValidatingWebhookConfiguration`;
  - Kyverno `ImageValidatingPolicy`.

### 4.2. Namespace runtime read-only

Trong `techx-tf4` và `kyverno`:

- `get/list` Pods;
- `get/list` Deployments, ReplicaSets và PDB;
- `get/list` Events.

Không cấp:

- `get/list` Secrets;
- `pods/exec`;
- create/patch/update/delete workload production.

### 4.3. Namespace negative-test

Tạo namespace:

```text
techx-supply-chain-test
```

Trong namespace này, cấp:

- `create/get/list/delete` Pod;
- `get/list` Event.

Namespace có quota nhỏ, không có LoadBalancer/Ingress và không chứa production secret.

## 5. Acceptance criteria

- [ ] `aws sts get-caller-identity` thành công sau SSO login.
- [ ] `aws ecr describe-repositories --repository-names techx-corp` trả về mutability.
- [ ] Auditor ECR login và `cosign verify` được một digest mà không cần push permission.
- [ ] Auditor liệt kê được OCI referrers của digest bằng ECR `ListImageReferrers`
      (AWS ghi nhận API này sử dụng quyền `ecr:BatchGetImage`).
- [ ] `kubectl -n techx-tf4 get pods` đọc được `status.containerStatuses.imageID`.
- [ ] Đọc được admission policy/webhook runtime.
- [ ] Tạo Pod negative-test trong `techx-supply-chain-test`; unsigned image bị admission reject.
- [ ] `kubectl auth can-i` xác nhận auditor không sửa được production Deployment và không đọc Secret.

## 6. Lệnh CDO07 dùng để nghiệm thu

```powershell
$env:AWS_PROFILE = '<cdo07-profile>'
aws sso login
aws sts get-caller-identity

aws ecr describe-repositories `
  --repository-names techx-corp `
  --region us-east-1

kubectl auth can-i get pods -n techx-tf4
kubectl auth can-i get imagevalidatingpolicies.policies.kyverno.io
kubectl auth can-i create pods -n techx-supply-chain-test
kubectl auth can-i patch deployments -n techx-tf4
kubectl auth can-i get secrets -n techx-tf4
```

Expected hai lệnh cuối cho production mutation/secret là `no`.

## 7. Ranh giới trách nhiệm

- CDO08 Security/IAM chỉ bổ sung ECR actions nếu raw `AccessDenied` chứng minh thiếu.
- CDO04 Platform/Infra kiểm tra EKS Access Entry hiện có; chỉ bổ sung RBAC/namespace test
  nếu `kubectl auth can-i` chứng minh thiếu.
- CDO07 chạy lại checks, lưu raw evidence và xác nhận least privilege.
- Không cấp credential dài hạn hoặc quyền ECR write cho auditor.
