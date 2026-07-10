# Presentation Script: TechX TF4 - Performance &amp; Cost Optimization

Thời lượng gợi ý: 10-15 phút  
Phạm vi: Week 1 evidence cho hệ thống TechX TF4 trên AWS EKS  
Trọng tâm: Baseline architecture, deployment flow, Performance Efficiency, Cost Optimization, gaps và hướng xử lý

---

## 1. Mở đầu

Xin chào mọi người.

Trong phần trình bày này, em sẽ giới thiệu phần hệ thống mà team đang đảm nhận trong Phase 3 của TechX, sau đó đi qua kiến trúc triển khai trên AWS/EKS, flow deployment, và hai trụ chính team đã tập trung trong tuần này là **Performance Efficiency** và **Cost Optimization**.

Mục tiêu của tuần này không phải là tối ưu cực đoan ngay từ đầu, mà là tạo được một baseline có bằng chứng rõ ràng:

- Hệ thống đang chạy ở đâu.
- Traffic đi qua những lớp nào.
- Những workload nào đang tạo áp lực performance.
- Những tài nguyên nào đang tạo chi phí.
- Những điểm nào có thể tối ưu ngay, và những điểm nào cần thêm runtime evidence trước khi thay đổi.

Nói ngắn gọn, hướng làm của team là **evidence-first**: mọi khuyến nghị về performance hoặc cost đều cần dựa trên kiến trúc, số liệu runtime, log, trace, hoặc cấu hình thực tế trong repo.

---

## 2. Giới thiệu hệ thống được đảm nhận

Hệ thống TechX là một nền tảng microservices mô phỏng e-commerce chạy trên EKS.

Các nhóm service chính gồm:

- **Entry layer**: `frontend-proxy`, nhận traffic từ ALB.
- **Storefront layer**: `frontend`, `image-provider`, phục vụ giao diện và hình ảnh sản phẩm.
- **Product &amp; AI layer**: `product-catalog`, `product-reviews`, `llm`, `recommendation`, `ad`.
- **Checkout revenue path**: `cart`, `checkout`, `payment`, `email`, `currency`, `shipping`, `quote`.
- **Data &amp; messaging layer**: `postgresql`, `valkey-cart`, `kafka`.
- **Async consumers**: `accounting`, `fraud-detection`.
- **Observability layer**: `prometheus`, `jaeger`, `grafana`, `otel-collector`, `opensearch`.
- **Control and test layer**: `flagd`, `load-generator`.

Trong tuần này, team tập trung vào việc hiểu hệ thống dưới góc nhìn vận hành:

- Request của user đi vào hệ thống như thế nào.
- Các service nào nằm trên critical path.
- Những thành phần nào ảnh hưởng trực tiếp đến latency.
- Những thành phần nào tạo chi phí cố định hoặc chi phí có thể tăng theo usage.

---

## 3. Architecture overview

### 3.1. AWS High-Level Architecture

![AWS High-Level Architecture](./slide-assets/01-techx-tf4-aws-high-level-architecture.jpg)

Ở sơ đồ đầu tiên, hệ thống được triển khai trong AWS Cloud, region `us-east-1`.

Kiến trúc có các lớp chính:

- VPC trải trên 2 Availability Zones.
- Public subnets chứa entry components như Internet Gateway, NAT Gateway và ALB.
- Private subnets chứa EKS worker nodes.
- EKS cluster chạy các workload của hệ thống.
- Worker nodes pull image từ ECR thông qua NAT Gateway.

Luồng inbound chính là:

```text
User -> Internet Gateway -> ALB -> frontend-proxy -> services trong EKS
```

Luồng outbound chính là:

```text
EKS Worker Nodes -> NAT Gateway -> ECR / AWS external services
```

Một điểm quan trọng ở đây là Week 1 chỉ claim Multi-AZ ở compute layer, tức là worker nodes được phân bố trên 2 AZ. Team chưa claim full HA cho toàn bộ stateful workload như PostgreSQL, Kafka, Valkey, OpenSearch hoặc Prometheus.

Về cost, team chọn **Single NAT Gateway** cho Week 1 để kiểm soát chi phí. Đây là một trade-off: tiết kiệm hơn, nhưng chưa phải network HA tối đa.

### 3.2. EKS Namespace Application Architecture

![EKS Namespace Application Architecture](./slide-assets/02-techx-tf4-eks-namespace-architecture.jpg)

Sơ đồ thứ hai đi sâu vào bên trong namespace `techx-tf4`.

Traffic từ ALB đi vào `frontend-proxy`, sau đó tới `frontend`. Từ `frontend`, request tách thành hai nhóm lớn:

- Product browsing, review, AI assistant, recommendation và ads.
- Cart và checkout.

Luồng quan trọng nhất về business là checkout revenue path:

```text
frontend -> checkout -> cart/product-catalog/currency/payment/shipping/email/kafka
```

Đây là path cần ưu tiên theo dõi latency, error rate, retry, timeout và trace. Nếu checkout bị chậm hoặc lỗi dây chuyền, tác động trực tiếp là người dùng không hoàn tất được đơn hàng.

Trong EKS cũng có data và messaging layer:

