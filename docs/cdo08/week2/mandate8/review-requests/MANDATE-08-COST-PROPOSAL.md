# [REVIEW REQUEST] CDO04 - Cost Review Cho CDO08-MANDATE-08

| Field | Value |
|---|---|
| From | CDO08 |
| To | CDO04 Cost |
| Backlog | `CDO08-MANDATE-08` - Managed Data Services Migration |
| Date | 2026-07-19 |
| Region | `us-east-1` |
| Review result | **APPROVED WITH CONDITIONS** |

## 1. Mục Tiêu Review

MANDATE-08 yêu cầu chuyển 3 datastore tự vận hành trong EKS sang managed services:

| Current self-hosted service | Proposed managed target | Reason |
|---|---|---|
| PostgreSQL | Amazon RDS PostgreSQL Multi-AZ | Dữ liệu catalog/review/accounting có tính giao dịch và cần backup/failover tốt hơn |
| Valkey cart | Amazon ElastiCache for Valkey 2-node | Cart nằm trên checkout path; cần giảm rủi ro single in-cluster pod |
| Kafka Kraft | Amazon MSK Provisioned | Event/order stream cần managed broker thay vì single broker trong EKS |

CDO04 đã approve hướng kiến trúc và cost envelope ở trạng thái **APPROVED WITH CONDITIONS**. CDO08 được phép merge tài liệu và tiếp tục các task baseline/provisioning, nhưng **chưa được production cutover** cho tới khi các final gates ở mục 10 hoàn tất.

## 2. CDO04 Feedback Đã Được Incorporate

| CDO04 request | Update trong bản này |
|---|---|
| Đính kèm AWS Pricing Calculator export | Chuyển thành required artifact trước final approval; xem mục 3 |
| Xác nhận RDS price có bao gồm standby không | Không claim tới khi Calculator/export xác nhận; cost model tách assumption |
| Verify MSK storage official price | Đánh dấu cần Calculator/export xác nhận, không treat `$0.08/GiB-month` là final |
| Bổ sung backup/snapshot/log/monitoring/transfer/NLB/DMS/storage growth | Thêm Base, Expected, Guardrail Cost ở mục 4 |
| Không cộng standby RDS vào usable app capacity | Đã sửa capacity model ở mục 5 |
| Không cộng toàn bộ Valkey replica vào write capacity | Đã sửa capacity model ở mục 5 |
| Bỏ claim RTO `< 60s` | Đã sửa thành expected failover cần runtime validation |
| MirrorMaker incremental cost không được ghi `$0` tuyệt đối | Đã sửa thành no service fee, nhưng có node-hour/transfer/log risk |
| Resource freed không phải cost saving | Đã sửa thành capacity headroom gain, không claim saving |
| Capacity phải dựa measured workload | Thêm measured workload evidence requirement ở mục 5 |
| Auto-cleanup/expiry cho migration resources | Thêm cleanup guardrail ở mục 7 |

## 3. CDO04 Re-review Decision

CDO04 phản hồi ngày 2026-07-19 với trạng thái **APPROVED WITH CONDITIONS**:

| Item | CDO04 decision |
|---|---|
| RDS PostgreSQL Multi-AZ `db.t4g.micro`, 20 GiB gp3 | Approved with conditions |
| ElastiCache for Valkey, 2 node `cache.t4g.micro` | Approved with conditions |
| MSK Provisioned, 2 broker `kafka.t3.small` | Approved with conditions |
| AWS DMS `dms.t3.medium`, tối đa 24 giờ | Approved as temporary migration resource |
| Temporary NLB | Approved only if technically required |
| MirrorMaker 2 on EKS | Approved as temporary workload |

Cost envelope được duyệt:

| Envelope | Approved cap |
|---|---:|
| Base Fixed Cost | `<= $30/week` |
| Expected Operating Cost | `<= $35/week` |
| Recurring Guardrail Cost | `<= $45/week` |
| One-time Migration Guardrail | `<= $10` |
| Total TF weekly budget | `<= $300/week` |

Ý nghĩa phê duyệt:

```text
ARCHITECTURE DIRECTION: APPROVED
COST ENVELOPE: APPROVED
DOCUMENTATION MERGE: APPROVED
PRODUCTION CUTOVER: CONDITIONAL ON FINAL GATES
```

CDO08 có thể tiếp tục task `CDO08-REL-14` để provision baseline hạ tầng managed data theo Terraform/GitOps, miễn là các PR vẫn giữ đúng envelope trên và không bắt đầu cutover app/data trước khi final gates pass.

## 4. Required Pricing Artifacts Trước Final Approval

CDO08 không xem các số dưới đây là final production budget cho đến khi có đủ artifact sau:

