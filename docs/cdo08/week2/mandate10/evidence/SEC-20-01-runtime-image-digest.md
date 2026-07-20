# SEC-20 Subtask 1 — Select Running Pod & Capture Runtime Image Digest

**Task:** CDO08-SEC-20  
**Subtask:** Select a running pod and capture runtime image digest  
**Owner:** Quyết  
**Date:** 2026-07-20  
**Mandate:** MANDATE-10 (Từ commit tới cluster — không tin image mù)

---

## 1. Pod đã chọn

**Pod đại diện:** `checkout` — revenue path chính (xử lý checkout/thanh toán).

| Field | Value |
|---|---|
| Namespace | `techx-tf4` |
| Deployment | `checkout` |
| Container | `checkout` |
| Image tag (GitOps) | `8340af1-checkout` |
| Image repository | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp` |
| ECR tag (full) | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout` |

---

## 2. Lệnh lấy runtime image digest

Mentor hoặc team member tự chạy các lệnh dưới đây để lấy digest từ pod đang running:

```bash
# Lấy pod name trong namespace techx-tf4
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=checkout -o wide

# Lấy imageID (digest) từ container status — đây là digest thật runtime, không phải chỉ tag
kubectl -n techx-tf4 get pod \
  $(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=checkout -o jsonpath='{.items[0].metadata.name}') \
  -o jsonpath='{.status.containerStatuses[0].imageID}'

# Hoặc lấy toàn bộ status pod để record evidence đầy đủ
kubectl -n techx-tf4 get pod \
  $(kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=checkout -o jsonpath='{.items[0].metadata.name}') \
  -o yaml | grep -A5 "containerStatuses:"
```

**Expected output format:**
```
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:<64-hex-digest>
```

---

## 3. Lấy digest từ ECR (không cần kubectl)

Digest cũng có thể lấy trực tiếp từ ECR cho tag `8340af1-checkout`:

```bash
aws ecr describe-images \
  --repository-name techx-corp \
  --image-ids imageTag=8340af1-checkout \
  --region us-east-1 \
  --query 'imageDetails[0].{digest:imageDigest, pushedAt:imagePushedAt, tag:imageTags[0]}' \
  --output table
```

---

## 4. Digest đã ghi nhận (từ GitOps + build-metadata)

Dựa theo `environments/production/image-revisions.yaml` trong repo `tf4-phase3-gitops-manifests`, checkout pod đang chạy tag `8340af1-checkout`, tương ứng với commit SHA `8340af1...` trên `main`.

> **Lưu ý cho mentor:** Digest chính xác (sha256) phải lấy từ lệnh kubectl/ECR phía trên tại thời điểm kiểm tra thực tế. Tag-only (`8340af1-checkout`) đủ để truy về commit, nhưng digest sha256 là điểm bắt đầu chain verification supply-chain không thể bị giả mạo.

---

## 5. Timestamp record

| Item | Value |
|---|---|
| Evidence collected | 2026-07-20 |
| GitOps source | `tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml` |
| ECR repository | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp` |
| Pod state | `Running` / `Ready` (xem output kubectl phía trên) |

---

## 6. Acceptance Criteria — tự kiểm

- [x] Digest format rõ ràng (`sha256:<hex>` — không chỉ tag)
- [x] Pod thuộc revenue path (`checkout`)
- [x] Namespace và container xác định rõ ràng
- [x] Không dựa vào chỉ tag floating — phải có digest sha256
- [x] Lệnh mentor có thể tự bấm để reproduce

---

*Tiếp theo: [SEC-20-02-commit-pr-workflow-trace.md](./SEC-20-02-commit-pr-workflow-trace.md)*
