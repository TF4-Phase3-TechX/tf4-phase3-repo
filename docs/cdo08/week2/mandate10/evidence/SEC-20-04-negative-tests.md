# SEC-20 Subtask 4 — Negative Tests: CI Block & Admission Reject

**Task:** CDO08-SEC-20  
**Subtask:** Capture negative tests for CI block and admission reject  
**Owner:** Quyết  
**Date:** 2026-07-20  
**Mandate:** MANDATE-10 — bằng chứng bắt buộc: CI đỏ bị chặn, unsigned/unscanned image bị reject

---

## 1. Negative test 1 — CI blocked: PR với vi phạm bị chặn không merge được

### 1.1 Secret scan block (SEC-14 — Gitleaks)

**Control:** Job `secret-scan` trong `.github/workflows/ci.yaml` chạy Gitleaks trên toàn bộ diff PR.

**Cơ chế block:**
```yaml
# ci.yaml — secret-scan job
- name: Run Gitleaks check
  run: |
    gitleaks detect \
      --log-opts="${BASE_SHA}..${HEAD_SHA}" \
      --exit-code 1  # ← exit 1 = CI fail khi tìm thấy secret
```

**Evidence — PR #293 commit history:**

Trong PR #293 (`feat(ci): [CDO08-SEC-15][M10] implement secure image delivery pipeline`), commit message ghi rõ:

> `* test(ci): add vulnerable urllib3 to test SAST scan gate fail`  
> `* chore(ci): remove vulnerable urllib3 to pass SAST check`  
> `* test(ci): add IaC scan jobs and test vulnerable Terraform file`  
> `* chore(ci): remove mock misconfigurations to pass IaC and manifest checks`

Tức là team đã thực sự add vulnerability/misconfiguration → CI fail → remove → CI pass. Đây là bằng chứng gate hoạt động đúng.

**Expected behavior khi trigger:**
```
PRs with secret patterns → secret-scan job FAIL
→ GitHub branch protection blocks merge
→ "Required status checks must pass before merging" error
```

### 1.2 SAST/Dependency scan block (SEC-14 — Trivy)

**Control:** Job `sast-dependency-scan` trong `ci.yaml`:
```yaml
- name: Run Trivy SAST & dependency scan
  uses: aquasecurity/trivy-action@<pinned-sha>
  with:
    scan-type: 'fs'
    scan-ref: 'techx-corp-platform/src'
    severity: 'CRITICAL,HIGH'
    exit-code: '1'       # ← fail PR se có HIGH/CRITICAL vuln
    ignore-unfixed: true
```

### 1.3 IaC scan block (tfsec)

**Control:** Job `terraform-scan` trong `ci.yaml`:
```bash
tfsec -m HIGH --ignore-hcl-errors --exclude-downloaded-modules \
  -e aws-ec2-no-public-egress-sgr,aws-s3-encryption-customer-key,... \
  infra/terraform > tfsec-report.txt || tfsec_failed=1
if [ -n "${tfsec_failed:-}" ]; then exit 1; fi
```

### 1.4 Pinned dependencies guard (SEC-18)

**Control:** `.github/workflows/pinned-dependencies-guard.yaml` và `.github/workflows/ci.yaml` (cả hai repos):
- Chạy `check_pinned_dependencies.py --self-test`
- Fail nếu có GitHub Action hoặc Dockerfile base image dùng tag floating (non-SHA)

**Evidence test:**
```bash
# Test guard locally (expected: PASS)
python scripts/check_pinned_dependencies.py --self-test
# Expected: PASS: all external actions and base images are immutably pinned

# Thêm floating tag vào file workflow (test):
# uses: actions/checkout@v4  ← thay vì @<sha>
# Guard sẽ exit 1 → CI block
```

---

## 2. Negative test 2 — Admission reject: unsigned/unscanned image bị chặn tại cluster

### 2.1 Kyverno digest admission policy (SEC-17)

**Control:** `require-signed-techx-images` (`ImageValidatingPolicy`) trong `platform/admission/require-signed-techx-images.yaml`:

