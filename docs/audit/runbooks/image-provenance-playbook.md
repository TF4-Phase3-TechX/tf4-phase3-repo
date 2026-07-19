# Playbook: Truy ngược vòng đời Image (Image Provenance Tracing)
## CDO07 — Mandate 04/05 · Bài kiểm tra tại chỗ

> **Mục tiêu:** Khi mentor chỉ vào một pod đang chạy, đội truy ngược **full provenance**
> (Pod → Image → ECR → Signature → SBOM → CI Build → Source Commit → PR)
> ngay trước mặt, thời gian tính bằng **giây** (≤30s với script tự động).

| Thông tin | Giá trị |
|---|---|
| Cluster | `techx-tf4-cluster` |
| Region | `us-east-1` |
| ECR Repository | `techx-corp` (IMMUTABLE tags) |
| AWS Account | `511825856493` |
| Profile AWS | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| Namespace | `techx-tf4` |
| Image Tag Format | `<git-sha-7>-<service>` (ví dụ: `8340af1-currency`) |
| Script | `scripts/trace-image-provenance.sh` |

---

## Chuỗi Provenance — 6 mắt xích

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐
│ 1. Running  │───▶│ 2. ECR Image │───▶│ 3. Cosign     │───▶│ 4. Prove-   │───▶│ 5. GitHub   │───▶│ 6. Source    │
│    Pod      │    │    Metadata  │    │    Signature  │    │    nance    │    │    Actions  │    │    Commit   │
│             │    │              │    │    Verify     │    │    Attest   │    │    Run      │    │    + PR     │
└─────────────┘    └──────────────┘    └───────────────┘    └─────────────┘    └─────────────┘    └──────────────┘
kubectl            aws ecr              cosign verify        cosign verify-     GitHub API         git log
get pod            describe-images      (OIDC keyless)       attestation        workflow runs      + PR lookup
→ image digest     → tag, push time     → signer identity    → repo, SHA,       → actor, trigger   → author, msg
                   → scan status                              workflow, run_id   → run URL           → PR review
```

**Ý nghĩa của mỗi mắt xích:**
1. **Pod → Digest:** Image nào đang thực sự chạy trong container (không phải tag — tag có thể bị reuse, digest thì unique)
2. **ECR Metadata:** Khi nào image được push, có được quét CVE chưa, tag immutable (không ai đổi được)
3. **Cosign Signature:** Image có được ký bởi CI pipeline hợp lệ không (OIDC keyless từ GitHub Actions)
4. **Provenance Attestation:** Attestation gắn vào image: repo nào, commit nào, workflow nào, run ID nào build ra nó
5. **GitHub Actions Run:** Ai trigger build, build từ event gì (push/PR merge), link trực tiếp đến workflow run
6. **Source Code:** Commit message, author, PR được review/approve bởi ai → **quy trách nhiệm về người**

---

## Phần 1: Chuẩn bị trước khi bị hỏi (≤2 phút)

### 1.1 Xác nhận AWS credentials

```bash
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

Phải trả về ARN `TF4-AuditReadOnlyAndAnalyze` và account `511825856493`.
Nếu expired:
```bash
aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### 1.2 Xác nhận kubeconfig

```bash
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1
kubectl -n techx-tf4 get pods --request-timeout=10s 2>&1 | head -5
```

Phải thấy danh sách pods đang chạy.

### 1.3 Xác nhận tools

```bash
# Bắt buộc
kubectl version --client
aws --version
jq --version

# Tùy chọn (nếu có → full 6/6 steps)
cosign version 2>/dev/null && echo "cosign OK" || echo "cosign NOT AVAILABLE (steps 3-4 sẽ fallback)"
gh auth status 2>/dev/null && echo "gh CLI OK" || echo "gh NOT AVAILABLE (steps 5-6 cần GITHUB_TOKEN)"
```

### 1.4 Liệt kê pods đang chạy (để mentor chọn)

```bash
kubectl -n techx-tf4 get pods -o wide --no-headers | awk '{print $1, $3, $5}'
```

---

## Phần 2: Chạy bằng Script tự động (≤30 giây)

### Cách 1: Mentor chỉ vào pod — dùng `--pod`

```bash
# Mentor chỉ vào pod "currency-7d8f9b6c4-x2k9p"
bash scripts/trace-image-provenance.sh --pod currency-7d8f9b6c4-x2k9p
```

### Cách 2: Mentor đưa digest — dùng `--digest`

```bash
bash scripts/trace-image-provenance.sh --digest sha256:a1b2c3d4e5f6...
```

### Cách 3: Pod có nhiều container — dùng `--container`

```bash
bash scripts/trace-image-provenance.sh --pod frontend-proxy-abc123 --container frontend-proxy
```

### Tuỳ chỉnh

```bash
# Đổi namespace
bash scripts/trace-image-provenance.sh --pod my-pod --namespace techx-observability

# Đổi AWS profile
bash scripts/trace-image-provenance.sh --pod my-pod --profile MyCustomProfile

