# CDO08-SEC-20 - Mandate 10 End-to-End Provenance Evidence

**Thoi diem kiem tra:** 2026-07-19T20:07:55Z  
**Cluster:** `techx-tf4-cluster`  
**Namespace kiem tra chinh:** `techx-tf4`  
**Pod mau:** `checkout-68f6488757-pdr58`  
**Ket luan hien tai:** **PARTIAL / CHUA DU DIEU KIEN PASS MANDATE 10**

Mandate 10 yeu cau mentor co the tu truy nguoc mot pod dang chay theo chuoi:

```text
running pod -> image digest -> source commit -> PR approval -> scan pass -> signer/provenance -> SBOM
```

He thong hien da co nhieu control quan trong, nhung production runtime hien tai van chua dap ung day du yeu cau "cluster chi chay image da ky va tham chieu theo digest".

---

## 1. Runtime pod digest evidence

Lenh:

```sh
kubectl -n techx-tf4 get pod checkout-68f6488757-pdr58 \
  -o jsonpath='{.metadata.name}{"\n"}{range .status.containerStatuses[*]}{.name}{" image="}{.image}{"\n"}{.name}{" imageID="}{.imageID}{"\n"}{end}'
```

Ket qua:

```text
checkout-68f6488757-pdr58
checkout image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout
checkout imageID=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:a4d43a5b0cc0fe03cc0ed3435d87fb28e1e469af7f4c37c8390eb9f8f22f16f9
```

Trang thai pod:

```sh
kubectl -n techx-tf4 get pod checkout-68f6488757-pdr58 \
  -o jsonpath='{.metadata.creationTimestamp}{"\n"}{.status.containerStatuses[0].ready}{"\n"}{.status.containerStatuses[0].restartCount}{"\n"}'
```

```text
2026-07-18T19:58:15Z
true
0
```

ECR digest read-back:

```sh
aws ecr describe-images \
  --region us-east-1 \
  --repository-name techx-corp \
  --image-ids imageDigest=sha256:a4d43a5b0cc0fe03cc0ed3435d87fb28e1e469af7f4c37c8390eb9f8f22f16f9 \
  --query 'imageDetails[0].{tags:imageTags,digest:imageDigest,pushedAt:imagePushedAt}' \
  --output json
```

```json
{
  "tags": [
    "8340af1-checkout"
  ],
  "digest": "sha256:a4d43a5b0cc0fe03cc0ed3435d87fb28e1e469af7f4c37c8390eb9f8f22f16f9",
  "pushedAt": "2026-07-14T22:04:40.328000+07:00"
}
```

Source commit tu image tag:

```sh
git show --stat --oneline 8340af1
```

```text
8340af1 feat(cdo08): REL-09 timeout/retry cho checkout dependencies (#146)
```

Danh gia:

- **Pass:** runtime co imageID digest that va ECR trace duoc tag `8340af1-checkout` ve digest.
- **Gap:** Deployment manifest van tham chieu image bang tag, khong phai digest:

```sh
kubectl -n techx-tf4 get deploy checkout \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

```text
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout
```

---

## 2. GitOps source evidence

Lenh:

```sh
kubectl -n argocd get application techx-corp \
  -o jsonpath='{range .spec.sources[*]}{.repoURL}{" path="}{.path}{" targetRevision="}{.targetRevision}{"\n"}{end}'
```

Ket qua:

```text
https://github.com/TF4-Phase3-TechX/tf4-phase3-repo.git path=techx-corp-chart targetRevision=cf8e7c1a815f54627e0e13cc9ad87b229a4d8d4f
https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests.git path= targetRevision=main
```

Argo status:

```sh
kubectl -n argocd get application techx-corp \
  -o jsonpath='{.status.sync.revisions}{"\n"}{.status.health.status}{"\n"}{.status.sync.status}{"\n"}'
```

```text
["cf8e7c1a815f54627e0e13cc9ad87b229a4d8d4f","a4a4c728653a69d2ab27ca0aaa060609a4df0ee4"]
Healthy
Synced
```

GitOps image revisions tai commit `a4a4c728653a69d2ab27ca0aaa060609a4df0ee4`:

```yaml
components:
  checkout:
    imageOverride:
      tag: "8340af1-checkout"
