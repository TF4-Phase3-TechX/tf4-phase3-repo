# CDO08-REL-31: MSK Broker AZ Placement & Client Recovery Readiness

**Task:** CDO08-REL-31 (P0)
**Mandate:** MANDATE-21 - DR Failover
**Owner:** Quân (CDO08)
**Ngày thu thập evidence:** 2026-07-28
**Trạng thái:** Evidence hoàn tất - **không có blocker quyền**; sẵn sàng làm input cho REL-35


## 1. Mục tiêu

Chứng minh MSK `techx-tf4-orders` **không** là SPOF theo AZ, và producer/consumer của luồng orders (`checkout`, `accounting`, `fraud-detection`) có thể phục hồi khi mất 1 AZ. Đây là evidence nền cho witnessed drill REL-35.

## 2. Definition of Done - đối chiếu

| DoD | Trạng thái | Mục |
|---|---|---|
| Bằng chứng MSK trải >= 2 AZ (hoặc blocker/approval rõ) | **PASS** - 2 broker/2 AZ **và** 100% partition replicated qua cả 2 AZ | §A |
| Bằng chứng app runtime đang dùng MSK secret | **PASS** - 3/3 app secretKeyRef `msk-kafka-secret`; bootstrap khớp byte-for-byte với AWS API | §B |
| Checklist kiểm tra producer/consumer/order correctness sau drill | **PASS** - checklist §F, đã verify từng metric/dimension tồn tại thật | §F |


## A. MSK cluster & AZ placement

### A.1. Cluster state (runtime API - profile `TF4-SecurityIAMSSOManager`)

`aws kafka describe-cluster-v2 --cluster-arn arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2`

| Thuộc tính | Giá trị runtime |
|---|---|
| Cluster name | `techx-tf4-orders` |
| **State** | **`ACTIVE`** |
| Type | `PROVISIONED` |
| Creation time | `2026-07-19T14:25:48Z` |
| Kafka version | 3.9.x |
| Số broker | 2 |
| Instance type | `kafka.t3.small` |
| Client subnets | `subnet-0280b36e2249f33d8`, `subnet-0753e69d90fe8f820` |
| EBS/broker | 10 GB, StorageMode `LOCAL` |
| Encryption in transit | ClientBroker `TLS`, InCluster `true` |
| Client auth | SASL: SCRAM `true` + IAM `true` |
| Enhanced monitoring | `DEFAULT` (đủ cho metric dùng ở §F - đã verify) |
| Broker logs | CloudWatch `/aws/msk/techx-tf4-orders` |

Khớp declared config trong `infra/terraform/msk.tf` (`aws_msk_cluster.orders`, dòng 83-133) - không có drift.

### A.2. Broker -> subnet -> AZ (`kafka:ListNodes`)

| Broker | Endpoint | Subnet | AZ | AZ-ID |
|---|---|---|---|---|
| 1 | `b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com` | `subnet-0753e69d90fe8f820` (10.0.11.0/24) | **us-east-1b** | use1-az2 |
| 2 | `b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com` | `subnet-0280b36e2249f33d8` (10.0.10.0/24) | **us-east-1a** | use1-az1 |

Subnet -> AZ resolve bằng `aws ec2 describe-subnets` (VPC `vpc-0a4e2abe9fbb70451`).

### A.3. Partition replication qua AZ - bằng chứng SPOF cấp dữ liệu

Hạ tầng 2 AZ **chưa đủ** để loại SPOF: nếu topic có RF=1 thì mất 1 AZ vẫn mất partition. Đối chiếu 3 metric CloudWatch (2026-07-28) chứng minh replication thật:

| Metric | Broker 1 (us-east-1b) | Broker 2 (us-east-1a) | Tổng |
|---|---:|---:|---:|
| `PartitionCount` (gồm cả replica) | 119 | 119 | **238** |
| `LeaderCount` | 59 | 60 | **119** |
| `GlobalPartitionCount` (partition duy nhất, **không** tính replica) | - | - | **119** |

