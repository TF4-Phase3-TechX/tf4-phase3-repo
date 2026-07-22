# CDO08-SEC-20 - Evidence Mandate 10: Secure Delivery Pipeline

**Thoi diem kiem tra:** 2026-07-22T07:15:11Z  
**Cluster:** `techx-tf4-cluster`  
**Namespace runtime:** `techx-tf4`  
**Ket luan:** **PASS voi pham vi TF4 application images**

Mandate 10 yeu cau khi chi vao mot pod dang chay, team phai truy nguoc duoc:

```text
running pod -> image digest -> source commit -> workflow -> signer -> SBOM/provenance
```

Evidence duoi day dung pod `load-generator` lam mau live trace.

---

## 1. Runtime dang chay image theo digest

Lenh:

```sh
kubectl -n techx-tf4 get pod -l opentelemetry.io/name=load-generator \
  -o jsonpath='{.items[0].metadata.name}{"\n"}{.items[0].spec.containers[0].image}{"\n"}{.items[0].status.containerStatuses[0].imageID}{"\n"}'
```

Ket qua:

```text
load-generator-777d9f8c68-bw855
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
```

Danh gia:

- Pod dang chay dung image co digest bat bien.
- Digest trong `spec.containers[0].image` khop voi `status.containerStatuses[0].imageID`.

---

## 2. Signature Cosign hop le

Lenh:

```sh
cosign verify \
  --certificate-identity-regexp '^https://github\.com/TF4-Phase3-TechX/tf4-phase3-repo/\.github/workflows/.*@refs/heads/main$' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
```

Ket qua rut gon:

```text
Verification for 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The code-signing certificate was verified using trusted certificate authority certificates

Issuer: https://token.actions.githubusercontent.com
Subject: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main
GitHub Workflow Name: build-and-push
GitHub Workflow Repository: TF4-Phase3-TechX/tf4-phase3-repo
GitHub Workflow Ref: refs/heads/main
GitHub Workflow SHA: 694654e2113b71d7d3ff188948fdb1b640cef3fc
```

Danh gia:

- Image digest live da duoc ky bang Cosign keyless.
- Signer la GitHub Actions OIDC cua repo `TF4-Phase3-TechX/tf4-phase3-repo`.
- Workflow ky la `build-and-push.yaml` tren `refs/heads/main`.

---

## 3. Provenance va SBOM attestation hop le

Lenh:

```sh
cosign verify-attestation \
  --type custom \
  --certificate-identity-regexp '^https://github\.com/TF4-Phase3-TechX/tf4-phase3-repo/\.github/workflows/.*@refs/heads/main$' \
  --certificate-oidc-issuer 'https://token.actions.githubusercontent.com' \
  --output json \
  511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 \
  > /private/tmp/sec20-load-generator-attestation.jsonl
```

Ket qua verify rut gon:

```text
Verification for 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The code-signing certificate was verified using trusted certificate authority certificates

Certificate subject: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/.github/workflows/build-and-push.yaml@refs/heads/main
Certificate issuer URL: https://token.actions.githubusercontent.com
GitHub Workflow Trigger: push
GitHub Workflow SHA: 694654e2113b71d7d3ff188948fdb1b640cef3fc
GitHub Workflow Name: build-and-push
GitHub Workflow Repository: TF4-Phase3-TechX/tf4-phase3-repo
GitHub Workflow Ref: refs/heads/main
```

Lenh parse predicate:

```sh
jq -r '.payload' /private/tmp/sec20-load-generator-attestation.jsonl \
  | base64 -d \
  | jq '(.predicate.Data | fromjson) | {kind, repo, commit, workflow, run_id, service_name, image_digest, provenance, sbom: {kind: .sbom.kind, bomFormat: .sbom.bomFormat, documentBomFormat: .sbom.document.bomFormat, vulnerabilities: .sbom.document.vulnerabilities}}'
```

Ket qua:

```json
{
  "kind": "secure-delivery-evidence",
  "repo": "TF4-Phase3-TechX/tf4-phase3-repo",
  "commit": "694654e2113b71d7d3ff188948fdb1b640cef3fc",
  "workflow": "build-and-push",
  "run_id": "29897119328",
  "service_name": "load-generator",
  "image_digest": "sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781",
  "provenance": {
    "repo": "TF4-Phase3-TechX/tf4-phase3-repo",
    "commit": "694654e2113b71d7d3ff188948fdb1b640cef3fc",
    "workflow": "build-and-push",
    "run_id": "29897119328",
    "service_name": "load-generator",
    "image_digest": "sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781"
  },
  "sbom": {
    "kind": "cyclonedx-sbom",
    "bomFormat": "CycloneDX",
    "documentBomFormat": "CycloneDX",
    "vulnerabilities": []
  }
}
```

Danh gia:

- Attestation co provenance tro ve repo, commit, workflow, run id va service name.
- Attestation co SBOM dang CycloneDX.
- SBOM cua image mau khong con HIGH/CRITICAL vulnerability trong artifact da ky.

---

## 4. Admission enforcement tren namespace runtime

Lenh:

```sh
kubectl get ns techx-tf4 -o jsonpath='{.metadata.labels}{"\n"}'
```

Ket qua:

```json
{
  "kubernetes.io/metadata.name": "techx-tf4",
  "name": "techx-tf4",
  "techx.io/policy-scope": "enforced",
  "techx.io/sec17-digest-enforce": "true",
  "techx.io/sec17-signature-enforce": "true"
}
```

Lenh:

```sh
kubectl get imagevalidatingpolicy require-signed-techx-images \
  -o jsonpath='{.status.conditionStatus.ready}{"\n"}{.spec.validationActions}{"\n"}{.spec.matchConstraints.namespaceSelector}{"\n"}'
```

Ket qua:

```text
true
["Deny"]
{"matchLabels":{"techx.io/sec17-signature-enforce":"true"}}
```

Lenh:

```sh
kubectl get validatingadmissionpolicybinding require-digest-image-reference-binding \
  -o jsonpath='{.spec.validationActions}{"\n"}{.spec.matchResources.namespaceSelector}{"\n"}'
```

Ket qua:

```text
["Deny"]
{"matchLabels":{"techx.io/sec17-digest-enforce":"true"}}
```

Danh gia:

- Namespace runtime da bat ca digest enforce va signature enforce.
- Digest policy va signature policy deu chay o che do `Deny`.

---

## 5. Admission negative/positive tests

### 5.1. Reject image `latest`

Lenh:

```sh
kubectl -n techx-tf4 run sec20-latest-negative \
  --image=nginx:latest \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-latest-negative","image":"nginx:latest","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Ket qua:

```text
The pods "sec20-latest-negative" is invalid: :
ValidatingAdmissionPolicy 'disallow-mutable-image-tag' with binding
'disallow-mutable-image-tag-binding' denied request:
Image must pin a fixed tag or digest ... ':latest' ... are not allowed.
```

### 5.2. Reject TF4 ECR tag-only image

Lenh:

```sh
kubectl -n techx-tf4 run sec20-ecr-tagonly-negative \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-ecr-tagonly-negative","image":"511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Ket qua:

```text
The pods "sec20-ecr-tagonly-negative" is invalid: :
ValidatingAdmissionPolicy 'require-digest-image-reference' with binding
'require-digest-image-reference-binding' denied request:
TF4 ECR image must be pinned by immutable digest:
repo@sha256:<digest> or repo:tag@sha256:<digest>.
```

### 5.3. Accept signed TF4 ECR digest image

Lenh:

```sh
kubectl -n techx-tf4 run sec20-ecr-signed-digest-positive \
  --image=511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781 \
  --dry-run=server -o yaml \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"sec20-ecr-signed-digest-positive","image":"511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781","securityContext":{"allowPrivilegeEscalation":false,"runAsNonRoot":true,"capabilities":{"drop":["ALL"]}},"resources":{"requests":{"cpu":"10m","memory":"16Mi"},"limits":{"cpu":"50m","memory":"64Mi"}}}]}}'
```

