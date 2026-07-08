# Truy vấn Metric giám sát luồng Checkout (SLO Metric Queries)

**Lưu ý:** Các câu lệnh PromQL dưới đây được định nghĩa dựa trên chuẩn OpenTelemetry gRPC metrics do ứng dụng TechX Corp và OTel Collector sinh ra trên cụm EKS. Tên metric gốc là `rpc_server_duration_milliseconds` với các nhãn gRPC tương ứng.

## 1. Lưu lượng (Rate - Requests per Second)
* **Mục đích:** Theo dõi số lượng đơn hàng / lượt checkout đang diễn ra mỗi giây trên service `checkout`.
* **Câu lệnh PromQL thực tế:**
  ```promql
  sum(rate(rpc_server_duration_milliseconds_count{service_name="checkout", rpc_method="PlaceOrder"}[5m]))
  ```
* **Cách hiểu:** Tính tổng số request gọi vào hàm `PlaceOrder` của service `checkout` mỗi giây (tính trung bình trong khung thời gian 5 phút).

## 2. Tỷ lệ lỗi (Errors - Error Rate)
* **Mục đích:** Phát hiện ngay lập tức nếu khách hàng đặt hàng nhưng hệ thống trả về lỗi gRPC (Mã status code khác 0).
* **Câu lệnh PromQL thực tế (Tỷ lệ % lỗi):**
  ```promql
  sum(rate(rpc_server_duration_milliseconds_count{service_name="checkout", rpc_method="PlaceOrder", rpc_grpc_status_code!="0"}[5m])) 
  / 
  sum(rate(rpc_server_duration_milliseconds_count{service_name="checkout", rpc_method="PlaceOrder"}[5m])) * 100
  ```
* **Cách hiểu:** Lấy số request lỗi (gRPC status code khác 0, ví dụ như lỗi 13 - Internal Error) chia cho tổng số request để ra tỷ lệ phần trăm lỗi. Nếu con số này vượt quá 1% (vi phạm trực tiếp SLO Checkout `>= 99.0%`), cần kích hoạt Alert. Ngưỡng 5% được định nghĩa là ngưỡng khẩn cấp (emergency/severity threshold) yêu cầu đội ngũ kỹ sư xử lý ngay lập tức.

## 3. Độ trễ (Duration - P95 Latency)
* **Mục đích:** Đo thời gian phản hồi của 95% request checkout để kiểm soát trải nghiệm người dùng.
* **Câu lệnh PromQL thực tế (tính bằng mili-giây):**
  ```promql
  histogram_quantile(0.95, sum(rate(rpc_server_duration_milliseconds_bucket{service_name="checkout", rpc_method="PlaceOrder"}[5m])) by (le))
  ```
* **Cách hiểu:** Tìm ra mức thời gian (tính bằng mili-giây) mà 95% các request checkout hoàn thành. Nếu con số này vượt quá ngưỡng SLO thiết lập (ví dụ: `2000ms`), cần cảnh báo độ trễ cao.

---

## 4. Đánh giá khả năng áp dụng thực tế (Gap Analysis & Code Audit)

*(Khảo sát thực tế trên cụm EKS và ứng dụng)*

* **Hiện trạng cấu hình mã nguồn:** 
  * Dịch vụ `checkout` đã sử dụng OpenTelemetry Metrics SDK thông qua hàm `initMeterProvider` để xuất metric qua giao thức OTLP gRPC.
  * Ứng dụng chạy dưới dạng gRPC server và được giám sát qua middleware `otelgrpc.NewServerHandler`. 
  * Các metric sinh ra trong Prometheus đã được xác thực có dạng `rpc_server_duration_milliseconds_count`, `rpc_server_duration_milliseconds_bucket` với đầy đủ các nhãn như `rpc_method="PlaceOrder"`, `rpc_grpc_status_code="0"`.
* **Hiện trạng hệ thống (Xác thực trên cụm EKS):**
  * **Hạ tầng đã sẵn sàng:** OTel Collector đã được deploy thành công dưới dạng DaemonSet và Prometheus đã thu thập (scrape) được đầy đủ metric gRPC từ service `checkout`.
* **Hành động đề xuất:**
  1. Sử dụng các câu lệnh PromQL dựa trên gRPC phía trên thay thế hoàn toàn cho các lệnh HTTP (`http_requests_total`) cũ để đảm bảo tính tương thích tuyệt đối với code thực tế.
  2. Bổ sung Alert rule dựa trên các câu lệnh PromQL gRPC này vào Prometheus/Grafana khi kích hoạt Alertmanager.
