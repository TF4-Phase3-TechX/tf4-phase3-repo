# CDO08-REL-24 Negative Deletion Test Evidence

Status: Policy simulation evidence captured - CloudTrail runtime attempts pending only if mentor requires live audit events

## Scope

This test proves that normal CI/operator roles cannot delete protected recovery assets. The current evidence uses IAM `SimulatePrincipalPolicy` for the protected CI apply role to avoid destructive operations against production recovery assets. If mentor requires runtime audit events, run the same actions from a temporary CI job against disposable `rel24-negative-test-*` assets and append CloudTrail event IDs.

## Preconditions

- Bootstrap Terraform has applied the CI permissions boundary and explicit deny policy.
- Infra Terraform has applied REL-24 roles and PostgreSQL migration backup bucket policy.
- CloudTrail `tf4-general-cloudtrail` is logging management events and selected S3 data events.
- Test resources are disposable and named with `rel24-negative-test-`.
- PM/Platform confirmed the CI apply role policy simulator result after bootstrap guardrail application.

## Role ARNs

Collect these from Terraform outputs:

```bash
terraform -chdir=infra/bootstrap output github_actions_terraform_apply_role_arn
terraform -chdir=infra/bootstrap output rel24_ci_recovery_asset_guardrail_policy_arn
terraform -chdir=infra/bootstrap output rel24_ci_recovery_asset_explicit_deny_policy_arn
terraform -chdir=infra/terraform output rel24_backup_admin_role_arn
terraform -chdir=infra/terraform output rel24_restore_operator_role_arn
terraform -chdir=infra/terraform output rel24_backup_delete_break_glass_role_arn
terraform -chdir=infra/terraform output rel24_msk_orders_archive_bucket_name
```

## Negative Tests

Run each delete attempt from the normal role path being tested. For CI, run from a temporary GitHub Actions job that assumes `tf4-github-actions-terraform-apply`; for a human normal operator, use the operator role session.

## Policy Simulation Evidence

Verification source: AWS CLI live verification on 2026-07-26T10:59:42+07:00, matching PM/Platform IAM `SimulatePrincipalPolicy` screenshot.

Verifier caller identity:

```json
{
  "Account": "511825856493",
  "Arn": "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10/thuy"
}
```

Policy source:

```text
arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply
```

CI apply role guardrails observed:

```text
PermissionsBoundary: arn:aws:iam::511825856493:policy/tf4-rel24-protected-recovery-assets-guardrail
Attached policy:     arn:aws:iam::511825856493:policy/tf4-rel24-ci-protected-recovery-assets-deny
Compatibility allow: IAMFullAccess + PowerUserAccess still attached, constrained by the explicit deny and boundary.
```

Command:

```bash
aws iam simulate-principal-policy \
  --policy-source-arn arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply \
  --action-names rds:DeleteDBSnapshot elasticache:DeleteSnapshot s3:DeleteObject kafka:DeleteCluster \
  --resource-arns "*"
```

Simulation result:

| Action | Decision |
| --- | --- |
| `rds:DeleteDBSnapshot` | `explicitDeny` |
| `elasticache:DeleteSnapshot` | `explicitDeny` |
| `s3:DeleteObject` | `explicitDeny` |
| `kafka:DeleteCluster` | `explicitDeny` |

Matched deny sources:

- `tf4-rel24-ci-protected-recovery-assets-deny`
- `tf4-rel24-protected-recovery-assets-guardrail` permissions boundary

Conclusion: the normal CI apply role is blocked from deleting the protected recovery asset classes required by REL-24. This satisfies the policy-control portion of the negative deletion test without touching production assets.

### RDS Snapshot Delete

```bash
aws rds delete-db-snapshot \
  --db-snapshot-identifier rel24-negative-test-rds \
  --region "$AWS_REGION"
```

Expected result: `AccessDenied` or explicit deny mentioning protected recovery assets.

### ElastiCache Snapshot Delete

```bash
aws elasticache delete-snapshot \
  --snapshot-name rel24-negative-test-valkey \
  --region "$AWS_REGION"
```

Expected result: `AccessDenied` or explicit deny.

### S3 Archive Object Version Delete

```bash
aws s3api delete-object \
  --bucket "tf4-postgresql-migration-backups-${AWS_ACCOUNT_ID}-${AWS_REGION}" \
  --key "rel15/rel24-negative-test-object" \
  --version-id "$REL24_TEST_VERSION_ID" \
  --region "$AWS_REGION"
```

Expected result: `AccessDenied` from bucket policy or identity explicit deny.

### MSK Protected Deletion

Use a disposable test cluster or IAM policy simulator if no safe cluster exists.

```bash
aws kafka delete-cluster \
  --cluster-arn "$REL24_TEST_MSK_CLUSTER_ARN" \
  --region "$AWS_REGION"
```

Expected result: `AccessDenied` for normal CI/operator. Do not point this at `techx-tf4-orders`.

## Approved Workflow Smoke Test

Assume the backup admin role with approval tags and perform a non-destructive read plus create-only operation on a disposable test object.

```bash
aws sts assume-role \
  --role-arn "$REL24_BACKUP_ADMIN_ROLE_ARN" \
  --role-session-name rel24-backup-admin-smoke \
  --tags Key=Rel24Approval,Value=approved Key=ChangeId,Value=CDO08-REL-24

aws s3api put-object \
  --bucket "tf4-postgresql-migration-backups-${AWS_ACCOUNT_ID}-${AWS_REGION}" \
  --key "rel15/rel24-negative-test-object" \
  --body ./rel24-negative-test-object.txt \
  --region "$AWS_REGION"
```

Expected result: put succeeds for the approved backup admin role; delete remains denied unless the break-glass role is used with deletion approval tags.

## CloudTrail Evidence Queries

Management events:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=DeleteDBSnapshot \
  --region "$AWS_REGION"
```

S3 object delete data events are delivered to the configured trail and CloudWatch Logs. Query the log group for denied archive deletes:

```bash
aws logs start-query \
  --log-group-name /aws/cloudtrail/tf4-general-cloudtrail \
  --start-time "$REL24_QUERY_START_EPOCH" \
  --end-time "$REL24_QUERY_END_EPOCH" \
  --query-string "fields @timestamp, userIdentity.arn, eventName, errorCode, requestParameters.bucketName, requestParameters.key | filter eventName like /DeleteObject/ and errorCode like /AccessDenied/ | sort @timestamp desc" \
  --region "$AWS_REGION"
```

Record the following for each test:

| Test | Actor ARN | Action | Target | Result | CloudTrail event ID/time |
| --- | --- | --- | --- | --- | --- |
| RDS snapshot delete | `arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply` | `rds:DeleteDBSnapshot` | protected RDS snapshots | `explicitDeny` by IAM simulator | N/A - simulator evidence, no live delete attempted |
| ElastiCache snapshot delete | `arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply` | `elasticache:DeleteSnapshot` | protected ElastiCache snapshots | `explicitDeny` by IAM simulator | N/A - simulator evidence, no live delete attempted |
| S3 archive object delete | `arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply` | `s3:DeleteObject` | protected backup/archive object prefixes | `explicitDeny` by IAM simulator | N/A - simulator evidence, no live delete attempted |
| MSK delete | `arn:aws:iam::511825856493:role/tf4-github-actions-terraform-apply` | `kafka:DeleteCluster` | protected MSK cluster class | `explicitDeny` by IAM simulator | N/A - simulator evidence, no live delete attempted |
