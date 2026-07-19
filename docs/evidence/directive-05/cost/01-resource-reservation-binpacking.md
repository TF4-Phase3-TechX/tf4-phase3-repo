# D5-COST-01 — Resource Reservation and Bin-Packing Analysis

**Jira:** `C0G-51`  
**Owner:** CDO-04 — Performance & Cost  
**Cluster / namespace:** `techx-tf4-cluster` / `techx-tf4`  
**Region:** `us-east-1`  
**Evidence collected:** `2026-07-16T03:34:02Z`  
**Git SHA:** `40cd1ff08ac3a9d0eac548b634a099f5716a8caf`  
**Status:** **PARTIAL — desired baseline validates; worst-case HPA is blocked by `limits.cpu` quota; 4 workers are required for modeled scheduler headroom. No authorized rollout was performed.**

---

## 1. Scope and decision boundary

This report evaluates the Directive 5 requirement that every workload declares CPU/memory requests and limits, specifically its Cost Optimization outcome: predictable reservation, scheduler bin-packing, and bounded node-scale cost. Directive requirements are at [`docs/requirements/mandates/MANDATE-05-runtime-hardening.md`](../../../requirements/mandates/MANDATE-05-runtime-hardening.md).

This is a CDO04 COST/PERF report. It does **not** claim that the admission policy rejects root containers or mutable image tags; those policy/ADR and rejection proofs remain owned by the Security workstream. The resource model here uses the Helm desired state, current `ResourceQuota`, and live scheduler evidence.

**Important distinction:** requests determine placement; limits are a namespace admission guardrail; `kubectl top` is observed usage. Low CPU usage is not evidence of scheduler headroom.

---

## 2. Inputs, method, and reproducibility

| Input | Authority | Use |
|---|---|---|
| Workload resources and replica/HPA values | [`techx-corp-chart/values.yaml`](../../../../techx-corp-chart/values.yaml) | Desired reservations |
| Pod rendering and init-container behavior | [`techx-corp-chart/templates/_objects.tpl`](../../../../techx-corp-chart/templates/_objects.tpl) | Container coverage |
| HPA rendering | [`techx-corp-chart/templates/hpa.yaml`](../../../../techx-corp-chart/templates/hpa.yaml) | HPA min/max |
| Namespace hard limits | [`deploy/quota.yaml`](../../../../deploy/quota.yaml) | Quota compatibility |
| Managed worker configuration | [`infra/terraform/eks.tf`](../../../../infra/terraform/eks.tf) | 2 × `t3.large` baseline |
| Karpenter configuration | [`infra/terraform/karpenter-nodepool.tf`](../../../../infra/terraform/karpenter-nodepool.tf) | Dynamic worker boundary |
| Worker pricing model | [D3-COST-01](../../MANDATE-03-%20Maintenance%20Capacity%20%26%20Cost-Efficient%20Resilience/D3-COST-01-replica-capacity-cost-model/01-replica-capacity-cost-model.md) | EC2 + root EBS estimate |

The application was rendered with the same release name, namespace, image override, and values overlays as CI. [`raw/13-calculate-reservations.py`](raw/13-calculate-reservations.py) parses the resulting 22 Deployment templates, including regular and init containers, and asserts every container has CPU/memory request and limit fields. Scheduler reservation for a Pod is calculated as:

```text
max(sum(regular containers), max(init containers))
```

The conservative rollout model is intentionally stricter than a single rollout: all HPAs reach `maxReplicas`, then every Deployment has `ceil(25% × its HPA-min/current replicas)` surge Pod concurrently. It identifies the capacity ceiling; it is not a forecast that all Deployments will roll simultaneously.

The static `deploy/karpenter/nodepool.yaml` still says `limits.cpu: "4"`, but Terraform is authoritative and the live NodePool confirms `spec.limits.cpu: 16`; the stale annotation merely preserves an older applied manifest ([`raw/07-live-karpenter-nodepool-nodeclaim.yaml`](raw/07-live-karpenter-nodepool-nodeclaim.yaml)).

---

## 3. Rendered resource coverage and HPA envelope

| Check | Result | Evidence |
|---|---|---|
| Rendered Deployments | 22 | [`raw/14-reservation-calculation.json`](raw/14-reservation-calculation.json) |
| HPA targets | `checkout`, `currency`, `frontend` | same |
| Missing CPU/memory requests or limits in regular/init containers | none | same |
| HPA min → max | each `2 → 3` | same; chart values |
| Server-side dry-run of all rendered Deployments | **PASS**, exit 0 | [`raw/12b-server-side-dry-run-deployments.command.txt`](raw/12b-server-side-dry-run-deployments.command.txt), [`stdout`](raw/12b-server-side-dry-run-deployments.stdout.txt) |

