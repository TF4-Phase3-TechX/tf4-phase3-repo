# CDO08 Tuần 1 - Báo Cáo Quét Kiến Trúc & Rủi Ro Kỹ Thuật (Architecture & Technical Risk Findings)

**Người thực hiện:** Nguyên (Lead Security + Reliability)  
**Trụ cột (Pillar):** Security + Reliability  
**Mức độ ưu tiên (Priority):** P1  
**Trạng thái:** Hoàn thành  
**Ngày báo cáo:** 2026-07-09  

---

## 1. Cơ sở Kiến trúc (Architecture Baseline)

### 1.1 Sơ đồ Phụ thuộc của Dịch vụ (Service Dependency Table)
Bảng dưới đây mô tả cách thức giao tiếp và các phụ thuộc (dependency) giữa các microservice trong TechX Corp Platform.

| Service | Giao thức | Phụ thuộc downstream (Gọi service nào) | Mức độ quan trọng đối với Checkout Flow |
| :--- | :--- | :--- | :--- |
| **frontend-proxy** (Envoy) | HTTP/gRPC | `frontend`, Grafana, Jaeger, Prometheus, OpenSearch | **Cao (Critical)** - Entrypoint của toàn hệ thống |
| **frontend** (Next.js) | gRPC / HTTP | `product-catalog`, `product-reviews`, `cart`, `checkout`, `recommendation`, `ad` | **Cao (Critical)** - Giao diện storefront chính |
| **product-catalog** (Go) | gRPC | `postgresql`, `flagd` | **Cao (Critical)** - Xác thực thông tin và giá sản phẩm khi checkout |
| **product-reviews** (Python) | gRPC / HTTP | `postgresql`, `llm`, `product-catalog`, `flagd` | Thấp (Chỉ hiển thị/đánh giá review sản phẩm) |
| **cart** (.NET) | gRPC | `valkey-cart`, `flagd` | **Cao (Critical)** - Quản lý giỏ hàng của người dùng |
| **checkout** (Go) | gRPC | `cart`, `product-catalog`, `currency`, `shipping` (HTTP), `payment`, `email` (HTTP), `kafka`, `flagd` | **Nghiêm trọng (Critical Path Orchestrator)** |
| **currency** (C++) | gRPC | Không có | **Cao (Critical)** - Quy đổi ngoại tệ cho đơn hàng & phí ship |
| **shipping** (NodeJS) | HTTP | `quote` | **Cao (Critical)** - Tính phí và tạo vận đơn giao hàng |
| **quote** (NodeJS) | HTTP | Không có | **Cao (Critical)** - Tính toán phí vận chuyển |
| **payment** (NodeJS) | gRPC | `flagd` | **Cao (Critical)** - Thực hiện thanh toán qua thẻ tín dụng |
| **email** (Python) | HTTP | `flagd` | Thấp (Nếu lỗi sẽ ghi log cảnh báo, không làm hỏng flow chính) |
| **recommendation** (Python) | gRPC | `product-catalog`, `flagd` | Thấp (Chỉ gợi ý sản phẩm) |
| **ad** (Go) | gRPC | `flagd` | Thấp (Chỉ hiển thị quảng cáo) |
| **accounting** (C#) | Kafka / gRPC | `kafka` (consumer), `postgresql` (db write) | Thấp (Xử lý bất đồng bộ sau khi đặt hàng thành công) |
| **fraud-detection** (Go) | Kafka / gRPC | `kafka` (consumer), `flagd` | Thấp (Xử lý kiểm tra gian lận bất đồng bộ) |

### 1.2 Chi tiết Luồng Checkout (Checkout Flow)
Luồng checkout hoạt động dưới dạng một giao dịch đồng bộ được điều phối bởi service `checkout` (hàm `PlaceOrder`):

1. **Lấy thông tin giỏ hàng (Get Cart)**: Gọi sang service `cart` (`GetCart` gRPC) để lấy danh sách item.
2. **Chuẩn bị đơn hàng (Prepare Order)**: Gọi sang service `product-catalog` (`GetProduct` gRPC) trong vòng lặp để lấy chi tiết từng sản phẩm (tên, giá).
3. **Quy đổi tiền tệ (Convert Currency)**: Quy đổi giá sản phẩm từ USD sang tiền tệ của khách hàng bằng service `currency` (`Convert` gRPC).
4. **Lấy phí vận chuyển (Get Shipping Quote)**: Gửi thông tin giỏ hàng đến service `shipping` qua HTTP POST `/get-quote`, sau đó quy đổi phí ship sang tiền tệ của khách.
5. **Thanh toán (Charge Card)**: Gửi yêu cầu thanh toán thẻ tín dụng đến service `payment` (`Charge` gRPC).
6. **Tạo vận đơn (Book Shipment)**: Xác nhận giao hàng thông qua service `shipping` qua HTTP POST `/ship-order`.
7. **Xóa giỏ hàng (Empty Cart)**: Gọi service `cart` (`EmptyCart` gRPC) để dọn sạch giỏ của user.
8. **Gửi email xác nhận (Send Email)**: Gửi thông tin đơn hàng tới service `email` qua HTTP POST `/send_order_confirmation` (xử lý lỗi mềm, chỉ log warning nếu gửi lỗi).
9. **Publish Event Đơn Hàng (Publish Order Event)**: Đẩy event kết quả đơn hàng vào Kafka topic `orders` để các service downstream (`accounting`, `fraud-detection`) xử lý bất đồng bộ.

### 1.3 Hiện trạng Hạ tầng Thực tế (Verified Infrastructure Status)
Kết quả phân tích mã nguồn IaC Terraform trong thư mục `infra/terraform` và đối chiếu thực tế cụm EKS:

1. **Độ tin cậy hạ tầng Multi-AZ**: 
   - VPC chạy trên 2 Availability Zone (`azs = ["${var.aws_region}a", "${var.aws_region}b"]` trong `vpc.tf`). 
   - Managed Node Group chạy trong subnet private với kích thước tối thiểu là 2 node (`min_size = 2`, `desired_size = 2` trong `eks.tf`) sử dụng instance `t3.large`.
2. **Cấu hình Single NAT Gateway**: 
   - Cấu hình VPC bật `enable_nat_gateway = true`, `single_nat_gateway = true` và `one_nat_gateway_per_az = false` (trong `vpc.tf`), giúp giảm chi phí khoảng $32/tuần hạ tầng AWS.
3. **Cấu hình Ingress Controller**:
   - `aws-load-balancer-controller` đang chạy với 2 replicas trong namespace `kube-system` lúc **2026-07-09T10:04:36+07:00**, tự động cấu hình Application Load Balancer để hướng traffic vào các microservice.

---

## 2. Phát hiện (Findings) & Phân tích Rủi ro

### Finding CDO08-REL-01: Thiếu Liveness và Readiness Probe cho các Microservice Critical
- **Finding ID**: CDO08-REL-01
- **Trụ cột liên quan**: Reliability
- **Service/Component ảnh hưởng**: `checkout`, `cart`, `payment`, `frontend`, `product-catalog`
- **Mô tả lỗi/gap**: Tất cả các microservice được cấu hình trong Helm chart đều không bật cấu hình Liveness Probe và Readiness Probe. Kubernetes hoàn toàn không có cách nào để biết pod đã khởi tạo xong hoặc có đang khỏe mạnh hay không để định tuyến traffic.
- **Tác động (Impact)**: Khi thực hiện deploy phiên bản mới (rollout), reschedule node hoặc khi pod bị restart, Kubernetes sẽ hướng traffic vào pod mới ngay lập tức trước khi ứng dụng khởi chạy xong, gây ra lỗi HTTP 5xx hàng loạt cho khách hàng (lặp lại sự cố lịch sử `INC-3`). Điều này ảnh hưởng trực tiếp đến SLO success rate của checkout (`>= 99.0%`).
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Cấu hình Chart**: `techx-corp-chart/values.yaml` (Dưới map cấu hình của các component như `checkout`, `cart`, `payment`, `frontend`, `product-catalog`, không có dòng cấu hình `readinessProbe` hay `livenessProbe` nào được định nghĩa; chỉ có phần template bị comment ở dòng 151-153).
  - **Helm Templates**: `techx-corp-chart/templates/_objects.tpl` (Dòng 73-80 chỉ render probe nếu biến này được định nghĩa rõ ràng trong values).
  - **Quét cụm EKS Runtime (Thực hiện lúc 2026-07-09T10:24:53+07:00)**:
    ```bash
    $ kubectl get deploy checkout -n techx-tf4 -o jsonpath='{.spec.template.spec.containers[0].readinessProbe}'
    # (Kết quả trả về trống rỗng - không cấu hình probe)
    ```
- **Đề xuất xử lý**: Bổ sung cấu hình mặc định cho `readinessProbe` và `livenessProbe` vào `values.yaml` cho toàn bộ các service critical dựa trên gRPC/HTTP health endpoint có sẵn của chúng.
- **Kế hoạch Test**:
  1. Thêm cấu hình probe vào file values trên môi trường staging.
  2. Thực hiện command `kubectl rollout restart deployment/cart -n techx-tf4` trong khi chạy tool test tải nhẹ.
  3. Kiểm tra xem có request nào lỗi 5xx hay không (kỳ vọng: 0 lỗi).
- **Kế hoạch Rollback**: Revert thay đổi trong `values.yaml` và thực hiện `helm upgrade` để xóa bỏ cấu hình probe.
- **Owner phối hợp**: Deploy Operator (CDO04/CDO07)
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P0**  
  *(Likelihood: 4, Severity: 4, Business Impact: 5, SLO Impact: 5, Security Impact: 1, Evidence Confidence: 5. Điểm điều chỉnh: **24**)*

### Finding CDO08-REL-02: Các Thành phần Stateful được Deploy như Stateless Deployment (Không có PVC)
- **Finding ID**: CDO08-REL-02
- **Trụ cột liên quan**: Reliability
- **Service/Component ảnh hưởng**: `valkey-cart`, `postgresql`, `kafka`
- **Mô tả lỗi/gap**: Các thành phần lưu trữ dữ liệu trạng thái (`valkey-cart` lưu giỏ hàng, `postgresql` lưu danh mục sản phẩm/review, và `kafka` lưu hàng đợi event) được định nghĩa dưới dạng Kubernetes Deployment thông thường với 1 replica duy nhất và hoàn toàn không gắn Persistent Volume Claim (PVC).
- **Tác động (Impact)**: Bất kỳ sự cố dọn dẹp pod, quá tải node dẫn đến reschedule hay bảo trì cụm (drain node) sẽ lập tức xóa sạch toàn bộ dữ liệu lưu trong bộ nhớ hoặc ổ đĩa tạm thời của container. Người dùng sẽ bị mất sạch giỏ hàng (lặp lại sự cố lịch sử `INC-2`), cơ sở dữ liệu PostgreSQL bị reset về trạng thái init gốc, và hàng đợi Kafka bị mất các event chưa kịp consume (làm hỏng luồng đối soát kế toán).
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Helm Templates**: `techx-corp-chart/templates/_objects.tpl` (Dòng 7 hardcode cứng `kind: Deployment` cho toàn bộ các workload; chart không hỗ trợ render `StatefulSet`).
  - **Helm Values**: `techx-corp-chart/values.yaml` (Dòng 882-907 cấu hình `valkey-cart`, dòng 867-881 cấu hình `postgresql`, dòng 784-816 cấu hình `kafka` đều chỉ định `replicas: 1` và không có PVC).
  - **Quét cụm EKS Runtime (Thực hiện lúc 2026-07-09T10:25:59+07:00)**:
    ```bash
    $ kubectl get pvc -n techx-tf4
    No resources found in techx-tf4 namespace.
    ```
- **Đề xuất xử lý**: Chuyển đổi các thành phần database/broker sang cụm StatefulSet kèm theo PVC lưu dữ liệu persistent, hoặc tốt nhất là chuyển sang sử dụng dịch vụ managed của AWS (Amazon RDS cho PostgreSQL, Amazon ElastiCache cho Valkey, Amazon MSK cho Kafka).
- **Kế hoạch Test**:
  1. Truy cập storefront, thêm sản phẩm vào giỏ hàng.
  2. Kill pod Valkey: `kubectl -n techx-tf4 delete pod -l app.kubernetes.io/name=valkey-cart`.
  3. Load lại trang storefront và xác nhận giỏ hàng bị mất (hiện tại) hoặc được giữ nguyên sau khi sửa (kỳ vọng).
- **Kế hoạch Rollback**: Quay lại cấu hình stateless ban đầu nếu việc xin cấp PVC gặp lỗi hạ tầng.
- **Owner phối hợp**: CDO04 (để đánh giá chi phí ổ đĩa EBS hoặc AWS managed service so với ngân sách $300/tuần).
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 3, Severity: 4, Business Impact: 4, SLO Impact: 4, Security Impact: 1, Evidence Confidence: 5. Điểm điều chỉnh: **21**)*

