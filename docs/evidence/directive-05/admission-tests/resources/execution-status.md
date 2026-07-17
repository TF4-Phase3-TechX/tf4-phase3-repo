# Resource admission test execution status

## Current status

The manifest suite and runner have been created under this folder.

## What was verified

- The repository now contains dedicated manifests for the required resource-policy cases:
  - missing resources
  - missing limits
  - missing requests
  - init container missing resources
  - compliant manifest
- A PowerShell runner was added to execute the tests in a non-production namespace (`techx-admission-test`).

## Blocker

The test run could not be completed against the live cluster because the environment did not have valid Kubernetes/AWS credentials at the time of execution.

Observed errors:

- `kubectl apply --dry-run=server` failed because the cluster API requested credentials.
- `aws sts get-caller-identity` failed because the provided AWS credentials were incomplete/invalid.

## Next step for mentor/CI

Run the script once a valid kubeconfig or authenticated AWS session is available:

```powershell
./docs/evidence/directive-05/admission-tests/resources/run-admission-tests.ps1
```

The output should be captured into the `results` folder and used as the acceptance evidence for the policy checks.