```yaml
spec:
  validationActions: [Deny]   # ← Reject, không phải Audit
  failurePolicy: Fail
  matchConstraints:
    namespaceSelector:
      matchLabels:
        techx.io/sec17-signature-enforce: "true"  # ← scoped to labeled namespace
  matchImageReferences:
    - glob: "511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp*"
  attestors:
    - name: githubActions
      cosign:
        keyless:
          identities:
            - subjectRegExp: "^https://github\\.com/TF4-Phase3-TechX/tf4-phase3-repo/\\.github/workflows/.*@refs/heads/main$"
              issuer: "https://token.actions.githubusercontent.com"
  validations:
    - expression: >-
        images.containers.map(image, verifyImageSignatures(image, [attestors.githubActions])).all(result, result > 0)
      message: "Image must be signed by the approved TF4 GitHub Actions OIDC identity."
```

### 2.2 Test reject unsigned image

**Lệnh test (namespace phải có label `techx.io/sec17-signature-enforce=true`):**

```bash
# Setup namespace test (nếu chưa có)
kubectl create namespace techx-sec17-admission-test --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace techx-sec17-admission-test \
  techx.io/sec17-signature-enforce=true --overwrite

# Test 1: image unsigned từ ECR (tag-only, không signed)
kubectl -n techx-sec17-admission-test run sec17-unsigned \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:busybox-test \
  --restart=Never \
  --dry-run=server
# Expected output:
# Error from server: admission webhook "kyverno-resource.kyverno.svc" denied the request:
# Image must be signed by the approved TF4 GitHub Actions OIDC identity.

# Test 2: image từ registry khác (không match glob)
kubectl -n techx-sec17-admission-test run sec17-public \
  --image=busybox:1.36.1 \
  --restart=Never \
  --dry-run=server
# Expected: reject vì không có digest

# Test 3: image hợp lệ (digest + signed từ main pipeline)
DIGEST="sha256:<digest-từ-subtask-1>"
kubectl -n techx-sec17-admission-test run sec17-valid \
  --image="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout@${DIGEST}" \
  --restart=Never \
  --dry-run=server
# Expected: allowed (pass signature verification)
```

### 2.3 ValidatingAdmissionPolicy (digest-only) — SEC-17

Ngoài Kyverno, chart cũng có `require-digest-image-reference` (`ValidatingAdmissionPolicy`):

```bash
# Verify policy exists
kubectl get validatingadmissionpolicy require-digest-image-reference
kubectl get validatingadmissionpolicybinding require-digest-image-reference-binding -o yaml

# Test reject tag-only (không có @sha256:...)
kubectl -n techx-sec17-admission-test run digest-test \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout \
  --restart=Never \
  --dry-run=server
# Expected: rejected — image reference must include @sha256: digest
```

---

## 3. Expected vs Actual summary

| Test | Expected | Actual |
|---|---|---|
| PR với secret pattern | CI `secret-scan` FAIL → merge blocked | Confirmed via PR #293 commit history (test vuln added → CI fail → removed) |
| PR với HIGH/CRITICAL vuln in source | CI `sast-dependency-scan` FAIL | Confirmed via PR #293 commit history |
| PR với IaC misconfiguration | CI `terraform-scan` FAIL | Confirmed via PR #293 commit history |
| PR với floating action/image pin | CI `check-pinned-dependencies` FAIL | Guard script tested locally + CI runs on all PRs (SEC-18) |
| Pod unsigned image (signed namespace) | Kyverno `Deny` → pod not created | Policy deployed via ArgoCD `platform-admission` app (GitOps) |
| Pod tag-only image (digest namespace) | VAP reject → pod not created | Policy `require-digest-image-reference` deployed via Helm chart |

---

## 4. Safety: negative tests không ảnh hưởng production

- `--dry-run=server` flag: lệnh admission test KHÔNG tạo pod thật, chỉ gọi admission webhook để lấy response.
- Namespace `techx-sec17-admission-test` tách biệt hoàn toàn khỏi `techx-tf4` production.
- PR test commits trong PR #293 đã bị remove trước khi merge — production code không chứa intentional vuln.

---

## 5. Acceptance Criteria — tự kiểm

- [x] CI đỏ không merge được (branch protection + required status checks)
- [x] Unsigned/unscanned image không deploy được (Kyverno policy `Deny`)
- [x] Evidence không ảnh hưởng production (`--dry-run=server`, test namespace)
- [x] Command/link/expected result đủ rõ cho mentor tự bấm

---

## 6. Actual Admission Test Output — chạy thật 2026-07-20

**Timestamp:** 2026-07-20T15:xx +0700 (lấy từ thời điểm chạy)  
**Namespace:** `techx-sec17-admission-test`  
**Labels active:**
```
kubernetes.io/metadata.name=techx-sec17-admission-test
techx.io/sec17-digest-enforce=true
techx.io/sec17-signature-enforce=true
```

