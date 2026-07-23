# D18-COST-04 — NAT Gateway and cross-AZ data-transfer baseline

**Owner:** CDO-04

**Reviewer/notify:** CDO-08

**Status:** Partial — usage baseline complete; destination attribution blocked by absent Flow Logs

**Region:** `us-east-1`

**Account:** `511825856493`

## 1. Measurement contract

Two windows are used because CloudWatch supports exact timestamps while Cost Explorer
uses UTC calendar days and can report the latest day as estimated/incomplete.

| Source | Exact UTC window | Scope | Caveat |
|---|---|---|---|
| CloudWatch `AWS/NATGateway` | `[2026-07-12T06:00:00Z, 2026-07-19T06:00:00Z)` | `nat-0f57f14c4e6039bf4` | Exact completed seven-day NAT counter window |
| Cost Explorer | `[2026-07-12T00:00:00Z, 2026-07-19T00:00:00Z)` | Account, `us-east-1` usage types | Results were `Estimated=true`; 2026-07-18 contained 15 NAT hours at collection time |
| AWS/Kubernetes configuration snapshot | `2026-07-19T06:44:53Z` | TF4 VPC, ALB and current EKS context | Point-in-time placement/configuration evidence |

Collection identity was the read-only SSO role
`AWSReservedSSO_TF4-CostPerfReadOnlyAlerting`; no credentials are stored in this package.

## 2. NAT usage baseline

The VPC has one public, zonal NAT Gateway in `us-east-1a`:

- NAT: `nat-0f57f14c4e6039bf4`
- VPC: `vpc-0a4e2abe9fbb70451`
- subnet: `subnet-023018dac76fc69f3`
- created: `2026-07-07T09:03:49Z`
- both private subnets use route table `rtb-03b6b2cb0144ce3bb`, whose default
  route points to this NAT.

### CloudWatch, exact seven-day window

| Metric (Sum) | Bytes | Decimal GB | GiB |
|---|---:|---:|---:|
| `BytesInFromSource` / `BytesOutToDestination` | 1,980,695,329 | 1.9807 | 1.8446 |
| `BytesInFromDestination` / `BytesOutToSource` | 42,757,236,700 | 42.7572 | 39.8208 |
| Billable processed-byte proxy: ingress on both sides | 44,737,932,029 | **44.7379** | **41.6654** |

`PacketsDropCount=0` and `ErrorPortAllocation=0`. Maximum active connections were
`299`. The traffic is strongly download-heavy: destination-to-source bytes are about
21.59 times source-to-destination bytes.

### Cost Explorer, UTC calendar-day window

| Usage type | Total |
|---|---:|
| `NatGateway-Hours` | **159 hours** |
| `NatGateway-Bytes` | **39.0289095582 GB** |

The CloudWatch and Cost Explorer totals must not be expected to match: their windows
differ and the final Cost Explorer day was incomplete/estimated. USD is intentionally
not used as the primary result.

## 3. Cross-AZ baseline

Cost Explorer reported `DataTransfer-Regional-Bytes = 140.547 GB` for the account-wide
UTC calendar-day window.

| Service attribution | GB |
|---|---:|
| `EC2 - Other` | **140.5467992931** |
| `Amazon Elastic Load Balancing` | **0.0000597564** |
| `AWS Data Transfer` | 0 |

This is a real usage baseline, but it is account-wide and not resource-ID attributable.
It must not be presented as 140.547 GB generated exclusively by EKS. The near-total
`EC2 - Other` attribution and the single-AZ NAT design make two paths high-priority
hypotheses: pod/node traffic between AZs, and `us-east-1b` egress crossing to the NAT
in `us-east-1a`. Flow Logs are required to split those paths quantitatively.

## 4. Placement and load-balancer findings

- Four ready nodes: two in `us-east-1a` and two in `us-east-1b`.
- Pod CIDRs observed as `10.0.10.x` in `us-east-1a` and `10.0.11.x` in
  `us-east-1b`.
