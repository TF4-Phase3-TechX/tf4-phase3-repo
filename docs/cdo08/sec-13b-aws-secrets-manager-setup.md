# SEC-13B: Create AWS Secrets Manager Entries for RDS, ElastiCache, MSK

**Task:** CDO08-118 — [SEC-13B][Secrets] Create AWS Secrets Manager entries for RDS ElastiCache MSK  
**Parent:** CDO08-1061 — [CDO08-SEC-13][P0][Secrets] Wire managed data credentials through Secrets Manager and ESO

## Yêu cầu

- Region: `us-east-1`
- Secret prefix: `techx/tf4/`
- **Không commit secret value vào Git, Jira, Slack, PR description.**
- Chỉ người có quyền `secretsmanager:CreateSecret` / `secretsmanager:PutSecretValue` mới thực hiện.

## Cần có trước khi chạy

- Endpoint / ARN từ Nam (managed infra owner):
  - RDS private endpoint
  - ElastiCache private endpoint
  - MSK bootstrap servers
- App credentials (username/password) cho RDS đã được tạo ở database level.
- MSK auth mode đã chốt (TLS-only / SCRAM / IAM).

## Lệnh tạo secret

### 1. RDS PostgreSQL — `techx/tf4/rds-postgres`

Thay `<...>` bằng giá trị thật trước khi chạy. **Không lưu file này sau khi đã điền giá trị thật.**

```bash
aws secretsmanager create-secret \
  --name "techx/tf4/rds-postgres" \
  --description "RDS PostgreSQL credentials and connection strings for techx-tf4 apps" \
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

Nếu secret đã tồn tại (update value):

```bash
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/rds-postgres" \
  --secret-string '{...}' \
  --region us-east-1
```

Verify (chỉ kiểm tra key, không in value):

```bash
aws secretsmanager describe-secret \
  --secret-id "techx/tf4/rds-postgres" \
  --region us-east-1 \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate}'
```

---

### 2. ElastiCache Valkey — `techx/tf4/elasticache-valkey`

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

Nếu ElastiCache bật AUTH/TLS (chỉ sau khi xác nhận cart service support):

```bash
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/elasticache-valkey" \
  --secret-string '{
    "host": "<elasticache-private-endpoint>",
    "port": "6379",
    "address": "<elasticache-private-endpoint>:6379",
    "password": "<real-password>",
    "tls_enabled": "true"
  }' \
  --region us-east-1
```

Verify:

```bash
aws secretsmanager describe-secret \
  --secret-id "techx/tf4/elasticache-valkey" \
  --region us-east-1 \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate}'
```

---

### 3. MSK Kafka — `techx/tf4/msk-kafka`

Payload khi MSK dùng TLS listener (không app-level auth):

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

Payload nếu MSK dùng SCRAM:

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

Verify:

```bash
aws secretsmanager describe-secret \
  --secret-id "techx/tf4/msk-kafka" \
  --region us-east-1 \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate}'
```

---

## List all secrets để confirm

```bash
aws secretsmanager list-secrets \
  --region us-east-1 \
  --query 'SecretList[?starts_with(Name, `techx/tf4/`)].{Name:Name,ARN:ARN}' \
  --output table
```

Kỳ vọng thấy:
- `techx/tf4/rds-postgres`
- `techx/tf4/elasticache-valkey`
- `techx/tf4/msk-kafka`

## Rotation strategy

Sau khi cutover, rotate credential định kỳ hoặc khi có incident:

```bash
# Rotate RDS password
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/rds-postgres" \
  --secret-string '{...new-payload-with-new-password...}' \
  --region us-east-1

# ESO sẽ tự pick up trong refreshInterval (1h)
# Hoặc force sync:
kubectl -n techx-tf4 annotate externalsecret rds-postgres-secret \
  force-sync=$(date +%s) --overwrite
```

Không cần restart pod — ESO sẽ update Kubernetes Secret, app đọc lại secret từ mounted env khi restart hoặc redeploy tiếp theo.
