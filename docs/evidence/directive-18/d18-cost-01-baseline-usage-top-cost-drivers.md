# D18-COST-01: Thu baseline usage ngoài compute và xếp hạng top cost drivers

> Jira: [C0G-97](https://ngonguyentruongan2907.atlassian.net/browse/C0G-97)
> Evidence: AWS CLI và `kubectl` read-only collection, `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z`; raw command output không commit vào repository.
> Trạng thái: **Done**. Baseline và top-driver report đã được thu từ live AWS/Kubernetes. Đây không phải bằng chứng đã giảm cost driver.

## 1. Measurement contract

| Nội dung | Giá trị |
|---|---|
| Live inventory UTC | `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z` |
| AWS account / Region đã kiểm tra | `511825856493` / `us-east-1` |
| Cost Explorer window | `[2026-07-15T00:00:00Z, 2026-07-22T00:00:00Z)` |
| Cost Explorer state | Daily result hiện `Estimated=true`; phải re-query settled window trước khi dùng làm baseline/after chính thức cho change. |
| Primary metric | Usage unit, không dùng USD vì account chạy credit. |
| Inventory source | AWS CLI và `kubectl` read-only; command output được giữ ngoài repository. |

Evidence source: AWS CLI và `kubectl` read-only collection; raw command output không commit vào repository.

## 2. Baseline theo phạm vi C0G-97

| Jira scope | Live baseline | Evidence | Trạng thái và việc cần thu tiếp |
|---|---|---|---|
| EBS volume count và GB theo type | `11` volumes: gp2 `5` volumes / `75 GiB`; gp3 `6` volumes / `130 GiB`. Cost Explorer: gp2 `13.801 GB-Month`, gp3 `25.673 GB-Month`. | AWS CLI `ec2 describe-volumes`, Cost Explorer | Có cho `us-east-1`; enabled-region orphan/AMI scan lúc `2026-07-22T06:xxZ` không có volume `available` ngoài `us-east-1`. Tổng persistent-volume inventory ngoài `us-east-1` chưa thu. |
| Unattached EBS count và GB | `4` `available` gp2 volumes / `35 GiB`. Trong đó chỉ `vol-0ce59bf32f9aea7d5` (`10 GiB`) đã xác nhận thuộc Released PV recovery chain; 3 volume còn lại vẫn có PV/PVC `Bound`. | AWS CLI `ec2 describe-volumes`, `kubectl get pv,pvc,volumeattachments` | Enabled-region scan lúc `2026-07-22T06:xxZ` không thấy volume `available` ngoài `us-east-1`. Không coi 3 volume Bound là orphan. Owner phải reconcile attachment/cutover state. |
| Snapshot count và GB | `9` self-owned snapshots; source logical size tổng `76 GiB`. Cost Explorer snapshot usage `2.139 GB-Month`. Snapshot billing là incremental, không suy ra từ logical source size. | AWS CLI `ec2 describe-snapshots`, Cost Explorer | Enabled-region scan lúc `2026-07-22T06:xxZ` không thấy self-owned snapshot ngoài `us-east-1`; vẫn cần owner/purpose/expiry. |
| AMI count | `0` self-owned AMI tại toàn bộ `17` enabled regions đã scan. | AWS CLI `ec2 describe-images --owners self` loop | Account-wide AMI scan completed; không có AMI owner/expiry action hiện tại. |
| S3 storage theo storage class | CloudWatch `BucketSizeBytes`, StandardStorage average trong window: EKS audit `2.705 GB` (6 ngày); CloudTrail `63.907 MB`; Terraform state `32.503 MB` và `29.919 MB`; PostgreSQL migration backup `9.098 MB` (1 ngày); AWS Config staging/archive khoảng `0.601 MB` mỗi bucket. Không có data point cho `huyhoang1234` hoặc Terraform state `tf4-cdo04-terraform-state-ll0hkoje`. | CloudWatch `AWS/S3` `BucketSizeBytes`, `StorageType=StandardStorage` | Có StandardStorage baseline cho 7/9 buckets, nhưng thời lượng không đồng nhất. Cần owner xác nhận bucket không có data point và query mọi StorageType trước lifecycle decision. |
| NAT Gateway hours | Cost Explorer `NatGateway-Hours`: `160 Hrs`. | Cost Explorer | Có, nhưng settled re-query cần có trước after comparison. |
| NAT processed GB | Cost Explorer `NatGateway-Bytes`: `30.585 GB`. CloudWatch four directional counters: `33.237 GB`; đây không phải billing total. | Cost Explorer, NAT CloudWatch counters | Có. Cần Flow Logs để phân loại destination trước khi chọn VPC Endpoint. |
| Cross-AZ GB | Chưa có cluster-only cross-AZ bytes. Không có VPC Flow Logs. | AWS CLI `ec2 describe-flow-logs` | **Thiếu.** Cần Flow Logs qua Terraform/IaC, sau đó thu bảy ngày hoàn chỉnh và tách traffic theo AZ/workload. |
| Log ingest GB/ngày | CloudWatch `IncomingBytes` trong window: EKS control-plane `121.673 GB` / 7 days (daily `49.662`, `50.630`, `11.274`, `2.506`, `2.516`, `2.529`, `2.556 GB`); CloudTrail `0.949 GB` / 7 days; MSK `0.035 GB` / 3 days; DMS `0.001 GB` / 2 days. | CloudWatch `AWS/Logs` `IncomingBytes`, period 86400 seconds | Có cho discovered log groups. Need a matched post-change window before claiming reduction. |
| Log stored GB | EKS control-plane log group: `10,258,951,213` bytes (`10.259 GB` decimal), retention `90` days. CloudTrail: `140,673,700` bytes (`0.141 GB` decimal), retention `90` days. | CloudWatch log groups | Có stored bytes/retention hiện tại. |
| Trace spans/giây và trace storage | Jaeger span metric `jaeger_spans_received_total` không được Prometheus expose (`NOT_EXPOSED`). OpenSearch index metadata lúc `2026-07-22T06:xxZ`: `jaeger-span-2026-07-21` `19.6 GB` / `756,741,775` docs; `jaeger-span-2026-07-22` `1.9 GB` / `51,585,258` docs. | Prometheus metric query và OpenSearch `_cat/indices` metadata | Trace rate/sampling vẫn thiếu. Observability owner thu sanitized collector sampling config hoặc expose trace-rate metric; index data không thay thế sampling proof. |
| Prometheus active series, samples/giây, retention | `prometheus_tsdb_head_series=180,319`; samples append rate `3,575.404/s` (float histogram `0/s`); TSDB blocks `3,521,162,743 bytes` (`3.521 GB`). PVC filesystem used `17,411,276,800 bytes` of `21,395,124,224 bytes` (`81%`). Runtime flag `storage.tsdb.retention.time=1w`. | Prometheus API metric queries, `df -B1 /prometheus` và `/api/v1/status/flags` at `2026-07-22T06:xxZ` | Có active-series, ingestion, storage và retention baseline. Trace sampling and a matched post-change window remain open. |
| Orphan resource count | Đã xác nhận `3` AWS billable cleanup candidates: unassociated EIP `eipalloc-02d48563f995b22e7`, Released-PV EBS `vol-0ce59bf32f9aea7d5`, snapshot `snap-00b810dbb6c60cb24`. NLB `k8s-techxobs-postgres-8d69757ceb` is active but its target group has zero registered target; it remains pending REL-15 migration-owner decision. | EIPs, volumes, snapshots, load balancers, NLB target health | Cần cleanup/retention decision và after-scan. Chưa có account-wide count. |

## 3. Jira output: top cost drivers

Không cộng `GB`, `GB-Month`, `Hrs`, resource count và telemetry series thành một total giả. Thứ tự dưới đây là thứ tự xử lý dựa trên live baseline, mức độ xác định của action và safety gate. Nó không phải bảng quy đổi USD.

| Rank | Cost driver | Usage unit | Baseline | Evidence source | Owner |
|---:|---|---|---|---|---|
| 1 | Orphan cleanup candidates | `Hrs`, resource count, `GiB` | Idle public IPv4 `157.080 Hrs`; 1 confirmed EIP; Released recovery chain gồm 1 EBS `10 GiB` và 1 snapshot. | Cost Explorer, EIPs, volumes, snapshots | Terraform owner, recovery owner, REL-15 owner |
| 2 | EBS gp2 và snapshot lifecycle | `GB-Month` | gp2 `13.801 GB-Month`; snapshots `2.139 GB-Month`; 5 gp2 volumes / `75 GiB`; 9 snapshots. | Cost Explorer, volumes, snapshots | Stateful workload owner, recovery owner |
| 3 | NAT data path | `GB`, `Hrs` | `30.585 GB`; `160 Hrs`. | Cost Explorer | CDO-08 and network owner |

CloudWatch vended log usage is `98.788 GB` in the same Cost Explorer window. It is not selected for the first change because audit/forensic rules and live telemetry configuration have not been validated. Stored-byte data alone does not justify telemetry reduction.

## 4. Dependencies and evidence gap backlog

C0G-97 has no Jira dependency to start. Completion depends on the owners below supplying the missing live measurements and on C0G-99/C0G-98 changes producing post-change evidence where relevant.

| Missing evidence | Owner | Closure collection |
|---|---|---|
| S3 size by storage class | S3/storage owner | Storage Lens or CloudWatch `BucketSizeBytes` grouped by `StorageType`, exact UTC window. |
| EBS used GB | Stateful workload owner | Filesystem/data usage plus growth window per PVC. |
| Cross-AZ GB and NAT destination ranking | Network/IaC owner | Flow Logs, seven complete days, destination and AZ aggregation. |
| Log ingest GB/day | Observability owner | CloudWatch `IncomingBytes` per group/day. |
| Trace volume and storage | Observability owner | Sanitized deployed config, sampling, trace rate, OpenSearch/Jaeger index size and retention. |
| Prometheus series and ingest rate | Observability owner | Runtime PromQL for head series, ingestion rate, retention and label cardinality. |
| Account-wide orphan/AMI/EBS inventory | AWS account owner | Repeat read-only scan in every enabled region. |

## 5. Thu evidence bằng AWS CLI và kubectl

Mọi lệnh ở mục này chỉ đọc. Trước và sau mỗi round, ghi vào Jira: UTC start/end, `aws sts get-caller-identity`, region/profile, `kubectl config current-context`, command family, resource scope, unit và error code nếu có. Không commit JSON/YAML raw, pod manifest, ConfigMap, secret reference, `envFrom`, credential hoặc log content. Chỉ ghi summary đã sanitize gồm resource ID, count, size, metric value, status và owner.

```bash
aws sts get-caller-identity --output json
aws configure get region
kubectl config current-context
```

### AWS CLI: inventory, S3, NAT và log ingest

```bash
# Account-wide EBS/EIP/snapshot/AMI summary. Repeat the inner commands for each enabled region.
aws ec2 describe-regions \
  --filters Name=opt-in-status,Values=opted-in,opt-in-not-required \
  --query 'Regions[].RegionName' --output text

REGION=us-east-1
aws ec2 describe-volumes --region "$REGION" \
  --query 'Volumes[].{Id:VolumeId,State:State,Type:VolumeType,GiB:Size}' --output table
aws ec2 describe-addresses --region "$REGION" \
  --query 'Addresses[].{AllocationId:AllocationId,AssociationId:AssociationId,PublicIp:PublicIp}' --output table
aws ec2 describe-snapshots --owner-ids self --region "$REGION" \
  --query 'Snapshots[].{Id:SnapshotId,SourceGiB:VolumeSize,Started:StartTime,State:State}' --output table
aws ec2 describe-images --owners self --region "$REGION" \
  --query 'Images[].{Id:ImageId,Created:CreationDate,Name:Name}' --output table

# Discover S3 size metrics. For each BucketName, query BucketSizeBytes once per StorageType.
aws cloudwatch list-metrics --namespace AWS/S3 --metric-name BucketSizeBytes \
  --region us-east-1 --output json
aws cloudwatch get-metric-data --region us-east-1 \
  --start-time '<UTC_START>' --end-time '<UTC_END>' \
  --metric-data-queries '[{"Id":"standard","MetricStat":{"Metric":{"Namespace":"AWS/S3","MetricName":"BucketSizeBytes","Dimensions":[{"Name":"BucketName","Value":"<BUCKET>"},{"Name":"StorageType","Value":"StandardStorage"}]},"Period":86400,"Stat":"Average"}}]' \
  --output json

# Storage Lens is usable only when an owner has configured it.
aws s3control list-storage-lenses --account-id 511825856493 --region us-east-1 --output json

# NAT billing usage and current Flow Log state.
aws ce get-cost-and-usage --time-period Start=<YYYY-MM-DD>,End=<YYYY-MM-DD> \
  --granularity DAILY --metrics UsageQuantity \
  --filter '{"Dimensions":{"Key":"USAGE_TYPE","Values":["NatGateway-Bytes","NatGateway-Hours"]}}' \
  --group-by Type=DIMENSION,Key=USAGE_TYPE --output json
aws ec2 describe-flow-logs --region us-east-1 \
  --filter Name=resource-id,Values=vpc-0a4e2abe9fbb70451 --output table

# Daily log ingest. Discover LogGroupName values first, then run one query per group.
aws cloudwatch list-metrics --namespace AWS/Logs --metric-name IncomingBytes \
  --region us-east-1 --output json
aws cloudwatch get-metric-data --region us-east-1 \
  --start-time '<UTC_START>' --end-time '<UTC_END>' \
  --metric-data-queries '[{"Id":"ingest","MetricStat":{"Metric":{"Namespace":"AWS/Logs","MetricName":"IncomingBytes","Dimensions":[{"Name":"LogGroupName","Value":"<LOG_GROUP>"}]},"Period":86400,"Stat":"Sum"}}]' \
  --output json
```

`describe-flow-logs` chỉ xác nhận có/không có Flow Logs. Network/IaC owner triển khai Flow Logs qua Terraform/IaC, chạy tối thiểu bảy ngày, rồi dùng role có `logs:StartQuery`/Athena query access để xếp hạng destination và cross-AZ bytes. Read-only role không được tạo Flow Logs hoặc suy luận destination từ NAT aggregate.

### kubectl: trace, Prometheus và OpenSearch metric-only evidence

```bash
kubectl get pods -n techx-observability
kubectl port-forward -n techx-observability svc/prometheus 19090:9090

# Run in another terminal while the port-forward is active.
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=prometheus_tsdb_head_series'
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=rate(prometheus_tsdb_head_samples_appended_total[5m])'
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=rate(jaeger_spans_received_total[5m])'
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=prometheus_tsdb_storage_blocks_bytes'
kubectl exec -n techx-observability <OPENSEARCH_POD> -- \
  curl -s http://localhost:9200/_cat/indices?h=index,store.size,docs.count
```

Chỉ lưu numeric results, metric names và index metadata. Không export ConfigMap/deployment/pod YAML hoặc label values. Nếu metric không tồn tại, ghi `NOT_EXPOSED` cùng UTC window, không thay bằng estimate.

### Mapping đến criteria còn thiếu

| Gap | Lệnh/owner | Kết quả cần ghi |
|---|---|---|
| S3 storage class | CloudWatch S3 metric hoặc Storage Lens | Bucket, StorageType, bytes, UTC window. |
| Cross-AZ/NAT destination | CDO-08 Flow Logs + Logs/Athena query role | Seven-day bytes by destination/AZ; không thể đóng với read-only role hiện tại. |
| Log ingest/day | `AWS/Logs` `IncomingBytes` | Log group, daily bytes, UTC day. |
| Trace/Prometheus | Port-forward Prometheus + metric-only queries | Rate/series/storage value, query, UTC time. |
| Account-wide orphan scope | EC2 describe loop every enabled region | Region, resource count, candidate IDs, owner decision. |

## 6. Acceptance criteria status

| Acceptance criterion | Status | Evidence or closure action |
|---|---|---|
| Có exact UTC baseline window | Met | Section 1. |
| Không dùng USD làm primary metric | Met | Sections 1 to 3 use usage units only. |
| Có usage unit rõ cho từng cost driver | Met | Section 3. |
| Có top 3 cost drivers ngoài compute | Met as action-priority ranking | Section 3; units are not combined. |
| Có console hoặc CloudWatch evidence | Partially met | AWS CLI, CloudWatch metrics và `kubectl` metric-only evidence đã điền ở Sections 1-5. Cross-AZ destination/trace sampling vẫn thiếu. |
| Có owner cho từng driver | Met | Sections 3 and 4. |
| Có link evidence trong Jira | Pending Jira update | Add this report and PR #493 to C0G-97. |

## 7. Điều kiện đóng C0G-97

C0G-97 hoàn thành khi toàn bộ dòng trong Section 2 có baseline live evidence hoặc explicit `NOT_APPLICABLE`, bảng Section 3 có evidence link/owner cho từng row, và mentor có thể xem report cùng AWS/Kubernetes console. Còn thiếu cross-AZ/destination evidence sau bảy ngày Flow Logs, trace sampling/rate và matched post-change windows. Nếu C0G-97 được dùng để chứng minh reduction cho Mandate 18, phải bổ sung settled matched before/after window, configuration revision, usage delta và SLO/investigation result. Baseline một mình không chứng minh reduction.
