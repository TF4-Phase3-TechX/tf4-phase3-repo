# CDO08-REL-23 Subtask 4 - R.0 backup-before-import + R.1b Kafka rollback-window offset reset +
# R.2 rename-truoc-khi-import (khong DROP truc tiep). Xem plan §7.2, §7.2.1.
# Chi chay sau khi 05-write-freeze.ps1 xac nhan 0 connection techx_app, va ValidatedDumpPath
# da qua 04-restore-accounting-drill.ps1 + validate PASS.
#
# Vi du:
#   .\06-import-production.ps1 -RestoreTime 2026-07-20T10:00:00Z -ValidatedDumpPath .\accounting-....dump

param(
    [Parameter(Mandatory)][string]$RestoreTime,
    [Parameter(Mandatory)][string]$ValidatedDumpPath,
    [string]$Namespace = 'techx-tf4',
    [string]$OpsNamespace = 'rel23-ops',
    [string]$Region = 'us-east-1',
    [string]$ProductionInstanceId = 'techx-tf4-postgresql',
    [string]$BackupPath,
    [switch]$SkipKafkaOffsetReset
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

if (-not (Test-Path $ValidatedDumpPath)) { throw "ValidatedDumpPath khong ton tai: $ValidatedDumpPath" }

$runId = New-RunId
if (-not $BackupPath) { $BackupPath = ".\accounting-production-backup-$runId.dump" }

$creds = Get-RdsMasterCreds -DbInstanceIdentifier $ProductionInstanceId -Region $Region
$podName = "pg-import-$runId"
$pod = New-PgClientPod -Namespace $OpsNamespace -PodName $podName `
    -PgHost $creds.Host -PgPort $creds.Port -PgUser $creds.User -PgPassword $creds.Password -PgDatabase 'otel'

try {
    # --- R.0: backup-before-import (rollback checkpoint bat buoc) ---
    Write-Host '[INFO] R.0 - Backup schema accounting production truoc khi dung gi...'
    kubectl exec -n $pod.Namespace $pod.PodName -- pg_dump --schema=accounting --format=custom --file=/tmp/prod-backup.dump
    Assert-LastExitCode 'pg_dump (R.0 backup)'

    kubectl cp "$($pod.Namespace)/$($pod.PodName):/tmp/prod-backup.dump" $BackupPath
    Assert-LastExitCode 'kubectl cp (R.0 backup ra local)'
    Write-Host "[OK] R.0 backup luu tai $BackupPath - GIU LAI, day la rollback checkpoint duy nhat truoc R.2."

    # --- R.1b: Kafka rollback-window offset reset (xem plan §7.2.1) ---
    if (-not $SkipKafkaOffsetReset) {
        Write-Host "[INFO] R.1b - Reset offset consumer group 'accounting' ve RestoreTime=$RestoreTime..."
        $kafkaPodName = "kafka-reset-$runId"
        $kafkaPod = New-KafkaClientPod -Namespace $OpsNamespace -PodName $kafkaPodName
        try {
            kubectl exec -n $kafkaPod.Namespace $kafkaPod.PodName -- sh -c `
                '/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server "$KAFKA_ADDR" --command-config /tmp/client.properties --group accounting --topic orders --reset-offsets --to-datetime "$0" --execute' `
                $RestoreTime
            Assert-LastExitCode 'kafka-consumer-groups.sh --reset-offsets'
            Write-Host "[OK] R.1b hoan tat - offset group 'accounting' da reset ve $RestoreTime."
        }
        finally {
            Remove-KafkaClientPod -Namespace $kafkaPod.Namespace -PodName $kafkaPod.PodName
        }
    }
    else {
        Write-Host '[WARN] Bo qua R.1b theo -SkipKafkaOffsetReset - chi dung khi chac chan RestoreTime sat lien voi thoi diem freeze (khong co rollback window dang ke). Xem plan §7.2.1 truoc khi bo qua.'
    }

    # --- R.2: rename-truoc-khi-import, KHONG DROP SCHEMA truc tiep ---
    Write-Host '[INFO] R.2 - Rename accounting -> accounting_old, import ban da validate...'
    kubectl cp $ValidatedDumpPath "$($pod.Namespace)/$($pod.PodName):/tmp/accounting-validated.dump"
    Assert-LastExitCode 'kubectl cp (validated dump vao pod)'

    Invoke-PgSql -Namespace $pod.Namespace -PodName $pod.PodName -Sql 'ALTER SCHEMA accounting RENAME TO accounting_old;'

    kubectl exec -n $pod.Namespace $pod.PodName -- pg_restore --dbname=otel --schema=accounting /tmp/accounting-validated.dump
    Assert-LastExitCode 'pg_restore (R.2 import production)'

    Write-Host '[OK] R.2 hoan tat.'
    Write-Host "[NOTE] Chay tiep .\07-validate-production.ps1 TRUOC khi reopen traffic (08). Rollback checkpoint: schema accounting_old + $BackupPath."
}
finally {
    Remove-PgClientPod -Namespace $pod.Namespace -PodName $pod.PodName
}
