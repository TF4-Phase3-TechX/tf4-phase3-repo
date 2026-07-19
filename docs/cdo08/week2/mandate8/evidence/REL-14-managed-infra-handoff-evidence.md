# REL-14 Managed Data Infra - Output & Handoff Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-14
**Ngày cập nhật:** 2026-07-19

Tài liệu này tổng hợp output hạ tầng managed data layer của `CDO08-REL-14` để bàn giao cho các task tiếp theo:

- `SEC-13`: tạo AWS Secrets Manager secret, ExternalSecret và Kubernetes Secret contract.
- `REL-15`: chuẩn bị cutover PostgreSQL sang RDS.
- `REL-16`: chuẩn bị cutover Valkey/cart sang ElastiCache.
- `REL-17`: chuẩn bị cutover Kafka/orders sang MSK.

Phạm vi của REL-14 chỉ là provision managed baseline bằng Terraform. Tài liệu này không xác nhận data migration/cutover đã hoàn tất, không chứa plaintext credential và không thay thế runbook migration chi tiết của từng store.

---

## 1. Trạng thái Tổng quan

| Store        | Managed target            | Trạng thái | Ghi chú                                                                                 |
| ------------ | ------------------------- | ---------- | --------------------------------------------------------------------------------------- |
| PostgreSQL   | Amazon RDS PostgreSQL     | PASS       | Đã apply, RDS `available`, private, Multi-AZ, encrypted, backup retention 7 ngày.       |
| Valkey/cart  | Amazon ElastiCache Valkey | PASS       | Đã apply, replication group `available`, Valkey, Multi-AZ, failover, at-rest và transit encryption đều bật. |
| Kafka/orders | Amazon MSK                | PASS       | Đã apply, MSK cluster `ACTIVE`, 2 brokers private subnet, KMS encryption và SASL/SCRAM bootstrap brokers. |

---

## 2. RDS PostgreSQL Baseline

### 2.1. Terraform Outputs

| Field                  | Value                                                           |
| ---------------------- | --------------------------------------------------------------- |
| Account ID             | `511825856493`                                                  |
| VPC ID                 | `vpc-0a4e2abe9fbb70451`                                         |
| Cluster name           | `techx-tf4-cluster`                                             |
| RDS endpoint           | `techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com` |
| Port                   | `5432`                                                          |
| Database name          | `otel`                                                          |
| RDS instance ARN       | `arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql`    |
| Security group ID      | `sg-0fbc6edd9ae2742d1`                                          |
| Subnet group           | `techx-tf4-postgresql-private`                                  |
| Parameter group        | `techx-tf4-postgresql17-dms`                                    |
| Master user secret ARN | `<sensitive>`                                                   |

Ghi chú: `rds_postgresql_master_user_secret_arn` là RDS-managed admin/bootstrap secret. Workload không consume trực tiếp secret này.

### 2.2. Runtime Verification

Lệnh verify:

```powershell
aws rds describe-db-instances `
  --db-instance-identifier techx-tf4-postgresql `
  --region us-east-1 `
  --profile tf4 `
  --query 'DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Port:Endpoint.Port,Public:PubliclyAccessible,MultiAZ:MultiAZ,Encrypted:StorageEncrypted,BackupRetention:BackupRetentionPeriod,DBName:DBName,VpcSecurityGroups:VpcSecurityGroups[*].VpcSecurityGroupId}'
```

Output đã ghi nhận:

```json
{
    "Status": "available",
    "Endpoint": "techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com",
    "Port": 5432,
    "Public": false,
    "MultiAZ": true,
    "Encrypted": true,
    "BackupRetention": 7,
    "DBName": "otel",
    "VpcSecurityGroups": ["sg-0fbc6edd9ae2742d1"]
}
```

Kết luận:

- RDS đã `available`.
- Không public endpoint.
- Multi-AZ đã bật.
- Storage encryption đã bật.
- Backup retention là 7 ngày.
- Security group khớp output Terraform.

### 2.3. Secret Contract Handoff cho SEC-13

REL-14 không tạo app secret hoặc ExternalSecret. SEC-13 sẽ tạo/update secret theo contract sau:

| Field                    | Value                    |
| ------------------------ | ------------------------ |
| AWS Secrets Manager path | `techx/tf4/rds-postgres` |
| Kubernetes Secret name   | `rds-postgres-secret`    |
| Namespace                | `techx-tf4`              |
| Database name            | `otel`                   |
| Port                     | `5432`                   |

Payload kỳ vọng theo `sec-13-managed-data-secret-contract.md`:

```json
{
    "host": "techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com",
    "port": "5432",
    "username": "<app-user>",
    "password": "<real-password>",
    "dbname": "otel",
    "connection_string_dotnet": "Host=techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com;Port=5432;Username=<app-user>;Password=<real-password>;Database=otel;SSL Mode=Require;Trust Server Certificate=true",
    "connection_string_go": "postgres://<app-user>:<real-password>@techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com:5432/otel?sslmode=require",
    "connection_string_python": "host=techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com port=5432 user=<app-user> password=<real-password> dbname=otel sslmode=require"
}
```

Kubernetes Secret keys:

| Key                  | Consumer          |
| -------------------- | ----------------- |
| `dotnet-conn-string` | `accounting`      |
| `go-conn-string`     | `product-catalog` |
| `python-conn-string` | `product-reviews` |

### 2.4. Handoff cho REL-15

REL-15 có thể dùng các thông tin sau để chuẩn bị PostgreSQL cutover:

- RDS private endpoint: `techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com`
- Port: `5432`
- DB name: `otel`
- RDS security group: `sg-0fbc6edd9ae2742d1`
- RDS instance ARN: `arn:aws:rds:us-east-1:511825856493:db:techx-tf4-postgresql`
- Parameter group DMS/logical replication: `techx-tf4-postgresql17-dms`

REL-15 vẫn cần tự verify connectivity, schema/data parity và cutover readiness trước khi đổi traffic.

---

## 3. ElastiCache Valkey Baseline

### 3.1. Terraform Outputs

| Field                 | Value                                                                               |
| --------------------- | ----------------------------------------------------------------------------------- |
| Replication group ID  | `techx-tf4-valkey-cart`                                                             |
| Replication group ARN | `arn:aws:elasticache:us-east-1:511825856493:replicationgroup:techx-tf4-valkey-cart` |
| Primary endpoint      | `master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com`                      |
| Reader endpoint       | `replica.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com`                     |
| Port                  | `6379`                                                                              |
| Security group ID     | `sg-09a2b8fa50eaf3df8`                                                              |
| Subnet group          | `techx-tf4-valkey-private`                                                          |
| Parameter group       | `techx-tf4-valkey9-cart`                                                            |
| At-rest encryption    | `true`                                                                              |
| Transit encryption    | `true`                                                                              |
| Snapshot retention    | `7` ngày                                                                            |

### 3.2. Runtime Verification

Lệnh verify:

```powershell
aws elasticache describe-replication-groups `
  --replication-group-id techx-tf4-valkey-cart `
  --region us-east-1 `
  --profile tf4 `
  --query 'ReplicationGroups[0].{Status:Status,Engine:Engine,TransitEncryptionEnabled:TransitEncryptionEnabled,TransitEncryptionMode:TransitEncryptionMode,AtRestEncryptionEnabled:AtRestEncryptionEnabled,MultiAZ:MultiAZ,AutomaticFailover:AutomaticFailover,PrimaryEndpoint:NodeGroups[0].PrimaryEndpoint.Address,ReaderEndpoint:NodeGroups[0].ReaderEndpoint.Address}'
```

Output đã ghi nhận:

```json
{
    "Status": "available",
    "Engine": "valkey",
    "TransitEncryptionEnabled": true,
    "TransitEncryptionMode": "preferred",
    "AtRestEncryptionEnabled": true,
    "MultiAZ": "enabled",
    "AutomaticFailover": "enabled",
    "PrimaryEndpoint": "master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com",
    "ReaderEndpoint": "replica.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com"
}
```

Kết luận:

- ElastiCache replication group đã `available`.
- Engine là `valkey`.
- At-rest encryption đã bật.
- Transit encryption đã bật với mode `preferred`.
- Multi-AZ đã bật.
- Automatic failover đã bật.
- Primary endpoint và reader endpoint khớp output Terraform.