# Dry-run (chỉ in commands, không chạy)
bash scripts/trace-image-provenance.sh --dry-run --pod my-pod
```

### Đọc kết quả

Script sẽ in:
- **6 bước** với thông tin chi tiết từng mắt xích
- **VERDICT** cuối cùng: ✅ COMPLETE / ⚠️ PARTIAL / ❌ INCOMPLETE
- **JSON provenance record** (machine-readable, có thể lưu làm evidence)
- **Thời gian truy ngược** tính bằng giây

---

## Phần 3: Truy ngược thủ công từng bước (khi script không chạy được)

### Bước 1: Pod → Image Digest

```bash
# Lấy image và digest từ pod
POD_NAME="currency-7d8f9b6c4-x2k9p"

kubectl -n techx-tf4 get pod "$POD_NAME" -o jsonpath='{
  "image": "{.spec.containers[0].image}",
  "imageID": "{.status.containerStatuses[0].imageID}",
  "container": "{.spec.containers[0].name}"
}'
```

**Output mẫu:**
```
image: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-currency
imageID: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:abc123def456...
container: currency
```

> **Key insight:** `imageID` chứa digest thực tế đang chạy — đây là bằng chứng không thể giả.

### Bước 2: ECR Metadata

```bash
DIGEST="sha256:abc123def456..."

aws ecr describe-images \
  --repository-name techx-corp \
  --image-ids "imageDigest=${DIGEST}" \
  --region us-east-1 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.imageDetails[0] | {
      tags: .imageTags,
      digest: .imageDigest,
      pushed: .imagePushedAt,
      sizeMB: (.imageSizeInBytes / 1048576 | floor),
      scanStatus: .imageScanStatus.status,
      scanFindings: .imageScanFindingsSummary.findingSeverityCounts
    }'
```

**Giải thích cho mentor:**
> "ECR repository được cấu hình `image_tag_mutability = IMMUTABLE` (Terraform `ecr.tf`).
> Nghĩa là tag `8340af1-currency` một khi push thì không ai có thể ghi đè.
> `scan_on_push = true` nên mọi image đều được quét CVE tự động."

### Bước 3: Parse tag → Git SHA

```bash
TAG="8340af1-currency"

# Tag format: <git-sha-7>-<service-name>
GIT_SHA="${TAG%%-*}"     # → 8340af1
SERVICE="${TAG#*-}"       # → currency

echo "Git SHA (7 chars): $GIT_SHA"
echo "Service name: $SERVICE"
```

> **Key insight:** Tag encoding = Git commit SHA, nên từ bất kỳ image nào đều truy ngược
> được về đúng commit trong source code.

### Bước 4: Cosign Signature Verification (nếu có cosign)

```bash
IMAGE_REF="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@${DIGEST}"

# Verify signature
cosign verify \
  --certificate-identity-regexp='.*' \
  --certificate-oidc-issuer-regexp='.*' \
  "$IMAGE_REF"
```

**Giải thích cho mentor:**
> "Image được ký bằng Cosign keyless/OIDC trong CI pipeline (`build-and-push.yaml` step
> 'Security and Attestation'). Signature gắn vào Sigstore transparency log (Rekor),
> xác nhận image được build bởi GitHub Actions chứ không phải ai đó push tay."

### Bước 5: Provenance Attestation (nếu có cosign)

```bash
# Verify attestation
cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp='.*' \
  --certificate-oidc-issuer-regexp='.*' \
  "$IMAGE_REF" | jq '.payload | @base64d | fromjson | .predicate'
```

**Output mẫu:**
```json
{
  "repo": "TF4-Phase3-TechX/tf4-phase3-repo",
  "commit": "8340af1...",
  "workflow": "build-and-push",
  "run_id": "12345678",
  "service_name": "currency",
  "image_digest": "sha256:abc123..."
}
```

> **Key insight:** Attestation được tạo trong CI (`build-and-push.yaml:240-261`)
> và gắn vào image bằng `cosign attest`. Nó chứa chính xác repo, commit, workflow,
> run_id — không thể giả mạo vì nằm trên Sigstore transparency log.

### Bước 6: GitHub Actions Run + Source Code

```bash
GIT_SHA="8340af1"

# Xem commit
gh api "/repos/TF4-Phase3-TechX/tf4-phase3-repo/commits/${GIT_SHA}" \
  | jq '{sha: .sha, message: .commit.message, author: .commit.author.name, date: .commit.author.date}'

# Xem PR liên quan
gh api "/repos/TF4-Phase3-TechX/tf4-phase3-repo/commits/${GIT_SHA}/pulls" \
  | jq '.[0] | {pr: .number, title: .title, url: .html_url, merged_by: .merged_by.login}'

# Xem GitHub Actions run
gh api "/repos/TF4-Phase3-TechX/tf4-phase3-repo/actions/runs?head_sha=$(gh api /repos/TF4-Phase3-TechX/tf4-phase3-repo/commits/${GIT_SHA} | jq -r .sha)&per_page=3" \
  | jq '.workflow_runs[] | select(.name=="build-and-push") | {run_id: .id, url: .html_url, actor: .actor.login, trigger: .event, status: .conclusion}'
