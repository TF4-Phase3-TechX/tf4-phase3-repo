# Khảo sát trước khi tiếp quản hệ thống — Phase 3

> **Phạm vi khảo sát:** thư mục `phase3/`  
> **Ngày khảo sát:** 06/07/2026  
> **Cách đọc tài liệu:** các nhận định dưới đây được rút ra từ source code và cấu hình có trong repository. Những nội dung phụ thuộc vào cluster, AWS hoặc traffic thực tế đều được đánh dấu **cần xác minh sau khi deploy**.

---

## 1. Mục đích tài liệu

Tài liệu này giúp TF nắm nhanh hệ thống trước khi bắt đầu Phase 3:

- Hệ thống đang có những thành phần nào và chúng liên kết với nhau ra sao.
- Luồng nào ảnh hưởng trực tiếp đến khách hàng, doanh thu và SLO.
- Điểm mạnh đã có sẵn, rủi ro cần kiểm chứng và các việc nên ưu tiên trong Tuần 1.
- Các câu hỏi cần trả lời bằng bằng chứng sau khi deploy, thay vì suy đoán từ source code.

Tài liệu không thay thế việc kiểm tra runtime. Hãy xem đây là **bản đồ để bắt đầu tiếp quản**, sau đó xác thực lại bằng Grafana, Jaeger, logs, `kubectl`, AWS Cost Explorer và các bài kiểm thử tải.

---

## 2. Tóm tắt hệ thống

TechX Corp Platform là một storefront thương mại điện tử chạy trên Kubernetes. Kiến trúc dùng nhiều microservice viết bằng nhiều ngôn ngữ, giao tiếp chủ yếu qua gRPC; một số luồng dùng HTTP hoặc Kafka. Hệ thống có PostgreSQL, Valkey, Kafka, một tính năng AI cho review sản phẩm và observability stack gồm OpenTelemetry Collector, Prometheus, Jaeger, OpenSearch và Grafana.

### 2.1 Các luồng quan trọng


| Luồng                 | Đường đi chính                                                                      | Ý nghĩa                                       |
| --------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------- |
| Duyệt và tìm sản phẩm | `frontend` → `product-catalog` → PostgreSQL                                         | Trải nghiệm cửa hàng và khả năng tìm sản phẩm |
| Xem review và hỏi AI  | `frontend` → `product-reviews` → PostgreSQL / `llm`                                 | Tính năng AI trọng tâm trên trang sản phẩm    |
| Giỏ hàng              | `frontend` / `checkout` → `cart` → Valkey                                           | Giữ trạng thái mua hàng của khách             |
| Đặt hàng              | `frontend` → `checkout` → cart, catalog, currency, shipping, payment, email → Kafka | Luồng doanh thu quan trọng nhất               |
| Xử lý sau đặt hàng    | Kafka → `accounting`, `fraud-detection`                                             | Ghi nhận đơn hàng và phát hiện rủi ro         |


**Checkout là luồng cần ưu tiên bảo vệ nhất** vì đây là nơi chuyển đổi thành doanh thu. SLO hiện đặt mức thành công cho checkout là **≥ 99,0%**.

### 2.2 Những thành phần cần chú ý ngay

- `frontend-proxy` và `frontend` là entrypoint cho khách hàng.
- `checkout`, `payment`, `cart`, `product-catalog`, `shipping` và `currency` tạo thành `checkout path`.
- PostgreSQL, Valkey và Kafka đang là các dependency nền tảng cho dữ liệu và sự kiện.
- OpenTelemetry, Prometheus, Jaeger, OpenSearch và Grafana là nguồn dữ liệu để đo SLO, tìm bottleneck và phục vụ incident investigation.
- `flagd` và các hook OpenFeature tạo thành `fault-injection mechanism` do BTC quản lý. Không được gỡ, tắt hoặc đổi hướng cơ chế này.

### 2.3 Nhận định ban đầu từ source code và cấu hình


| Khu vực       | Nhận định                                                                                | Tác động cần theo dõi                                                       |
| ------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Checkout      | Gọi nhiều dependency theo thứ tự; một dependency lỗi có thể làm checkout thất bại        | Ảnh hưởng trực tiếp đến SLO và doanh thu                                    |
| Availability  | Cấu hình mặc định có `replicas: 1`; chưa thấy HPA/PDB trong chart                        | Rủi ro khi pod, node hoặc tải gặp vấn đề                                    |
| Data layer    | PostgreSQL, Valkey và Kafka chạy in-cluster với một replica trong baseline               | Có thể tạo single point of failure (SPOF)                                   |
| Observability | Prometheus, OpenSearch và Jaeger chưa có persistence rõ ràng trong baseline              | Có thể mất lịch sử khi pod restart                                          |
| AI            | Mặc định dùng mock LLM; có `fault-injection flags` cho rate limit và inaccurate response | Cần đánh giá chất lượng, fallback, latency và chi phí                       |
| Security      | Grafana anonymous Admin, OpenSearch tắt security plugin trong values mẫu                 | Cần xác minh public exposure thực tế trước khi đánh giá mức độ nghiêm trọng |


**Tham chiếu source code:** `onboarding/ARCHITECTURE.md`, `onboarding/SLO.md`, `onboarding/INCIDENT_HISTORY.md`, `techx-corp-chart/values.yaml`, `techx-corp-platform/src/checkout/main.go`.

---

## 3. Bản đồ repository

### 3.1 Cấu trúc thư mục gốc


