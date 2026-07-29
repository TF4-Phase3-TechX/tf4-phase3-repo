# CDO08-REL-22 ElastiCache Valkey Snapshot Recovery Readiness Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Verify ElastiCache snapshot recovery readiness
**Ngày ghi nhận:** 2026-07-27

Tài liệu này ghi lại evidence snapshot recovery readiness cho ElastiCache Valkey/cart trong Mandate 20. Evidence không chứa plaintext credential, secret value hoặc dữ liệu production.

---

## 1. Output Của Subtask

Subtask này cần tạo ra các output sau:

- Automated snapshot retention 7 ngày cho ElastiCache Valkey.
- Encryption at-rest và in-transit đã bật.
- Snapshot gần nhất ở trạng thái `available`.
- Restore method rõ ràng để REL-25 có thể tạo replication group mới khi kiểm thử.
- Ghi rõ cart TTL 60 phút; recovery outcome là khôi phục khả năng phục vụ cart service, không cam kết khôi phục toàn bộ active cart.

Kết luận hiện tại:

| Hạng mục            | Trạng thái | Evidence chính                                                                   |
| ------------------- | ---------- | -------------------------------------------------------------------------------- |
| Replication group   | PASS       | `techx-tf4-valkey-cart` đang `available`                                         |
| Snapshot retention  | PASS       | `SnapshotRetentionLimit=7`, `SnapshotWindow=18:00-19:00`                         |
| Encryption at-rest  | PASS       | `AtRestEncryptionEnabled=True`                                                   |
| Encryption transit  | PASS       | `TransitEncryptionEnabled=True`, `AuthTokenEnabled=True`                         |
| Snapshot gần nhất   | PASS       | `automatic.techx-tf4-valkey-cart-002-2026-07-25-18-01`, `available`              |
| Restore method      | PASS       | `create-replication-group --snapshot-name ...` command được ghi nhận             |
| Cart recovery scope | PASS       | Cart TTL 60 phút; recovery outcome là service readiness, không full cart restore |
| Production impact   | PASS       | Không restore, không delete, không thay đổi dữ liệu production                   |

---

## 2. Runtime Target

```text
Replication group: techx-tf4-valkey-cart
ARN: arn:aws:elasticache:us-east-1:511825856493:replicationgroup:techx-tf4-valkey-cart
Engine: valkey
Node type: cache.t4g.micro
Status: available
Automatic failover: enabled
Multi-AZ: enabled
Member clusters:
- techx-tf4-valkey-cart-001
- techx-tf4-valkey-cart-002
```

Runtime command:

```powershell
aws elasticache describe-replication-groups `
  --replication-group-id techx-tf4-valkey-cart `
  --profile tf4 `
  --region us-east-1 `
  --query 'ReplicationGroups[0].{Id:ReplicationGroupId,Status:Status,Engine:Engine,NodeType:CacheNodeType,TransitEncryptionEnabled:TransitEncryptionEnabled,AtRestEncryptionEnabled:AtRestEncryptionEnabled,AuthTokenEnabled:AuthTokenEnabled,SnapshotRetentionLimit:SnapshotRetentionLimit,SnapshotWindow:SnapshotWindow,AutomaticFailover:AutomaticFailover,MultiAZ:MultiAZ,ARN:ARN}' `
  --output table
```

Observed output:

```text
Id: techx-tf4-valkey-cart
Status: available
Engine: valkey
NodeType: cache.t4g.micro
AtRestEncryptionEnabled: True
TransitEncryptionEnabled: True
AuthTokenEnabled: True
SnapshotRetentionLimit: 7
SnapshotWindow: 18:00-19:00
AutomaticFailover: enabled
MultiAZ: enabled
```

Kết luận:

- ElastiCache Valkey cart đang `available`.
- Automated snapshot retention là 7 ngày.
- Snapshot window là `18:00-19:00`.
- At-rest encryption và in-transit encryption đang bật.
- Auth token, Multi-AZ và automatic failover đang bật.

---

## 3. Snapshot Evidence

Automated snapshots hiện có trong region:

```powershell
aws elasticache describe-snapshots `
  --profile tf4 `
  --region us-east-1 `
  --query 'Snapshots[*].{Name:SnapshotName,RG:ReplicationGroupId,Cluster:CacheClusterId,Status:SnapshotStatus,Type:SnapshotSource,StartTime:NodeSnapshots[0].SnapshotCreateTime,Engine:Engine}' `
  --output table
