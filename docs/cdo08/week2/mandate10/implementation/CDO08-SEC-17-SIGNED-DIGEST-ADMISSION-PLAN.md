# CDO08-SEC-17 - Signed Digest Admission Plan

## Mục tiêu

SEC-17 bảo đảm cluster chỉ nhận image có tham chiếu immutable bằng digest và có thể kiểm tra chữ ký supply-chain trước khi workload chạy.

Task này xử lý phần còn thiếu sau SEC-16 và SEC-19:

- SEC-16 đã build, scan, sign, attest SBOM/provenance bằng Cosign.
- SEC-19 đã thêm cơ chế promote image tag kèm digest vào GitOps.
- SEC-17 thêm lớp admission để chặn image không đạt chuẩn ở Kubernetes API server.

## Trạng thái hiện tại

Runtime hardening admission hiện đã có `disallow-mutable-image-tag`, nhưng policy đó chỉ cấm `latest` và image không có tag. Nó vẫn cho phép image `repo:tag`.

Điều này chưa đủ cho Mandate 10 vì tag vẫn có thể bị đổi nội dung. Mandate 10 cần image chạy trong cluster phải trỏ tới artifact cụ thể bằng digest, ví dụ:

```text
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout@sha256:<digest>
```

## Quyết định triển khai

### 1. Dùng native ValidatingAdmissionPolicy để enforce digest-only

Chart thêm policy:

```text
require-digest-image-reference
```

Policy này reject Pod nếu container hoặc initContainer image không có `@sha256:<digest>`.

Binding hiện chỉ áp dụng cho namespace có label:

```text
techx.io/sec17-digest-enforce=true
```

Lý do không bật thẳng toàn production ngay:

- `environments/production/image-revisions.yaml` hiện vẫn còn workload tag-only.
- Nếu enforce toàn `techx-tf4` ngay, rollout production có thể bị chặn trước khi promotion PR ghi đủ digest.
- Staged scope cho phép tạo evidence reject/allow trong namespace test trước, rồi mở rộng sang production khi GitOps đã sẵn sàng.

### 2. Dùng Kyverno cho bước verify chữ ký Cosign

Kubernetes native `ValidatingAdmissionPolicy` chỉ kiểm tra được syntax/field bằng CEL. Nó không thể gọi registry/Rekor/Fulcio để verify chữ ký Cosign.

Vì vậy phần signature admission cần Kyverno `verifyImages` hoặc Sigstore policy-controller. Hướng được chọn là Kyverno vì:

- hỗ trợ `verifyImages` trực tiếp;
- phổ biến cho policy-as-code trong Kubernetes;
- có thể enforce theo namespace trước, rồi mở rộng dần;
- có thể kiểm tra keyless OIDC issuer/subject từ GitHub Actions.

## Điều kiện mở rộng sang production

Không đổi binding sang toàn `techx-tf4` cho tới khi đủ các điều kiện sau:

1. GitOps `image-revisions.yaml` có `imageOverride.digest` cho workload cần rollout.
2. Image tương ứng đã được SEC-16 sign bằng Cosign từ GitHub Actions OIDC.
3. Có evidence `cosign verify` pass với:
   - issuer: `https://token.actions.githubusercontent.com`;
   - identity regexp: `^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/.*@refs/heads/main$`.
4. Kyverno đã healthy và policy ở namespace test reject image unsigned/tag-only, allow signed digest image.
5. Có rollback/break-glass: chuyển binding về test namespace hoặc xóa binding nếu admission chặn nhầm.

## Evidence cần lấy

### Kiểm tra policy đã tồn tại

```sh
kubectl get validatingadmissionpolicy require-digest-image-reference
kubectl get validatingadmissionpolicybinding require-digest-image-reference-binding -o yaml
```

### Tạo namespace test

```sh
kubectl create namespace techx-sec17-admission-test --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace techx-sec17-admission-test techx.io/sec17-digest-enforce=true --overwrite
```

### Test reject image tag-only

```sh
kubectl -n techx-sec17-admission-test run sec17-tag-only \
  --image=busybox:1.36.1 \
  --restart=Never \
  --dry-run=server
```

Expected: request bị reject vì thiếu `@sha256:<digest>`.

### Test reject latest

```sh
kubectl -n techx-sec17-admission-test run sec17-latest \
  --image=busybox:latest \
  --restart=Never \
  --dry-run=server
```

Expected: request bị reject.

### Test allow digest image

Dùng một digest thật từ ECR đã được scan/sign:

```sh
kubectl -n techx-sec17-admission-test run sec17-digest \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:<tag>@sha256:<digest> \
  --restart=Never \
  --dry-run=server
```

Expected: request qua được digest policy. Nếu Kyverno signature policy đã bật, image cũng phải pass signature verification.

## Rollback

Nếu digest admission chặn nhầm workload:

```sh
kubectl delete validatingadmissionpolicybinding require-digest-image-reference-binding
```

Sau đó revert GitOps/chart change để Argo CD không tạo lại binding sai.

## Việc còn lại sau PR này

- Deploy Kyverno qua GitOps.
- Thêm Kyverno policy verify Cosign signature theo GitHub Actions OIDC.
- Chạy negative/positive test trong namespace test.
- Khi GitOps promotion có digest đầy đủ, mở rộng enforcement sang production namespace.