- The internet-facing ALB spans both public subnets and targets pod IPs.
- `frontend-proxy` has two replicas, one in each AZ at the snapshot.
- Critical two-replica services are often distributed across hosts/AZs at runtime,
  but their declared topology spread key is `kubernetes.io/hostname`, not
  `topology.kubernetes.io/zone`.
- Most singleton services have no zone-aware placement. Stateful dependencies
  PostgreSQL, Kafka and Valkey were all in `us-east-1a`; callers exist in both AZs.
- ClusterIP services default to `internalTrafficPolicy: Cluster`, so a request may
  select a remote-AZ endpoint even where a local replica exists.
- The OTel collector service is the exception: `internalTrafficPolicy: Local`.

Reliability guardrail: do not force all workloads into the NAT AZ and do not reduce
replicas merely to avoid cross-AZ bytes.

## 5. Traffic matrix

`Unknown` means the path exists or is plausible from configuration but cannot be
assigned GB without flow-level evidence.

| Source | Destination | Baseline GB | NAT | Cross-AZ | Necessary | Optimization |
|---|---|---:|---|---|---|---|
| Private subnets | Internet/AWS public endpoints, aggregate | 39.0289 CE; 44.7379 CW-window proxy | Yes | For `us-east-1b` via NAT in 1a | Mixed | Attribute with Flow Logs; retain genuine external egress |
| Nodes/pods | S3 | Unknown | Yes today | Possible from 1b | Necessary service, avoidable NAT | S3 Gateway Endpoint after policy/route review |
| Nodes/pods | ECR API + ECR registry/S3 layers | Unknown | Yes today | Possible from 1b | Necessary, avoidable NAT | Interface endpoints `ecr.api`, `ecr.dkr` plus S3 gateway |
| Controllers/workloads | STS | Unknown | Yes today | Possible from 1b | Necessary, avoidable NAT | Regional STS plus interface endpoint |
| Nodes/agents | CloudWatch Logs | Unknown | Yes today | Possible from 1b | Necessary logging, avoidable NAT | Interface endpoint `logs`; do not disable logs |
| Managed-node operations | SSM family | Unknown | Yes if used | Possible from 1b | Necessary when used | Evaluate `ssm`, `ssmmessages`, `ec2messages` endpoints |
| ALB, both AZs | `frontend-proxy` pod IPs | ELB regional: 0.0000598 | No | Possible | Necessary | Preserve two-AZ ingress; validate target-group AZ behavior before changing |
| Pod in one AZ | ClusterIP endpoint in other AZ | Included only in 140.547 account aggregate | No | Yes | Mixed | Zone spread plus local-first routing only after SLO/failover test |
| Services | Genuine third-party APIs | Unknown | Yes | Possible from 1b | Necessary | Keep NAT; add allow-list/proxy/cache only where application semantics permit |
| Load generator | Storefront | Unknown | Depends on resolved public path | Possible | Test-only | Keep disabled outside explicit test windows; use private service path for internal tests |

## 6. Necessary versus avoidable

**Necessary:** public storefront ingress; real third-party API egress; inter-AZ traffic
required for failover or a singleton stateful dependency until that dependency is
safely redesigned; critical AWS telemetry/audit traffic.

**Avoidable candidates:** AWS-service traffic sent through NAT; 1b-to-1a NAT hairpin;
remote endpoint selection when healthy local replicas exist; internal load generation
through the public ALB; image pulls repeated because of churn or ineffective node
caching. Candidate does not mean approved change.

## 7. VPC Endpoint opportunities, ordered

1. **S3 Gateway Endpoint** — prerequisite for ECR layer downloads and common S3
   traffic; no private DNS change, but it changes private route tables and requires
   endpoint-policy review.
2. **ECR `api` and `dkr` Interface Endpoints** — removes registry/API NAT traffic;
   pair with S3 gateway.
