# CDO08-REL-23 Subtask 3 - Export schema accounting tu instance PITR tam.
# Xem plan §6.2. Dung -PitrInfoPath (file JSON do 01-restore-pitr-isolated.ps1 sinh ra, chua
# Endpoint + MasterPassword biet truoc) thay vi doc MasterUserSecret qua Secrets Manager - IAM role
# van hanh khong duoc phep doc secret do (xem plan §9).
#
# Vi du:
#   .\03-export-accounting.ps1 -PitrInfoPath .\rel23-pitr-20260724t120000z.json

param(
    [Parameter(Mandatory)][string]$PitrInfoPath,
    [string]$OpsNamespace = 'rel23-ops',
    [string]$DumpPath
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if (-not (Test-Path $PitrInfoPath)) { throw "PitrInfoPath khong ton tai: $PitrInfoPath" }
$pitrInfo = Get-Content $PitrInfoPath -Raw | ConvertFrom-Json

$runId = New-RunId
if (-not $DumpPath) { $DumpPath = ".\accounting-$runId.dump" }
$podName = "pg-export-$runId"

$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $pitrInfo.Endpoint -PgUser $pitrInfo.MasterUser -PgPassword $pitrInfo.MasterPassword -PgDatabase 'otel'

try {
    Write-Host "[INFO] t_export_start=$(Get-UtcNowIso)"

    kubectl exec -n $pod.Namespace $pod.PodName -- pg_dump --schema=accounting --format=custom --file=/tmp/accounting.dump
    Assert-LastExitCode 'pg_dump --schema=accounting'

    kubectl cp "$($pod.Namespace)/$($pod.PodName):/tmp/accounting.dump" $DumpPath
    Assert-LastExitCode 'kubectl cp (export dump ra local)'

    $size = (Get-Item $DumpPath).Length
    Write-Host "[OK] Dump written: $DumpPath ($size bytes)"
    Write-Host "[INFO] t_export_done=$(Get-UtcNowIso)"
    Write-Host "[NOTE] --schema=accounting tu gioi han pham vi - khong the lan catalog/reviews vao dump nay."
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}

Write-Host "[INFO] Dump path (dung cho 04-restore-accounting-drill.ps1 va sau khi validate, cho 06-import-production.ps1): $DumpPath"

