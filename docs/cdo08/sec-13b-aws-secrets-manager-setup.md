# SEC-13B: Create AWS Secrets Manager Entries for RDS, ElastiCache, MSK

**Task:** CDO08-118 — [SEC-13B][Secrets] Create AWS Secrets Manager entries for RDS ElastiCache MSK  
**Mục tiêu:** Tạo secret placeholders/values theo output từ Nam

## Trước khi tạo

Cần Nam (managed infra owner) cung cấp:
- RDS private endpoint
- ElastiCache private endpoint
- MSK bootstrap servers và auth mode (TLS-only / SCRAM / IAM)

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
    "host": "<rds-private-endpoint>",
    "port": "5432",
    "username": "<app-user>",
    "password": "<real-password>",
    "dbname": "otel",
    "connection_string_dotnet": "Host=<rds-private-endpoint>;Port=5432;Username=<app-user>;Password=<real-password>;Database=otel;SSL Mode=Require;Trust Server Certificate=true",
    "connection_string_go": "postgres://<app-user>:<real-password>@<rds-private-endpoint>:5432/otel?sslmode=require",
    "connection_string_python": "host=<rds-private-endpoint> port=5432 user=<app-user> password=<real-password> dbname=otel sslmode=require"
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

Payload tối thiểu (chưa bật AUTH/TLS):

```bash
aws secretsmanager create-secret \
  --name "techx/tf4/elasticache-valkey" \
  --description "ElastiCache Valkey endpoint for techx-tf4 cart service" \
  --secret-string '{
    "host": "<elasticache-private-endpoint>",
    "port": "6379",
    "address": "<elasticache-private-endpoint>:6379"
  }' \
  --region us-east-1
```

---

## 3. MSK Kafka — `techx/tf4/msk-kafka`

Payload TLS listener (không app-level auth):

```bash
aws secretsmanager create-secret \
  --name "techx/tf4/msk-kafka" \
  --description "MSK Kafka bootstrap servers for techx-tf4 apps" \
  --secret-string '{
    "bootstrap_servers": "<broker-1>:9094,<broker-2>:9094,<broker-3>:9094",
    "security_protocol": "SSL"
  }' \
  --region us-east-1
```

Payload SCRAM (nếu MSK dùng SCRAM):

```bash
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/msk-kafka" \
  --secret-string '{
    "bootstrap_servers": "<broker-1>:9096,<broker-2>:9096,<broker-3>:9096",
    "security_protocol": "SASL_SSL",
    "sasl_mechanism": "SCRAM-SHA-512",
    "username": "<app-user>",
    "password": "<real-password>"
  }' \
  --region us-east-1
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