The first whole-chart dry-run exited 1 because the render contains cluster-scoped objects and `kube-system` objects while the command was deliberately namespace-scoped to `techx-tf4`; the evidence is retained at [`raw/12-server-side-dry-run-rendered-app.*`](raw/). The cost-relevant Deployment-only dry-run then passed with `--server-side --dry-run=server --force-conflicts`; dry-run does not persist changes.

---

## 4. Before/after reservation and quota table

The historical D3 snapshot and fresh live collection have the same baseline values. The fresh equality is recorded in [`raw/01-live-resourcequota-prevalidation.yaml`](raw/01-live-resourcequota-prevalidation.yaml) and is not assumed from history.

| Scenario | Requests CPU | Requests memory | Limits CPU | Limits memory | Pods | Quota result |
|---|---:|---:|---:|---:|---:|---|
| Before: D3 snapshot, 2026-07-15 | 1905m / 4000m (47.6%) | 3491Mi / 8192Mi (42.6%) | 7450m / 8000m (93.1%) | 5893Mi / 12288Mi (48.0%) | 31 / 40 (77.5%) | Baseline only |
| Fresh baseline / rendered HPA min | 1905m / 4000m (47.6%) | 3491Mi / 8192Mi (42.6%) | 7450m / 8000m (93.1%) | 5893Mi / 12288Mi (48.0%) | 31 / 40 (77.5%) | **PASS**, but 550m limit-CPU margin |
| HPA maximum: +1 replica each for `frontend`, `checkout`, `currency` | 2155m / 4000m (53.9%) | 3827Mi / 8192Mi (46.7%) | **8450m / 8000m (105.6%)** | 6501Mi / 12288Mi (52.9%) | 34 / 40 (85.0%) | **FAIL — `limits.cpu` exceeds quota by 450m** |
| HPA maximum + conservative simultaneous 25% rollout surge | 3555m / 4000m (88.9%) | 6690Mi / 8192Mi (81.7%) | **13875m / 8000m (173.4%)** | 11202Mi / 12288Mi (91.2%) | **56 / 40 (140.0%)** | **FAIL — CPU limits and Pods** |

The HPA-only delta is `+250m` CPU request, `+336Mi` memory request, `+1000m` CPU limit, `+608Mi` memory limit, and `+3` Pods. This is enough to make a current HPA scale-up fail admission, regardless of node CPU availability. The prior `FailedCreate` evidence in [`docs/evidence/directive-03/cost/raw/10-events-techx-tf4.txt`](../../directive-03/cost/raw/10-events-techx-tf4.txt) shows the same failure mode for `frontend` at this quota.

**Minimum correction before approving HPA max:** set quota after an approved capacity decision, not blindly. The mathematical minimum for HPA maximum is `limits.cpu: 8450m`; a safe value must also cover the approved rollout strategy and a stated margin. The all-Deployment simultaneous-surge model additionally needs 56 Pods and 13875m limits CPU, but that is a conservative planning ceiling rather than a recommended resting quota.

---

## 5. Bin-packing and node utilization

### 5.1 Live three-worker state

All workers were Ready. Each exposes approximately 1930m allocatable CPU and 7079–7101Mi allocatable memory; aggregate allocatable capacity is 5790m CPU, 21259Mi memory, and 105 Pods. Reservation includes every Running/ Pending Pod on each node, including `kube-system`, observability, Argo CD, and application Pods.

| Node | Type | Allocatable CPU / memory / pods | Reserved requests CPU / memory / pods | Reservation ratio CPU / memory / pods | Observed CPU / memory |
|---|---|---|---|---|---|
| `ip-10-0-10-17` | Karpenter `t3a.large` | 1930m / 7101Mi / 35 | 1695m / 4611Mi / 24 | 87.8% / 64.9% / 68.6% | 293m (15%) / 3906Mi (55%) |
| `ip-10-0-10-231` | managed `t3.large` | 1930m / 7079Mi / 35 | 1790m / 2630Mi / 24 | 92.8% / 37.2% / 68.6% | 215m (11%) / 3425Mi (48%) |
| `ip-10-0-11-40` | managed `t3.large` | 1930m / 7079Mi / 35 | 1910m / 1168Mi / 21 | **99.0%** / 16.5% / 60.0% | 192m (9%) / 3901Mi (55%) |

