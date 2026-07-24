# CDO08-REL-23 Subtask 2 - Xoa instance PITR tam + SG tam sau khi dung xong.
# Xem plan §5.2. Doc TargetId/TmpSgId tu file JSON do 01-restore-pitr-isolated.ps1 sinh ra -
# khong can go tay lai 2 gia tri nay.
#
# Vi du:
#   .\02-cleanup-pitr-isolated.ps1 -PitrInfoPath .\rel23-pitr-<run-id>.json

param(
    [string]$PitrInfoPath,
    [string]$TargetId,
    [string]$TmpSgId,
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if ($PitrInfoPath) {
    if (-not (Test-Path $PitrInfoPath)) { throw "PitrInfoPath khong ton tai: $PitrInfoPath" }
    $pitrInfo = Get-Content $PitrInfoPath -Raw | ConvertFrom-Json
    if (-not $TargetId) { $TargetId = $pitrInfo.TargetId }
    if (-not $TmpSgId) { $TmpSgId = $pitrInfo.TmpSgId }
}
if (-not $TargetId -or -not $TmpSgId) {
    throw 'Can truyen -PitrInfoPath, hoac ca -TargetId va -TmpSgId truc tiep.'
}

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

if ($PitrInfoPath) {
    Remove-Item $PitrInfoPath -Force
    Write-Host "[INFO] Da xoa $PitrInfoPath (chua master password cua instance vua xoa)."
}

Write-Host '[OK] Cleanup Subtask 2 hoan tat - khong con hạ tang nao con lai tu buoc PITR isolated.'