### Finding CDO08-REL-03: Khởi tạo Nhà cung cấp OpenFeature Trực tiếp Trên Mỗi Request Thanh Toán
- **Finding ID**: CDO08-REL-03
- **Trụ cột liên quan**: Reliability
- **Service/Component ảnh hưởng**: `payment`
- **Mô tả lỗi/gap**: Trong code của service `payment` (Node.js), hàm xử lý thanh toán `charge` gọi khởi tạo lại và chờ kết nối nhà cung cấp flagd trên mỗi request đơn lẻ (`OpenFeature.setProviderAndWait(flagProvider)`).
- **Tác động (Impact)**: Việc tạo lại kết nối gRPC/WebSocket tới flagd sidecar cho mỗi request thanh toán sẽ gây nghẽn cổ chai (bottleneck) nghiêm trọng dưới tải cao, đẩy p95 latency của checkout lên cực lớn hoặc gây timeout thanh toán, trực tiếp vi phạm SLO success rate của checkout.
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Mã nguồn ứng dụng**: `techx-corp-platform/src/payment/charge.js` (Dòng 24-29):
    ```javascript
    module.exports.charge = async request => {
      const span = tracer.startSpan('charge');
      await OpenFeature.setProviderAndWait(flagProvider);
      const numberVariant =  await OpenFeature.getClient().getNumberValue("paymentFailure", 0);
    ```
  - Static Code Verification Timestamp: 2026-07-09T08:35:00+07:00.