- PostgreSQL cho catalog/data.
- Valkey cho cart/cache.
- Kafka cho event bất đồng bộ.

Sau khi order được tạo, Kafka publish event cho `accounting` và `fraud-detection` xử lý async. Đây là hướng tốt vì tách các tác vụ hậu xử lý ra khỏi luồng thanh toán chính.

Observability layer gồm Prometheus, Jaeger, Grafana, OTel Collector và OpenSearch. Đây là nền tảng để team đo performance và cũng là một cost driver gián tiếp vì nó tiêu thụ CPU/RAM trên worker nodes.

### 3.3. External Services, Cost &amp; Control Layer

![External Services Cost Control Layer](./slide-assets/03-techx-tf4-external-services-cost-control-layer.jpg)

Sơ đồ thứ ba thể hiện các thành phần nằm ngoài runtime path chính nhưng rất quan trọng cho vận hành và cost control.

Các thành phần chính:

- **Amazon ECR**: lưu container images cho EKS pull về chạy.
- **AWS Budgets**: đặt cost guardrail, cảnh báo ở các ngưỡng 70%, 90%, 100%.
- **Cost Explorer**: dùng để đối chiếu estimate với actual cost.
- **Central Flag Configuration**: sync flag vào `flagd` để hỗ trợ fault injection hoặc incident simulation.

Điểm cần nhấn mạnh là AWS Budgets và Cost Explorer không nằm trong user request path. Chúng nằm trong cost visibility/control path, giúp team không chỉ deploy được hệ thống mà còn kiểm soát được chi phí sau deploy.

---

## 4. Deployment flow trên EKS

Về deployment, hệ thống được đóng gói và triển khai theo flow chính:

```text
Source code -> Container image -> ECR -> Helm/Terraform/GitHub Actions -> EKS
```

Ở mức hạ tầng:

- Terraform quản lý các thành phần AWS như EKS, VPC, node group, budget guardrail.
- EKS node group hiện dùng `t3.large`, desired 2 nodes, max 4 nodes.
- Worker nodes nằm ở private subnet và pull image từ ECR qua NAT Gateway.

Ở mức application:

- Helm chart quản lý các deployment/service/config của microservices.
- Các pod chạy trong namespace `techx-tf4`.
- Observability stack chạy để thu metrics/logs/traces.
- ALB expose các route public như webstore, Grafana và Jaeger.

Trong evidence runtime, team đã xác nhận:

- Webstore public endpoint trả `HTTP 200 OK`.
- Grafana route `/grafana/` trả `HTTP 200 OK`.
- Jaeger route `/jaeger/ui/` trả `HTTP 200 OK`.
- 22 application deployments trong `techx-tf4` đều `READY 1/1`.
- Application pods đang `Running`.
- Worker nodes phân bố ở 2 AZ: `us-east-1a` và `us-east-1b`.

Tuy nhiên, runtime cũng ghi nhận một số cảnh báo cần xử lý trước khi right-sizing:

- `accounting` đang CrashLoopBackOff do `OOMKilled`, restart hơn 118 lần trong khoảng 15 giờ, memory request/limit hiện là `120Mi`.
- `checkout` từng restart 4 lần lúc startup vì Kafka broker chưa sẵn sàng, log báo `connection refused`; sau khi Kafka sẵn sàng thì pod ổn định.
- `load-generator` từng bị `OOMKilled` 1 lần, củng cố quyết định tắt `LOCUST_AUTOSTART` và chỉ bật khi load test có kiểm soát.
- `checkout` có memory limit `20Mi` và `GOMEMLIMIT=16MiB`, headroom chỉ khoảng `4Mi`. Đây là risk estimate dựa trên cấu hình, chưa phải confirmed OOM.
- CPU/RAM runtime được theo dõi bằng Prometheus/Grafana dashboard và PromQL.

Những điểm này ảnh hưởng trực tiếp đến quyết định right-sizing: team chưa thể giảm tài nguyên vội khi vẫn còn OOM/restart thật và một số service có memory buffer quá mỏng.

---

## 5. Hai trụ team đảm nhận: Performance và Cost

Trong tuần này, team tập trung vào hai trụ:

1. **Performance Efficiency**
2. **Cost Optimization**

Hai trụ này liên quan chặt với nhau.

Nếu chỉ tối ưu cost mà không nhìn performance, team có thể giảm tài nguyên quá tay, gây OOM, tăng latency hoặc làm hỏng checkout flow.

Ngược lại, nếu chỉ tăng tài nguyên để cải thiện performance mà không nhìn cost, hệ thống có thể chạy ổn nhưng lãng phí chi phí AWS.

Vì vậy hướng làm của team là cân bằng:

- Performance dùng runtime evidence để biết bottleneck nằm ở đâu.
- Cost dùng baseline estimate và cost driver để biết tiền đang đi vào đâu.
- Right-sizing chỉ được đề xuất khi hai phía không mâu thuẫn với nhau.

---

## 6. Performance Efficiency - Tuần này đã làm gì

Ở trụ Performance, team đã làm các nhóm việc chính.

### 6.1. Critical flows và phạm vi đo Week 1

