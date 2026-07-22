# [AUDIT-CDO07-MANDATE10-01] Yêu cầu quyền đọc ECR Provenance

- Trạng thái: ACTIVE - AccessDenied đã được tái hiện sau khi xác thực SSO
- Reporter: CDO07 Audit - Task 46 / MANDATE-10
- Owner cần Tech Lead điều phối: IAM/Cloud owner quản lý Permission Set CDO07
- Priority: P0 - blocker truy vết Pod về Source
- Ngày cập nhật: 2026-07-21
- AWS account/region: 511825856493 / us-east-1
- ECR repository: techx-corp
- Audit role: TF4-AuditReadOnlyAndAnalyze
- Principal: arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/trieu.nguyen

## 1. Mục đích

CDO07 cần kiểm chứng chuỗi provenance của một image đang chạy:

~~~text
Pod imageID
  -> ECR image digest
  -> ECR OCI referrers
  -> Cosign signature
  -> Provenance/SBOM/vulnerability attestations
  -> source commit + PR + approvers
~~~

Ticket này chỉ xin quyền đọc có giới hạn trong ECR repository techx-corp. Không yêu cầu Audit cấu hình admission policy, thay đổi cluster, deploy workload hoặc ghi vào GitOps.

## 2. Preflight đã thực hiện

AWS identity đã xác nhận:

~~~text
Account: 511825856493
Role: AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882
User: trieu.nguyen
~~~

EKS cluster đã xác nhận:

~~~text
Cluster: techx-tf4-cluster
Status: ACTIVE
Kubernetes: 1.34
Namespace: techx-tf4
~~~

Pod runtime evidence:

~~~text
Pod: currency-7d75c44fb-gc9db
Container: currency
Image: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:411e9a2-currency
Image digest: sha256:0c910c26005a088d406bf6fe3ad34f52dc3ccd06656ff4d3a7303549ac005dc
~~~

## 3. Blocker thực tế

Lệnh read-only sau đã bị từ chối:

~~~powershell
aws ecr describe-images --repository-name techx-corp --image-ids "imageDigest=sha256:0c910c26005a088d406bf6fe3ad34f52dc3ccd06656ff4d3a7303549ac005dc" --region us-east-1
~~~

Lỗi thực tế là AccessDenied cho action ecr:DescribeImages trên resource:

~~~text
arn:aws:ecr:us-east-1:511825856493:repository/techx-corp
~~~

Đây là lỗi effective permission sau khi SSO đã đăng nhập thành công, không phải ExpiredToken, lỗi kube-context, DNS hoặc network timeout.

Evidence local:

~~~text
D:\evidence\M10\03-pod-runtime-image-digest.json
D:\evidence\M10\03-pod-runtime-image-digest.png
D:\evidence\M10\04-ecr-describe-images-access-denied.png
~~~

## 4. Policy read-only đề nghị cấp

Đề nghị thêm policy sau vào Permission Set/role TF4-AuditReadOnlyAndAnalyze:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Mandate10AuditReadProvenanceArtifacts",
      "Effect": "Allow",
      "Action": [
        "ecr:DescribeImages",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Resource": "arn:aws:ecr:us-east-1:511825856493:repository/techx-corp"
    }
  ]
}
~~~

Mục đích:

- ecr:DescribeImages: đọc tag, digest, thời điểm push và metadata.
- ecr:BatchGetImage: đọc OCI manifest.
- ecr:GetDownloadUrlForLayer: tải layer chứa signature/attestation payload.
- ecr:BatchCheckLayerAvailability: kiểm tra layer trước khi OCI client đọc artifact.

ecr:GetAuthorizationToken không nằm trong policy delta vì Permission Set hiện đã có quyền này và action không hỗ trợ scope theo repository.

Nếu sau khi cấp policy, lệnh aws ecr list-image-referrers trả AccessDenied riêng cho action này, chỉ bổ sung action sau và xác nhận với IAM owner:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "Mandate10AuditListImageReferrers",
      "Effect": "Allow",
      "Action": [
        "ecr:ListImageReferrers"
      ],
      "Resource": "arn:aws:ecr:us-east-1:511825856493:repository/techx-corp"
    }
  ]
}
~~~

## 5. Quyền tuyệt đối không yêu cầu

Không cấp cho CDO07:

- ecr:PutImage
- ecr:BatchDeleteImage
- ecr:DeleteRepository
- ecr:InitiateLayerUpload
- ecr:UploadLayerPart
- ecr:CompleteLayerUpload
- ECR repository khác ngoài techx-corp
- Kubernetes Pod/Deployment create, update, patch hoặc delete
- Kubernetes Secret read
- pods/exec
- cluster-admin
- Terraform apply
- GitOps write trên production
- Quyền tạo/cập nhật Branch Protection

## 6. Acceptance criteria

- [ ] IAM owner xác nhận Permission Set đã áp dụng policy.
- [ ] AWS identity vẫn là account 511825856493 và role Audit.
- [ ] aws ecr describe-images đọc được exact digest của Pod.
- [ ] ECR digest khớp tuyệt đối với imageID của Pod.
- [ ] aws ecr list-image-referrers đọc được referrers hoặc có raw AccessDenied riêng để xử lý.
- [ ] Cosign đọc/verify được signature và attestations nếu artifact tồn tại.
- [ ] Audit vẫn không có ECR write hoặc Kubernetes workload write.
- [ ] Raw before/after output đã redact và lưu vào evidence pack.

## 7. Cách kiểm tra sau khi IAM cấp quyền

~~~powershell
aws sts get-caller-identity

aws ecr describe-images --repository-name techx-corp --image-ids "imageDigest=sha256:0c910c26005a088d406bf6fe3ad34f52dc3ccd06656ff4d3a7303549ac005dc" --region us-east-1 --output json

aws ecr list-image-referrers --repository-name techx-corp --subject-id "sha256:0c910c26005a088d406bf6fe3ad34f52dc3ccd06656ff4d3a7303549ac005dc" --region us-east-1
~~~

Sau khi ECR read pass, Audit tiếp tục verify Cosign signature, custom provenance, CycloneDX SBOM, scan artifacts, Commit/PR/approvers và Branch Protection.

## 8. Trách nhiệm

- IAM/Cloud owner: kiểm tra effective permission và chỉ apply policy delta tối thiểu.
- CDO07 Audit: cung cấp raw AccessDenied, chạy lại preflight và xác nhận least privilege.
- Security/Platform: xử lý signing/admission/runtime nếu có gap.
- Audit: không nhận quyền triển khai production hoặc quyền ghi artifact.

## 9. Kết luận tạm thời

Pod-to-digest tracing đã hoàn thành. Provenance chain chưa thể hoàn tất vì Audit role bị deny ecr:DescribeImages trên đúng repository cần kiểm tra.

Ticket chỉ đóng sau khi ECR read access hoạt động và Audit thu được evidence SBOM, provenance, scan, signature, Commit, PR approver và Branch Protection.
