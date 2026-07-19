# Plan: CDO08-SEC-16 — Make images immutable, signed with SBOM and provenance

**Owner:** Quân
**Priority:** P0
**Backlog:** CDO08-SEC-16 [SupplyChain]
**Directive:** MANDATE-10 (Từ commit tới cluster — không tin image mù), yêu cầu #3
**Ngày:** 2026-07-19

---

## 0. Phạm vi

Task này hiện thực **nửa đầu** yêu cầu #3 của MANDATE-10 — phần **build/registry side**: registry immutable, mỗi image được ký (cosign) + kèm SBOM + kèm provenance, và có build artifact đủ truy commit → digest → signer.

**Không thuộc phạm vi** (đã audit riêng, báo cáo cho người phụ trách khác, xem §10):
- Nửa sau của yêu cầu #3 — *"cluster chỉ chạy image đã ký, tham chiếu theo digest — admission enforce"*. Cluster hiện chưa có cơ chế nào verify chữ ký cosign tại admission (VAP/CEL của K8s gốc không có khả năng crypto-verify); cần Kyverno/Sigstore policy-controller hoặc tương đương — thay đổi kiến trúc riêng, không nằm trong 4 subtask của ticket này.
- Yêu cầu #1 (branch protection + required status checks trên `main`) — audit cho thấy ruleset `main` hiện chỉ có rule review (2 approval + code owner), chưa có `required_status_checks`.

Bốn subtask của ticket ánh xạ tới các yêu cầu như sau:

| # | Subtask | Yêu cầu MANDATE-10 #3 |
|---|---|---|
| 1 | Change ECR repository to immutable tags | Registry immutable |
| 2 | Add cosign keyless signing for built images | Mỗi image được ký (cosign) |
| 3 | Generate provenance attestation linked to commit and workflow | Kèm provenance |
| 4 | Generate SBOM for every built image | Kèm SBOM |

---

## 1. Mục tiêu

Biến image artifact do pipeline `build-and-push.yaml` build/push ra thành **bất biến và có nguồn gốc xác minh được**: không thể ghi đè tag cũ trong ECR; mỗi image có chữ ký cosign, SBOM, provenance gắn thẳng vào digest trên registry (không chỉ nằm trong build log); pipeline fail cứng nếu bất kỳ bước ký/SBOM/provenance nào thất bại; có lệnh verify được cả 3 loại cho một image bất kỳ.

---

## 2. Bối cảnh hệ thống hiện tại (evidence)

Hiện trạng trước khi bắt đầu ticket (theo mô tả gốc của ticket, đối chiếu lại với repo):

| Hạng mục | Evidence | Ý nghĩa |
|---|---|---|
| ECR mutability | `infra/terraform/ecr.tf:6` — `image_tag_mutability = "MUTABLE"` | Tag cũ có thể bị ghi đè — vi phạm trực tiếp yêu cầu #3. |
| Build metadata | `build-and-push.yaml` job `build` bước "Verify pushed image digests" + "Write build metadata" — đã có `image-digests.txt` (service→digest) và `build-metadata.json` (repo/tag/git_sha/services) | Đã đủ truy digest → commit → service, nhưng chưa có ký/SBOM/provenance để truy tiếp signer. |
| Cosign / SBOM / provenance | Grep pipeline: không có bước nào dùng `cosign`, không có SBOM, không có attestation | Image ra khỏi ECR mà không ai chứng minh được nó sạch/từ đâu — đúng vấn đề MANDATE-10 nêu. |

**Ghi chú:** trong lúc triển khai, phát hiện một phần cosign sign + provenance (custom predicate) + SBOM (Trivy CycloneDX, dạng build artifact) **đã được thêm sẵn** vào `build-and-push.yaml` bởi PR #293 (`feat(ci): [CDO08-SEC-15][M10] implement secure image delivery pipeline and scan gates`) trước khi ticket này bắt đầu — xem chi tiết phần nào có sẵn / phần nào tự viết thêm ở §5.

---

## 3. Phương án — tradeoff

### 3.1 Ký: cosign keyless (OIDC/Fulcio) — không dùng long-lived key

