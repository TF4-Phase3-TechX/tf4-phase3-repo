# CDO08-REL-23 Subtask 2 - Xoa instance PITR tam + SG tam sau khi dung xong.
# Xem plan §5.2.
#
# Vi du:
#   .\02-cleanup-pitr-isolated.ps1 -TargetId rel23-accounting-pitr-20260724t120000z -TmpSgId sg-0123abcd

param(
    [Parameter(Mandatory)][string]$TargetId,
    [Parameter(Mandatory)][string]$TmpSgId,
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

Write-Host "[INFO] Deleting isolated instance $TargetId..."
aws rds delete-db-instance --region $Region --db-instance-identifier $TargetId `
    --skip-final-snapshot --delete-automated-backups | Out-Null
Assert-LastExitCode 'aws rds delete-db-instance'

aws rds wait db-instance-deleted --region $Region --db-instance-identifier $TargetId
Assert-LastExitCode 'aws rds wait db-instance-deleted'
Write-Host "[OK] Instance $TargetId deleted."

Write-Host "[INFO] Deleting temp SG $TmpSgId..."
aws ec2 delete-security-group --region $Region --group-id $TmpSgId
Assert-LastExitCode 'aws ec2 delete-security-group'
Write-Host "[OK] SG $TmpSgId deleted."

Write-Host '[OK] Cleanup Subtask 2 hoan tat - khong con hạ tang nao con lai tu buoc PITR isolated.'
