# SEC-13A: Managed Data Secret Contract

**Task:** CDO08-117 — [SEC-13A][Secrets] Define managed data secret contract  
**Mục tiêu:** Chốt secret name/path/key schema cho RDS, ElastiCache, MSK

## Namespace target

Tất cả Kubernetes Secrets được sync vào namespace: `techx-tf4`

## Secret Contract

### 1. RDS PostgreSQL

| Field | Value |
|---|---|
| AWS Secrets Manager path | `techx/tf4/rds-postgres` |
| Kubernetes Secret name | `rds-postgres-secret` |
| Namespace | `techx-tf4` |

**Payload schema:**

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

| Key | Source property | Consumer service |
|---|---|---|
| `dotnet-conn-string` | `connection_string_dotnet` | `accounting` |
| `go-conn-string` | `connection_string_go` | `product-catalog` |
| `python-conn-string` | `connection_string_python` | `product-reviews` |

---

### 2. ElastiCache Valkey

| Field | Value |
|---|---|
| AWS Secrets Manager path | `techx/tf4/elasticache-valkey` |
| Kubernetes Secret name | `elasticache-valkey-secret` |
| Namespace | `techx-tf4` |

**Payload schema (tối thiểu, chưa bật AUTH/TLS):**

```json
{
  "host": "<elasticache-private-endpoint>",
  "port": "6379",
  "address": "<elasticache-private-endpoint>:6379"
}
```

**Payload schema (nếu bật AUTH/TLS — chỉ sau khi `cart` service xác nhận hỗ trợ):**

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

| Key | Source property | Consumer service |
|---|---|---|
| `valkey-address` | `address` | `cart` |

---

### 3. MSK Kafka

| Field | Value |
|---|---|
| AWS Secrets Manager path | `techx/tf4/msk-kafka` |
| Kubernetes Secret name | `msk-kafka-secret` |
| Namespace | `techx-tf4` |

**Payload schema (TLS listener, không app-level auth):**

```json
{
  "bootstrap_servers": "<broker-1>:9094,<broker-2>:9094,<broker-3>:9094",
  "security_protocol": "SSL"
}
```

**Payload schema (SCRAM auth):**

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

| Key | Source property | Consumer service |
|---|---|---|
| `kafka-address` | `bootstrap_servers` | `accounting`, `checkout`, `fraud-detection` |

> MSK auth mode phải chốt với managed infra owner trước khi tạo secret thật (CDO08-118).