| Tiêu chí | Keyless (OIDC + Fulcio + Rekor) | Long-lived private key (KMS/file) |
|---|---|---|
| Quản lý key | Không cần lưu trữ/xoay vòng key nào — cert ngắn hạn cấp theo mỗi lần chạy, gắn danh tính OIDC của chính GitHub Actions run | Phải tạo, lưu (KMS/Secret), xoay vòng định kỳ, kiểm soát ai truy cập được key |
| Rủi ro rò rỉ | Không có key tĩnh nào để rò rỉ — cert hết hạn gần như ngay sau khi ký | Rò rỉ key = ký giả được vô thời hạn cho tới khi phát hiện + thu hồi |
| Hạ tầng thêm | 0 — `permissions: id-token: write` đã có sẵn ở workflow (dùng chung cho `aws-actions/configure-aws-credentials`) | Cần thêm KMS key hoặc secret, IAM/permission riêng |
| Truy vết signer | Cert Fulcio chứa thẳng danh tính workflow (`https://github.com/<repo>/.github/workflows/<file>@refs/heads/<branch>`) + ghi vào Rekor (transparency log công khai, bất biến) | Chỉ biết "ký bằng key X", không tự chứng minh được run nào đã ký nếu không có log riêng |
| Khớp MANDATE-10 #5 (truy ngược "ai/khóa nào ký") | Có sẵn, không cần thêm cơ chế log | Cần tự xây thêm hệ thống log ký |

→ Chọn **keyless**: `cosign sign --yes` không kèm `--key`, tận dụng đúng `id-token: write` đã có, không thêm quản lý vòng đời key nào.

### 3.2 SBOM: Trivy CycloneDX — không thêm Syft

Ticket cho phép "Syft/Trivy SBOM hoặc tool tương đương". Chọn **Trivy** vì:
- Đã là dependency có sẵn trong cùng job (dùng để scan CVE ở bước 1) — không cần cài thêm tool, không tăng thời gian pipeline vì tải thêm binary.
- CycloneDX là format `cosign attest --type cyclonedx` hỗ trợ native (predicate type dựng sẵn, không cần tự định nghĩa JSON schema như provenance "custom").

### 3.3 Provenance: predicate `custom` tự định nghĩa — không dùng chuẩn SLSA provenance đầy đủ

Đã cân nhắc `cosign attest --type slsaprovenance`/`slsaprovenance1` (chuẩn SLSA in-toto đầy đủ, có builder id, materials, build config). Chọn **`custom`** vì:
- Predicate hiện tại (`repo`, `commit`, `workflow`, `run_id`, `service_name`, `image_digest`) đã đủ trả lời đúng câu hỏi MANDATE-10 #5 đặt ra ("từ commit nào, workflow nào, repo nào") mà không cần map dữ liệu build hiện có sang schema SLSA đầy đủ (materials/builder.id) — việc đó tốn công hơn đáng kể mà không được yêu cầu trong DoD của ticket này.
- Có thể nâng cấp lên SLSA chuẩn sau nếu MANDATE-10 hoặc mentor yêu cầu cụ thể — không phải quyết định một chiều (predicate `custom` không khoá cứng, đổi `--type` là đủ).

---

## 4. Ảnh hưởng tới hệ thống hiện tại (impact analysis)

| Rủi ro | Chi tiết | Biện pháp giảm thiểu |
|---|---|---|
| Pipeline build chậm hơn | Thêm cài cosign + 3 lệnh sign/attest + 3 lệnh verify cho mỗi service, mỗi lần build | Cosign sign/verify/attest chạy nhanh (giây), không đáng kể so với build image (phút); verify chạy tuần tự cùng job build đã có sẵn, không thêm job/runner mới. |
| Sign/SBOM/provenance fail chặn cả service khác trong cùng run | Vòng lặp xử lý từng service tuần tự trong 1 job; 1 service fail set `gate_status.txt=1` nhưng **không dừng vòng lặp giữa chừng** (`if !`, không phải `set -e` sớm) — các service còn lại vẫn được xử lý, chỉ cuối cùng job fail chung | Đây là hành vi cố ý: fail-closed ở **cuối job** (không promote gì cả nếu có 1 service lỗi) nhưng vẫn xử lý hết để log đầy đủ lỗi của mọi service trong 1 lần chạy, đỡ phải chạy lại nhiều lần để thấy hết lỗi. |
| Ảnh hưởng tới `promote` job (mở PR GitOps) | Job `promote` có điều kiện `needs.build.result == 'success'` — nếu `build` job fail (do gate `Enforce security gate results` exit 1), `promote` **không chạy** | Không cần rollback thủ công gì thêm — image build lỗi ký/SBOM/provenance sẽ không bao giờ có PR GitOps được tạo, tức không tới được ArgoCD/cluster. Xem §8. |
| Image cũ (build trước khi có ký/SBOM/provenance) đang chạy trên cluster | Các image build trước PR #293/ticket này không có signature/SBOM/provenance | Ngoài phạm vi ticket này (không rebuild lại lịch sử) — chỉ áp dụng cho build mới từ nay. Không có yêu cầu DoD nào bắt buộc backfill. |

