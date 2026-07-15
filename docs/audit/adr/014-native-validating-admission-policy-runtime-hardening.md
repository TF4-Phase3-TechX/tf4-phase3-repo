# ADR 014: Native ValidatingAdmissionPolicy for runtime hardening

- Status: Proposed — technical review and cluster-scope RBAC required
- Date: 2026-07-15
- Owner: Nhân
- Reviewer: Nguyên
- Ticket: CDO08-SEC-04

## Context

Directive #5 requires admission-time rejection of workloads that run as root, allow privilege escalation, retain Linux capabilities, use floating images, or omit CPU/memory requests and limits. Rollout must not reduce the service SLO.

The target EKS API server is Kubernetes v1.34.9. The current security audit role cannot list or manage ValidatingAdmissionPolicy, CRDs, or validating webhooks, so the installed admission inventory could not be confirmed.

## Decision

Use Kubernetes `ValidatingAdmissionPolicy` with CEL rather than installing Kyverno or Gatekeeper.

Reasons:

- The API is stable and available on the target Kubernetes version.
- No new controller, compute request, webhook certificate, or operational dependency is introduced.
- It meets Directive #5's near-zero additional infrastructure-cost constraint.
- Audit and enforcement can be separated using bindings and namespace labels.

Three policies cover the different Kubernetes object paths:

- Pod and Pod ephemeral-container updates.
- Deployment, StatefulSet, DaemonSet, and Job.
- CronJob.

The policy checks application and init containers for:

- `runAsNonRoot: true` at container or pod level.
- `allowPrivilegeEscalation: false` at container level.
- `capabilities.drop` containing `ALL`.
- `RuntimeDefault` or `Localhost` seccomp at container or pod level.
- A fixed image tag or SHA-256 digest; untagged and `latest` images are rejected.
- CPU/memory requests and limits.

## Rollout decision

Bindings are opt-in by namespace label:

- `security.techx.io/runtime-hardening=audit` activates `Audit,Warn`.
- `security.techx.io/runtime-hardening=enforce` activates `Deny`.

Rollout order:

1. Obtain cluster-scope read/apply permission and have the policy reviewed.
2. Server-side dry-run the policies to compile CEL without persistence.
3. Apply policies and audit bindings.
4. Label a dedicated test namespace `audit`, then inspect warnings.
5. Fix current workload and complete owner smoke tests.
6. Change only the test namespace label to `enforce` and demonstrate the three deny cases plus one allow case.
7. Enforce production only after the violation count is zero and SLO rollback criteria are agreed.

## Rules not immediately enforced in production

All rules remain proposed/audit-only until existing images without a verified non-root `USER` are rebuilt or tested. `readOnlyRootFilesystem` is deliberately not an admission requirement in this batch because application write paths have not all been tested.

## Safety and rollback

- Do not label `techx-tf4` as `enforce` until all rendered and runtime workloads comply.
- To stop false-positive denial, change the namespace label from `enforce` to `audit`; this preserves visibility while removing `Deny`.
- If necessary, delete only the affected enforce binding. Do not delete all policies first.
- Policy `failurePolicy: Fail` is intentional for enforce mode, but must be reviewed before production activation.
- Workload hardening rolls out independently from admission enforcement and is reverted through the existing Helm/GitOps release revision.

## Alternatives considered

### Kyverno

Good Kubernetes-native authoring, reporting, and exceptions, but it adds a controller/webhook and operating cost when no existing installation can be confirmed.

### OPA Gatekeeper

Strong general policy framework, but adds controller/webhook operations and Rego complexity. Prefer it only if the platform team already standardizes on Gatekeeper.

## Consequences

- Platform administrators must grant or perform cluster-scoped policy operations.
- Native CEL has fewer reporting and exception features than dedicated engines; namespace opt-in and narrowly scoped bindings are therefore part of the design.
- A Deployment violation is rejected at Deployment admission rather than being accepted and failing later when its ReplicaSet creates Pods.

## Approval

- Owner (Nhân): pending
- Technical reviewer (Nguyên): pending
- Service owner smoke test: pending