| Đường dẫn              | Vai trò trong Phase 3                                                  |
| ---------------------- | ---------------------------------------------------------------------- |
| `README.md`            | Giới thiệu nhanh về Phase 3 và cấu trúc repository                     |
| `RULES.md`             | Thể lệ, năm trụ CDO, trụ AI, timeline, deliverables và luật disqualify |
| `GETTING_STARTED.md`   | Quy trình build image, push ECR, deploy bằng Helm và kiểm tra baseline |
| `onboarding/`          | Kiến trúc, SLO, ngân sách, lịch sử sự cố và hướng dẫn pitch            |
| `mandates/`            | Nơi BTC đặt các directive bắt buộc trong quá trình vận hành            |
| `deploy/`              | Script build/push, values overlay và ResourceQuota                     |
| `techx-corp-platform/` | Source code của các service, Docker Compose và cấu hình local          |
| `techx-corp-chart/`    | Helm chart để deploy ứng dụng và observability stack                   |


### 3.2 Khu vực cần đọc trước


| Khu vực                          | Nội dung nên khai thác                                                            |
| -------------------------------- | --------------------------------------------------------------------------------- |
| `onboarding/ARCHITECTURE.md`     | Bản đồ service, dependency và các luồng khách hàng                                |
| `onboarding/SLO.md`              | Mục tiêu dịch vụ và error budget                                                  |
| `onboarding/BUDGET.md`           | Trần chi phí khoảng `$300/tuần/TF` và các đánh đổi cần chứng minh                 |
| `onboarding/INCIDENT_HISTORY.md` | Những điểm yếu từng xuất hiện: quá tải DB, mất cart và deploy thiếu readiness     |
| `onboarding/PITCH_GUIDE.md`      | Cách xếp hạng backlog theo rủi ro × tác động kinh doanh                           |
| `GETTING_STARTED.md`             | Lệnh và thứ tự để đưa baseline lên EKS                                            |
| `techx-corp-chart/values.yaml`   | Cấu hình thực tế của thành phần, tài nguyên, bảo mật, observability và data layer |
| `techx-corp-chart/templates/`    | Khả năng mà chart đã hỗ trợ nhưng values chưa chắc đã bật                         |
| `deploy/values-flagd-sync.yaml`  | Overlay bắt buộc để dùng central fault-injection flag source của BTC              |


### 3.3 Các nhóm source code chính


| Nhóm       | Thành phần tiêu biểu                                                                        | Vai trò                                             |
| ---------- | ------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| Storefront | `frontend-proxy`, `frontend`, `image-provider`                                              | Nhận request của khách, hiển thị web và phục vụ ảnh |
| Product    | `product-catalog`, `product-reviews`, `recommendation`, `ad`, `llm`                         | Danh mục, review, AI, gợi ý và quảng cáo            |
| Order      | `cart`, `checkout`, `payment`, `shipping`, `quote`, `currency`, `email`                     | Xử lý giỏ hàng và đơn hàng                          |
| Event      | `kafka`, `accounting`, `fraud-detection`                                                    | Publish và consume sự kiện đơn hàng                 |
| Data       | PostgreSQL, Valkey                                                                          | Lưu catalog, review, accounting và cart             |
| Operations | OpenTelemetry Collector, Prometheus, Jaeger, OpenSearch, Grafana, `load-generator`, `flagd` | Observability, load generation và fault injection   |


---

## 4. Kiến trúc và các luồng chính

### 4.1 Mô hình giao tiếp

- Khách hàng đi vào hệ thống qua `frontend-proxy` (Envoy) tại cổng `8080`.
- `frontend` là storefront Next.js, gọi các backend service qua gRPC.
- Giao tiếp HTTP chủ yếu xuất hiện ở các service như `shipping`, `quote`, `email` và LLM endpoint.
- `checkout` publish sự kiện đơn hàng vào Kafka; `accounting` và `fraud-detection` thực hiện `asynchronous processing`.
- Service phát telemetry về OpenTelemetry Collector; Collector gửi dữ liệu tiếp đến Prometheus, Jaeger và OpenSearch.

```mermaid
flowchart LR
  U[Khách hàng] --> P[frontend-proxy / Envoy]
  P --> F[frontend / Next.js]

  F --> CATALOG[product-catalog]
  F --> REVIEW[product-reviews]
  F --> CART[cart]
  F --> CHECKOUT[checkout]
  F --> REC[recommendation]
  F --> AD[ad]

  CATALOG --> PG[(PostgreSQL)]
  REVIEW --> PG
  REVIEW --> LLM[llm]
  CART --> VK[(Valkey)]

  CHECKOUT --> CART
  CHECKOUT --> CATALOG
  CHECKOUT --> CUR[currency]
  CHECKOUT --> SHIP[shipping]
  SHIP --> QUOTE[quote]
  CHECKOUT --> PAY[payment]
  CHECKOUT --> MAIL[email]
  CHECKOUT --> K[(Kafka)]

  K --> ACC[accounting]
  K --> FRAUD[fraud-detection]
  ACC --> PG

  F -. OTLP .-> OTEL[OpenTelemetry Collector]
  CHECKOUT -. OTLP .-> OTEL
  CATALOG -. OTLP .-> OTEL
  CART -. OTLP .-> OTEL
  REVIEW -. OTLP .-> OTEL
  OTEL --> PROM[Prometheus]
  OTEL --> JAEGER[Jaeger]
  OTEL --> OS[OpenSearch]
  PROM --> G[Grafana]
  JAEGER --> G
  OS --> G
```

### 4.2 Luồng checkout

Checkout là một orchestrator. Khi người dùng đặt hàng, service này lần lượt lấy cart, kiểm tra sản phẩm, quy đổi giá, lấy phí ship, thanh toán, tạo vận đơn, xóa cart, gửi email và publish sự kiện đơn hàng.

