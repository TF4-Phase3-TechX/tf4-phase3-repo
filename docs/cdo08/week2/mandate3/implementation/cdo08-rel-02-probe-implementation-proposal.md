# Phân tích health capability cho critical app services

| Thông tin     | Giá trị                                                             |
| ------------- | ------------------------------------------------------------------- |
| Backlog ID    | `CDO08-REL-02`                                                      |
| Owner         | Hoàng Nam                                                           |
| Pillar        | Reliability                                                         |
| Priority      | P0                                                                  |
| Loại tài liệu | Technical implementation proposal                                   |
| Review gate   | Nguyên review technical risk trước khi cập nhật Helm                |
| Phạm vi       | CDO08 Week 2 - readiness/liveness probe cho 7 critical app services |

## 1. Mục tiêu

Tài liệu này đánh giá health capability hiện có của bảy service critical trong
`CDO08-REL-02`, từ đó đề xuất readiness/liveness probe phù hợp trước khi cập
nhật Helm chart.

Phạm vi gồm:

- `frontend-proxy`
- `frontend`
- `checkout`
- `cart`
- `payment`
- `shipping`
- `product-catalog`

Hướng hiện tại phù hợp để xây dựng production baseline vì ưu tiên:

- Tận dụng capability sẵn có.
- Hạn chế thay đổi logic ứng dụng trong lần rollout đầu tiên.
- Giảm rủi ro probe gây side effect hoặc restart dây chuyền.
- Có thể triển khai theo batch và rollback nhanh.

Đây là baseline triển khai ban đầu, chưa phải thiết kế health check cuối cùng.

## 2. Ma trận đề xuất

| Service           | Readiness đề xuất                                        | Liveness đề xuất         | Lý do và giới hạn                                                                                                               |
| ----------------- | -------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| `frontend-proxy`  | HTTP GET `/ready`, port `10000`                          | TCP port `8080`          | Envoy có admin readiness endpoint. Không expose admin port qua Service/Ingress.                                                 |
| `frontend`        | TCP port `8080`                                          | TCP port `8080`          | Chưa có health endpoint riêng. TCP chỉ xác nhận process đã mở port.                                                             |
| `checkout`        | Native gRPC, port `8080`                                 | Native gRPC, port `8080` | Health trả `SERVING` tĩnh, phù hợp shallow health nhưng chưa phản ánh downstream.                                               |
| `cart`            | Native gRPC, port `8080`, service `oteldemo.CartService` | TCP port `8080`          | Readiness phải giữ logic `failedReadinessProbe`; liveness không dùng cùng health signal để tránh flag làm pod restart liên tục. |
| `payment`         | Native gRPC, port `8080`                                 | Native gRPC, port `8080` | Không gọi logic thanh toán thật trong probe. Health hiện là shallow health.                                                     |
| `shipping`        | TCP port `8080`                                          | TCP port `8080`          | Chỉ có business endpoint dạng POST; không dùng `/get-quote` hoặc `/ship-order` làm probe.                                       |
| `product-catalog` | Native gRPC, port `8080`                                 | Native gRPC, port `8080` | Health hiện trả `SERVING` tĩnh; readiness có thể nâng cấp kiểm tra DB sau baseline.                                             |

Native gRPC probe phải sử dụng port số; không sử dụng named port.

## 3. Source evidence