- **Đề xuất xử lý**: Di chuyển đoạn mã `await OpenFeature.setProviderAndWait(flagProvider)` ra ngoài hàm `charge` và đưa vào giai đoạn khởi chạy (startup) của ứng dụng trong file `index.js`, đảm bảo chỉ kết nối một lần duy nhất.
- **Kế hoạch Test**:
  1. Chạy test tải Locust vào storefront luồng checkout.
  2. Đo p95 latency của service payment trước và sau khi tối ưu hóa để so sánh hiệu năng.
- **Kế hoạch Rollback**: Revert lại code cũ trong `charge.js`.
- **Owner phối hợp**: Không cần.
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 4, Severity: 4, Business Impact: 5, SLO Impact: 5, Security Impact: 1, Evidence Confidence: 5. Điểm điều chỉnh: **24**)*

### Finding CDO08-REL-04: Cấu Hình Kafka Producer Bất Đồng Bộ Dễ Gây Mất Tin Nhắn Đơn Hàng Thầm Lặng
- **Finding ID**: CDO08-REL-04
- **Trụ cột liên quan**: Reliability
- **Service/Component ảnh hưởng**: `checkout`, `kafka`
- **Mô tả lỗi/gap**: Dịch vụ `checkout` cấu hình Kafka Producer ở dạng bất đồng bộ (`sarama.NewAsyncProducer`) và thiết lập mức độ bảo đảm truyền tin (RequiredAcks) ở dạng `sarama.NoResponse` (tức là bắn-và-quên, không cần broker xác nhận đã nhận tin nhắn). Đồng thời, khi publish event thất bại, luồng checkout không hề đọc lỗi từ channel `Errors()` và vẫn hoàn thành giao dịch mà không cảnh báo (Silent Failure).
- **Tác động (Impact)**: 
  - Nếu Kafka broker bị sập, quá tải mạng, hoặc nghẽn hàng đợi, các tin nhắn đơn hàng sẽ bị mất thầm lặng (silently lost) mà không được ghi nhận lại.
  - Gây mất đồng bộ dữ liệu nghiêm trọng giữa dịch vụ thanh toán (`checkout`) và dịch vụ kế toán (`accounting`), dẫn đến việc khách hàng bị trừ tiền thành công nhưng hệ thống kế toán hoàn toàn không lưu vết đơn hàng (giải thích cho sự cố lịch sử `INC-3`).
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Mã nguồn Go (Thời điểm trước commit sửa đổi)**:
    - Trong file `techx-corp-platform/src/checkout/kafka/producer.go`:
      ```go
      saramaConfig.Producer.RequiredAcks = sarama.NoResponse
      producer, err := sarama.NewAsyncProducer(brokers, saramaConfig)
      ```
    - Trong file `techx-corp-platform/src/checkout/main.go`:
      ```go
      func (cs *checkout) sendToPostProcessor(ctx context.Context, result *pb.OrderResult) {
          // ...
          cs.KafkaProducerClient.Input() <- &msg
      }
      ```
      *(Hoàn toàn không có cơ chế log hay throw error khi ghi Kafka gặp sự cố).*