Trước khi đọc dashboard, team chốt **7 flow cần đo** để metric luôn gắn với trải nghiệm người dùng hoặc một bước xử lý nghiệp vụ cụ thể:

| Flow ID | Critical flow | Endpoint / component chính | Priority performance test |
|---|---|---|---|
| F01 | Browse Product | `GET /products` — search, filter, sort, pagination | P1 |
| F02 | Product Detail | `GET /products/:id` — giá, tồn kho, review | P1 |
| F03 | Cart | `GET /cart`, `POST/PATCH/DELETE /cart/items...` | P1 |
| F04 | Checkout | `POST /checkout/preview`, `POST /orders` | **P0** |
| F05 | Payment | `POST /payments`, `POST /payments/webhook` | **P0** |
| F06 | AI Review / Summary | `GET /products/:id/review-summary`, `POST /ai/reviews/summary` | P2 |
| F07 | Kafka Async Order Event | `order.created`, `payment.succeeded`, `order.completed` | **P0** |

Ba flow phải ưu tiên trong performance test là **Checkout, Payment và Kafka Async Order Event**. Checkout và Payment nằm trên revenue path; Kafka quyết định các bước hậu xử lý như inventory, notification, audit và fulfillment có theo kịp sau khi đơn hàng thành công hay không.

Các flow Browse Product, Product Detail và Cart vẫn cần coverage vì có traffic cao hoặc ảnh hưởng conversion trước checkout. AI Review / Summary được theo dõi riêng vì phụ thuộc provider bên ngoài, có timeout và cost profile khác với API thông thường.

### 6.2. P0 metrics dùng cho Week 1 Pitch

Ở đây cần phân biệt hai khái niệm:

- **P0 flow** là mức ưu tiên performance test: Checkout, Payment, Kafka async order event.
- **P0 metric** là bộ chỉ số bắt buộc trên Week 1 Pitch và dashboard tổng quan, áp dụng theo flow phù hợp.

Bộ P0 metric gồm:

1. **p95/p99 latency** — p95 cho trải nghiệm của phần lớn request; p99 để phát hiện tail latency.
2. **Request rate** — RPS/RPM hoặc message/second, để mọi kết quả latency/error có ngữ cảnh tải.
3. **Error rate** — HTTP 5xx, timeout, business error hoặc publish/consume error.
4. **Success rate** — tỷ lệ request thành công dùng để đối chiếu SLO.
5. **Pod restart count** — tín hiệu crash hoặc OOM; Week 1 đã có evidence trực tiếp ở `accounting`, `checkout` và `load-generator`.
6. **Kafka lag** — backlog message chưa được consumer xử lý.
7. **DLQ count** — event lỗi bị đẩy vào Dead Letter Queue; happy-path test phải bằng 0.

Ngưỡng ban đầu dùng để test và review:

| Flow | p95 target | p99 target | Error target | Metric bổ sung |
|---|---:|---:|---:|---|
| Browse Product | ≤ 300 ms | ≤ 800 ms | ≤ 1% | Product/pagination query latency |
| Product Detail | ≤ 350 ms | ≤ 900 ms | ≤ 1% | Product/review query latency |
| Cart | ≤ 400 ms | ≤ 1,000 ms | ≤ 1% | Cart read/write latency |
| **Checkout** | **≤ 800 ms** | **≤ 1,500 ms** | **≤ 2%** | Order transaction, inventory check, event publish |
| **Payment** | **≤ 1,200 ms** | **≤ 2,500 ms** | **≤ 2%** | Gateway latency, webhook latency, event publish |
| AI Review / Summary | ≤ 3,000 ms | ≤ 5,000 ms | ≤ 3% | Provider latency, timeout và fallback |
| **Kafka Async Order Event** | **≤ 500 ms publish** | **≤ 1,000 ms publish** | **≤ 1% publish/consume** | Consumer lag, processing time, DLQ |

Các guardrail tổng hợp đi kèm là API availability `≥ 99.5%`, AI timeout sau `5,000 ms` và phải fallback, Kafka backlog không vượt `60 giây` trong điều kiện tải bình thường, DLQ bằng `0` trong happy path. CPU và memory là metric P1 dùng cho root-cause analysis; AI token usage và cost/request là P2 dùng cho production hardening.

Các threshold trên là **đề xuất ban đầu từ PERF-01 và vẫn cần Tech Lead xác nhận trước khi trở thành SLO chính thức**. Week 1 Pitch phải phân biệt rõ target với actual: nếu chưa có controlled load-test result theo từng flow, team trình bày đây là measurement contract và baseline cần validate, không gọi là kết quả đã đạt.

### 6.3. Runtime performance evidence

Team thu thập evidence từ Grafana, Prometheus, Jaeger và kubectl.

Các kết quả chính:

- Hệ thống có trace trên Jaeger cho nhiều flow quan trọng.
- Các service như `checkout`, `payment`, `product-catalog`, `frontend`, `recommendation`, `product-reviews` đều có trace coverage.
- Grafana có dashboard latency, error rate, request rate, CPU và memory theo pod.
- Pod status, restart reason và node placement đã được capture bằng kubectl.
- CPU/RAM runtime dùng Prometheus/Grafana làm source metrics chính.

