# Resource admission test manifests

This folder contains a small test set for validating resource-related admission policy behavior without targeting a production namespace.

## Scope

The cases below are designed to verify that the policy rejects:

- a container without any resource requests/limits
- a container with requests but no limits
- a container with limits but no requests
- an init container without resources

The cases also include a compliant manifest that should be accepted.

## Test namespace

All manifests target the namespace `resource-policy-test` so the tests do not run in production.

## Execution

From the repository root:

```powershell
kubectl create namespace resource-policy-test --dry-run=client -o yaml | kubectl apply -f -
.
\docs\evidence\directive-05\admission-tests\resources\run-admission-tests.ps1
```

## Expected policy behavior

- `01-missing-resources.yaml` should be rejected because the container has no `resources` block.
- `02-missing-limits.yaml` should be rejected because `spec.containers[0].resources.limits` is missing.
- `03-missing-requests.yaml` should be rejected because `spec.containers[0].resources.requests` is missing.
- `04-initcontainer-missing-resources.yaml` should be rejected because `spec.initContainers[0].resources` is missing.
- `05-compliant.yaml` should be accepted.
