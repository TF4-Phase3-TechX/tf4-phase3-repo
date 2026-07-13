# Performance Screenshots Folder

Thư mục này dùng để lưu trữ các ảnh chụp màn hình minh chứng cho Epic 03 (Performance Efficiency) làm tài liệu nghiệm thu.

### Các ảnh cần chụp và lưu tại đây:

1. **`grafana-resources-idle.png`**: Ảnh chụp dashboard Grafana về tài nguyên CPU/RAM ở trạng thái hệ thống rảnh (Idle).
2. **`grafana-resources-load.png`**: Ảnh chụp dashboard Grafana về tài nguyên CPU/RAM khi đang sinh tải bằng Locust.
3. **`checkout-trace.png`**: Ảnh chụp màn hình biểu đồ Spans phân rã (Waterfall spans) của Checkout Flow trên Jaeger UI (bao phủ 13 services).
4. **`product-ai-trace.png`**: Ảnh chụp màn hình biểu đồ Spans phân rã (Waterfall spans) của Product AI Assistant Flow trên Jaeger UI (bao phủ 8 services).
5. **`jaeger-services-dropdown.png`**: Ảnh chụp danh sách service dropdown trên Jaeger UI mở rộng để chứng minh OpenTelemetry đã đăng ký thành công cả 17 microservices.

*Lưu ý: Bạn hãy mở Jaeger UI và Grafana theo link Load Balancer của dự án, tìm các trace ID trên, chụp ảnh màn hình và lưu đúng tên file vào thư mục này để liên kết markdown trong báo cáo hoạt động chính xác.*