Điều này cho team đủ cơ sở để nhìn performance ở mức trace, request flow và resource trend. Với các quyết định right-sizing lớn, team vẫn cần quan sát thêm 48-72 giờ để tránh cắt tài nguyên khi còn OOM/restart bất thường.

#### Evidence để chiếu khi nói phần metric Performance

Khi trình bày phần này, có thể chiếu lần lượt các ảnh evidence sau từ `PERF-04`.

**Grafana - Pod CPU usage**

![Grafana Pod CPU Usage](./slide-assets/grafana-pods-cpu.png)

Lời dẫn:

Ở ảnh này, team dùng Grafana/Prometheus làm nguồn metrics runtime chính. Đây là evidence cho CPU usage theo pod trong namespace `techx-tf4`, giúp xác định workload nào đang tạo áp lực CPU.

**Grafana - Pod Memory usage**

![Grafana Pod Memory Usage](./slide-assets/grafana-pods-memory.png)

Lời dẫn:

Ảnh này cho thấy memory usage theo pod. Đây là input quan trọng cho cả Performance và Cost, vì nếu memory đã sát limit hoặc có OOMKilled thì team không được giảm limit chỉ để tiết kiệm chi phí.

**Grafana - Resource idle**

![Grafana Resources Idle](./slide-assets/grafana-resources-idle.png)

Lời dẫn:

Đây là trạng thái hệ thống khi không có load test chủ động. Ảnh idle giúp team biết baseline tự nhiên của workload trước khi so sánh với trạng thái under load.

**Grafana - Resource under load**

![Grafana Resources Under Load](./slide-assets/grafana-resources-load.png)

Lời dẫn:

Đây là trạng thái khi có tải. Khi so sánh với idle, team có thể thấy service nào tăng CPU/RAM rõ nhất, từ đó ưu tiên tuning cho các service trên critical path như `frontend`, `checkout`, `product-reviews` và `cart`.

**Grafana - Latency dashboard**

![Grafana Latency](./slide-assets/grafana-latency.png)

Lời dẫn:

Latency dashboard dùng để kiểm tra p95/p99 và phát hiện service nào làm chậm request path. Đây là evidence quan trọng trước khi đề xuất HPA hoặc tăng resource cho service.

**Grafana - Error rate dashboard**

![Grafana Error Rate](./slide-assets/grafana-error-rate.png)

Lời dẫn:

Error rate giúp team tránh tối ưu sai hướng. Nếu sau một thay đổi cost hoặc resource mà error rate tăng, thay đổi đó phải rollback hoặc điều tra lại.

**Grafana - Request rate dashboard**

![Grafana Request Rate](./slide-assets/grafana-request-rate.png)

Lời dẫn:

Request rate cho biết traffic thực tế vào hệ thống. Ảnh này cũng liên quan trực tiếp tới COST-05, vì load-generator autostart có thể làm request rate không phản ánh đúng user traffic thật.

**Jaeger - Service coverage**

![Jaeger Services Dropdown](./slide-assets/jaeger-services-dropdown.png)

Lời dẫn:

Ảnh này chứng minh các service chính đã xuất hiện trên Jaeger. Nghĩa là OpenTelemetry tracing đã đủ để team phân tích flow ở mức request, không chỉ nhìn metric tổng quan.

**Jaeger - Checkout flow evidence**

![Checkout Flow Trace 1](./slide-assets/checkout-flow-1-1.png)

![Checkout Flow Trace 2](./slide-assets/checkout-flow-1-2.png)

Lời dẫn:

Checkout là revenue-critical path. Trace này cho thấy request phải đi qua nhiều downstream service như cart, product-catalog, currency, payment, shipping, email và Kafka. Đây là lý do team đánh giá checkout có rủi ro latency cộng dồn nếu các call vẫn chạy tuần tự.

**Jaeger - Browse product flow**

![Browse Product Flow](./slide-assets/browse-product-flow.png)

Lời dẫn:

Ảnh này dùng để nói về flow browse catalog và `product-catalog`. Ở baseline hiện tại flow phản hồi nhanh, nhưng bottleneck tiềm năng vẫn nằm ở search query nếu dữ liệu sản phẩm tăng lớn.

**Jaeger - Product AI Assistant flow**

![Product AI Assistant Flow](./slide-assets/product-ai-assistant-flow.png)

Lời dẫn:

Flow AI Assistant đi qua `product-reviews` và mock `llm`. Hiện tại mock LLM còn nhanh, nhưng nếu chuyển sang LLM thật, latency có thể tăng mạnh. Vì vậy hướng xử lý là cache, timeout và streaming response.

**Jaeger - Recommendation flow**

![Get Product Recommendations Flow](./slide-assets/get-product-recommendations-flow.png)

Lời dẫn:

Trace recommendation cho thấy frontend có thể gọi nhiều lần sang `product-catalog` để lấy chi tiết sản phẩm. Đây là evidence cho hướng tối ưu batch hoặc parallel call ở Week 2.

### 6.4. Bottleneck analysis

Team đã chỉ ra một số bottleneck quan trọng.

Thứ nhất là **N+1 currency conversion khi list nhiều sản phẩm**.

