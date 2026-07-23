# CDO08-REL-24 Backup Deletion Separation of Duties

Status: Proposed for PM/Tech Lead approval

## Decision

Protected recovery assets for RDS accounting/PostgreSQL, ElastiCache Valkey cart, MSK orders archive, AWS Config archive, and migration backup buckets must not be deleted by normal CI or normal operators. Backup creation, restore, and exceptional deletion are split across separate roles.

## Responsibility Matrix

| Workflow | Requester | Approver | Executor | Guardrail |
| --- | --- | --- | --- | --- |
| Terraform plan/apply for allowed infra changes | Platform engineer | PR reviewers / tf4-leads | `tf4-github-actions-terraform-apply` | Permissions boundary plus explicit deny blocks protected delete and guardrail tamper. |
| Create RDS/ElastiCache recovery point or write S3 archive object | CDO08 Reliability | PM or Tech Lead | `tf4-rel24-backup-admin` | Can create/write recovery assets, cannot delete protected sources. |
| Restore from RDS/ElastiCache snapshot or read archive for replay | Incident commander / CDO08 Reliability | PM or Tech Lead | `tf4-rel24-restore-operator` | Can restore/create replacement resources, cannot delete protected sources. |
| Delete protected backup/archive asset | Incident commander | PM plus Tech Lead | `tf4-rel24-backup-delete-break-glass` | Requires tagged assume-role session with `Rel24DeletionApproved=true` and `ChangeId`. |
| Audit deletion attempt or approval trail | CDO07 Audit | Audit lead | CloudTrail / CloudWatch Logs | Management events and selected S3 data events capture actor/action/time/result. |

## Implemented Controls

- Bootstrap role `tf4-github-actions-terraform-apply` keeps existing broad managed policies for compatibility, but is constrained by `tf4-rel24-protected-recovery-assets-guardrail`.
- The same CI role also has `tf4-rel24-ci-protected-recovery-assets-deny`, so delete attempts are denied even if a future broad allow is attached.
- Guardrail tamper is denied for the CI role: it cannot remove its own permissions boundary, mutate the REL-24 guardrail policies, or detach the REL-24 explicit deny policy.
- `tf4-rel24-backup-admin` can create RDS and ElastiCache snapshots, start AWS Backup jobs, and write archive objects, but has an explicit deny for protected delete operations.
- `tf4-rel24-restore-operator` can restore replacement resources and read archive objects, but has the same explicit deny for protected delete operations.
- `tf4-rel24-backup-delete-break-glass` can delete protected assets only in a tagged session that carries `Rel24DeletionApproved=true`.
- The PostgreSQL migration backup bucket has a bucket policy that denies normal operator delete and retention-control changes under the protected prefix; Terraform CI is denied by its identity guardrail while still able to maintain reviewed IaC policy.
- CloudTrail S3 data event selectors include the PostgreSQL migration backup prefix and expected MSK orders archive prefix.

## Approval Contract

All human assume-role sessions for REL-24 operational roles must include:

```bash
--tags Key=Rel24Approval,Value=approved Key=ChangeId,Value=<ticket-or-incident-id>
```

Break-glass deletion sessions must include:

```bash
--tags Key=Rel24DeletionApproved,Value=true Key=ChangeId,Value=<ticket-or-incident-id>
```

The approver records the change/incident ID in the ticket before credentials are issued. The executor records the resulting CloudTrail event IDs in the evidence file.
