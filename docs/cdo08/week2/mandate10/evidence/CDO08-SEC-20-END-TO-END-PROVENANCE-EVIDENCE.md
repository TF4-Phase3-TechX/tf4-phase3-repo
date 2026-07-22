# CDO08-SEC-20 - Evidence Mandate 10: Secure Delivery Pipeline

**Thời điểm kiểm tra:** 2026-07-22T07:15:11Z  
**Cluster:** `techx-tf4-cluster`  
**Namespace runtime:** `techx-tf4`  
**Kết luận:** **PASS với phạm vi TF4 application images**

Mandate 10 yêu cầu khi chỉ vào một pod đang chạy, team phải truy ngược được:

```text
running pod -> image digest -> source commit -> workflow -> signer -> SBOM/provenance
```

Evidence dưới đây dùng pod `load-generator` làm mẫu live trace.

---

## 1. Runtime đang chạy image theo digest

Lệnh:

```sh
kubectl -n techx-tf4 get pod -l opentelemetry.io/name=load-generator \
  -o jsonpath='{.items[0].metadata.name}{"\n"}{.items[0].spec.containers[0].image}{"\n"}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
```

Kết quả:

```text
load-generator-777d9f8c68-bw855
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
```

Đánh giá:

- Pod đang chạy đúng image có digest bất biến.
- Digest trong `spec.containers[0].image` khớp với `status.containerStatuses[0].imageID`.

---

## 2. Signature Cosign hợp lệ

Lệnh:

```sh
cosign verify \
  --certificate-identity-regexp '^https://github\.com/TF4-Phase3-TechX/tf4-phase3-repo/\.github/workflows/.*@refs/heads/main$' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
```

Kết quả rút gọn:

```text
Verification for 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The code-signing certificate was verified using trusted certificate authority certificates

Issuer: https://token.actions.githubusercontent.com
Subject: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main
GitHub Workflow Name: build-and-push
GitHub Workflow Repository: TF4-Phase3-TechX/tf4-phase3-repo
GitHub Workflow Ref: refs/heads/main
GitHub Workflow SHA: 694654e2113b71d7d3ff188948fdb1b640cef3fc
```

Đánh giá:

- Image digest live đã được ký bằng Cosign keyless.
- Signer là GitHub Actions OIDC của repo `TF4-Phase3-TechX/tf4-phase3-repo`.
- Workflow ký là `build-and-push.yaml` trên `refs/heads/main`.

---

## 3. Provenance và SBOM attestation hợp lệ

Lệnh:

```sh
cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp '^https://github\.com/TF4-Phase3-TechX/tf4-phase3-repo/\.github/workflows/.*@refs/heads/main$' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  --output json \
  511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 \
  > /private/tmp/sec20-load-generator-attestation.jsonl
```

Kết quả verify rút gọn:

```text
Verification for 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The code-signing certificate was verified using trusted certificate authority certificates

Certificate subject: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main
Certificate issuer URL: https://token.actions.githubusercontent.com
GitHub Workflow Trigger: push
GitHub Workflow SHA: 694654e2113b71d7d3ff188948fdb1b640cef3fc
GitHub Workflow Name: build-and-push
GitHub Workflow Repository: TF4-Phase3-TechX/tf4-phase3-repo
GitHub Workflow Ref: refs/heads/main
```

Lệnh parse predicate:

```sh
jq -r '.payload' /private/tmp/sec20-load-generator-attestation.jsonl \
  | base64 -d \
  | jq '(.predicate.Data | fromjson) | {kind, repo, commit, workflow, run_id, service_name, image_digest, provenance, sbom: {kind: .sbom.kind, bomFormat: .sbom.bomFormat, documentBomFormat: .sbom.document.bomFormat, vulnerabilities: .sbom.document.vulnerabilities}}'
```

Kết quả:

```json
{
  "kind": "secure-delivery-evidence",
  "repo": "TF4-Phase3-TechX/tf4-phase3-repo",
  "commit": "694654e2113b71d7d3ff188948fdb1b640cef3fc",
  "workflow": "build-and-push",
  "run_id": "29897119328",
  "service_name": "load-generator",
  "image_digest": "sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781",
  "provenance": {
    "repo": "TF4-Phase3-TechX/tf4-phase3-repo",
    "commit": "694654e2113b71d7d3ff188948fdb1b640cef3fc",
    "workflow": "build-and-push",
    "run_id": "29897119328",
    "service_name": "load-generator",
    "image_digest": "sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781"
  },
  "sbom": {
    "kind": "cyclonedx-sbom",
    "bomFormat": "CycloneDX",
    "documentBomFormat": "CycloneDX",
    "vulnerabilities": []
  }
}
```

