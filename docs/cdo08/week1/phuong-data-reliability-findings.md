# Phuong - Data Reliability Findings

**Task:** [Data] Scan Data Reliability Risks - CDO08 Week 1

| Item | Value |
|------|------|
| Owner | Phương |
| Pillar | Reliability |
| Priority | P1 |
| Week | Week 1 |
| Status | Final |

---

# 1. Executive Summary

## 1.1 Objective

Mục tiêu của báo cáo là đánh giá hiện trạng Reliability của các data component chính trong hệ thống nhằm xác định các rủi ro liên quan đến:

- Single Point of Failure (SPOF)
- Data Loss
- Persistence / Storage
- Backup / Restore
- High Availability
- Business Impact

Việc đánh giá được thực hiện thông qua:

- Static Analysis (Source Code + Helm Chart)
- Runtime Verification (Kubernetes/EKS)
- Service Dependency Analysis

---

## 1.2 Assessment Scope

| Component | Scope |
|------------|-----------------------------|
| PostgreSQL | Reliability Baseline |
| Valkey | Reliability Baseline |
| Kafka | Reliability Baseline |
| Storage | PVC / Persistence |
| High Availability | Replica / HA |
| Backup & Restore | Recovery Capability |
| Runtime | Kubernetes Verification |

---

## 1.3 Overall Result

Qua quá trình đánh giá:

- Đã kiểm tra 3 data components: PostgreSQL, Valkey và Kafka.
- Đã xác minh runtime trên namespace `techx-tf4`.
- Đã xác định nhiều khoảng trống liên quan đến Persistence, High Availability và Backup/Restore.
- Các findings đều có evidence từ source code, Helm Chart hoặc Kubernetes runtime.

---

# 2. Data Baseline

## 2.1 PostgreSQL Baseline

### Component Overview

| Item | Value |
|------|------|
| Image | postgres:17.6 |
| Deployment | Deployment |
| Replica | 1 |
| Service | ClusterIP |
| Port | 5432 |

### Runtime

| Item | Value |
|------|------|
| Pod Status | Running |
| Ready | 1/1 |
| Restart | 0 |

### Storage

| Item | Value |
|------|------|
| PVC | Not Found |
| Persistent Storage | Not Configured |
| StatefulSet | No |

### Backup / Restore

| Item | Status |
|------|--------|
| Backup | Not Found |
| Restore Guide | Not Found |
| Restore Evidence | Not Found |

### Service Dependency

| Service | Usage |
|----------|----------------|
| product-catalog | Product Data |
| product-reviews | Review Data |
| accounting | Accounting Records |

---

## 2.2 Valkey Baseline

### Component Overview

| Item | Value |
|------|------|
| Image | valkey/valkey:9.0.1-alpine3.23 |
| Deployment | Deployment |
| Replica | 1 |
| Service | ClusterIP |
| Port | 6379 |

### Runtime

| Item | Value |
|------|------|
| Pod Status | Running |
| Ready | 1/1 |
| Restart | 0 |

### Storage

| Item | Value |
|------|------|
| Persistence | Not Configured |
| PVC | Not Found |

### Monitoring

- OpenTelemetry Redis Metrics Enabled

### Service Dependency

| Service | Usage |
|----------|----------------|
| cart | Cart State Storage |

Connection

```text
VALKEY_ADDR=valkey-cart:6379
```

Business Flow

```text
Customer
     │
Frontend
     │
Cart
     │
Valkey
```

---

## 2.3 Kafka Baseline

### Component Overview

| Item | Value |
|------|------|
| Deployment | Deployment |
| Replica | 1 |
| Service | ClusterIP |
| Client Port | 9092 |
| Controller Port | 9093 |

### Runtime

| Item | Value |
|------|------|
| Pod Status | Running |
| Ready | 1/1 |
| Restart | 0 |

### Storage

| Item | Value |
|------|------|
| StatefulSet | No |
| PVC | Not Found |
| Persistence | Not Verified |

### Producer

| Service | Action |
|----------|----------------|
| checkout | Publish Order Event |

### Consumers

| Service | Action |
|----------|----------------|
| accounting | Consume Order Event |
| fraud-detection | Consume Order Event |

Event Flow

```text
Checkout
     │
     ▼
   Kafka
     │
 ┌───┴────────┐
 ▼            ▼
Accounting  Fraud Detection
```

---

## 2.4 Backup / Restore Baseline

| Component | Backup | Restore | Verification |
|------------|--------|----------|--------------|
| PostgreSQL | ❌ | ❌ | Not Found |
| Valkey | ❌ | ❌ | Not Found |
| Kafka | ❌ | ❌ | Not Found |

---

## 2.5 Runtime Verification Summary

**Verification Date**

```
2026-07-08
```

**Namespace**

```
techx-tf4
```

### Commands Executed

```bash
kubectl get pods -n techx-tf4
kubectl get svc -n techx-tf4
kubectl get deployment -n techx-tf4
kubectl get pvc -n techx-tf4
kubectl get statefulset -n techx-tf4
kubectl describe pod
kubectl logs
```