---

## 5. Thiết kế chi tiết

Toàn bộ nằm trong 1 step `Security and Attestation (Scan, Sign, SBOM, Provenance, Verify)` của job `build`, `.github/workflows/build-and-push.yaml`, chạy tuần tự **8 bước** cho từng service (đọc từ `image-digests.txt`, sinh ra ở bước "Verify pushed image digests" ngay trước đó):

| # | Bước | Có sẵn từ PR #293 hay tự viết mới ở ticket này |
|---|---|---|
| 1 | Trivy CVE scan (chặn HIGH/CRITICAL) | Có sẵn |
| 2 | Generate SBOM CycloneDX (Trivy) | Có sẵn |
| 3 | Cosign sign keyless | Có sẵn |
| 4 | Generate + attest provenance (`--type custom`) | Có sẵn |
| 5 | **Verify signature** | **Viết mới ở ticket này** |
| 6 | **Verify provenance attestation** | **Viết mới ở ticket này** |
| 7 | **Attest SBOM lên registry** (`--type cyclonedx`) | **Viết mới ở ticket này** |
| 8 | **Verify SBOM attestation** | **Viết mới ở ticket này** |

Bước 1-4 chỉ tạo ra chữ ký/SBOM/provenance nhưng **chưa ai kiểm chứng lại** và SBOM ban đầu chỉ là build artifact (không gắn vào registry) — đây đúng là gap khiến DoD "Evidence verify cosign/SBOM/provenance được với một image" chưa đạt trước khi có bước 5-8.

### 5.1 Bước 5 — Verify signature

```bash
# 5. Verify signature — evidence of signer identity (OIDC subject/issuer) and Rekor transparency log entry
echo ">> [5/8] Verifying Cosign signature..."
if ! cosign verify \
  --certificate-identity-regexp "^https://github.com/${{ github.repository }}/.github/workflows/.*@refs/heads/.*$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$image_ref_digest" \
  --output text > "security-artifacts/cosign-verify-${service}-${digest_clean}.txt" 2>&1; then
  echo "::error::Cosign verify failed for $service — could not confirm signature"
  cat "security-artifacts/cosign-verify-${service}-${digest_clean}.txt"
  echo "1" > security-artifacts/gate_status.txt
fi
```

### 5.2 Bước 6 — Verify provenance attestation

```bash
# 6. Verify provenance attestation — evidence that the predicate (commit/repo/workflow/run_id/digest) is authentic
echo ">> [6/8] Verifying Provenance Attestation..."
if ! cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp "^https://github.com/${{ github.repository }}/.github/workflows/.*@refs/heads/.*$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$image_ref_digest" \
  --output text > "security-artifacts/provenance-verify-${service}-${digest_clean}.txt" 2>&1; then
  echo "::error::Provenance verify failed for $service — could not confirm attestation"
  cat "security-artifacts/provenance-verify-${service}-${digest_clean}.txt"
  echo "1" > security-artifacts/gate_status.txt
fi
```

### 5.3 Bước 7 — Attest SBOM lên registry

```bash
# 7. Attest SBOM — binds the CycloneDX SBOM to the image digest on the registry (not just a build artifact)
echo ">> [7/8] Attesting SBOM..."
if ! cosign attest --yes \
  --predicate "security-artifacts/sbom-${service}-${digest_clean}.json" \
  --type cyclonedx \
  "$image_ref_digest"; then
  echo "::error::Failed to attest SBOM for $service"
  echo "1" > security-artifacts/gate_status.txt
fi
```

### 5.4 Bước 8 — Verify SBOM attestation

```bash
# 8. Verify SBOM attestation — evidence the CycloneDX SBOM attached to the digest is authentic
echo ">> [8/8] Verifying SBOM Attestation..."
if ! cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp "^https://github.com/${{ github.repository }}/.github/workflows/.*@refs/heads/.*$" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  "$image_ref_digest" \
  --output text > "security-artifacts/sbom-verify-${service}-${digest_clean}.txt" 2>&1; then
  echo "::error::SBOM verify failed for $service — could not confirm attestation"
  cat "security-artifacts/sbom-verify-${service}-${digest_clean}.txt"
  echo "1" > security-artifacts/gate_status.txt
fi
```

