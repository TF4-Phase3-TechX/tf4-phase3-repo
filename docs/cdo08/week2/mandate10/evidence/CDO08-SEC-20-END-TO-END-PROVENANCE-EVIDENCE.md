# CDO08-SEC-20 - Mandate 10 End-to-End Provenance Evidence

**Thoi diem kiem tra:** 2026-07-20T18:49:50Z  
**Cluster:** `techx-tf4-cluster`  
**Namespace kiem tra chinh:** `techx-tf4`  
**Namespace admission test:** `techx-admission-test`  
**Ket luan hien tai:** **PARTIAL / CHUA DU DIEU KIEN PASS MANDATE 10**

Mandate 10 yeu cau mentor co the chi vao mot pod dang chay va truy nguoc duoc:

```text
running pod -> image digest -> source commit -> PR approval -> scan pass -> signer/provenance -> SBOM
```

He thong hien da co nhieu control quan trong, nhung production runtime van chua dap ung day du yeu cau "cluster chi chay image da ky va tham chieu theo digest".

---

## 1. Tom tat ket qua

| Hang muc Mandate 10 | Trang thai | Evidence hien tai |
|---|---|---|
| CI/scan gate co ton tai | Partial pass | `.github/workflows/ci.yaml`, `.github/workflows/build-and-push.yaml` co secret scan, Trivy, tfsec, kube-linter, image CVE scan |
| ECR immutable | Pass | `techx-corp` co `imageTagMutability=IMMUTABLE` |
| Actions/base images pinned | Pass | `scripts/check_pinned_dependencies.py --root .` pass |
| Build scoped theo service thay doi | Pass ve workflow design | `build-and-push.yaml` chon service theo path change |
| Runtime app healthy | Pass | `techx-corp` Argo app `Synced/Healthy`, key deployments ready |
| Runtime image co digest thuc te | Partial pass | Pod runtime co `imageID=@sha256`, nhung Deployment spec van dung tag |
| GitOps deploy bang digest | Fail hien tai | `image-revisions.yaml` chi co `tag`, chua co `digest` |
| Admission chan `latest` | Pass | Server-side dry-run `nginx:latest` bi reject |
| Admission chan tag-only/unsigned image | Fail hien tai | Digest/signature policy van `test-scope-only`; tag-only ECR image van duoc accept trong namespace test |
| Signature/SBOM/provenance verify tren production digest | Chua du evidence | Can artifact cua successful `build-and-push` run dung digest production va/hoac `cosign` local verify |

---

## 2. GitOps va runtime hien tai

Lenh:

```sh
kubectl -n argocd get application techx-corp \
  -o jsonpath='{range .spec.sources[*]}{.repoURL}{" path="}{.path}{" targetRevision="}{.targetRevision}{"\n"}{end}{"sync="}{.status.sync.status}{" health="}{.status.health.status}{" revisions="}{.status.sync.revisions}{"\n"}'
```

Ket qua:

```text
https://github.com/TF4-Phase3-TechX/tf4-phase3-repo.git path=techx-corp-chart targetRevision=b218451c8ae3903dbe4eeeadd7958beafb13fee1
https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests.git path= targetRevision=main
sync=Synced health=Healthy revisions=["b218451c8ae3903dbe4eeeadd7958beafb13fee1","818d230cb8621838c08bf52e5f3e532e3d09571d"]
```

Lenh:

```sh
kubectl -n techx-tf4 get deploy checkout frontend payment product-catalog shipping \
  -o jsonpath='{range .items[*]}{.metadata.name}{" image="}{.spec.template.spec.containers[0].image}{" replicas="}{.status.readyReplicas}{"/"}{.spec.replicas}{"\n"}{end}'
```

Ket qua:

```text
checkout image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout replicas=2/2
frontend image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:411e9a2-frontend replicas=3/3
payment image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-payment replicas=2/2
product-catalog image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-product-catalog replicas=2/2
shipping image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-shipping replicas=2/2
```

Danh gia:

- App runtime dang healthy.
- Deployment spec van la tag-only, vi du `:8340af1-checkout`.
- Mandate 10 chua pass vi production chua chay `repo:tag@sha256:<digest>`.