### Summary

| Verification | Result |
|-------------|--------|
| PostgreSQL Running | ✅ |
| Valkey Running | ✅ |
| Kafka Running | ✅ |
| Services Available | ✅ |
| PVC Exists | ❌ |
| Backup Verified | ❌ |
| Restore Verified | ❌ |

---

# 3. Findings

---

## DR-001 – PostgreSQL Single Point of Failure

| Field | Value |
|------|------|
| Finding ID | DR-001 |
| Pillar | Reliability |
| Component | PostgreSQL |
| Finding | PostgreSQL chỉ chạy với **1 replica** |
| Evidence | `values.yaml`, `kubectl get deployment -n techx-tf4` |
| Business Impact | Nếu Pod hoặc Node gặp sự cố, Product Catalog, Product Reviews và Accounting đều bị ảnh hưởng |
| Priority | **P0** |
| Recommendation | Đánh giá triển khai PostgreSQL High Availability |
| Owner | CDO04 |

---

## DR-002 – PostgreSQL Persistence Gap

| Field | Value |
|------|------|
| Finding ID | DR-002 |
| Pillar | Reliability |
| Component | PostgreSQL |
| Finding | Không tìm thấy PVC hoặc Persistent Storage |
| Evidence | Helm Chart, `kubectl get pvc -n techx-tf4` |
| Business Impact | Pod recreate có nguy cơ mất dữ liệu và kéo dài thời gian phục hồi |
| Priority | **P0** |
| Recommendation | Đánh giá PersistentVolumeClaim hoặc Managed Storage |
| Owner | CDO04 |

---

## DR-003 – PostgreSQL Backup / Restore Gap

| Field | Value |
|------|------|
| Finding ID | DR-003 |
| Pillar | Reliability |
| Component | PostgreSQL |
| Finding | Không tìm thấy Backup, Restore Guide hoặc Restore Evidence |
| Evidence | Helm Chart, Kubernetes Resources, Documentation |
| Business Impact | Không có bằng chứng chứng minh khả năng khôi phục dữ liệu sau sự cố |
| Priority | **P1** |
| Recommendation | Thiết kế Backup Strategy và Restore Procedure |
| Owner | CDO04 |

---

## DR-004 – Hardcoded Database Credentials

| Field | Value |
|------|------|
| Finding ID | DR-004 |
| Pillar | Security |
| Component | PostgreSQL |
| Finding | Database credentials được cấu hình trực tiếp |
| Evidence | `values.yaml`, `kubectl describe pod` |
| Business Impact | Tăng nguy cơ lộ thông tin đăng nhập, khó xoay vòng Secret |
| Priority | **P1** |
| Recommendation | Chuyển sang Kubernetes Secret hoặc AWS Secrets Manager |
| Owner | Thuỷ |

---

## DR-005 – Valkey No Persistence

| Field | Value |
|------|------|
| Finding ID | DR-005 |
| Pillar | Reliability |
| Component | Valkey |
| Finding | Không có Persistence hoặc PVC |
| Evidence | Helm Chart, `kubectl get pvc -n techx-tf4` |
| Business Impact | Pod recreate có thể làm mất Cart State, ảnh hưởng trực tiếp Checkout |
| Priority | **P0** |
| Recommendation | Đánh giá Persistent Storage hoặc Amazon ElastiCache |
| Owner | CDO04 |

---

## DR-006 – Valkey Single Point of Failure

| Field | Value |
|------|------|
| Finding ID | DR-006 |
| Pillar | Reliability |
| Component | Valkey |
| Finding | Valkey chỉ chạy với 1 replica |
| Evidence | `values.yaml`, `kubectl get deployment` |
| Business Impact | Nếu Valkey Down, Cart Service mất backend và Checkout bị ảnh hưởng |
| Priority | **P1** |
| Recommendation | Đánh giá High Availability cho Valkey |
| Owner | CDO04 |

---

## DR-007 – Kafka Single Broker

| Field | Value |
|------|------|
| Finding ID | DR-007 |
| Pillar | Reliability |
| Component | Kafka |
| Finding | Kafka chỉ chạy với 1 broker |
| Evidence | `values.yaml`, `kubectl get deployment` |
| Business Impact | Producer và Consumer đều phụ thuộc vào một broker duy nhất |
| Priority | **P1** |
| Recommendation | Đánh giá Kafka HA hoặc Amazon MSK |
| Owner | CDO04 |

---

## DR-008 – Kafka Persistence Gap

| Field | Value |
|------|------|
| Finding ID | DR-008 |
| Pillar | Reliability |
| Component | Kafka |
| Finding | Không tìm thấy Persistence hoặc PVC |
| Evidence | Helm Chart, `kubectl get pvc -n techx-tf4` |
| Business Impact | Broker failure có thể ảnh hưởng đến độ bền của Order Event |
| Priority | **P1** |
| Recommendation | Đánh giá Persistent Storage hoặc Stateful Kafka |
| Owner | CDO04 |

---

## DR-009 – Kafka Downstream Processing Risk