| Artifact | Required content | Owner to confirm |
|---|---|---|
| AWS Pricing Calculator export | RDS, ElastiCache, MSK, DMS, temporary NLB trong `us-east-1` | CDO04 |
| RDS pricing confirmation | Xác nhận `db.t4g.micro Multi-AZ` hourly rate đã bao gồm primary + standby hay phải nhân 2 | CDO04 |
| MSK storage pricing confirmation | Xác nhận official storage rate cho MSK EBS trong `us-east-1` | CDO04 |
| Data transfer assumptions | Cross-AZ, NAT, private subnet path, migration traffic path | CDO04 + CDO08 |
| Monitoring/log assumptions | CloudWatch logs/metrics, enhanced monitoring nếu bật, MSK broker logs | CDO04 |

## 5. Cost Model Cần Review

### 5.1. Base Fixed Cost

Base Fixed Cost là chi phí tối thiểu khi managed services chạy ổn định, chưa tính usage spike, storage growth, data transfer, logs và temporary migration resources.

| Component | Proposed config | Cost status |
|---|---|---|
| RDS PostgreSQL | Multi-AZ, `db.t4g.micro`, 20 GiB gp3 | Needs Calculator confirmation |
| ElastiCache Valkey | 2 nodes, `cache.t4g.micro`, Multi-AZ/failover | Needs Calculator confirmation |
| MSK Provisioned | 2 brokers, `kafka.t3.small`, 10 GiB EBS/broker | Needs Calculator confirmation |

### 5.2. Expected Cost

Expected Cost phải cộng thêm các phần usage có khả năng xảy ra trong vận hành bình thường:

| Cost driver | Expected treatment |
|---|---|
| RDS backup/snapshot | Tính theo backup retention 7 ngày và storage thực tế; ghi rõ phần nào nằm trong included backup allowance nếu có |
| RDS monitoring/logs | Tính nếu bật enhanced monitoring, Performance Insights hoặc export logs |
| ElastiCache backup/snapshot | Tính snapshot retention và storage growth nếu bật snapshot |
| MSK broker storage growth | Tính từ initial 10 GiB/broker tới expected growth; không chỉ tính initial size |
| MSK logs/monitoring | Tính CloudWatch logs/metrics nếu bật broker logs hoặc enhanced monitoring |
| Cross-AZ/data transfer | Tính theo traffic path thực tế giữa EKS, RDS, ElastiCache, MSK và migration bridge |
| NAT data processing | Chỉ tính nếu migration/runtime traffic đi qua NAT |

### 5.3. Guardrail Cost

Guardrail Cost là mức trần dùng để tránh surprise bill nếu migration kéo dài hoặc storage/log tăng.

| Guardrail scenario | Required cap/decision |
|---|---|
| DMS chạy quá 24 giờ | Phải có max runtime/expiry và alert trước khi vượt |
| Temporary NLB quên xóa | Phải có cleanup deadline và owner |
| MirrorMaker chạy lâu hơn window | Phải có TTL/replicas/resources limit và cleanup owner |
| MSK storage auto-growth | Phải có max storage cap và alert threshold |
| Log/telemetry tăng do migration | Phải có retention và expected ingestion estimate |

## 6. Capacity Justification Phải Dựa Trên Measured Workload

Không dùng pod `limits` để claim managed service "dư thừa lớn". `limits` chỉ là quota/container guardrail, không phải workload demand thực tế.

### 6.1. PostgreSQL / RDS

| Item | Required evidence |
|---|---|
| CPU/memory | Peak và p95 usage của PostgreSQL hiện tại |
| Connections | Max/current DB connections |
| Query load | TPS hoặc query rate nếu có |
| Storage | Current used size và growth estimate |
| IO | IOPS/throughput nếu có metrics |
| Failover | Không claim RTO cho tới khi test |

**Capacity rule:** standby của RDS Multi-AZ one-standby **không được tính là usable read/write capacity** cho application. Standby là HA/failover capacity, không phải capacity phục vụ traffic bình thường.

**RTO wording:** không claim `RTO < 60s`. RDS Multi-AZ failover thường cần runtime validation; target wording hiện tại là:

```text
Expected failover behavior: khoảng 60-120 giây hoặc theo kết quả controlled failover test thực tế.
Final RTO chỉ được claim sau khi CDO08/PM/CDO04 chứng minh bằng runtime evidence.
```

### 6.2. Valkey / ElastiCache

| Item | Required evidence |
|---|---|
| Memory | Used memory, peak memory, key count, TTL behavior |
| Ops/s | Cart read/write ops/s dưới load đại diện |
| Connections | Current/max client connections |
| Failover | Cart/checkout behavior khi failover hoặc node replacement |

**Capacity rule:** nếu app dùng primary endpoint thì replica Valkey **không được cộng vào write capacity**. Replica được xem là HA/read/failover capacity.

### 6.3. Kafka / MSK

| Item | Required evidence |
|---|---|
| Throughput | Bytes in/out per topic hoặc broker |
| Consumer health | Consumer lag, commit behavior |
| Storage | Current topic size và growth/day |
| CPU/memory | Broker usage under representative load |
| Partition count | Topic/partition count và replication decision |