- **Đề xuất xử lý**: 
  1. Chuyển đổi Kafka Producer sang dạng đồng bộ (`sarama.NewSyncProducer`) để phát hiện lỗi publish trực tiếp.
  2. Nâng mức ACK lên `sarama.WaitForAll` kết hợp cấu hình retry tối đa là 5 lần.
  3. Cấu hình lại gRPC `PlaceOrder` để nhận dạng lỗi publish và lưu trữ/retry.
- **Kế hoạch Test**: Giả lập sập Kafka broker, chạy test checkout và xác nhận lỗi được bắt thành công bởi checkout service (không bị mất đơn thầm lặng).
- **Kế hoạch Rollback**: Khôi phục lại cấu hình Async Producer và `RequiredAcks = sarama.NoResponse` ban đầu.
- **Owner phối hợp**: CDO07 / Deploy Operator.
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 4, Severity: 4, Business Impact: 5, SLO Impact: 4, Security Impact: 1, Evidence Confidence: 5. Điểm điều chỉnh: **23**)*

### Finding CDO08-REL-05: Hệ Thống Giám Sát Observability Thiếu Tính Bền Vững và Khả Năng Cảnh Báo
- **Finding ID**: CDO08-REL-05
- **Trụ cột liên quan**: Reliability
- **Service/Component ảnh hưởng**: `prometheus`, `opensearch` (trong namespace `techx-observability`)
- **Mô tả lỗi/gap**: Trong cấu hình giám sát dùng chung (Observability stack): (1) Tùy chọn lưu trữ Persistent Volume (PV) cho Prometheus Server và OpenSearch đều bị tắt (`persistence.enabled: false`). (2) Alertmanager của Prometheus bị tắt mặc định (`alertmanager.enabled: false`).
- **Tác động (Impact)**: 
  - Toàn bộ log audit của OpenSearch và metric đo đạc SLO của Prometheus sẽ bị xóa sạch nếu pod bị restart hoặc rescheduling, làm mất khả năng phân tích xu hướng SLO dài hạn của toàn dự án.
  - Đội vận hành sẽ bị "mù" thông tin khi có sự cố xảy ra vì Alertmanager bị tắt và không thể gửi cảnh báo tự động về Slack/Email.
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Helm Values**: `techx-corp-chart/values.yaml` (Dòng 1121: `alertmanager.enabled: false`; Dòng 1175: `persistentVolume.enabled: false` cho Prometheus; Dòng 1223: `persistence.enabled: false` cho OpenSearch).
  - **Quét cụm EKS Runtime (Thực hiện lúc 2026-07-09T10:03:22+07:00)**:
    ```bash
    $ kubectl get pvc -n techx-observability
    No resources found in techx-observability namespace.
    ```