```

Danh gia:

- **Pass:** Argo app `techx-corp` dang `Synced/Healthy`.
- **Gap:** GitOps production source hien chi luu `tag`, chua luu `digest` cho `checkout`. Day la blocker cho DoD cua SEC-19/SEC-20.

---

## 3. Pipeline and gate evidence

### 3.1. CI scan gates

File: `.github/workflows/ci.yaml`

Dang co cac gate sau:

| Gate | Evidence trong workflow | Trang thai |
|---|---|---|
| Secret scan | `Secret scan (Gitleaks)` | Co job fail tren secret finding |
| SAST/dependency scan | `SAST & Dependency scan (Trivy)` | Co job fail tren HIGH/CRITICAL |
| IaC scan | `Terraform IaC scan (tfsec)` | Co job fail tren HIGH |
| Helm/Kubernetes manifest scan | `Helm Manifest scan (kube-linter)` | Co job fail neu linter fail |
| Docker smoke build | `Docker smoke build checkout + shipping` | Co build smoke cho checkout/shipping |

### 3.2. Image scan, signing, SBOM, provenance

File: `.github/workflows/build-and-push.yaml`

Dang co step:

```text
Security and Attestation (Scan, Sign, SBOM, Provenance, Verify)
```

Step nay xu ly tung service digest theo 8 buoc:

```text
1. Trivy CVE scan HIGH/CRITICAL
2. Generate CycloneDX SBOM
3. Cosign keyless sign
4. Cosign custom provenance attestation
5. Verify Cosign signature
6. Verify provenance attestation
7. Attest SBOM
8. Verify SBOM attestation
```

Trusted signing identity trong workflow:

```text
issuer: https://token.actions.githubusercontent.com
identity regexp: ^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/.*@refs/heads/main$
```

Danh gia:

- **Pass ve code control:** workflow da co scan/sign/SBOM/provenance/verify va fail gate bang `gate_status.txt`.
- **Gap ve runtime evidence:** chua co artifact URL cua mot successful `build-and-push.yaml` run tren `main` duoc gan vao file nay. Mentor can artifact `security-artifacts-*` va `build-metadata-*` cua dung digest production de verify.
- **Gap local:** may local tai thoi diem kiem tra chua cai `cosign`, nen chua verify truc tiep signature/SBOM/provenance bang CLI local.

Lenh mentor/operator co the chay sau khi co `cosign`:

```sh
IMAGE='511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:a4d43a5b0cc0fe03cc0ed3435d87fb28e1e469af7f4c37c8390eb9f8f22f16f9'
IDENTITY='^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/.*@refs/heads/main$'
ISSUER='https://token.actions.githubusercontent.com'

cosign verify \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$IMAGE"

cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$IMAGE"

cosign verify-attestation \
  --type cyclonedx \
  --certificate-identity-regexp "$IDENTITY" \
  --certificate-oidc-issuer "$ISSUER" \
  "$IMAGE"
```

---

## 4. Immutable dependency evidence

Lenh:

```sh
python3 scripts/check_pinned_dependencies.py --root .
```

Ket qua:

```text
Pinned dependency scan: workflows=4 actions=39 dockerfiles=28 external_images=45
PASS: all external actions and base images are immutably pinned
```

ECR repository:

```sh
aws ecr describe-repositories \
  --region us-east-1 \
  --repository-names techx-corp \
  --query 'repositories[0].{name:repositoryName,mutability:imageTagMutability,scanOnPush:imageScanningConfiguration.scanOnPush}' \
  --output json