3. **STS Interface Endpoint** — use regional STS endpoints and verify SDK behavior.
4. **CloudWatch Logs Interface Endpoint** — retain all critical logging while moving
   transport off NAT.
5. **SSM endpoint set** — deploy only if measured/operational use justifies the
   per-AZ endpoint footprint.

All endpoint work touches shared networking, security groups, endpoint policies and/or
private DNS. CDO-08 review is therefore mandatory. No endpoint is deployed by this task.

## 8. Topology proposal without reducing reliability

1. Add a second spread constraint on `topology.kubernetes.io/zone` with
   `maxSkew: 1` for replicated revenue-path workloads; retain hostname spread.
2. Keep the ALB and revenue-path replicas in both AZs.
3. Measure before considering `internalTrafficPolicy: Local`. Local routing needs at
   least one ready endpoint per AZ, readiness-aware rollout, and failure/SLO tests;
   otherwise it can create black holes or overload.
4. For chatty service pairs, use zone-aware hints/locality only after confirming the
   caller and callee both have adequate per-AZ capacity.
5. Do not solve the single NAT cross-AZ path by pinning all pods to `us-east-1a`.
   First remove AWS-service bytes with endpoints; then compare residual egress with
   the reliability and hourly footprint of a NAT per AZ.

## 9. Evidence gap and decision

`DescribeFlowLogs` returned an empty list and `DescribeVpcEndpoints` returned an empty
list. Consequently, no defensible top-destination ranking, destination-level GB split,
or cluster-only cross-AZ split can be produced from current telemetry. Cost Explorer
groups NAT bytes under `EC2 - Other`, not destination service.

The correct next action is a time-bounded VPC Flow Log collection reviewed by CDO-08,
not immediate endpoint deployment based on guesses. See
`D18-CDO08-request-platform-coordination.md` in this directory.

## 10. Acceptance status

- [x] NAT usage baseline.
- [ ] Top NAT destinations — blocked by absent Flow Logs/query logs.
- [x] Cross-AZ usage baseline — account-wide baseline; resource attribution remains a gap.
- [x] Necessary and avoidable traffic classification.
- [x] VPC Endpoint opportunity list.
- [x] Topology proposal that preserves reliability.
- [x] Evidence sources and exact UTC windows.

Dependency `D18-COST-01` was not present in the repository at collection time. This
package therefore records its own measurement contract and must be reconciled with
the D18-COST-01 canonical baseline before sign-off.

## 11. Screenshot evidence commands

Run these in PowerShell with the terminal maximized. Each block prints the UTC
window before the result so the timestamp and measurement are visible in one image.
Do not display or capture `C:\Users\ASUS\.aws\credentials`.

### NAT Gateway identity and route

```powershell
$env:AWS_PROFILE = '511825856493_TF4-CostPerfReadOnlyAlerting'
$env:AWS_REGION = 'us-east-1'
Write-Host 'SNAPSHOT UTC:' ([DateTimeOffset]::UtcNow.ToString('u'))
aws ec2 describe-nat-gateways --nat-gateway-ids nat-0f57f14c4e6039bf4 `
  --query 'NatGateways[0].{NatGatewayId:NatGatewayId,State:State,SubnetId:SubnetId,VpcId:VpcId,Created:CreateTime}' `
  --output table
aws ec2 describe-route-tables --route-table-ids rtb-03b6b2cb0144ce3bb `
  --query 'RouteTables[0].{Associations:Associations[].SubnetId,Routes:Routes[].{Destination:DestinationCidrBlock,NAT:NatGatewayId}}' `
  --output json
```

Capture filename: `01-nat-and-private-routes.png`.

### Seven-day NAT CloudWatch counters

