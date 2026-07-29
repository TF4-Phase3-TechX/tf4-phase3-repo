# Mandate 22 production drill go/no-go checklist

- Jira: [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83)
- Accountable owner/defender: Thành Tâm
- Drill operator and evidence coordinator: Đinh Danh Nam
- CDO owner: the named approver for the exact production window
- Last updated: 2026-07-29
- Closure contract: purpose -> owner -> design/trade-off -> artifact ->
  verification -> claim boundary

## Purpose

This checklist prevents another live attempt from discovering a deterministic
precondition only after the detector fires. It is intentionally a minimum
go/no-go contract, not a requirement to produce perfect dashboards or high
load.

The 2026-07-29 attempt proved the production detector path but did not prove
successful remediation:

- incident `inc-b0451f11cb05` detected a `service_latency_spike` for
  `product-reviews`;
- the controller escalated before mutation because
  `AIOPS_KNOWN_GOOD_REVISIONS` did not pin `product-reviews`;
- the broad service histogram was also dominated by
  `grpc.health.v1.Health/Check` (about 300 probes per five minutes);
- the user RPC histogram reached about 4.85 seconds, while the broad service
  histogram remained near 1.9 milliseconds.

The successful acceptance path is:

```text
bounded user-RPC latency
  -> one incident
  -> policy preflight
  -> one patch to a pinned retained healthy template
  -> ready rollout
  -> user-RPC SLO recovery with sufficient traffic
  -> terminal durable saga with Lease/Argo ownership cleaned
  -> GitOps restore
```

## Safe baseline observed after the failed attempt

Read-only runtime inspection at `2026-07-29T17:05:36Z` confirmed:

- AWS account `511825856493` and cluster `techx-tf4-cluster`;
- `product-reviews` Deployment revision 98, 2/2 ready, zero restarts, no
  `MANDATE22_*` variables;
- `aiops` Deployment revision 56, 1/1 ready, zero restarts;
- `REMEDIATION_MODE=dry-run`, autonomous remediation `false`, durable file saga
  backend, no known-good pin;
- `/v1/incidents` empty, `product-reviews` mutation block false, no durable saga
  ID, and readiness/Prometheus/OpenSearch/Jaeger available.

This is level-5 evidence for a safe restored baseline only. It is not evidence
of a successful remediation.

## Gate strictness

A **STOP** item is allowed only when its absence can produce an invalid result,
an unsafe mutation, or an unrecoverable/ambiguous drill. Everything else is a
warning or evidence item.

The following are **not** STOP gates:

- Locust UI versus the targeted CLI; either may produce the bounded traffic;
- even distribution across both product-review pods;
- a large virtual-user count;
- mentor presence during the run;
- a readable Argo `Application` CR from the operator role, if the merged GitOps
  source and Argo UI prove the same narrow ignore rule;
- a separate manual Kubernetes server dry-run. The controller performs
  `dryRun=All` immediately before mutation and fails closed if it is denied.

## Five hard STOP gates

Do not merge the live activation until all five rows are green. Record the
command output or link beside each checkbox.

| Gate | Minimum pass condition | Why it is a hard stop |
| --- | --- | --- |
| G1 Clean baseline | Target and AIOps are ready; fault is absent; mode is `dry-run`; autonomous is `false`; no non-terminal/cooldown-blocking incident, open saga, Lease or mutation block exists | A stale action can be mistaken for the new drill or race the new mutation |
| G2 Correct user signal | The deployed AIOps image scopes product-review latency, error and verification volume to `oteldemo.ProductReviewService/GetProductReviews`; a small dry-run smoke produces a numeric user-RPC series | Health probes previously hid the incident and could falsely satisfy verification volume |
| G3 Exact rollback target | Healthy Deployment revision `R` is named, still retained after fault revision `F` is ready, and live config contains `AIOPS_KNOWN_GOOD_REVISIONS=product-reviews=R` | “Previous” is not necessarily healthy; the controller deliberately denies an unpinned live action |
| G4 Mutation lifecycle | Exact target allowlist, live policy, durable saga storage, patch/Lease RBAC and narrow time-boxed Argo template ownership are active together | Missing any one causes preflight denial, Argo overwrite or incomplete cleanup |
| G5 Recovery ready | A restore diff is reviewed and ready; an operator owns it; bounded traffic will continue through post-action verification; the normal product-review route is used, not a paid-AI endpoint | A stopped load makes recovery telemetry unavailable, and an unowned restore extends production risk |

### G1 — clean baseline

Run from `E:\xBrain-capstone3` with the refreshed read-only account-511
credentials:

```powershell
$env:AWS_SHARED_CREDENTIALS_FILE=(Resolve-Path '.aws\credentials.txt').Path
$profile='511825856493_TF4-AIReadOnlyOrLimitedInvoke'
aws sts get-caller-identity --profile $profile
kubectl config current-context
kubectl -n techx-tf4 rollout status deploy/product-reviews --timeout=60s
kubectl -n techx-tf4 rollout status deploy/aiops --timeout=60s
kubectl -n techx-tf4 get pods `
  -l 'app.kubernetes.io/name in (product-reviews,aiops)' `
  -o custom-columns='NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount'
```

Expected identity/account and context:

```text
Account: 511825856493
cluster: techx-tf4-cluster
product-reviews: 2/2 ready, zero unexpected restarts
aiops: 1/1 ready, zero unexpected restarts
```

Use the AIOps API from its pod:

```powershell
$pod=kubectl -n techx-tf4 get pod `
  -l app.kubernetes.io/name=aiops `
  -o jsonpath='{.items[0].metadata.name}'
$code=@'
import asyncio, json, urllib.request
from app.config import Settings
from app.saga import build_saga_store

for path in (
    "/readyz",
    "/v1/incidents",
    "/v1/targets/product-reviews/mutation-block",
    "/v1/telemetry/status",
):
    body = urllib.request.urlopen(
        "http://127.0.0.1:8080" + path, timeout=10
    ).read().decode()
    print(path, body)

s = Settings()
store = build_saga_store(s.saga_backend, s.saga_path or None)
open_sagas = asyncio.run(store.list_open_for_target("product-reviews"))
print("mode", s.remediation_mode)
print("autonomous", s.autonomous_remediation_enabled)
print("known_good", json.dumps(s.known_good_revisions, sort_keys=True))
print("open_sagas", [item.saga_id for item in open_sagas])
'@
$b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($code))
kubectl -n techx-tf4 exec $pod -- python -c `
  'import base64,sys;exec(base64.b64decode(sys.argv[1]))' $b64
```

Before staging the fault, pass means:

```text
/readyz = ready
/v1/incidents has no non-terminal or cooldown-blocking product-review incident
blocked = false and durable_saga_ids = []
telemetry sources needed for the drill are available
mode = dry-run
autonomous = False
open_sagas = []
no MANDATE22_* variables on product-reviews
```

### G2 — correct user signal

The code contract is exact operation scoping:

```text
service_name="product-reviews"
span_kind="SPAN_KIND_SERVER"
k8s_namespace_name="techx-tf4"
span_name="oteldemo.ProductReviewService/GetProductReviews"
```

The deployed image must include the operation-scoping tests from the PR linked
to this checklist. After five ordinary review requests in dry-run mode, compare
the method series with probe volume:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(traces_span_metrics_duration_milliseconds_bucket{
      service_name="product-reviews",
      span_kind="SPAN_KIND_SERVER",
      k8s_namespace_name="techx-tf4",
      span_name="oteldemo.ProductReviewService/GetProductReviews"
    }[5m])
  )
)
```

```promql
sum by (span_name) (
  increase(traces_span_metrics_calls_total{
    service_name="product-reviews",
    span_kind="SPAN_KIND_SERVER",
    k8s_namespace_name="techx-tf4"
  }[5m])
)
```

Pass means the first query is numeric after user traffic and the generated
detection and verification queries contain the product-review operation
matcher. A broad service query being numeric from health checks is not a pass.

### G3 — exact rollback target

Capture healthy revision `R` before fault staging:

```powershell
$healthy=kubectl -n techx-tf4 get deploy product-reviews `
  -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}'
kubectl -n techx-tf4 get rs `
  -l app.kubernetes.io/name=product-reviews `
  -o custom-columns='RS:.metadata.name,REV:.metadata.annotations.deployment\.kubernetes\.io/revision,CREATED:.metadata.creationTimestamp,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image'
