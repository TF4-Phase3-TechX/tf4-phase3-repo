# CDO08-REL-23 Subtask 4 - R.6 Cleanup: xoa schema accounting_old sau khi da xac nhan on dinh.
# KHONG chay ngay sau 08-reopen-traffic.ps1 - accounting_old la rollback checkpoint cuoi cung,
# chi xoa sau khi theo doi mot khoang thoi gian on dinh (xem plan §7.2 R.6).
#
# Vi du:
#   .\09-cleanup-old-schema.ps1 -Confirm

param(
    [string]$Namespace = 'techx-tf4',
    [string]$OpsNamespace = 'rel23-ops',
    [string]$Region = 'us-east-1',
    [string]$ProductionInstanceId = 'techx-tf4-postgresql',
    [switch]$Confirm
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if (-not $Confirm) {
    throw 'An toan: phai truyen -Confirm de xac nhan da theo doi on dinh du lau va sẵn sang xoa vinh vien accounting_old.'
}

$runId = New-RunId
$podName = "pg-cleanup-old-$runId"
$creds = Get-RdsMasterCreds -DbInstanceIdentifier $ProductionInstanceId -Region $Region
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase 'otel'

try {
    $hasOld = Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName `
        -Sql "SELECT count(*) FROM pg_namespace WHERE nspname='accounting_old';"
    if ([int]$hasOld -eq 0) {
        Write-Host '[INFO] Khong con schema accounting_old - khong co gi de don dep.'
        return
    }

    Write-Host '[INFO] R.6 - Xoa schema accounting_old...'
    Invoke-PgSql -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'DROP SCHEMA accounting_old CASCADE;'
    Write-Host '[OK] R.6 hoan tat - da don dep rollback checkpoint accounting_old.'
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}
