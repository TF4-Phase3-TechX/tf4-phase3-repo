# D18-COST-05 after read-only collection

**Collection window:** `2026-07-25T17:00Z`–`2026-07-25T17:02Z` for AWS inventory and
`2026-07-25T17:02Z` for Kubernetes metric queries.  
**Account / region:** `511825856493` / `us-east-1`; enabled-region scan covered all
17 enabled regions.  
**Access mode:** AWS CLI and `kubectl` read-only queries. No resource mutation,
raw event export, pod manifest, secret, or credential was collected.

## 1. Account-wide orphan after-scan

`us-east-1` now has 7 EBS volumes, all `in-use`, and 0 `available` volumes
(`0 GiB` available). There are 0 unassociated EIPs and 0 self-owned AMIs.
There are 4 self-owned snapshots in `us-east-1`; all other 16 enabled regions
returned 0 volumes, 0 snapshots, 0 unassociated EIPs, and 0 AMIs.

The four remaining snapshots are:

| Snapshot | Source volume | Logical source GiB | Decision signal |
|---|---|---:|---|
| `snap-0f827827d252cd8c2` | `vol-0024e483121338f0e` | 160 | retain / migration backup |
| `snap-0a6903e05af18a326` | `vol-0024e483121338f0e` | 40 | retain / migration backup |
| `snap-03ab92962492589ac` | `vol-0024e483121338f0e` | 8 | retain / recovery |
| `snap-0f1c39885a3145560` | `vol-0024e483121338f0e` | 8 | retain / recovery |

Snapshot count is `4` (baseline `9`), but logical source size is `216 GiB`
(baseline `76 GiB`) because the current migration backups are larger. This is
count reduction, not proof of snapshot-byte reduction.

## 2. EBS after inventory

All seven current volumes are `gp3`; the prior five `gp2` volumes and 35 GiB of
`available` EBS are gone. Current provisioned total is `290 GiB` versus the
baseline `205 GiB`, because the OpenSearch volume is now `160 GiB`. Therefore
the evidence supports `gp2 elimination` and `unattached-storage reduction`,
but not total provisioned-GiB reduction or right-sizing.

## 3. Matched NAT and log windows

Endpoint apply start: `2026-07-25T03:28:00Z`. A same-duration comparison was
made against the immediately preceding window:
`2026-07-24T13:54:07Z`–`2026-07-25T03:28:00Z` versus
`2026-07-25T03:28:00Z`–`2026-07-25T17:01:53Z` (13.53 hours each).

| Metric | Before | After | Delta | Interpretation |
|---|---:|---:|---:|---|
| NAT `BytesOutToDestination` | 79,063,981 bytes | 83,768,702 bytes | **+5.95%** | no matched-window reduction |
| EKS control-plane `IncomingBytes` | 25.982 GB | 24.703 GB | about **-4.9%** | partial window; not a settled daily result |

The previously documented `~61%` NAT daily-rate signal remains a non-matched
7-day-versus-12.7-hour comparison. It must not be promoted to a settled
reduction verdict until a complete post-change window is available.

VPC Flow Logs remain `ACTIVE` with `DeliverLogsStatus=SUCCESS`, created at
`2026-07-25T03:28:08Z`, retention 7 days. The flow-log group currently reports
`storedBytes=0`; there is not yet a seven-day destination or cross-AZ dataset.

## 4. Observability after snapshot

Prometheus was queried through the running server container using metric-only
queries at approximately `2026-07-25T17:02Z`:

| Query | Value | Baseline comparison |
|---|---:|---|
| `prometheus_tsdb_head_series` | `208,592` | higher than baseline `179,044` |
| `rate(prometheus_tsdb_head_samples_appended_total[5m])` | `33,287.225/s` | higher than baseline `3,535.45/s` |
| `prometheus_tsdb_storage_blocks_bytes` | `4,801,665,869` bytes (`4.802 GB`) | higher than baseline `3.521 GB` |
| `rate(jaeger_spans_received_total[5m])` | empty result | `NOT_EXPOSED` |

The Prometheus after snapshot is not a reduction result; the series, sample
rate, and blocks are higher than baseline. Grafana dashboard export and a
matched Jaeger lookup were not available in this collection.

## 5. Validation still required

No dedicated post-endpoint Browse → Cart → Checkout Locust/smoke run was
executed during this read-only collection. Storefront pods were Running, but
that does not provide success rate, error rate, p95, or p99. A complete
post-change SLO run, a seven-day NAT/Flow Logs window, and owner/expiry
decisions for retained snapshots are still required for PASS.