| Service           | Evidence                                                                | Nội dung xác nhận                                                                                                  |
| ----------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `frontend-proxy`  | `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml:245-249`        | Envoy admin listener dùng port `10000`; có thể sử dụng `/ready` cho readiness mà không expose qua Service/Ingress. |
| `frontend`        | `techx-corp-chart/values.yaml:358-409`                                  | Service mở port `8080`; source chưa có health endpoint riêng.                                                      |
| `checkout`        | `techx-corp-platform/src/checkout/main.go:252-253`                      | Đăng ký gRPC health server trên cùng gRPC server của service.                                                      |
| `cart`            | `techx-corp-platform/src/cart/src/Program.cs:90-102`                    | Đăng ký gRPC health service và `readinessCheck`.                                                                   |
| `cart`            | `techx-corp-platform/src/cart/src/services/HealthCheckService.cs:30-43` | Health status đọc flag `failedReadinessProbe`.                                                                     |
| `payment`         | `techx-corp-platform/src/payment/index.js:41-43`                        | Đăng ký gRPC health và trả `SERVING` cho service mặc định.                                                         |
| `shipping`        | `techx-corp-platform/src/shipping/src/main.rs:46-54`                    | HTTP server lắng nghe trên service port nhưng chưa có health route riêng.                                          |
| `shipping`        | `techx-corp-platform/src/shipping/src/shipping_service.rs:18-48`        | Các route hiện có là business POST endpoint, không phù hợp để dùng làm probe.                                      |
| `product-catalog` | `techx-corp-platform/src/product-catalog/main.go:250-251`               | Đăng ký gRPC health server trên service port.                                                                      |
| Chart             | `techx-corp-chart/templates/_objects.tpl:73-79`                         | Template đã hỗ trợ render `livenessProbe` và `readinessProbe` từ component values.                                 |
| Chart             | `techx-corp-chart/values.yaml:152-153`                                  | Baseline chỉ có probe dạng comment, chưa có component nào bật probe.                                               |

Các gRPC health implementation hiện tại của `checkout`, `payment` và
`product-catalog` là shallow health. Chúng xác nhận gRPC server phản hồi nhưng
không kiểm tra toàn bộ downstream dependency.

## 4. Ràng buộc đối với Cart

`failedReadinessProbe` được định nghĩa là fault-injection flag dành cho Cart và
được đọc trong `HealthCheckService`. Theo `RULES.md`, flagd và các hook
OpenFeature có sẵn là cơ chế được bảo vệ, không được gỡ bỏ hoặc vô hiệu hóa.

Nếu dùng cùng gRPC health cho cả readiness và liveness, khi BTC bật
`failedReadinessProbe`, cả hai probe có thể fail. Kubernetes khi đó không chỉ
loại pod khỏi traffic mà còn restart container liên tục, làm sai mục tiêu của
kịch bản readiness failure.

Vì vậy baseline đề xuất:

- Readiness dùng gRPC health để giữ nguyên fault-injection behavior.
- Liveness dùng TCP để chỉ kiểm tra process còn mở cổng dịch vụ.
- Không sửa hoặc bỏ logic đọc `failedReadinessProbe`.

## 5. Nguyên tắc thiết kế

### 5.1. Không làm probe quá sâu ngay từ đầu

Ví dụ, checkout phụ thuộc vào `cart`, `payment`, `shipping`,
`product-catalog` và `currency`.

Không nên để liveness của checkout kiểm tra tất cả các service đó.

Nếu Payment tạm thời lỗi, một deep liveness check có thể tạo chuỗi phản ứng:

```text
Payment lỗi
  -> Checkout liveness fail
  -> Kubernetes restart Checkout
  -> Checkout mới vẫn không gọi được Payment
  -> Checkout tiếp tục restart
```

Một lỗi Payment có thể biến thành restart dây chuyền.

Nguyên tắc áp dụng:

- Liveness trả lời: chính ứng dụng này có còn hoạt động không?

- Readiness trả lời: ứng dụng này hiện có đủ điều kiện nhận traffic không?

Readiness có thể kiểm tra một dependency thật sự bắt buộc, nhưng cũng không nên kiểm tra toàn bộ hệ thống quá sâu.

### 5.2. Giai đoạn đầu ưu tiên probe nhẹ

Thứ tự triển khai an toàn:

1. Dùng capability có sẵn: HTTP `/ready`, gRPC health hoặc TCP port.
2. Theo dõi rollout và false positive.
3. Nâng readiness cho dependency quan trọng như Cart - Valkey và Product
   Catalog - PostgreSQL.

Cách này ít phá logic và dễ chứng minh trong pitch hơn việc sửa health endpoint hàng loạt ngay lập tức.

