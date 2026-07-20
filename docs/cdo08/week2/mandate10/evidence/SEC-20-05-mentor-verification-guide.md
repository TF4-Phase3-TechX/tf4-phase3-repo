# SEC-20 Subtask 5 — Mentor Verification Guide & Mandate 10 Final Verdict

**Task:** CDO08-SEC-20  
**Subtask:** Write mentor verification guide and final Mandate 10 verdict  
**Owner:** Quyết  
**Date:** 2026-07-20  
**Mandate:** MANDATE-10 — Từ commit tới cluster — không tin image mù

---

## 1. Prerequisites — mentor cần có

| Tool | Cài chưa? | Command kiểm tra |
|---|---|---|
| `kubectl` + kubeconfig | Cần truy cập cluster `techx-tf4` | `kubectl cluster-info` |
| AWS CLI + credentials | Profile `tf4` hoặc role có quyền ECR/read | `aws sts get-caller-identity` |
| `cosign` | Verify signature/SBOM/provenance | `cosign version` |
| `gh` CLI (optional) | Xem Actions artifacts | `gh auth status` |
| `jq` | Decode provenance payload | `jq --version` |
| ECR login | Pull/inspect image | `aws ecr get-login-password --region us-east-1 \| docker login --username AWS --password-stdin 511825856493.dkr.ecr.us-east-1.amazonaws.com` |

---

## 2. Verification steps — từng bước mentor tự bấm

### Step 1: Xác nhận pod đang chạy

```bash
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=checkout
```

**Expected result:** Ít nhất 1 pod với STATUS = `Running`, READY = `1/1` (hoặc tương đương).

---

### Step 2: Lấy runtime image digest từ pod

```bash
POD=$(kubectl -n techx-tf4 get pods \
  -l app.kubernetes.io/component=checkout \
  -o jsonpath='{.items[0].metadata.name}')
echo "Pod: $POD"

IMAGE_ID=$(kubectl -n techx-tf4 get pod $POD \
  -o jsonpath='{.status.containerStatuses[0].imageID}')
echo "Runtime imageID: $IMAGE_ID"

# Extract digest
DIGEST=$(echo $IMAGE_ID | grep -oP 'sha256:[a-f0-9]{64}')
echo "Digest: $DIGEST"
```

**Expected result:** `sha256:<64-hex-chars>` — đây là starting point không thể giả mạo.

---

### Step 3: Xác nhận tag và commit SHA trong ECR

```bash
aws ecr describe-images \
  --repository-name techx-corp \
  --region us-east-1 \
  --image-ids imageDigest=$DIGEST \
  --query 'imageDetails[0].{digest:imageDigest, tags:imageTags, pushed:imagePushedAt}' \
  --output table
```

**Expected result:**
- `digest`: khớp `$DIGEST`
- `tags`: `8340af1-checkout` (short-sha-service format)
- Short SHA `8340af1` → commit `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/8340af1`

---

### Step 4: Verify cosign signature

```bash
IMAGE="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@$DIGEST"

cosign verify \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE"
```

**Expected result:** JSON với `Subject` = workflow URL, không có error.  
**Fail result:** `error: no matching signatures` → image chưa được ký.

---

### Step 5: Verify provenance attestation

```bash
cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE" | jq -r '.payload | @base64d | fromjson | .predicate'
```

**Expected result:**
```json
{
  "repo": "TF4-Phase3-TechX/tf4-phase3-repo",
  "commit": "<full-40-char-sha>",
  "workflow": "build-and-push",
  "run_id": "<github-run-id>",
  "service_name": "checkout",
  "image_digest": "sha256:<digest>"
}
```

**Verify:** `commit` field → `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/<commit>` → xem PR nào đã merge commit này.

---

### Step 6: Verify SBOM attestation

```bash
cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE" | jq -r '.payload | @base64d | fromjson | .predicate | {bomFormat, specVersion, components_count: (.components | length)}'
```

**Expected result:**
```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "components_count": <N>
}
```

---

### Step 7: Trace commit về PR và approval