```mermaid
sequenceDiagram
  participant U as Khách hàng
  participant F as frontend
  participant C as checkout
  participant Cart as cart
  participant Cat as product-catalog
  participant Cur as currency
  participant Ship as shipping
  participant Pay as payment
  participant Email as email
  participant K as Kafka

  U->>F: POST /api/checkout
  F->>C: gRPC PlaceOrder
  C->>Cart: GetCart
  C->>Cat: GetProduct
  C->>Cur: Convert
  C->>Ship: Get quote
  C->>Pay: Charge
  C->>Ship: Ship order
  C->>Cart: EmptyCart
  C->>Email: Send confirmation
  C->>K: Publish order event
  F-->>U: Kết quả đặt hàng
```

Ý nghĩa vận hành:

- Các `synchronous dependency` trên `checkout path` cần timeout, retry và fallback có chủ đích.
- Tối ưu một service đơn lẻ chưa đủ; cần xem toàn bộ trace checkout để biết dependency nào là bottleneck.
- Kafka lỗi hoặc lag không nhất thiết làm request khách hàng lỗi ngay, nhưng có thể gây chậm accounting/fraud và tạo khoảng trống audit.

### 4.3 Luồng AI cho review sản phẩm

`product-reviews` cung cấp review, điểm trung bình và tính năng hỏi AI. Service đọc review từ PostgreSQL, có thể lấy thêm thông tin sản phẩm từ `product-catalog`, sau đó gọi endpoint OpenAI-compatible.

```mermaid
sequenceDiagram
  participant U as Khách hàng
  participant F as frontend
  participant R as product-reviews
  participant DB as PostgreSQL
  participant C as product-catalog
  participant L as llm
  participant Flag as flagd

  U->>F: Hỏi AI trên trang sản phẩm
  F->>R: AskProductAIAssistant
  R->>Flag: Đọc feature flag
  R->>L: Chat completion
  L-->>R: Tool calls
  R->>DB: Lấy review
  R->>C: Lấy thông tin sản phẩm khi cần
  R->>L: Tổng hợp kết quả
  L-->>R: Câu trả lời
  R-->>F: Phản hồi AI
```

Lưu ý: mock LLM phục vụ baseline không đại diện cho chất lượng, latency hoặc chi phí khi dùng LLM thật. Trước khi bật model thật, cần có eval set, fallback và cách đo cost per AI request.

### 4.4 Dữ liệu và luồng sự kiện


| Thành phần | Dùng cho                      | Điểm cần theo dõi                                                           |
| ---------- | ----------------------------- | --------------------------------------------------------------------------- |
| PostgreSQL | Catalog, review và accounting | Connection pool, query latency, saturation, backup và persistence           |
| Valkey     | Trạng thái giỏ hàng           | TTL, restart, persistence, replica và nguy cơ cart loss                     |
| Kafka      | Sự kiện đơn hàng              | Producer acknowledgment, consumer lag, retry, backlog và nguy cơ event loss |
| OpenSearch | Logs                          | Retention, persistence, exposure và chi phí                                 |
| Prometheus | Metrics                       | Retention, cardinality, persistence và SLO query                            |
| Jaeger     | Traces                        | Retention, sampling và khả năng phục vụ incident investigation sau sự cố    |


---

## 5. Danh mục service theo trách nhiệm


| Service              | Chức năng chính                                    | Dependency quan trọng                            | Ghi chú vận hành                                                            |
| -------------------- | -------------------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------- |
| `frontend-proxy`     | `entrypoint`, route storefront và observability UI | frontend, Grafana, Jaeger, load generator, flagd | Cần xác minh service có `public exposure` hay chỉ truy cập qua port-forward |
| `frontend`           | Storefront và API routes                           | Các service gRPC                                 | Là điểm nhìn gần nhất với trải nghiệm khách                                 |
| `product-catalog`    | List, get và search sản phẩm                       | PostgreSQL, flagd                                | Search dùng `LOWER(...) LIKE`; cần đo khi tải lớn                           |
| `product-reviews`    | Review, điểm trung bình và AI assistant            | PostgreSQL, LLM, product catalog, flagd          | Cần eval AI và xử lý rate limit                                             |
| `llm`                | Mock OpenAI-compatible LLM                         | flagd                                            | Có thể thay bằng endpoint thật qua overlay                                  |
| `cart`               | Thao tác giỏ hàng                                  | Valkey, flagd                                    | Có retry reconnect; cart vẫn phụ thuộc Valkey                               |
| `checkout`           | Checkout orchestration                             | Nhiều dependency + Kafka                         | Revenue-critical, nên ưu tiên tracing và alert                              |
| `payment`            | Mock charge processing                             | flagd                                            | Cần readiness, failure rate và log review                                   |
| `shipping` / `quote` | Tính phí và tạo thông tin ship                     | quote                                            | Một phần checkout flow                                                      |
| `currency`           | Quy đổi tiền tệ                                    | —                                                | `Synchronous dependency` của checkout                                       |
| `email`              | Gửi xác nhận đơn hàng                              | flagd                                            | Có `memory-leak fault-injection flag`                                       |
| `recommendation`     | Gợi ý sản phẩm                                     | product-catalog, flagd                           | Cần xem cache/failure behavior                                              |
| `ad`                 | Quảng cáo theo ngữ cảnh                            | flagd                                            | Có `fault-injection flags` cho CPU/GC/failure                               |
| `accounting`         | Lưu order event                                    | Kafka, PostgreSQL                                | Cần xác nhận event được consume và persist                                  |
| `fraud-detection`    | Consume sự kiện để phát hiện rủi ro                | Kafka, flagd                                     | Là nơi phù hợp để theo dõi consumer lag                                     |
| `load-generator`     | Load generation bằng Locust                        | frontend-proxy, flagd                            | Dùng cho baseline và kiểm thử sau thay đổi                                  |
| `flagd`              | Feature flags và fault-injection paths             | Central flag source của BTC                      | Là hạ tầng được bảo vệ                                                      |