### 5.3. TCP probe chỉ là phương án tối thiểu

TCP probe chỉ xác nhận port đang mở, chưa chứng minh:

- Application xử lý request được.
- Event loop không bị treo.
- Dependency còn kết nối.
- Dữ liệu đã load xong.

Do đó TCP phù hợp cho frontend và shipping trong baseline đầu tiên, nhưng nên ghi rõ đây là giới hạn đã biết và có thể nâng cấp sau.

### 5.4. Health trả `SERVING` tĩnh vẫn có giá trị

Nó chưa phản ánh dependency, nhưng vẫn xác nhận được:

- Process đang chạy.
- gRPC server đã khởi tạo.
- Port có thể nhận gRPC.
- Health service phản hồi.

Vì vậy không nên nói nó “vô dụng”. Chính xác hơn:

Nó là shallow health check: đủ cho baseline, nhưng chưa phải dependency-aware
readiness.

### 5.5. Cấu hình threshold thận trọng

Ngoài probe type, cần đánh giá `initialDelaySeconds`, `periodSeconds`,
`timeoutSeconds`, `failureThreshold` và `successThreshold`.

Nếu quá nhạy, một lần network chậm cũng làm Pod NotReady hoặc restart. Nếu quá lỏng, Pod lỗi lâu mới được phát hiện.

Baseline ban đầu theo backlog đã được duyệt:

```yaml
initialDelaySeconds: 15
periodSeconds: 10
timeoutSeconds: 3
failureThreshold: 3
```

Các giá trị này là điểm bắt đầu để rollout, không phải cấu hình tối ưu chung cho
mọi service. Liveness nên ít nhạy hơn readiness nếu runtime evidence cho thấy
service khởi động hoặc warm-up chậm. Chỉ bổ sung `startupProbe` khi có bằng
chứng startup time vượt ngưỡng readiness/liveness hiện tại.

## 6. Kế hoạch rollout

Không bật probe cho toàn bộ service trong một release lớn. Thứ tự đề xuất:

1. `frontend-proxy`.
2. `frontend`.
3. `checkout`.
4. `payment` và `product-catalog`, từng service một.
5. `shipping`.
6. `cart` sau cùng vì có `failedReadinessProbe` cần kiểm chứng riêng.

Sau mỗi service:

- Render chart để xác nhận probe nằm đúng container và port.
- Theo dõi `kubectl rollout status`.
- Kiểm tra pod events, restart count và thời gian chuyển sang `Ready`.
- Chạy smoke test phù hợp; sau batch checkout path, Quân xác nhận browse, cart
  và checkout.
- Dừng rollout batch tiếp theo nếu xuất hiện false `NotReady`, restart bất
  thường hoặc customer flow lỗi.

## 7. Verification và rollback

### 7.1. Verification

```bash
helm template techx-corp ./techx-corp-chart \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml

kubectl -n techx-tf4 rollout status deploy/<service>
kubectl -n techx-tf4 describe pod <pod-name>
kubectl -n techx-tf4 get pods
```

Runtime jsonpath phải xác nhận readiness/liveness đã được render trong pod
spec. Smoke test phải bao phủ storefront, cart và checkout sau các batch liên
quan.

### 7.2. Rollback

- Dừng batch rollout tiếp theo khi probe gây pod stuck hoặc restart bất thường.
- Revert probe config của service bị ảnh hưởng hoặc rollback về Helm revision
  ổn định gần nhất.
- Xác nhận pod trở lại `Ready`, restart count ổn định và customer flow hoạt
  động sau rollback.
- Không thay đổi hoặc vô hiệu hóa `failedReadinessProbe` để xử lý lỗi rollout.

## 8. Các quyết định cần technical review

Nguyên xác nhận trước khi cập nhật Helm chart:

- Chấp thuận probe type trong ma trận cho từng service.
- Chấp thuận Cart dùng gRPC readiness nhưng TCP liveness để bảo toàn
  `failedReadinessProbe`.
