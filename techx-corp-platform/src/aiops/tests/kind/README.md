# Mandate 22 Git/Argo sandbox

`m22_gitops_sandbox.py` runs all three Mandate 22 rounds against a disposable
local Git repository, Kind cluster and real Argo CD Application. It exercises the
production detector, worker, controller, runtime observer and Lease lock. The
local adapter writes real branches and commits and enforces the three checks,
while explicitly simulating the Git-provider PR/webhook boundary.

Install the pinned AIOps requirements, create the cluster and Argo CD, then run:

```powershell
python tests/kind/m22_gitops_sandbox.py `
  --scenario <success|forced-wrong|restart-recovery> `
  --context kind-m22-gitops-sandbox `
  --evidence-dir <artifact-directory>
```

The lightweight pytest contract can additionally be enabled with:

```text
RUN_M22_KIND=1
M22_GITOPS_SANDBOX_REPOSITORY=<owner/repository>
M22_ARGO_APPLICATION=techx-corp
M22_TARGET=product-reviews
```

The complete pre-production sandbox gate has three rounds:

1. successful managed-env remediation;
2. signed forced-wrong candidate followed by compensation;
3. controller restart plus ambiguous branch/PR/merge responses.

Each round captures incident, policy SHA, PR/check identities, merge SHA, Argo
observation, exact review-RPC traffic and terminal saga as JSON. All three were
observed on Kind/Argo on 2026-07-30. Production still requires the dedicated
GitHub App, rulesets, secret/egress bootstrap, activation PR and CDO/on-call
sign-off.

The old `m22-rbac*.yaml` direct-patch fixtures are obsolete and must not be
applied.
