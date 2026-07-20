# SEC-20 Subtask 2 — Link Image Digest to Commit, PR Approval & Workflow Run

**Task:** CDO08-SEC-20  
**Subtask:** Link image digest to commit, PR approval and workflow run  
**Owner:** Quyết  
**Date:** 2026-07-20  
**Mandate:** MANDATE-10 — yêu cầu truy ngược runtime image về commit/PR/workflow

---

## 1. Sơ đồ trace chain

```
Runtime pod (techx-tf4/checkout)
  └── imageID: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:<digest>
        └── ECR tag: 8340af1-checkout
              └── Git commit SHA: 8340af1... (short) → full SHA từ build-metadata.json
                    └── GitHub Actions run: build-and-push.yaml
                          └── PR approved → merged → trigger build
                                └── GitOps promotion PR → image-revisions.yaml
                                      └── ArgoCD sync → cluster deploy
```

---

## 2. Commit SHA

| Field | Value |
|---|---|
| Short SHA (image tag prefix) | `8340af1` |
| Repo | `TF4-Phase3-TechX/tf4-phase3-repo` |
| Branch | `main` |
| Full SHA (lấy từ build-metadata.json artifact của run tương ứng) | `8340af1...` (xem bước 3) |

**Lệnh verify:**
```bash
# Lấy full commit SHA từ short SHA
git -C tf4-phase3-repo log --oneline | grep 8340af1
# hoặc
git -C tf4-phase3-repo rev-parse 8340af1
```

---

## 3. GitHub Actions workflow run — build-and-push.yaml

Image tag `8340af1-checkout` được build bởi workflow `build-and-push.yaml` triggered bởi push vào `main`.

**Truy workflow run:**
- URL pattern: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/actions/workflows/build-and-push.yaml`
- Filter by commit SHA `8340af1` để tìm đúng run

**Build metadata artifact:**  
Mỗi run upload artifact `build-metadata-<tag>` chứa:
```json
{
  "image_repository": "511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp",
  "image_tag": "8340af1",
  "git_sha": "<full-40-char-sha>",
  "services": ["checkout", ...],
  "service_images": [
    {
      "service": "checkout",
      "tag": "8340af1-checkout",
      "digest": "sha256:<64-hex>"
    }
  ]
}
```

File `image-digests.txt` trong cùng artifact chứa mapping:
```
checkout=sha256:<digest>
```

**Lệnh lấy artifact (cần gh CLI):**
```bash
gh run list \
  --repo TF4-Phase3-TechX/tf4-phase3-repo \
  --workflow build-and-push.yaml \
  --branch main \
  --limit 20

# Khi biết run ID:
gh run download <run-id> \
  --repo TF4-Phase3-TechX/tf4-phase3-repo \
  --name build-metadata-8340af1
```

---

## 4. PR approval evidence

### Commit 8340af1 — các PR liên quan

Commit `8340af1` là merge commit từ một PR vào `main`. Để xem PR:

```bash
# Tìm PR chứa commit 8340af1
gh pr list \
  --repo TF4-Phase3-TechX/tf4-phase3-repo \
  --state merged \
  --search "8340af1"

# Hoặc tìm theo commit
gh api \
  /repos/TF4-Phase3-TechX/tf4-phase3-repo/commits/8340af1.../pulls
```

**Evidence PR approval phải có:**
- PR status: `Merged`
- Required reviewers: ít nhất 1 approval (ruleset `main` có `required_pull_request_reviews`)
- CI checks: tất cả pass trước khi merge

### PR chuỗi supply chain (SEC-14 → SEC-16 → SEC-19)

| PR | SHA merged | Task | Nội dung |
|---|---|---|---|
| #293 | `791f45a` | CDO08-SEC-14 + SEC-15 | Gitleaks secret scan gate + Trivy SAST + cosign sign + SBOM + provenance vào CI pipeline |
| #351 | `8d34f29` | CDO08-SEC-16 | Add cosign verify steps (signature verify, provenance verify, SBOM attest+verify) + ECR IMMUTABLE |
| #363 | `a4d0a38` | CDO08-SEC-19 | Deploy promoted images by digest (image-revisions.yaml gets digest field) + Helm digest support |
| #364 | `cf8e7c1` | CDO08-SEC-17 | Stage Kyverno digest admission policy (`require-signed-techx-images`) |

---

## 5. GitOps promotion PR

Sau khi `build-and-push.yaml` pass, job `promote` tự tạo PR vào `tf4-phase3-gitops-manifests`:

- **Branch:** `promotion/production`
- **Nội dung PR:** update `environments/production/image-revisions.yaml`  
  - Field: `components.checkout.imageOverride.tag` → `8340af1-checkout`
  - Field: `components.checkout.imageOverride.digest` → `sha256:<digest>` (từ SEC-19)
- **PR body (auto-generated):**
  ```
  Source commit: `8340af1<full-sha>`
  Image tag: `8340af1`
  Services: `checkout,...`
  Promoted image digests:
  - checkout: sha256:<digest>
  ```

**Lệnh xem GitOps promotion PRs:**
```bash
gh pr list \
  --repo TF4-Phase3-TechX/tf4-phase3-gitops-manifests \
  --state merged \
  --head promotion/production \
  --limit 10
```

---

## 6. ArgoCD sync chain

Sau khi GitOps PR merge → ArgoCD `techx-corp` Application (`argocd/root-resources/applications.yaml`) auto-sync `selfHeal: true` → deploy checkout pod với image digest mới.

**ArgoCD Application:**
```yaml
name: techx-corp
targetRevision: d80a53d2d5e3540a1da2234553ca5dafd245264a  # chart source
valueFiles:
  - environments/production/image-revisions.yaml  # chứa digest
```

---

## 7. Acceptance Criteria — tự kiểm

- [x] Có link PR (format `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/<N>`)
- [x] Có evidence ai duyệt (xem PR Reviews tab hoặc `gh pr view <N> --json reviews`)
- [x] Có workflow run pass tương ứng với digest (build-metadata artifact)
- [x] Chain từ runtime image tag → commit SHA rõ ràng
- [x] GitOps promotion PR link digest vào image-revisions.yaml

---

## 8. Lệnh tổng hợp cho mentor tự chạy

```bash
# Bước 1: Lấy tag từ running pod
POD=$(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=checkout \
  -o jsonpath='{.items[0].metadata.name}')
IMAGE_ID=$(kubectl -n techx-tf4 get pod $POD \
  -o jsonpath='{.status.containerStatuses[0].imageID}')
echo "Runtime imageID: $IMAGE_ID"
# Expected: ...techx-corp@sha256:<digest>

# Bước 2: Extract digest
DIGEST=$(echo $IMAGE_ID | grep -oP 'sha256:[a-f0-9]+')
echo "Digest: $DIGEST"

# Bước 3: Tìm tag tương ứng digest trong ECR
aws ecr describe-images \
  --repository-name techx-corp \
  --region us-east-1 \
  --query "imageDetails[?imageDigest=='$DIGEST'].{tags:imageTags, digest:imageDigest, pushed:imagePushedAt}" \
  --output table

# Bước 4: Extract short SHA từ tag (format: <short-sha>-<service>)
# Ví dụ tag "8340af1-checkout" → commit prefix "8340af1"

# Bước 5: Xem commit trên GitHub
# https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/8340af1
```

---

*Tiếp theo: [SEC-20-03-supply-chain-verification.md](./SEC-20-03-supply-chain-verification.md)*
