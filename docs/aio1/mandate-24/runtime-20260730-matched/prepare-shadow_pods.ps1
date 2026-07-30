param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9-]+$')]
    [string]$RunId,
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

$source = kubectl --context $Context -n $Namespace get deployment product-reviews -o json |
    ConvertFrom-Json
$readyPod = kubectl --context $Context -n $Namespace get pods `
    -l opentelemetry.io/name=product-reviews -o json |
    ConvertFrom-Json |
    Select-Object -ExpandProperty items |
    Where-Object { $_.status.phase -eq 'Running' } |
    Select-Object -First 1

if (-not $readyPod) {
    throw 'No running production product-reviews pod is available as the node reference.'
}

$serviceSelector = kubectl --context $Context -n $Namespace get service product-reviews -o json |
    ConvertFrom-Json |
    Select-Object -ExpandProperty spec |
    Select-Object -ExpandProperty selector

function Set-ContainerEnv {
    param(
        [Parameter(Mandatory = $true)]$Container,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $existing = $Container.env | Where-Object { $_.name -eq $Name } | Select-Object -First 1
    if ($existing) {
        $existing.PSObject.Properties.Remove('valueFrom')
        if ($existing.PSObject.Properties['value']) {
            $existing.value = $Value
        } else {
            $existing | Add-Member -NotePropertyName value -NotePropertyValue $Value
        }
        return
    }

    $Container.env += [pscustomobject]@{ name = $Name; value = $Value }
}

function New-ShadowPod {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('on', 'off')][string]$Mode
    )

    $name = "m24-overhead-$Mode-$RunId"
    $labels = [ordered]@{
        'app.kubernetes.io/component' = 'product-reviews'
        'app.kubernetes.io/name' = 'm24-overhead-shadow'
        'm24.techx.io/run-id' = $RunId
        'm24.techx.io/mode' = $Mode
        'opentelemetry.io/name' = "m24-overhead-$Mode"
    }

    if (
        $serviceSelector.'opentelemetry.io/name' -eq
        $labels.'opentelemetry.io/name'
    ) {
        throw "$name would match the production product-reviews Service selector."
    }

    $podSpec = $source.spec.template.spec | ConvertTo-Json -Depth 100 | ConvertFrom-Json
    $podSpec | Add-Member -NotePropertyName nodeName -NotePropertyValue $readyPod.spec.nodeName -Force
    $podSpec.restartPolicy = 'Never'
    $container = $podSpec.containers | Where-Object { $_.name -eq 'product-reviews' }

    Set-ContainerEnv -Container $container -Name LLM_OBSERVABILITY_ENABLED `
        -Value $(if ($Mode -eq 'on') { 'true' } else { 'false' })
    Set-ContainerEnv -Container $container -Name OTEL_SDK_DISABLED `
        -Value $(if ($Mode -eq 'on') { 'false' } else { 'true' })

    $pod = [ordered]@{
        apiVersion = 'v1'
        kind = 'Pod'
        metadata = [ordered]@{
            name = $name
            namespace = $Namespace
            labels = $labels
            annotations = [ordered]@{
                'm24.techx.io/purpose' = 'matched-observability-overhead'
                'm24.techx.io/source-image' = [string]$container.image
            }
        }
        spec = $podSpec
    }

    $existing = kubectl --context $Context -n $Namespace get pod $name `
        --ignore-not-found -o name
    if ($existing) {
        throw "Refusing to overwrite existing pod: $existing"
    }

    $pod | ConvertTo-Json -Depth 100 -Compress |
        kubectl --context $Context -n $Namespace create -f -
}

New-ShadowPod -Mode off
New-ShadowPod -Mode on

Write-Output "RUN_ID=$RunId"
Write-Output "NODE=$($readyPod.spec.nodeName)"
Write-Output "SOURCE_IMAGE=$($source.spec.template.spec.containers[0].image)"