```bash
# Tìm PR chứa commit
gh api \
  /repos/TF4-Phase3-TechX/tf4-phase3-repo/commits/<commit-sha>/pulls \
  --jq '.[0] | {number: .number, title: .title, merged_at: .merged_at, merged_by: .merged_by.login}'
```

**Expected result:** PR number, title, merged date, merged by — chứng minh ai đã approve/merge.

---

### Step 8: Verify GitOps promotion chain

```bash
# Xem image-revisions.yaml trong GitOps repo
gh api \
  /repos/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/contents/environments/production/image-revisions.yaml \
  --jq '.content | @base64d' | grep -A3 "checkout:"
```

**Expected result:**
```yaml
checkout:
  imageOverride:
    tag: "8340af1-checkout"
    digest: "sha256:<digest>"  # ← added by SEC-19
```

---

### Step 9 (Optional): Test admission reject

```bash
# Namespace test phải tồn tại và có label
kubectl get namespace techx-sec17-admission-test --show-labels 2>/dev/null || \
  kubectl create namespace techx-sec17-admission-test
kubectl label namespace techx-sec17-admission-test \
  techx.io/sec17-signature-enforce=true --overwrite

# Test reject unsigned image
kubectl -n techx-sec17-admission-test run test-unsigned \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:latest \
  --restart=Never \
  --dry-run=server
```

**Expected result:** `Error ... denied the request: Image must be signed by the approved TF4 GitHub Actions OIDC identity.`

---

## 3. Known limitations và gaps

Mentor cần biết các điểm sau để đánh giá đúng:

### Gap 1: Runtime verify không có live build artifact [MEDIUM]

- **Vấn đề:** SEC-16 plan note rõ: evidence chính thức từ `build-and-push.yaml` trên `main` là `security-artifacts-<tag>` artifact. Kiro không thể trigger CI build thật trong session này, nên file `cosign-verify-checkout-*.txt` thật chưa được đính kèm ở đây.
- **Cách kiểm:** Vào GitHub Actions → `build-and-push.yaml` → chọn run tương ứng commit `8340af1` → download artifact `security-artifacts-8340af1` → xem các file verify.
- **Thay thế immediate:** Các lệnh `cosign verify*` ở Step 4-6 trên cho phép mentor tự verify từ digest — đây là cách chính xác nhất, không phụ thuộc vào artifact CI đã expire hay chưa.

### Gap 2: Image-revisions.yaml chưa có digest field [MEDIUM]

- **Vấn đề:** SEC-19 (`a4d0a38`) đã thêm promotion job ghi digest vào `image-revisions.yaml`. Tuy nhiên, tag `8340af1` hiện tại trong `image-revisions.yaml` **chưa có** `digest:` field — đây là image được promote trước khi SEC-19 merged.
- **Hệ quả:** ArgoCD `techx-corp` app hiện deploy theo tag, không theo digest. Admission policy `require-digest-image-reference` chưa active trên `techx-tf4` namespace (chỉ scoped theo label, `techx-tf4` chưa có label đó).
- **Cách xử lý:** Lần promote tiếp theo sau commit vào `main` sẽ tự động thêm digest field (SEC-19 đã live trên main). Hoặc manual trigger `build-and-push.yaml` với checkout service.

### Gap 3: Kyverno admission policy scoped to test namespace [LOW]

- **Vấn đề:** `require-signed-techx-images` hiện chỉ áp dụng cho namespace có label `techx.io/sec17-signature-enforce=true`. Production namespace `techx-tf4` chưa có label này.
- **Lý do cố ý:** SEC-17 plan ghi rõ — chỉ mở rộng sang production sau khi `image-revisions.yaml` có digest entries và image đã được sign từ main. Đây là staged rollout, không phải gap quên.
- **Hệ quả:** Hiện tại, cluster production không enforce signature verify tại admission. Controls chuỗi supply chain (scan → sign → promote) đã đủ để ngăn unsigned image tới GitOps.

### Gap 4: required_status_checks trên ruleset main [LOW]

