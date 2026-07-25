param(
  [string]$OutputDir = "docs/evidence/directive-18/D18-COST-02-orphaned-resources/raw/before"
)

$ErrorActionPreference = "Continue"

if (!(Test-Path $OutputDir)) {
  New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

Write-Output "Collecting Kubernetes Services..."
kubectl get svc -A -o json > "$OutputDir/k8s-services.json"

Write-Output "Collecting Kubernetes Ingresses..."
kubectl get ingress -A -o json > "$OutputDir/k8s-ingresses.json"

Write-Output "Collecting TargetGroupBindings (if available)..."
kubectl get targetgroupbindings -A -o json > "$OutputDir/k8s-targetgroupbindings.json"

Write-Output "Collecting Pods and Node mapping..."
kubectl get pods -A -o wide > "$OutputDir/k8s-pods-wide.txt"
kubectl get nodes -o wide > "$OutputDir/k8s-nodes-wide.txt"

Write-Output "Kubernetes data collection complete! Files saved to $OutputDir"