**Tham chiếu source code:** `onboarding/ARCHITECTURE.md`, `pb/demo.proto`, `src/checkout/main.go`, `src/product-reviews/product_reviews_server.py`, `src/cart/`, `src/accounting/Consumer.cs`, `src/fraud-detection/`.

---

## 6. Build, deploy và nền tảng Kubernetes

### 6.1 Quy trình baseline

1. Kiểm tra quyền AWS, context Kubernetes, Helm, Docker buildx và ECR.
2. Build toàn bộ app image từ source, sau đó push vào ECR của TF.
3. Build Helm dependencies.
4. Deploy chart với repository ECR của TF, observability overlay và **bắt buộc** có `values-flagd-sync.yaml`.
5. Kiểm tra pod, truy cập storefront, tạo một đơn thử và xác nhận traces/logs/event flow.

### 6.2 Helm chart hiện có

Chart đã hỗ trợ nhiều khả năng cần thiết:

- Deployment, Service, Ingress, ConfigMap.
- `replicas`, `nodeSelector`, affinity, tolerations.
- `securityContext`, sidecar, init container, volume.
- Liveness probe và readiness probe.

Tuy nhiên, source hiện cho thấy một số điểm cần xác minh sau deploy:


| Hạng mục   | Hiện trạng từ values                                             | Việc cần xác minh                                                          |
| ---------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Replica    | Mặc định `replicas: 1`                                           | Thành phần nào thực sự đang có nhiều replica                               |
| HPA / PDB  | Chưa thấy manifest baseline                                      | Có HPA/PDB được thêm bởi overlay hoặc runtime không                        |
| Probe      | Template hỗ trợ nhưng baseline chưa thể hiện đầy đủ              | Rendered manifest có readiness/liveness cho các service revenue path không |
| Resource   | Nhiều service có memory limit nhưng chưa thấy requests nhất quán | Pod QoS, scheduler behavior, throttling, OOM và mức dùng thực tế           |
| Scheduling | Node selector, affinity, toleration mặc định rỗng                | Workload đang nằm ở node/AZ nào                                            |
| Ingress    | Template có hỗ trợ, baseline chưa thấy bật                       | `frontend-proxy` được expose ra ngoài bằng cách nào                        |


### 6.3 Dependency chạy trong cluster


| Dependency          | Baseline                                                  | Rủi ro cần đánh giá                                                   |
| ------------------- | --------------------------------------------------------- | --------------------------------------------------------------------- |
| PostgreSQL          | Deployment in-cluster, một replica                        | Dữ liệu, backup, persistence, credential, connection pool và failover |
| Valkey              | In-cluster, một replica                                   | cart state loss khi pod/node bị ảnh hưởng                             |
| Kafka               | KRaft single broker, một replica                          | Lag, event delivery, consumer recovery và event durability            |
| flagd               | In-cluster, sync read-only từ BTC khi deploy đúng overlay | Không được đổi flag source hoặc vô hiệu hóa                           |
| Observability stack | Cài qua subchart                                          | Memory footprint, persistence, retention và cost                      |


### 6.4 Những phần chưa có trong repository

Repository không chứa Terraform/CDK cho EKS, VPC, node group, IAM/IRSA, autoscaler/Karpenter, load balancer, NAT, storage class hoặc AWS tagging policy. Đây là các thông tin phải thu thập trong Tuần 1 trước khi đưa ra kết luận về security, availability hoặc cost.

---

## 7. Observability và vận hành

### 7.1 Luồng telemetry

```mermaid
flowchart TD
  S[Ứng dụng và hạ tầng] -->|OTLP| C[OpenTelemetry Collector]
  C -->|Metrics| P[Prometheus]
  C -->|Traces| J[Jaeger]
  C -->|Logs| O[OpenSearch]
  P --> G[Grafana]
  J --> G
  O --> G
  G --> A[Alerting]
```

Collector nhận OTLP cùng một số metrics Kubernetes, host và Kafka. Các dashboard có sẵn gồm các dashboard liên quan đến NGINX, APM, OpenTelemetry Collector, PostgreSQL, span metrics và hệ thống demo.

### 7.2 Điều đã có và khoảng trống ban đầu


| Đã có                                               | Cần bổ sung hoặc xác minh                                             |
| --------------------------------------------------- | --------------------------------------------------------------------- |
| Metrics, logs, traces, dashboard và load generator  | SLO dashboard cho storefront, cart và checkout                        |
| Jaeger để theo dõi distributed trace                | Alert cho checkout, payment, DB saturation, Kafka lag và error budget |
| Một alert cho cart latency                          | Kênh alert có gửi được đến email/Slack/on-call thực tế không          |
| `Fault-injection flags` để kiểm thử fault tolerance | Retention và persistence của Prometheus, OpenSearch, Jaeger           |
| Transform giảm cardinality của Next.js span name    | Query và label thực tế sau khi deploy                                 |


### 7.3 Các chỉ số baseline cần đo trong Tuần 1