### 3.3. Secret Contract Handoff cho SEC-13

REL-14 không tạo app secret hoặc ExternalSecret. SEC-13 sẽ tạo/update secret theo contract sau:

| Field                    | Value                          |
| ------------------------ | ------------------------------ |
| AWS Secrets Manager path | `techx/tf4/elasticache-valkey` |
| Kubernetes Secret name   | `elasticache-valkey-secret`    |
| Namespace                | `techx-tf4`                    |
| App key                  | `valkey-address`               |
| Payload keys             | `host`, `port`, `address`      |

Payload tối thiểu:

```json
{
    "host": "master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com",
    "port": "6379",
    "address": "master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com:6379"
}
```

AUTH/TLS payload chỉ bật sau khi `cart` xác nhận hỗ trợ.

### 3.4. Handoff cho REL-16

REL-16 có thể dùng các thông tin sau để chuẩn bị Valkey/cart cutover:

- Primary endpoint: `master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com`
- Reader endpoint: `replica.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com`
- Port: `6379`
- Security group: `sg-09a2b8fa50eaf3df8`
- Secret contract path: `techx/tf4/elasticache-valkey`
- Kubernetes Secret: `techx-tf4/elasticache-valkey-secret`
- App key: `valkey-address`

REL-16 vẫn cần verify app compatibility với TLS/auth mode trước khi cutover.

---

## 4. MSK Kafka Baseline

### 4.1. Terraform Outputs

| Field                        | Value                                                                                                                             |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Cluster name                 | `techx-tf4-orders`                                                                                                                |
| Cluster ARN                  | `arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2`                            |
| Bootstrap brokers SASL/SCRAM | `b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096` |
| Client port                  | `9096`                                                                                                                            |
| Broker node type             | `kafka.t3.small`                                                                                                                  |
| Broker storage               | `10 GiB`                                                                                                                          |
| Storage autoscaling max      | `100 GiB`                                                                                                                         |
| Security group ID            | `sg-0b15c69a8c397e9d6`                                                                                                            |
| KMS key ARN                  | `arn:aws:kms:us-east-1:511825856493:key/e9f0c549-066e-41b0-bf07-bc2fe404b966`                                                     |
| Authentication protocol      | `SASL_SSL with SCRAM-SHA-512`                                                                                                     |

Ghi chú:

- REL-14 không tạo credential thật trong Terraform.
- REL-14 không đưa password vào Terraform state.
- REL-14 không tạo SCRAM secret association.
- Security group dùng port `9096` cho SASL/SCRAM.
- SEC-13 chịu trách nhiệm tạo secret app và SCRAM association.

### 4.2. Runtime Verification

Lệnh verify cluster:

```powershell
aws kafka list-clusters-v2 `
  --region us-east-1 `
  --profile tf4 `
  --query 'ClusterInfoList[?ClusterName==`techx-tf4-orders`].{Name:ClusterName,Arn:ClusterArn,State:State}'
```

Output đã ghi nhận:

```json
[
    {
        "Name": "techx-tf4-orders",
        "Arn": "arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2",
        "State": "ACTIVE"
    }
]
```

Lệnh verify chi tiết:

```powershell
aws kafka describe-cluster-v2 `
  --cluster-arn arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2 `
  --region us-east-1 `
  --profile tf4 `
  --query 'ClusterInfo.{Name:ClusterName,State:State,KafkaVersion:Provisioned.CurrentBrokerSoftwareInfo.KafkaVersion,BrokerCount:Provisioned.NumberOfBrokerNodes,Subnets:Provisioned.BrokerNodeGroupInfo.ClientSubnets,SecurityGroups:Provisioned.BrokerNodeGroupInfo.SecurityGroups,Encryption:Provisioned.EncryptionInfo}'
