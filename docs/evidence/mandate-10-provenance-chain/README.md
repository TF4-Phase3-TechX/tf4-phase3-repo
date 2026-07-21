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
| `images/` | Compact human-readable terminal evidence |
| `PROVENANCE-CHAIN-RECORD.json` | Consolidated machine-readable evidence record |

## Screenshot status

| Screenshot | Status | Meaning |
|---|---|---|
| `P1-01-cluster-context.png` | Ready | EKS cluster context |
| `P1-02-pod-runtime-image-digest.png` | Ready | Runtime Pod digest |
| `P1-03-ecr-digest-match.png` | Ready | ECR digest equality |
| `P1-04-cosign-signature-verification.png` | Ready | Cosign signature PASS |
| `P1-05-provenance-attestation-sbom-retake-required.png` | Retake required | Previous screenshot counted the wrong SBOM property |

The attestation data itself is valid and the consolidated record stores
`vulnerabilityCount: 0`. The P1-05 screenshot must be recaptured using the
correct `sbom.document.vulnerabilities` path before it is attached as final
Jira evidence.

The H2 screenshots remain in the local evidence workspace only:

```text
D:\evidence\M10\H2-01-commit-to-pr.png
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
