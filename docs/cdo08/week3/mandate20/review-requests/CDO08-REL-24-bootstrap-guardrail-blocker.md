# CDO08-REL-24 Bootstrap Guardrail Blocker

Status: Resolved by PM/Platform simulator verification

Task: `[CDO08-REL-24][P0][Security] Protect backups and archives from unauthorized deletion`

## Summary

REL-24 previously appeared blocked because the bootstrap-side guardrail for the normal CI apply role had not been confirmed. PM/Platform later confirmed the protected delete actions now evaluate to `explicitDeny` for `tf4-github-actions-terraform-apply` in IAM `SimulatePrincipalPolicy`.

## Current State

The following REL-24 roles exist in AWS:

- `tf4-rel24-backup-admin`
- `tf4-rel24-restore-operator`
- `tf4-rel24-backup-delete-break-glass`

The role that must be protected and tested is:

- `tf4-github-actions-terraform-apply`

This role retains the broad managed policies kept for Terraform compatibility:

- `PowerUserAccess`
- `IAMFullAccess`

PM/Platform verification shows the REL-24 guardrail/explicit deny now constrains the CI apply role: IAM policy simulation evaluates the protected delete actions as `explicitDeny`:

- `rds:DeleteDBSnapshot`
- `elasticache:DeleteSnapshot`
- `s3:DeleteObject`
- `kafka:DeleteCluster`

## Impact

The original blocker is resolved for policy-control evidence. The evidence file has been updated with simulator results. If mentor requires runtime CloudTrail audit events, CDO08 still needs a temporary CI job to attempt deletes against disposable `rel24-negative-test-*` targets and append the resulting CloudTrail event IDs.

This previously blocked the Definition of Done items:

- Normal CI/operator cannot delete backup/archive.
- Delete attempts have audit evidence.

## Root Cause

The REL-24 change spans both:

- `infra/terraform`: creates backup admin, restore operator, break-glass roles, S3 archive controls, and CloudTrail evidence selectors.
- `infra/bootstrap`: adds the permissions boundary and explicit deny policy to `tf4-github-actions-terraform-apply`.

The observed CI/CD apply initially appeared to have applied `infra/terraform`, but not the required `infra/bootstrap` changes.

Local `terraform -chdir=infra/bootstrap plan` showed bootstrap state drift / missing state management, with many existing bootstrap resources planned as `to add`. Because of that, bootstrap should not be applied blindly from local without Platform review.

## Requested PM/Platform Action

No further PM/Platform action is required for simulator-based policy evidence.

Required end state for `tf4-github-actions-terraform-apply`:

- permissions boundary set to `tf4-rel24-protected-recovery-assets-guardrail`
- managed policy `tf4-rel24-ci-protected-recovery-assets-deny` attached
- existing CI apply flow remains able to run allowed Terraform plan/apply operations

Suggested verification commands:

```bash
aws iam get-role \
  --role-name tf4-github-actions-terraform-apply

aws iam list-attached-role-policies \
  --role-name tf4-github-actions-terraform-apply

aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply \
  --action-names rds:DeleteDBSnapshot elasticache:DeleteSnapshot s3:DeleteObject kafka:DeleteCluster \
  --resource-arns "*"
```

Observed simulator result after unblock:

- `explicitDeny` for all protected delete actions.

## Next Step After Unblock

After PM/Platform verification, CDO08 updated:

`docs/cdo08/week3/mandate20/evidence/CDO08-REL-24-negative-deletion-tests.md`

Simulator evidence table captures:

- actor ARN
- action
- target
- result
- CloudTrail event ID/time as N/A because no live delete was attempted
