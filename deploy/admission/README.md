# Runtime hardening admission rollout

These manifests implement CDO08-SEC-04 using native Kubernetes ValidatingAdmissionPolicy.

## Files

- `runtime-hardening-policy.yaml`: CEL policies; no binding means no effect.
- `runtime-hardening-audit-bindings.yaml`: `Audit,Warn` for namespaces labelled `security.techx.io/runtime-hardening=audit`.
- `runtime-hardening-enforce-bindings.yaml`: `Deny` for namespaces labelled `security.techx.io/runtime-hardening=enforce`.
- `tests/`: isolated invalid/valid Deployment examples.

## Required review and permission

These resources are cluster-scoped. Do not apply them with the current `TF4-SecReliabilityReadOnlyAudit` role. Nguyên/platform security must review the CEL expressions, `failurePolicy`, scope, and rollback before a privileged operator applies them.

## Audit rollout

```powershell
kubectl apply --server-side --dry-run=server -f deploy/admission/runtime-hardening-policy.yaml
kubectl apply --server-side --dry-run=server -f deploy/admission/runtime-hardening-audit-bindings.yaml
kubectl apply -f deploy/admission/runtime-hardening-policy.yaml
kubectl apply -f deploy/admission/runtime-hardening-audit-bindings.yaml
kubectl label namespace <audit-namespace> security.techx.io/runtime-hardening=audit --overwrite
```

Do not use the production namespace for the first admission test.

## Enforce test

After the audit namespace is compliant:

```powershell
kubectl apply --server-side --dry-run=server -f deploy/admission/runtime-hardening-enforce-bindings.yaml
kubectl apply -f deploy/admission/runtime-hardening-enforce-bindings.yaml
kubectl label namespace <test-namespace> security.techx.io/runtime-hardening=enforce --overwrite
kubectl -n <test-namespace> apply --dry-run=server -f deploy/admission/tests/deny-root.yaml
kubectl -n <test-namespace> apply --dry-run=server -f deploy/admission/tests/deny-latest.yaml
kubectl -n <test-namespace> apply --dry-run=server -f deploy/admission/tests/deny-missing-limits.yaml
kubectl -n <test-namespace> apply --dry-run=server -f deploy/admission/tests/allow-valid.yaml
```

Expected results: the first three commands are denied with the matching policy message; `allow-valid.yaml` is allowed.

## Fast rollback

Remove denial while retaining audit visibility:

```powershell
kubectl label namespace <namespace> security.techx.io/runtime-hardening=audit --overwrite
```

If the namespace must be taken completely out of scope:

```powershell
kubectl label namespace <namespace> security.techx.io/runtime-hardening-
```

Deleting an individual enforce binding is the second rollback option. Perform changes through the approved source-of-truth workflow.
