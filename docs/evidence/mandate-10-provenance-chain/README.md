# MANDATE-10 — Provenance Chain Evidence Pack

This directory contains the CDO07 Audit evidence for the read-only Provenance
Chain sub-task:

```text
Running Pod -> Image Digest -> ECR -> Cosign Signature
             -> Provenance/SBOM Attestation -> GitHub Actions Commit
```

## Scope

This pack verifies the live delivery chain. It does not change the pipeline,
ECR, Terraform, Kubernetes admission, branch protection, or production
workloads.

Human approval, PR reviewer identity, and branch-protection evidence are kept
out of this pack and belong to the separate Human Approval (`H2`) workstream.

## Directory map

| Path | Purpose |
|---|---|
| `PROVENANCE-CHAIN-AUDIT-REPORT.md` | Auditor conclusion, findings, and CDO08 dependency review |
| `RUNBOOK.md` | Reproducible live collection and screenshot procedure |
| `screenshots/` | Compact human-readable terminal evidence |
| `raw/` | Small machine-readable/text evidence records |

## Screenshot status

| Screenshot | Status | Meaning |
|---|---|---|
| `S1-00-cluster-context.png` | Ready | EKS cluster context |
| `S1-01-pod-runtime-image-digest.png` | Ready | Runtime Pod digest |
| `S1-02-ecr-digest-match.png` | Ready | ECR digest equality |
| `S1-03-cosign-signature-verification.png` | Ready | Cosign signature PASS |
| `S1-04-provenance-attestation-sbom.png` | Retake required | Previous screenshot counted the wrong SBOM property |

The attestation data itself is valid and the compact raw summary records
`Vulnerabilities: 0`. The S1-04 screenshot must be recaptured using the
correct `sbom.document.vulnerabilities` path before it is attached as final
Jira evidence.

The H2 screenshots remain in the local evidence workspace only:

```text
D:\evidence\M10\H2-01-pr-commit-link.png
D:\evidence\M10\H2-02-pr-approval-reviewers.png
D:\evidence\M10\H2-03-main-branch-protection.png
```

## Live evidence identity

The captured record is for:

```text
Cluster:  techx-tf4-cluster
Region:   us-east-1
Namespace: techx-tf4
Service:  currency
Digest:   sha256:663bf6d56564e82cd767233bb70c45df6818a18d64781a7dc37732a4247e791c
Commit:   a93093665767a27c40b71e6597b10c1ce20dd702
Run ID:   29811592226
```