| Field | Value |
|------|------|
| Finding ID | DR-009 |
| Pillar | Reliability |
| Component | Kafka |
| Finding | Kafka lỗi không chặn Checkout nhưng làm gián đoạn xử lý hậu kỳ |
| Evidence | Producer (`checkout`), Consumer (`accounting`, `fraud-detection`) |
| Business Impact | Accounting không ghi sổ, Fraud Detection không xử lý Order Event |
| Priority | **P1** |
| Recommendation | Đánh giá Retry, DLQ và Monitoring |
| Owner | CDO04 |

---

## DR-010 – Missing Backup / Restore Proof

| Field | Value |
|------|------|
| Finding ID | DR-010 |
| Pillar | Reliability |
| Component | Data Platform |
| Finding | Chưa có bằng chứng Backup hoặc Restore thành công |
| Evidence | Helm Chart, Documentation, Kubernetes Resources |
| Business Impact | Chưa chứng minh được khả năng khôi phục dữ liệu khi xảy ra sự cố |
| Priority | **P1** |
| Recommendation | Xây dựng Backup Evidence và Restore Test Report |
| Owner | CDO04 |

---

# 4. Evidence

Mọi kết luận trong báo cáo đều được chứng minh bằng **Static Analysis** (Source Code/Helm Chart) và **Runtime Verification** (Kubernetes).

Verification Time: `2026-07-08`

Namespace: `techx-tf4`

---

# 4.1 PostgreSQL Evidence

## PG-01. PostgreSQL Configuration

### Static Evidence

**Source**

`techx-corp-chart/values.yaml`

**Finding**

- Image: `postgres:17.6`
- Replica: `1`
- Memory Limit: `100Mi`

**Screenshot**

> PostgreSQL configuration trong `values.yaml`

```yaml
postgresql:
  enabled: true
  useDefault:
    env: false
  imageOverride:
    repository: "postgres"
    tag: "17.6"
  replicas: 1
  service:
    port: 5432
  env:
    - name: POSTGRES_USER
      value: root
    - name: POSTGRES_PASSWORD
      value: otel
    - name: POSTGRES_DB
      value: otel
  resources:
    limits:
      memory: 100Mi
```
![PG-01](evidence/postgresql/pg-01-values.png)

---

## PG-02. PostgreSQL Deployment

### Static Evidence

**Source**

`techx-corp-chart/templates/_objects.tpl`

**Finding**

- PostgreSQL được deploy bằng `Deployment`
- Không sử dụng `StatefulSet`

```yaml 
{{- define "techx-corp.deployment" }}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .name }}
  ```
**Screenshot**

![PG-02](evidence/postgresql/pg-02-deployment-template.png)

---

## PG-03. PostgreSQL Persistence

### Static Evidence

**Source**

- `techx-corp-chart/values.yaml`
- `techx-corp-chart/templates/_objects.tpl`

**Finding**

Không tìm thấy:

- PVC
- volumeClaimTemplates
- PersistentVolume
- cấu hình storage persistence riêng cho PostgreSQL

**Evidence Note**

Helm chart hiện chỉ cấu hình PostgreSQL thông qua image, replica, environment và resources, nhưng không có volume hoặc claim để lưu trữ dữ liệu bền vững khi pod restart hoặc recreate.

---

### Runtime Evidence

**Command**

```bash
kubectl get pvc -n techx-tf4
```

**Output**

```
PS D:\AWS_WEEK\xbrain-learners\phase3\cdo8\tf4-phase3-repo> kubectl get pvc -n techx-tf4

No resources found in techx-tf4 namespace.
```

**Screenshot**

![PG-04](evidence/postgresql/pg-04-pvc.png)

---

## PG-04. PostgreSQL Runtime

### Runtime Evidence

**Command**

```bash
kubectl get deployment -n techx-tf4
```
**Output**
```
PS D:\AWS_WEEK\xbrain-learners\phase3\cdo8\tf4-phase3-repo> kubectl get deployment -n techx-tf4
NAME              READY   UP-TO-DATE   AVAILABLE   AGE
accounting        1/1     1            1           32h
ad                1/1     1            1           32h
cart              1/1     1            1           32h
checkout          1/1     1            1           32h
currency          1/1     1            1           32h
email             1/1     1            1           32h
flagd             1/1     1            1           32h
fraud-detection   1/1     1            1           32h
frontend          1/1     1            1           32h
frontend-proxy    1/1     1            1           32h
image-provider    1/1     1            1           32h
kafka             1/1     1            1           32h
llm               1/1     1            1           32h
load-generator    1/1     1            1           32h
payment           1/1     1            1           32h
postgresql        1/1     1            1           32h
product-catalog   1/1     1            1           32h
product-reviews   1/1     1            1           32h
quote             1/1     1            1           32h
recommendation    1/1     1            1           32h
shipping          1/1     1            1           32h
valkey-cart       1/1     1            1           32h
```
**Screenshot**

![PG-05](evidence/postgresql/pg-05-deployment.png)

---

**Command**

```bash
kubectl describe pod postgresql-75fff48d97-6prp2 -n techx-tf4
```