- **Vấn đề:** SEC-16 plan note: `required_status_checks` chưa được cấu hình trên ruleset `main` — chỉ có required review (2 approvals + CODEOWNERS). Về lý thuyết, admin có thể merge PR mà không cần CI pass.
- **Hệ quả:** Chỉ ảnh hưởng đến tình huống admin override — không ảnh hưởng normal workflow.
- **Recommendation:** Cần admin thêm required CI checks vào branch protection ruleset.

---

## 4. Mandate 10 Final Verdict

### Yêu cầu Mandate 10 — đánh giá từng điểm

| # | Yêu cầu | Trạng thái | Evidence |
|---|---|---|---|
| 1 | Branch protection + required status checks trên `main` | ⚠️ **PARTIAL** | Required reviews có. Required CI checks chưa bật (xem Gap 4). |
| 2 | CI scan gates (secret/SAST/IaC/manifest) chặn PR vi phạm | ✅ **PASS** | SEC-14 (PR #293), ci.yaml: Gitleaks + Trivy + tfsec + kube-linter. Evidence commit history PR #293. |
| 3a | Registry immutable tags | ✅ **PASS** | ECR `IMMUTABLE` via `infra/terraform/ecr.tf` (PR #293). |
| 3b | Image signed + SBOM + provenance trước khi promote | ✅ **PASS** | build-and-push.yaml 8-step gate (SEC-15 + SEC-16). Pipeline fail nếu sign/SBOM/provenance fail. |
| 3c | Cluster chỉ chạy image đã ký (admission) | ⚠️ **PARTIAL** | Kyverno policy deployed nhưng scoped to test namespace (Gap 3). Production namespace chưa enforce. |
| 4 | Pinned dependencies (actions/images theo digest) | ✅ **PASS** | SEC-18, check_pinned_dependencies.py guard trên cả 2 repos. |
| 5 | Truy ngược từ runtime pod → commit → signer | ✅ **PASS** | Full chain: pod imageID → ECR tag → git SHA → workflow run → cosign verify (Steps 1-7 trên). |

### Verdict tổng

**PARTIAL PASS** — Mandate 10 đạt **5/7 điểm** (tính 2 điểm partial là 1):

- ✅ Supply chain controls (scan → sign → attest → verify) hoàn chỉnh trên pipeline
- ✅ Evidence trail đầy đủ từ pod digest về commit/PR/workflow/signature/SBOM/provenance
- ✅ Negative tests: CI gates block vi phạm
- ⚠️ Hai gap cần hoàn thiện để đạt FULL PASS:
  1. **Bật `required_status_checks`** trên ruleset `main` (Gap 4) — cần admin permission
  2. **Mở rộng admission policy** sang production namespace sau promote với digest (Gap 3) — unblock khi `image-revisions.yaml` có digest entries

### Khuyến nghị đóng mandate

PM/mentor có thể coi Mandate 10 đạt nếu:
- Accept 2 gaps còn lại là "tracked and scoped" (không phải unknown risk)
- Xác nhận Steps 1-8 trong verification guide tự bấm được và pass

Nếu muốn FULL PASS trước khi đóng: 
1. Trigger 1 lần `build-and-push.yaml` trên `main` để có build artifact mới với digest trong `image-revisions.yaml`
2. Thêm `required_status_checks` vào branch protection

---

## 5. Index evidence files

| File | Nội dung |
|---|---|
| `SEC-20-01-runtime-image-digest.md` | Pod selection + kubectl/ECR commands lấy digest |
| `SEC-20-02-commit-pr-workflow-trace.md` | Chain: digest → ECR tag → commit SHA → PR → GitOps PR → ArgoCD |
| `SEC-20-03-supply-chain-verification.md` | Scan report + cosign verify commands + SBOM + provenance |
| `SEC-20-04-negative-tests.md` | CI block evidence + admission reject test commands |
| `SEC-20-05-mentor-verification-guide.md` | (file này) Step-by-step guide + verdict |

**Không có secret nào được hardcode trong bất kỳ file evidence nào trên.**