Khi frontend list products với currency khác USD, mỗi sản phẩm có thể phát sinh một gRPC call sang `currency`. Nếu số lượng sản phẩm tăng, số call tăng theo N. Giải pháp nhanh nhất là cache exchange rate ngắn hạn theo cặp tiền, ví dụ `USD -> VND`, để nhiều product dùng chung một tỷ giá trong một khoảng thời gian ngắn. Cách này giảm call lặp lại, không thêm hạ tầng mới, và phù hợp cả Performance Efficiency lẫn Cost Optimization.

Thứ hai là **catalog search dùng `LIKE %query%` nên có nguy cơ full scan khi data tăng**.

Search trong `product-catalog` dùng `LOWER()` và `LIKE %query%`, không tận dụng được index thường. Nếu data lớn hơn, PostgreSQL có thể phải scan nhiều row hơn. Giải pháp nhanh và rẻ nhất ở giai đoạn này là thêm `LIMIT` hợp lý cho search result, ví dụ giới hạn số product trả về cho mỗi request. Cách này giữ latency ổn định hơn, tránh trả quá nhiều dữ liệu cho UI, và chưa cần thêm OpenSearch nên không phát sinh compute/storage cost mới.

Thứ ba là **checkout còn nhiều dependency chạy tuần tự trên revenue path**.

Checkout hiện gọi nhiều service theo chuỗi: cart, product-catalog, currency, payment, shipping, email, Kafka. Nếu một service downstream chậm, latency checkout bị cộng dồn. Giải pháp ưu tiên là async hóa phần không cần chặn response chính, trước mắt là email/post-processing sau khi order đã được ghi nhận. Cách này giảm latency người dùng cảm nhận được và tận dụng Kafka/event flow hiện có, không cần thêm managed service mới. Với payment/order, cần thêm idempotency key và outbox pattern, tức là retry không tạo double charge/double order và event được publish nhất quán với trạng thái order.

### 6.5. Scaling và right-sizing recommendation

Team cũng review resource config và thấy:

- Nhiều service thiếu CPU requests/limits.
- Nhiều service chỉ có memory limit nhưng thiếu memory request.
- `llm` mock thiếu resource config rõ ràng.
- `checkout` memory limit quá sát: limit `20Mi`, `GOMEMLIMIT=16MiB`, headroom chỉ khoảng `4Mi`. Đây là risk estimate dựa trên cấu hình; restart hiện có của checkout đến từ Kafka startup race, chưa phải OOM.

Khuyến nghị performance là:

- Bổ sung CPU/memory requests cho các service chính.
- Tăng buffer memory cho `checkout`, ví dụ limit `64Mi` và `GOMEMLIMIT` khoảng 80% limit, rồi verify lại bằng Grafana/Prometheus.
- Đặt HPA cho `frontend` và `checkout` sau khi Prometheus/Grafana metrics ổn định đủ 48-72 giờ.
- Theo dõi p95/p99 latency và restart/OOM sau mỗi lần thay đổi.

---

## 7. Cost Optimization - Tuần này đã làm gì

Ở trụ Cost, team làm các task chính sau.

### 7.1. Baseline infrastructure cost estimate

Team đã xác định các cost driver chính của hệ thống:

- EKS control plane.
- EC2 worker nodes: 2 x `t3.large`.
- NAT Gateway.
- ALB.
- EBS gp3 root volumes.
- ECR.
- CloudWatch Logs.
- Observability stack chạy trong cluster.

Baseline estimate breakdown:

| Thành phần | Số lượng / Giả định | Ước tính theo tháng | Ước tính theo tuần | Ghi chú |
|---|---:|---:|---:|---|
| EKS Cluster Control Plane | 1 cluster, Kubernetes `1.34` standard support | `$73.00` | `$16.80` | Phí EKS cố định |
| EC2 Worker Nodes | 2 x `t3.large` | `$121.47` | `$27.96` | Compute cost cố định chính |
| Kịch bản EC2 scale tối đa | 4 x `t3.large` | `$242.94` | `$55.91` | Chỉ là scenario nếu node group scale lên maxSize=4 |
| EBS Root Volumes | 40 GiB gp3 | `$3.20` | `$0.74` | 2 volumes x 20 GiB |
| NAT Gateway | 1 NAT Gateway | `$32.85` | `$7.56` | Chưa bao gồm data processing `$0.045/GB` |
| ALB base hourly | 1 ALB | `$16.43` | `$3.78` | Chưa bao gồm LCU usage |
| Ví dụ ALB LCU | Trung bình 1 LCU | `$5.84` | `$1.34` | Chỉ là ví dụ, actual phụ thuộc traffic |
| ECR Storage | 1 repo `techx-corp` | `Pending` | `Pending` | Cần kiểm tra image size/count |
| CloudWatch Logs | 8 log groups | `Pending / hiện tại thấp` | `Pending / hiện tại thấp` | Cần theo dõi ingestion trend |
| PVC Storage | Không tìm thấy PVC | `$0.00` | `$0.00` | Ít storage cost hiện tại, nhưng có persistence risk |
| Observability Stack | Workloads chạy trong cluster | Đã bao gồm trong EC2 nodes | Đã bao gồm trong EC2 nodes | Là indirect cost vì tiêu thụ CPU/RAM worker nodes |
| Data Transfer | NAT/ALB/cross-AZ tùy traffic | `Pending` | `Pending` | Cần Cost Explorer / traffic data |