**Output**

```text
Status: Running
Image: postgres:17.6
Ready: True
Restart Count: 0
Limits:
  memory: 100Mi
Environment:
  POSTGRES_USER: root
  POSTGRES_PASSWORD: otel
Volumes:
  postgresql-init:
    Type: ConfigMap
Annotations:
  io.opentelemetry.discovery.metrics/enabled: true
```

**Screenshot**

![PG-05](evidence/postgresql/pg-05-describe-pod.png)

**Conclusion**

Runtime configuration khớp với Helm Chart và xác nhận PostgreSQL đang hoạt động bình thường.

---


**Command**

```bash
kubectl logs postgresql-75fff48d97-6prp2 -n techx-tf4
```

**Verified**

- PostgreSQL 17.6 khởi tạo thành công (`initdb` completed).
- Database initialization script (`init.sql`) được thực thi thành công.
- Các database objects (schema, table, index) được tạo thành công.
- PostgreSQL lắng nghe trên port `5432`.
- Database sẵn sàng nhận kết nối (`database system is ready to accept connections`).
- Không ghi nhận `ERROR`, `FATAL` hoặc `PANIC` trong log tại thời điểm kiểm tra.
- Checkpoint hoạt động bình thường, cho thấy database đang vận hành ổn định.

**Output**

```text
LOG:  starting PostgreSQL 17.6
LOG:  database system is ready to accept connections

/usr/local/bin/docker-entrypoint.sh: running /docker-entrypoint-initdb.d/init.sql

CREATE DATABASE
CREATE ROLE
CREATE SCHEMA
CREATE TABLE
CREATE INDEX
INSERT 0 50
INSERT 0 10

PostgreSQL init process complete; ready for start up.

LOG:  listening on IPv4 address "0.0.0.0", port 5432
LOG:  database system is ready to accept connections
```

**Screenshot**

![PG-06 - PostgreSQL Runtime Logs](evidence/postgresql/pg-06-logs.png)

**Conclusion**

Runtime logs xác nhận PostgreSQL khởi tạo thành công, thực thi đầy đủ script khởi tạo cơ sở dữ liệu, sẵn sàng nhận kết nối trên cổng `5432` và không ghi nhận lỗi nghiêm trọng tại thời điểm kiểm tra.
---

# 4.2 Valkey Evidence

## VK-01. Valkey Configuration

### Static Evidence

Source: `values.yaml`

```yaml
  valkey-cart:
    enabled: true
    useDefault:
      env: false
    imageOverride:
      repository: "valkey/valkey"
      tag: "9.0.1-alpine3.23"
    replicas: 1
    ports:
      - name: valkey-cart
        value: 6379
```

Screenshot

![VK-01](evidence/valkey/vk-01-values.png)

---

## VK-02. Cart Dependency

### Static Evidence

Source: `techx-corp-platform/src/cart/src/Program.cs`

``` yaml
var builder = WebApplication.CreateBuilder(args);
string valkeyAddress = builder.Configuration["VALKEY_ADDR"];
if (string.IsNullOrEmpty(valkeyAddress))
{
    Console.WriteLine("VALKEY_ADDR environment variable is required.");
    Environment.Exit(1);
}
```
Screenshot

![VK-02](evidence/valkey/vk-02-program.png)

---

## VK-03. Cart Service Dependency on Valkey

### Static Evidence

**Source**: `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs`

**Finding**

- Cart Service kết nối tới Valkey thông qua `ConnectionMultiplexer`.
- Cart Service sử dụng Redis Database để lưu và truy xuất Cart State.
- Cart State được lưu bằng Redis Hash và thiết lập TTL 60 phút.

**Relevant Code**

```csharp
_connectionString = $"{valkeyAddress},ssl=false,allowAdmin=true,abortConnect=false";

_redisConnectionOptions = ConfigurationOptions.Parse(_connectionString);

_redisConnectionOptions.ConnectRetry = RedisRetryNumber;
_redisConnectionOptions.ReconnectRetryPolicy = new ExponentialRetry(1000);

_redis = ConnectionMultiplexer.Connect(_redisConnectionOptions);

var cache = _redis.GetDatabase();

cache.StringSet("cart", "OK");
object res = cache.StringGet("cart");
```

```csharp
var db = _redis.GetDatabase();

// Read Cart State
var value = await db.HashGetAsync(userId, CartFieldName);

// Write Cart State
await db.HashSetAsync(
    userId,
    new[] { new HashEntry(CartFieldName, cart.ToByteArray()) }
);

// Set TTL
await db.KeyExpireAsync(userId, TimeSpan.FromMinutes(60));
```

**Conclusion**

Source code xác nhận Cart Service sử dụng Valkey làm nơi lưu trữ Cart State. Dữ liệu giỏ hàng được đọc/ghi trực tiếp vào Valkey thông qua Redis Hash (`HashGetAsync`/`HashSetAsync`) và có thời gian sống (TTL) là 60 phút. Nếu Valkey bị mất dữ liệu hoặc Pod bị recreate khi không có persistence, Cart State của người dùng có nguy cơ bị mất.
Screenshot

