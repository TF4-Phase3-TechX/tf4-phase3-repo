<#
.SYNOPSIS
Shows Kubernetes status, OOM/restart state, and Prometheus memory usage for Grafana, Jaeger, and Accounting.

.EXAMPLE
.\scripts\observability-memory-report.ps1

.EXAMPLE
.\scripts\observability-memory-report.ps1 -Namespace techx-observability -PeakHours 48
#>
[CmdletBinding()]
param(
    [string]$Namespace = "techx-observability",
    [ValidateRange(1, 168)]
    [int]$PeakHours = 24
)

$ErrorActionPreference = "Stop"

function Invoke-Kubectl {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $output = & kubectl @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        if ($AllowFailure) {
            return $null
        }

        throw "kubectl $($Arguments -join ' ') failed:`n$($output -join "`n")"
    }

    return $output
}

function Get-WorkloadPod {
    param(
        [Parameter(Mandatory)][string]$Name,
        [string]$WorkloadNamespace = $Namespace
    )

    $json = Invoke-Kubectl -Arguments @(
        "get", "pods", "-n", $WorkloadNamespace,
        "-l", "app.kubernetes.io/name=$Name",
        "--field-selector=status.phase=Running",
        "-o", "json"
    )
    $items = @(($json | ConvertFrom-Json).items)
    if ($items.Count -eq 0) {
        return $null
    }

    return $items |
        Sort-Object { [datetimeoffset]$_.metadata.creationTimestamp } -Descending |
        Select-Object -First 1
}

function Invoke-PromQuery {
    param([Parameter(Mandatory)][string]$Query)

    $encodedQuery = [uri]::EscapeDataString(($Query -replace "\s+", " ").Trim())
    $url = "http://localhost:9090/api/v1/query?query=$encodedQuery"
    $response = Invoke-Kubectl -AllowFailure -Arguments @(
        "exec", "-n", $Namespace, $script:PrometheusPod,
        "-c", $script:PrometheusContainer,
        "--", "wget", "-qO-", $url
    )
    if (-not $response) {
        return @()
    }

    try {
        $payload = $response | ConvertFrom-Json
        if ($payload.status -ne "success") {
            return @()
        }
        return @($payload.data.result)
    }
    catch {
        return @()
    }
}

function Get-PromValue {
    param([Parameter(Mandatory)][string]$Query)

    $result = @(Invoke-PromQuery -Query $Query)
    if ($result.Count -eq 0 -or -not $result[0].value) {
        return $null
    }

    return [double]$result[0].value[1]
}

function Convert-ToBytes {
    param($Quantity)

    if ($null -eq $Quantity -or [string]::IsNullOrWhiteSpace([string]$Quantity)) {
        return $null
    }

    $text = ([string]$Quantity).Trim()
    if ($text -notmatch '^([0-9]+(?:\.[0-9]+)?)([EPTGMK]i|[EPTGMK]|m)?$') {
        return $null
    }

    $value = [double]$Matches[1]
    $suffix = $Matches[2]
    $multiplier = switch -CaseSensitive ($suffix) {
        ""   { 1.0 }
        "m"  { 0.001 }
        "K"  { 1e3 }
        "M"  { 1e6 }
        "G"  { 1e9 }
        "T"  { 1e12 }
        "P"  { 1e15 }
        "E"  { 1e18 }
        "Ki" { 1KB }
        "Mi" { 1MB }
        "Gi" { 1GB }
        "Ti" { 1TB }
        "Pi" { [math]::Pow(1024, 5) }
        "Ei" { [math]::Pow(1024, 6) }
    }

    return $value * $multiplier
}

function Format-Memory {
    param($Bytes)

    if ($null -eq $Bytes) {
        return "N/A"
    }

    if ([double]$Bytes -ge 1GB) {
        return "{0:N3} GiB" -f ([double]$Bytes / 1GB)
    }

    return "{0:N2} MiB" -f ([double]$Bytes / 1MB)
}

function Format-Percent {
    param($Value)

    if ($null -eq $Value) {
        return "N/A"
    }

    return "{0:N1}%" -f [double]$Value
}

function Get-MemoryPercent {
    param($Bytes, $LimitBytes)

    if ($null -eq $Bytes -or $null -eq $LimitBytes -or [double]$LimitBytes -le 0) {
        return $null
    }

    return 100 * [double]$Bytes / [double]$LimitBytes
}

function Get-ContainerState {
    param($Status)

    if ($Status.state.running) {
        return "Running"
    }
    if ($Status.state.waiting) {
        return "Waiting: $($Status.state.waiting.reason)"
    }
    if ($Status.state.terminated) {
        return "Terminated: $($Status.state.terminated.reason)"
    }

    return "Unknown"
}

function Show-WorkloadReport {
    param(
        [Parameter(Mandatory)][string]$DisplayName,
        [Parameter(Mandatory)][string]$LabelName,
        [Parameter(Mandatory)][string]$MainContainer,
        [string]$WorkloadNamespace = $Namespace
    )

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host " $($DisplayName.ToUpperInvariant()) MEMORY REPORT" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan

    $pod = Get-WorkloadPod -Name $LabelName -WorkloadNamespace $WorkloadNamespace
    if (-not $pod) {
        Write-Host "No running $DisplayName pod found in namespace $WorkloadNamespace." -ForegroundColor Red
        return
    }

    $podName = $pod.metadata.name
    $statuses = @($pod.status.containerStatuses)
    $readyCount = @($statuses | Where-Object ready).Count
    $mainSpec = @($pod.spec.containers | Where-Object name -eq $MainContainer)[0]
    $mainStatus = @($statuses | Where-Object name -eq $MainContainer)[0]

    if (-not $mainSpec -or -not $mainStatus) {
        Write-Host "Main container '$MainContainer' was not found in pod $podName." -ForegroundColor Red
        return
    }

    $limitText = $mainSpec.resources.limits.memory
    $limitBytes = Convert-ToBytes $limitText

    Write-Host "Pod        : $podName"
    Write-Host "Namespace  : $WorkloadNamespace"
    Write-Host "Node       : $($pod.spec.nodeName)"
    Write-Host "Captured   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
    Write-Host ""

    Write-Host "1. POD STATUS" -ForegroundColor Yellow
    [pscustomobject]@{
        Pod       = $podName
        Phase     = $pod.status.phase
        Ready     = "$readyCount/$($statuses.Count)"
        StartedAt = ([datetimeoffset]$pod.status.startTime).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss zzz")
        QoS       = $pod.status.qosClass
    } | Format-Table -AutoSize

    Write-Host "2. CONTAINER RESOURCES AND RESTARTS" -ForegroundColor Yellow
    $pod.spec.containers | ForEach-Object {
        $spec = $_
        $status = @($statuses | Where-Object name -eq $spec.name)[0]
        $lastReason = if ($status.lastState.terminated.reason) {
            $status.lastState.terminated.reason
        }
        else {
            "-"
        }

        [pscustomobject]@{
            Container  = $spec.name
            State      = Get-ContainerState $status
            Ready      = $status.ready
            Restarts   = $status.restartCount
            LastReason = $lastReason
            Request    = if ($spec.resources.requests.memory) { $spec.resources.requests.memory } else { "-" }
            Limit      = if ($spec.resources.limits.memory) { $spec.resources.limits.memory } else { "-" }
        }
    } | Format-Table -AutoSize

    $selector = "namespace=`"$WorkloadNamespace`",pod=`"$podName`""
    $mainSelector = "$selector,container=`"$MainContainer`""
    # A restarted container produces a new cAdvisor series with a different container ID.
    # Aggregate those series before calculating peaks so restarts are not double-counted.
    $mainCurrent = Get-PromValue "max(container_memory_working_set_bytes{$mainSelector})"
    $mainPeak1h = Get-PromValue "max(max_over_time(container_memory_working_set_bytes{$mainSelector}[1h]))"
    $mainPeakPeriod = Get-PromValue "max(max_over_time(container_memory_working_set_bytes{$mainSelector}[$($PeakHours)h]))"
    $podCurrent = Get-PromValue "sum(max by (container) (container_memory_working_set_bytes{$selector,container!=`"`"}))"
    $podPeakPeriod = Get-PromValue "max_over_time((sum(max by (container) (container_memory_working_set_bytes{$selector,container!=`"`"})))[$($PeakHours)h:15s])"

    Write-Host "3. MEMORY SUMMARY" -ForegroundColor Yellow
    @(
        [pscustomobject]@{
            Scope       = "$DisplayName main container"
            Measurement = "Current"
            Memory      = Format-Memory $mainCurrent
            Limit       = if ($limitText) { $limitText } else { "N/A" }
            LimitUsage  = Format-Percent (Get-MemoryPercent $mainCurrent $limitBytes)
        }
        [pscustomobject]@{
            Scope       = "$DisplayName main container"
            Measurement = "Peak last 1h"
            Memory      = Format-Memory $mainPeak1h
            Limit       = if ($limitText) { $limitText } else { "N/A" }
            LimitUsage  = Format-Percent (Get-MemoryPercent $mainPeak1h $limitBytes)
        }
        [pscustomobject]@{
            Scope       = "$DisplayName main container"
            Measurement = "Peak last $($PeakHours)h"
            Memory      = Format-Memory $mainPeakPeriod
            Limit       = if ($limitText) { $limitText } else { "N/A" }
            LimitUsage  = Format-Percent (Get-MemoryPercent $mainPeakPeriod $limitBytes)
        }
        [pscustomobject]@{
            Scope       = "Whole $DisplayName pod"
            Measurement = "Current"
            Memory      = Format-Memory $podCurrent
            Limit       = "Per-container"
            LimitUsage  = "N/A"
        }
        [pscustomobject]@{
            Scope       = "Whole $DisplayName pod"
            Measurement = "Peak last $($PeakHours)h"
            Memory      = Format-Memory $podPeakPeriod
            Limit       = "Per-container"
            LimitUsage  = "N/A"
        }
    ) | Format-Table -AutoSize

    Write-Host "4. PER-CONTAINER PEAK - LAST $($PeakHours) HOURS" -ForegroundColor Yellow
    $perContainer = @(Invoke-PromQuery "max by (container) (max_over_time(container_memory_working_set_bytes{$selector,container!=`"`"}[$($PeakHours)h]))")
    if ($perContainer.Count -eq 0) {
        Write-Host "No per-container memory series returned by Prometheus." -ForegroundColor DarkYellow
    }
    else {
        $perContainer | ForEach-Object {
            $bytes = [double]$_.value[1]
            $containerSpec = @($pod.spec.containers | Where-Object name -eq $_.metric.container)[0]
            $containerLimitText = $containerSpec.resources.limits.memory
            $containerLimitBytes = Convert-ToBytes $containerLimitText

            [pscustomobject]@{
                Container  = $_.metric.container
                PeakMemory = Format-Memory $bytes
                Limit      = if ($containerLimitText) { $containerLimitText } else { "N/A" }
                LimitUsage = Format-Percent (Get-MemoryPercent $bytes $containerLimitBytes)
            }
        } | Sort-Object { Convert-ToBytes $_.PeakMemory } -Descending | Format-Table -AutoSize
    }

    Write-Host "5. CONCLUSION" -ForegroundColor Yellow
    $lastReason = $mainStatus.lastState.terminated.reason
    $peakPercent = Get-MemoryPercent $mainPeakPeriod $limitBytes

    Write-Host "Current main-container memory : $(Format-Memory $mainCurrent)"
    Write-Host "$($PeakHours)h peak main-container memory: $(Format-Memory $mainPeakPeriod) ($(Format-Percent $peakPercent) of $limitText)"
    Write-Host "Current whole-pod memory      : $(Format-Memory $podCurrent)"
    Write-Host "$($PeakHours)h peak whole-pod memory     : $(Format-Memory $podPeakPeriod)"

    if ($mainStatus.restartCount -eq 0 -and -not $lastReason) {
        Write-Host "Current pod has no main-container restart or termination history." -ForegroundColor Green
    }
    else {
        $reasonText = if ($lastReason) { $lastReason } else { "not retained" }
        $color = if ($lastReason -eq "OOMKilled") { "Red" } else { "Yellow" }
        Write-Host "WARNING: main container restarts=$($mainStatus.restartCount), last reason=$reasonText." -ForegroundColor $color
    }

    if ($null -eq $peakPercent) {
        Write-Host "Memory pressure could not be evaluated because the limit or metric is unavailable." -ForegroundColor DarkYellow
    }
    elseif ($peakPercent -ge 90) {
        Write-Host "CRITICAL: $DisplayName exceeded 90% of its main-container memory limit." -ForegroundColor Red
    }
    elseif ($peakPercent -ge 80) {
        Write-Host "WARNING: $DisplayName exceeded 80% of its main-container memory limit." -ForegroundColor Yellow
    }
    else {
        Write-Host "$DisplayName memory stayed below 80% of its main-container limit." -ForegroundColor Green
    }
}

