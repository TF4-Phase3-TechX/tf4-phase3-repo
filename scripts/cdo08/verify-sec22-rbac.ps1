param(
    [string]$AppNamespace = "techx-tf4",
    [string]$ObservabilityNamespace = "techx-observability"
)

$ErrorActionPreference = "Stop"
$failures = 0

function Test-Permission {
    param(
        [string]$Namespace,
        [string]$ServiceAccount,
        [string]$Verb,
        [string]$Resource,
        [string]$Expected
    )

    $identity = "system:serviceaccount:${Namespace}:${ServiceAccount}"
    $actual = (& kubectl auth can-i $Verb $Resource --namespace $Namespace --as $identity 2>&1 | Out-String).Trim()

    if ($LASTEXITCODE -ne 0) {
        $actual = "ERROR: $actual"
    }

    $status = if ($actual -eq $Expected) { "PASS" } else { "FAIL" }
    if ($status -eq "FAIL") { $script:failures++ }

    [pscustomobject]@{
        Namespace      = $Namespace
        ServiceAccount = $ServiceAccount
        Permission     = "$Verb $Resource"
        Expected       = $Expected
        Actual         = $actual
        Status         = $status
    }
}

$applicationServiceAccounts = @(
    "accounting", "ad", "cart", "checkout", "currency", "email", "flagd",
    "fraud-detection", "frontend", "frontend-proxy", "image-provider", "kafka",
    "llm", "load-generator", "payment", "postgresql", "product-catalog",
    "product-reviews-bedrock", "quote", "recommendation", "shipping", "valkey-cart"
)

$results = @()

foreach ($serviceAccount in $applicationServiceAccounts) {
    $results += Test-Permission $AppNamespace $serviceAccount "list" "secrets" "no"
    $results += Test-Permission $AppNamespace $serviceAccount "list" "pods" "no"
    $results += Test-Permission $AppNamespace $serviceAccount "create" "pods" "no"
    $results += Test-Permission $AppNamespace $serviceAccount "create" "pods/exec" "no"
}

$noApiServiceAccounts = @("jaeger", "opensearch", "techx-observability-alertmanager")
foreach ($serviceAccount in $noApiServiceAccounts) {
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "list" "secrets" "no"
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "list" "pods" "no"
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "create" "pods" "no"
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "create" "pods/exec" "no"
}

$results += Test-Permission $ObservabilityNamespace "grafana" "list" "configmaps" "yes"
$results += Test-Permission $ObservabilityNamespace "grafana" "list" "secrets" "no"
$results += Test-Permission $ObservabilityNamespace "grafana" "list" "pods" "no"
$results += Test-Permission $ObservabilityNamespace "grafana" "create" "pods" "no"
$results += Test-Permission $ObservabilityNamespace "grafana" "create" "pods/exec" "no"

foreach ($serviceAccount in @("prometheus", "otel-collector", "metrics-server")) {
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "list" "pods" "yes"
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "list" "secrets" "no"
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "create" "pods" "no"
    $results += Test-Permission $ObservabilityNamespace $serviceAccount "create" "pods/exec" "no"
}

$results | Format-Table -AutoSize

if ($failures -gt 0) {
    Write-Error "SEC-22 RBAC verification failed: $failures unexpected result(s)."
    exit 1
}

Write-Output "SEC-22 RBAC verification passed."