![VK-03](evidence/valkey/vk-03-cartstore.png)

---

## VK-04. Runtime Verification

**Command**

```bash
kubectl get deployment -n techx-tf4
```
**Output**
```
PS D:\AWS_WEEK\xbrain-learners\phase3\cdo8\tf4-phase3-repo> kubectl get deployment -n techx-tf4
NAME              READY   UP-TO-DATE   AVAILABLE   AGE
accounting        1/1     1            1           33h
ad                1/1     1            1           33h
cart              1/1     1            1           33h
checkout          1/1     1            1           33h
currency          1/1     1            1           33h
email             1/1     1            1           33h
flagd             1/1     1            1           33h
fraud-detection   1/1     1            1           33h
frontend          1/1     1            1           33h
frontend-proxy    1/1     1            1           33h
image-provider    1/1     1            1           33h
kafka             1/1     1            1           33h
llm               1/1     1            1           33h
load-generator    1/1     1            1           33h
payment           1/1     1            1           33h
postgresql        1/1     1            1           33h
product-catalog   1/1     1            1           33h
product-reviews   1/1     1            1           33h
quote             1/1     1            1           33h
recommendation    1/1     1            1           33h
shipping          1/1     1            1           33h
valkey-cart       1/1     1            1           33h
```

Screenshot

![VK-04](evidence/valkey/vk-04-deployment.png)

---

**Command**

```bash
kubectl get pvc -n techx-tf4
```
**Output**
```
PS D:\AWS_WEEK\xbrain-learners\phase3\cdo8\tf4-phase3-repo> kubectl get pvc -n techx-tf4
No resources found in techx-tf4 namespace.
```
Screenshot

![VK-05](evidence/valkey/vk-05-pvc.png)

---

**Command**

```bash
kubectl describe pod valkey-cart-5866fc4b85-ktkxq -n techx-tf4
```

**Verified**

| Item | Value |
|------|------|
| Pod Status | Running |
| Ready | True |
| Restart Count | 0 |
| Image | `valkey/valkey:9.0.1-alpine3.23` |
| Service Port | `6379/TCP` |
| Memory Request | `20Mi` |
| Memory Limit | `20Mi` |
| Environment Variables | None |
| Deployment Type | Controlled by `ReplicaSet` (Deployment) |
| OpenTelemetry Metrics | Enabled (`scraper: redis`) |
| PersistentVolumeClaim | Not Found |
| Mounted Volume | Kubernetes ServiceAccount only |

**Output**

```
Status: Running
Ready: True
Restart Count: 0

Image:
valkey/valkey:9.0.1-alpine3.23

Port:
6379/TCP

Limits:
  memory: 20Mi

Requests:
  memory: 20Mi

Environment:
  <none>

Annotations:
  io.opentelemetry.discovery.metrics/enabled: true
  io.opentelemetry.discovery.metrics/scraper: redis

Controlled By:
ReplicaSet/valkey-cart-5866fc4b85
```

**Screenshot**

![VK-04 - Valkey Runtime Configuration](evidence/valkey/vk-04-describe-pod.png)

**Conclusion**

Runtime verification xác nhận Valkey Pod đang hoạt động bình thường với image `valkey/valkey:9.0.1-alpine3.23`, expose cổng `6379`, giới hạn bộ nhớ `20Mi` và đã bật OpenTelemetry Redis metrics. Pod được quản lý bởi `Deployment` (thông qua `ReplicaSet`) và không ghi nhận PersistentVolumeClaim hoặc volume lưu trữ dữ liệu bền vững tại thời điểm kiểm tra.
---

**Command**

```bash
kubectl logs valkey-cart-5866fc4b85-ktkxq -n techx-tf4
```

**Verified**

- Valkey 9.0.1 khởi động thành công.
- Server chạy ở chế độ `standalone`.
- Valkey lắng nghe trên cổng `6379`.
- Server sẵn sàng nhận kết nối (`Ready to accept connections tcp`).
- Valkey thực hiện RDB background save định kỳ và ghi nhận trạng thái `DB saved on disk`.
- Không ghi nhận `ERROR`, `FATAL` hoặc lỗi runtime tại thời điểm kiểm tra.

**Output**

```
Valkey version=9.0.1

Running mode=standalone, port=6379.

Ready to accept connections tcp

100 changes in 300 seconds. Saving...

DB saved on disk

Background saving terminated with success
```

**Screenshot**

![VK-05 - Valkey Runtime Logs](evidence/valkey/vk-05-logs.png)

**Conclusion**

Runtime logs xác nhận Valkey hoạt động ổn định, sẵn sàng nhận kết nối trên cổng `6379` và cơ chế RDB snapshot đang hoạt động bình thường. Tuy nhiên, log chỉ chứng minh dữ liệu được ghi xuống filesystem của container; cần kết hợp với kết quả `kubectl get pvc` và `kubectl describe pod` để đánh giá khả năng lưu trữ bền vững (persistent storage).
---

# 4.3 Kafka Evidence

## KF-01. Kafka Configuration

