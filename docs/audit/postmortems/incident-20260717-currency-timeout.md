# Postmortem: Lỗi nghiệp vụ mua hàng (Frontend & Checkout) do Currency Service quá tải CPU và nghẽn OpenTelemetry

**Trạng thái:** Nháp  
**Ngày xảy ra sự cố:** 2026-07-17  
**Thời gian phát hiện:** Khoảng 03:40 - 06:30 UTC (10:40 - 13:30 GMT+7)  
**Chỉ huy xử lý sự cố:** CDO07 Auditability Team  
**Người viết:** Bá Huân / CDO07 Auditability  
**Jira liên quan:** AUDIT-018 (Nghi ngờ nghẽn dịch vụ giám sát và quá tải tài nguyên)  
**PR/rollback liên quan:** N/A  

---

## Tóm tắt

Vào khoảng từ 03:40 đến 06:30 UTC ngày 17/07/2026, hệ thống ghi nhận tỷ lệ lỗi (Error Rate) tăng vọt trên hai luồng nghiệp vụ chính là **Frontend (frontend errors)** và **Checkout (checkout errors)**. Khách hàng gặp lỗi không thể hoàn tất quá trình thanh toán (PlaceOrder). Lỗi xuất phát từ việc dịch vụ `currency` bị quá tải CPU (CPU Throttling), dẫn đến việc phản hồi gRPC bị chậm trễ quá 1 giây và kích hoạt cơ chế Timeout trong dịch vụ `checkout`. 

Đồng thời, sự cố Jaeger bị crash loop liên tục làm nghẽn hạ tầng giám sát, khiến log lỗi của các dịch vụ `checkout` và `currency` không thể xem được qua `kubectl logs` do gRPC log exporter bị nghẽn (Deadline Exceeded).

---

## Ảnh hưởng tới khách hàng / nghiệp vụ

- **Luồng bị ảnh hưởng:** Luồng mua hàng và thanh toán (PlaceOrder / Checkout) trên giao diện Web.
- **Thời lượng:** Khoảng 2 tiếng 50 phút.
- **Ảnh hưởng SLO:** Tỷ lệ lỗi luồng Checkout đạt đỉnh ở mức **3.54 req/s** và Frontend là **4.59 req/s** tại thời điểm 06:28:00 UTC.
- **Ảnh hưởng khách hàng:** Khách hàng không thể đổi đơn vị tiền tệ hoặc thanh toán đơn hàng thành công đối với một số sản phẩm cụ thể (như `9SIQT8TOJO`, `HQTGWGPNH4`, `LS4PSXUNUM`, `L9ECAV7KIM`).

---

## Timeline

| Thời gian (UTC) | Sự kiện | Evidence / Chi tiết |
| --- | --- | --- |
| 03:40 UTC | Lỗi frontend errors và checkout errors bắt đầu tăng dần | Grafana Dashboard "Business Flow Error Rate" |
| 04:00 UTC | Dịch vụ `currency` bị quá tải CPU, kích hoạt Horizontal Pod Autoscaler (HPA) | HPA Event: `SuccessfulRescale (New size: 3; reason: cpu resource utilization above target)` |
| 06:28 UTC | Lỗi đạt đỉnh điểm: Frontend errors đạt 4.59 req/s, Checkout errors đạt 3.54 req/s | Grafana Dashboard Screenshot |
| 06:35 UTC | Đội vận hành phát hiện hệ thống Jaeger giám sát bị crash loop liên tục | Output: `jaeger-7b6f6548cb-m97sz` có **149 restarts (89s ago)** |
| 06:40 UTC | Phát hiện log của `currency` và `checkout` bị trống | Output: `[OTLP LOG GRPC Exporter] Export() failed: Deadline Exceeded` do nghẽn Jaeger |

---

## Nguyên nhân gốc

Sự cố xảy ra do sự kết hợp của 3 nguyên nhân kỹ thuật dưới đây:

1.  **Quá tải CPU trên Currency Service (C++ CPU Throttling)**:
    - Service `currency` giới hạn CPU cực kỳ thấp: `Limits: cpu: 300m`, `Requests: cpu: 75m`.
    - Khi lượng tải mua hàng tăng lên, CPU của dịch vụ này nhanh chóng chạm ngưỡng giới hạn (Resource Limit) dẫn đến tình trạng **CPU Throttling** (tiến trình bị treo tạm thời để điều tiết tài nguyên).
    - HPA đã cố gắng cứu vãn bằng cách scale-up số replica của `currency` lên mức tối đa là 3 pods, nhưng do CPU limit quá thấp nên vẫn không giải quyết được tình trạng nghẽn CPU trên từng pod.
