# CDO08-REL-23 Subtask 4 - R.4 Rollback: dung khi 07-validate-production.ps1 FAIL sau R.2 va da
# thu nhanh remediation §7.2.1 nhung van khong dat. Xoa ban import loi, doi ten accounting_old
# tro lai thanh accounting. accounting_old CHUA bao gio bi dong tu R.2 nen luon co duong lui.
#
# Vi du:
#   .\rollback-01-restore-old-schema.ps1

param(
    [string]$Namespace = 'techx-tf4',
    [string]$OpsNamespace = 'rel23-ops',
    [string]$Region = 'us-east-1',
    [string]$ProductionInstanceId = 'techx-tf4-postgresql'
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

$runId = New-RunId
$podName = "pg-rollback-$runId"
$creds = Get-RdsMasterCreds -DbInstanceIdentifier $ProductionInstanceId -Region $Region
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase 'otel'

try {
    $hasOld = Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName `
        -Sql "SELECT count(*) FROM pg_namespace WHERE nspname='accounting_old';"
    if ([int]$hasOld -eq 0) {
        throw 'Khong tim thay schema accounting_old - khong co gi de rollback (da chay 09-cleanup-old-schema.ps1 truoc do?).'
    }

    Write-Host '[WARN] R.4 - Rollback: xoa ban import loi, khoi phuc accounting_old...'
    Invoke-PgSqlFile -Namespace $pod.Namespace -PodName $pod.PodName -SqlScript @'
DROP SCHEMA accounting CASCADE;
ALTER SCHEMA accounting_old RENAME TO accounting;
'@
    Write-Host '[OK] Rollback hoan tat - schema accounting da khoi phuc ve dung trang thai truoc R.2.'
    Write-Host '[NOTE] Neu da chay R.1b (reset offset Kafka), can danh gia lai: offset da bi keo lui nhung DB da rollback ve truoc do - kiem tra tinh nhat quan Kafka/DB truoc khi mo lai traffic.'
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}
