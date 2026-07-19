# D18 / CDO-08 platform coordination request

**Requester/execution owner:** CDO-04

**Reviewer:** CDO-08

**Related task:** D18-COST-04

**Requested decision:** approve a time-bounded, metadata-only VPC Flow Log measurement

## Evidence motivating the request

- Seven-day Cost Explorer baseline: `39.0289095582 GB` NAT processing and `159`
  NAT Gateway hours for `[2026-07-12T00:00:00Z, 2026-07-19T00:00:00Z)`.
- Regional transfer baseline: `140.547 GB`, almost entirely `EC2 - Other`.
- `DescribeFlowLogs` returned no flow logs.
- Both private subnets route through one zonal NAT in `us-east-1a`.
- No VPC endpoints exist.

## Requested controlled measurement

Enable VPC Flow Logs for VPC `vpc-0a4e2abe9fbb70451` (or the two private subnets)
for seven complete UTC days. Capture metadata only; no packet payloads. The format
must support at least:

`version account-id interface-id srcaddr dstaddr srcport dstport protocol packets bytes start end action log-status flow-direction traffic-path pkt-src-aws-service pkt-dst-aws-service`

Preferred destination is an existing approved log analytics destination with explicit
retention. If none exists, CDO-08 must approve destination, IAM delivery role, KMS
requirements, access policy and retention before creation.

## Queries and output required

Produce bytes/GB grouped by:

1. source subnet/AZ and destination IP;
2. `pkt-dst-aws-service` for S3 and other identifiable AWS services;
3. NAT ENI `eni-0ae19ffaaa4ad0df9` traffic direction;
4. source ENI/pod/node to destination AZ for intra-VPC flows;
5. destination port and accepted/rejected status.

The output must contain the exact half-open UTC interval and distinguish complete
from partial log delivery.

## Guardrails / review points

- No payload collection.
- Do not expose operational endpoints publicly.
- Do not disable critical logs, metrics, traces or alerts.
- Do not change `flagd`.
- Define retention and deletion/lifecycle before enabling collection.
- Review IAM role, resource policy, KMS, log destination access and audit impact.
- Implement through Terraform/GitOps; no live patch as source of truth.
- Remove or retain the measurement configuration only through a reviewed Git record.

## Follow-on decision gate

After the seven-day query, CDO-04 will rank destinations by measured GB and propose
only endpoints whose avoided NAT/cross-AZ usage and operational benefit justify their
own footprint. S3/ECR/STS/Logs/SSM are opportunities, not approved implementations.

## Review record

- [ ] CDO-08 approves destination and retention.
- [ ] CDO-08 approves IAM/KMS/resource policies.
- [ ] CDO-08 approves endpoint-policy/private-DNS implications for any follow-on.
- [ ] CDO-04 records collection start/end UTC.
- [ ] CDO-04 publishes destination-ranked before evidence.