- **Đề xuất xử lý**: Bật `persistence.enabled: true` gắn kèm PVC cho Prometheus/OpenSearch và kích hoạt `alertmanager.enabled: true` cùng cấu hình receiver webhook.
- **Kế hoạch Test**: Bật persistence và alertmanager, restart pod và verify metrics/logs không bị mất, giả lập lỗi để verify cảnh báo gửi đi thành công.
- **Kế hoạch Rollback**: Revert lại cấu hình values.yaml.
- **Owner phối hợp**: CDO04 (Cost team) / CDO07.
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 4, Severity: 4, Business Impact: 4, SLO Impact: 4, Security Impact: 1, Evidence Confidence: 5. Điểm điều chỉnh: **22**)*

### Finding CDO08-SEC-01: Grafana Bật Quyền Anonymous Admin Mặc Định Nguy Hiểm
- **Finding ID**: CDO08-SEC-01
- **Trụ cột liên quan**: Security
- **Service/Component ảnh hưởng**: `grafana` (trong namespace `techx-observability`)
- **Mô tả lỗi/gap**: Trong cấu hình mặc định của chart, Grafana được thiết lập tắt màn hình đăng nhập và cấp quyền cao nhất (Admin) cho tất cả người dùng truy cập ẩn danh (anonymous access).
- **Tác động (Impact)**: Bất kỳ ai truy cập vào link Grafana (có thể expose qua Envoy proxy ra ngoài internet) đều có toàn quyền quản trị cao nhất: thay đổi dashboard, cấu hình alert, hoặc thậm chí xóa trắng các data source kết nối tới PostgreSQL, OpenSearch.
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Helm Values**: `techx-corp-chart/values.yaml` (Dòng 1188-1193, 1197 thiết lập cụ thể `org_role: Admin` và `disable_login_form: true`).
  - **Quét cụm EKS Runtime (Thực hiện lúc 2026-07-09T10:05:10+07:00)**:
    ```bash
    $ kubectl get secret grafana -n techx-observability -o yaml
    apiVersion: v1
    data:
      admin-password: YWRtaW4=
      admin-user: YWRtaW4=
      ldap-toml: ""
    kind: Secret
    metadata:
      creationTimestamp: "2026-07-09T01:56:33Z"
      name: grafana
      namespace: techx-observability
    type: Opaque
    ```
    *(Giải mã base64: `YWRtaW4=` tương đương với tên đăng nhập `admin` và mật khẩu quản trị `admin`)*.
- **Đề xuất xử lý**: Tắt quyền anonymous admin. Thiết lập `enabled: false` cho anonymous access hoặc cấu hình `org_role: Viewer`. Bật lại login form và cấu hình admin password bảo mật sử dụng Kubernetes Secret.
- **Kế hoạch Test**:
  1. Deploy lại config Grafana mới.
  2. Dùng trình duyệt ẩn danh truy cập `/grafana` và kiểm tra xem có bị bắt đăng nhập hoặc chỉ hiển thị quyền đọc (Viewer) hay không.