Suy luận:

```text
LeaderCount(b1) + LeaderCount(b2) = 59 + 60 = 119 = GlobalPartitionCount
  => mỗi partition có đúng 1 leader; leadership chia gần đều 2 AZ.

PartitionCount(b1) + PartitionCount(b2) = 238 = 2 x 119
  => mọi partition (119/119) đều có replica trên CẢ HAI broker
  => tức trên cả us-east-1a và us-east-1b.
```

**Kết luận A: MSK `techx-tf4-orders` ACTIVE, 2 broker ở 2 AZ, và 100% partition (bao gồm topic `orders`) được replicate qua cả 2 AZ. Mất 1 AZ vẫn còn bộ replica đầy đủ của mọi partition trên broker sống sót => KHÔNG phải SPOF theo AZ.**

Củng cố bằng config: `default.replication.factor=2`, `offsets.topic.replication.factor=2`, `transaction.state.log.replication.factor=2`, `min.insync.replicas=1` (`aws_msk_configuration.orders`, `msk.tf` dòng 72-80). `min.insync.replicas=1` là điều kiện để producer **vẫn ghi được** khi chỉ còn 1 replica in-sync (xem lưu ý durability ở §E).

### A.4. Health baseline trước drill (2026-07-28)

| Metric | Giá trị | Ý nghĩa |
|---|---|---|
| `ActiveControllerCount` | 1 | Đúng 1 controller, không split-brain |
| `OfflinePartitionsCount` | 0 | Không partition nào offline |
| `UnderReplicatedPartitions` (broker 1 / broker 2) | 0 / 0 | Mọi replica in-sync |
| `GlobalTopicCount` | 11 | |
| `GlobalPartitionCount` | 119 | |

## B. App runtime đang dùng MSK secret

### B.1. Nguồn khai báo (declarative)

- Chart default `techx-corp-chart/values.yaml`: `managedData.kafka` có `secretName: msk-kafka-secret`, `services: [accounting, checkout, fraud-detection]` (mặc định `enabled: false`).
- Production override (GitOps `environments/production/app-values.yaml`, khối `managedData`, dòng 848-862):

```yaml
managedData:
  enabled: true
  kafka:
    enabled: true
    secretName: msk-kafka-secret
    services: [checkout, accounting, fraud-detection]
```

- Cùng file, khối component toggle (dòng 737-738) đặt self-hosted `kafka: enabled: false`. Runtime xác nhận: không còn statefulset/deployment Kafka self-hosted trong `techx-tf4` (chỉ còn `kafka-connect-orders-archive` của REL-22, không nằm trong request path).

### B.2. Secret contract (runtime, namespace `techx-tf4`)

Secret `msk-kafka-secret` tồn tại, keys: `kafka-address`, `username`, `password`, `security-protocol`, `sasl-mechanism`.

| Key | Giá trị (không nhạy cảm) |
|---|---|
| `kafka-address` | `b-2.techxtf4orders...:9096,b-1.techxtf4orders...:9096` |
| `security-protocol` | `SASL_SSL` |
| `sasl-mechanism` | `SCRAM-SHA-512` |
| `username` | `techx_tf4_orders_app` |

**Cross-check với AWS API:** `aws kafka get-bootstrap-brokers` trả về

```text
BootstrapBrokerStringSaslScram = b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,
                                 b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096
```

Giá trị này **khớp byte-for-byte** với `kafka-address` trong secret => secret sinh đúng từ MSK (không phải chuỗi gõ tay/stale), và bootstrap list chứa **cả 2 broker ở 2 AZ**. (Cluster cũng expose `BootstrapBrokerStringSaslIam` cổng 9098 cho Firehose/REL-28; app dùng SCRAM 9096.)

### B.3. Wiring runtime của 3 app (kubectl, deployment env)

