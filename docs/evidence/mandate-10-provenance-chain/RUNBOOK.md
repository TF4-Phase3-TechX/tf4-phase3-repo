# MANDATE-10 Provenance Chain Runbook

## 1. Audit rule

Every evidence item must be collected from the live system during the same
verification window. Do not reconstruct a result by displaying an old JSON or
text file in the terminal.

The raw record may be retained after collection, but the terminal output used
for a screenshot must come from the command that queried EKS, ECR, Cosign, or
GitHub at that time.

## 2. Pre-flight

Run these commands in the same terminal session:

```powershell
aws sts get-caller-identity
kubectl config current-context
kubectl get pods -n techx-tf4
gh auth status
cosign version
```

The AWS identity must be the read-only Audit role. If the named AWS profile is
not configured locally, use the already-valid current AWS session and do not
add a nonexistent `--profile` argument.

## 3. Live collection sequence

Use the following order so every later check uses the exact digest obtained
from the running Pod:

1. Select a Running `currency` Pod and display `imageID` and the extracted
   `sha256` digest.
2. Query ECR by that exact digest and display `DigestMatch: True`.
3. Run `cosign verify` with the GitHub Actions OIDC issuer and `main` workflow
   identity restriction.
4. Run `cosign verify-attestation --type custom` and decode only the compact
   predicate fields.
5. Confirm the attestation digest equals the runtime digest and that the SBOM
   is CycloneDX.

The full PowerShell commands used for the live run are documented in the
parent Audit ticket and should be pasted as a block, not typed manually one
line at a time.

## 4. Correct SBOM count extraction

The custom delivery predicate stores the vulnerability list under
`sbom.document.vulnerabilities`. Reading `sbom.vulnerabilities` returns null;
in Windows PowerShell, counting that null can incorrectly display `1`.

Use this logic in the compact attestation output:

```powershell
$sbomDocument = $data.sbom.document
$vulnerabilityCount = 0
if ($null -ne $sbomDocument -and $null -ne $sbomDocument.vulnerabilities) {
    $vulnerabilityCount = @($sbomDocument.vulnerabilities).Count
}

[PSCustomObject]@{
    Attestation        = "PASS"
    Repository         = $data.repo
    CommitSHA          = $data.commit
    Workflow           = $data.workflow
    GitHubRunID        = $data.run_id
    ImageDigest        = $data.image_digest
    DigestMatch        = ($data.image_digest -eq $digest)
    SBOMKind           = $data.sbom.kind
    SBOMFormat         = $data.sbom.bomFormat
    Vulnerabilities    = $vulnerabilityCount
} | Format-List
```

## 5. Screenshot standard

Capture only the final compact result, not the long command history and not the
474 KB raw attestation payload. The screenshot must show:

- the evidence title or step name;
- the image digest or relevant object identifier;
- the PASS/FAIL result;
- the signer, workflow, commit, or SBOM fields relevant to that step.

Recommended names:

```text
P1-01-cluster-context.png
P1-02-pod-runtime-image-digest.png
P1-03-ecr-digest-match.png
P1-04-cosign-signature-verification.png
P1-05-provenance-attestation-sbom-retake-required.png
```

Use `Win + Shift + S` after the compact result is visible. Keep the raw
command output separately for reproducibility.

## 6. Automation

The repository already contains the read-only automation entry point:

```text
scripts/trace-image-provenance.sh
```

From Git Bash, it can collect the chain from a selected Pod:

```bash
bash scripts/trace-image-provenance.sh --pod <running-pod-name>
```

It performs the Pod, ECR, Cosign, attestation, GitHub Actions, and source
lookup steps when the required tools and read permissions are available. It
also reports skipped steps instead of presenting inferred data as verified.

Automation is appropriate for:

- collecting live JSON/text records;
- decoding the attestation;
- comparing the runtime and attestation digests;
- calculating a final PASS/PARTIAL/FAIL result;
- producing a checksum manifest for the evidence directory.

Screenshots are only the presentation layer. They may remain manual because a
human reviewer should see the compact result in the same terminal session.
Automating screenshots is possible, but it does not improve the cryptographic
evidence and can hide stale terminal state.

## 7. Audit limitations to report

- The signed predicate currently contains the commit SHA and build metadata,
  but no direct `pull_request_number` field.
- The commit-to-PR and reviewer checks are intentionally outside this Provenance
  Chain pack and belong to the H2 branch.
- A missing AWS ECR read permission must be reported as a collection blocker;
  it must not be silently replaced with a tag-only inference.
