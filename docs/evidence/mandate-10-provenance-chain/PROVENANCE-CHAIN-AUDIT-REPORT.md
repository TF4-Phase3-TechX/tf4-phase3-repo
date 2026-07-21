# MANDATE-10 — Bằng chứng kiểm toán chuỗi Provenance

**Người phụ trách:** Nguyễn Phú Triệu (CDO-07 Auditability)
**Phạm vi:** Chỉ kiểm tra chuỗi Provenance
**Thời điểm thu thập bằng chứng:** 2026-07-21
**Nhánh nguồn:** `main`

## 1. Phạm vi kiểm toán

Tài liệu này ghi nhận kết quả kiểm tra độc lập, chỉ đọc đối với chuỗi
Provenance của image theo yêu cầu MANDATE-10:

```text
Pod đang chạy
  -> Image Digest thực tế
  -> Metadata image trong ECR
  -> Chữ ký Cosign
  -> Attestation Provenance/SBOM theo in-toto
  -> Workflow và commit của GitHub Actions
```

PR này không thay đổi GitHub Actions, Terraform, ECR, cơ chế admission của
Kubernetes, branch protection hoặc workload production. Bằng chứng phê duyệt
của con người và kiểm tra branch protection được dành riêng cho luồng công
việc `H2`.

## 2. Kết quả kiểm tra trực tiếp

Các giá trị dưới đây được thu thập trực tiếp từ EKS, ECR, Cosign và GitHub
Actions. Các file JSON/text được lưu giữ trong thư mục bằng chứng cục bộ
`D:\evidence\M10`.

| Liên kết cần kiểm tra | Giá trị quan sát được | Kết quả |
|---|---|---|
| Pod | `techx-tf4/currency-858bcdfbc6-pq4rb` | PASS |
| Image thực tế | `techx-corp:a930936-currency` | PASS |
| Digest thực tế | `sha256:663bf6d56564e82cd767233bb70c45df6818a18d64781a7dc37732a4247e791c` | PASS |
| So khớp digest ECR | Digest của Pod bằng digest trong ECR | PASS |
| Chữ ký | Cosign exit code `0`; claims, certificate và transparency log đã được xác minh | PASS |
| OIDC issuer | `https://token.actions.githubusercontent.com` | PASS |
| Workflow ký | `build-and-push`, `refs/heads/main` | PASS |
| Commit Provenance | `a93093665767a27c40b71e6597b10c1ce20dd702` | PASS |
| Lần chạy GitHub Actions | `29811592226`, kết luận `success` | PASS |
| SBOM | CycloneDX (`cyclonedx-sbom`) | PASS |
| Kết quả lỗ hổng | `0` phát hiện trong bản tóm tắt attestation/scan đã thu thập | PASS |

## 3. Danh mục bằng chứng

### Chuỗi Provenance — đính kèm vào sub-task Provenance

| Bằng chứng | Mục đích |
|---|---|
| `images/P1-01-cluster-context.png` | Ghi nhận ngữ cảnh cluster: `techx-tf4-cluster`, ACTIVE, Kubernetes 1.34 |
| `images/P1-02-pod-runtime-image-digest.png` | Lấy image và digest bất biến từ Pod đang chạy |
| `images/P1-03-ecr-digest-match.png` | Xác nhận digest và tag tương ứng tồn tại trong ECR |
| `images/P1-04-cosign-signature-verification.png` | Hiển thị kết quả xác minh chữ ký Cosign PASS |
| `images/P1-05-provenance-attestation-sbom-retake-required.png` | Cần chụp lại; bản hiện tại đếm nhầm thuộc tính SBOM |
| `PROVENANCE-CHAIN-RECORD.json` | Bản ghi hợp nhất về runtime, registry, chữ ký, attestation, scan và pipeline |

File raw `06-cosign-attestation.txt` chỉ được giữ bên ngoài repository làm
bản sao lưu. File này quá dài để dùng làm ảnh Jira; bản JSON hợp nhất là bản
dùng cho việc review.

## 4. Kết luận kiểm toán

Đối với workload `currency` được kiểm tra, digest của image đang chạy có thể
truy vết đến image trong ECR, chữ ký OIDC hợp lệ của GitHub Actions, attestation
in-toto đã ký, workflow `build-and-push`, commit SHA chính xác, lần chạy
Actions và SBOM CycloneDX.

Chuỗi quan sát được:

```text
Pod currency
  -> sha256:663bf6d56564e82cd767233bb70c45df6818a18d64781a7dc37732a4247e791c
  -> build-and-push / run 29811592226
  -> commit a93093665767a27c40b71e6597b10c1ce20dd702
  -> provenance đã ký + SBOM CycloneDX
```

## 5. Phát hiện: PR ID không phải trường trực tiếp trong attestation

Delivery predicate đã thu thập có repository, commit, workflow, run ID, tên
service, image digest và dữ liệu SBOM. Không quan sát thấy trường
`pull_request_number` trong attestation.

Vì vậy:

1. Liên kết digest với commit được chứng minh bằng mật mã trong PR này.
2. PR ID có thể được đối chiếu từ commit thông qua GitHub API.
3. Việc đưa trực tiếp PR ID vào signed predicate cần pipeline owner thay đổi
   pipeline; Audit không thực hiện thay đổi production đó.
4. Đối chiếu commit với PR, danh tính người phê duyệt và kết quả branch
   protection thuộc luồng Human Approval (`H2`) riêng.

## 6. Đã rà soát phần phụ thuộc triển khai của CDO08

CDO08 đã triển khai các kiểm soát delivery nền tảng. Các thay đổi liên quan
được rà soát cho mục đích kiểm toán và không bị sửa trong PR này:

- `origin/cdo08/sec20-fix-combined-sbom-provenance-attestation` — kết hợp
  delivery predicate đã ký với SBOM CycloneDX và xác minh digest.
- `origin/cdo08/sec20-fix-sbom-attestation-verify` — tăng cường xác minh
  attestation và xử lý retry.
- `origin/cdo08/sec20-fix-ecr-cosign-mutability-workflow` — xử lý hành vi
  artifact tag của ECR Cosign trong delivery workflow.
- `origin/CDO08-SEC-20-provenance-evidence` — bằng chứng SEC-20 và tài liệu
  hướng dẫn của team triển khai.

Đóng góp của Audit là xác minh độc lập và tổ chức bằng chứng, không triển khai
lại các kiểm soát delivery.

## 7. Hướng dẫn đính kèm lên Jira

Sau khi chụp lại P1-05, đính kèm bốn ảnh P1-* đạt yêu cầu và bản ghi JSON hợp
nhất vào sub-task Provenance Chain. Không đính kèm ảnh `H2-*` vào PR này; các
ảnh đó dành cho branch Human Approval riêng.
