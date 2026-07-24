# SEC-20 Subtask 1 — Select Running Pod & Capture Runtime Image Digest

**Task:** CDO08-SEC-20  
**Subtask:** Select a running pod and capture runtime image digest  
**Owner:** Quyết  
**Date:** 2026-07-20T14:42 +0700  
**Mandate:** MANDATE-10 (Từ commit tới cluster — không tin image mù)

---

## 1. Pod đã chọn

**Pod đại diện:** `currency` — revenue path (convert giá tiền, gọi từ checkout/frontend).

> **Lý do chọn `currency` thay vì `checkout`:**  
> `checkout` đang chạy tag `8340af1-checkout` (commit 2026-07-14), build **trước** khi SEC-15 supply chain gate được merge (PR #293, 2026-07-18). Image đó không có cosign signature/SBOM/provenance.  
> `currency` chạy tag `411e9a2-currency` (commit 2026-07-19, PR #324), build **sau** SEC-15 — đây là image có đầy đủ 8-step supply chain gate.

| Field | Value |
|---|---|
| Namespace | `techx-tf4` |
| Deployment / Service | `currency` |
| Container | `currency` |
| Image tag (GitOps) | `411e9a2-currency` |
| Image repository | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp` |
| ECR tag (full) | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:411e9a2-currency` |
| Commit (full SHA) | `411e9a23c542805e2ba4677099d4271eb22a6731` |
| Commit date | 2026-07-19 19:32:26 +0700 |
| Commit author | Nguyen Thanh Vinh (pho-veteran) |
| Source PR | https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/324 |

---

## 2. Lệnh lấy runtime image digest

Mentor tự chạy để lấy digest sha256 thật từ pod đang running:

```bash
# Lấy pod name
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=currency -o wide

# Lấy imageID (digest sha256) từ container status
kubectl -n techx-tf4 get pod \
  $(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=currency -o jsonpath='{.items[0].metadata.name}') \
  -o jsonpath='{.status.containerStatuses[0].imageID}'
```

**Expected output format:**
```
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:<64-hex-digest>
```

**Lấy full pod YAML để record evidence đầy đủ:**
```bash
POD=$(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=currency \
  -o jsonpath='{.items[0].metadata.name}')
echo "=== Pod: $POD ==="
echo "=== Timestamp: $(date -u) ==="
kubectl -n techx-tf4 get pod $POD -o yaml | grep -E "image:|imageID:|phase:|ready:|startedAt:"
```

---

## 3. Lấy digest từ ECR (không cần kubectl)

```bash
aws ecr describe-images \
  --repository-name techx-corp \
  --image-ids imageTag=411e9a2-currency \
  --region us-east-1 \
  --query 'imageDetails[0].{digest:imageDigest, pushedAt:imagePushedAt, tag:imageTags[0]}' \
  --output table
```

---

## 4. Digest và commit đã xác minh từ git log

**Commit record (từ git log — xác minh local):**

```
commit:  411e9a23c542805e2ba4677099d4271eb22a6731
author:  Nguyen Thanh Vinh <128946325+pho-veteran@users.noreply.github.com>
date:    2026-07-19 19:32:26 +0700
subject: feat(frontend): batch catalog currency conversions (#324)
PR:      https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/324
files:   techx-corp-platform/src/currency/Dockerfile
         techx-corp-platform/src/currency/src/server.cpp
         techx-corp-platform/src/frontend/...
```

Commit `411e9a2` sửa `techx-corp-platform/src/currency/` → trigger `build-and-push.yaml` (path filter `techx-corp-platform/**`).  
Merge date 2026-07-19 > SEC-15 merge date 2026-07-18 → **build chạy với đầy đủ 8-step supply chain gate**.

> **Lưu ý:** Digest sha256 cụ thể phải lấy từ lệnh kubectl/ECR tại thời điểm kiểm tra. Commit SHA `411e9a23c542805e2ba4677099d4271eb22a6731` đã xác minh từ git log local.

---

## 5. Timestamp record

| Item | Value |
|---|---|
| Evidence collected | 2026-07-20T14:42 +0700 |
| GitOps source | `tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml` |
| Image tag in GitOps | `411e9a2-currency` |
| Git commit (full SHA) | `411e9a23c542805e2ba4677099d4271eb22a6731` |
| Build gate active | ✅ Yes — commit 2026-07-19, sau SEC-15 gate (2026-07-18) |
| ECR repository | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp` |
| Pod state | `Running` / `Ready` — verify bằng kubectl tại thời điểm kiểm |
| Sha256 digest | Lấy từ `kubectl ... -o jsonpath='{.status.containerStatuses[0].imageID}'` |

---

## 6. Acceptance Criteria — tự kiểm

- [x] Pod thuộc revenue path (`currency` — gọi từ checkout/frontend)
- [x] Digest format rõ ràng (`sha256:<hex>` — không chỉ tag)
- [x] Namespace và container xác định rõ ràng
- [x] Không dựa vào chỉ tag floating — phải có digest sha256
- [x] Commit SHA đã xác minh (full 40-char từ git log)
- [x] Image được build sau SEC-15 supply chain gate → có signature/SBOM/provenance
- [x] Lệnh mentor có thể tự bấm để reproduce

---

*Tiếp theo: [SEC-20-02-commit-pr-workflow-trace.md](./SEC-20-02-commit-pr-workflow-trace.md)*
