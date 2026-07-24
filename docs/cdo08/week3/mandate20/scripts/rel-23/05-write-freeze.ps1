# CDO08-REL-23 Subtask 4 - R.1 Write freeze: scale accounting ve 0 + gate xac nhan 0 connection ghi.
# Xem plan §7.2 R.1. accounting la mot ROLE (techx_app), khong phai 1 process - scale Deployment
# chi chan dung con consumer nay; gate pg_stat_activity de phat hien job/cron/psql thu cong khac.
#
# Vi du:
#   .\05-write-freeze.ps1

param(
    [string]$Namespace = 'techx-tf4',
    [string]$OpsNamespace = 'rel23-ops',
    [string]$Region = 'us-east-1',
    [string]$ProductionInstanceId = 'techx-tf4-postgresql',
    [int]$TimeoutSeconds = 120,
    [int]$PollSeconds = 5
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

Write-Host "[INFO] t_R1_freeze_start=$(Get-UtcNowIso)"
Write-Host "[INFO] R.1 - Scaling deployment/accounting to 0 in $Namespace..."
kubectl scale deployment/accounting -n $Namespace --replicas=0
Assert-LastExitCode 'kubectl scale deployment/accounting --replicas=0'
kubectl rollout status deployment/accounting -n $Namespace --timeout=60s
Assert-LastExitCode 'kubectl rollout status (scale down)'

$runId = New-RunId
$podName = "pg-freeze-gate-$runId"
$creds = Get-RdsMasterCreds -DbInstanceIdentifier $ProductionInstanceId -Region $Region
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase 'otel'

try {
    Write-Host '[INFO] Gate: cho 0 active connection cua role techx_app...'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $count = -1
    do {
        $count = [int](Invoke-PgSqlScalar -Namespace $pod.Namespace -PodName $pod.PodName `
            -Sql "SELECT count(*) FROM pg_stat_activity WHERE usename='techx_app';")
        if ($count -eq 0) { break }
        Write-Host "[INFO] Con $count connection techx_app, doi $PollSeconds giay..."
        Start-Sleep -Seconds $PollSeconds
    } while ((Get-Date) -lt $deadline)

    if ($count -ne 0) {
        throw "Timeout sau $TimeoutSeconds giay: van con $count connection techx_app - kiem tra job/cron/psql thu cong khac dang dung role nay truoc khi tiep tuc sang R.2."
    }
    Write-Host '[OK] R.1 hoan tat - 0 active connection techx_app. Write-freeze confirmed.'
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}
