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

**Payload schema theo REL-14 hiện tại:**

```json
{
  "host": "<elasticache-private-endpoint>",
  "port": "6379",
  "address": "<elasticache-private-endpoint>:6379"
}
```

REL-14 hiện bật transit encryption cho ElastiCache. Secret contract vẫn dùng key
`address` để không leak endpoint trong Git, nhưng **không bật production cutover**
cho `managedData.valkey.enabled=true` cho tới khi `cart` hỗ trợ TLS connection
option. Code hiện tại tự dựng connection string với `ssl=false`, nên chỉ đổi
endpoint qua secret là chưa đủ cho managed Valkey TLS.

**Payload schema mở rộng nếu bật AUTH/TLS trong app cutover:**

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

> TLS/auth behavior thuộc REL-16 hoặc task cutover Valkey. SEC-13 chỉ chuẩn bị
> secret path, key schema và chart wiring.

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

REL-14 hiện dùng `SASL_SSL` với `SCRAM-SHA-512`. SEC-13 hiện chỉ wire
`bootstrap_servers` vào `KAFKA_ADDR` để chuẩn bị contract/app wiring tối thiểu.
Không bật `managedData.kafka.enabled=true` cho production cho tới khi Kafka
clients trong `accounting`, `checkout` và `fraud-detection` được cập nhật để đọc
và dùng `security_protocol`, `sasl_mechanism`, `username`, `password`.

> SCRAM client config và MSK cutover thuộc REL-17 hoặc task migration/cutover
> tương ứng. SEC-13 không commit secret value và không claim Kafka cutover ready.
