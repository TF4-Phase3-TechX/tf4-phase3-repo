# CDO08-REL-23 Subtask 4 - R.5 Reopen traffic: chi chay sau khi 07-validate-production.ps1 PASS.
# Scale accounting ve 1, theo doi consumer lag group 'accounting' ve 0 (bao gom ca phan replay
# rollback-window neu da chay R.1b o buoc 06). Xem plan §7.2, §7.2.1.
#
# Vi du:
#   .\08-reopen-traffic.ps1

param(
    [string]$Namespace = 'techx-tf4',
    [string]$OpsNamespace = 'rel23-ops',
    [int]$TimeoutSeconds = 3600,
    [int]$PollSeconds = 15
)

$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\00-common.ps1"

Write-Host "[INFO] R.5 - Scaling deployment/accounting to 1 in $Namespace..."
kubectl scale deployment/accounting -n $Namespace --replicas=1
Assert-LastExitCode 'kubectl scale deployment/accounting --replicas=1'
kubectl rollout status deployment/accounting -n $Namespace --timeout=120s
Assert-LastExitCode 'kubectl rollout status (scale up)'

$runId = New-RunId
$kafkaPodName = "kafka-lag-$runId"
$kafkaPod = New-KafkaClientPod -Namespace $OpsNamespace -PodName $kafkaPodName

try {
    Write-Host "[INFO] Theo doi consumer lag group 'accounting' toi khi ve 0 (timeout ${TimeoutSeconds}s)..."
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        # Phai chay qua "sh -c" de shell trong pod expand $KAFKA_ADDR - goi truc tiep binary khong
        # qua shell se truyen literal chuoi "$KAFKA_ADDR" (khong duoc thay the) lam bootstrap-server sai.
        $describe = kubectl exec -n $kafkaPod.Namespace $kafkaPod.PodName -- sh -c `
            '/opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server "$KAFKA_ADDR" --command-config /tmp/client.properties --describe --group accounting'
        Assert-LastExitCode 'kafka-consumer-groups.sh --describe'
        Write-Host $describe

        # Cot LAG la cot thu 6 (index 5) trong output cua --describe; cong don qua cac partition.
        $totalLag = 0
        $sawNumber = $false
        foreach ($line in ($describe -split "`n")) {
            $cols = ($line.Trim() -split '\s+')
            if ($cols.Length -ge 6 -and $cols[5] -match '^\d+$') {
                $totalLag += [int]$cols[5]
                $sawNumber = $true
            }
        }
        if ($sawNumber -and $totalLag -eq 0) {
            Write-Host '[OK] Consumer lag = 0.'
            break
        }
        Write-Host "[INFO] Lag hien tai (uoc tinh): $totalLag - doi $PollSeconds giay..."
        Start-Sleep -Seconds $PollSeconds
    } while ((Get-Date) -lt $deadline)

    if ((Get-Date) -ge $deadline) {
        throw "Timeout sau $TimeoutSeconds giay: consumer lag chua ve 0 - kiem tra thu cong bang 'kafka-consumer-groups.sh --describe --group accounting' truoc khi coi la reopen thanh cong."
    }

    Write-Host "[INFO] t_R5_traffic_reopened=$(Get-UtcNowIso)"
    Write-Host "[NOTE] Trong luc replay (neu co R.1b), theo doi log pod accounting: so dong 'Order parsing failed' nen xap xi dung so order da co san trong ban restore (do overlap) - neu cao bat thuong thi dung lai dieu tra (xem plan §7.2.1)."
}
finally {
    Remove-KafkaClientPod -Namespace $kafkaPod.Namespace -PodName $kafkaPod.PodName
}

Write-Host '[OK] R.5 hoan tat. Chay tiep 09-cleanup-old-schema.ps1 sau khi da theo doi on dinh mot khoang thoi gian (khong xoa accounting_old ngay).'
