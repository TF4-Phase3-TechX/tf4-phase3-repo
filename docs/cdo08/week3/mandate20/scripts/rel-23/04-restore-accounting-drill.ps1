# CDO08-REL-23 Subtask 3 - Restore dump accounting vao database drill (otel_drill), tren chinh instance tam.
# Xem plan §6.3. Idempotent: DROP DATABASE IF EXISTS + CREATE DATABASE moi lan chay.
# Dung -PitrInfoPath (xem 03-export-accounting.ps1) - ket noi bang master password tu dat o buoc 01,
# khong dung Secrets Manager. --no-owner --no-privileges la du cho muc dich validate (khong can quyen
# thanh vien role nao khac vi da ket noi thang bang postgres).
#
# Vi du:
#   .\04-restore-accounting-drill.ps1 -PitrInfoPath .\rel23-pitr-....json -DumpPath .\accounting-....dump

param(
    [Parameter(Mandatory)][string]$PitrInfoPath,
    [Parameter(Mandatory)][string]$DumpPath,
    [string]$OpsNamespace = 'rel23-ops'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if (-not (Test-Path $DumpPath)) { throw "DumpPath khong ton tai: $DumpPath" }
if (-not (Test-Path $PitrInfoPath)) { throw "PitrInfoPath khong ton tai: $PitrInfoPath" }
$pitrInfo = Get-Content $PitrInfoPath -Raw | ConvertFrom-Json

$runId = New-RunId
$podName = "pg-drill-$runId"

$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $pitrInfo.Endpoint -PgUser $pitrInfo.MasterUser -PgPassword $pitrInfo.MasterPassword -PgDatabase 'postgres'

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