> Bước 5-8 chỉ chạy khi `scan_failed -eq 0` (cùng nhánh với sign/attest gốc) — image dính HIGH/CRITICAL CVE thì không được ký/SBOM-attest/provenance-attest, nên cũng không cần verify.

> Cả 3 lệnh verify dùng chung `--certificate-identity-regexp`/`--certificate-oidc-issuer` — đúng danh tính OIDC của chính workflow này (`https://token.actions.githubusercontent.com`, subject khớp `*.github/workflows/*@refs/heads/*`) — không verify được nếu ký bởi identity khác, đúng ý "chỉ tin image do pipeline này ký".

### 5.5 ECR immutable

```hcl
# infra/terraform/ecr.tf
resource "aws_ecr_repository" "techx_corp" {
  name                 = "techx-corp"
  image_tag_mutability = "IMMUTABLE"
  ...
}
```

Kèm sửa runbook rollback thủ công REL-09 (`docs/cdo08/week2/mandate0/implementation/CDO08-REL-09-timeout-retry-plan.md`) — đổi từ "rebuild + push lại tag cũ" (sẽ bị ECR từ chối dưới IMMUTABLE) sang trỏ thẳng `helm upgrade --set default.image.tag=<old-tag>` vào tag cũ đã có sẵn.

---

## 6. Rollout

| Bước | Việc | Commit | Trạng thái |
|---|---|---|---|
| 1 | ECR `MUTABLE` → `IMMUTABLE` + sửa runbook rollback REL-09 | `5486823` | ✅ Đã merge vào nhánh `CDO08-SEC-16` |
| 2 | Verify signature (bước 5) | `9fe55ef` | ✅ Đã push |
| 3 | Verify provenance attestation (bước 6) | `a123b1e` | ✅ Đã push |
| 4 | Attest SBOM lên registry (bước 7) | `38e5077` | ✅ Đã push |
| 5 | Verify SBOM attestation (bước 8) | `d1397a5` | ✅ Đã push |
| 6 | Chạy thử 1 lần build thật trên GitHub Actions, xác nhận cả 8 bước pass | — | ⏳ Chưa chạy — cần trigger `build-and-push.yaml` (push vào `main` có đổi path liên quan, hoặc `workflow_dispatch`) |
| 7 | Merge nhánh `CDO08-SEC-16` vào `main` | — | ⏳ Chưa merge |

### 6.1 Đối chiếu Definition of Done gốc của ticket

| DoD | Trạng thái | Bằng chứng |
|---|---|---|
| Không thể overwrite tag cũ trong ECR | ✅ | `ecr.tf:6` `IMMUTABLE`, commit `5486823` |
| Mỗi pushed image có signature, SBOM, provenance | ✅ | Bước 3 (sign), 7 (SBOM attest), 4 (provenance attest) — chạy theo vòng lặp từng service trong `image-digests.txt` |
| Pipeline fail nếu signing/SBOM/provenance fail | ✅ | Mọi bước 2-8 đều set `security-artifacts/gate_status.txt=1` khi lỗi; step "Enforce security gate results" đọc file này, `exit 1` nếu `=1` |
| Evidence verify cosign/SBOM/provenance được với một image | ✅ | Bước 5 (`cosign verify`), 6 (`cosign verify-attestation --type custom`), 8 (`cosign verify-attestation --type cyclonedx`) — output ra `security-artifacts/*.txt`, upload qua step "Upload security artifacts" có sẵn |

---

## 7. Verification — lệnh mẫu cho một image bất kỳ

Dùng được ngay sau khi có ít nhất 1 lần chạy `build-and-push.yaml` thành công (bước 6 ở §6). Thay `<digest>` bằng digest thật của service muốn kiểm (lấy từ `image-digests.txt` artifact của run đó, hoặc `aws ecr describe-images`).

```powershell
$env:IMAGE = "511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:<digest>"
$env:IDENTITY_REGEXP = "^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/.*@refs/heads/.*$"
$env:ISSUER = "https://token.actions.githubusercontent.com"

# Verify chữ ký
cosign verify --certificate-identity-regexp $env:IDENTITY_REGEXP --certificate-oidc-issuer $env:ISSUER $env:IMAGE

# Verify provenance
cosign verify-attestation --type custom --certificate-identity-regexp $env:IDENTITY_REGEXP --certificate-oidc-issuer $env:ISSUER $env:IMAGE

# Verify SBOM
cosign verify-attestation --type cyclonedx --certificate-identity-regexp $env:IDENTITY_REGEXP --certificate-oidc-issuer $env:ISSUER $env:IMAGE
```