---

## 3. GitOps image revisions

File:

```text
../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml
```

Ket qua hien tai:

```yaml
components:
  checkout:
    imageOverride:
      tag: "8340af1-checkout"
  frontend:
    imageOverride:
      tag: "411e9a2-frontend"
  payment:
    imageOverride:
      tag: "8340af1-payment"
  product-catalog:
    imageOverride:
      tag: "8340af1-product-catalog"
  shipping:
    imageOverride:
      tag: "8340af1-shipping"
```

Expected de pass:

```yaml
components:
  checkout:
    imageOverride:
      tag: "<short-sha>-checkout"
      digest: "sha256:<digest>"
```

Danh gia:

- Source chart da co helper render image dang `repo:tag@sha256:<digest>` khi `imageOverride.digest` ton tai.
- GitOps production hien chua co `digest`, nen runtime van khong the render digest-pinned image.

---

## 4. CI/CD gate va attestation control

### 4.1 CI gate

File:

```text
.github/workflows/ci.yaml
```

Workflow co cac gate:

| Gate | Trang thai thiet ke |
|---|---|
| Secret scan | `Secret scan (Gitleaks)` |
| SAST/dependency scan | `SAST & Dependency scan (Trivy)` |
| IaC scan | `Terraform IaC scan (tfsec)` |
| Helm/Kubernetes lint | `Helm Manifest scan (kube-linter)` |

### 4.2 Image scan/sign/SBOM/provenance

File:

```text
.github/workflows/build-and-push.yaml
```

Workflow co step:

```text
Security and Attestation (Scan, Sign, SBOM, Provenance, Verify)
```

Step nay xu ly tung service digest:

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

Trusted signer:

```text
issuer: https://token.actions.githubusercontent.com
identity regexp: ^https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/.*@refs/heads/main$
```

Danh gia:

- Workflow da co control can thiet.
- Chua du evidence de pass production vi can artifact cua successful run gan voi digest dang rollout.

---

## 5. Immutable dependency va ECR

Lenh:

```sh
python3 scripts/check_pinned_dependencies.py --root .
```

Ket qua:

```text
Pinned dependency scan: workflows=4 actions=39 dockerfiles=28 external_images=45
PASS: all external actions and base images are immutably pinned
```

Lenh:

```sh
aws ecr describe-repositories \
  --region us-east-1 \
  --repository-names techx-corp \
  --query 'repositories[0].{name:repositoryName,mutability:imageTagMutability,scanOnPush:imageScanningConfiguration.scanOnPush}' \
  --output json
```

Ket qua:

```json
{
  "name": "techx-corp",
  "mutability": "IMMUTABLE",
  "scanOnPush": true
}
```

Danh gia:

- ECR immutable: pass.
- Action/base image pinning: pass.
- ECR scan-on-push chi la bo sung; gate chinh van phai la pre-deploy scan trong workflow.

---

## 6. Admission control evidence

Lenh:

```sh
kubectl get validatingadmissionpolicy,validatingadmissionpolicybinding
```

Ket qua hien co:

```text
disallow-mutable-image-tag
require-digest-image-reference
require-resource-limits
require-run-as-nonroot
require-drop-all-capabilities
disallow-hostpath-volumes
disallow-privileged-and-host-access
```

Kyverno image signature policy:

```sh
kubectl get imagevalidatingpolicy require-signed-techx-images -o yaml
```

Ket qua rut gon:

```text
name: require-signed-techx-images
ready: true
validationActions:
- Deny
namespaceSelector:
  matchLabels:
    techx.io/sec17-signature-enforce: "true"
```

Digest policy binding:

```text
require-digest-image-reference-binding
namespaceSelector:
  matchLabels:
    techx.io/sec17-digest-enforce: "true"
validationActions:
- Deny
```

Namespace labels:

```sh
kubectl get ns techx-tf4 techx-observability techx-admission-test --show-labels
```

```text
techx-tf4              kubernetes.io/metadata.name=techx-tf4,name=techx-tf4,techx.io/policy-scope=enforced
techx-observability    kubernetes.io/metadata.name=techx-observability
techx-admission-test   kubernetes.io/metadata.name=techx-admission-test
```

