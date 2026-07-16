# CDO07 - Báo cáo Minh chứng Cấu hình SLO Alerts (OBS-01)

**Nhóm thực hiện:** CDO07 (Audit)  
**Người thực hiện:** Võ Hồng Đức
**Ngày thực hiện:** 2026-07-16  
**Trạng thái:** Hoàn thành cấu hình & Báo cáo kết quả  

---

## 1. Bối cảnh & Mục tiêu (DOD)

Task **OBS-01** yêu cầu thiết lập các chỉ số giám sát SLI queries, cấu hình Prometheus Alerts và Alertmanager Slack/Email receiver cho các dịch vụ trọng tâm: **checkout, payment, Kafka, và Database (PostgreSQL/Valkey)**.

Tất cả cấu hình đã được chỉnh sửa thành công tại các tệp cấu hình cục bộ (Local config):
*   Tệp cấu hình Alert Rules: [`techx-corp-chart/prometheus/flash-sale-alerts.yaml`](../../../techx-corp-chart/prometheus/flash-sale-alerts.yaml)
*   Tệp cấu hình Alertmanager: [`techx-corp-chart/values.yaml`](../../../techx-corp-chart/values.yaml)
*   Tệp script kiểm chứng: [`scripts/verify-flash-sale-alerts.sh`](../../../scripts/verify-flash-sale-alerts.sh) (Đã nâng lên 21 rules)

---

## 2. Ngưỡng SLO & SLI Queries đã cấu hình (Sub-task 1 & 2)

Dưới đây là chi tiết các SLI queries (viết bằng PromQL) tương ứng với các ngưỡng SLO đã thống nhất:

### 2.1 Luồng Checkout (Đặt hàng)
*   **Checkout Latency p95 > 1s trong 5 phút (Critical):**
    ```promql
    histogram_quantile(
      0.95,
      sum by (le) (
        rate(traces_span_metrics_duration_milliseconds_bucket{
          service_name="frontend",
          span_kind="SPAN_KIND_SERVER",
          span_name="POST /api/checkout"
        }[5m])
      )
    ) > 1000
    ```

### 2.2 Dịch vụ Payment (Thanh toán)
*   **Payment Success Rate < 99% trong 5 phút (Critical):**
    ```promql
    (
      sum(rate(traces_span_metrics_calls_total{
        service_name="payment",
        span_kind="SPAN_KIND_SERVER",
        status_code!="STATUS_CODE_ERROR"
      }[5m]))
      /
      sum(rate(traces_span_metrics_calls_total{
        service_name="payment",
        span_kind="SPAN_KIND_SERVER"
      }[5m]))
    ) < 0.99
    and
    sum(increase(traces_span_metrics_calls_total{
      service_name="payment",
      span_kind="SPAN_KIND_SERVER"
    }[5m])) >= 20
    ```
*   **Payment Latency p95 > 1s trong 5 phút (Critical):**
    ```promql
    histogram_quantile(
      0.95,
      sum by (le) (
        rate(traces_span_metrics_duration_milliseconds_bucket{
          service_name="payment",
          span_kind="SPAN_KIND_SERVER"
        }[5m])
      )
    ) > 1000
    ```

### 2.3 Cơ sở dữ liệu & Message Queue (PostgreSQL / Valkey / Kafka)
*   **Postgres Down (Không có replica khả dụng trong 1 phút):**
    ```promql
    k8s_deployment_available{k8s_namespace_name="techx-tf4", k8s_deployment_name="postgresql"} < 1
    ```
*   **Valkey (Cache) Down:**
    ```promql
    k8s_deployment_available{k8s_namespace_name="techx-tf4", k8s_deployment_name="valkey-cart"} < 1
    ```
*   **Kafka (Queue) Down:**
    ```promql
    k8s_deployment_available{k8s_namespace_name="techx-tf4", k8s_deployment_name="kafka"} < 1
    ```

---

## 3. Cấu hình Alertmanager & Slack/Email Routing (Sub-task 3)

Tập tin `values.yaml` đã được cấu hình định tuyến thông báo kết hợp, chuyển tiếp các cảnh báo đến cả kênh Slack `#tf4-alerts` và danh sách email của đội vận hành/kiểm toán (bao gồm `bui********@dtu.edu.vn`):

```yaml
    config:
      global:
        resolve_timeout: 5m
        smtp_smarthost: 'smtp.gmail.com:587'
        smtp_from: 'tf4-on-call-email@gmail.com'
        smtp_auth_username: 'tf4-on-call-email@gmail.com'
        smtp_auth_password_file: '/etc/alertmanager/secrets/password'
        smtp_require_tls: true
      route:
        group_by: ['alertname']
        group_wait: 10s
        group_interval: 10s
        repeat_interval: 1h
        receiver: 'combined-notifications'
      receivers:
        - name: 'combined-notifications'
          slack_configs:
            - channel: '#tf4-alerts'
              api_url: 'http://localhost:8080/dummy-slack-webhook'
              send_resolved: true
          email_configs:
            - to: 'bui********@dtu.edu.vn'
              send_resolved: true
            - to: 'van********@gmail.com'
              send_resolved: true
            - to: 'ngo********@gmail.com'
              send_resolved: true
```

