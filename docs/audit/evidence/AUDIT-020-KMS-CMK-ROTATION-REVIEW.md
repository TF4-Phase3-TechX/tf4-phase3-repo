# AUDIT-020 - KMS CMK Key Policy and Rotation Review

**Owner:** CDO07 Audit
**Date:** 2026-07-15
**Scope:** Review the KMS customer managed key (CMK) used by CloudTrail.
**Target Trail:** `tf4-general-cloudtrail`
**Region:** `us-east-1`

---

## 1. Objective

Validate that CloudTrail audit data is encrypted with a dedicated KMS CMK, that automatic key rotation is enabled, and that `kms:Decrypt` access is not broadly granted in the CMK key policy.

This document records the repository-side review and the AWS CLI verification steps. Screenshots and raw command output are uploaded separately to Jira as task evidence.

---

## 2. Definition of Done

- [x] Collect the KMS CMK ARN used by CloudTrail.
- [ ] Review the KMS key policy for broad `kms:Decrypt` permissions.
- [ ] Confirm KMS key rotation status with `aws kms get-key-rotation-status`.
- [ ] Attach evidence in Jira using AWS CLI output or screenshots.

Current repository status: CMK ARN and IaC references are documented. Runtime evidence is expected to be attached in Jira.

---

## 3. CloudTrail CMK ARN

CloudTrail is configured to use the following KMS CMK:

```text
arn:aws:kms:us-east-1:511825856493:key/4f20f498-949c-4970-9a79-7f34f1497d98
```

Verification command:

```powershell
aws cloudtrail describe-trails `
  --trail-name-list tf4-general-cloudtrail `
  --region us-east-1 `
  --query "trailList[0].KmsKeyId" `
  --output text
```

Expected result:

```text
arn:aws:kms:us-east-1:511825856493:key/4f20f498-949c-4970-9a79-7f34f1497d98
```

---

## 4. Key Rotation Verification

Verification command:

```powershell
aws kms get-key-rotation-status `
  --key-id "arn:aws:kms:us-east-1:511825856493:key/4f20f498-949c-4970-9a79-7f34f1497d98" `
  --region us-east-1
```

Pass condition:

```json
{
  "KeyRotationEnabled": true
}
```

Review result: **PASS** when Jira evidence shows `KeyRotationEnabled = true`.

---

## 5. Key Policy Review

Verification command:

```powershell
aws kms get-key-policy `
  --key-id "arn:aws:kms:us-east-1:511825856493:key/4f20f498-949c-4970-9a79-7f34f1497d98" `
  --policy-name default `
  --region us-east-1 `
  --output json
```

Review checklist:

- CloudTrail service principal is present: `cloudtrail.amazonaws.com`.
- CloudTrail permissions are limited to log encryption use cases, such as `kms:GenerateDataKey*` and `kms:DescribeKey`.
- No unrelated IAM principal is granted broad `kms:Decrypt`.
- No unconditional `Principal = "*"` statement grants `kms:Decrypt`.
- If CloudWatch Logs has decrypt permissions, access is scoped with encryption context conditions such as `kms:EncryptionContext:aws:logs:arn`.

Review result: **PASS** when the Jira key policy evidence does not show broad or unrelated `kms:Decrypt` access.

---

## 6. Terraform Reference

Repository references:

- `infra/terraform/cloudtrail.tf`
- `infra/terraform/outputs.tf`

Relevant IaC controls:

```hcl
resource "aws_kms_key" "cloudtrail" {
  description             = "TF4 CloudTrail dedicated KMS key - log encryption & tamper-evident"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false
}
```

```hcl
resource "aws_cloudtrail" "main" {
  name       = "tf4-general-cloudtrail"
  kms_key_id = aws_kms_key.cloudtrail.arn
}
```

```hcl
output "cloudtrail_kms_key_arn" {
  description = "ARN of the KMS CMK used to encrypt CloudTrail logs"
  value       = aws_kms_key.cloudtrail.arn
}
```

---

## 7. Observation

Repository IAM documentation contains a proposed CDO07 audit policy with `kms:Decrypt` on all KMS keys in `us-east-1` for account `511825856493`:

```text
arn:aws:kms:us-east-1:511825856493:key/*
```

This document reviews the CloudTrail CMK key policy itself. If the proposed audit IAM policy is active in AWS, it should be separately confirmed and scoped down where possible to avoid over-privileged decrypt access.

Reference:

- `docs/iam/group/cdo07/TF4-AuditReadOnlyAndAnalyze.md`

---

## 8. Audit Conclusion

Task 20 can be approved from the CDO07 audit perspective when Jira contains the following evidence:

- CloudTrail `KmsKeyId` output showing the CMK ARN above.
- KMS rotation output showing `KeyRotationEnabled = true`.
- KMS key policy screenshot or AWS CLI output showing no broad `kms:Decrypt` grant.
- Terraform screenshot or PR reference showing `enable_key_rotation = true` and CloudTrail `kms_key_id`.

Final status: **Approved after Jira evidence upload**.