Sources: [`raw/04-live-nodes-prevalidation.yaml`](raw/04-live-nodes-prevalidation.yaml), [`raw/05-node-allocatable-and-allocated.txt`](raw/05-node-allocatable-and-allocated.txt), [`raw/06-node-observed-usage.txt`](raw/06-node-observed-usage.txt), and [`raw/14-reservation-calculation.json`](raw/14-reservation-calculation.json).

The three-worker model has only `395m` aggregate request CPU headroom before HPA expansion. At HPA maximum it has `145m` (2.5%) aggregate headroom, and topology/PDB placement may make it smaller in practice. The existing node-level 99.0% reservation means 3 workers are **not** maintenance-safe for a roll/recovery event even though observed CPU is only 9–15%.

### 5.2 Four-worker maintenance target

Terraform defines 2 managed `t3.large` workers (`min=2`, `desired=2`, `max=4`). Live Karpenter has one `t3a.large`; the target adds one equivalent dynamic worker, giving 7720m CPU, approximately 28360Mi memory, and 140 Pod slots.

| Model | CPU request reservation | CPU headroom | Memory request reservation | Memory headroom | Result |
|---|---:|---:|---:|---:|---|
| Current all-namespace baseline, 3 workers | 5395m / 5790m (93.2%) | 395m | 8409Mi / 21259Mi (39.6%) | 12850Mi | Current placement only |
| HPA max, 3 workers | 5645m / 5790m (97.5%) | 145m | 8745Mi / 21259Mi (41.1%) | 12514Mi | Not maintenance-safe |
| HPA max, 4 workers | 5645m / 7720m (73.1%) | 2075m | 8745Mi / 28360Mi (30.8%) | 19615Mi | Scheduler headroom, **but quota still blocks** |
| HPA max + simultaneous surge, 4 workers | 7045m / 7720m (91.3%) | 675m | 11608Mi / 28360Mi (40.9%) | 16752Mi | Scheduler-only model fits narrowly; quota and Pod quota fail |

The 4-worker target is the minimum reasonable maintenance target for the **scheduler** model. It is not pre-provisioned headroom: Karpenter's 16-vCPU setting is only a configuration ceiling, and actual placement still depends on NodeClaims, zones, PDBs, affinity/spread rules, and quota admission.

---

## 6. Node-scale cost estimate

D3-COST-01 verified these On-Demand `us-east-1` inputs from AWS Price List API:

- `t3.large`: `$0.0832/hour` compute;
- `t3a.large`: `$0.0752/hour` compute;
- 20-GiB gp3 root disk: `$1.60/month` = `$0.0021918/hour`.

| Worker scenario | Full hourly rate | Hourly total | Monthly equivalent (730h) | Delta vs 2 managed workers |
|---|---:|---:|---:|---:|
| 2 × managed `t3.large` baseline | `$0.0853918` | `$0.1707836` | `$124.67` | — |
| Observed: 2 × `t3.large` + 1 × Karpenter `t3a.large` | mixed | `$0.2481754` | `$181.17` | `$56.50/month` |
| Maintenance target: 2 × `t3.large` + 2 × `t3a.large` | mixed | `$0.3255672` | `$237.67` | `$113.00/month` |

The final two rows are **monthly equivalents**, not an actual-billing forecast. A second dynamic `t3a.large` costs approximately `$0.0773918/hour`, `$0.6191` for 8 hours, or `$1.8574` for 24 hours. Cost Explorer/CUR reconciliation remains a post-run check.

---

## 7. Dry-run and runtime status

- The Deployment-only server-side dry-run passed at `2026-07-16T03:34Z`; no object was persisted.
- The post-validation snapshot shows all 22 Deployments at `READY = UP-TO-DATE = AVAILABLE` and all 31 application Pods `Running`; no application Pod is `Pending` ([`raw/15-postvalidation-deployments.txt`](raw/15-postvalidation-deployments.txt), [`raw/16-postvalidation-pods.txt`](raw/16-postvalidation-pods.txt)).
- No authorized rollout was part of C0G-51 evidence collection. Therefore this is a **live health snapshot**, not a claim that a new resource rollout was tested.
- The current event is an AWS Load Balancer Controller `FailedNetworkReconcile`, not a quota or scheduler `FailedCreate` event ([`raw/17-postvalidation-events.txt`](raw/17-postvalidation-events.txt)).

---

## 8. Acceptance criteria assessment