---

## 4. Minh chứng Kết nối Môi trường (Verification Evidence)

Các kết nối tới cụm EKS phục vụ audit đã được thiết lập thành công từ máy kiểm toán cá nhân:

### 4.1 Xác thực SSO & AWS STS Identity
```powershell
PS> aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-982572xxxxxx
{
    "UserId": "AROA6J6GDWLZM2E7DFKLA:<USERNAME>",
    "Account": "982572xxxxxx",
    "Arn": "arn:aws:sts::982572xxxxxx:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_3c6f2df16efb4594/<USERNAME>"
}
```

### 4.2 Thiết lập Session Manager Tunnel thành công
Phiên SSM kết nối tới Bastion Host `i-0ea522xxxxxxxxx` để forward cổng Grafana (`13000 -> 3000`) chạy thông suốt ở chế độ background:
```powershell
PS> aws ssm start-session --target i-0ea522xxxxxxxxx --document-name AWS-StartPortForwardingSession --profile TF4-AuditReadOnlyAndAnalyze-982572xxxxxx --region us-east-1 --% --parameters "{\"portNumber\":[\"13000\"],\"localPortNumber\":[\"3000\"]}"

Starting session with SessionId: <USERNAME>-091a1a72df29ca28
Port 3000 opened for sessionId <USERNAME>-091a1a72df29ca28.
Waiting for connections...
```

### 4.3 Đọc logs và thông tin Kubernetes Pods trên cụm
```powershell
PS> kubectl get pods -n techx-observability
NAME                                     READY   STATUS      RESTARTS   AGE
grafana-5bfd99cc46-8wbmx                 4/4     Running     0          18m
prometheus-5c799696f6-tll2n              2/2     Running     0          18m
techx-observability-alertmanager-0       1/1     Running     0          2m37s
```

---

## 5. Kết quả Cảnh báo nổ trên Slack & Email (Sub-task 4)

*(Hình ảnh tin nhắn test notification từ kênh Slack và Email)*

![Slack Alert Screenshot](./screenshots/slack_alert_fired.png)

---

## 6. Nhật ký Thay đổi cấu hình & Lý do thực hiện (Change Log & Rationale)

Dưới đây là bảng tổng hợp chi tiết các file cấu hình đã được chỉnh sửa và lý do nghiệp vụ tương ứng:

| Tệp tin thay đổi | Nội dung đã chỉnh sửa | Lý do thực hiện |
| :--- | :--- | :--- |
| [`techx-corp-chart/prometheus/flash-sale-alerts.yaml`](../../../techx-corp-chart/prometheus/flash-sale-alerts.yaml) | Thêm 6 Alert Rules mới:<br>- `CheckoutLatencyP95High`<br>- `PaymentSuccessRateLow`<br>- `PaymentLatencyP95High`<br>- `PostgreSqlDown`<br>- `ValkeyCartDown`<br>- `KafkaDown` | **Đáp ứng Sub-task 2**: Xây dựng các câu truy vấn SLI (PromQL) để đo lường độ trễ và tỷ lệ lỗi của luồng Checkout/Payment, cũng như giám sát trạng thái sống sót của Database/Queue. Điều này giúp phát hiện sớm các nguy cơ đe dọa cam kết SLO. |
| [`techx-corp-chart/values.yaml`](../../../techx-corp-chart/values.yaml) | - Cấu hình định tuyến Alertmanager gửi song song tới cả **Slack Webhook** (`#tf4-alerts`) và **Email SMTP** (Gmail).<br>- Thêm email nhận cảnh báo mới: **`bui********@dtu.edu.vn`**.<br>- Giữ nguyên 2 email on-call cũ: `van********@gmail.com` và `ngo********@gmail.com`. | **Đáp ứng Sub-task 3**: Thiết lập Alertmanager nhận tin nhắn và định tuyến cảnh báo.<br>- Tích hợp Slack để phục vụ chụp ảnh minh chứng (DOD).<br>- Tích hợp Email và bổ sung `bui********@dtu.edu.vn` để đảm bảo kiểm toán viên nhóm CDO07 trực tiếp nhận được bản tin cảnh báo song song với đội On-call. |
| [`scripts/verify-flash-sale-alerts.sh`](../../../scripts/verify-flash-sale-alerts.sh) | Cập nhật `EXPECTED_RULE_COUNT` thành `21`. | Đảm bảo script xác thực kiểm tra đúng 21 quy tắc cảnh báo (15 rules baseline cũ + 6 rules SLO mới thêm). |
| [`docs/audit/runbooks/flash-sale-alerts.md`](../../../docs/audit/runbooks/flash-sale-alerts.md) | Thêm hướng dẫn xử lý sự cố cho 6 rules mới. | Đảm bảo tính sẵn sàng vận hành của tài liệu hướng dẫn on-call khi cảnh báo nổ. |