**Capacity rule:** MSK `2 brokers` không tự động chứng minh đủ capacity nếu chưa có bytes/sec, lag và storage growth evidence.

### 6.4. MirrorMaker 2

MirrorMaker 2 không có AWS managed service fee nếu chạy trong EKS, nhưng **không được claim incremental cost = `$0` tuyệt đối**.

Phải ghi như sau:

```text
MirrorMaker 2 has no separate AWS service fee. Incremental cost depends on EKS node-hours, NAT/data transfer path, logs/metrics/traces, and whether existing node headroom can absorb the temporary workload.
```

Việc xóa Kafka self-hosted sau cutover chỉ được ghi là **capacity headroom gain**. Chưa được claim cost saving cho tới khi có evidence giảm node-hours hoặc avoided scale-up.

## 7. Revised Architecture Recommendation

CDO08 vẫn đề xuất hướng managed migration sau, nhưng chuyển sang trạng thái **conditional approval required**:

| Component | Recommendation | Condition before production approval |
|---|---|---|
| PostgreSQL | RDS PostgreSQL Multi-AZ | Calculator export, measured workload, RTO wording fixed, backup/snapshot included |
| Valkey | ElastiCache Valkey 2-node | Cost approval for Multi-AZ, measured memory/ops/connections, clarify primary write capacity |
| Kafka | MSK Provisioned | Official MSK storage price, bytes/lag/storage growth, expected/guardrail cost |
| DMS | Temporary only | Max runtime, cleanup automation, storage/log cost included |
| MirrorMaker 2 | Temporary EKS workload | Node-headroom check, TTL/cleanup, telemetry/transfer cost estimate |
| Temporary NLB | Migration bridge only if needed | LCU/hour/data cost, deletion deadline, owner |

## 8. Cleanup Và Expiry Guardrail

Các tài nguyên migration tạm thời phải có expiry rõ trước khi production cutover.

| Temporary item | Cleanup requirement | Evidence required |
|---|---|---|
| DMS replication instance | Stop/delete sau migration window hoặc tối đa 24h nếu không có exception | `aws dms describe-replication-instances` không còn active temporary instance |
| DMS replication task | Stop/delete sau cutover | `aws dms describe-replication-tasks` |
| PostgreSQL replication slot | Drop sau migration nếu không còn CDC | SQL evidence hoặc RDS evidence |
| Temporary NLB | Delete sau migration bridge không còn cần | `aws elbv2 describe-load-balancers` không còn temporary NLB |
| Temporary SG rules | Remove rule chỉ dùng cho migration bridge | `aws ec2 describe-security-groups` |
| MirrorMaker 2 Deployment/Job | Scale down/delete sau Kafka cutover | `kubectl get deploy,job -A | grep -i mirrormaker` không còn workload active |
| Temporary GitOps values | Revert/disable migration flags sau cutover | Git SHA và Argo sync evidence |

## 9. CDO04 Decision

CDO04 đã phản hồi như sau:

| Question | CDO04 response |
|---|---|
| RDS Multi-AZ `db.t4g.micro` + 20 GiB gp3 có được approve không? | Approved with conditions |
| RDS hourly price dùng trong model là bao nhiêu và đã bao gồm standby chưa? | Must be confirmed by Pricing Calculator export |
| ElastiCache Valkey 2-node `cache.t4g.micro` có được approve không? | Approved with conditions |
| MSK Provisioned `kafka.t3.small` 2 brokers có được approve không? | Approved with conditions |
| MSK storage official rate trong `us-east-1` là bao nhiêu? | Must be confirmed by Pricing Calculator export |
| DMS `dms.t3.medium` tối đa 24h có được approve không? | Approved as temporary migration resource |
| Temporary NLB migration bridge có được approve không? | Approved only if technically required |
| Expected Cost và Guardrail Cost tối đa được duyệt là bao nhiêu? | Expected `<= $35/week`; recurring guardrail `<= $45/week`; one-time migration `<= $10` |

## 10. Final Approval Gate

CDO08 không bắt đầu production cutover cho RDS/ElastiCache/MSK cho tới khi các mục dưới đây hoàn tất:

- [ ] AWS Pricing Calculator export được attach.
- [x] Cost envelope được CDO04 approve ở trạng thái conditional.
- [ ] Final Expected Cost `<= $35/week` theo Calculator export.
- [ ] Final recurring Guardrail Cost `<= $45/week` theo Calculator export.
- [ ] One-time Migration Cost `<= $10`.
- [ ] Measured workload evidence được attach hoặc CDO04 chấp nhận assumption.
- [ ] Cleanup/expiry plan cho DMS, NLB, MirrorMaker, replication slot và temporary SG rules được approve.
- [ ] SEC-13 secret contract sẵn sàng để không đưa plaintext credential vào repo.
- [ ] Rollback/cutover plan của REL-15/REL-16/REL-17 được review.
- [ ] Reconnect behavior cho RDS, Valkey và MSK được review.
- [ ] SLO và correctness validation được chuẩn bị.