```

```json
{
  "name": "techx-corp",
  "mutability": "IMMUTABLE",
  "scanOnPush": true
}
```

Danh gia:

- **Pass:** GitHub Actions va Docker base images da duoc pin bang commit SHA/digest.
- **Pass:** ECR repository da bat immutable tag.
- **Luu y:** ECR scan-on-push chi la bo sung; Mandate 10 yeu cau scan gate truoc promote/deploy, phan nay nam trong `build-and-push.yaml`.

---

## 5. Scoped rebuild and promotion evidence

File: `.github/workflows/build-and-push.yaml`

Workflow chi build cac service thay doi theo path:

```text
techx-corp-platform/src/<service>/
```

Neu chi doi chart:

```text
chart_changed=true
services=[]
```

thi workflow chi mo promotion PR cap nhat chart source SHA, khong build image.

Promotion job cap nhat GitOps bang source SHA va digest map neu co:

```text
image-digests.txt -> IMAGE_DIGESTS_JSON -> environments/production/image-revisions.yaml
```

Danh gia:

- **Pass ve workflow design:** build da scoped theo service thay doi, khong full rebuild mac dinh.
- **Gap runtime hien tai:** production GitOps file chua co digest entries, nen can mot run moi sau SEC-19 de chung minh digest promotion da thuc su ghi vao GitOps va rollout ra cluster.

---

## 6. Admission control evidence

Current admission policies:

```sh
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding
```

```text
validatingadmissionpolicy.admissionregistration.k8s.io/disallow-mutable-image-tag
validatingadmissionpolicy.admissionregistration.k8s.io/require-digest-image-reference
validatingadmissionpolicy.admissionregistration.k8s.io/require-drop-all-capabilities
validatingadmissionpolicy.admissionregistration.k8s.io/require-resource-limits
validatingadmissionpolicy.admissionregistration.k8s.io/require-run-as-nonroot

validatingadmissionpolicybinding.admissionregistration.k8s.io/disallow-mutable-image-tag-binding
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-digest-image-reference-binding
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-drop-all-capabilities-binding
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-resource-limits-binding
validatingadmissionpolicybinding.admissionregistration.k8s.io/require-run-as-nonroot-binding
```

Kyverno signature policy:

```sh
kubectl get imagevalidatingpolicies.policies.kyverno.io -A
```

```text
NAME                          AGE    READY
require-signed-techx-images   110m   true
```

Policy scope hien tai:

```yaml
require-digest-image-reference-binding:
  validationActions:
    - Deny
  matchResources:
    namespaceSelector:
      matchLabels:
        techx.io/sec17-digest-enforce: "true"

require-signed-techx-images:
  validationActions:
    - Deny
  matchConstraints:
    namespaceSelector:
      matchLabels:
        techx.io/sec17-signature-enforce: "true"
```

Namespace labels:

```sh
kubectl get ns techx-tf4 techx-observability techx-admission-test --show-labels
```

```text
techx-tf4              kubernetes.io/metadata.name=techx-tf4,name=techx-tf4
techx-observability    kubernetes.io/metadata.name=techx-observability
techx-admission-test   kubernetes.io/metadata.name=techx-admission-test
```

Negative test da chay:

```sh
kubectl -n techx-admission-test run sec20-latest-negative \
  --image=nginx:latest \
  --dry-run=server -o yaml
```

Ket qua:

```text
The pods "sec20-latest-negative" is invalid: : ValidatingAdmissionPolicy 'disallow-mutable-image-tag' with binding 'disallow-mutable-image-tag-binding' denied request: Image must pin a fixed tag or digest...
```

Tag-only test voi securityContext/resources hop le:

```sh
kubectl -n techx-admission-test run sec20-tagonly-ecr-negative \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-tagonly-ecr-negative","image":"511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Ket qua:

```text
Dry-run accepted.
```

Danh gia:

- **Pass:** policy chan `:latest` dang enforce.
- **Pass:** Kyverno `ImageValidatingPolicy` da `READY=true`.
- **Gap:** digest/signature policies dang scoped bang namespace label `techx.io/sec17-*`, nhung cac namespace `techx-tf4`, `techx-observability`, `techx-admission-test` chua co label nay.
- **Gap:** vi chua label namespace, tag-only ECR image van pass server-side dry-run trong namespace test. Chua du bang chung "unsigned/unscanned image bi reject" theo Mandate 10.

---

## 7. Mentor verification guide

### Buoc 1 - Chon pod va lay digest

```sh
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 get pod <pod-name> \
  -o jsonpath='{.spec.containers[0].image}{"\n"}{.status.containerStatuses[0].imageID}{"\n"}'
```

Expected:

- Pod `Running/Ready`.
- `imageID` co `@sha256:<digest>`.
- De pass Mandate 10 day du, `.spec.containers[0].image` cung phai co digest, khong chi `imageID`.

### Buoc 2 - Truy ECR digest

```sh
aws ecr describe-images \
  --region us-east-1 \
  --repository-name techx-corp \
  --image-ids imageDigest=<sha256:digest> \
  --query 'imageDetails[0].{tags:imageTags,digest:imageDigest,pushedAt:imagePushedAt}'
```

Expected:

- ECR tra ve dung digest va tag service.

### Buoc 3 - Truy commit/PR

```sh
git show --stat --oneline <short-sha-from-tag>
```

Expected:

- Commit message co PR number.
- PR tren GitHub co review approval va required checks pass.

### Buoc 4 - Verify signing/SBOM/provenance

```sh
cosign verify --certificate-identity-regexp "$IDENTITY" --certificate-oidc-issuer "$ISSUER" "$IMAGE"
cosign verify-attestation --type custom --certificate-identity-regexp "$IDENTITY" --certificate-oidc-issuer "$ISSUER" "$IMAGE"
cosign verify-attestation --type cyclonedx --certificate-identity-regexp "$IDENTITY" --certificate-oidc-issuer "$ISSUER" "$IMAGE"
```

Expected:

- Signature verify pass.
- Provenance attestation co repo, commit, workflow, run_id, service name, image digest.
- SBOM attestation verify pass.

### Buoc 5 - Verify admission reject

Can chay tren namespace da duoc gan label enforce:

```sh
kubectl label ns techx-admission-test techx.io/sec17-digest-enforce=true techx.io/sec17-signature-enforce=true --overwrite
```

Sau do chay dry-run tag-only/unsigned image. Expected:

- Tag-only bi reject boi `require-digest-image-reference`.
- Unsigned image bi reject boi `require-signed-techx-images`.
- Signed digest image tu pipeline trusted pass.

Khong nen label production namespace truoc khi GitOps production image revisions da co digest va image moi da co signature/SBOM/provenance.

---

## 8. Final verdict

| Yeu cau Mandate 10 | Trang thai | Evidence |
|---|---|---|
| CI do khong merge/deploy | Chua verify truc tiep trong file nay | Can branch protection/ruleset screenshot/API evidence tu SEC-14 |
| Secret/SAST/IaC/image scan gate | Partial pass | Workflow co gate; can dinh kem successful/failed run artifact |
| ECR immutable | Pass | `imageTagMutability=IMMUTABLE` |
| Actions/base images pinned | Pass | `scripts/check_pinned_dependencies.py` pass |
| Build scoped theo service doi | Pass ve workflow design | `build-and-push.yaml` select affected services |
| Runtime pod trace digest -> commit | Partial pass | `checkout` trace duoc digest -> tag -> commit, nhung manifest tag-only |
| GitOps deploy by digest | **Fail hien tai** | `image-revisions.yaml` chi co `tag`, chua co `digest` |
| Admission reject latest | Pass | `nginx:latest` bi reject |
| Admission reject tag-only/unsigned | **Fail hien tai** | digest/signature policies dang test-scope va namespace chua label |
| Cosign signature/SBOM/provenance verify voi digest production | Chua verify trong phien nay | Local chua co `cosign`; can artifact tu build tren `main` |

**Ket luan:** SEC-20 chua nen dong o trang thai `Done`. He thong da co nen tang control, nhung can hoan tat cac viec sau de pass Mandate 10:

1. Chay mot `build-and-push.yaml` thanh cong tren `main` sau khi SEC-16/SEC-19 da merge, lay artifact `security-artifacts-*` va `build-metadata-*`.
2. Dam bao GitOps promotion PR ghi `digest` cho service duoc build trong `environments/production/image-revisions.yaml`.
3. Rollout service mau de `.spec.containers[0].image` tham chieu digest.
4. Gan label enforce cho namespace test va chup evidence:
   - tag-only bi reject;
   - unsigned image bi reject;
   - signed digest image pass.
5. Sau khi production image revisions da co digest va signature day du, moi mo rong enforce cho production namespace.
