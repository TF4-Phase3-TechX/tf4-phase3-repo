# CDO08-REL-24 Bootstrap Guardrail Blocker

Status: Blocked - PM/Platform action required

Task: `[CDO08-REL-24][P0][Security] Protect backups and archives from unauthorized deletion`

## Summary

REL-24 has applied the infra-side operational roles, but the bootstrap-side guardrail for the normal CI apply role has not been applied. Because of that, the 4 negative deletion tests cannot produce valid `AccessDenied` evidence yet.

## Current State

The following REL-24 roles exist in AWS:

- `tf4-rel24-backup-admin`
- `tf4-rel24-restore-operator`
- `tf4-rel24-backup-delete-break-glass`

The role that must be protected and tested is:

- `tf4-github-actions-terraform-apply`

Current AWS inspection showed this role still has:

- `PowerUserAccess`
- `IAMFullAccess`

But it does not yet have:

- permissions boundary `tf4-rel24-protected-recovery-assets-guardrail`
- attached deny policy `tf4-rel24-ci-protected-recovery-assets-deny`

IAM policy simulation for the CI apply role still evaluates the protected delete actions as `allowed`:

- `rds:DeleteDBSnapshot`
- `elasticache:DeleteSnapshot`
- `s3:DeleteObject`
- `kafka:DeleteCluster`

## Impact

The evidence step is blocked. Running the negative deletion tests now would not prove the required control, because the CI apply role is not yet protected by the REL-24 bootstrap guardrail.

This blocks the Definition of Done items:

- Normal CI/operator cannot delete backup/archive.
- Delete attempts have audit evidence.

## Root Cause

The REL-24 change spans both:

- `infra/terraform`: creates backup admin, restore operator, break-glass roles, S3 archive controls, and CloudTrail evidence selectors.
- `infra/bootstrap`: adds the permissions boundary and explicit deny policy to `tf4-github-actions-terraform-apply`.

The observed CI/CD apply appears to have applied `infra/terraform`, but not the required `infra/bootstrap` changes.

Local `terraform -chdir=infra/bootstrap plan` showed bootstrap state drift / missing state management, with many existing bootstrap resources planned as `to add`. Because of that, bootstrap should not be applied blindly from local without Platform review.

## Requested PM/Platform Action

Please unblock REL-24 by applying the bootstrap guardrail with the correct bootstrap state/import flow.

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
  --policy-source-arn arn:aws:iam::<account-id>:role/tf4-github-actions-terraform-apply \
  --action-names rds:DeleteDBSnapshot elasticache:DeleteSnapshot s3:DeleteObject kafka:DeleteCluster \
  --resource-arns "*"
```

Expected simulator result after unblock:

- `explicitDeny` or deny-equivalent result for all protected delete actions.

## Next Step After Unblock

After the bootstrap guardrail is applied, CDO08 will run the 4 negative deletion tests and fill:

`docs/cdo08/week3/mandate20/evidence/CDO08-REL-24-negative-deletion-tests.md`

Evidence table will capture:

- actor ARN
- action
- target
- result
- CloudTrail event ID/time