```powershell
$env:AWS_PROFILE = '511825856493_TF4-CostPerfReadOnlyAlerting'
$start = '2026-07-12T06:00:00Z'
$end = '2026-07-19T06:00:00Z'
Write-Host "EXACT UTC WINDOW: [$start, $end)"
foreach ($metric in 'BytesInFromSource','BytesInFromDestination','PacketsDropCount','ErrorPortAllocation') {
  aws cloudwatch get-metric-statistics --region us-east-1 `
    --namespace AWS/NATGateway --metric-name $metric `
    --dimensions Name=NatGatewayId,Value=nat-0f57f14c4e6039bf4 `
    --start-time $start --end-time $end --period 604800 `
    --statistics Sum Maximum --output table
}
```

Capture filename: `02-nat-cloudwatch-7d.png`.

### Cost Explorer NAT and regional-transfer baseline

```powershell
$env:AWS_PROFILE = '511825856493_TF4-CostPerfReadOnlyAlerting'
Write-Host 'EXACT UTC WINDOW: [2026-07-12T00:00:00Z, 2026-07-19T00:00:00Z)'
aws ce get-cost-and-usage `
  --time-period Start=2026-07-12,End=2026-07-19 `
  --granularity DAILY --metrics UsageQuantity `
  --group-by Type=DIMENSION,Key=USAGE_TYPE --output table `
  --query "ResultsByTime[].{Date:TimePeriod.Start,Estimated:Estimated,Usage:Groups[?contains(Keys[0], 'NatGateway') || contains(Keys[0], 'DataTransfer-Regional')].{Type:Keys[0],Quantity:Metrics.UsageQuantity.Amount,Unit:Metrics.UsageQuantity.Unit}}"
```

Capture filename: `03-ce-nat-regional-transfer-7d.png`.

### Missing Flow Logs and VPC Endpoints

```powershell
$env:AWS_PROFILE = '511825856493_TF4-CostPerfReadOnlyAlerting'
Write-Host 'SNAPSHOT UTC:' ([DateTimeOffset]::UtcNow.ToString('u'))
aws ec2 describe-flow-logs --region us-east-1 --output table
aws ec2 describe-vpc-endpoints --region us-east-1 `
  --filters Name=vpc-id,Values=vpc-0a4e2abe9fbb70451 --output table
```

Capture filename: `04-flowlogs-endpoints-gap.png`.

### Kubernetes node/AZ and workload placement

```powershell
Write-Host 'SNAPSHOT UTC:' ([DateTimeOffset]::UtcNow.ToString('u'))
kubectl get nodes -L topology.kubernetes.io/zone -o wide
kubectl get pods -n techx-tf4 -o wide --sort-by=.spec.nodeName
kubectl get ingress -n techx-tf4 techx-alb-ingress -o wide
```

Capture filename: `05-kubernetes-az-placement.png`.

Store approved screenshots under
`docs/evidence/directive-18/D18-COST-04-nat-cross-az-analysis/screenshots/` and add
their SHA-256 hashes to this README before final sign-off. Screenshots are not added
by this change because no screenshots were supplied and credentials/account details
must be reviewed before publishing images.

## 12. Submission comment

**Đã làm gì?**

Đã đo NAT Gateway hours/processed GB và regional cross-AZ GB; phân tích route,
ALB, pod/node/AZ placement; lập traffic matrix, danh sách VPC Endpoint opportunities
và đề xuất topology không giảm reliability.

**Kiểm chứng bằng cách nào?**

Đối chiếu CloudWatch `AWS/NATGateway`, Cost Explorer usage type, AWS EC2/ELB read-only
API và snapshot Kubernetes trong các cửa sổ UTC ghi tại mục 1. Collector có thể chạy
lại bằng `scripts/d18-cost-04-collect-readonly.ps1`.

**Evidence nằm ở đâu?**

README này, file phối hợp CDO-08 cùng thư mục và PR GitHub của branch D18-COST-04.
Thay câu cuối bằng URL GitHub cụ thể sau khi PR được tạo.