Estimate hiện tại:

- Fixed baseline current: khoảng `$246.95/month`, tương đương `$56.83/week`.
- Fixed baseline + average 1 ALB LCU: khoảng `$252.79/month`, tương đương `$58.18/week`.
- Scenario node group scale lên 4 x `t3.large`: khoảng `$368.42/month`, tương đương `$84.79/week`.

So với target `$300/week`, baseline hiện tại vẫn dưới budget. Nhưng điều quan trọng là compute cost có thể tăng gần gấp đôi nếu node group scale từ 2 lên 4 nodes.

### 7.2. Single NAT trade-off

Team chọn Single NAT Gateway cho Week 1.

Lợi ích:

- Giảm fixed NAT cost so với NAT per AZ.
- Phù hợp cho giai đoạn baseline và kiểm soát chi phí.

Trade-off:

- Chưa đạt network HA tối đa cho outbound traffic.
- Nếu NAT Gateway hoặc AZ liên quan gặp vấn đề, outbound từ private subnet có thể bị ảnh hưởng.

Hướng sau này:

- Nếu hệ thống cần production-grade network HA, cân nhắc NAT Gateway per AZ.
- Nếu traffic outbound lớn, cần dùng Cost Explorer để theo dõi NAT data processing.

### 7.3. AWS Budget cost guardrail

Team đã thêm AWS Budget bằng Terraform.

Budget guardrail có:

- Budget type: COST.
- Time unit: MONTHLY.
- Default limit: 300 USD/month.
- Threshold notification: 70%, 90%, 100%.
- Email recipients lấy từ GitHub Secret, không hard-code trong repo.
- Tích hợp vào CI/Terraform plan/apply workflow.

Điểm cần nói rõ là có khác biệt giữa một số tài liệu nói target `$300/week` và Terraform guardrail default `$300/month`. Đây là gap governance cần chốt lại: team sẽ giữ monthly guardrail chặt hơn, hay đổi limit theo weekly-equivalent.

### 7.4. Right-sizing &amp; cost saving recommendation

Ở COST-05, team không đề xuất giảm tài nguyên bừa.

Recommendation chính:

- Disable `LOCUST_AUTOSTART`, để `load-generator` chỉ chạy khi test có kiểm soát.
- Giữ node group hiện tại ở 2 x `t3.large` trong Week 1.
- Không giảm Jaeger/Grafana/Prometheus/OpenSearch memory khi chưa có đủ evidence.
- Điều tra pod restart/OOM trước khi right-size.
- Set CloudWatch log retention cho log groups không critical.
- Thêm ECR lifecycle policy để tránh image storage tăng âm thầm.

Quick win rõ nhất là **disable load-generator autostart**.

Lý do:

- `load-generator` tạo synthetic traffic 24/7 sẽ làm nhiễu metrics.
- Nó có thể làm tăng trace/log volume.
- Nó tạo áp lực lên observability stack.
- Nó có thể khiến team hiểu nhầm workload thật và đưa ra quyết định right-sizing sai.

---

## 8. Backlog của Performance

Backlog Performance gồm:

1. Chuẩn hóa Prometheus/Grafana dashboard và PromQL làm source of truth cho CPU/RAM.
2. Thu thập CPU/memory pod và node trong 48-72 giờ.
3. Fix `accounting` OOMKilled CrashLoop bằng cách tăng memory và verify restart count về 0 trong 24h.
4. Tăng buffer memory cho `checkout` vì limit `20Mi` và `GOMEMLIMIT=16MiB` chỉ còn khoảng `4Mi` headroom.
5. Hoàn thiện HPA cho `frontend` và `checkout` sau khi metrics ổn định.
6. Tối ưu N+1 currency conversion bằng cache exchange rate ngắn hạn.
7. Thêm `LIMIT` cho product catalog search để bảo vệ latency và tránh thêm hạ tầng search mới quá sớm.
8. Async hóa email/post-processing trong checkout flow; với payment/order thì thêm idempotency key và outbox pattern.
9. Theo dõi p95/p99 latency, error rate, request rate sau mỗi thay đổi.

---

## 9. Backlog của Cost

Backlog Cost gồm:

1. Chốt lại budget policy: `$300/month` hay monthly equivalent của `$300/week`.
2. Validate AWS Budget bằng AWS CLI/console sau Terraform apply.
3. Thu thập Cost Explorer actual billing data.
4. So sánh actual cost với baseline estimate.
5. Disable `LOCUST_AUTOSTART` và verify request/trace volume giảm.
6. Set CloudWatch retention cho log groups phù hợp.
7. Thêm ECR lifecycle policy.
8. Theo dõi NAT Gateway data processing và ALB LCU.
9. Sau khi có 48-72h runtime metrics, đánh giá lại instance type hoặc max node group.
10. Chỉ thực hiện compute right-sizing khi không còn OOM/restart bất thường và performance target vẫn đạt.

---

## 10. Lỗ hổng hiện tại của hai trụ và hướng xử lý

### 10.1. Lỗ hổng Performance

