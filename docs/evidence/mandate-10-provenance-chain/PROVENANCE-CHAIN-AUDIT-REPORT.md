# MANDATE-10 — Provenance Chain Audit Evidence

**Owner:** CDO07 Audit
**Scope:** Provenance Chain only
**Evidence collection:** 2026-07-21
**Source branch:** `main`

## 1. Audit scope

This document records an independent, read-only verification of the image
provenance chain required by MANDATE-10:

```text
Running Pod
  -> runtime Image Digest
  -> ECR image metadata
  -> Cosign signature
  -> in-toto provenance/SBOM attestation
  -> GitHub Actions workflow and commit
```

This PR does not change GitHub Actions, Terraform, ECR, Kubernetes admission,
branch protection, or production workloads. Human approval evidence and branch
protection review are intentionally reserved for the separate `H2` workstream.

## 2. Live verification result

The following values were collected directly from EKS, ECR, Cosign, and GitHub
Actions. The JSON/text files are retained in the local evidence directory
`D:\evidence\M10`.

| Link | Observed value | Result |
|---|---|---|
| Pod | `techx-tf4/currency-858bcdfbc6-pq4rb` | PASS |
| Runtime image | `techx-corp:a930936-currency` | PASS |
| Runtime digest | `sha256:663bf6d56564e82cd767233bb70c45df6818a18d64781a7dc37732a4247e791c` | PASS |
| ECR digest equality | Pod digest equals ECR digest | PASS |
| Signature | Cosign exit code `0`; claims, certificate, and transparency log verified | PASS |
| OIDC issuer | `https://token.actions.githubusercontent.com` | PASS |
| Signing workflow | `build-and-push`, `refs/heads/main` | PASS |
| Provenance commit | `a93093665767a27c40b71e6597b10c1ce20dd702` | PASS |
| GitHub Actions run | `29811592226`, conclusion `success` | PASS |
| SBOM | CycloneDX (`cyclonedx-sbom`) | PASS |
| Vulnerability result | `0` findings in the captured attestation/scan summary | PASS |

## 3. Evidence index

### Provenance Chain — attach to the Provenance sub-task

| Evidence | Purpose |
|---|---|
| `screenshots/S1-00-cluster-context.png` | Cluster context: `techx-tf4-cluster`, ACTIVE, Kubernetes 1.34 |
| `screenshots/S1-01-pod-runtime-image-digest.png` | Obtains the image and immutable digest from the running Pod |
| `screenshots/S1-02-ecr-digest-match.png` | Confirms the same digest and tag exist in ECR |
| `screenshots/S1-03-cosign-signature-verification.png` | Shows Cosign signature verification PASS |
| `screenshots/S1-04-provenance-attestation-sbom.png` | Required final screenshot; previous copy needs recapture because it counted the wrong SBOM property |
| `raw/03-pod-runtime-image-digest.json` | Machine-readable Pod runtime record |
| `raw/04-ecr-manifest.json` | Machine-readable ECR manifest record |
| `raw/05-cosign-provenance-sbom-summary.json` | Compact provenance and SBOM summary |
| `raw/05-cosign-signature-verification.txt` | Compact Cosign verification record |
| `raw/06-build-metadata.json` | Build metadata linking commit, service tag, and image digest |
| `raw/06-actions-run.json` | GitHub Actions run status and commit |
| `raw/06-trivy-scan.txt` | Human-readable scan result |
| `raw/06-gate-status.txt` | Pipeline gate result; `0` means no gate failure was recorded |

The raw `06-cosign-attestation.txt` is retained outside the repository as a
backup only. It is too
large for a useful Jira screenshot; the compact attestation screenshot and JSON
summary are the review copies.

## 4. Auditor conclusion

For the captured `currency` workload, the runtime image digest is traceable to
the ECR image, a valid GitHub Actions OIDC signature, a signed in-toto
attestation, the `build-and-push` workflow, the exact commit SHA, the Actions
run, and the CycloneDX SBOM.

The observed chain is:

```text
currency Pod
  -> sha256:663bf6d56564e82cd767233bb70c45df6818a18d64781a7dc37732a4247e791c
  -> build-and-push / run 29811592226
  -> commit a93093665767a27c40b71e6597b10c1ce20dd702
  -> signed provenance + CycloneDX SBOM
```

## 5. Finding: PR number is not a direct attestation field

The captured delivery predicate contains repository, commit, workflow, run ID,
service name, image digest, and SBOM data. A `pull_request_number` field was
not observed in the attestation.

Therefore:

1. The digest-to-commit link is cryptographically evidenced in this PR.
2. A PR number can be correlated from the commit through the GitHub API.
3. Direct inclusion of the PR number in the signed predicate would require a
   change by the pipeline owner; Audit does not make that production change.
4. The commit-to-PR correlation, approver identity, and branch-protection
   result belong to the separate Human Approval (`H2`) workstream.

## 6. CDO08 implementation dependency reviewed

CDO08 already implemented the underlying delivery controls. The relevant work
was reviewed for audit context and is not modified by this PR:

- `origin/cdo08/sec20-fix-combined-sbom-provenance-attestation` — combines the
  signed delivery predicate with the CycloneDX SBOM and verifies the digest.
- `origin/cdo08/sec20-fix-sbom-attestation-verify` — hardens attestation
  verification and retry handling.
- `origin/cdo08/sec20-fix-ecr-cosign-mutability-workflow` — handles the ECR
  Cosign artifact-tag behavior in the delivery workflow.
- `origin/CDO08-SEC-20-provenance-evidence` — implementation team's SEC-20
  evidence and mentor guide.

The Audit contribution is independent verification and evidence organization,
not reimplementation of those controls.

## 7. Jira attachment guidance

Attach the four final `S1-*` screenshots and the compact JSON/text records to
the Provenance Chain sub-task after S1-04 is recaptured. Do not attach the
`H2-*` screenshots to this PR; they are reserved for the separate Human
Approval branch.
