# [AUDIT-CDO07-MANDATE10-01] Yêu cầu quyền đọc ECR provenance tối thiểu

- **Trạng thái:** DRAFT — chỉ activate khi preflight sau SSO trả `AccessDenied`
- **Reporter:** CDO07 Audit — Task 10
- **Owner cần Tech Lead điều phối:** IAM/Cloud owner quản lý Permission Set CDO07
- **Priority:** P0 — blocker truy vết Pod về Source
- **Deadline:** trước 12:00 ngày 20/07/2026
- **AWS account/region:** `511825856493` / `us-east-1`
- **ECR repository:** `techx-corp`

## 1. Mục đích

CDO07 cần kiểm chứng chuỗi provenance của một Pod đang chạy:

```text
Pod imageID
  -> ECR image digest
  -> Cosign signature
  -> provenance/SBOM/vulnerability attestations
  -> source commit + PR + approvers
```

Ticket này chỉ xin quyền đọc OCI artifact trong đúng ECR repository. Ticket không yêu
cầu CDO07 cài admission controller, chọn công nghệ policy hoặc thay đổi cluster.

## 2. Quyền hiện có — không cấp lại

Tài liệu IAM hiện tại đã khai báo:

- `ecr:Describe*`;
- `ecr:List*`;
- `ecr:GetAuthorizationToken`;
- `eks:DescribeCluster`.

Terraform cũng đã map role `TF4-AuditReadOnlyAndAnalyze` vào
`AmazonEKSViewPolicy` để đọc Pod runtime.

Không bổ sung lại các quyền trên nếu effective permission đã hoạt động.

## 3. Static gap cần runtime xác nhận

Các tài liệu Permission Set hiện chưa khai báo ba ECR data-plane read actions mà
OCI/Cosign client có thể cần để đọc manifest và layer của signature/attestation:

```text
ecr:BatchGetImage
ecr:GetDownloadUrlForLayer
ecr:BatchCheckLayerAvailability
```

- `BatchGetImage`: đọc image/OCI manifest; AWS cũng dùng permission này cho
  `ListImageReferrers`.
- `GetDownloadUrlForLayer`: lấy URL tải layer chứa payload.
- `BatchCheckLayerAvailability`: kiểm tra layer trước khi OCI client tải artifact.

Đây đều là read actions và hỗ trợ resource-level scope theo ECR repository.

## 4. Điều kiện activate ticket

CDO07 phải refresh SSO trước:

```powershell
$env:AWS_PROFILE = "<cdo07-profile>"
aws sso login
aws sts get-caller-identity
```

Sau đó chọn một digest thật từ Pod:

```powershell
kubectl -n techx-tf4 get pod <pod-name> `
  -o jsonpath='{range .status.containerStatuses[*]}{.name}{"`t"}{.imageID}{"`n"}{end}'
```

Chạy ECR/Cosign read preflight:

```powershell
aws ecr batch-get-image `
  --repository-name techx-corp `
  --image-ids imageDigest=sha256:<64-hex> `
  --region us-east-1

aws ecr list-image-referrers `
  --repository-name techx-corp `
  --subject-id imageDigest=sha256:<64-hex> `
  --region us-east-1
```

Sau khi login ECR, chạy `cosign verify` hoặc `cosign download attestation` trên exact
digest.

Chỉ activate ticket khi raw output đã redact cho thấy principal CDO07 bị
`AccessDenied` ở một trong ba action nêu trên.

Không dùng các lỗi sau làm bằng chứng thiếu quyền:

- `ExpiredToken`;
- SSO chưa login;
- tunnel/kube-context đóng;
- DNS/network timeout;
- signature hoặc attestation không tồn tại;
- signer identity không khớp.

Nếu preflight đọc được đầy đủ artifact thì đóng ticket là `NOT REQUIRED`.

## 5. Policy delta đề nghị

Chỉ áp dụng khi điều kiện ở mục 4 đã thỏa:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Mandate10ReadProvenanceArtifacts",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Resource": "arn:aws:ecr:us-east-1:511825856493:repository/techx-corp"
    }
  ]
}
```

`ecr:GetAuthorizationToken` không nằm trong delta vì Permission Set hiện đã có và action
này không hỗ trợ resource-level scope.

## 6. Quyền không yêu cầu

Không cấp cho CDO07:

- `ecr:PutImage`;
- `ecr:BatchDeleteImage`;
- layer upload hoặc repository mutation;
- ECR repository khác `techx-corp`;
- Kubernetes Pod/Deployment create, update, patch hoặc delete;
- Kubernetes Secret read;
- `pods/exec`;
- cluster-admin;
- Terraform apply hoặc GitOps write trên production;
- quyền tạo/cập nhật Branch Protection.

Negative admission test do Security/Platform thực hiện trong namespace an toàn; CDO07
đứng cùng kiểm chứng và thu evidence, không cần quyền tạo Pod.

## 7. Acceptance criteria

- [ ] SSO identity đúng role `TF4-AuditReadOnlyAndAnalyze`.
- [ ] Chỉ các action bị `AccessDenied` thực tế mới được bổ sung.
- [ ] Resource chỉ là repository `techx-corp`.
- [ ] `aws ecr batch-get-image` đọc được exact Pod digest.
- [ ] `aws ecr list-image-referrers` liệt kê được artifact của digest.
- [ ] Cosign tải/verify được signature và attestations nếu artifact tồn tại.
- [ ] CDO07 vẫn không có ECR write hoặc Kubernetes workload write.
- [ ] Raw before/after output đã redact được lưu vào evidence pack.

## 8. Trách nhiệm

- IAM/Cloud owner: kiểm tra effective permission và chỉ apply policy delta cần thiết.
- CDO07: cung cấp raw `AccessDenied`, chạy lại preflight và xác nhận least privilege.
- Security/Platform: xử lý mọi gap về signing/admission/runtime; không chuyển quyền
  triển khai production sang CDO07.