try {
    $null = Get-Command kubectl -ErrorAction Stop
    $context = Invoke-Kubectl -Arguments @("config", "current-context")

    $prometheusPodObject = Get-WorkloadPod -Name "prometheus"
    if (-not $prometheusPodObject) {
        throw "No running Prometheus pod found in namespace $Namespace."
    }

    $script:PrometheusPod = $prometheusPodObject.metadata.name
    $prometheusContainers = @($prometheusPodObject.spec.containers | ForEach-Object name)
    $script:PrometheusContainer = if ($prometheusContainers -contains "prometheus-server") {
        "prometheus-server"
    }
    else {
        $prometheusContainers[0]
    }

    Write-Host ""
    Write-Host "################################################################" -ForegroundColor Cyan
    Write-Host " OBSERVABILITY MEMORY AND OOM REPORT" -ForegroundColor Cyan
    Write-Host "################################################################" -ForegroundColor Cyan
    Write-Host "Cluster       : $context"
    Write-Host "Namespace     : $Namespace"
    Write-Host "Prometheus pod: $script:PrometheusPod"
    Write-Host "Peak window   : $PeakHours hours"

    Show-WorkloadReport -DisplayName "Grafana" -LabelName "grafana" -MainContainer "grafana"
    Show-WorkloadReport -DisplayName "Jaeger" -LabelName "jaeger" -MainContainer "jaeger"
    Show-WorkloadReport -DisplayName "Accounting" -LabelName "accounting" -MainContainer "accounting" -WorkloadNamespace "techx-tf4"

    Write-Host ""
    Write-Host "Report completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')." -ForegroundColor Cyan
}
catch {
    Write-Error $_
    exit 1
}