Cho một **pod đang chạy** (thay vì digest biết trước), lấy digest từ chính pod trước:

```powershell
kubectl -n techx-tf4 get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].imageID}'
```

> Chưa chạy các lệnh trên với digest thật trong phiên này (cần `aws sso login` để có quyền đọc ECR — token AWS local đã hết hạn lúc kiểm tra). Đây là lệnh mẫu đúng cú pháp đã verify flag hợp lệ với `cosign --help` cài trên máy, chưa phải evidence đã chạy thành công.

---

## 8. Rollback / Safety

| Tình huống | Rollback | Lý do |
|---|---|---|
| 1 service fail sign/SBOM/provenance/verify trong 1 run | Không cần rollback — `promote` job không chạy (điều kiện `needs.build.result == 'success'`), nên không có PR GitOps nào được tạo, image lỗi không tới ArgoCD/cluster. Sửa lỗi rồi chạy lại `build-and-push.yaml`. | Fail-closed by design — xem §4. |
| ECR `IMMUTABLE` chặn nhầm một thao tác thủ công cần overwrite tag | Không rollback registry — sửa quy trình thủ công để dùng tag mới thay vì tag cũ (đã áp dụng cho runbook REL-09, §5.5). Nếu phát sinh thêm chỗ khác dùng lại tag, sửa tương tự, không đổi `image_tag_mutability` về `MUTABLE`. | Đổi về `MUTABLE` là đảo ngược chính DoD của ticket này. |
| Cần tắt tạm việc ký/SBOM/provenance (vd Fulcio/Rekor sập, chặn toàn bộ build) | Revert riêng các commit `9fe55ef`/`a123b1e`/`38e5077`/`d1397a5` (chỉ thêm verify + SBOM-attest, không đụng sign/SBOM-gen/provenance-attest gốc) hoặc comment tạm step "Security and Attestation" | Ưu tiên khôi phục khả năng build/deploy hơn là giữ đủ evidence tạm thời — nhưng đây là biện pháp khẩn cấp, cần ghi lại lý do + thời gian tắt. |

---

## 9. Coordination

| Role | Người | Trách nhiệm |
|---|---|---|
| Owner | Quân | Viết pipeline, plan doc này |
| Theo dõi riêng (ngoài phạm vi ticket) | Người phụ trách MANDATE-10 #1 | `required_status_checks` chưa có trên ruleset `main` — đã báo cáo, không tự sửa (cần quyền admin repo, hiện tại chỉ có `push`) |
| Theo dõi riêng (ngoài phạm vi ticket) | Người phụ trách MANDATE-10 #3 (nửa sau) | Cluster chưa verify chữ ký tại admission — cần Kyverno/Sigstore policy-controller hoặc tương đương, kèm sửa `clusterResourceWhitelist` của AppProject `techx-production` (repo gitops) để ArgoCD cho phép sync CRD mới — đã báo cáo, không tự triển khai |

---

## 10. Definition of Done

- [x] `infra/terraform/ecr.tf` — `image_tag_mutability = "IMMUTABLE"`.
- [x] Runbook rollback REL-09 cập nhật để không overwrite tag cũ.
- [x] Cosign keyless signing (`cosign sign --yes`, không `--key`) — có sẵn từ PR #293, xác nhận đúng dùng OIDC.
- [x] SBOM CycloneDX (Trivy) mỗi image — có sẵn từ PR #293.
- [x] SBOM attest lên registry (`cosign attest --type cyclonedx`) — mới thêm.
- [x] Provenance attest (`cosign attest --type custom`, gồm repo/commit/workflow/run_id/service/digest) — có sẵn từ PR #293.
- [x] Verify signature, verify provenance, verify SBOM — cả 3 mới thêm, đều fail gate nếu verify hỏng.
- [x] Pipeline fail cứng nếu bất kỳ bước sign/SBOM-gen/SBOM-attest/provenance-attest/verify nào lỗi (`gate_status.txt` + step "Enforce security gate results").
- [ ] Chạy thử thành công 1 lần trên GitHub Actions thật (chưa trigger trong phiên này).
- [ ] Merge nhánh `CDO08-SEC-16` vào `main`.
- [ ] Chạy lệnh verify (§7) với digest thật của ít nhất 1 image, đính evidence (output thật, không phải lệnh mẫu) vào `docs/cdo08/week2/mandate10/evidence/` khi có ảnh/log thật.