| Nhóm       | Chỉ số cần ghi nhận                                                 | Lý do                                         |
| ---------- | ------------------------------------------------------------------- | --------------------------------------------- |
| Storefront | Non-5xx rate, p95 latency theo route                                | Đối chiếu SLO browse/search                   |
| Cart       | Tỷ lệ thành công và latency của Add/Get/Empty                       | Cart có SLO ≥ 99,5%                           |
| Checkout   | Success rate, p95/p99, error theo dependency                        | Luồng doanh thu có SLO ≥ 99,0%                |
| Dependency | Latency/error của catalog, shipping, payment, email, currency       | Xác định bottleneck trong trace               |
| PostgreSQL | Connection, query latency, cache hit, deadlock, saturation          | Liên quan trực tiếp lịch sử sự cố INC-1       |
| Valkey     | Latency, errors, memory, restart                                    | Liên quan lịch sử mất cart INC-2              |
| Kafka      | Producer errors, consumer lag, topic throughput                     | Bảo vệ accounting, fraud và audit             |
| AI         | Request count, 429/error, latency, token/cost, eval pass rate       | Bảo đảm không đưa phản hồi sai lệch đến khách |
| Cost       | Chi phí/ngày, cost per 1.000 requests, cost per successful checkout | Chứng minh hiệu quả trong ngân sách           |


---

## 8. Tính năng AI

### 8.1 Hiện trạng

Tính năng AI nằm ở trang review sản phẩm:

- UI có các quick prompt như tóm tắt review, đề xuất theo độ tuổi và tìm phản hồi tiêu cực.
- `product-reviews` gọi endpoint OpenAI-compatible bằng OpenAI SDK.
- Service dùng tool-calling để lấy review và thông tin sản phẩm trước khi tổng hợp câu trả lời.
- Mặc định dùng `llm` mock; có overlay `deploy/values-aio-llm.yaml` để kết nối LLM thật qua Kubernetes Secret.

### 8.2 Rủi ro và cách kiểm chứng


| Rủi ro                                     | Cách kiểm chứng phù hợp                                                                 |
| ------------------------------------------ | --------------------------------------------------------------------------------------- |
| Tóm tắt sai hoặc hallucinate thông tin     | Xây dựng eval set từ review/product facts; đo tỷ lệ pass và kiểm tra manual             |
| Rate limit hoặc LLM endpoint `unavailable` | Bật `fault-injection flag`, kiểm thử timeout, retry, fallback và trải nghiệm UI         |
| `High latency`                             | Tách latency của LLM trong trace; đo p95 theo model/route                               |
| Chi phí khó kiểm soát                      | Ghi nhận token, request volume, cost per AI request và cost per đơn hàng                |
| Prompt/content `data leakage`              | Review `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` trước khi dùng dữ liệu thật |
| Quản lý secret                             | Xác minh secret có tồn tại, không có `secret exposure` qua logs và không hard-code key  |


Nguyên tắc: AI là best-effort, nhưng **không được hiển thị tóm tắt sai lệch cho khách**. Khi chưa đủ tự tin, fallback rõ ràng và minh bạch tốt hơn trả lời chắc chắn nhưng không đúng.

---

## 9. Đánh giá theo năm trụ CDO


| Trụ                    | Điểm đã có                                                                             | Rủi ro hoặc khoảng trống cần xác minh                                                                                               | Ưu tiên hợp lý trong Tuần 1                                                        |
| ---------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Security               | Một số thành phần chạy non-root; LLM key dùng Kubernetes Secret                        | Grafana anonymous Admin, OpenSearch tắt security plugin, credential tĩnh, chưa có bằng chứng về NetworkPolicy/IRSA                  | Xác minh public exposure, ranh giới truy cập, logs có dữ liệu nhạy cảm hay không   |
| Reliability            | Health service ở nhiều service, init container chờ dependency, cart có reconnect retry | Single replica, chưa thấy probe/HPA/PDB đầy đủ, data layer in-cluster single instance, Kafka producer acknowledgment cần kiểm chứng | Kiểm tra rendered manifest, pod restart, rollout, node drain và dependency failure |
| Performance Efficiency | Có span metrics, RED metrics, Locust, trace và custom cart histogram                   | Chưa có right-sizing từ usage thật, search query có thể chậm khi scale, không có autoscaling baseline                               | Tạo baseline load test, trace bottleneck, đo CPU/memory                            |
| Cost Optimization      | Có ResourceQuota và ngân sách mục tiêu                                                 | Chưa có AWS Budgets/Anomaly Detection/IaC tagging; chưa biết chi phí thực tế của node, observability, mạng                          | Bật cảnh báo chi phí, ghi daily burn và unit cost                                  |
| Auditability           | Rules yêu cầu ADR, decision log và postmortem; OTel logs/traces hỗ trợ điều tra        | Deploy hiện thiên về Helm thủ công; chưa thấy CloudTrail/K8s audit/retention và template vận hành                                   | Tạo ADR/runbook/postmortem, ghi lại deploy và ownership                            |


### 9.1 Liên hệ với lịch sử sự cố


| Sự cố cũ                                          | Bài học nên áp dụng                                                                 |
| ------------------------------------------------- | ----------------------------------------------------------------------------------- |
| INC-1: checkout chậm/lỗi do cạn DB connection     | Baseline load test, theo dõi pool/saturation, timeout và alert sớm                  |
| INC-2: mất cart khi node được lên lịch lại        | Đánh giá Valkey durability, persistence/replica/managed option và trade-off chi phí |
| INC-3: lỗi payment khi deploy vì pod chưa `Ready` | Chuẩn hóa readiness/liveness, rollout có kiểm soát và rollback test                 |


---

## 10. `flagd` và fault injection

### 10.1 Quy tắc bắt buộc

`flagd` và các hook OpenFeature là `fault-injection infrastructure` được BTC bảo vệ. Khi deploy, TF phải dùng `deploy/values-flagd-sync.yaml` để flagd `sync` từ central source ở chế độ `read-only`.

Không được:

- Gỡ, tắt, refactor để core service không còn đọc incident flag.
- Đổi endpoint hoặc flag source để né sự cố.
- Bật lại local UI để thay đổi `flag` trong chế độ BTC sync.
- Bỏ `-f deploy/values-flagd-sync.yaml` trong lần `helm upgrade`.

