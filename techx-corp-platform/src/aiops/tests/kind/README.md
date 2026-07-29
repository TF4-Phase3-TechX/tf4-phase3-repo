# Mandate 22 disposable Kind gate

These tests exercise the production `KubernetesRollbackAdapter` against an
isolated cluster. They are skipped by normal pytest runs. Never point either
kubeconfig variable at EKS or another shared cluster.

## PowerShell setup

Install Kind from its official release, then run from
`techx-corp-platform/src/aiops`:

```powershell
$kind = (Get-Command kind).Source
$taskRoot = Join-Path ([IO.Path]::GetTempPath()) 'xbrain-m22-kind'
$admin = Join-Path $taskRoot 'kubeconfig'
$limited = Join-Path $taskRoot 'kubeconfig-aiops'
$deps = Join-Path $taskRoot 'pydeps'
$manifests = Join-Path $PWD 'tests/kind'

New-Item -ItemType Directory -Path $taskRoot -Force | Out-Null
& $kind create cluster `
  --name m22-local `
  --image 'kindest/node:v1.34.3@sha256:08497ee19eace7b4b5348db5c6a1591d7752b164530a36f855cb0f2bdcbadd48' `
  --kubeconfig $admin `
  --wait 120s

kubectl --kubeconfig $admin apply -f (Join-Path $manifests 'm22-rbac.yaml')
kubectl --kubeconfig $admin apply -f (Join-Path $manifests 'm22-target.yaml')
kubectl --kubeconfig $admin -n m22-local rollout status `
  deployment/product-reviews --timeout=60s
kubectl --kubeconfig $admin apply -f (Join-Path $manifests 'm22-target-v2.yaml')
kubectl --kubeconfig $admin -n m22-local rollout status `
  deployment/product-reviews --timeout=60s

Copy-Item -LiteralPath $admin -Destination $limited -Force
$token = kubectl --kubeconfig $admin -n m22-local create token aiops --duration=1h
kubectl --kubeconfig $limited config set-credentials m22-aiops --token=$token
kubectl --kubeconfig $limited config set-context kind-m22-local `
  --user=m22-aiops --namespace=m22-local
kubectl --kubeconfig $limited config use-context kind-m22-local

python -m pip install --target $deps 'kubernetes==32.0.1'
$env:PYTHONPATH = $deps
$env:KUBECONFIG = $limited
$env:M22_KIND_ADMIN_KUBECONFIG = $admin
python -m pytest tests/kind/test_m22_kind.py -q
```

For a consecutive clean-reset gate, delete only the disposable
`product-reviews` Deployment and remediation Lease with the admin kubeconfig,
then reapply `m22-target.yaml` followed by `m22-target-v2.yaml` before each run.

## Cleanup

```powershell
& $kind delete cluster --name m22-local
$resolved = [IO.Path]::GetFullPath($taskRoot)
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
if (-not $resolved.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
  throw 'Refusing to clean a path outside the system temp directory'
}
Remove-Item -LiteralPath $resolved -Recurse -Force
```

The gate proves controller/Kubernetes lifecycle behavior with a deterministic
verifier. It does not provide production telemetry or a Mandate 22 live pass.