Ket qua rut gon:

```yaml
apiVersion: v1
kind: Pod
metadata:
  annotations:
    kyverno.io/image-verification-outcomes: '{"require-signed-techx-images":{"name":"require-signed-techx-images","ruleType":"ImageVerify","message":"success","status":"pass"}}'
  name: sec20-ecr-signed-digest-positive
  namespace: techx-tf4
spec:
  containers:
  - image: 511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:694654e-load-generator@sha256:f8f812d08422916771406a059f22442b43940e8564e38b2ed4bf28542a8e0781
```

Danh gia:

- `latest` bi chan.
- TF4 ECR tag-only image bi chan.
- TF4 ECR signed digest image duoc chap nhan va Kyverno verify signature thanh cong.

---

## 6. Runtime image coverage

Lenh:

```sh
kubectl -n techx-tf4 get deploy -o wide
kubectl -n techx-tf4 get rollout cart -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}{.status.phase}{"\n"}'
```

Ket qua rut gon:

```text
accounting        ...:c553182-accounting@sha256:2989...        1/1
ad                ...:b0374a9-ad@sha256:78ee...                1/1
currency          ...:a930936-currency@sha256:663b...          2/2
email             ...:694654e-email@sha256:f751...             1/1
fraud-detection   ...:c553182-fraud-detection@sha256:0516...   1/1
frontend          ...:c646c2b-frontend@sha256:84ba...          2/2
frontend-proxy    ...:8340af1-frontend-proxy@sha256:7a2d...    2/2
image-provider    ...:694654e-image-provider@sha256:82b1...    1/1
llm               ...:8340af1-llm@sha256:92bd...               1/1
load-generator    ...:694654e-load-generator@sha256:f8f8...    1/1
payment           ...:8340af1-payment@sha256:3ec5...           2/2
product-catalog   ...:8340af1-product-catalog@sha256:e0c6...   2/2
product-reviews   ...:d1c4632-product-reviews@sha256:f8a9...   1/1
quote             ...:8340af1-quote@sha256:c0a0...             2/2
recommendation    ...:8340af1-recommendation@sha256:7ed0...    1/1
shipping          ...:8340af1-shipping@sha256:496b...          2/2

cart rollout:
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:0f983db-cart@sha256:4b6d4958d2fdbeb4862b5d83965d754a3b4551b3c9fd44e58eda2f350374ce28
Healthy
```

Ghi chu:

- `cart` dung Argo Rollout, khong phai Deployment, nhung Rollout `cart` dang `Healthy` va image cung da pin digest.
- `flagd` la external control service `ghcr.io/open-feature/flagd:v0.12.9`, nam ngoai pham vi TF4 ECR image signing/enforcement va khong duoc sua theo quyet dinh cua team.
- `kafka` khong con runtime app pod trong `techx-tf4` sau MSK cutover; entry tag-only trong GitOps neu con ton tai la stale/non-runtime va can don dep rieng neu muon dashboard GitOps sach hon.

---

## 7. Final verdict

Mandate 10 dat muc **PASS cho TF4 application images**:

- CI/CD da scan image truoc deploy va fail khi co HIGH/CRITICAL CVE.
- ECR immutable da bat.
- Runtime app images dang chay theo digest.
- Cosign signature cua live digest verify thanh cong.
- Provenance attestation tro ve repo, commit, workflow va run id.
- SBOM CycloneDX ton tai trong attestation va khong co vulnerabilities trong image mau.
- Admission policy chay `Deny`: reject `latest`, reject TF4 ECR tag-only, accept signed TF4 ECR digest.

Phan can theo doi sau:

- Codify label `techx.io/sec17-signature-enforce=true` trong GitOps namespace management neu namespace label dang duoc quan ly ngoai cluster.
- Don dep stale GitOps entry cho workload khong con runtime neu can lam Argo/GitOps sach hoan toan.
