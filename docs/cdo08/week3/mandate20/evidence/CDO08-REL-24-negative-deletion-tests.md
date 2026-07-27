# CDO08-REL-24 Negative Deletion Test Evidence

Status: Runtime evidence captured from GitHub Actions run `30191955252`

## Scope

This test proves that normal CI/operator roles cannot delete protected recovery assets. Runtime evidence was captured from the manual GitHub Actions workflow `.github/workflows/rel24-negative-deletion-tests.yaml`, run from `main`, because the protected CI apply role only trusts GitHub OIDC sessions from `refs/heads/main`.

## Preconditions

- Bootstrap Terraform has applied the CI permissions boundary and explicit deny policy.
- Infra Terraform has applied REL-24 roles and PostgreSQL migration backup bucket policy.
- CloudTrail `tf4-general-cloudtrail` is logging management events and selected S3 data events.
- Test resources are disposable and named with `rel24-negative-test-`.
- PM/Platform confirmed the CI apply role policy simulator result after bootstrap guardrail application.
- Runtime test workflow ran successfully on `main`: `rel24-negative-deletion-tests`, run `30191955252`.

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

## Runtime Evidence Workflow

Workflow:

```text
.github/workflows/rel24-negative-deletion-tests.yaml
```

Why workflow is required:

- The target actor is `tf4-github-actions-terraform-apply`.
- That role trust policy allows GitHub OIDC only for `repo:TF4-Phase3-TechX/tf4-phase3-repo:ref:refs/heads/main`.
- Running from local SSO credentials would prove the wrong actor.

Workflow run:

```text
https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/actions/runs/30191955252
```

Workflow output artifact:

```text
rel24-negative-deletion-evidence
```

The artifact contains command outputs plus CloudTrail / CloudWatch Logs query results.

Runtime summary:

```text
Run time UTC: 2026-07-26T06:58:06Z
Region: us-east-1
Actor ARN: arn:aws:sts::511825856493:assumed-role/tf4-github-actions-terraform-apply/GitHubActions
```

Runtime delete attempt results:

| Test | Runtime result |
| --- | --- |
| RDS snapshot delete | `AccessDenied`, explicit deny in `tf4-rel24-ci-protected-recovery-assets-deny` |
| ElastiCache snapshot delete | `AccessDenied`, explicit deny in identity-based policy |
| S3 archive object delete | `AccessDenied`, explicit deny in `tf4-rel24-ci-protected-recovery-assets-deny` |
| MSK delete | `AccessDeniedException`, explicit deny in `tf4-rel24-ci-protected-recovery-assets-deny` |

Runtime audit query result:

| Event | Audit result |
| --- | --- |
| `DeleteDBSnapshot` | CloudTrail event found: `0851b4de-96ae-4490-ac23-257b9e92d555` at `2026-07-26T06:58:09Z` |
| `DeleteSnapshot` | CloudTrail event found: `22209e0d-5ec5-4449-82c4-4d4bbd8d81a7` at `2026-07-26T06:58:09Z` |
| `DeleteCluster` | CloudTrail event found: `db06d1eb-1bc7-4d79-942d-5e2673ea5eb6` at `2026-07-26T06:58:11Z` |
| `DeleteObject` | CloudTrail S3 data event found in trail S3 log object: `0bcdcb4e-4e18-41fc-a4e8-3c6774c9b9bd` at `2026-07-26T06:58:10Z` |

S3 `DeleteObject` audit source: `s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/us-east-1/2026/07/26/511825856493_CloudTrail_us-east-1_20260726T0700Z_ihVD5Y1OUwIRj2jt.json.gz`.

## Policy Simulation Pre-Check

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

Conclusion: the normal CI apply role is expected to be blocked from deleting the protected recovery asset classes required by REL-24. This is a pre-check only; the runtime workflow above is required for CloudTrail-backed evidence.

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
| RDS snapshot delete | `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-terraform-apply/GitHubActions` | `rds:DeleteDBSnapshot` | `rel24-negative-test-rds` | `AccessDenied` explicit deny in `tf4-rel24-ci-protected-recovery-assets-deny` | `0851b4de-96ae-4490-ac23-257b9e92d555` / `2026-07-26T06:58:09Z` |
| ElastiCache snapshot delete | `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-terraform-apply/GitHubActions` | `elasticache:DeleteSnapshot` | `rel24-negative-test-valkey` | `AccessDenied` explicit deny in identity-based policy | `22209e0d-5ec5-4449-82c4-4d4bbd8d81a7` / `2026-07-26T06:58:09Z` |
| S3 archive object delete | `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-terraform-apply/GitHubActions` | `s3:DeleteObject` | `rel15/rel24-negative-test-object` | `AccessDenied` explicit deny in `tf4-rel24-ci-protected-recovery-assets-deny` | `0bcdcb4e-4e18-41fc-a4e8-3c6774c9b9bd` / `2026-07-26T06:58:10Z` |
| MSK delete | `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-terraform-apply/GitHubActions` | `kafka:DeleteCluster` | disposable `rel24-negative-test-msk` ARN | `AccessDeniedException` explicit deny in `tf4-rel24-ci-protected-recovery-assets-deny` | `db06d1eb-1bc7-4d79-942d-5e2673ea5eb6` / `2026-07-26T06:58:11Z` |
