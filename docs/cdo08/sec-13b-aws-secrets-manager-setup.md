# SEC-13B: Create AWS Secrets Manager Entries for RDS, ElastiCache, MSK

**Task:** CDO08-118 — [SEC-13B][Secrets] Create AWS Secrets Manager entries for RDS ElastiCache MSK  
**Mục tiêu:** Tạo AWS Secrets Manager entries và nạp value thật theo output managed infra, không commit secret value vào Git

## Trước khi tạo

Không tạo dummy/placeholder value nếu ExternalSecret có thể sync vào cluster.
Chỉ tạo hoặc update secret khi đã có value thật hoặc khi change window chấp
nhận trạng thái ExternalSecret chưa Ready.

Cần Nam/managed infra owner cung cấp:
- RDS private endpoint
- ElastiCache private endpoint
- MSK bootstrap servers và auth mode (TLS-only / SCRAM / IAM)

Cần app/cutover owner xác nhận thêm:
- RDS app username/password, không dùng master/admin secret làm workload credential.
- Valkey TLS behavior đã được app hỗ trợ nếu ElastiCache bật transit encryption.
- MSK client config đã hỗ trợ SCRAM/IAM nếu MSK yêu cầu app-level auth.

Secret prefix: `techx/tf4/` — region: `us-east-1`

**Không commit secret value vào Git, Jira, Slack, PR description.**

---

## 1. RDS PostgreSQL — `techx/tf4/rds-postgres`

Điền giá trị thật từ Nam vào `<...>` rồi chạy. Key schema theo contract CDO08-117.

```bash
aws secretsmanager create-secret \
  --name "techx/tf4/rds-postgres" \
  --description "RDS PostgreSQL credentials and connection strings for techx-tf4" \
  --secret-string '{
    "host": "techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com",
    "port": "5432",
    "username": "<app-user>",
    "password": "<real-password>",
    "dbname": "otel",
    "connection_string_dotnet": "Host=techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com;Port=5432;Username=<app-user>;Password=<real-password>;Database=otel;SSL Mode=Require;Trust Server Certificate=true",
    "connection_string_go": "postgres://<app-user>:<real-password>@techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com:5432/otel?sslmode=require",
    "connection_string_python": "host=techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com port=5432 user=<app-user> password=<real-password> dbname=otel sslmode=require"
  }' \
  --region us-east-1
```

Update nếu secret đã tồn tại:

```bash
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/rds-postgres" \
  --secret-string '{...}' \
  --region us-east-1
```

---

## 2. ElastiCache Valkey — `techx/tf4/elasticache-valkey`

Payload theo contract endpoint. REL-14 hiện bật transit encryption, nên không bật
app cutover sang secret này cho tới khi `cart` hỗ trợ TLS connection option.

```bash
aws secretsmanager create-secret \
  --name "techx/tf4/elasticache-valkey" \
  --description "ElastiCache Valkey endpoint for techx-tf4 cart service" \
  --secret-string '{
    "host": "master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com",
    "port": "6379",
    "address": "master.techx-tf4-valkey-cart.pyo0mq.use1.cache.amazonaws.com:6379"
  }' \
  --region us-east-1
```

---

## 3. MSK Kafka — `techx/tf4/msk-kafka`

MSK auth mode đã chốt: `SASL_SSL with SCRAM-SHA-512`, port `9096` (REL-14).

Payload SCRAM (REL-14 dùng SASL_SSL/SCRAM-SHA-512):

```bash
aws secretsmanager create-secret \
  --name "techx/tf4/msk-kafka" \
  --description "MSK Kafka bootstrap servers for techx-tf4 apps" \
  --secret-string '{
    "bootstrap_servers": "b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096",
    "security_protocol": "SASL_SSL",
    "sasl_mechanism": "SCRAM-SHA-512",
    "username": "<app-user>",
    "password": "<real-password>"
  }' \
  --region us-east-1
```

Update nếu secret đã tồn tại:

```bash
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/msk-kafka" \
  --secret-string '{
    "bootstrap_servers": "b-1.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096,b-2.techxtf4orders.5n1354.c2.kafka.us-east-1.amazonaws.com:9096",
    "security_protocol": "SASL_SSL",
    "sasl_mechanism": "SCRAM-SHA-512",
    "username": "<app-user>",
    "password": "<real-password>"
  }' \
  --region us-east-1
```

Lưu ý: app hiện chưa tự đọc các field SCRAM ngoài `bootstrap_servers` từ
`KAFKA_ADDR`. Chỉ nạp secret SCRAM để chuẩn bị SEC-13; không bật Kafka cutover
cho tới khi REL-17 cập nhật client config.

---

## 4. MSK SCRAM Secret Association

MSK yêu cầu SCRAM secret có prefix `AmazonMSK_` trong AWS Secrets Manager.
Secret này tách biệt với `techx/tf4/msk-kafka` — một cái cho MSK authentication,
một cái cho ESO sync vào K8s.

**Bước 1: Tạo SCRAM secret với prefix `AmazonMSK_`**

```bash
aws secretsmanager create-secret \
  --name "AmazonMSK_techx-tf4-orders-app" \
  --secret-string '{"username":"<app-user>","password":"<real-password>"}' \
  --region us-east-1
```

**Bước 2: Associate SCRAM secret với MSK cluster**

```bash
aws kafka batch-associate-scram-secret \
  --cluster-arn arn:aws:kafka:us-east-1:511825856493:cluster/techx-tf4-orders/71e62f82-16ff-4111-b94d-704cccf87259-2 \
  --secret-arn-list <arn-of-scram-secret> \
  --region us-east-1
```

Lấy ARN của SCRAM secret từ output lệnh `create-secret` ở bước 1, hoặc chạy:

```bash
aws secretsmanager describe-secret \
  --secret-id "AmazonMSK_techx-tf4-orders-app" \
  --region us-east-1 \
  --query 'ARN' \
  --output text
```

---

## Verify sau khi tạo

Chỉ kiểm tra metadata, không in value:

```bash
aws secretsmanager list-secrets \
  --region us-east-1 \
  --query 'SecretList[?starts_with(Name, `techx/tf4/`)].{Name:Name,ARN:ARN}' \
  --output table
```

Kỳ vọng thấy đủ 3 entry:
- `techx/tf4/rds-postgres`
- `techx/tf4/elasticache-valkey`
- `techx/tf4/msk-kafka`
