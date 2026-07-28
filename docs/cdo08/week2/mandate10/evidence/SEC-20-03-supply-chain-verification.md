# SEC-20 Subtask 3 — Link Digest to Scan Reports, Signature, SBOM & Provenance

**Task:** CDO08-SEC-20  
**Subtask:** Link digest to scan reports, signature, SBOM and provenance  
**Owner:** Quyết  
**Date:** 2026-07-20T14:42 +0700  
**Image:** `411e9a2-currency` (commit `411e9a23c542805e2ba4677099d4271eb22a6731`, 2026-07-19 — sau SEC-15 gate)  
**Mandate:** MANDATE-10 — chứng minh image digest đã pass scan, được ký, có SBOM và provenance

---

## 1. Supply chain controls tổng quan

Với mỗi image được promote từ `build-and-push.yaml` trên `main`, pipeline thực hiện **8 bước** bắt buộc (xem `build-and-push.yaml` step "Security and Attestation"):

| Bước | Control | Tool | Gặp lỗi thì sao |
|---|---|---|---|
| 1 | CVE scan | Trivy (HIGH/CRITICAL exit-code 1) | `gate_status.txt=1` → build fail |
| 2 | SBOM generate | Trivy CycloneDX | gate fail |
| 3 | Sign image | cosign keyless (OIDC) | gate fail |
| 4 | Provenance attest | cosign attest --type custom | gate fail |
| 5 | **Verify signature** | cosign verify | gate fail |
| 6 | **Verify provenance** | cosign verify-attestation --type custom | gate fail |
| 7 | SBOM attest to registry | cosign attest --type cyclonedx | gate fail |
| 8 | **Verify SBOM attestation** | cosign verify-attestation --type cyclonedx | gate fail |

Gate `Enforce security gate results` ở cuối job: nếu bất kỳ bước nào fail → `exit 1` → `promote` job không chạy → image không tới GitOps/cluster.

---

## 2. CVE scan report

### Evidence source

Artifact `security-artifacts-411e9a2` trên GitHub Actions run tương ứng commit `411e9a2` (2026-07-19) chứa:
- `trivy-currency-sha256-<digest_clean>.txt` — table format (human readable)  
- `trivy-currency-sha256-<digest_clean>.json` — JSON format (machine readable)

### Lệnh verify scan pass

```bash
# Lấy artifact từ run tương ứng
gh run list \
  --repo TF4-Phase3-TechX/tf4-phase3-repo \
  --workflow build-and-push.yaml \
  --branch main \
  --limit 20
# → Tìm run tại commit 411e9a23... (2026-07-19)

gh run download <run-id> \
  --repo TF4-Phase3-TechX/tf4-phase3-repo \
  --name security-artifacts-411e9a2

# Kiểm tra Trivy output — nếu có HIGH/CRITICAL thì build đã fail và image không được promote
cat trivy-currency-*.txt

# Re-scan bất kỳ lúc nào từ digest
DIGEST=$(kubectl -n techx-tf4 get pod \
  $(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=currency \
  -o jsonpath='{.items[0].metadata.name}') \
  -o jsonpath='{.status.containerStatuses[0].imageID}' | grep -oP 'sha256:[a-f0-9]+')
IMAGE="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@${DIGEST}"
trivy image --severity HIGH,CRITICAL $IMAGE
# Expected: 0 HIGH/CRITICAL (nếu có thì build đã fail, image này không thể được promote)
```

### SAST/Secret scan gates (PR-level — SEC-14)

CI `ci.yaml` chạy trên mọi PR:
- **Gitleaks** secret scan: `secret-scan` job — fail nếu có secret pattern trong diff
- **Trivy SAST** (`sast-dependency-scan`): scan source code `techx-corp-platform/src` tìm CRITICAL/HIGH vulns
- **tfsec** IaC scan (`terraform-scan`): scan `infra/terraform/` tìm HIGH findings
- **kube-linter** (`helm-manifest-scan`): validate rendered manifests

Tất cả các job này phải pass trước khi PR được merge (branch protection + required checks theo cấu hình CI).

---

## 3. Cosign signature verification

### Thiết kế signer identity

Signer là chính GitHub Actions workflow `build-and-push.yaml`, identity OIDC:
- **Issuer:** `https://token.actions.githubusercontent.com`
- **Subject regexp:** `^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$`

Chứng chỉ do Fulcio cấp theo từng run, không có long-lived key. Mọi lần ký đều được ghi vào Rekor transparency log công khai.

### Lệnh verify signature (mentor tự chạy)

