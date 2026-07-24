# CDO08-REL-23 Subtask 3 - Export schema accounting tu instance PITR tam.
# Xem plan §6.2. Dung Get-RdsMasterCreds (khong dung techx_app) vi can quyen doc day du + dump ACL dung.
#
# Vi du:
#   .\03-export-accounting.ps1 -IsolatedInstanceId rel23-accounting-pitr-20260724t120000z

param(
    [Parameter(Mandatory)][string]$IsolatedInstanceId,
    [string]$Region = 'us-east-1',
    [string]$OpsNamespace = 'rel23-ops',
    [string]$DumpPath
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

$runId = New-RunId
if (-not $DumpPath) { $DumpPath = ".\accounting-$runId.dump" }
$podName = "pg-export-$runId"

$creds = Get-RdsMasterCreds -DbInstanceIdentifier $IsolatedInstanceId -Region $Region
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase 'otel'

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