- Chấp thuận threshold baseline `15/10/3/3` làm điểm bắt đầu và cho phép điều
  chỉnh theo runtime evidence.
- Chấp thuận rollout từng service, dừng batch khi xuất hiện false `NotReady`,
  restart bất thường hoặc smoke test lỗi.
- Xác nhận chưa cần sửa application health endpoint trong lần rollout
  baseline; HTTP/dependency-aware health là follow-up sau khi baseline ổn định.

Sau khi technical review được approve mới cập nhật Helm values, render chart và
triển khai runtime verification theo Jira task.

## 9. Hướng nâng cấp sau baseline

### Mức 1 - Thực hiện trong task hiện tại

- Envoy: HTTP readiness `/ready`, TCP liveness.
- Các gRPC service: native gRPC readiness/liveness, ngoại trừ Cart sử dụng TCP
  liveness để bảo toàn hành vi `failedReadinessProbe`.
- Service chưa có health endpoint riêng: TCP probe.
- Rollout theo từng service.
- Smoke test browse, cart và checkout.

### Mức 2 - Nâng cấp sau khi baseline ổn định

- `frontend`, `shipping`: thêm HTTP health endpoint nhẹ.
- Cart readiness kiểm tra Valkey bằng operation nhẹ.
- Product Catalog readiness kiểm tra PostgreSQL bằng ping có timeout.
- Giữ liveness độc lập với downstream.
- Theo dõi false restart và thời gian pod chuyển sang `Ready`.

### Mức 3 - Chỉ thực hiện khi có evidence và review riêng

- Readiness tổng hợp nhiều dependency.
- Health check sâu vào business logic.
- Probe gọi query nặng.
- Một cấu hình probe global áp dụng cho tất cả service.

Các thay đổi này phức tạp và dễ gây lỗi dây chuyền, nên không thuộc lần rollout
baseline của Week 2.

## 10. Kết luận

Hướng hiện tại đã ổn để làm production baseline mà không phải sửa sâu logic service. Nên bắt đầu bằng HTTP/gRPC/TCP capability có sẵn, giữ probe nhẹ và rollout từng service. Sau khi baseline ổn mới nâng readiness cho các dependency quan trọng như Valkey và PostgreSQL. Liveness không nên phụ thuộc downstream để tránh restart dây chuyền.

Đề xuất này giả định hệ thống đang phục vụ khách hàng và mọi thay đổi probe đều
có thể tác động trực tiếp đến traffic. Vì vậy, việc bắt đầu bằng shallow health,
triển khai từng service và theo dõi runtime là lựa chọn có chủ đích nhằm giới
hạn blast radius. Bật deep health hoặc thay đổi đồng loạt ngay từ đầu có thể
khiến nhiều pod cùng `NotReady` hoặc restart nếu threshold hay dependency check
chưa chính xác, dẫn đến gián đoạn nghiêm trọng hơn finding ban đầu.

Sau khi baseline vận hành ổn định và có đủ runtime evidence, readiness mới được
nâng cấp có chọn lọc cho những dependency thật sự bắt buộc. Phần nâng cấp sau
baseline vì vậy là bước tiếp theo của chiến lược production rollout, không phải
phần bị bỏ qua trong thiết kế hiện tại.

Đây cũng là cách bảo vệ hợp lý trước mentor: nhóm không cố thiết kế probe hoàn hảo ngay từ đầu, mà chọn safe incremental rollout — cải thiện rõ reliability nhưng giữ blast radius của thay đổi ở mức thấp.
<<<<<<< Updated upstream
=======

>>>>>>> Stashed changes
---
## 🛡️ CDO-07 Audit Approval Sign-Off
- **Trạng thái:** ✅ APPROVED / PASS
- **Người kiểm duyệt:** CDO-07 (Đội ngũ Auditability)
<<<<<<< Updated upstream
- **Ngày thực hiện:** 2026-07-16
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.
=======
- **Ngày thực hiện:** 2026-07-17
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.
>>>>>>> Stashed changes
