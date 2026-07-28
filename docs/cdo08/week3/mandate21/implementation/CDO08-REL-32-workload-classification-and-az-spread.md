# CDO08-REL-32 Workload Classification And AZ Spread

**Task:** CDO08-REL-32
**Mandate:** MANDATE-21 - DR Failover
**Owner chinh:** Thuy
**Ngay quyet dinh:** 2026-07-28
**Inputs:** REL-28 revenue path scope, REL-29 runtime baseline/gap register, REL-31 MSK readiness evidence

## 1. Decision Summary

REL-32 khong scale tat ca workload 1 replica. Quyet dinh chi sua HA/topology/PDB cho workload co anh huong ro den customer SLO hoac order-data correctness/RPO.

| Workload | Classification | Current REL-29 baseline | Decision | Helm/GitOps action |
|---|---|---|---|---|
| `frontend-proxy` | Customer-SLO critical | 2/2, HPA min 2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `frontend` | Customer-SLO critical | 2/2, HPA min 2, PDB allowed 1, spread `1a/1b` | Khong doi cho REL32; runtime blocker xu ly ngoai task nay | None |
| `product-catalog` | Customer-SLO critical | 2/2, HPA min 2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `cart` | Customer-SLO critical | 2/2, HPA min 2, PDB allowed 1, nhung ca 2 pod o `us-east-1a` | Can harden topology spread | Change zone `topologySpreadConstraints.whenUnsatisfiable` to `DoNotSchedule` |
| `checkout` | Customer-SLO critical + MSK producer | 2/2, HPA min 2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `payment` | Customer-SLO critical | 2/2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `shipping` | Customer-SLO critical | 2/2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `currency` | Customer-SLO critical | 2/2, HPA min 2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `quote` | Customer-SLO critical | 2/2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `email` | Async notification | 2/2, PDB allowed 1, spread `1a/1b` | Khong doi | None |
| `accounting` | Data-correctness critical | 1/1, `Recreate`, no HPA/PDB/topology observed, pod in `1b` | Khong scale trong REL32; require drill evidence lag returns to 0 and no missing/duplicate confirmed order | None |
| `fraud-detection` | Data-correctness critical | 1/1, `Recreate`, no HPA/PDB/topology observed, pod in `1b` | Khong scale trong REL32; require drill evidence lag returns to 0 | None |
| `kafka-connect-orders-archive` | Archive/RPO supporting | 1/1, `tasks.max=1`, lag baseline 0 | Khong scale trong REL32; verify restart/rebalance catch-up in drill | None |
| `load-generator` | Drill tooling | 1/1, pod in `1b` | Khong scale de bao ve production SLO | None |
| `product-reviews`, `llm`, `recommendation`, `aiops`, `flagd` | Supporting/out of REL32 customer path | Mixed; product-reviews had readiness gap in REL29 | Out of scope for REL32 scale unless owner adds explicit drill scope | None |

## 2. Rationale

REL-28 defines the customer synchronous path as `frontend-proxy`, `frontend`, `product-catalog`, `cart`, `checkout`, `payment`, `shipping`, `currency`, and `quote`. REL-29 shows all of these already have at least two replicas and protection except `cart` placement: both ready `cart` pods were observed in `us-east-1a`. Because `cart` is on browse/cart/checkout, losing `us-east-1a` can remove all cart pods even though desired replicas is 2. REL32 therefore changes the cart zone spread from soft `ScheduleAnyway` to hard `DoNotSchedule`.

`accounting` and `fraud-detection` are data-correctness critical, not synchronous customer-serving pods. REL-31 shows MSK is ACTIVE across two AZs, every partition has replicas on both brokers, the app bootstrap secret contains both broker endpoints, consumer group lag was 0 at baseline, and Kafka offsets are replicated. The remaining acceptance point is not more replicas by default; it is drill evidence that after pod/AZ loss the consumers resume, lag returns to about 0 within the REL-28 catch-up target, and order reconciliation shows no missing confirmed order or duplicate business result.

`kafka-connect-orders-archive` supports archive/RPO evidence but the connector is configured with `tasks.max=1`. Adding a second worker would mostly provide standby/rebalance behavior, not parallel archive tasks, and would require expanding the chart template surface. REL31 already tracks `connect-orders-s3-archive` lag baseline as 0; REL35 must verify connector/task status and catch-up after restart or AZ loss.

`load-generator` is drill tooling. If it stops, evidence/load continuity is affected, but it is not a customer outage. It should remain 1 replica for production SLO posture unless the drill plan explicitly requires HA load generation or an external driver.

## 3. Required Implementation

Only `cart` needs a REL32 config change:

```yaml
components:
  cart:
    schedulingRules:
      topologySpreadConstraints:
        - topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
```

Existing `cart` controls retained:

| Control | Required state |
|---|---|
| Replicas/HPA | HPA enabled, `minReplicas: 2`, max 4 |
| PDB | enabled, `minAvailable: 1` |
| Host spread | hostname constraint `DoNotSchedule` |
| Zone spread | zone constraint changed to `DoNotSchedule` |

## 4. Validation Plan

Pre-merge:

- `helm lint techx-corp-chart`
- `helm template techx-corp techx-corp-chart -n techx-tf4 -f ../tf4-phase3-gitops-manifests/environments/production/app-values.yaml -f ../tf4-phase3-gitops-manifests/environments/production/image-revisions.yaml`
- Server-side dry-run when cluster access is available:
  `helm template ... | kubectl apply --server-side --dry-run=server -f -`

Local validation status on 2026-07-28:

| Check | Status | Note |
|---|---|---|
| Source/GitOps diff review | PASS | Only `cart` zone topology constraint changed from `ScheduleAnyway` to `DoNotSchedule` |
| `helm lint` | NOT RUN | Local shell does not have `helm` in PATH |
| `helm template` | NOT RUN | Local shell does not have `helm` in PATH |
| Server-side dry-run | NOT RUN | Requires Helm render output before piping to `kubectl` |

Post-sync:

- `kubectl -n techx-tf4 get deploy cart -o yaml` must show zone `whenUnsatisfiable: DoNotSchedule`.
- `kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=cart -o wide` must show ready cart pods across at least two AZs.
- `kubectl -n techx-tf4 get hpa cart` must keep min replicas >= 2.
- `kubectl -n techx-tf4 get pdb cart` must keep at least one available pod protected.

## 5. DoD Trace

| DoD item | REL32 answer |
|---|---|
| Every replica/HPA/topology/PDB change traces to classification | PASS: only `cart` topology changes, traced to customer-SLO critical classification and REL29-GAP-01 |
| No customer-SLO critical workload has only 1 available replica | PASS by REL29 baseline, with `cart` placement fixed by this change |
| Workload remaining 1 replica has clear reason/evidence | PASS: `accounting`, `fraud-detection`, `kafka-connect-orders-archive`, `load-generator` documented above |
| Live pod placement after sync spans at least 2 AZs for >=2 replicas | PENDING runtime sync validation |
