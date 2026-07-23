# CDO08-REL-25 - Isolated Restore Environment and Guardrails

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20
**Subtask:** Design isolated restore environment and safety guardrails
**Owner:** CDO08 Reliability
**Updated:** 2026-07-23

## Mục tiêu

Ngăn restore nhầm hoặc ghi đè production khi chạy Mandate 20 restore drill. Restore phải đi vào môi trường tách biệt, không dùng production identifier, production endpoint, production DNS, hoặc production app access path.

## Naming Contract

Restore target phải có prefix/suffix rõ:

```text
RESTORE_DRILL_ID=rel25-YYYYMMDD
RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-rel25-YYYYMMDD-postgresql-restore
RESTORE_TARGET_DNS_NAME=rel25-YYYYMMDD-postgresql-restore.internal
```

Không dùng:

```text
techx-tf4-postgresql
techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com
*.prod*
*.production*
```

## Isolation Design

Restore target phải nằm trên private subnet hoặc restore-only subnet group. Security group chỉ mở `tcp/5432` từ validation client, không mở từ production app service account hoặc toàn bộ production runtime.

Access path duy nhất được chấp nhận:

```text
validation-client pod -> restore-only security group -> restore RDS target
```

Validation client phải có label:

```text
restore-validation-client=true
```

## Temporary Secrets

Secret phục vụ drill phải là secret tạm, ví dụ:

```text
rds-admin-temp-rel25-YYYYMMDD
rds-app-temp-rel25-YYYYMMDD
```

Rules:

- không dùng production app secret
- không commit plaintext credential
- secret chỉ cấp quyền restore/validation
- xóa secret sau khi evidence hoàn tất

## No-production-DNS Guardrail

Restore target không được gắn production DNS. Preflight chặn alias chứa `prod` hoặc `production`, và chặn endpoint/identifier production đã biết.

Preflight script:

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-target-preflight.sh
```

Script fail nếu:

- `RESTORE_TARGET_IDENTIFIER` trùng `techx-tf4-postgresql`
- `RESTORE_TARGET_ENDPOINT` trùng production RDS endpoint được resolve trực tiếp từ AWS
- identifier không bắt đầu bằng `techx-tf4-drill-${RESTORE_DRILL_ID}`
- identifier thiếu marker `drill` hoặc `restore`
- DNS alias chứa `prod` hoặc `production`
- AWS RDS resolved endpoint không khớp biến input
- RDS target `PubliclyAccessible=True`
- không có validation client pod theo selector `restore-validation-client=true`

## Cost, TTL, Cleanup Tags

Mọi resource drill phải có tag/label:

```text
Owner=CDO08
Team=CDO08
Project=TF4
Environment=RestoreDrill
Mandate=20
Task=CDO08-REL-25
RestoreDrillId=rel25-YYYYMMDD
TTLHours=24
CleanupAfter=YYYY-MM-DDTHH:mm:ssZ
CostCenter=ReliabilityDrill
Production=false
```

Cleanup checklist:

- delete validation pods/jobs
- delete Kubernetes temporary secrets
- delete restore-only RDS target sau khi export evidence
- delete restore-only security group/subnet group nếu không còn reference
- verify không còn Route53/CNAME trỏ vào restore target

## Acceptance Criteria Mapping

| Acceptance Criteria | Evidence/Guardrail |
| --- | --- |
| Restore target không dùng production identifier/endpoint | Preflight chặn production identifier và endpoint. |
| Chỉ validation client được kết nối | Thiết kế SG chỉ mở từ validation client; preflight yêu cầu pod label `restore-validation-client=true`. |
| Có preflight check fail nếu target trùng production | `rel25-restore-target-preflight.sh` fail-fast khi identifier/endpoint/resolved endpoint trùng production. |

## Example Command

```bash
RESTORE_DRILL_ID=rel25-20260723 \
RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-rel25-20260723-postgresql-restore \
RESTORE_TARGET_ENDPOINT=techx-tf4-drill-rel25-20260723-postgresql-restore.xxxxxx.us-east-1.rds.amazonaws.com \
RESTORE_TARGET_DNS_NAME=rel25-20260723-postgresql-restore.internal \
VALIDATION_CLIENT_SELECTOR=restore-validation-client=true \
bash ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-target-preflight.sh
```

## Verification

The preflight script passed ShellCheck and seven isolated guardrail checks on
2026-07-23. The checks covered missing input, production identifier,
production endpoint, production DNS, public restore target, missing validation
client, and a valid isolated target. The checks used local AWS and kubectl
mocks and did not connect to production.

```bash
docker run --rm -v "$PWD:/repo:ro" koalaman/shellcheck:stable \
  /repo/docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-target-preflight.sh
```

### Commands to run before a drill

Prerequisites:

- Bash, AWS CLI v2, and kubectl are installed.
- The operator has an AWS SSO profile with permission to describe both RDS
  instances.
- The operator has read access to the TF4 EKS cluster.
- The isolated restore target and validation-client pod already exist.

Each operator must use their own SSO profile. A read-only profile with
`rds:DescribeDBInstances` is sufficient.

Authenticate and verify that AWS and Kubernetes point to the intended TF4
account and cluster:

```powershell
$env:AWS_PROFILE="<your-sso-profile>"
aws sso login --profile $env:AWS_PROFILE
aws sts get-caller-identity --profile $env:AWS_PROFILE
kubectl config current-context
kubectl -n techx-tf4 get pod -l restore-validation-client=true
```

Expected AWS account and Kubernetes context:

```text
AWS account: 511825856493
Kubernetes context: arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster
```

Run the preflight from Bash after the isolated restore target and validation
client exist:

```bash
export AWS_PROFILE=<your-sso-profile>
export AWS_REGION=us-east-1
export RESTORE_DRILL_ID=rel25-YYYYMMDD
export RESTORE_TARGET_IDENTIFIER=techx-tf4-drill-rel25-YYYYMMDD-postgresql-restore
export RESTORE_TARGET_ENDPOINT=<endpoint-cua-restore-target>
export RESTORE_TARGET_DNS_NAME=rel25-YYYYMMDD-postgresql-restore.internal
export NAMESPACE=techx-tf4
export VALIDATION_CLIENT_SELECTOR=restore-validation-client=true

bash ./docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-target-preflight.sh
```

Do not replace `RESTORE_TARGET_IDENTIFIER` or `RESTORE_TARGET_ENDPOINT` with
production values just to make the command pass. The script must stop with
`[ERROR]` when either value matches production.

The script intentionally has no default AWS profile. Another operator can run
the same script by setting `AWS_PROFILE` to their own authenticated profile:

```bash
export AWS_PROFILE=<your-sso-profile>
aws sso login --profile "$AWS_PROFILE"
```