Source: `values.yaml`
```yaml
kafka:
  enabled: true
  useDefault:
    env: true
  replicas: 1
  ports:
    - name: plaintext
      value: 9092
    - name: controller
      value: 9093
  env:
    - name: KAFKA_ADVERTISED_LISTENERS
      value: PLAINTEXT://kafka:9092
    - name: KAFKA_LISTENERS
      value: PLAINTEXT://:9092,CONTROLLER://:9093
    - name: KAFKA_CONTROLLER_LISTENER_NAMES
      value: CONTROLLER
    - name: KAFKA_CONTROLLER_QUORUM_VOTERS
      value: 1@kafka:9093
```
Screenshot

![KF-01](evidence/kafka/kf-01-values.png)

---

**Source**

`techx-corp-platform/src/checkout/kafka/producer.go`

**Finding**

- Checkout sử dụng **Sarama SyncProducer** để publish Order Event lên Kafka.
- Producer yêu cầu broker xác nhận từ tất cả replica (`RequiredAcks = WaitForAll`).
- Retry tối đa `5` lần nếu gửi thất bại.
- Timeout gửi message là `10s`.
- Producer trả về cả Success và Error để application xử lý.
- Chưa bật **Idempotent Producer** (theo comment trong source).

**Relevant Code**

```go
saramaConfig := sarama.NewConfig()

saramaConfig.Producer.Return.Successes = true
saramaConfig.Producer.Return.Errors = true

saramaConfig.Producer.RequiredAcks = sarama.WaitForAll

saramaConfig.Producer.Retry.Max = 5

saramaConfig.Producer.Timeout = 10 * time.Second

producer, err := sarama.NewSyncProducer(brokers, saramaConfig)
```

**Conclusion**

Checkout Service sử dụng Kafka SyncProducer với cấu hình **WaitForAll + Retry (5 lần)** nhằm tăng độ tin cậy khi publish Order Event. Tuy nhiên, producer **chưa bật Idempotent Producer**, do đó hệ thống vẫn theo mô hình **at-least-once delivery** và consumer cần xử lý idempotency để tránh xử lý trùng lặp.

## KF-03. Accounting Consumer

**Source**

`techx-corp-platform/src/accounting/Consumer.cs`

**Finding**

- Accounting service consume Kafka topic `orders`.
- Consumer group là `accounting`.
- Kafka broker được lấy từ biến môi trường `KAFKA_ADDR`.
- Auto commit bị tắt để tránh commit offset trước khi xử lý xong.
- Offset chỉ được commit sau khi ghi dữ liệu vào PostgreSQL thành công.
- Có idempotency check để xử lý duplicate delivery.
- Nếu parse/persist/commit lỗi, partition sẽ bị pause để tránh silent message loss.

**Relevant Code**

```csharp
private const string TopicName = "orders";

var servers = Environment.GetEnvironmentVariable("KAFKA_ADDR")
    ?? throw new InvalidOperationException("The KAFKA_ADDR environment variable is not set.");

_consumer = BuildConsumer(servers);
_consumer.Subscribe(TopicName);
```

```csharp
var conf = new ConsumerConfig
{
    GroupId = "accounting",
    BootstrapServers = servers,
    AutoOffsetReset = AutoOffsetReset.Earliest,
    EnableAutoCommit = false,
    EnableAutoOffsetStore = false
};
```

```csharp
dbContext.SaveChanges();
transaction.Commit();

// Commit Kafka offset ONLY after durable DB write succeeds.
CommitOffset(consumeResult);
```

```csharp
if (OrderAlreadyPersisted(dbContext, order))
{
    CommitOffset(consumeResult);
    return;
}
```

```csharp
_logger.LogError(ex,
    "Order persistence failed for order {OrderId} at partition {Partition} offset {Offset}: " +
    "transaction rolled back, offset NOT committed. " +
    "Partition will be paused to prevent offset advance past failed message.",
    order.OrderId, consumeResult.Partition, consumeResult.Offset);

if (!PausePartition(consumeResult.TopicPartition, consumeResult.Offset.Value))
{
    _isListening = false;
}
```

**Conclusion**

Static analysis xác nhận `accounting` là Kafka consumer của topic `orders` và có cơ chế reliability tốt hơn mức cơ bản: tắt auto commit, commit offset sau khi ghi PostgreSQL thành công, rollback khi lỗi và pause partition để tránh đọc vượt qua message lỗi. Tuy nhiên, service vẫn phụ thuộc vào Kafka và PostgreSQL; nếu Kafka down thì Accounting không nhận được Order Event, còn nếu PostgreSQL lỗi thì offset sẽ không được commit và xử lý hậu kỳ sẽ bị dừng/chậm.

**Screenshot**

![KF-03](evidence/kafka/kf-03-accounting.png)

---

## KF-04. Fraud Detection Consumer

**Source**

`techx-corp-platform/src/fraud-detection/src/main/kotlin/frauddetection/main.kt`

**Finding**

