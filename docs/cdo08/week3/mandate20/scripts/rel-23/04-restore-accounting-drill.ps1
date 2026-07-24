# CDO08-REL-23 Subtask 3 - Restore dump accounting vao database drill (otel_drill), tren chinh instance tam.
# Xem plan §6.3. Idempotent: DROP DATABASE IF EXISTS + CREATE DATABASE moi lan chay.
# KHONG dung --role=techx_app (master moi tu sinh khong phai thanh vien role do - se fail
# "permission denied to set role"). --no-owner --no-privileges la du cho muc dich validate.
#
# Vi du:
#   .\04-restore-accounting-drill.ps1 -IsolatedInstanceId rel23-accounting-pitr-... -DumpPath .\accounting-....dump

param(
    [Parameter(Mandatory)][string]$IsolatedInstanceId,
    [Parameter(Mandatory)][string]$DumpPath,
    [string]$Region = 'us-east-1',
    [string]$OpsNamespace = 'rel23-ops'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if (-not (Test-Path $DumpPath)) { throw "DumpPath khong ton tai: $DumpPath" }

$runId = New-RunId
$podName = "pg-drill-$runId"

$creds = Get-RdsMasterCreds -DbInstanceIdentifier $IsolatedInstanceId -Region $Region
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase 'postgres'

try {
    kubectl cp $DumpPath "$($pod.Namespace)/$($pod.PodName):/tmp/accounting.dump"
    Assert-LastExitCode 'kubectl cp (dump vao pod)'

    Invoke-PgSqlFile -Namespace $pod.Namespace -PodName $pod.PodName -SqlScript @'
DROP DATABASE IF EXISTS otel_drill;
CREATE DATABASE otel_drill;
'@

    kubectl exec -n $pod.Namespace $pod.PodName -- pg_restore --dbname=otel_drill --no-owner --no-privileges --clean --if-exists /tmp/accounting.dump
    Assert-LastExitCode 'pg_restore (drill)'

    Write-Host '[OK] Restored into otel_drill for validation.'
    Write-Host '[NOTE] Chay tiep 07-validate-production.ps1 -Database otel_drill de doi chieu voi checklist §4.4/§7.1 truoc khi cutover production.'
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}
