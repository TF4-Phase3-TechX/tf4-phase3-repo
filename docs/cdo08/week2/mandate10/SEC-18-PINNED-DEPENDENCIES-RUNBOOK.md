# SEC-18: Updating Pinned GitHub Actions and Docker Base Images

- **Task:** CDO08-SEC-18
- **Owner:** Nhân
- **Repositories:** `tf4-phase3-repo`, `tf4-phase3-gitops-manifests`

## Purpose

This runbook describes how to upgrade GitHub Actions and Docker base images while keeping every external dependency immutable. Never remove a SHA or digest to perform an upgrade.

Disallowed references:

```yaml
uses: actions/checkout@v4
uses: owner/action@main
uses: owner/action@master
uses: owner/action@stable
```

```dockerfile
FROM node:latest
FROM node:22-alpine
FROM ubuntu
```

Allowed references:

```yaml
uses: actions/checkout@<full-40-character-commit-sha> # v4
```

```dockerfile
FROM node:22-alpine@sha256:<64-character-digest>
```

## Scan Scope

Source repository:

```text
tf4-phase3-repo/.github/workflows/*.yml
tf4-phase3-repo/.github/workflows/*.yaml
tf4-phase3-repo/**/Dockerfile*
```

GitOps repository:

```text
tf4-phase3-gitops-manifests/.github/workflows/*.yml
tf4-phase3-gitops-manifests/.github/workflows/*.yaml
```

The GitOps repository currently contains no Dockerfiles. Its verification evidence should report `Dockerfiles scanned: 0` rather than silently omitting the scan.

## Updating a GitHub Action

1. Review the desired release and breaking changes in the action's official GitHub repository.
2. Resolve the desired tag directly from that repository. For example, in PowerShell:

   ```powershell
   git ls-remote https://github.com/actions/checkout.git `
     "refs/tags/v4" `
     "refs/tags/v4^{}"
   ```

3. If the command returns an annotated tag object and a peeled `^{}` reference, use the peeled commit SHA. Otherwise, use the commit SHA returned for the tag.
4. Confirm that the selected SHA contains exactly 40 hexadecimal characters.
5. Replace every use of the old reference and update the readable version comment:

   ```yaml
   # Before
   uses: actions/checkout@<old-40-character-sha> # v4

   # After
   uses: actions/checkout@<new-40-character-sha> # v5
   ```

6. Do not commit an intermediate moving reference such as `actions/checkout@v5`.
7. Do not add SHAs to local actions or reusable workflows that begin with `./`:

   ```yaml
   uses: ./.github/actions/example
   uses: ./.github/workflows/reusable.yaml
   ```

## Updating a Docker Base Image

1. Review the desired release from the official registry or upstream repository.
2. Select an exact, readable tag. Do not use `latest`, a tag containing `latest`, or an image with no tag.
3. Resolve the digest:

   ```powershell
   docker buildx imagetools inspect node:22-alpine
   ```

4. Record the top-level OCI index or manifest-list digest:

   ```text
   Digest: sha256:<64-character-digest>
   ```

   Do not use a layer digest. Prefer the multi-platform index digest when it supports the deployment platform.

5. Confirm support for at least `linux/amd64`. Confirm `linux/arm64` as well when multi-architecture builds are required.
6. Update every external builder and runtime stage:

   ```dockerfile
   FROM golang:1.24-bookworm@sha256:<builder-digest> AS builder
   FROM gcr.io/distroless/static-debian12:nonroot@sha256:<runtime-digest>
   ```

7. Do not pin an internal stage name:

   ```dockerfile
   FROM builder AS final
   FROM base AS release
   ```

8. For variable-based base images, pin the default value and do not override it with a floating build argument:

   ```dockerfile
   ARG BASE_IMAGE="image:tag@sha256:<digest>"
   FROM ${BASE_IMAGE}
   ```

9. A digest does not make a `latest` tag acceptable:

   ```dockerfile
   # Disallowed
   FROM image:v1-latest@sha256:<digest>

   # Allowed
   FROM image:v1.2.3@sha256:<digest>
   ```

## Local Verification

Run the guard from the root of each repository:

```bash
python3 scripts/check_pinned_dependencies.py --self-test
```

On Windows when Python is not installed, use a pinned Python container:

```powershell
$pythonImage = "python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b"
docker run --rm `
  -v "${PWD}:/repo" `
  -w /repo `
  $pythonImage `
  python scripts/check_pinned_dependencies.py --self-test
```

The expected result is:

```text
PASS: all external actions and base images are immutably pinned
```

The guard must return exit code `1` for a floating dependency.

## Smoke Build

The application build context is `tf4-phase3-repo/techx-corp-platform`. Build every service affected by a base-image update. At minimum, SEC-18 verifies `checkout` and `shipping`.

```powershell
docker buildx build `
  --platform linux/amd64 `
  --load `
  --file src/checkout/Dockerfile `
  --tag checkout:pin-update-test `
  .
```

Also build services with special builder/runtime stages or variable-based images when those images change. If a build fails, compare it with the previous known-good pin to distinguish an image regression from a pre-existing application issue. Never fix a build by removing the digest.

## Required Checks Before Merge

GitHub Actions:

- [ ] SHA is a full 40-character commit SHA from the official repository.
- [ ] Annotated tags were resolved to the peeled commit.
- [ ] The version comment matches the release represented by the SHA.
- [ ] Release notes and breaking changes were reviewed.
- [ ] No external action uses `@v*`, `@main`, `@master`, or another tag.
- [ ] Affected workflows and `check-pinned-dependencies` pass.

Docker base images:

- [ ] Every external `FROM` has `@sha256:<64-hex>`.
- [ ] No image uses `latest` or an untagged reference.
- [ ] The digest came from the official registry and matches the readable tag.
- [ ] The digest supports the required deployment platform.
- [ ] Builder and runtime stages were checked.
- [ ] Affected image builds and service smoke tests pass.
- [ ] Image scanning satisfies the current HIGH/CRITICAL vulnerability policy.
- [ ] `check-pinned-dependencies` passes.

Repository and review checks:

- [ ] Both source and GitOps repositories were scanned.
- [ ] Both PRs pass CI and link to CDO08-SEC-18.
- [ ] Before/after inventory or scan evidence is attached to the PR or Jira.
- [ ] Required reviewers approve the change.
- [ ] `check-pinned-dependencies` is green and required before merge.

## Rollback

If a new SHA or digest causes a regression:

1. Do not merge the failing update.
2. Restore the previous known-good SHA or digest.
3. Keep the immutable reference format.
4. Review breaking changes, correct the configuration or application in the appropriate task, and rerun the guard, build, and smoke tests.

Valid rollback:

```yaml
uses: owner/action@<previous-known-good-40-character-sha> # version
```

```dockerfile
FROM image:tag@sha256:<previous-known-good-digest>
```

Do not roll back to `@v4`, `@main`, `:latest`, or a tag-only image. If both the old and new pins fail identically, record a pre-existing issue in Jira and handle it outside SEC-18.

## Exceptions and Allowlist Approval

The default policy is no exceptions. An allowlist entry is permitted only when immutable pinning has no technical solution and the exception is explicitly approved by the **Security Owner and Platform Owner**.

Every exception must record:

- dependency and file;
- technical justification and risk;
- Security/Platform approvers;
- expiration date;
- Jira remediation task.

Do not use an allowlist merely because updating a pin is inconvenient.

## Branch Protection

After the workflow first runs, repository administrators must require this status check on `main` in both repositories:

```text
check-pinned-dependencies
```

A failing guard must block merge. Store ruleset or branch-protection evidence in Jira or the PR.

## Maintenance Cadence

- Review Action and base-image updates at least monthly.
- Update immediately for relevant critical CVEs or security advisories.
- Perform every update through a reviewed PR; never update `main` directly.
- Dependabot or Renovate may propose pin updates, but each PR still requires guard, build, security scan, and reviewer approval.

## SEC-18 Pull Requests

SEC-18 changes two Git repositories, so it requires one PR for `tf4-phase3-repo` and one PR for `tf4-phase3-gitops-manifests`. Both PRs must link to CDO08-SEC-18 and this runbook.