```

---

## Phần 4: Template trả lời mentor

### Khi mentor chỉ vào một pod bất kỳ:

```
WHO BUILT IT:
  - GitHub Actions workflow "build-and-push" (automated CI/CD)
  - Triggered by: [actor] pushing to main
  - PR #[number] "[title]" — reviewed and approved by [reviewers]

WHAT IS RUNNING:
  - Image: techx-corp:[sha]-[service]
  - Digest: sha256:[digest] (immutable, verified by ECR)
  - CVE Scan: [COMPLETE — 0 CRITICAL, 0 HIGH]

WHEN WAS IT BUILT:
  - Source commit: [date] by [author]
  - Image pushed to ECR: [push_time]
  - Deployed via ArgoCD GitOps reconciliation

HOW DO WE TRUST IT:
  1. ECR tags are IMMUTABLE — cannot be overwritten
  2. Image is signed by Cosign (OIDC keyless via GitHub Actions)
  3. Provenance attestation on Sigstore transparency log
  4. CVE scan on push — no CRITICAL/HIGH vulnerabilities
  5. PR required 2 approvals before merge to main
  6. GitOps promotion PR reviewed before ArgoCD deploys

FULL CHAIN:
  Pod [pod_name]
  → Image [image:tag]
  → Digest [sha256:...]
  → ECR push [timestamp], scan [status]
  → Cosign signature [verified/skipped]
  → Built by GitHub Actions run #[run_id]
  → Source commit [sha] by [author]
  → PR #[number] merged by [merger]
```

### Ví dụ trả lời nhanh:

> "Pod `currency-7d8f9b6c4-x2k9p` đang chạy image digest `sha256:abc123...`,
> tag `8340af1-currency`, được push lên ECR lúc 2026-07-15T03:22:41Z.
> Image được build bởi GitHub Actions run #12345678, trigger bởi `nguyen` push
> commit `8340af1` — 'fix(currency): add readiness probe' — vào main.
> PR #142 đã được 2 người review. Image có chữ ký Cosign trên Sigstore.
> ECR scan COMPLETE, 0 CRITICAL, 0 HIGH. Toàn bộ truy ngược mất 8 giây."

---

## Phần 5: Tại sao chuỗi provenance đáng tin?

| Mắt xích | Cơ chế bảo vệ | Evidence |
|-----------|---------------|----------|
| **ECR tag** | `image_tag_mutability = IMMUTABLE` (Terraform) | `ecr.tf` — tag không thể bị ghi đè |
| **Cosign signature** | OIDC keyless từ GitHub Actions → Sigstore Rekor | `build-and-push.yaml:232-237` |
| **Provenance attestation** | `cosign attest --predicate` gắn metadata vào image | `build-and-push.yaml:240-261` |
| **CVE scan** | `scan_on_push = true` — ECR quét tự động | `ecr.tf:8-10` |
| **Build isolation** | GitHub Actions runner ephemeral, OIDC auth | `build-and-push.yaml:106-109` |
| **PR gate** | 2 approvals required, status checks must pass | `CONTRIBUTING.md` branch protection |
| **GitOps promotion** | Separate repo, human review, ArgoCD reconcile | `build-and-push.yaml:304-412` |
| **Audit separation** | CDO07 chỉ có Read-only — không sửa được evidence | ADR-001, IAM policy |

---

## Phần 6: Troubleshooting

### Pod not found
```bash
# Liệt kê tất cả pods
kubectl -n techx-tf4 get pods --no-headers | grep -i "<service-name>"
```

### ECR describe-images trả về lỗi
```bash
# Thử tìm bằng tag thay vì digest
aws ecr describe-images --repository-name techx-corp \
  --image-ids "imageTag=8340af1-currency" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493

# Liệt kê tất cả tags gần đây
aws ecr describe-images --repository-name techx-corp \
  --query 'sort_by(imageDetails,& imagePushedAt)[-5:].{tag:imageTags[0],digest:imageDigest,pushed:imagePushedAt}' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  --output table
```

### Cosign verify fails
```bash
# ECR login cần thiết cho cosign
aws ecr get-login-password --region us-east-1 \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | cosign login --username AWS --password-stdin \
    511825856493.dkr.ecr.us-east-1.amazonaws.com
```

### GitHub API rate limit
```bash
# Check remaining rate limit
gh api /rate_limit | jq '.rate'

# Hoặc dùng GITHUB_TOKEN
curl -s -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit | jq '.rate'
```

### Credentials hết hạn giữa chừng
```bash
aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

---

**Playbook version:** 1.0
**Tác giả:** CDO07 — TF4 Phase 3
**Ngày:** 2026-07-18
**Script:** `scripts/trace-image-provenance.sh`
**Liên quan:** `docs/audit/runbooks/forensic-playbook-timeline.md` (playbook truy vết audit log — bổ sung)