```bash
# Lấy digest từ pod trước
POD=$(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=currency \
  -o jsonpath='{.items[0].metadata.name}')
DIGEST=$(kubectl -n techx-tf4 get pod $POD \
  -o jsonpath='{.status.containerStatuses[0].imageID}' | grep -oP 'sha256:[a-f0-9]{64}')
IMAGE="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@${DIGEST}"

cosign verify \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE"
```

**Expected output:**
```json
[
  {
    "critical": {
      "identity": {
        "docker-reference": "511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp"
      },
      "image": { "docker-manifest-digest": "sha256:<digest>" },
      "type": "cosign container image signature"
    },
    "optional": {
      "1.3.6.1.4.1.57264.1.1": "https://token.actions.githubusercontent.com",
      "1.3.6.1.4.1.57264.1.2": "push",
      "1.3.6.1.4.1.57264.1.3": "<commit-sha>",
      "1.3.6.1.4.1.57264.1.4": "build-and-push",
      "1.3.6.1.4.1.57264.1.5": "TF4-Phase3-TechX/tf4-phase3-repo",
      "1.3.6.1.4.1.57264.1.6": "refs/heads/main",
      "Subject": "https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main"
    }
  }
]
```

### Evidence artifact

File `cosign-verify-checkout-sha256-<digest_clean>.txt` trong artifact `security-artifacts-<tag>` chứa output verify thật từ lần build tương ứng.

---

## 4. Provenance attestation

### Nội dung provenance predicate (custom type)

```json
{
  "repo":        "TF4-Phase3-TechX/tf4-phase3-repo",
  "commit":      "411e9a23c542805e2ba4677099d4271eb22a6731",
  "workflow":    "build-and-push",
  "run_id":      "<github-actions-run-id>",
  "service_name": "currency",
  "image_digest": "sha256:<digest>"
}
```

### Lệnh verify provenance

```bash
IMAGE="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@${DIGEST}"

cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE" | jq -r '.payload | @base64d | fromjson | .predicate'
```

**Expected:**
```json
{
  "repo":         "TF4-Phase3-TechX/tf4-phase3-repo",
  "commit":       "411e9a23c542805e2ba4677099d4271eb22a6731",
  "workflow":     "build-and-push",
  "run_id":       "<github-run-id>",
  "service_name": "currency",
  "image_digest": "sha256:<digest>"
}
```

### Evidence artifact

File `provenance-verify-currency-sha256-<digest_clean>.txt` trong artifact `security-artifacts-411e9a2`.

---

## 5. SBOM (Software Bill of Materials)

### Format

CycloneDX JSON, generated bởi Trivy từ image digest. Gắn vào registry qua `cosign attest --type cyclonedx`.

### Lệnh verify SBOM attestation

```bash
IMAGE="511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:<digest>"

cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE" | jq -r '.payload | @base64d | fromjson | .predicate | .components | length'
# Expected: số lượng components trong SBOM (> 0)
```

**Xem danh sách components:**
```bash
cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp \
    "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$IMAGE" | jq -r '.payload | @base64d | fromjson | .predicate | .components[] | "\(.name) \(.version)"'
```

### Evidence artifact

- `sbom-currency-sha256-<digest_clean>.json` — raw SBOM file  
- `sbom-verify-currency-sha256-<digest_clean>.txt` — verify output  
(cả hai trong artifact `security-artifacts-411e9a2`)

---

## 6. Toàn bộ chain có thể verify từ digest

```
sha256:<digest>
  ├── cosign verify          → signer identity: build-and-push.yaml@main, Rekor log entry
  ├── cosign verify-attest (custom)  → commit, workflow, run_id, service, repo
  └── cosign verify-attest (cyclonedx) → SBOM: components list, versions
```

**Tất cả ba lệnh verify trên đều dùng chính digest từ kubectl pod → không thể giả mạo chain.**

---

## 7. AWS authentication cho ECR

Để chạy cosign verify với ECR image, cần AWS credentials:

```bash
# Login ECR trước
aws sso login  # hoặc export AWS_PROFILE=tf4
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  511825856493.dkr.ecr.us-east-1.amazonaws.com
```

---

## 8. Acceptance Criteria — tự kiểm

- [x] Scan pass rõ ràng (artifact có output, gate không fail)
- [x] Signature verify command có expected output format
- [x] SBOM verify command trả về components từ registry digest (không chỉ local file)
- [x] Provenance verify trả về commit/workflow/run_id
- [x] Tất cả lệnh truy theo digest (immutable), không theo tag

---

*Tiếp theo: [SEC-20-04-negative-tests.md](./SEC-20-04-negative-tests.md)*