- **Kế hoạch Rollback**: Revert lại cấu hình trong values.yaml.
- **Owner phối hợp**: CDO07 (Auditability / Observability team)
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P0**  
  *(Likelihood: 5, Severity: 5, Business Impact: 4, SLO Impact: 3, Security Impact: 5, Evidence Confidence: 5. Điểm điều chỉnh: **27**)*

### Finding CDO08-SEC-02: Hardcode Thông Tin Tài Khoản Database Dạng Plain Text Trong Repo
- **Finding ID**: CDO08-SEC-02
- **Trụ cột liên quan**: Security
- **Service/Component ảnh hưởng**: `accounting`, `product-reviews`, `product-catalog`, `postgresql`
- **Mô tả lỗi/gap**: Thông tin tài khoản kết nối CSDL PostgreSQL bao gồm user, password tĩnh được lưu trực tiếp dưới dạng chữ rõ (plain text) trong values file và mã nguồn SQL script khởi tạo.
- **Tác động (Impact)**: Lộ thông tin kết nối CSDL quan trọng cho bất kỳ ai đọc repo. Nếu hacker kiểm soát được cổng DB, chúng có thể trực tiếp đánh cắp dữ liệu khách hàng hoặc chỉnh sửa thông tin giá sản phẩm.
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Helm Values**: `techx-corp-chart/values.yaml` (Dòng 183: `DB_CONNECTION_STRING` của `accounting`, dòng 619: `DB_CONNECTION_STRING` của `product-reviews`, dòng 582: `DB_CONNECTION_STRING` của `product-catalog`, dòng 868-871: `POSTGRES_USER`/`POSTGRES_PASSWORD` của `postgresql`).
  - **SQL Init Script**: `techx-corp-chart/postgresql/init.sql` (Dòng 4: `CREATE USER otelu WITH PASSWORD 'otelp';`).
  - **Quét cụm EKS Runtime (Thực hiện lúc 2026-07-09T09:36:38+07:00)**:
    ```bash
    $ kubectl get secret -n techx-tf4
    NAME                                TYPE                 DATA   AGE
    flagd-sync                          Opaque               1      32h
    sh.helm.release.v1.techx-corp.v10   helm.sh/release.v1   1      42m
    # (Hoàn toàn không tồn tại secret postgresql-secret)
    ```
- **Đề xuất xử lý**: Sử dụng cơ chế Kubernetes Secret (`postgresql-secret`) để map động các biến connection string vào pod thông qua `env.valueFrom.secretKeyRef`.
- **Kế hoạch Test**:
  1. Tạo k8s secret thủ công hoặc qua GitOps.
  2. Update chart, chạy lệnh `kubectl get pod <pod_name> -o yaml` để verify các biến môi trường CSDL không còn hiển thị plain text.
- **Kế hoạch Rollback**: Trở lại cấu hình cứng cũ trong values file.
- **Owner phối hợp**: Không cần.
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 4, Severity: 4, Business Impact: 3, SLO Impact: 2, Security Impact: 5, Evidence Confidence: 5. Điểm điều chỉnh: **23**)*

### Finding CDO08-SEC-03: OpenSearch Vô Hiệu Hóa Plugin Bảo Mật (DISABLE_SECURITY_PLUGIN)
- **Finding ID**: CDO08-SEC-03
- **Trụ cột liên quan**: Security
- **Service/Component ảnh hưởng**: `opensearch` (trong namespace `techx-observability`)
- **Mô tả lỗi/gap**: OpenSearch (nơi lưu trữ toàn bộ log hệ thống) được cấu hình tắt plugin bảo mật (`DISABLE_SECURITY_PLUGIN = "true"`) trong file `values.yaml`.
- **Tác động (Impact)**: Bất kỳ ai kết nối tới OpenSearch đều có thể đọc/ghi/xóa dữ liệu log mà không cần xác thực tài khoản. Kẻ tấn công có thể xóa dấu vết log audit hoặc đánh cắp log chứa các thông tin nhạy cảm của khách hàng (PII) được ghi nhận trong quá trình vận hành.
- **Bằng chứng kỹ thuật (Evidence)**:
  - **Helm Values**: `techx-corp-chart/values.yaml` (Dòng 1229-1230):
    ```yaml
    - name: "DISABLE_SECURITY_PLUGIN"
      value: "true"
    ```
  - Static Code Verification Timestamp: 2026-07-09T08:35:00+07:00.