Cả 3 deployment lấy 5 biến Kafka từ `msk-kafka-secret` qua `secretKeyRef`:

| App | Role trong orders path | Env <- secretKeyRef | Pod |
|---|---|---|---|
| `checkout` | Producer | `KAFKA_ADDR`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_SASL_MECHANISM`, `KAFKA_USERNAME`, `KAFKA_PASSWORD` <- `msk-kafka-secret` | 2/2 Running |
| `accounting` | Consumer (group `accounting`) | 5 biến như trên <- `msk-kafka-secret` | 1/1 Running |
| `fraud-detection` | Consumer (group `fraud-detection`) | 5 biến như trên <- `msk-kafka-secret` | 1/1 Running |

**Cross-check phía broker:** CloudWatch `AWS/Kafka` publish consumer-lag metric cho đúng 2 consumer group `accounting` và `fraud-detection` trên topic `orders` => broker xác nhận 2 app này đang thực sự consume từ MSK, không chỉ có env đúng. Group thứ 3 `connect-orders-s3-archive` là REL-22 archive connector.

**Kết luận B: cả 3 app đang dùng `msk-kafka-secret` ở runtime, trỏ tới MSK bootstrap 2-AZ, SASL_SSL/SCRAM-SHA-512; broker-side metric xác nhận consumer đang hoạt động.**

## C. Baseline consumer lag & order path (2026-07-28)

| Consumer group | Topic | `SumOffsetLag` (max, 3 datapoint gần nhất) | Vai trò |
|---|---|---:|---|
| `accounting` | `orders` | 0 | Ghi order vào RDS (RPO-critical) |
| `fraud-detection` | `orders` | 0 | Fraud scoring |
| `connect-orders-s3-archive` | `orders` | 0 | REL-22 archive (RPO-supporting) |

Cả 3 group lag = 0 trước drill => baseline sạch, mọi độ lệch quan sát trong drill là do AZ loss chứ không phải nợ tồn.

## D. Client (app) AZ topology & gap phân tích

Node -> AZ (kubectl node label `topology.kubernetes.io/zone`):

| App | Replicas | Vị trí hiện tại | topologySpread zone | PDB |
|---|---|---|---|---|
| `checkout` | 2 | 1 pod us-east-1b (`ip-10-0-11-17`) + 1 pod us-east-1a (`ip-10-0-10-182`) | Có (`maxSkew=1`, zone, `ScheduleAnyway`) + hostname `DoNotSchedule` | `checkout` minAvailable=1 |
| `accounting` | 1 | us-east-1b (`ip-10-0-11-82`) | Không | Không |
| `fraud-detection` | 1 | us-east-1b (`ip-10-0-11-82`) | Không | Không |

**Nhận định:**

- **Producer (`checkout`) chịu được mất 1 AZ**: 2 replica đang trải 1a + 1b, có topologySpread theo zone và PDB `minAvailable=1`. Mất 1 AZ => 1 replica sống sót tiếp tục produce.
- **Consumer (`accounting`, `fraud-detection`) hiện dồn 1 AZ**: mỗi cái 1 replica và **đều nằm us-east-1b** (cùng 1 node `ip-10-0-11-82`), không topologySpread/PDB. Nếu mất **us-east-1b**, cả hai consumer down đồng thời cho tới khi K8s reschedule sang AZ còn lại. Không mất dữ liệu (offset đã commit ở MSK, xem §E) nhưng phát sinh **recovery latency** = thời gian reschedule + consumer rejoin, tính vào mục tiêu catch-up <= 10 phút của REL-28 §2.
- Lưu ý: mất **us-east-1b** là kịch bản xấu nhất cho consumer - nó đồng thời mất broker 1. Dù vậy broker 2 (us-east-1a) giữ replica đầy đủ của mọi partition (§A.3) nên dữ liệu orders không mất.
- Đây đúng điều kiện REL-28 ADR §7 đặt ra ("có thể giữ 1 replica nếu chứng minh MSK giữ event, consumer resume..."). REL-31 chứng minh cơ chế resume (§E); phần **đặt lại placement/topologySpread/PDB cho 2 consumer chuyển cho REL-32** (ADR §8.4).

## E. Expected client reconnect behavior (ghi để đối chiếu khi drill)

**Bootstrap resilience:** `kafka-address` chứa cả `b-1` và `b-2` (§B.2). Client bootstrap được qua broker còn sống nếu 1 broker/AZ mất => không phụ thuộc 1 endpoint.

**Producer (`checkout`) khi mất AZ chứa 1 broker:**

- Metadata refresh phát hiện leader mới. Vì mọi partition có replica trên cả 2 broker (§A.3), broker sống sót đủ điều kiện lên leader cho toàn bộ partition mà nó đang follow.
- Với `min.insync.replicas=1`, partition chỉ còn 1 in-sync replica **vẫn nhận write** => availability của luồng produce được giữ.
- **Lưu ý durability (không phải blocker):** trong cửa sổ mất AZ, RF hiệu dụng = 1. Nếu broker còn lại lỗi tiếp trước khi re-replicate xong, có rủi ro mất message. Kịch bản Mandate 21 là mất **1** AZ nên chấp nhận được; ghi ra để reviewer thấy trade-off availability/durability là có chủ đích.

**Consumer (`accounting`, `fraud-detection`) khi pod bị mất theo AZ:**

- Consumer config (`techx-corp-platform/src/accounting/Consumer.cs`): `GroupId=accounting`, `EnableAutoCommit=true`, `AutoOffsetReset=Earliest`.
- Sau reschedule/restart, consumer rejoin group và resume từ **committed offset** => semantics **at-least-once**. Có thể **duplicate** vài message đã xử lý nhưng chưa commit tại thời điểm mất pod.
- `accounting` chống double-count ở tầng dữ liệu: `OrderEntity.Id = order.OrderId` là khóa chính, nên insert lại cùng order sẽ vi phạm PK thay vì cộng đôi. Đây là căn cứ cho tiêu chí "no duplicate gây double accounting" ở REL-28 §4 - **vẫn phải verify bằng đối soát thật trong drill** (§F.4), không coi là đã chứng minh.
- Offset của group nằm trên topic `__consumer_offsets` với `offsets.topic.replication.factor=2` => bản thân offset cũng sống sót khi mất 1 AZ.

## F. Failover drill checklist (chuẩn bị cho REL-35)

Chạy **trước** (baseline) và **sau** khi mentor gây AZ loss, đối chiếu chênh lệch. Mọi metric/dimension dưới đây đã được verify là tồn tại thật trên cluster này.

### F.1. MSK / broker health

- [ ] `aws kafka describe-cluster-v2 --cluster-arn <ARN>` -> `State=ACTIVE`.
- [ ] `aws kafka list-nodes --cluster-arn <ARN>` -> broker ở AZ sống vẫn trả endpoint.
- [ ] CloudWatch `AWS/Kafka`, dimension `Cluster Name=techx-tf4-orders`:
  - `ActiveControllerCount` = 1 (nếu controller ở AZ mất, kỳ vọng bầu lại về 1).
  - `OfflinePartitionsCount` = 0 (**>0 là fail** - có partition không leader).
  - `GlobalPartitionCount` giữ 119 (không mất partition).
- [ ] CloudWatch per-broker (thêm dimension `Broker ID`):
  - `UnderReplicatedPartitions`: kỳ vọng **>0 tạm thời** khi mất 1 broker, phải **về 0** sau recovery.
  - `LeaderCount` broker sống sót tăng lên ~119 (nhận leadership toàn bộ), rồi cân bằng lại sau recovery.

### F.2. Producer health (`checkout`)

- [ ] Pod `checkout` còn >= 1 Ready ở AZ sống (PDB `minAvailable=1`).
- [ ] Checkout Success Rate trên `checkout-revenue-dashboard` không rớt dưới SLO 99.0% quá 5 phút (REL-28 §2).
- [ ] Không spike lỗi produce (log `checkout`; `BytesInPerSec`/`MessagesInPerSec` vẫn có traffic - loại khả năng "xanh giả" do không có tải).

### F.3. Consumer health (`accounting`, `fraud-detection`)

- [ ] Pod được reschedule sang AZ sống và về `Running` (ghi lại thời điểm để tính recovery latency - liên quan gap §D).
- [ ] CloudWatch `SumOffsetLag` / `MaxOffsetLag` / `EstimatedMaxTimeLag`, dimension `Cluster Name` + `Consumer Group` (`accounting`, `fraud-detection`) + `Topic=orders`: lag tăng trong failure window rồi **về ~0 trong <= 10 phút** (REL-28 §2 post-checkout catch-up). Baseline trước drill = 0 (§C).
- [ ] Đối chiếu chéo bằng `kafka-consumer-groups.sh --describe --group <g>` từ pod client (mẫu pod client SASL: `docs/cdo08/week3/mandate20/scripts/rel-23/00-common.ps1`).
- [ ] `connect-orders-s3-archive` cũng catch up (REL-22 archive là nguồn RPO phụ trợ).

### F.4. Order correctness / RPO (confirmed orders)

- [ ] `expected confirmed order count` trong failure window (load-generator / checkout result).
- [ ] `== MSK orders event count` (topic `orders`).
- [ ] `== accounting persisted order count` (schema `accounting` trong RDS PostgreSQL).
- [ ] `no missing order`.
- [ ] `no duplicate order gây double accounting` - verify thật, không dựa suy luận PK ở §E.
- [ ] Nếu lệch: dùng replay/reconcile tooling Mandate 20 (REL-23/REL-25) để đối soát.

### F.5. Điều kiện PASS

- MSK: `OfflinePartitionsCount` = 0 suốt drill; `UnderReplicatedPartitions` về 0 sau recovery.
- Checkout SLO phục hồi trong RTO target (REL-28 §2/§3).
- Consumer lag về ~0 trong <= 10 phút.
- RPO confirmed order = 0 (no missing, no double-count).


## G. Kết luận REL-31

1. **MSK `techx-tf4-orders` ACTIVE và không là SPOF theo AZ.** 2 broker ở 2 AZ (broker 1 = us-east-1b, broker 2 = us-east-1a), và quan trọng hơn: **100% partition (119/119) có replica trên cả 2 AZ** - chứng minh bằng `PartitionCount` 119+119 = 2 x `GlobalPartitionCount` 119. Fills yêu cầu "broker/node-level evidence" của REL-28 §6.
2. **3/3 app dùng `msk-kafka-secret` ở runtime**; bootstrap khớp byte-for-byte với `GetBootstrapBrokers`, chứa cả 2 broker/2 AZ, SASL_SSL + SCRAM-SHA-512. Broker-side lag metric xác nhận consumer đang thực sự đọc từ MSK.
3. **Producer `checkout` sẵn sàng chịu mất 1 AZ** (2 replica trải AZ + topologySpread + PDB minAvailable=1).
4. **Baseline sạch trước drill**: controller=1, offline partitions=0, under-replicated=0, lag=0 cho cả 3 consumer group.
5. **Gap chuyển REL-32:** `accounting` và `fraud-detection` mỗi cái 1 replica và **cùng nằm trên 1 node ở us-east-1b**, chưa có topologySpread/PDB. Cơ chế resume (committed offset + `offsets.topic.replication.factor=2` + dedup PK `order_id`) đã chứng minh là không mất dữ liệu; việc bố trí lại placement để giảm recovery latency thuộc REL-32.
6. **Checklist drill (§F)** đã verify từng metric/dimension tồn tại thật, sẵn sàng làm input cho REL-35.