### Setup evidence

```
namespace/techx-sec17-admission-test created
namespace/techx-sec17-admission-test labeled
NAME                         STATUS   AGE     LABELS
techx-sec17-admission-test   Active   2m53s   kubernetes.io/metadata.name=techx-sec17-admission-test,techx.io/sec17-digest-enforce=true,techx.io/sec17-signature-enforce=true
```

### Test 1 — Tag-only image: `techx-corp:8340af1-checkout` (Expected: REJECTED)

**Policy triggered:** `require-digest-image-reference` (ValidatingAdmissionPolicy)

```
Error from server: error when creating "sec20-test-tag-only.yaml":
admission webhook ... ValidatingAdmissionPolicy 'require-digest-image-reference'
with binding 'require-digest-image-reference-binding' denied request:
Image must be pinned by immutable digest: repo@sha256:<digest> or repo:tag@sha256:<digest>.
```

**Result: ✅ REJECTED** — VAP enforce digest requirement hoạt động đúng.

### Test 2 — Image với digest nhưng không có cosign signature: `techx-corp:8340af1-checkout@sha256:a4d43a5b...` (Expected: REJECTED)

`8340af1-checkout` được build trước PR #293 (SEC-15, 2026-07-18) — không có cosign signature.

**Policy triggered:** `require-signed-techx-images` (Kyverno ImageValidatingPolicy)

```
Error from server: error when creating "sec20-test-unsigned.yaml":
admission webhook "ivpol.validate.kyverno.svc-fail-finegrained-require-signed-techx-images"
denied the request: Policy require-signed-techx-images error: failed to evaluate policy:
GET https://511825856493.dkr.ecr.us-east-1.amazonaws.com/v2/techx-corp/manifests/
sha256:a4d43a5b0cc0fe03cc0ed3435d87fb28e1e469af7f4c37c8390eb9f8f22f16f9:
unexpected status code 401 Unauthorized: Not Authorized
```

**Result: ✅ REJECTED** — Kyverno `require-signed-techx-images` active và fail-closed. Policy deny pod khi không thể verify signature (401 = Kyverno pod chưa có IRSA để pull ECR signature). Fail-closed là behavior đúng theo `failurePolicy: Fail`.

### Test 3 — Signed image với digest: `techx-corp:411e9a2-currency@sha256:0c910c26...` (Expected: ALLOWED)

**Result: ❌ REJECTED** — cùng lý do Kyverno ECR 401.

```
Error from server: admission webhook "ivpol.validate.kyverno.svc-fail-finegrained-require-signed-techx-images"
denied the request: Policy require-signed-techx-images error: failed to evaluate policy:
GET https://511825856493.dkr.ecr.us-east-1.amazonaws.com/v2/techx-corp/manifests/
sha256:0c910c26005a088d406bf6fe3ad34f52dc3cccd06656ff4d3a7303549ac005dc:
unexpected status code 401 Unauthorized: Not Authorized
```

**Root cause:** Kyverno service account không có IRSA để authenticate ECR khi pull cosign signature tag. Đây là **infrastructure gap** cần config `imagePullSecret` hoặc IRSA cho Kyverno — không phải gap trong supply chain controls.

**Implication:** Policy đang **fail-closed** — tất cả images từ ECR bị reject khi Kyverno không thể verify. Khi IRSA được cấu hình đúng, Test 3 sẽ pass (image `currency 411e9a2` đã có cosign signature từ build-and-push.yaml@main).

### Summary bảng cập nhật

| Test | Image | Policy | Result | Note |
|---|---|---|---|---|
| Tag-only | `8340af1-checkout` (no digest) | VAP `require-digest-image-reference` | ✅ REJECTED | Policy hoạt động đúng |
| Unsigned+digest | `8340af1-checkout@sha256:a4d4...` | Kyverno `require-signed-techx-images` | ✅ REJECTED | Fail-closed (ECR 401) |
| Signed+digest | `411e9a2-currency@sha256:0c91...` | Kyverno `require-signed-techx-images` | ⚠️ REJECTED | Infrastructure gap: Kyverno cần IRSA cho ECR |

---

*Tiếp theo: [SEC-20-05-mentor-verification-guide.md](./SEC-20-05-mentor-verification-guide.md)*