Lỗ hổng 1: `accounting` đang CrashLoopBackOff do OOMKilled.

Bằng chứng:

```bash
kubectl get pod accounting-6696f5bdb8-7wvkg -n techx-tf4
kubectl describe pod accounting-6696f5bdb8-7wvkg -n techx-tf4 | grep -E 'Restart Count|State:|Reason:|BackOff'
kubectl logs accounting-6696f5bdb8-7wvkg -n techx-tf4 --previous --tail=50
```

Output quan trọng:

```text
State:          Waiting
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
Restart Count:  118
Limits:
  memory:  120Mi
Warning  BackOff  x689 over 15h
```

Tác động:

- `accounting` là .NET app có OpenTelemetry auto-instrumentation và Kafka consumer.
- Memory request/limit `120Mi` không đủ cho workload hiện tại, nên pod bị OOMKilled liên tục.
- Nếu cắt tài nguyên lúc này, async accounting pipeline sẽ kém ổn định hơn.

Hướng xử lý:

- Tăng memory cho `accounting` lên tối thiểu khoảng `200-256Mi`.
- Sau khi chỉnh, verify restart count không tăng trong 24h.
- Dùng Grafana/Prometheus để kiểm tra memory trend trước khi chốt limit cuối cùng.

Lỗ hổng 2: `checkout` có startup race với Kafka và memory buffer quá mỏng.

Bằng chứng restart:

```bash
kubectl describe pod checkout-87c785988-dz7w4 -n techx-tf4 | grep -E 'Restart Count|State:|Reason:|Exit Code|GOMEMLIMIT|memory'
kubectl logs checkout-87c785988-dz7w4 -n techx-tf4 --previous
```

Log root cause:

```text
panic: KAFKA_ADDR is set but producer creation failed: kafka: client has run out of available brokers to talk to: dial tcp 172.20.180.83:9092: connect: connection refused
```

Tác động:

- `checkout` restart 4 lần lúc startup vì Kafka broker chưa sẵn sàng. Đây là startup ordering issue, không phải OOM.
- Cấu hình memory vẫn quá sát: limit `20Mi`, `GOMEMLIMIT=16MiB`, headroom chỉ khoảng `4Mi`.
- Nếu traffic tăng, Go runtime, HTTP/gRPC clients, Kafka producer và OTEL instrumentation có ít buffer để hấp thụ spike.

Hướng xử lý:

- Thêm retry/backoff khi checkout tạo Kafka producer lúc startup.
- Tăng memory limit checkout lên khoảng `64Mi` và đặt `GOMEMLIMIT` khoảng 80% limit.
- Ghi rõ đây là config-based risk estimate cho OOM, chưa phải confirmed OOM event của checkout.

Lỗ hổng 3: Checkout flow còn nhiều dependency chạy tuần tự trên revenue path.

Tác động:

- Latency bị cộng dồn qua cart, product-catalog, currency, payment, shipping, email và Kafka.
- Downstream chậm có thể kéo chậm toàn bộ checkout.
- Payment/order cần tránh double charge hoặc double order khi có retry.

Hướng xử lý:

- Ưu tiên async hóa email/post-processing, vì các bước này không cần chặn response checkout chính.
- Với payment/order, thêm idempotency key và outbox pattern để retry an toàn và publish event nhất quán.
- Chọn hướng này vì dùng Kafka/event flow hiện có, giảm latency user thấy được, và không thêm chi phí hạ tầng mới.

Lỗ hổng 4: Catalog search có nguy cơ full scan khi data tăng.

Tác động:

- Search trong `product-catalog` dùng `LOWER()` và `LIKE %query%`, nên index thường khó phát huy tác dụng.
- Khi dữ liệu sản phẩm tăng, query có thể scan nhiều row và làm latency browse/search tăng.

Hướng xử lý:

- Chọn giải pháp nhanh là thêm `LIMIT` hợp lý cho search result.
- Lý do Performance Efficiency: giới hạn số row/result phải xử lý và trả về cho UI.
- Lý do Cost Optimization: chưa thêm OpenSearch hoặc index phức tạp ở Week 1, nên không tăng compute/storage cost.

Lỗ hổng 5: Currency conversion có rủi ro N+1 gRPC call khi list nhiều sản phẩm.

Tác động:

- Product listing với currency khác USD có thể gọi `currency` theo từng sản phẩm.
- Số call tăng theo số product hiển thị, làm tăng latency và noise trong trace.

Hướng xử lý:

- Chọn cache exchange rate ngắn hạn theo cặp tiền, ví dụ `USD -> VND`.
- Lý do Performance Efficiency: nhiều product dùng chung một tỷ giá nên giảm call lặp lại.
- Lý do Cost Optimization: không thêm service hoặc hạ tầng mới, chỉ giảm work lặp trong runtime.

### 10.2. Lỗ hổng Cost

Lỗ hổng 1: Cost Explorer actual data chưa đầy đủ.

Tác động:

- Baseline hiện tại vẫn là estimate, chưa phải actual bill.
- Chưa thấy rõ usage-based charges như NAT data processing, ALB LCU, CloudWatch ingestion.

Hướng xử lý:

- Chờ billing data cập nhật.
- Capture Cost Explorer.
- So sánh estimate với actual daily/weekly burn rate.

Lỗ hổng 2: Budget unit chưa thống nhất.

Tác động:

- Một số tài liệu dùng target `$300/week`.
- Terraform Budget default đang là `$300/month`.
- Nếu không nói rõ, reviewer có thể hiểu sai guardrail.

Hướng xử lý:

- Chốt budget policy.
- Nếu cần weekly target, đổi Terraform monthly limit sang monthly equivalent.
- Ghi rõ trong README/evidence.

Lỗ hổng 3: Load generator autostart.

Tác động:

- Tạo synthetic traffic liên tục.
- Làm nhiễu performance metrics.
- Có thể làm tăng log/trace và indirect cost.

Hướng xử lý:

- Set `LOCUST_AUTOSTART=false`.
- Chỉ bật load-generator khi có controlled load test.
- Verify Grafana/Jaeger sau khi tắt autostart.

Lỗ hổng 4: Observability stack có OOM/restart risk.

Tác động:

- Jaeger/Grafana không nên bị giảm memory.
- Nếu observability không ổn định, team mất nguồn evidence để right-size.

Hướng xử lý:

- Không giảm memory Jaeger/Grafana trong Week 1.
- Với Grafana, cân nhắc tăng request/limit theo evidence OOMKilled.
- Theo dõi OOMKilled/restart count sau khi giảm synthetic traffic.
- Hiện tại đang tạm thời tăng memory limit của cả 2 bằng live kubectl để tránh OOMKilled tạm thời để testing, sẽ điều chỉnh theo right-sizing với cost phù hợp sau.

Lỗ hổng 5: CloudWatch retention và ECR lifecycle chưa hoàn chỉnh.

Tác động:

- Log storage và image storage có thể tăng âm thầm.

Hướng xử lý:

- Set retention cho non-critical log groups.
- Thêm lifecycle policy cho untagged/dev images.

---

## 11. Kết luận

Tóm lại, trong tuần này team đã xây được một baseline khá rõ cho cả kiến trúc, performance và cost.

Về architecture:

- Hệ thống chạy trên EKS trong AWS.
- Inbound traffic đi qua ALB vào `frontend-proxy`.
- Application chia thành nhiều layer: storefront, product/AI, checkout, data/messaging, async consumer và observability.
- External services như ECR, AWS Budgets, Cost Explorer đóng vai trò quan trọng trong deployment và cost control.

Về Performance:

- Team đã có trace, dashboard và runtime evidence.
- Đã chốt 7 critical flows; P0 performance-test scope là Checkout, Payment và Kafka Async Order Event.
- Đã chốt bộ P0 metric cho Week 1 Pitch: p95/p99 latency, request rate, error/success rate, pod restart count, Kafka lag và DLQ.
- Đã có initial threshold theo từng flow; đây là measurement contract cần controlled load test và Tech Lead xác nhận, chưa phải tuyên bố mọi flow đã đạt target.
- Đã xác định các bottleneck chính: N+1 currency conversion, catalog search full scan, checkout sequential dependency.
- Đã có hướng scaling/right-sizing nhưng cần thêm 48-72 giờ runtime data từ Prometheus/Grafana và cần xử lý OOM/restart bất thường trước khi áp dụng mạnh.

Về Cost:

- Baseline hiện tại dưới target `$300/week`.
- Cost driver chính là EC2 worker nodes, EKS control plane, NAT Gateway, ALB và observability stack.
- Quick win an toàn nhất là disable `load-generator` autostart.
- Không giảm observability memory khi đã có OOM/restart risk.
- AWS Budget guardrail đã được đưa vào Terraform, nhưng cần chốt lại monthly/weekly budget policy.

Thông điệp chính của phần trình bày là: team không chỉ tìm cách giảm chi phí, mà đang xây một quy trình tối ưu có kiểm soát. Mọi quyết định right-sizing cần đi qua evidence, validation và rollback plan để không đánh đổi performance/reliability lấy một khoản tiết kiệm chưa chắc chắn.

---

## 12. Tài liệu tham chiếu

- `docs/evidence/epic-02-baseline-architecture/01-aws-high-level-architecture.md`
- `docs/evidence/epic-02-baseline-architecture/02-eks-namespace-application-architecture.md`
- `docs/evidence/epic-02-baseline-architecture/03-external-services-cost-control-layer.md`
- `docs/evidence/epic-03-performance-efficiency/01-critical-flows-and-metrics.md`
- `docs/evidence/epic-03-performance-efficiency/03-bottleneck-analysis.md`
- `docs/evidence/epic-03-performance-efficiency/04-runtime-performance-evidence.md`
- `docs/evidence/epic-03-performance-efficiency/05-scaling-right-sizing-recommendation.md`
- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- `docs/evidence/epic-04-cost-optimization/02-single-nat-tradeoff.md`
- `docs/evidence/epic-04-cost-optimization/03-aws-budget-cost-guardrail.md`
- `docs/evidence/epic-04-cost-optimization/05-right-sizing-cost-saving-recommendation.md`
- `docs/evidence/epic-04-cost-optimization/06-cost-quick-wins.md`
