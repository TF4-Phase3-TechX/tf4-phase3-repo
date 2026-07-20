param(
  [string]$Namespace = 'resource-policy-test',
  [string]$OutputDir = 'docs/evidence/directive-05/admission-tests/resources/results'
)

$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

kubectl create namespace $Namespace --dry-run=client -o yaml | kubectl apply -f - | Out-Null

$cases = @(
  @{ Name = '01-missing-resources'; File = 'docs/evidence/directive-05/admission-tests/resources/01-missing-resources.yaml'; Expected = 'reject'; Field = 'spec.containers[0].resources' },
  @{ Name = '02-missing-limits'; File = 'docs/evidence/directive-05/admission-tests/resources/02-missing-limits.yaml'; Expected = 'reject'; Field = 'spec.containers[0].resources.limits' },
  @{ Name = '03-missing-requests'; File = 'docs/evidence/directive-05/admission-tests/resources/03-missing-requests.yaml'; Expected = 'reject'; Field = 'spec.containers[0].resources.requests' },
  @{ Name = '04-initcontainer-missing-resources'; File = 'docs/evidence/directive-05/admission-tests/resources/04-initcontainer-missing-resources.yaml'; Expected = 'reject'; Field = 'spec.initContainers[0].resources' },
  @{ Name = '05-compliant'; File = 'docs/evidence/directive-05/admission-tests/resources/05-compliant.yaml'; Expected = 'accept'; Field = 'n/a' }
)

foreach ($case in $cases) {
  $outFile = Join-Path $OutputDir ($case.Name + '.log')
  Write-Host "Running $($case.Name)"
  kubectl apply --dry-run=server -f $case.File -n $Namespace 2>&1 | Tee-Object -FilePath $outFile | Out-String | Write-Host
  Write-Host "Expected result: $($case.Expected)"
  Write-Host "Expected field: $($case.Field)"
  Write-Host '---'
}
