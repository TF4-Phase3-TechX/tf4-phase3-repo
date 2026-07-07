# Truy vấn Metric giám sát luồng Checkout (SLO Metric Queries)

**Lưu ý:** Các câu lệnh PromQL dưới đây được định nghĩa dựa trên chuẩn naming convention của Prometheus. Tên metric thực tế (`http_requests_total`, `http_request_duration_seconds`) có thể cần điều chỉnh nhẹ tùy thuộc vào thư viện instrument code của Dev.

## 1. Lưu lượng (Rate - Requests per Second)
* **Mục đích:** Theo dõi số lượng đơn hàng / lượt checkout đang diễn ra mỗi giây để biết hệ thống đang chịu tải ra sao.
* **Câu lệnh PromQL đề xuất:**
  ```promql
  sum(rate(http_requests_total{service="checkout"}[5m]))
  ```
* **Cách hiểu:** Tính tổng tốc độ tăng của các request gọi vào service `checkout` trong khung thời gian 5 phút.

## 2. Tỷ lệ lỗi (Errors - Error Rate)
* **Mục đích:** Phát hiện ngay lập tức nếu khách hàng bấm thanh toán nhưng hệ thống trả về lỗi (Mã 5xx).
* **Câu lệnh PromQL đề xuất (Tỷ lệ % lỗi):**
  ```promql
  sum(rate(http_requests_total{service="checkout", status=~"5.."}[5m])) 
  / 
  sum(rate(http_requests_total{service="checkout"}[5m])) * 100
  ```
* **Cách hiểu:** Lấy số request lỗi chia cho tổng số request để ra tỷ lệ phần trăm. Nếu con số này vượt quá 1% hoặc 5% (tùy định nghĩa SLO), cần kích hoạt Alert.

## 3. Độ trễ (Duration - P95 Latency)
* **Mục đích:** Đo thời gian chờ đợi của 95% khách hàng khi thanh toán. Trải nghiệm thanh toán chậm sẽ dẫn đến rớt đơn.
* **Câu lệnh PromQL đề xuất:**
  ```promql
  histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{service="checkout"}[5m])) by (le))
  ```
* **Cách hiểu:** Tìm ra mức thời gian (tính bằng giây) mà 95% các request checkout hoàn thành. Ví dụ kết quả là `2.5`, nghĩa là 95% khách hàng hoàn tất thanh toán dưới 2.5 giây.

---

## 4. Đánh giá khả năng áp dụng thực tế (Gap Analysis & Code Audit)

*(Khảo sát thực tế dựa trên mã nguồn của service `checkout` và cụm Kubernetes)*

* **Hiện trạng cấu hình mã nguồn:** 
  * Khi kiểm tra file [techx-corp-platform/src/checkout/main.go](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/checkout/main.go), dịch vụ `checkout` sử dụng OpenTelemetry Metrics SDK qua hàm [initMeterProvider](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/checkout/main.go#L103) để xuất metric qua giao thức OTLP gRPC (`otlpmetricgrpc`), thay vì sử dụng thư viện Prometheus client truyền thống để phơi lộ endpoint HTTP `/metrics`.
  * Dịch vụ này được chạy dưới dạng một gRPC server (sử dụng [pb.RegisterCheckoutServiceServer](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/checkout/main.go#L252)) và được giám sát qua middleware [otelgrpc.NewServerHandler](file:///d:/xbrain/tf4-phase3-repo/techx-corp-platform/src/checkout/main.go#L250). Do đó, các metric thực tế sinh ra sẽ theo định dạng gRPC (ví dụ: `rpc_server_duration_milliseconds` hoặc tương đương sau khi được OTel collector chuyển đổi).
* **Khoảng trống hệ thống:** 
  * Do **OTel Collector chưa được triển khai** trên cụm Kubernetes, metric của service `checkout` hiện không thể xuất đi đâu và Prometheus Server cũng chưa thể cào (scrape) được các metric này.
* **Hành động đề xuất:**
  1. Triển khai OTel Collector trên cụm Kubernetes để nhận gRPC metric từ service `checkout` và chuyển đổi/xuất sang cho Prometheus thu thập.
  2. Xem xét chuyển đổi các câu lệnh PromQL phía trên từ dạng HTTP (`http_requests_total`) sang dạng gRPC tương ứng (`rpc_server_duration_milliseconds_bucket`, `rpc_server_handled_total`) để khớp hoàn toàn với instrumentation thực tế trong code.