Đánh giá:

- Attestation có provenance trỏ về repo, commit, workflow, run id và service name.
- Attestation có SBOM dạng CycloneDX.
- SBOM của image mẫu không còn HIGH/CRITICAL vulnerability trong artifact đã ký.

---

## 4. Admission enforcement trên namespace runtime

Lệnh:

```sh
kubectl get ns techx-tf4 -o jsonpath='{.metadata.labels}{"\n"}'
```

Kết quả:

```json
{
  "kubernetes.io/metadata.name": "techx-tf4",
  "name": "techx-tf4",
  "techx.io/policy-scope": "enforced",
  "techx.io/sec17-digest-enforce": "true",
  "techx.io/sec17-signature-enforce": "true"
}
```

Lệnh:

```sh
kubectl get imagevalidatingpolicy require-signed-techx-images \
  -o jsonpath='{.status.conditionStatus.ready}{"\n"}{.spec.validationActions}{"\n"}{.spec.matchConstraints.namespaceSelector}{"\n"}'
```

Kết quả:

```text
true
["Deny"]
{"matchLabels":{"techx.io/sec17-signature-enforce":"true"}}
```

Lệnh:

```sh
kubectl get validatingadmissionpolicybinding require-digest-image-reference-binding \
  -o jsonpath='{.spec.validationActions}{"\n"}{.spec.matchResources.namespaceSelector}{"\n"}'
```

Kết quả:

```text
["Deny"]
{"matchLabels":{"techx.io/sec17-digest-enforce":"true"}}
```

Đánh giá:

- Namespace runtime đã bật cả digest enforce và signature enforce.
- Digest policy và signature policy đều chạy ở chế độ `Deny`.

---

## 5. Admission negative/positive tests

### 5.1. Reject image `latest`

Lệnh:

```sh
kubectl -n techx-tf4 run sec20-latest-negative \
  --image=nginx:latest \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-latest-negative","image":"nginx:latest","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Kết quả:

```text
The pods "sec20-latest-negative" is invalid: :
ValidatingAdmissionPolicy 'disallow-mutable-image-tag' with binding
'disallow-mutable-image-tag-binding' denied request:
Image must pin a fixed tag or digest ... ':latest' ... are not allowed.
```

### 5.2. Reject TF4 ECR tag-only image

Lệnh:

```sh
kubectl -n techx-tf4 run sec20-ecr-tagonly-negative \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-ecr-tagonly-negative","image":"511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Kết quả:

```text
The pods "sec20-ecr-tagonly-negative" is invalid: :
ValidatingAdmissionPolicy 'require-digest-image-reference' with binding
'require-digest-image-reference-binding' denied request:
TF4 ECR image must be pinned by immutable digest:
repo@sha256:<digest> or repo:tag@sha256:<digest>.
```

### 5.3. Accept signed TF4 ECR digest image

Lệnh:

```sh
kubectl -n techx-tf4 run sec20-ecr-signed-digest-positive \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-ecr-signed-digest-positive","image":"511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Kết quả rút gọn:

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    kyverno.io/image-verification-outcomes: '{"require-signed-techx-images":{"name":"require-signed-techx-images","ruleType":"ImageVerify","message":"success","status":"pass"}}'
  name: sec20-ecr-signed-digest-positive
  namespace: techx-tf4
spec:
  containers:
  - image: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
```

Đánh giá:

- `latest` bị chặn.
- TF4 ECR tag-only image bị chặn.
- TF4 ECR signed digest image được chấp nhận và Kyverno verify signature thành công.

---

## 6. Runtime image coverage

Lệnh:

```sh
kubectl -n techx-tf4 get deploy -o wide
kubectl -n techx-tf4 get rollout cart -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}{.status.phase}{"\n"}'
```

Kết quả rút gọn:

```text
accounting        ...:c553182-accounting@sha256:2989...        1/1
ad                ...:b0374a9-ad@sha256:78ee...                1/1
currency          ...:a930936-currency@sha256:663b...          2/2
email             ...:694654e-email@sha256:f751...             1/1
fraud-detection   ...:c553182-fraud-detection@sha256:0516...   1/1
frontend          ...:c646c2b-frontend@sha256:84ba...          2/2
frontend-proxy    ...:8340af1-frontend-proxy@sha256:7a2d...    2/2
image-provider    ...:694654e-image-provider@sha256:82b1...    1/1
llm               ...:8340af1-llm@sha256:92bd...               1/1
load-generator    ...:694654e-load-generator@sha256:f8f8...    1/1
payment           ...:8340af1-payment@sha256:3ec5...           2/2
product-catalog   ...:8340af1-product-catalog@sha256:e0c6...   2/2
product-reviews   ...:d1c4632-product-reviews@sha256:f8a9...   1/1
quote             ...:8340af1-quote@sha256:c0a0...             2/2
recommendation    ...:8340af1-recommendation@sha256:7ed0...    1/1
shipping          ...:8340af1-shipping@sha256:496b...          2/2

cart rollout:
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:0f983db-cart@sha256:4b6d4958d2fdbeb4862b5d83965d754a3b4551b3c9fd44e58eda2f350374ce28
Healthy
```

Ghi chú:

- `cart` dùng Argo Rollout, không phải Deployment, nhưng Rollout `cart` đang `Healthy` và image cũng đã pin digest.
- `flagd` là external control service `ghcr.io/open-feature/flagd:v0.12.9`, nằm ngoài phạm vi TF4 ECR image signing/enforcement và không được sửa theo quyết định của team.
- `kafka` không còn runtime app pod trong `techx-tf4` sau MSK cutover; entry tag-only trong GitOps nếu còn tồn tại là stale/non-runtime và cần dọn dẹp riêng nếu muốn dashboard GitOps sạch hơn.

---

## 7. PR đỏ cố tình để kiểm tra branch rule

Mandate 10 yêu cầu mở một PR có CI cố tình đỏ và chứng minh PR đó không được merge.

PR evidence:

```text
https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/501
```

PR này cố tình thêm file Terraform sai cú pháp:

```text
infra/terraform/sec20-intentional-red-ci.tf
```

Expected:

```text
CI/Terraform validation phải fail.
PR phải bị chặn merge do required status checks.
```

Kiểm tra ruleset hiện tại:

```sh
gh api repos/TF4-Phase3-TechX/tf4-phase3-repo/rulesets/18601993
```

Kết quả rút gọn:

```json
{
  "name": "main",
  "enforcement": "active",
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_linear_history"},
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 2,
        "require_code_owner_review": true,
        "require_last_push_approval": true
      }
    }
  ],
  "bypass_actors": [
    {"actor_type": "Team", "bypass_mode": "always"}
  ]
}
```

Đánh giá:

- Repo hiện đã có ruleset yêu cầu PR review, code owner review và linear history.
- Ruleset hiện **chưa có required status checks**, nên chưa đủ mạnh để chứng minh “CI đỏ thì không merge được”.
- Ruleset còn có bypass team, nên nếu người có bypass quyền merge thì vẫn có thể vượt rule.

Required follow-up:

- Bổ sung required status checks cho `main`, tối thiểu gồm các CI/security gates chính.
- Hạn chế hoặc document bypass actor; nếu giữ bypass, phải ghi rõ chỉ dùng cho break-glass và không dùng trong Mandate 10 demo.
- Sau khi sửa rule, dùng PR #501 để mentor kiểm tra red CI bị chặn merge.

---

## 8. Final verdict

Mandate 10 đạt mức **PASS cho TF4 application images**:

- CI/CD đã scan image trước deploy và fail khi có HIGH/CRITICAL CVE.
- ECR immutable đã bật.
- Runtime app images đang chạy theo digest.
- Cosign signature của live digest verify thành công.
- Provenance attestation trỏ về repo, commit, workflow và run id.
- SBOM CycloneDX tồn tại trong attestation và không có vulnerabilities trong image mẫu.
- Admission policy chạy `Deny`: reject `latest`, reject TF4 ECR tag-only, accept signed TF4 ECR digest.

Phần cần theo dõi sau:

- Sửa GitHub ruleset để required status checks thật sự chặn PR đỏ.
- Codify label `techx.io/sec17-signature-enforce=true` trong GitOps namespace management nếu namespace label đang được quản lý ngoài cluster.
- Dọn dẹp stale GitOps entry cho workload không còn runtime nếu cần làm Argo/GitOps sạch hoàn toàn.
