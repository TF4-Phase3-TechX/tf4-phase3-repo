# SEC-13A: Managed Data Secret Contract

**Task:** CDO08-117 — [SEC-13A][Secrets] Define managed data secret contract  
**Parent:** CDO08-1061 — [CDO08-SEC-13][P0][Secrets] Wire managed data credentials through Secrets Manager and ESO

## Mục đích

Tài liệu này định nghĩa contract (tên secret, key schema, namespace target) cho 3 managed data services: RDS PostgreSQL, ElastiCache Valkey, MSK Kafka. Contract này là nguồn truth duy nhất được dùng bởi:

- Người tạo AWS Secrets Manager entries (CDO08-118)
- Người tạo ExternalSecret manifests trong GitOps repo (CDO08-119)
- Người wire Helm values trong app repo (CDO08-120)

## Namespace target

Tất cả Kubernetes Secrets được sync vào namespace: `techx-tf4`

## Secret Contract

### 1. RDS PostgreSQL

| Field | Value |
|---|---|
| AWS Secrets Manager name | `techx/tf4/rds-postgres` |
| Kubernetes Secret name | `rds-postgres-secret` |
| Namespace | `techx-tf4` |

**AWS Secrets Manager payload schema:**

```json
{
  "host": "<rds-private-endpoint>",
  "port": "5432",
  "username": "<app-user>",
  "password": "<real-password>",
  "dbname": "otel",
  "connection_string_dotnet": "Host=<rds-private-endpoint>;Port=5432;Username=<app-user>;Password=<real-password>;Database=otel;SSL Mode=Require;Trust Server Certificate=true",
  "connection_string_go": "postgres://<app-user>:<real-password>@<rds-private-endpoint>:5432/otel?sslmode=require",
  "connection_string_python": "host=<rds-private-endpoint> port=5432 user=<app-user> password=<real-password> dbname=otel sslmode=require"
}
```

**Kubernetes Secret keys (synced by ESO):**

| Key | Source property | Consumer |
|---|---|---|
| `dotnet-conn-string` | `connection_string_dotnet` | `accounting` |
| `go-conn-string` | `connection_string_go` | `product-catalog` |
| `python-conn-string` | `connection_string_python` | `product-reviews` |

**Notes:**
- Connection strings phải dùng private endpoint, không phải public endpoint.
- Không dùng password mặc định `otelp` của in-cluster postgres.
- SSL mode bắt buộc (`sslmode=require`).

---

### 2. ElastiCache Valkey

| Field | Value |
|---|---|
| AWS Secrets Manager name | `techx/tf4/elasticache-valkey` |
| Kubernetes Secret name | `elasticache-valkey-secret` |
| Namespace | `techx-tf4` |

**AWS Secrets Manager payload schema (tối thiểu, chưa bật AUTH/TLS):**

```json
{
  "host": "<elasticache-private-endpoint>",
  "port": "6379",
  "address": "<elasticache-private-endpoint>:6379"
}
```

**AWS Secrets Manager payload schema (nếu ElastiCache bật AUTH/TLS):**

```json
{
  "host": "<elasticache-private-endpoint>",
  "port": "6379",
  "address": "<elasticache-private-endpoint>:6379",
  "password": "<real-password>",
  "tls_enabled": "true"
}
```

**Kubernetes Secret keys (synced by ESO):**

| Key | Source property | Consumer |
|---|---|---|
| `valkey-address` | `address` | `cart` |

**Notes:**
- Chỉ bổ sung `password`/`tls_enabled` key sau khi xác nhận `cart` service hỗ trợ AUTH/TLS config.
- ElastiCache endpoint phải là private endpoint trong VPC.

---

### 3. MSK Kafka

| Field | Value |
|---|---|
| AWS Secrets Manager name | `techx/tf4/msk-kafka` |
| Kubernetes Secret name | `msk-kafka-secret` |
| Namespace | `techx-tf4` |

**AWS Secrets Manager payload schema (TLS listener, không app-level auth):**

```json
{
  "bootstrap_servers": "<broker-1>:9094,<broker-2>:9094,<broker-3>:9094",
  "security_protocol": "SSL"
}
```

**AWS Secrets Manager payload schema (SCRAM auth):**

```json
{
  "bootstrap_servers": "<broker-1>:9096,<broker-2>:9096,<broker-3>:9096",
  "security_protocol": "SASL_SSL",
  "sasl_mechanism": "SCRAM-SHA-512",
  "username": "<app-user>",
  "password": "<real-password>"
}
```

**Kubernetes Secret keys (synced by ESO):**

| Key | Source property | Consumer |
|---|---|---|
| `kafka-address` | `bootstrap_servers` | `accounting`, `checkout`, `fraud-detection` |

**Notes:**
- Auth mode cần được chốt với managed infra owner trước khi tạo secret thật.
- Nếu MSK dùng IAM auth, cần xác nhận Kafka client services hỗ trợ SASL/OAUTHBEARER trước khi cutover.
- OTel Collector cũng đang hardcode `kafka:9092` trong `kafkametrics` receiver — cần xác nhận scope sau khi Kafka cutover.

---

## App env wiring map

| Service | Env var | Kubernetes Secret | Key |
|---|---|---|---|
| `accounting` | `DB_CONNECTION_STRING` | `rds-postgres-secret` | `dotnet-conn-string` |
| `product-catalog` | `DB_CONNECTION_STRING` | `rds-postgres-secret` | `go-conn-string` |
| `product-reviews` | `DB_CONNECTION_STRING` | `rds-postgres-secret` | `python-conn-string` |
| `cart` | `VALKEY_ADDR` | `elasticache-valkey-secret` | `valkey-address` |
| `accounting` | `KAFKA_ADDR` | `msk-kafka-secret` | `kafka-address` |
| `checkout` | `KAFKA_ADDR` | `msk-kafka-secret` | `kafka-address` |
| `fraud-detection` | `KAFKA_ADDR` | `msk-kafka-secret` | `kafka-address` |

## Checklist trước khi cutover

- [ ] Auth mode MSK đã chốt với managed infra owner
- [ ] ElastiCache AUTH/TLS support của `cart` đã xác nhận
- [ ] Endpoint/ARN từ Nam đã cung cấp
- [ ] Secret values đã tạo trong AWS Secrets Manager (không paste vào Git/Jira/Slack)
- [ ] ExternalSecret Ready=True trước khi flip managed mode trong app