Hướng xử lý đúng là làm hệ thống chịu lỗi tốt hơn: timeout, retry, circuit breaker, fallback, containment, alerting và rollback an toàn.

### 10.2 Các nhóm `fault-injection flags` có sẵn


| Nhóm                | Fault-injection flags                                     | Ý nghĩa kiểm thử                         |
| ------------------- | --------------------------------------------------------- | ---------------------------------------- |
| AI                  | `llmInaccurateResponse`, `llmRateLimitError`              | Chất lượng AI, rate limit và fallback    |
| Product             | `productCatalogFailure`, `recommendationCacheFailure`     | Dependency product không ổn định         |
| Cart                | `cartFailure`, `failedReadinessProbe`                     | Khả năng xử lý lỗi cart và readiness     |
| Payment             | `paymentFailure`, `paymentUnreachable`                    | Bảo vệ checkout trước lỗi payment        |
| Kafka               | `kafkaQueueProblems`                                      | Producer overload, consumer delay và lag |
| Load/edge           | `loadGeneratorFloodHomepage`, `imageSlowLoad`             | Chịu tải và trải nghiệm storefront       |
| Service degradation | `adManualGc`, `adHighCpu`, `adFailure`, `emailMemoryLeak` | Saturation, lỗi service và leak          |


---

## 11. Kế hoạch Tuần 1

### 11.1 Mục tiêu cuối tuần

Cuối Tuần 1, TF nên có đủ bằng chứng để nói rõ:

1. Baseline đã chạy trên account của TF.
2. Một luồng checkout hoàn chỉnh đã được xác minh bằng trace, logs và Kafka consumer.
3. Đã có số liệu SLO, tải, resource và chi phí ban đầu.
4. Có sổ đăng ký rủi ro (risk register), backlog ưu tiên và các việc chủ động **không làm ngay**.
5. Pitch được bảo vệ bằng rủi ro × tác động kinh doanh × chi phí × kế hoạch rollback.

### 11.2 Danh sách ưu tiên


| #   | Công việc                             | Kết quả cần có                                                                                      | Ưu tiên |
| ---: | ------------------------------------- | --------------------------------------------------------------------------------------------------- | ------- |
| 1   | Xác nhận quyền truy cập và workspace  | AWS identity, region, EKS context, namespace, ECR, tool version, owner rõ ràng                      | P0      |
| 2   | Build/push toàn bộ app image vào ECR  | Danh sách image, tag/digest, build log và lệnh tái lập                                              | P0      |
| 3   | Deploy baseline với flagd sync        | Helm release, rendered values, pod trạng thái Ready hoặc exception có giải thích                    | P0      |
| 4   | Kiểm tra luồng nghiệp vụ end-to-end   | Storefront, product, AI, cart, checkout, accounting/fraud consume; có bằng chứng từ order/trace/log | P0      |
| 5   | Tạo baseline SLO, performance và cost | p95, error rate, checkout success, CPU/memory, Kafka lag, DB health, daily burn                     | P0      |
| 6   | Khảo sát cấu hình runtime             | Replica, probes, requests/limits, security context, service exposure và pod QoS                     | P1      |
| 7   | Lập sổ đăng ký rủi ro                 | Mã rủi ro, bằng chứng, mức độ nghiêm trọng, người phụ trách, hướng xử lý, cách xác minh và rollback | P1      |
| 8   | Chọn backlog cho Tuần 2               | Danh sách được xếp hạng, lý do, chi phí/rủi ro và danh sách chưa làm                                | P1      |
| 9   | Dựng vận hành tối thiểu               | ADR, decision log, runbook, postmortem, rota on-call và Ops Review template                         | P1      |
| 10  | Chuẩn bị pitch                        | Kiến trúc, baseline, rủi ro, backlog, trade-off, chi phí và rollback                                | P1      |


### 11.3 Mẫu baseline cho pitch


| Chỉ số                     | Baseline Tuần 1 | Mục tiêu sau thay đổi         | Nguồn                          |
| -------------------------- | ---------------: | -----------------------------: | ------------------------------ |
| Checkout success rate      | TBD             | ≥ 99,0%                       | Grafana / Prometheus           |
| Storefront p95 latency     | TBD             | &lt; 1 giây                   | Grafana / Prometheus           |
| Cart success rate          | TBD             | ≥ 99,5%                       | Grafana / Prometheus           |
| Kafka lag dưới tải         | TBD             | Bounded và có alert           | Prometheus                     |
| Cost / 1.000 requests      | TBD             | Giảm hoặc có lý do chính đáng | Cost Explorer + load test      |
| Cost / successful checkout | TBD             | Giảm hoặc có lý do chính đáng | Cost Explorer + checkout count |
| CPU/memory waste           | TBD             | Giảm over/under-provisioning  | `kubectl top` + values         |


---

## 12. Định hướng Tuần 2 và Tuần 3

### Tuần 2

- Thực thi các hạng mục backlog đã được ưu tiên và có bằng chứng từ Tuần 1.
- Giữ nguyên `fault-injection mechanism` của `flagd`; bổ sung biện pháp fault tolerance cho các `flag-triggered failure mode`, thay vì vô hiệu hóa fault injection.
- Sau mỗi thay đổi đáng kể: deploy có rollback plan, chạy test phù hợp, kiểm tra SLO và chi phí.
- Bắt đầu nhịp on-call và handoff hằng ngày: SLO, error budget, chi phí, incident, deploy, blocker.
- Bổ sung hoặc xác minh dashboard/alert cho checkout, payment, DB, Kafka và error budget.
- Theo dõi chi tiêu AWS hằng ngày, đánh giá thay đổi theo ROI.
- Chuẩn bị xử lý directive trong `mandates/` bằng ADR, bằng chứng hoàn thành và kế hoạch rollback.