- **Đề xuất xử lý**: Bật lại plugin bảo mật OpenSearch, thiết lập cơ chế xác thực cơ bản (basic auth) bằng mật khẩu lưu trong Kubernetes Secret.
- **Kế hoạch Test**: Deploy OpenSearch có bật security plugin, verify việc gọi API đọc log trực tiếp mà không truyền credentials sẽ bị trả về HTTP 401 Unauthorized.
- **Kế hoạch Rollback**: Cấu hình lại `DISABLE_SECURITY_PLUGIN: "true"`.
- **Owner phối hợp**: CDO07 (Auditability/Observability).
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 5, Severity: 4, Business Impact: 3, SLO Impact: 1, Security Impact: 5, Evidence Confidence: 5. Điểm điều chỉnh: **23**)*

### Finding CDO08-SEC-04: Thiếu Cấu Hình IAM Roles for Service Accounts (IRSA) Cho Các Pod
- **Finding ID**: CDO08-SEC-04
- **Trụ cột liên quan**: Security
- **Service/Component ảnh hưởng**: Toàn bộ pods sử dụng Service Account `techx-corp`
- **Mô tả lỗi/gap**: Service Account `techx-corp` (được dùng làm định danh chạy pod) không có annotation liên kết với vai trò IAM AWS (IAM Role).
- **Tác động (Impact)**: Do không cấu hình IRSA, toàn bộ các pod chạy trong cụm kế thừa trực tiếp quyền hạn (IAM Instance Profile) của worker node EKS. Nếu một container bị chiếm quyền điều khiển, hacker có thể lạm dụng quyền node để tương tác với ECR, CloudWatch, hoặc ghi đĩa EBS (gắn kèm theo node role), vi phạm nghiêm trọng nguyên tắc đặc quyền tối thiểu (least privilege).
- **Bằng chứng kỹ thuật (Evidence)**:
  - **IaC Terraform**: `infra/terraform/eks.tf` (Dòng 20-21 định nghĩa `enable_irsa = true` nhưng không có cấu hình ánh xạ SA cụ thể cho namespace `techx-tf4`).
  - **Quét cụm EKS Runtime (Thực hiện lúc 2026-07-09T09:38:42+07:00)**:
    ```bash
    $ kubectl get sa techx-corp -n techx-tf4 -o yaml
    apiVersion: v1
    kind: ServiceAccount
    metadata:
      annotations:
        meta.helm.sh/release-name: techx-corp
        meta.helm.sh/release-namespace: techx-tf4
      labels:
        app.kubernetes.io/managed-by: Helm
        app.kubernetes.io/part-of: techx-corp
        app.kubernetes.io/version: 2.2.0
        helm.sh/chart: techx-corp-0.40.9
      name: techx-corp
      namespace: techx-tf4
    ```
    *(Xác nhận phần `metadata.annotations` hoàn toàn trống rỗng, không chứa `eks.amazonaws.com/role-arn`)*.
- **Đề xuất xử lý**: Tạo IAM Role riêng biệt cho từng service (hoặc ít nhất là nhóm service), thiết lập Trust Policy cho EKS OIDC, và khai báo annotation trên các ServiceAccount tương ứng.
- **Kế hoạch Test**:
  1. Tạo IAM Role tối thiểu và gắn vào SA qua Helm values annotation.
  2. Deploy pod và chạy lệnh `kubectl exec` thử ghi đè tài nguyên AWS ECR từ bên trong pod để verify bị từ chối (Access Denied).
- **Kế hoạch Rollback**: Gỡ bỏ annotation khỏi ServiceAccount.
- **Owner phối hợp**: CDO04 (để cấu hình IAM Role thông qua Terraform).
- **Reviewer Status**: Approved
- **Priority đề xuất**: **P1**  
  *(Likelihood: 4, Severity: 4, Business Impact: 3, SLO Impact: 1, Security Impact: 5, Evidence Confidence: 5. Điểm điều chỉnh: **22**)*

---

## 3. Đánh giá Rủi ro Kỹ thuật (Technical Risk Review)

### 3.1 Các phát hiện/lỗi đủ mạnh để Pitch (Bảo vệ ngay Tuần 1)
1. **CDO08-REL-01 (Thiếu Probes)**: Lỗi nghiêm trọng gây mất SLO checkout success rate trực tiếp khi deploy pod mới. Cần làm ngay để bảo vệ SLO.
2. **CDO08-SEC-01 (Grafana Anonymous Admin / Admin Password)**: Lỗ hổng bảo mật trực diện, admin credentials mặc định `admin`/`admin` được xác thực nằm ngay trong secret của namespace `techx-observability`.
3. **CDO08-REL-03 (Payment OpenFeature loop)**: Lỗi kiến trúc làm nghẽn latency thanh toán, cực kỳ dễ pitch khi load test bị fail.
4. **CDO08-REL-04 (Async Kafka Producer dễ mất đơn)**: Gây mất tin nhắn event đơn hàng thầm lặng khi Kafka broker quá tải hoặc offline (không log/throw error).

