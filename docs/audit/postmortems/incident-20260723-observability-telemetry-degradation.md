# Báo cáo sự cố: Suy giảm Observability Telemetry

**Ngày ghi nhận:** 2026-07-23  
**Người ghi nhận:** Bùi Thành Nghĩa - CDO07
**Namespace:** `techx-observability`, `techx-tf4`  
**Hệ thống bị ảnh hưởng:** OTel Collector, Jaeger, Kafka metrics pipeline  
**Mức độ:** Medium (Suy giảm observability, không ảnh hưởng customer-facing)  
**Trạng thái:** Đã ghi nhận nguyên nhân, chờ xử lý  

---

## 1. Tóm tắt ngắn gọn

Hệ thống Observability gặp tình trạng suy giảm thu thập telemetry, biểu hiện qua việc OTel Collector và Jaeger liên tục chạm ngưỡng bộ nhớ và từ chối nhận thêm dữ liệu (Refusing data/Dropping data). Đồng thời, Kafka receiver trong OTel Collector liên tục báo lỗi do cố gắng kết nối đến dịch vụ `kafka:9092` vốn đã bị tắt ở production. 

Chưa ghi nhận sự cố application outage hay mất dữ liệu giao dịch ở các ứng dụng (VD: `product-reviews`).

## 2. Ảnh hưởng hệ thống

- Các ứng dụng kinh doanh hoạt động bình thường, không có tác động trực tiếp tới người dùng cuối.
- Dữ liệu trace, log, metric có thể bị thiếu, đứt quãng hoặc đến trễ trên Jaeger, OpenSearch và Prometheus.
- Các biểu đồ dashboard, cảnh báo (alert), AIOps detection và audit correlation có thể không chính xác và đáng tin cậy.
- OTel Collector exporter ở phía ứng dụng thỉnh nhận mã lỗi `StatusCode.UNAVAILABLE` khi đẩy telemetry.

## 3. Dấu hiệu trên cluster

- **Jaeger Pod:** Liên tục ghi nhận log vượt mức giới hạn bộ nhớ (Soft/Hard limit), kích hoạt Garbage Collection liên tục hoặc từ chối nhận dữ liệu (Refusing data).
- **OTel Collector Agent Pod:** Lỗi timeout (`DeadlineExceeded`) khi xuất dữ liệu sang Jaeger do Jaeger quá tải. Lỗi phân giải tên miền (`dial tcp: lookup kafka on ... no such host`) khi receiver cố kết nối `kafka:9092`.
- **Ứng dụng `product-reviews`:** Pod trạng thái Ready (1/1), không có lượt restart bất thường.

### Lệnh để verify lại:

```powershell
# Kiểm tra log Jaeger thấy lỗi Memorylimiter
kubectl logs -n techx-observability -l app.kubernetes.io/name=jaeger --tail=50

# Kiểm tra log OTel Collector thấy lỗi lookup kafka và deadline exceeded
kubectl logs -n techx-observability daemonset/otel-collector-agent --tail=50

# Kiểm tra trạng thái pod product-reviews bình thường
kubectl get pods -n techx-tf4 -l app.kubernetes.io/name=product-reviews
```

### Bằng chứng Log thực tế

**Log OTel Collector (Kafka Receiver Error & Export Error):**
```text
2026-07-23T15:12:13.451Z  warn  unable to open connection to broker  {"component": "kafkametrics", "addr": "kafka:9092", "err": "lookup kafka ... no such host"}
2026-07-23T15:12:18.123Z  info  Exporting failed. Will retry.        {"component": "otlp/jaeger", "error": "DeadlineExceeded desc = context deadline exceeded"}
```

**Log Jaeger (Memory Limiter):**
```text
2026-07-23T15:08:46.325Z  warn  Memory usage is above soft limit. Refusing data.  {"cur_mem_mib": 627}
2026-07-23T15:08:36.325Z  info  Memory usage is above soft limit. Forcing a GC.   {"cur_mem_mib": 620}
```

## 4. Root cause

- **Giới hạn bộ nhớ (Memory Limits):** Limit của OTel Collector (200Mi) và Jaeger (1Gi) chưa đủ đáp ứng khối lượng telemetry thực tế, dẫn đến cơ chế memory limiter kích hoạt (từ chối nhận dữ liệu tại ngưỡng 80% / 75%).
- **Cấu hình Kafka Receiver thừa:** Component `kafkametrics` vẫn được bật trong metrics pipeline để thu thập thông số Kafka, nhưng cụm Kafka in-cluster đã bị tắt trên production.

## 5. Cách khắc phục để khôi phục dịch vụ

Đề xuất điều chỉnh cấu hình GitOps (cần owner review trước khi deploy):

1. **Gỡ bỏ `kafkametrics`** khỏi metrics pipeline của OTel Collector.
2. **Cập nhật tài nguyên (Resources):**
   - Tăng Request/Limit của OTel Collector lên `192Mi/384Mi`.
   - Giữ Request của Jaeger ở `1Gi` và tăng Limit lên `2Gi`.
3. Nếu hiện tượng thiếu bộ nhớ vẫn tiếp diễn sau khi tăng tài nguyên, cần phân tích sâu hơn về trace volume, batching, sampling, và độ trễ khi ghi dữ liệu vào OpenSearch.

> **Lưu ý (Trade-off):** Việc tăng resource limit sẽ tiêu tốn thêm tài nguyên của cluster, cần kiểm tra node headroom trước khi rollout.

## 6. Hành động phòng ngừa

- Tự động hóa quá trình kiểm tra (audit) để dọn dẹp các cấu hình thu thập metric không còn sử dụng (như trường hợp Kafka).
- Bổ sung cấu hình cảnh báo sớm (Alerts) khi Memory Limiter của OTel Collector/Jaeger bắt đầu có dấu hiệu kích hoạt `Refusing data`.

## 7. Kết luận

Sự cố suy giảm khả năng thu thập telemetry do giới hạn tài nguyên chưa được tinh chỉnh phù hợp với nhu cầu thực tế và sót cấu hình receiver cho dịch vụ đã ngưng hoạt động. Không có bằng chứng cho thấy đây là lỗi ứng dụng (application code). Việc tinh chỉnh lại bộ nhớ và dọn dẹp cấu hình OTel Collector sẽ giúp khôi phục hệ thống Observability ổn định trở lại.