### Negative test 1 - latest image

Lenh:

```sh
kubectl -n techx-admission-test run sec20-latest-negative \
  --image=nginx:latest \
  --dry-run=server -o yaml
```

Ket qua:

```text
The pods "sec20-latest-negative" is invalid: :
ValidatingAdmissionPolicy 'disallow-mutable-image-tag' with binding
'disallow-mutable-image-tag-binding' denied request:
Image must pin a fixed tag or digest...
```

Danh gia: pass. `latest` bi chan.

### Negative test 2 - ECR tag-only image

Lenh:

```sh
kubectl -n techx-admission-test run sec20-tagonly-ecr-negative \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-tagonly-ecr-negative","image":"511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:8340af1-checkout","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Ket qua:

```text
apiVersion: v1
kind: Pod
metadata:
  name: sec20-tagonly-ecr-negative
  namespace: techx-admission-test
status:
  phase: Pending
```

Danh gia: fail cho Mandate 10. ECR tag-only image van duoc admission accept vi namespace test chua duoc label `techx.io/sec17-digest-enforce=true` va `techx.io/sec17-signature-enforce=true`.

---

## 7. Viec can lam de chuyen sang PASS

### Buoc 1 - Tao image moi bang workflow da co scan/sign/SBOM/provenance

Chay `build-and-push.yaml` tren `main` cho service mau, uu tien `checkout` hoac `frontend`.

Can lay evidence:

```text
security-artifacts-*
build-metadata-*
image-digests.txt
```

Expected:

```text
Trivy image scan: PASS
Cosign signature verify: PASS
Provenance attestation verify: PASS
SBOM attestation verify: PASS
```

### Buoc 2 - Merge GitOps promotion PR co digest

File can thay doi:

```text
tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml
```

Expected:

```yaml
checkout:
  imageOverride:
    tag: "<short-sha>-checkout"
    digest: "sha256:<digest>"
```

### Buoc 3 - Sync va verify runtime deploy bang digest

Lenh:

```sh
kubectl -n techx-tf4 get deploy checkout \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Expected:

```text
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:<short-sha>-checkout@sha256:<digest>
```

### Buoc 4 - Verify provenance tu pod dang chay

Lenh:

```sh
kubectl -n techx-tf4 get pod <checkout-pod> \
  -o jsonpath='{.spec.containers[0].image}{"\n"}{.status.containerStatuses[0].imageID}{"\n"}'
```

Expected:

```text
spec image co @sha256
status imageID cung digest
```

Neu may operator co `cosign`, verify:

```sh
IMAGE='511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:<digest>'
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

### Buoc 5 - Bat enforce tren namespace test va chay negative/positive admission

Lenh:

```sh
kubectl label ns techx-admission-test \
  techx.io/sec17-digest-enforce=true \
  techx.io/sec17-signature-enforce=true \
  --overwrite
```

Expected:

- `nginx:latest` bi reject.
- ECR tag-only bi reject.
- Signed digest image tu trusted workflow pass.

### Buoc 6 - Chi bat production enforce sau khi production da co digest/signature

Khong label `techx-tf4` voi `techx.io/sec17-digest-enforce=true` va `techx.io/sec17-signature-enforce=true` khi production con tag-only. Neu bat som, rollout production co the bi admission reject.

---

## 8. Final verdict

SEC-20 **chua nen dong Done** tai thoi diem nay.

Ly do:

1. Runtime production van tag-only.
2. GitOps production image revisions chua co digest.
3. Digest/signature admission policy dang `test-scope-only`.
4. Tag-only ECR image van duoc server-side dry-run accept trong namespace test.
5. Chua co successful build artifact gan voi digest production moi sau khi cac fix SBOM/provenance da merge.

Dieu kien de cap nhat ket luan thanh PASS:

- Co mot pod production chay image dang `repo:tag@sha256:<digest>`.
- GitOps source co `tag` va `digest` tu promotion PR.
- Artifact workflow co scan/sign/SBOM/provenance verify pass cho dung digest.
- Admission test reject `latest`, reject tag-only/unsigned, accept signed digest image.
- Sau do moi mo rong enforce cho production namespace theo tung wave.
