# Admission test results placeholder

This folder is intended for the outputs of the resource admission test run.

The current environment could not reach the cluster because Kubernetes credentials were not available, so the script was not able to produce real admission results yet.

When a valid kubeconfig/AWS credential is present, run:

```powershell
./docs/evidence/directive-05/admission-tests/resources/run-admission-tests.ps1
```

Expected output should include:

- rejection for the missing-resources case with a clear field-specific error
- rejection for the missing-limits case with a clear field-specific error
- rejection for the missing-requests case with a clear field-specific error
- rejection for the initcontainer case with the initContainer field identified
- acceptance for the compliant manifest