| Criterion | Result | Evidence / reason |
|---|---|---|
| Before/after reservation table | **PASS** | Section 4; [`raw/14-reservation-calculation.json`](raw/14-reservation-calculation.json) |
| Utilization ratio per node | **PASS** | Section 5; allocation and `kubectl top` raw outputs |
| Server-side dry-run or scheduling simulation | **PASS** | Deployment-only server dry-run exited 0 |
| Quota compatibility | **FAIL** | HPA maximum requires 8450m `limits.cpu`, exceeding the 8000m hard limit |
| Worst-case replica/HPA calculation | **PASS** | Section 4; three `2 → 3` HPAs and surge model |
| Estimated node-scale cost | **PASS** | Section 6; D3 verified price inputs |
| No Pod Pending after rollout | **PENDING** | Current snapshot has zero Pending Pods; no authorized rollout was run |
| Maintenance headroom conclusion | **FAIL for current 3-worker/quota configuration** | 3 workers have 145m HPA-max request headroom and quota blocks scale-up; 4 workers solve scheduler capacity but not quota admission |

---

## 9. Conclusion and next action

**Do not approve a D5 resource rollout as maintenance-safe yet.** The desired baseline is fully resourced, current Pods are healthy, and the rendered Deployments pass a server-side admission dry-run. However, the same desired configuration proves that the current `limits.cpu: 8` quota rejects the normal HPA maximum by 450m. The 3-worker cluster also has only 145m aggregate request CPU headroom at HPA maximum.

Minimum path to close the remaining criteria:

1. CDO04 approves a quota policy that covers HPA maximum, the permitted rollout surge, and an explicit maintenance margin; update `deploy/quota.yaml` only after that decision.
2. Ensure a fourth worker is available before maintenance; Karpenter's live `limits.cpu: 16` permits this, but it must be observed as Ready.
3. Perform the owner-approved rollout, then recapture quota, node allocation, HPA state, Pods, and events. Mark the no-Pending criterion PASS only when that post-rollout evidence is clean.
4. Security workstream links its Directive 5 admission-policy/ADR and invalid-manifest rejection proof; this report deliberately does not substitute a quota check for those policy controls.

---

## 10. Raw evidence index

| Artifact | Description |
|---|---|
| [`raw/00-collection-metadata.txt`](raw/00-collection-metadata.txt) | UTC, context, namespace, Git SHA, collector |
| [`raw/01-live-resourcequota-prevalidation.yaml`](raw/01-live-resourcequota-prevalidation.yaml) | Fresh quota hard/used values |
| [`raw/02-live-workloads-hpa-pdb-prevalidation.yaml`](raw/02-live-workloads-hpa-pdb-prevalidation.yaml) | Live desired/ready workloads, HPAs, PDBs |
| [`raw/03-live-pods-prevalidation.txt`](raw/03-live-pods-prevalidation.txt) / [`03b`](raw/03b-live-pods-all-namespaces-prevalidation.yaml) | Application placement and all-namespace reservation input |
| [`raw/04-live-nodes-prevalidation.yaml`](raw/04-live-nodes-prevalidation.yaml) | Node allocatable resources |
| [`raw/05-node-allocatable-and-allocated.txt`](raw/05-node-allocatable-and-allocated.txt) | Kubernetes per-node allocated-resource source |
| [`raw/06-node-observed-usage.txt`](raw/06-node-observed-usage.txt) | `kubectl top nodes` observed utilization |
| [`raw/07-live-karpenter-nodepool-nodeclaim.yaml`](raw/07-live-karpenter-nodepool-nodeclaim.yaml) | Live NodePool/NodeClaim, including CPU limit 16 |
| [`raw/08-live-events-prevalidation.txt`](raw/08-live-events-prevalidation.txt) | Pre-validation namespace events |
| [`raw/10-rendered-app-manifests.yaml`](raw/10-rendered-app-manifests.yaml) | CI-equivalent rendered desired state |
| [`raw/11-render-command.txt`](raw/11-render-command.txt) | Render command and result |
| [`raw/12b-server-side-dry-run-deployments.command.txt`](raw/12b-server-side-dry-run-deployments.command.txt) / [`stdout`](raw/12b-server-side-dry-run-deployments.stdout.txt) | Passing Deployment server-side dry-run |
| [`raw/13-calculate-reservations.py`](raw/13-calculate-reservations.py) | Reproducible calculation with assertions |
| [`raw/14-reservation-calculation.json`](raw/14-reservation-calculation.json) | Calculated reservations and ratios |
| [`raw/15-postvalidation-deployments.txt`](raw/15-postvalidation-deployments.txt)–[`19-postvalidation-collection-command.txt`](raw/19-postvalidation-collection-command.txt) | Post-dry-run health snapshot |