2.  **Timeout quá chặt trong Checkout Service**:
    - Khi chuẩn bị đơn hàng, service `checkout` gọi sang `currency` để đổi giá sản phẩm với thời gian chờ (timeout) rất nghiêm ngặt là **1.0 giây** cho mỗi lần thử (tối đa 2 lần thử).
    - Do `currency` bị CPU throttling, thời gian phản hồi gRPC vượt quá 1.0 giây, khiến `checkout` hủy kết nối và báo lỗi `Error: 13 INTERNAL: failed to convert price of "<PRODUCT_ID>" to USD`.
3.  **Nghẽn đường truyền log giám sát (Jaeger & OpenTelemetry Log Exporter)**:
    - Jaeger (`jaeger-7b6f6548cb-m97sz`) bị crash-loop liên tục (149 lần restart) do không ghi được dữ liệu sang OpenSearch.
    - Điều này làm nghẽn toàn bộ cổng nhận log của OpenTelemetry Collector.
    - Do `checkout` và `currency` cấu hình ghi log trực tiếp qua OTLP gRPC exporter về collector thay vì ghi ra stdout thông thường, nên việc collector bị nghẽn đã làm log của 2 service này bị trống trên console EKS với thông báo lỗi `Export() failed: Deadline Exceeded`.

---

## Phát hiện

- **Cách phát hiện:** Phát hiện thủ công qua biểu đồ Grafana "Business Flow Error Rate" và kiểm tra log của pod Frontend.
- **Khoảng trống phát hiện (Gap):** Không có cảnh báo tự động về trạng thái CrashLoopBackOff của Jaeger và HPA Scaling của Currency gửi về Slack/PagerDuty kịp thời.

---

## Phản ứng xử lý

1.  **Chẩn đoán ban đầu**: Kiểm tra log Frontend và tìm thấy lỗi nghiệp vụ `failed to convert price`.
2.  **Kiểm tra tài nguyên**: Chạy lệnh `kubectl describe deployment currency` và phát hiện giới hạn CPU `300m` quá thấp so với tải.
3.  **Kiểm tra HPA**: Chạy lệnh `kubectl describe hpa currency` phát hiện HPA đã scale lên mức tối đa là 3 pods do quá tải CPU.
4.  **Kiểm tra giám sát**: Phát hiện Jaeger bị crash loop liên tục và exporter báo lỗi `Deadline Exceeded`.

---

## Hạng mục hành động

| Hành động | Người phụ trách | Hạn hoàn thành | Jira/PR | Trạng thái |
| --- | --- | --- | --- | --- |
| Nâng giới hạn CPU của `currency` từ `300m` lên `1000m` trong Helm Chart | CDO04 DevOps Team | 2026-07-18 | PR #techx-corp-platform-123 | Đang mở |
| Tăng timeout gọi sang currency trong `checkout/main.go` lên 3.0s | CDO04 DevOps Team | 2026-07-18 | PR #techx-corp-platform-124 | Đang mở |
| Điều tra nguyên nhân Jaeger crash-loop và dọn dẹp dung lượng OpenSearch | CDO08 Security/Obs Team | 2026-07-18 | AUDIT-019 | Đang mở |
| Bổ sung cơ chế ghi log dự phòng (Fallback to stdout/stderr) khi OTLP Exporter bị lỗi | CDO07 Audit Team | 2026-07-19 | AUDIT-020 | Đang mở |

---

## Evidence

- **Log lỗi Frontend**:
  ```
  Error: 13 INTERNAL: failed to prepare order: failed to convert price of "9SIQT8TOJO" to USD
  Error: 13 INTERNAL: failed to prepare order: failed to convert price of "HQTGWGPNH4" to USD
  ```
- **Log lỗi gRPC Exporter nghẽn**:
  ```
  [Error] File: /opentelemetry-cpp/exporters/otlp/src/otlp_grpc_log_record_exporter.cc:184 [OTLP LOG GRPC Exporter] Export() failed: Deadline Exceeded
  ```
- **Lịch sử Scale-up của HPA**:
  ```
  Normal SuccessfulRescale 100s (x13 over 5h35m) horizontal-pod-autoscaler New size: 3; reason: cpu resource utilization (percentage of request) above target
  ```
- **Trạng thái Jaeger Crash-Loop**:
  ```
  NAME                      READY   STATUS    RESTARTS          AGE
  jaeger-7b6f6548cb-m97sz   1/1     Running   149 (89s ago)     28h
  ```

---

## Xác nhận

- **Người phụ trách:** Võ Hồng Đức - CDO07 Auditability  
- **Reviewer:** Chờ CDO04 & CDO08 Security Reviewer xác nhận  
- **Ngày:** 2026-07-17  
