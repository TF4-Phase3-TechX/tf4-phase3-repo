# [AUDIT-CDO07-MANDATE10-02] Phối hợp triển khai admission enforcement cho Directive #10

**Trạng thái:** TO DO  
**Reporter:** CDO07 Audit — Task 10  
**Primary owner đề nghị:** CDO08 Security (policy và trust policy)  
**Co-owner đề nghị:** CDO04 Platform/Infra (Terraform, IRSA, GitOps và rollout)  
**Priority:** P0 — blocker nghiệm thu Directive #10  
**Deadline:** trước 12:00 ngày 20/07/2026  
**AWS account/region:** `511825856493` / `us-east-1`  
**EKS/ECR:** `techx-tf4-cluster` / `techx-corp`

## 1. Bối cảnh

Cluster hiện có native `ValidatingAdmissionPolicy` cho runtime hardening, nhưng policy
đó chỉ chặn `latest`/untagged và vẫn cho tag cố định chạy. Native CEL policy không tải
được Cosign signature/attestations từ ECR.

Directive #10 yêu cầu cluster reject image:

- không pin digest;
- không được ký bởi trusted GitHub Actions workflow;
- thiếu SLSA provenance;
- thiếu CycloneDX SBOM;
- thiếu Trivy vulnerability PASS attestation.

CDO07 không yêu cầu AWS write trực tiếp. Platform/Security triển khai qua Terraform và
GitOps; CDO07 nghiệm thu bằng positive/negative test.

Ticket này là **implementation dependency**, không phải yêu cầu cấp cluster-admin cho
auditor. Quyền admin repo của CDO07 không thể tạo IRSA role, cài admission controller
hoặc thay đổi cluster runtime.

## 2. Phân công đề nghị

| Owner | Trách nhiệm |
|---|---|
| CDO08 Security | Chốt trust boundary, issuer/subject, predicate và policy exception |
| CDO04 Platform/Infra | Terraform IRSA, Argo/GitOps, capacity/SLO rollout và rollback |
| CDO07 Audit | Review PR, chạy acceptance, lưu evidence; không tự apply production |

## 3. Giải pháp đề nghị

- Kyverno chart `3.8.1`, appVersion `1.18.1`.
- Kyverno `ImageValidatingPolicy`.
- Cosign keyless trust:

```text
issuer:
https://token.actions.githubusercontent.com

subject:
https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main
```

- Private ECR authentication bằng Amazon credential helper và IRSA.
- Cosign `v3.0.6` new bundle format, signature/attestations lưu bằng OCI 1.1 referrers
  để không xung đột ECR tag immutability.
- `spec.failurePolicy: Fail`.
- `spec.validationActions: [Deny]` khi nghiệm thu; `Audit` chỉ dùng cho preflight ngắn.

Kyverno `v1.18.1` dùng Cosign `v3.0.6` và có code auto-detect bundle v3. Dù vậy owner
phải chạy preflight thực tế với một digest trong private ECR trước khi bật `Deny` ở
production; static compatibility không thay thế integration test.

## 4. Terraform/IRSA yêu cầu

Tạo role:

```text
tf4-kyverno-ecr-read
```

Trust policy phải giới hạn đúng EKS OIDC provider và Kyverno admission-controller
ServiceAccount, không trust toàn namespace hoặc toàn cluster.

Permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EcrAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "ReadTechxImagesAndAttestations",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:us-east-1:511825856493:repository/techx-corp"
    }
  ]
}
```

Không cấp:

- `ecr:PutImage`;
- layer upload;
- delete image/repository;
- wildcard ECR repository ngoài `techx-corp`.

## 5. GitOps/Argo CD yêu cầu

Trong `tf4-phase3-gitops-manifests`:

1. AppProject thêm exact Kyverno Helm repository.
2. Thêm destination namespace `kyverno`.
3. Whitelist đúng CRDs, webhook, RBAC và Kyverno policy resources cần thiết.
4. Tạo Argo Application pin chart `3.8.1`.
5. Không dùng `targetRevision: main`, `HEAD`, `latest` hoặc semver range.
6. Admission controller:
   - 3 replicas;
   - PDB;
   - topology spread/anti-affinity;
   - resource requests/limits;
   - ServiceAccount annotation IRSA.
7. Tắt background/cleanup/report controllers nếu policy không dùng để giảm cost.
8. Không prune/xóa native runtime hardening VAP của Mandate #5.

## 6. Policy behavior bắt buộc

Policy production phải:

- match app workload controllers và Pod;
- `validationConfigurations.required: true`;
- `validationConfigurations.verifyDigest: true`;
- `validationConfigurations.mutateDigest: false`, không âm thầm đổi tag;
- `credentials.providers: [amazon]`;
- verify Cosign signature;
- verify exact issuer/subject;
- require:
  - SLSA provenance;
  - CycloneDX SBOM;
  - Trivy `vuln` attestation;
- vulnerability attestation phải có HIGH=0 và CRITICAL=0;
- dùng Amazon registry credential helper;
- fail-closed khi registry/verification timeout;
- không cho app owner tự gắn bypass label;
- `validationActions: [Deny]`, không ở `Audit`/`Warn` khi bàn giao.

Namespace rollout đầu:

```text
techx-supply-chain-test
techx-tf4
```

Sau inventory/mirror, mở rộng tới các workload namespaces còn lại.

`kube-system` và `kyverno` có thể exclude để tránh bootstrapping deadlock. Mọi
exception khác cần ADR có owner, lý do, compensating control và review date.

## 7. SLO và rollout

1. Capture storefront/checkout baseline.
2. Install controller chưa có enforce policy.
3. Health check cả 3 admission replicas.
4. Audit preflight tối đa 30 phút.
5. Sửa/mirror mọi image vi phạm.
6. Chuyển `validationActions` sang `[Deny]`.
7. Chạy signed positive test.
8. Chạy unsigned/unscanned negative test.
9. Theo dõi error rate, latency, restart, webhook latency và admission errors ít nhất 15 phút.

Nếu phải hạ policy về `Audit` do sự cố, task chưa được tính Done cho tới khi sửa và
đưa lại `[Deny]`.

## 8. Acceptance criteria

- [ ] IRSA role tồn tại và trust đúng ServiceAccount.
- [ ] Kyverno đọc được Cosign artifacts trong private ECR.
- [ ] Preflight chứng minh Kyverno verify được Cosign v3 OCI referrers trong ECR
      `IMMUTABLE` trước khi rollout production.
- [ ] Kyverno admission có tối thiểu 3 ready replicas.
- [ ] Webhook failure policy là `Fail`.
- [ ] Trusted signed image theo digest được admit.
- [ ] Tag-only image bị reject.
- [ ] Unsigned digest bị reject.
- [ ] Digest có signature nhưng thiếu vuln/SBOM/provenance bị reject.
- [ ] Image ký bởi workflow/issuer khác bị reject.
- [ ] Policy có `validationActions: [Deny]` khi bàn giao.
- [ ] Storefront/checkout SLO không bị vi phạm.
- [ ] Flagd vẫn enabled và hoạt động; chỉ image reference được mirror/pin nếu cần.

## 9. Evidence CDO07 sẽ thu

```powershell
kubectl -n kyverno get deploy,pod,pdb
kubectl get validatingwebhookconfigurations
kubectl get imagevalidatingpolicies -o yaml
kubectl apply --dry-run=server -f unsigned-image-negative-test.yaml
kubectl -n techx-tf4 get pods -o json
```

CDO07 sẽ lưu output, policy, negative rejection, positive admission và SLO
before/after trong `docs/audit/evidence/mandate-10/`.
