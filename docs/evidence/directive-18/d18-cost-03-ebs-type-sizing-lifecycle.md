# D18-COST-03: Tối ưu EBS type, volume sizing và storage lifecycle

> Jira: [C0G-99](https://ngonguyentruongan2907.atlassian.net/browse/C0G-99)
> Evidence: AWS CLI và `kubectl` read-only collection, `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z`; raw command output không commit vào repository.
> Trạng thái: **Done**. Report đã thu baseline live AWS/Kubernetes và đối chiếu Scope/Acceptance Criteria của C0G-99. Chưa có gp2 migration, right-sizing hoặc lifecycle change được xác nhận hoàn tất.

## 1. Measurement contract và dependency

| Nội dung | Giá trị |
|---|---|
| Live inventory UTC | `2026-07-22T04:19:53Z` đến `2026-07-22T04:21:07Z` |
| AWS account / Region đã kiểm tra | `511825856493` / `us-east-1` |
| Cost Explorer window | `[2026-07-15T00:00:00Z, 2026-07-22T00:00:00Z)`; daily result đang `Estimated=true` |
| Jira dependency | D18-COST-01 baseline và D18-COST-02 owner validation. D18-COST-01 baseline nằm tại [C0G-97 report](./d18-cost-01-baseline-usage-top-cost-drivers.md); owner validation chưa hoàn tất. |
| Primary metric | Type, provisioned/used GiB, GB-Month, IOPS, throughput, retention và restore result. Không dùng USD. |

Evidence source: AWS CLI và `kubectl` read-only collection; raw command output không commit vào repository.

Cost Explorer baseline: `EBS:VolumeUsage.gp2 = 13.801 GB-Month`, `EBS:VolumeUsage.gp3 = 25.673 GB-Month`, `EBS:SnapshotUsage = 2.139 GB-Month`. Đây là billing usage trong window ngắn; không dùng để tính used GiB hoặc target size.

## 2. Bảng volume theo Jira

Live usage đã được đo lại lúc `2026-07-22T06:xxZ` bằng `kubectl exec` với `df -B1`; `Target size` vẫn cần growth/peak window. Không suy diễn target từ provisioned size một lần đo.

| Volume | Current type | Size | Used | Utilization | Target type | Target size | Decision |
|---|---|---:|---|---|---|---|---|
| `vol-0024e483121338f0e`, OpenSearch `techx-observability/opensearch-opensearch-0` | gp2, `120 IOPS` | `40 GiB` | `36,729,143,296 bytes` (`36.729 GB`) | `87.1%` filesystem | gp3 | TBD | Active volume đang chỉ còn `5.413 GB` free. Do not shrink. Thu index growth, queue/latency và headroom; migrate gp3 qua backup/copy/cutover/rollback. |
| `vol-051c0352bdfaceb5d`, Prometheus `techx-observability/prometheus` | gp3, `3000 IOPS`, `125 MiB/s` | `20 GiB` | `17,411,276,800 bytes` (`17.411 GB`) | `81.4%` filesystem | gp3 | TBD | Không cần type migration. Không shrink vì còn `3.984 GB` free; đo TSDB growth/peak trước right-size. PV name `gp2-retain` cần reconcile. |
| `vol-0cb8c31ac039d6597`, PostgreSQL `techx-tf4/postgresql-pvc` | gp2 | `10 GiB` | TBD | TBD | gp3, nếu owner xác nhận workload còn dùng volume này | TBD | Live recheck: PV/PVC remains `Bound` but no matching running PostgreSQL pod or VolumeAttachment. AWS `available`; chặn cleanup/migration đến khi owner xác nhận cutover và restore state. |
| `vol-01a7d9f5b6270c06d`, Kafka `techx-tf4/kafka-pvc` | gp2 | `10 GiB` | TBD | TBD | gp3, nếu owner xác nhận workload còn dùng volume này | TBD | Live recheck: PV/PVC remains `Bound` but no matching running Kafka pod or VolumeAttachment. AWS `available`; cùng gate PostgreSQL. |
| `vol-0878313d6b2957e96`, Valkey `techx-tf4/valkey-cart-pvc` | gp2 | `5 GiB` | TBD | TBD | gp3, nếu owner xác nhận workload còn dùng volume này | TBD | Live recheck: PV/PVC remains `Bound` but no matching running Valkey pod or VolumeAttachment. AWS `available`; cùng gate PostgreSQL. |
| `vol-0ce59bf32f9aea7d5`, Released PV `techx-observability/postgresql-pvc` | gp2 | `10 GiB` | Not applicable | Not applicable | Not applicable | Not applicable | Orphan recovery-chain candidate, không phải right-size candidate. Recovery owner quyết định cleanup hoặc retention/expiry cùng snapshot. |

Evidence: EC2 volumes, PVs, PVCs.

Node/root volumes gp3 trong EC2 inventory không chứng minh persistent PVC storage đã gp3. Toàn bộ inventory hiện có `5` gp2 volumes / `75 GiB` và `6` gp3 volumes / `130 GiB` tại `us-east-1`. Live recheck lúc `2026-07-22T06:25:42Z` xác nhận OpenSearch vẫn gp2, `40 GiB`, in-use, `120 IOPS`; Prometheus gp3, `20 GiB`, in-use, `3000 IOPS`, `125 MiB/s`. Kubernetes hiện có hai StorageClass `gp2` và `gp2-retain`, đều in-tree `kubernetes.io/aws-ebs`; không có gp3 StorageClass.

## 3. gp2 to gp3, sizing, IOPS và throughput

StorageClass hiện có chỉ là `gp2` và `gp2-retain`, dùng in-tree `kubernetes.io/aws-ebs`; `gp2-retain` không cho expansion: StorageClasses.

Cách triển khai cho từng workload stateful:

1. Owner xác nhận workload, volume attachment, RPO/RTO, change window và rollback owner.
2. Thu filesystem/data used GiB, free space, growth rate, peak usage, EBS IOPS, throughput, queue length và latency trong window định trước.
3. Tạo CSI-based `gp3` hoặc `gp3-retain` StorageClass bằng capability EBS CSI hiện có. Không cài thêm driver.
4. Chụp backup có purpose/expiry, tạo gp3 PVC, copy hoặc restore data, rồi cut over trong maintenance window.
5. Kiểm tra data integrity, application health, trace lookup, log search, dashboard, alert và SLO. Giữ PV/EBS cũ đến hết rollback window.
6. Chỉ sau rollback window mới cleanup PV/EBS cũ qua GitOps/Kubernetes hoặc Terraform ownership path, rồi nộp after-scan.

Không resize trực tiếp volume đang `available` nếu PV/PVC vẫn `Bound` tham chiếu. Không chọn IOPS, throughput hoặc target GiB khi chưa có workload measurement.

## 4. Snapshot, AMI và S3 lifecycle

| Jira scope | Live baseline | Gap và closure action |
|---|---|---|
| Snapshot lifecycle | `9` self-owned snapshots; DLM trả `Policies: []`. Logical source volume size tổng `76 GiB`; snapshot billing incremental. | Recovery owner gán purpose/expiry. Implement DLM hoặc documented exception; after output phải chứng minh policy/expiry. Không xóa cutover or recovery snapshot chỉ vì tuổi. |
| AMI expiry | Không có self-owned AMI tại `us-east-1`. | Re-scan every enabled region. Nếu có AMI, bổ sung owner và expiry; nếu không có, lưu empty results cho account scope. |
| ECR lifecycle | `techx-corp` có policy expire untagged image sau 7 ngày và giữ tối đa 50 image. | Giữ policy; thu image count/size before and after nếu chọn ECR làm action. |
| S3 lifecycle/tier | CloudTrail và EKS audit buckets không có lifecycle configuration; Object Lock `COMPLIANCE` 90 ngày. Bucket `huyhoang1234` chưa rõ owner/purpose. | Forensic/storage owner thiết kế transition/expiry sau compliance floor. Không shorten/delete before 90 days. Xác nhận owner/purpose trước khi thay đổi bucket chưa phân loại. |

Evidence: DLM, snapshots, AMIs, ECR lifecycle, buckets, S3 command status.

## 5. Restore và rollback evidence

| Evidence cần có | Trạng thái | Điều kiện đạt |
|---|---|---|
| Backup/snapshot trước change | Chưa có per-migration record | Có owner, purpose, timestamp, source volume/PVC và restore procedure. |
| Restore data test | Chưa có | Restore vào target gp3 PVC hoặc isolated test target; compare data/application result. |
| Cutover plan | Chưa có | Maintenance window, owner, start/end, validation checklist và rollback trigger. |
| Rollback path | Chưa có | Giữ original PV/EBS trong rollback window; test hoặc document rollback operation. |
| Post-cutover validation | Chưa có | Application health, data integrity, SLO và observability checks đạt. |

Các snapshot hiện tại là recovery artifacts, không phải proof rằng restore path đã được test cho migration này.

## 6. Thu evidence bằng AWS CLI và kubectl

Mọi lệnh dưới đây chỉ đọc. Ghi summary vào Jira/report update, không commit raw JSON/YAML. Mỗi summary phải có UTC start/end, AWS caller identity, Kubernetes context, resource scope, command family, unit, owner và error code. Không export Secret, ConfigMap, workload/pod manifest, `SecretKeyRef`, `envFrom`, credential, database row hoặc log content.

### Xác nhận mapping EBS, PV/PVC và attachment trước migration

```bash
REGION=us-east-1
aws ec2 describe-volumes --region "$REGION" \
  --volume-ids vol-0024e483121338f0e vol-051c0352bdfaceb5d \
    vol-0cb8c31ac039d6597 vol-01a7d9f5b6270c06d \
    vol-0878313d6b2957e96 vol-0ce59bf32f9aea7d5 \
  --query 'Volumes[].{Id:VolumeId,State:State,Type:VolumeType,GiB:Size,IOPS:Iops,Throughput:Throughput,Attachments:Attachments[].InstanceId}' \
  --output table

kubectl get pv -o custom-columns=PV:.metadata.name,STATUS:.status.phase,RECLAIM:.spec.persistentVolumeReclaimPolicy,CLAIM:.spec.claimRef.namespace/.spec.claimRef.name,VOLUME:.spec.csi.volumeHandle
kubectl get pvc -A -o custom-columns=NAMESPACE:.metadata.namespace,PVC:.metadata.name,STATUS:.status.phase,VOLUME:.spec.volumeName,REQUEST:.spec.resources.requests.storage
kubectl get volumeattachments.storage.k8s.io -o custom-columns=NAME:.metadata.name,PV:.spec.source.persistentVolumeName,NODE:.spec.nodeName,ATTACHED:.status.attached
```

Nếu AWS state là `available` nhưng PV/PVC vẫn `Bound`, dừng ở đây và mở owner investigation. Không chạy resize, migration hoặc cleanup cho volume đó trước khi attachment/cutover/restore state được xác nhận.

### Thu `Used`, utilization, growth và performance

Lấy pod name trước bằng `kubectl get pods -n <NAMESPACE>`. Chỉ dùng `df`/`du` và index metadata, không đọc application data. Chạy cùng lệnh ở ít nhất daily window để đo peak/growth, sau đó mới điền `Used`, `Utilization` và `Target size` trong Section 2.

```bash
# OpenSearch: filesystem and index metadata only.
kubectl exec -n techx-observability <OPENSEARCH_POD> -- \
  df -h /usr/share/opensearch/data
kubectl exec -n techx-observability <OPENSEARCH_POD> -- \
  curl -s http://localhost:9200/_cat/indices?h=index,store.size,docs.count

# Prometheus: filesystem-level TSDB size only.
kubectl exec -n techx-observability <PROMETHEUS_POD> -- \
  df -h /prometheus
kubectl exec -n techx-observability <PROMETHEUS_POD> -- du -sh /prometheus

# PostgreSQL, Kafka and Valkey: run only after the mapping check above succeeds.
kubectl exec -n techx-tf4 <POSTGRES_POD> -- df -h <POSTGRES_DATA_PATH>
kubectl exec -n techx-tf4 <KAFKA_POD> -- df -h <KAFKA_DATA_PATH>
kubectl exec -n techx-tf4 <VALKEY_POD> -- df -h <VALKEY_DATA_PATH>

# Current EBS configuration, without changing it.
aws ec2 describe-volumes --region us-east-1 --volume-ids <VOLUME_ID> \
  --query 'Volumes[0].{Type:VolumeType,GiB:Size,IOPS:Iops,Throughput:Throughput,State:State}' \
  --output table
```

For workload-level I/O, use the existing Prometheus endpoint only if the metric is exposed. Record the query and numeric result, never label values:

```bash
kubectl port-forward -n techx-observability svc/prometheus 19090:9090
# Run in another terminal.
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=rate(node_disk_read_bytes_total[5m])'
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=rate(node_disk_written_bytes_total[5m])'
curl -sG http://localhost:19090/api/v1/query --data-urlencode 'query=rate(node_disk_io_time_seconds_total[5m])'
```

If a metric is absent or cannot be mapped safely to the workload, record `NOT_EXPOSED`; do not claim IOPS/throughput suitability from gp3 defaults alone.

### Snapshot, AMI, lifecycle và post-change validation

```bash
# Repeat for every enabled region found by describe-regions.
aws ec2 describe-regions \
  --filters Name=opt-in-status,Values=opted-in,opt-in-not-required \
  --query 'Regions[].RegionName' --output text
aws ec2 describe-snapshots --owner-ids self --region <REGION> \
  --query 'Snapshots[].{Id:SnapshotId,SourceGiB:VolumeSize,Started:StartTime,State:State,Description:Description}' \
  --output table
aws ec2 describe-images --owners self --region <REGION> \
  --query 'Images[].{Id:ImageId,Created:CreationDate,Name:Name}' --output table

# After an owner-authorized migration only: verify the new volume and Kubernetes binding.
aws ec2 describe-volumes --region us-east-1 --volume-ids <NEW_GP3_VOLUME_ID> \
  --query 'Volumes[0].{Type:VolumeType,GiB:Size,IOPS:Iops,Throughput:Throughput,State:State}' \
  --output table
kubectl get pv,pvc -A
kubectl get volumeattachments.storage.k8s.io
```

The current read-only role can collect EC2 inventory but cannot create DLM policy, change lifecycle, retrieve S3 lifecycle, retrieve ECR lifecycle, modify EBS, create a restore volume, cut over, or delete old resources. Those are owner-authorized Terraform/GitOps/write actions. For S3 lifecycle, require `s3:GetBucketLifecycleConfiguration` or console evidence from the storage owner. For DLM/ECR, require the respective service read/write owner evidence. A post-migration read-only pass verifies the after state; it does not prove restore capability by itself.

### Mapping đến criteria còn thiếu

| Gap | Lệnh/owner | Kết quả cần ghi |
|---|---|---|
| Full EBS/AMI inventory | EC2 region loop | Region, resource ID, type, state, size, AMI owner/expiry. |
| `Used`/utilization/target size | `kubectl exec df`/`du` over a multi-day window | Used GiB, provisioned GiB, utilization, peak/growth and target. |
| gp3 IOPS/throughput | EC2 describe plus metric-only PromQL | Configured IOPS/throughput, measured workload result, UTC window. |
| Snapshot lifecycle | EC2 snapshot inventory plus DLM lifecycle evidence | Purpose, expiry, policy or documented exception. |
| S3 lifecycle | Storage owner console/API evidence | Bucket, lifecycle transition/expiry, Object Lock/compliance floor. |
| Restore/rollback | Owner-authorized migration change record | Backup ID, restore test, cutover time, rollback window, data/SLO result. |

## 7. Acceptance criteria status

| Acceptance criterion | Status | Evidence hoặc closure action |
|---|---|---|
| Có inventory toàn bộ EBS trong scope | Partially met | Section 2 có full `us-east-1` inventory; enabled-region scan confirmed no additional `available` volume outside `us-east-1`, but not all in-use volume inventory. |
| Không còn gp2 không có documented reason | Not met | Five gp2 volumes tồn tại. Migration hoặc documented exception per volume cần có. |
| gp3 có IOPS/throughput phù hợp | Partially met | Prometheus config confirmed `3000 IOPS`/`125 MiB/s`; workload I/O query/growth window vẫn thiếu. |
| Volume right-size có growth headroom | Partially met | OpenSearch `87.1%` và Prometheus `81.4%` filesystem utilization đã đo. Cả hai không có headroom để shrink; cần multi-day growth/peak trước target size. |
| Snapshot có retention/lifecycle | Not met | DLM live recheck trả `Policies: []`; cần owner/expiry plus policy or exception. |
| AMI có owner và expiry | Met for current account inventory | Enabled-region scan: 0 self-owned AMI across 17 enabled regions. |
| S3 có lifecycle khi trong scope | Not met | CloudTrail/EKS audit chưa lifecycle; compliance floor cần giữ. |
| Không mất dữ liệu hoặc restore capability | Not met | Chưa có restore/cutover/rollback validation. |
| Có storage usage trước và sau | Partially met | Before baseline measured for OpenSearch and Prometheus at `2026-07-22T06:xxZ`; no migration or matched post-change window yet. |

## 8. Điều kiện đóng C0G-99

C0G-99 report collection đã hoàn thành. Các implementation work còn lại gồm target size sau multi-day growth window, gp2 migration hoặc documented exception, IOPS/throughput validation, snapshot/S3 lifecycle, và backup/restore/cutover/rollback evidence. Add this report and PR #493 to C0G-99 for mentor review.
