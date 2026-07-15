[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunId,

    [Parameter(Mandatory = $true)]
    [string]$ApprovedWindow,

    [Parameter(Mandatory = $true)]
    [string]$RemediationVerdict,

    [Parameter(Mandatory = $true)]
    [string]$EnforcementEvidence,

    [string]$Namespace = "techx-tf4",
    [string]$EvidenceRoot = ""
)

$ErrorActionPreference = "Stop"

if ($RunId -notmatch '^D5-PERF-[0-9]{8}T[0-9]{6}Z$') {
    throw "RunId must match D5-PERF-YYYYMMDDTHHMMSSZ"
}

if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $PSScriptRoot "../docs/evidence/directive-05/official-$RunId/performance-regression"
}

$Raw = Join-Path $EvidenceRoot "raw"
$Dashboard = Join-Path $EvidenceRoot "dashboard"
New-Item -ItemType Directory -Force -Path $Raw, $Dashboard | Out-Null

function Save-CommandOutput {
    param([string]$Path, [scriptblock]$Command)
    & $Command 2>&1 | Out-File -FilePath $Path -Encoding utf8
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed; see $Path"
    }
}

$Now = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
@"
# D5-PERF-05 run metadata

- RUN_ID: ``$RunId``
- Precheck UTC: ``$Now``
- Approved window: ``$ApprovedWindow``
- Namespace: ``$Namespace``
- Remediation verdict: ``$RemediationVerdict``
- Enforcement evidence: ``$EnforcementEvidence``
- Load state: NOT STARTED
"@ | Out-File (Join-Path $EvidenceRoot "metadata.md") -Encoding utf8

$Blocked = @()
if ($RemediationVerdict -notmatch '(?i)^\s*PASS(?:\s|$|[-:])') {
    $Blocked += "Resource remediation does not have a PASS verdict."
}
if ([string]::IsNullOrWhiteSpace($ApprovedWindow) -or
    $ApprovedWindow -match '(?i)^\s*(NOT PROVIDED|TBD|UNKNOWN|NONE|N/A)\s*$') {
    $Blocked += "An absolute UTC approved change window was not provided."
}
if (-not (Test-Path $EnforcementEvidence)) {
    $Blocked += "Admission enforcement evidence path does not exist: $EnforcementEvidence"
}
else {
    $EnforcementText = Get-Content -Raw -Path $EnforcementEvidence
    if ($EnforcementText -match '(?i)(not enforced|not active|negative control was accepted|missing-resource[^\r\n]*accepted)') {
        $Blocked += "Admission evidence indicates that resource enforcement is not active."
    }
}

try {
    Save-CommandOutput (Join-Path $Raw "context.txt") { kubectl config current-context }
    Save-CommandOutput (Join-Path $Raw "pods-before.yaml") { kubectl -n $Namespace get pods -o yaml }
    Save-CommandOutput (Join-Path $Raw "deployments-before.yaml") { kubectl -n $Namespace get deployments -o yaml }
    Save-CommandOutput (Join-Path $Raw "hpa-before.yaml") { kubectl -n $Namespace get hpa -o yaml }
    Save-CommandOutput (Join-Path $Raw "nodes-before.txt") { kubectl describe nodes }
    Save-CommandOutput (Join-Path $Raw "events-before.txt") { kubectl -n $Namespace get events --sort-by=.lastTimestamp }

    $Pods = kubectl -n $Namespace get pods -o json | ConvertFrom-Json
    foreach ($Pod in $Pods.items) {
        if ($Pod.status.phase -eq 'Pending') {
            $Blocked += "Pending pod: $($Pod.metadata.name)"
        }
        foreach ($Status in @($Pod.status.containerStatuses)) {
            if ($Status.state.waiting.reason -eq 'CrashLoopBackOff') {
                $Blocked += "CrashLoopBackOff: $($Pod.metadata.name)/$($Status.name)"
            }
            if ($Status.lastState.terminated.reason -eq 'OOMKilled') {
                $Blocked += "Unresolved OOM history requires review: $($Pod.metadata.name)/$($Status.name)"
            }
        }
    }

    $HpaText = kubectl -n $Namespace get hpa --no-headers 2>&1
    if ($HpaText -match '<unknown>') {
        $Blocked += "At least one HPA reports unknown metrics."
    }
}
catch {
    $Blocked += "Cluster precheck failed: $($_.Exception.Message)"
}

$Verdict = if ($Blocked.Count -eq 0) { 'PASS - READY FOR APPROVED LOAD' } else { 'BLOCKED - DO NOT START LOAD' }
$Reasons = if ($Blocked.Count -eq 0) { '- None.' } else { ($Blocked | ForEach-Object { "- $_" }) -join "`n" }

@"
# D5-PERF-05 precheck verdict

**Verdict:** **$Verdict**

## Blocking reasons

$Reasons

## Operator action

This script never starts Locust and never restarts a workload. When PASS, use
the single approved Locust UI harness described in
``docs/evidence/directive-05/D5-PERF-05-performance-regression-contract.md``.
"@ | Out-File (Join-Path $EvidenceRoot "precheck-verdict.md") -Encoding utf8

Write-Host "$Verdict"
Write-Host "Evidence: $EvidenceRoot"
if ($Blocked.Count -gt 0) { exit 2 }
