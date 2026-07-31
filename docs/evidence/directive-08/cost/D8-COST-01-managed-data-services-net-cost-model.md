# D8-COST-01 — Managed Data Services Net Cost Model

## Status

`CONDITIONAL / INPUTS PENDING`

This deliverable is a formula-driven estimate, not actual billing. The current recommendation is the **HA recommended** scenario: RDS Multi-AZ, ElastiCache primary + replica/Multi-AZ, and a small three-broker MSK Provisioned cluster. The recommendation remains conditional until D8-PERF-01/02 provide same-window workload, throughput, retention, and post-cleanup node-hour evidence.

## Deliverable

Workbook: `outputs/d8-cost-01/D8-COST-01-managed-data-services-net-cost-model.xlsx`

The workbook contains:

- `Summary`: scenario comparison, net monthly impact, weekly total, budget headroom, and decision status.
- `Assumptions`: editable rates, usage drivers, ownership, and evidence status.
- `Before Baseline`: EKS/EBS/PVC baseline and removable-cost calculation.
- `Managed Options`: RDS Single-AZ/Multi-AZ, ElastiCache single/replica, and MSK Provisioned/Serverless comparisons.
- `Reconciliation`: Cost Explorer/CUR plan for before, cutover, post-cutover, and settled-month checks.
- `Sources & Checks`: source log, excluded costs, dependencies, and model controls.

## Key modeling decisions

1. Region is `us-east-1`; estimates use On-Demand rates, 168 hours/week, and 730 hours/month.
2. The Directive #8 guardrail is `$300/week` for the whole TF. This is distinct from the older `$300/month` Terraform budget evidence and is the controlling value for this task.
3. The current whole-TF run-rate uses the existing `$270.72/month` Cost Explorer MTD projection only as a proxy. It is not a settled bill.
4. Removed EKS node cost defaults to `$0`. Removing 170m CPU and 988 MiB of requested memory does not itself prove that a worker or NodeClaim disappears. The input may change only after post-cleanup evidence proves fewer node-hours.
5. The three self-hosted PVCs total 25 GiB gp2 and are modeled as removable after migration PASS and rollback-retention cleanup.
6. MSK throughput, serverless data processing, storage footprint, CloudWatch volume, and cross-AZ transfer are explicit placeholders pending D8-PERF-02.
7. Backup above included allowance, paid Performance Insights retention, CPU credits, KMS/Secrets API calls, NAT/VPC endpoint changes, DMS/NLB migration resources, discounts, credits, tax, and support are excluded until their triggers are known.

## Net-cost formula

```text
Net monthly impact
= RDS + ElastiCache + MSK
 + backup/storage/I-O/processing/monitoring/transfer/security
 - proven removed EKS node-hour cost
 - removed EBS/PVC cost
```

The whole-TF weekly projection is:

```text
(current TF monthly projection + net monthly impact) / (730 / 168)
```

Budget headroom is:

```text
$300/week - whole-TF weekly projection
```

## Acceptance criteria coverage

| Criterion | Status | Evidence |
|---|---|---|
| Before-cost baseline | PASS with runtime caveat | `Before Baseline`; manifest-backed reservations/PVCs, node saving conservative pending runtime proof |
| RDS options | PASS | Single-AZ and Multi-AZ rows |
| ElastiCache options | PASS | Single node and primary+replica/Multi-AZ rows |
| MSK comparison | PASS with input caveat | Provisioned and Serverless rows; throughput/retention placeholders visible |
| Net cost after removed EKS/EBS | PASS | Formula subtracts only proven/removable values; defaults node savings to zero |
| Weekly and monthly estimates | PASS | All scenarios calculate both periods |
| Budget delta/headroom | PASS | Whole-TF `$300/week` guardrail calculation |
| Excluded-cost list | PASS | `Sources & Checks` exclusions block |
| Estimate not called actual billing | PASS | Classification on Summary and source notes |
| Cost Explorer/CUR reconciliation plan | PASS | Dedicated `Reconciliation` sheet |

## Open dependencies before final approval

- D8-PERF-01: same-window PostgreSQL, Valkey, and Kafka workload baseline.
- D8-PERF-02: RDS capacity, cache footprint/request rate, Kafka partitions/throughput/retention, and post-cleanup EKS capacity evidence.
- CDO-08: final RDS, ElastiCache, and MSK service classes/topologies.
- Platform/Security: network path, KMS-key strategy, secret count, log settings, backup policy, and cross-AZ/NAT implications.
- Billing owner: Cost Explorer/CUR exports after billing latency and the first settled post-cutover month.