- Fraud Detection sử dụng Kafka Consumer để nhận Order Event.
- Consumer Group là `fraud-detection`.
- Subscribe topic `orders`.
- Kafka broker được lấy từ biến môi trường `KAFKA_ADDR`.
- Consumer liên tục poll Kafka để xử lý các Order Event.
- Nếu Kafka không khả dụng hoặc không có `KAFKA_ADDR`, service sẽ không thể consume message.

**Relevant Code**

```kotlin
const val topic = "orders"
const val groupID = "fraud-detection"

props[GROUP_ID_CONFIG] = groupID

val bootstrapServers = System.getenv("KAFKA_ADDR")
if (bootstrapServers == null) {
    println("KAFKA_ADDR is not supplied")
    exitProcess(1)
}

props[BOOTSTRAP_SERVERS_CONFIG] = bootstrapServers

val consumer = KafkaConsumer<String, ByteArray>(props).apply {
    subscribe(listOf(topic))
}
```

```kotlin
consumer.use {
    while (true) {
        consumer
            .poll(ofMillis(100))
            .forEach { record ->
                val orders = OrderResult.parseFrom(record.value())
                logger.info("Consumed record with orderId: ${orders.orderId}")
            }
    }
}
```

**Conclusion**

Static analysis xác nhận Fraud Detection là Kafka consumer của topic `orders`. Service liên tục poll Kafka để nhận Order Event và thực hiện xử lý phát hiện gian lận. Nếu Kafka gặp sự cố, Fraud Detection sẽ không nhận được sự kiện mới; tuy nhiên điều này **không chặn trực tiếp Checkout**, mà ảnh hưởng đến **xử lý hậu kỳ (post-checkout processing)**.

**Screenshot**

![KF-04](evidence/kafka/kf-04-fraud.png)

---

## KF-05. Runtime Verification

**Command**

```bash
kubectl get deployment -n techx-tf4
```
**Output**
```
PS D:\AWS_WEEK\xbrain-learners\phase3\cdo8\tf4-phase3-repo> kubectl get deployment -n techx-tf4
NAME              READY   UP-TO-DATE   AVAILABLE   AGE
accounting        1/1     1            1           33h
ad                1/1     1            1           33h
cart              1/1     1            1           33h
checkout          1/1     1            1           33h
currency          1/1     1            1           33h
email             1/1     1            1           33h
flagd             1/1     1            1           33h
fraud-detection   1/1     1            1           33h
frontend          1/1     1            1           33h
frontend-proxy    1/1     1            1           33h
image-provider    1/1     1            1           33h
kafka             1/1     1            1           33h
llm               1/1     1            1           33h
load-generator    1/1     1            1           33h
payment           1/1     1            1           33h
postgresql        1/1     1            1           33h
product-catalog   1/1     1            1           33h
product-reviews   1/1     1            1           33h
quote             1/1     1            1           33h
recommendation    1/1     1            1           33h
shipping          1/1     1            1           33h
valkey-cart       1/1     1            1           33h
```
Screenshot

![KF-05](evidence/kafka/kf-05-deployment.png)

---

**Command**

```bash
kubectl describe pod kafka-6684fb88c5-l428d -n techx-tf4
```

**Verified**

| Item | Value |
|------|------|
| Pod Status | Running |
| Ready | True |
| Restart Count | 0 |
| Image | `511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:2c041a7-kafka` |
| Client Port | `9092/TCP` |
| Controller Port | `9093/TCP` |
| Memory Request | `700Mi` |
| Memory Limit | `700Mi` |
| Deployment Type | Controlled by `ReplicaSet` (Deployment) |
| Kafka Advertised Listener | `PLAINTEXT://kafka:9092` |
| Kafka Listener | `PLAINTEXT://:9092, CONTROLLER://:9093` |
| Controller Quorum | `1@kafka:9093` |
| PersistentVolumeClaim | Not Found |
| Mounted Volume | Kubernetes ServiceAccount only |

**Key Output**

```text
Status: Running
Ready: True
Restart Count: 0

Image:
511825856493.dkr.ecr.us-east-1.amazonaws.com/techx-corp:2c041a7-kafka

Ports:
9092/TCP
9093/TCP

Limits:
  memory: 700Mi

Requests:
  memory: 700Mi

Environment:
KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
KAFKA_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093
KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093

Controlled By:
ReplicaSet/kafka-6684fb88c5
```

**Screenshot**

![KF-05 - Kafka Runtime Configuration](evidence/kafka/kf-05-describe-pod.png)

**Conclusion**

Runtime verification xác nhận Kafka Pod đang hoạt động bình thường với trạng thái **Running** và **Ready**. Kafka được triển khai bằng **Deployment** (thông qua `ReplicaSet`), lắng nghe trên cổng `9092` và `9093`, cấu hình **single controller quorum (`1@kafka:9093`)** và sử dụng image `techx-corp:2c041a7-kafka`. Không phát hiện **PersistentVolumeClaim (PVC)** hoặc volume lưu trữ dữ liệu bền vững được mount vào Pod tại thời điểm kiểm tra.

---

**Command**

```bash
kubectl logs kafka-6684fb88c5-l428d -n techx-tf4
```

