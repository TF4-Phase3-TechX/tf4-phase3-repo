# EPIC-01 Evidence - OBS-03: Repo auditability artifacts

EVIDENCE UPDATE

Owner group: CDO-07 Auditability

## What Changed

- Updated `.github/CODEOWNERS` to make ownership explicit for auditability artifacts.
- Added ADR template at `docs/audit/templates/ADR_TEMPLATE.md`.
- Added runbook template at `docs/audit/templates/RUNBOOK_TEMPLATE.md`.
- Added postmortem/COE template at `docs/audit/templates/POSTMORTEM_TEMPLATE.md`.
- Added destination folder for real ADR documents at `docs/audit/adr/`.
- Added destination folder for real runbooks at `docs/audit/runbooks/`.
- Added destination folder for real postmortem/COE documents at `docs/audit/postmortems/`.

## Current Result

- The repo now has reusable templates for change management, operational response, and incident/postmortem review.
- The repo also documents where real auditability documents should be created after copying from the templates.
- CODEOWNERS now has explicit ownership paths for `docs/audit/**`, `docs/evidence/**`, and `.github/**`.
- OBS-03 locally meets the docs/governance target: CODEOWNERS path coverage exists and ADR/runbook/postmortem artifacts are available.
- Runtime verification: N/A because this is a docs/governance-only change.
- Live verification: not live-verified yet; GitHub CODEOWNERS check is pending on PR #44.

## Evidence Location

- CODEOWNERS: `.github/CODEOWNERS`
- ADR template: `docs/audit/templates/ADR_TEMPLATE.md`
- Runbook template: `docs/audit/templates/RUNBOOK_TEMPLATE.md`
- Postmortem/COE template: `docs/audit/templates/POSTMORTEM_TEMPLATE.md`
- ADR destination folder: `docs/audit/adr/README.md`
- Runbook destination folder: `docs/audit/runbooks/README.md`
- Postmortem/COE destination folder: `docs/audit/postmortems/README.md`
- PR: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/44
- Evidence folder: `docs/evidence/epic-01`

## Verification

- Local file review:
  - `.github/CODEOWNERS`
  - `docs/audit/templates/ADR_TEMPLATE.md`
  - `docs/audit/templates/RUNBOOK_TEMPLATE.md`
  - `docs/audit/templates/POSTMORTEM_TEMPLATE.md`
  - `docs/audit/adr/README.md`
  - `docs/audit/runbooks/README.md`
  - `docs/audit/postmortems/README.md`
- Expected command before commit:

```powershell
git status --short
git diff --stat
```

## Notes / Follow-up

- Update the PR link in this evidence file after the PR is opened.
- Check the GitHub CODEOWNERS validation result on the PR.
- If the team creates a dedicated GitHub group for CDO-07, update `.github/CODEOWNERS` to include that group as the appropriate owner.