### Tuần 3

- Hoàn thiện các cải tiến có ROI cao và đã được kiểm chứng.
- Xử lý sự cố/directive bằng postmortem và ADR ký tên.
- Xác nhận rollback cho các thay đổi chính.
- Đo lại cùng bộ chỉ số baseline để chứng minh tác động thực tế.
- Chuẩn bị Service Health Readout: trạng thái SLO, error budget, cost, incident, quyết định, trade-off, rủi ro còn lại và bước tiếp theo.
- Nếu error budget đã bị đốt quá mức, đóng băng thay đổi rủi ro và ưu tiên ổn định.

---

## 13. Các hạng mục backlog ban đầu

Các hạng mục dưới đây là đề xuất ban đầu, không phải cam kết làm ngay. Thứ tự cuối cùng phải dựa trên số liệu runtime, phạm vi directive và ngân sách thực tế.


| Item                                             | Lý do ưu tiên                                                  | Điều kiện trước khi làm                                | Rollback                      |
| ------------------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------- |
| Chuẩn hóa readiness/liveness cho revenue path    | Liên hệ trực tiếp INC-3; chart đã hỗ trợ probe                 | Xác nhận health endpoint, test rollout và threshold    | Revert Helm values            |
| Dashboard và alert cho checkout SLO              | Không đo thì không vận hành được; checkout là revenue-critical | Xác nhận metrics/labels thực tế                        | Revert dashboard/alert config |
| Load test và trace bottleneck                    | Cần baseline trước mọi tối ưu performance/cost                 | Baseline cluster và guardrail tải                      | Dừng load generator           |
| Right-size requests/limits                       | Có thể giảm waste hoặc giảm OOM/throttling                     | Có `kubectl top`, load profile và bằng chứng về quota  | Revert Helm values            |
| HPA cho frontend/checkout/cart                   | Giảm rủi ro single replica/bottleneck khi tải cao              | Requests đúng, metrics ổn định, test scale up/down     | Xóa HPA hoặc scale thủ công   |
| Đánh giá Valkey durability/HA                    | INC-2 chưa được xử lý triệt để                                 | So sánh persistence/replica/managed option với chi phí | Trở về baseline + backup plan |
| Kafka lag monitoring và event integrity          | Bảo vệ accounting, fraud và audit                              | Xác nhận consumer group/metric/alert labels            | Revert dashboard/alert        |
| Kiểm tra Kafka producer acknowledgment           | Có dấu hiệu event failure có thể bị che khuất                  | Reproduce khi Kafka lỗi, đánh giá latency trade-off    | Revert config/code            |
| Kiểm soát public exposure của Grafana/OpenSearch | Mức rủi ro cao nếu các service này có public exposure          | Xác nhận ingress/LB, auth và network boundary          | Helm rollback có kiểm soát    |
| AWS Budgets + Cost Anomaly Detection             | Chi phí có trần; effort thấp                                   | Đủ IAM permission                                      | Xóa/chỉnh alert               |
| Báo cáo chi phí theo đơn vị                      | Cần bằng chứng cho pitch CFO                                   | Có Cost Explorer và số lượng workload                  | Không áp dụng                 |
| AI eval và fallback                              | Bảo vệ niềm tin khách hàng khi AI sai/rate limit               | Có eval set, UX/fallback policy và AIO owner           | Revert fallback code/config   |
| Chính sách telemetry GenAI                       | Hạn chế prompt/content `data leakage`                          | Xác định loại dữ liệu thực tế và nhu cầu debug         | Env/config rollback           |
| ADR, runbook, postmortem template                | Bắt buộc cho auditability và delivery                          | Thống nhất ownership trong TF                          | Không áp dụng                 |


---

## 14. Các câu hỏi cần trả lời sau khi deploy

### AWS và cluster

1. Account, region, EKS version, cluster name và namespace là gì?
2. VPC/subnet/NAT/load balancer/Ingress đang được thiết kế như thế nào?
3. Node group dùng instance gì, multi-AZ ra sao, có Spot/autoscaler/Karpenter không?
4. Service account có IRSA hay node IAM có quyền quá rộng không?
5. Storage class, EBS volume, backup và snapshot policy là gì?

### Runtime và bảo mật

6. `frontend-proxy` có `public exposure` hay chỉ dùng port-forward?
7. Pod nào có readiness/liveness probe, replica &gt; 1, requests/limits và PDB/HPA?
8. Pod QoS, restart, OOM, CPU throttling và node distribution thực tế ra sao?
9. Grafana/OpenSearch có auth phù hợp, có `public exposure` qua Ingress hay có thể truy cập từ namespace khác không?
10. Log/trace có chứa PII, thông tin payment hoặc nội dung prompt nhạy cảm không?

### SLO, cost và AI

11. Query/label nào là nguồn chuẩn cho SLO dashboard?
12. Alert có đến được đúng kênh on-call không?
13. Daily spend hiện tại gồm EKS/EC2/EBS/NAT/LB/log storage bao nhiêu?
14. Cost Explorer có tag đủ để tính cost per workload hay không?
15. LLM thật dùng provider/model/gateway nào, giá token ra sao và giới hạn rate limit thế nào?
16. AI eval set, tiêu chí pass và fallback mong muốn là gì?
17. Token/endpoint flagd có hoạt động ổn định trong mọi lần Helm upgrade không?

---

## Phụ lục A — Lệnh thu thập bằng chứng Tuần 1

> Thay `<REGION>`, `<ACCOUNT>`, `<NS>`, `<REG>` và `<POD>` bằng giá trị của TF.  
> Khi deploy, luôn giữ overlay `deploy/values-flagd-sync.yaml`.