**Verified**

- Kafka đang ghi và xoay log segment cho `__cluster_metadata`.
- Kafka KRaft snapshot được tạo thành công.
- Consumer group `accounting` đã join và rebalance thành công.
- Kafka metadata log đang nằm tại `/tmp/kafka-logs`.
- Không ghi nhận `ERROR`, `FATAL` hoặc crash trong đoạn log tại thời điểm kiểm tra.
- Log chứng minh Kafka đang hoạt động, nhưng **không chứng minh dữ liệu được lưu trên PersistentVolume**.

**Key Output**

```text
[GroupCoordinator 1]: Dynamic member with unknown member id joins group accounting
[GroupCoordinator 1]: Stabilized group accounting generation 18 with 1 members

[SnapshotGenerator id=1] Creating new KRaft snapshot file
[SnapshotEmitter id=1] Successfully wrote snapshot

[LocalLog partition=__cluster_metadata-0, dir=/tmp/kafka-logs] Rolled new log segment
[ProducerStateManager partition=__cluster_metadata-0] Wrote producer snapshot
```

**Screenshot**

![KF-06 - Kafka Runtime Logs](evidence/kafka/kf-06-logs.png)

**Conclusion**

Runtime logs xác nhận Kafka đang hoạt động, xử lý metadata log, tạo KRaft snapshot và có consumer group `accounting` kết nối thành công. Tuy nhiên, log cho thấy Kafka sử dụng đường dẫn `/tmp/kafka-logs`; cần kết hợp với `kubectl get pvc` và `kubectl describe pod` để kết luận rằng chưa có bằng chứng về persistent storage/PVC cho Kafka tại thời điểm kiểm tra.

---

# 4.4 Runtime Summary

| Component | Pod | Service | Deployment | PVC | Logs |
|------------|-----|----------|------------|-----|------|
| PostgreSQL | ✅ | ✅ | ✅ | ❌ | ✅ |
| Valkey | ✅ | ✅ | ✅ | ❌ | ✅ |
| Kafka | ✅ | ✅ | ✅ | ❌ | ✅ |

---

# 4.5 Evidence Index

| ID | Description |
|----|-------------|
| PG-01 | PostgreSQL values.yaml |
| PG-02 | PostgreSQL Deployment Template |
| PG-03 | PostgreSQL Storage Configuration |
| PG-04 | kubectl get pvc |
| PG-05 | kubectl get deployment |
| PG-06 | kubectl describe pod |
| PG-07 | kubectl logs |
| VK-01 | Valkey values.yaml |
| VK-02 | Cart Program.cs |
| VK-03 | ValkeyCartStore.cs |
| VK-04 | kubectl deployment |
| VK-05 | kubectl pvc |
| VK-06 | kubectl describe |
| VK-07 | kubectl logs |
| KF-01 | Kafka values.yaml |
| KF-02 | Producer.go |
| KF-03 | Accounting Consumer |
| KF-04 | Fraud Detection Consumer |
| KF-05 | kubectl deployment |
| KF-06 | kubectl describe |
| KF-07 | kubectl logs |

---

# 5. Backlog Candidates

| Finding ID | Candidate | Priority | Proposed Owner |
|------------|-----------|----------|----------------|
| DR-001 | PostgreSQL High Availability | P0 | CDO04 |
| DR-002 | PostgreSQL Persistent Storage | P0 | CDO04 |
| DR-003 | PostgreSQL Backup Strategy | P1 | CDO04 |
| DR-004 | PostgreSQL Secret Management | P1 | Thuỷ |
| DR-005 | Valkey Persistence | P0 | CDO04 |
| DR-006 | Valkey High Availability | P1 | CDO04 |
| DR-007 | Kafka High Availability | P1 | CDO04 |
| DR-008 | Kafka Persistent Storage | P1 | CDO04 |
| DR-009 | Kafka Retry / DLQ / Monitoring | P1 | CDO04 |
| DR-010 | Backup & Restore Validation | P1 | CDO04 |

---

# 6. Conclusion

Trong phạm vi Week 1, đã hoàn thành đánh giá Reliability cho ba data component chính của hệ thống:

- PostgreSQL
- Valkey
- Kafka

Kết quả đánh giá cho thấy:

- PostgreSQL có nguy cơ **Single Point of Failure**, chưa có Persistent Storage và chưa có bằng chứng về Backup/Restore.
- Valkey chưa cấu hình Persistence và chỉ chạy với một replica, có nguy cơ mất Cart State khi Pod bị recreate.
- Kafka hiện là single broker, chưa có bằng chứng về Persistent Storage và Backup/Restore.

Tổng cộng **10 findings** đã được ghi nhận. Mỗi finding đều có:

- Static Analysis Evidence
- Runtime Verification (EKS)
- Business Impact
- Recommendation
- Priority
- Proposed Owner

Các findings này đáp ứng Acceptance Criteria của task và có thể được sử dụng trực tiếp để xây dựng `cdo08-week1-backlog.md` cho các hoạt động cải thiện Reliability ở Week 2–3.