"healthy_revision=$healthy"
```

After the bounded fault template is ready:

- current revision is a different revision `F`;
- `R` remains among previous ReplicaSets;
- `R` has the reviewed healthy image/template and no fault variables;
- the activation values contain exactly:

```text
AIOPS_KNOWN_GOOD_REVISIONS=product-reviews=R
```

Do not use `F-1` by assumption. Compare the retained ReplicaSet template with
the captured healthy Deployment template. If `R` is pruned or no longer
healthy, STOP and restage from a new healthy baseline.

### G4 — mutation lifecycle

The single activation diff must make these values true together:

```text
aiopsRemediation.liveEnabled=true
REMEDIATION_MODE=live
AIOPS_AUTONOMOUS_REMEDIATION_ENABLED=true
AIOPS_ALLOWED_DEPLOYMENTS contains product-reviews
AIOPS_AUTONOMOUS_RUNBOOKS contains deployment-latency-rollback
AIOPS_KNOWN_GOOD_REVISIONS=product-reviews=R
AIOPS_SAGA_BACKEND=file
AIOPS_SAGA_PATH points to the mounted persistent volume
```

The same reviewed window must provide:

- Deployment get/list/watch/patch for the AIOps service account;
- ReplicaSet read and Lease create/get/update/patch/delete in `techx-tf4`;
- Argo ignore of `/spec/template` scoped only to Deployment
  `product-reviews`;
- no permission to delete Deployments or mutate `flagd`.

Pass may be established from rendered GitOps CI plus the synced Argo UI when
the operator role cannot read the Argo `Application` CR. Do not weaken this
gate to work around missing read permission.

### G5 — recovery, traffic and restore

Before activation:

- a restore PR/diff returns AIOps to `dry-run`/autonomous `false`, removes the
  known-good pin and temporary Argo ownership, removes the fault, and returns
  temporary RBAC to its default;
- the restore owner can merge it during the window;
- the targeted traffic command has been printed once without `--execute`;
- traffic uses only `/api/product-reviews/<product-id>`. This path reads review
  data and does not call the AI assistant/search Bedrock surfaces;
- keep traffic running until the incident is terminal and the last required
  verification poll is captured.

The targeted CLI is preferred because it has a cap, pacing, attribution and a
failure guard. Locust UI is acceptable if configured to the same one-route,
bounded contract. No GitOps change is required for load generation.

```powershell
python techx-corp-platform/src/load-generator/mandate_targeted_load.py `
  --scenario product-reviews `
  --owner nam `
  --run-id m22-<UTC-date>-success `
  --max-requests 500 `
  --workers 5 `
  --pace-seconds 0.10
```

Add `--execute` only after G1–G5 are green and activation is observed ready.
The request cap is an upper bound, not a target that must be exhausted.

## Live sequence and observation checklist

1. [ ] Record account, context, app SHA/image digest and GitOps main SHA.
2. [ ] Pass G1 and save output.
3. [ ] Record healthy revision `R` and export its full pod template.
4. [ ] Stage only the bounded fault while AIOps remains dry-run.
5. [ ] Confirm fault revision `F` is ready and `R` remains retained.
6. [ ] Pass the five-request G2 smoke and confirm the exact user-RPC series.
7. [ ] Confirm the restore diff is ready; then activate G3/G4.
8. [ ] Read settings from the live AIOps pod; do not trust the Git diff alone.
9. [ ] Start bounded targeted traffic and record its JSON output.
10. [ ] Observe exactly one incident and capture:
    `incident_id`, type, service, confidence, approval status, runbook and query.
11. [ ] Observe preflight events including the known-good revision and
    `kubernetes_server_dry_run_passed`.
12. [ ] Observe exactly one `action_executed`; `execution_attempts` must be 1.
13. [ ] Observe a new ready Deployment whose pod template matches retained
    healthy revision `R`.
14. [ ] Keep traffic running through settle and verification windows.
15. [ ] Observe user-RPC latency, error rate and request count recover.
16. [ ] Observe incident `resolved` and durable saga terminal.
17. [ ] Confirm Lease and Argo ownership annotations are cleaned.
18. [ ] Merge restore, then reconfirm G1.

## Stop conditions

Stop new traffic and use the prepared restore/recovery path when any condition
occurs:

- more than one incident or more than one mutation attempt appears;
- the selected revision differs from `R`;
- server dry-run, Lease, durable checkpoint or Argo ownership fails;
- the live template differs from the saga's expected template;
- target readiness drops below one available replica beyond the approved
  rollout budget;
- unrelated service SLOs breach;
- paid-AI calls increase unexpectedly;
- the traffic failure guard trips;
- the incident is not terminal by the approved time box.

If mutation has already been attempted, do not remove cleanup RBAC while an
open saga still owns a Lease or Argo window. Let startup reconciliation finish
or follow the approved recovery procedure. Do not start another drill on top
of a non-terminal saga.

## Evidence and closure boundary

Attach these artifacts to TF4AIO-83:

- this checklist with G1–G5 outputs;
- app and GitOps PRs, merge SHAs, image digest and deployed revisions;
- targeted-load JSON with owner/run ID;
- Prometheus queries/results for the exact user RPC;
- incident JSON and audit events;
- Deployment/ReplicaSet transition;
- terminal saga/cleanup evidence;
- final restore runtime snapshot.

Evidence levels remain distinct:

1. This checklist: designed/documented.
2. Operation-scoped query change: implemented.
3. Unit/CI and replay: tested offline.
4. Image and GitOps sync: deployed.
5. One complete production path: observed in runtime.
6. Jira/mentor closure: accepted/signed off.

Mandate 22 is not closed at levels 1–4. It closes only after level 5 evidence
shows the complete path above and the accountable owner can rerun and explain
it. Acceptance/sign-off remains a separate level 6 claim.