```sh
aws sts get-caller-identity
aws configure get region
kubectl config current-context
kubectl cluster-info
helm version
docker buildx version
```

```sh
aws ecr describe-repositories --repository-names techx-corp --region <REGION>
aws ecr list-images --repository-name techx-corp --region <REGION>
```

```sh
helm dependency build ./techx-corp-chart

helm upgrade --install techx-corp ./techx-corp-chart -n <NS> --create-namespace --set default.image.repository=<REG> -f deploy/values-observability.yaml -f deploy/values-flagd-sync.yaml
```

```sh
kubectl -n <NS> get pods -o wide
kubectl -n <NS> get deploy,svc,hpa,pdb
kubectl -n <NS> describe pod <POD>
kubectl -n <NS> logs deploy/frontend-proxy --tail=100
kubectl -n <NS> top pods
kubectl -n <NS> port-forward svc/frontend-proxy 8080:8080
```

Sau khi port-forward, kiểm tra:

- `http://localhost:8080/`
- `http://localhost:8080/grafana/`
- `http://localhost:8080/jaeger/ui/`
- `http://localhost:8080/loadgen/`

---

## Phụ lục B -- Phase 3 Implementation Notes

### Bootstrap init/apply order
1. `cd infra/bootstrap && terraform init && terraform apply` -- creates S3 state bucket, DynamoDB lock table.
2. The state bucket has `prevent_destroy = true` and `force_destroy = false`. To delete, first remove the lifecycle block via a targeted apply.
3. Noncurrent state versions expire after 90 days; incomplete multipart uploads abort after 7 days.
4. TLS is enforced on the state bucket via S3 bucket policy.


### OpenSearch runtime baseline

OpenSearch remains enabled in the observability overlay so logs and Grafana log panels keep working. Security plugin remains disabled for this runnable baseline. Harden OpenSearch auth/TLS later as a separate GitOps/security task.


### Backend migration caveat
- The main infra (`infra/terraform/`) uses an S3 backend. The bucket name and region are hard-coded in `providers.tf` because Terraform backends cannot use variables.
- After bootstrap, the backend must match: `bucket = "tf4-phase3-state-bucket-511825856493"`, `region = "us-east-1"`, `dynamodb_table = "tf4-phase3-state-locks"`.


### VPC CNI baseline

AmazonEKS_CNI_Policy remains on the worker node role for the runnable baseline. Move it to IRSA later if security hardening becomes a separate goal.


### ALB Controller baseline

The repo keeps the existing Ingress flow and assumes AWS Load Balancer Controller/IAM setup is handled outside this Terraform baseline. Do not add LBC IRSA here unless cluster bootstrap from scratch becomes in scope.

### Required Secrets before Helm install
Create these secrets in the `techx-tf4` namespace before deploying the Helm chart:

| Secret Name        | Key(s)                                                    | Purpose              |
| ------------------ | --------------------------------------------------------- | -------------------- |
| `flagd-sync`       | `token`                                                   | flagd bearer token   |
| `grafana-admin`    | `admin-password`                                          | Grafana admin pass   |
| `flagd-ui-secret`  | `secret-key-base`                                         | flagd-ui session key |
| `postgresql-secret`| `password`, `connection-string-dotnet`, `connection-string-go`, `connection-string-python` | DB credentials       |

Example:
```sh
kubectl -n techx-tf4 create secret generic flagd-sync --from-literal=token=<BTC_TOKEN>
kubectl -n techx-tf4 create secret generic grafana-admin --from-literal=admin-password=<PASSWORD>
kubectl -n techx-tf4 create secret generic flagd-ui-secret --from-literal=secret-key-base=<BASE64_KEY>
kubectl -n techx-tf4 create secret generic postgresql-secret   --from-literal=password=otel   --from-literal=connection-string-dotnet='Host=postgresql;Username=otelu;Password=otelp;Database=otel'   --from-literal=connection-string-go='postgres://otelu:otelp@postgresql/otel?sslmode=disable'   --from-literal=connection-string-python='host=postgresql user=otelu password=otelp dbname=otel'
```

### Why NAT is single gateway for cost
- `single_nat_gateway = true` reduces cost by approximately $32/week vs one NAT per AZ.
- Acceptable for sandbox/demo; production workloads should use one NAT per AZ for AZ-level failure isolation.

### How to set `allowed_cluster_endpoint_cidrs`
- Set `allowed_cluster_endpoint_cidrs` in `infra/terraform/variables.tf` or via `-var`:
  ```sh
  terraform apply -var='allowed_cluster_endpoint_cidrs=["203.0.113.0/24"]'
  ```
- Default is `["127.0.0.1/32"]` (loopback only). Override with your VPN/office CIDR for `kubectl` access. Public endpoint remains enabled but restricted.

### Cost controls deferred
- AWS Budget and Cost Anomaly Detection are not implemented in Terraform yet.
- Add them later when cost governance becomes in scope.

### Ingress baseline
- `deploy/ingress.yaml` keeps the existing ALB flow: `kubernetes.io/ingress.class: alb`, `scheme: internet-facing`, HTTP 80.
- `frontend-proxy` keeps the original demo routes for Grafana, Jaeger, loadgen, flagd, OTLP, images, and frontend.

---

## Nguồn tham chiếu chính

- `README.md`
- `RULES.md`
- `GETTING_STARTED.md`
- `onboarding/ARCHITECTURE.md`
- `onboarding/SLO.md`
- `onboarding/BUDGET.md`
- `onboarding/INCIDENT_HISTORY.md`
- `onboarding/PITCH_GUIDE.md`
- `techx-corp-platform/`
- `techx-corp-chart/`
- `deploy/`