```

Output đã ghi nhận:

```json
{
    "Name": "techx-tf4-orders",
    "State": "ACTIVE",
    "KafkaVersion": "3.9.x",
    "BrokerCount": 2,
    "Subnets": [
        "subnet-0280b36e2249f33d8",
        "subnet-0753e69d90fe8f820"
    ],
    "SecurityGroups": [
        "sg-0b15c69a8c397e9d6"
    ],
    "Encryption": {
        "EncryptionAtRest": {
            "DataVolumeKMSKeyId": "arn:aws:kms:us-east-1:511825856493:key/e9f0c549-066e-41b0-bf07-bc2fe404b966"
        },
        "EncryptionInTransit": {
            "ClientBroker": "TLS",
            "InCluster": true
        }
    }
}
```

Lệnh verify bootstrap brokers:

```powershell
aws kafka get-bootstrap-brokers `
  --cluster-arn arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2 `
  --region us-east-1 `
  --profile tf4
```

Output đã ghi nhận:

```json
{
    "BootstrapBrokerStringSaslScram": "b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096"
}
```

Kết luận:

- MSK cluster đã `ACTIVE`.
- Kafka version là `3.9.x`.
- Broker count là `2`.
- Broker nằm trong private subnet `subnet-0280b36e2249f33d8` và `subnet-0753e69d90fe8f820`.
- Security group khớp output Terraform: `sg-0b15c69a8c397e9d6`.
- Encryption at rest dùng KMS key đã output.
- Encryption in transit đã bật: client-broker `TLS`, in-cluster `true`.
- Có bootstrap broker SASL/SCRAM trên port `9096`.

### 4.3. Secret Contract Handoff cho SEC-13

REL-14 không tạo app secret hoặc ExternalSecret. SEC-13 sẽ tạo/update secret theo contract sau:

| Field                    | Value                         |
| ------------------------ | ----------------------------- |
| AWS Secrets Manager path | `techx/tf4/msk-kafka`         |
| Kubernetes Secret name   | `msk-kafka-secret`            |
| Namespace                | `techx-tf4`                   |
| App key                  | `kafka-address`               |
| Auth                     | `SASL_SSL with SCRAM-SHA-512` |
| Client port              | `9096`                        |

Payload SCRAM expected:

```json
{
    "bootstrap_servers": "b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096",
    "security_protocol": "SASL_SSL",
    "sasl_mechanism": "SCRAM-SHA-512",
    "username": "<app-user>",
    "password": "<real-password>"
}
```

### 4.4. Handoff cho REL-17

REL-17 có thể dùng các thông tin sau để chuẩn bị Kafka/orders cutover:

- MSK cluster name: `techx-tf4-orders`
- MSK cluster ARN: `arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2`
- Bootstrap brokers SASL/SCRAM: `b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096`
- Client port: `9096`
- Security group: `sg-0b15c69a8c397e9d6`
- Secret contract path: `techx/tf4/msk-kafka`
- Kubernetes Secret: `techx-tf4/msk-kafka-secret`

REL-17 vẫn cần verify topic, auth, producer/consumer compatibility và migration path trước khi cutover.

---

## 5. Rollback / Cleanup Plan

Nếu resource tạo sai hoặc cần rollback trước cutover:

1. Không đổi app traffic sang managed target.
2. Revert PR tương ứng trong source repo trước, sau đó để Terraform plan ra destroy đúng resource mới tạo.
3. Chỉ apply destroy nếu đã xác nhận resource đó chưa được SEC-13/REL-15/16/17 consume.
4. Không xóa self-hosted PostgreSQL/Valkey/Kafka trong EKS trong REL-14.
5. Không xóa secret hoặc credential thật nếu phần đó đã được SEC-13 tạo, trừ khi có approval của owner SEC-13.

Resource cleanup theo store:

- RDS: cần chú ý deletion protection/final snapshot nếu cleanup.
- ElastiCache: cần chú ý snapshot retention/final snapshot policy nếu cleanup.
- MSK: cần chú ý cluster deletion time, CloudWatch log group, KMS key pending deletion và cost phát sinh trong lúc chờ xóa.

---

## 6. Kết luận

Tính đến thời điểm cập nhật:

- RDS PostgreSQL baseline đã provision và verify PASS.
- ElastiCache Valkey baseline đã provision và verify PASS.
- MSK Kafka baseline đã provision và verify PASS.
- Không có plaintext credential trong evidence.
- Secret contract đã bám theo `sec-13-managed-data-secret-contract.md`.
- REL-14 chưa thực hiện migrate data hoặc cutover traffic.
