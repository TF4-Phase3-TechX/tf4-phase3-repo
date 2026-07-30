param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9-]+$')]
    [string]$RunId,
    [ValidateRange(5, 100)]
    [int]$Pairs = 20,
    [ValidateRange(0, 10)]
    [int]$WarmupPairs = 3,
    [ValidateRange(0, 10)]
    [double]$InterCallDelay = 0.5,
    [string]$Context = 'techx-tf4-prod',
    [string]$Namespace = 'techx-tf4'
)

$ErrorActionPreference = 'Stop'

if (-not $env:AWS_SHARED_CREDENTIALS_FILE) {
    $workspaceCredentials = 'E:\xBrain-capstone3\.aws\credentials.txt'
    if (-not (Test-Path -LiteralPath $workspaceCredentials)) {
        throw "AWS credentials file not found: $workspaceCredentials"
    }
    $env:AWS_SHARED_CREDENTIALS_FILE = $workspaceCredentials
}

$offName = "m24-overhead-off-$RunId"
$onName = "m24-overhead-on-$RunId"
$runnerName = "m24-overhead-runner-$RunId"
$off = kubectl --context $Context -n $Namespace get pod $offName -o json |
    ConvertFrom-Json
$on = kubectl --context $Context -n $Namespace get pod $onName -o json |
    ConvertFrom-Json

if ($off.spec.nodeName -ne $on.spec.nodeName) {
    throw 'The ON and OFF pods are not on the same node.'
}
if (-not $off.status.podIP -or -not $on.status.podIP) {
    throw 'The ON and OFF pod IPs are unavailable.'
}
if ($off.spec.containers[0].image -ne $on.spec.containers[0].image) {
    throw 'The ON and OFF images differ.'
}

$runnerScript = Join-Path $PSScriptRoot 'run_matched_overhead.py'
$encoded = [Convert]::ToBase64String(
    [System.IO.File]::ReadAllBytes($runnerScript)
)
$bootstrap = "import base64;exec(compile(base64.b64decode('$encoded'),'<m24-runner>','exec'))"
$containerSecurity = [ordered]@{
    allowPrivilegeEscalation = $false
    capabilities = [ordered]@{ drop = @('ALL') }
    readOnlyRootFilesystem = $true
    runAsNonRoot = $true
    runAsUser = 10001
    seccompProfile = [ordered]@{ type = 'RuntimeDefault' }
}

$pod = [ordered]@{
    apiVersion = 'v1'
    kind = 'Pod'
    metadata = [ordered]@{
        name = $runnerName
        namespace = $Namespace
        labels = [ordered]@{
            # The production NetworkPolicy allows only frontend-labelled
            # callers to reach product-reviews:3551.
            'app.kubernetes.io/component' = 'frontend'
            'app.kubernetes.io/name' = 'm24-overhead-runner'
            'm24.techx.io/run-id' = $RunId
            'opentelemetry.io/name' = 'm24-overhead-runner'
        }
    }
    spec = [ordered]@{
        restartPolicy = 'Never'
        nodeName = $off.spec.nodeName
        serviceAccountName = 'product-reviews-bedrock'
        securityContext = [ordered]@{
            seccompProfile = [ordered]@{ type = 'RuntimeDefault' }
        }
        volumes = @(
            [ordered]@{ name = 'output'; emptyDir = [ordered]@{} }
        )
        containers = @(
            [ordered]@{
                name = 'runner'
                image = $off.spec.containers[0].image
                imagePullPolicy = 'IfNotPresent'
                command = @('/venv/bin/python')
                args = @(
                    '-c', $bootstrap,
                    '--run-id', $RunId,
                    '--off-target', "$($off.status.podIP):3551",
                    '--on-target', "$($on.status.podIP):3551",
                    '--pairs', [string]$Pairs,
                    '--warmup-pairs', [string]$WarmupPairs,
                    '--inter-call-delay', [string]$InterCallDelay,
                    '--gate-percent', '5',
                    '--output-dir', '/tmp/m24',
                    '--proto-dir', '/app'
                )
                securityContext = $containerSecurity
                volumeMounts = @(
                    [ordered]@{ name = 'output'; mountPath = '/tmp/m24' }
                )
                resources = [ordered]@{
                    requests = [ordered]@{ cpu = '50m'; memory = '64Mi' }
                    limits = [ordered]@{ cpu = '250m'; memory = '128Mi' }
                }
            }
        )
    }
}

$existing = kubectl --context $Context -n $Namespace get pod $runnerName `
    --ignore-not-found -o name
if ($existing) {
    throw "Refusing to overwrite existing pod: $existing"
}

$pod | ConvertTo-Json -Depth 100 -Compress |
    kubectl --context $Context -n $Namespace create -f -

Write-Output "RUNNER=$runnerName"
Write-Output "OFF_TARGET=$($off.status.podIP):3551"
Write-Output "ON_TARGET=$($on.status.podIP):3551"
Write-Output "PAIRS=$Pairs"