### 3.2 Các phát hiện/lỗi cần bổ sung thêm bằng chứng / Đánh giá
1. **CDO08-REL-02 (Stateful Workload Deployment)**: Cần CDO04 review lại chi phí hạ tầng (EBS volume/AWS managed service) để tránh vượt budget $300/tuần của TF.
2. **CDO08-SEC-04 (Thiếu IRSA)**: Cần CDO04 định nghĩa các chính sách IAM Role tối thiểu tương ứng thông qua Terraform để liên kết với các ServiceAccount.
3. **CDO08-REL-05 (Thiếu Prometheus/OpenSearch Persistence & Alertmanager)**: Quét cụm đã xác thực `techx-observability` hoàn toàn không có PVC nào. Cần quyết định của CDO07 và CDO04 để cấu hình storage class và webhook.

### 3.3 Các phát hiện/lỗi nên để lại sau (Tuần 2-3)
1. **CDO08-SEC-02 (Database plain text credentials)**: Do DB chạy trong subnet private và chỉ được phân quyền nội bộ, rủi ro bị khai thác ở mức trung bình, có thể tối ưu ở tuần 2.

---

## 4. Ứng Viên Backlog (Backlog Candidates)
Dưới đây là danh sách issue đề xuất gửi cho Hải (PM) chấm điểm bằng rubric để đưa vào backlog tuần 2-3:

1. **Issue 1: Bật Liveness và Readiness Probes cho các Microservice trên Luồng Revenue**
   - *Mục tiêu*: Tránh lỗi HTTP 5xx khi deploy hoặc restart pods.
   - *Trụ cột*: Reliability
   - *Độ ưu tiên*: P0.
2. **Issue 2: Vô hiệu hóa Quyền Anonymous Admin trên Grafana và cấu hình mật khẩu quản trị**
   - *Mục tiêu*: Khắc phục lỗ hổng truy cập trái phép và xóa bỏ thông tin đăng nhập mặc định `admin`/`admin` của Grafana.
   - *Trụ cột*: Security
   - *Độ ưu tiên*: P0.
3. **Issue 3: Chuyển đổi Kafka Producer sang dạng đồng bộ (Sync Producer) và cấu hình báo lỗi tin nhắn**
   - *Mục tiêu*: Đảm bảo không bị mất tin nhắn đơn hàng thầm lặng khi Kafka broker gặp sự cố (xác thực tin nhắn ghi nhận thành công).
   - *Trụ cột*: Reliability
   - *Độ ưu tiên*: P1.
4. **Issue 4: Khởi tạo OpenFeature Provider ở mức Toàn cục (Global) trong Payment Service**
   - *Mục tiêu*: Loại bỏ latency dư thừa trên từng request thanh toán.
   - *Trụ cột*: Reliability
   - *Độ ưu tiên*: P1.
5. **Issue 5: Thiết lập Vai trò IAM riêng cho Service Account (IRSA)**
   - *Mục tiêu*: Thu hồi quyền node-level của pod, áp dụng least privilege trên AWS.
   - *Trụ cột*: Security
   - *Độ ưu tiên*: P1.
6. **Issue 6: Kích Hoạt Lại Alertmanager và Cấu hình Persistence (PV) Cho Prometheus/OpenSearch**
   - *Mục tiêu*: Đảm bảo gửi cảnh báo chủ động và lưu trữ durable cho metrics/logs phục vụ giám sát SLO.
   - *Trụ cột*: Reliability
   - *Độ ưu tiên*: P1.
7. **Issue 8: Bật Lại Plugin Bảo Mật (DISABLE_SECURITY_PLUGIN = false) Cho OpenSearch**
   - *Mục tiêu*: Bảo vệ an toàn dữ liệu log hệ thống, tránh truy cập nặc danh.
   - *Trụ cột*: Security
   - *Độ ưu tiên*: P1.
8. **Issue 9: Chuyển đổi Cơ sở dữ liệu và Giỏ hàng (PostgreSQL, Valkey) sang StatefulSet có PVC**
   - *Mục tiêu*: Đảm bảo không mất dữ liệu giỏ hàng và danh mục khi reschedule pod (giải quyết INC-2).
   - *Trụ cột*: Reliability
   - *Độ ưu tiên*: P1 (Cần CDO04 duyệt chi phí).
9. **Issue 10: Sử dụng Kubernetes Secrets để Quản lý Thông Tin Kết Nối PostgreSQL**
   - *Mục tiêu*: Tránh hardcode credentials dạng plain text trong Git repository.
   - *Trụ cột*: Security
   - *Độ ưu tiên*: P1.