```

Observed snapshots:

```text
automatic.techx-tf4-valkey-cart-002-2026-07-19-18-00  available  automated
automatic.techx-tf4-valkey-cart-002-2026-07-20-18-01  available  automated
automatic.techx-tf4-valkey-cart-002-2026-07-21-18-00  available  automated
automatic.techx-tf4-valkey-cart-002-2026-07-22-18-01  available  automated
automatic.techx-tf4-valkey-cart-002-2026-07-23-18-01  available  automated
automatic.techx-tf4-valkey-cart-002-2026-07-24-18-00  available  automated
automatic.techx-tf4-valkey-cart-002-2026-07-25-18-01  available  automated
```

Latest snapshot for restore test:

```text
Snapshot name: automatic.techx-tf4-valkey-cart-002-2026-07-25-18-01
Snapshot source: automated
Snapshot status: available
Snapshot create time: 2026-07-25T18:01:50+00:00
Engine: valkey
```

Kết luận:

- Có automated snapshot gần nhất ở trạng thái `available`.
- Snapshot gần nhất có thể dùng làm recovery point cho REL-25 restore drill.
- Snapshot retention thực tế đang giữ chuỗi snapshot tự động theo ngày.

---

## 4. Restore Readiness

Subnet group:

```powershell
aws elasticache describe-cache-subnet-groups `
  --cache-subnet-group-name techx-tf4-valkey-private `
  --profile tf4 `
  --region us-east-1 `
  --query 'CacheSubnetGroups[0].{Name:CacheSubnetGroupName,VpcId:VpcId,Subnets:Subnets[*].SubnetIdentifier}' `
  --output table
```

Observed output:

```text
Subnet group: techx-tf4-valkey-private
VPC: vpc-0a4e2abe9fbb70451
Subnets:
- subnet-0280b36e2249f33d8
- subnet-0753e69d90fe8f820
```

Restore method for REL-25 drill:

```powershell
aws elasticache create-replication-group `
  --replication-group-id techx-tf4-rel25-valkey-restore `
  --replication-group-description "REL-25 restore drill from REL-22 Valkey snapshot" `
  --snapshot-name automatic.techx-tf4-valkey-cart-002-2026-07-25-18-01 `
  --engine valkey `
  --cache-node-type cache.t4g.micro `
  --cache-subnet-group-name techx-tf4-valkey-private `
  --security-group-ids <approved-valkey-security-group-id> `
  --transit-encryption-enabled `
  --at-rest-encryption-enabled `
  --region us-east-1 `
  --profile tf4
```

Restore command intentionally not executed in this subtask. REL-22 validates readiness and records the recovery point; REL-25 owns destructive/restore drill execution.

Kết luận:

- Subnet group private cho restore target đã xác định được.
- Restore command đã được ghi lại để tái sử dụng.
- Không tạo replication group restore trong subtask này để tránh tác động production/cost ngoài phạm vi.

---

## 5. Cart TTL / Recovery Semantics

Cart code sets a 60-minute TTL on cart keys:

```text
techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs
- AddItemAsync: db.KeyExpireAsync(userId, TimeSpan.FromMinutes(60))
- EmptyCartAsync: db.KeyExpireAsync(userId, TimeSpan.FromMinutes(60))
```

Implication:

- Snapshot restore can recover Valkey service state from the latest recovery point.
- It does not guarantee full recovery of every active cart at failure time.
- Expected recovery outcome is cart service availability within the RTO target, with carts bounded by TTL and snapshot recency.
- No write-through database scope is introduced in Mandate 20.

Kết luận:

- Cart TTL 60 phút đã được xác nhận trong source.
- Restore snapshot không đồng nghĩa khôi phục toàn bộ active cart tại thời điểm lỗi.
- Mandate 20 không mở thêm hướng write-through DB cho cart.

---

## 6. Acceptance Criteria Mapping

| Acceptance Criteria                              | Evidence                                                                         | Status |
| ------------------------------------------------ | -------------------------------------------------------------------------------- | ------ |
| Có snapshot gần nhất                             | Latest automated snapshot `automatic.techx-tf4-valkey-cart-002-2026-07-25-18-01` | Done   |
| Restore method rõ                                | `create-replication-group --snapshot-name ...` command recorded                  | Done   |
| Cấu hình đúng ADR                                | Retention 7 ngày, at-rest encryption true, transit encryption true               | Done   |
| Không tạo task write-through DB trong Mandate 20 | Recovery semantics section states cart TTL and service-readiness boundary        | Done   |

## 7. Kết Luận

ElastiCache Valkey cart hiện có automated snapshot retention 7 ngày, encryption at-rest/in-transit bật, snapshot gần nhất ở trạng thái `available`, và restore path rõ để REL-25 dùng cho drill.

Subtask 5 đủ điều kiện hoàn tất ở mức readiness/evidence. Không thay đổi production data trong quá trình verify.
