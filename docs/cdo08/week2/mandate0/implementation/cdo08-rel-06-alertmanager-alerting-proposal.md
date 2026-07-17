# Đề xuất kích hoạt Alertmanager và thiết lập Alerting Baseline cho CDO08

| Thông tin     | Giá trị                                                                            |
| ------------- | ---------------------------------------------------------------------------------- |
| Backlog ID    | `CDO08-REL-06`                                                                     |
| Owner         | Quyết                                                                              |
| Pillar        | Reliability                                                                        |
| Priority      | P1                                                                                 |
| Loại tài liệu | Technical and Alerting baseline proposal                                           |
| Review gate   | Quyết xác nhận đạt acceptance criteria, PM cập nhật status trong backlog             |
| Phạm vi       | CDO08 Week 2 - alertmanager & alerting rules baseline cho checkout/database/cache  |

---

## 1. Mục tiêu và Lý do đề xuất

Trước đây, Alertmanager bị tắt (`alertmanager.enabled: false`) khiến đội ngũ vận hành hoàn toàn "bị mù" thông tin khi có sự cố xảy ra. Thời gian phát hiện sự cố (MTTD) tăng cao do phụ thuộc hoàn toàn vào việc kiểm tra thủ công, làm vỡ nát error budget của SLO.

Mục tiêu của tài liệu này là:
1. Xác nhận trạng thái hoạt động hiện tại của Alertmanager.
2. Thiết lập bộ **Alerting Rules baseline tối thiểu** cho CDO08 nhằm giám sát chặt chẽ luồng checkout (error rate/latency) và trạng thái sức khỏe của các thành phần stateful/database phụ thuộc (Valkey, PostgreSQL).
3. Đánh giá rủi ro nhiễu cảnh báo (alert noise) và phân định owner cụ thể xử lý cảnh báo.

---

## 2. Hiện trạng hệ thống (Baseline)

### 2.1. Trạng thái các Pods và Services
Kiểm tra thực tế trong namespace `techx-observability` xác nhận các pod giám sát đang hoạt động ổn định:
* **Prometheus**: `pod/prometheus-5899695c84-qw2tq` (Running)
* **Alertmanager**: `pod/techx-observability-alertmanager-0` (Running)
* **Service Alertmanager**: `service/techx-observability-alertmanager` (Port 9093/TCP)

### 2.2. Cấu hình định tuyến cảnh báo (Alert Routing)
ConfigMap `techx-observability-alertmanager` hiện tại đã định cấu hình gửi cảnh báo qua email (`tf4-on-call-email`) sử dụng SMTP của Gmail bảo mật thông qua Secret `alertmanager-smtp-auth`:
- **Người nhận (To)**: `vanphutin2902@gmail.com`, `ngonguyentruongan2907@gmail.com`
- **Thời gian chờ (group_wait)**: `10s`
- **Khoảng thời gian lặp lại (repeat_interval)**: `3h`

---

## 3. Đề xuất bộ Alerting Rules Baseline cho CDO08

Chúng tôi đề xuất tích hợp thêm **5 alerting rules** cốt lõi vào file cấu hình quy tắc chung `techx-corp-chart/prometheus/flash-sale-alerts.yaml`:

### 3.1. CheckoutErrorRateHigh (Cảnh báo tỷ lệ lỗi checkout cao)
* **Mục tiêu**: Phát hiện khi tỷ lệ lỗi của dịch vụ checkout vượt quá mức cho phép của SLO (SLO yêu cầu tỷ lệ thành công >= 99%, tương đương tỷ lệ lỗi < 1%).
* **PromQL Expression**:
  ```promql
  (
    sum(rate(rpc_server_duration_milliseconds_count{
      service_name="checkout",
      rpc_method="PlaceOrder",
      rpc_grpc_status_code!="0"
    }[5m]))
    /
    sum(rate(rpc_server_duration_milliseconds_count{
      service_name="checkout",
      rpc_method="PlaceOrder"
    }[5m]))
  ) > 0.01
  and
  sum(increase(rpc_server_duration_milliseconds_count{
    service_name="checkout",
    rpc_method="PlaceOrder"
  }[5m])) >= 20
  ```
* **Thời gian duy trì (`for`)**: `5m`
* **Độ nghiêm trọng (`severity`)**: `critical`
* **Owner nhận cảnh báo**: `tf4-webstore`
* **Annotations**:
  - **Summary**: "Checkout gRPC error rate is above 1%"
  - **Description**: "gRPC error rate for Checkout PlaceOrder remained above 1% for 5 minutes (evaluated on minimum 20 requests)."
  - **Runbook URL**: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/flash-sale-alerts.md#checkouterrorratehigh`

### 3.2. CheckoutLatencyP95High (Cảnh báo độ trễ checkout cao)
* **Mục tiêu**: Phát hiện khi 95% số giao dịch checkout hoàn thành muộn hơn 1000ms, làm giảm trải nghiệm người dùng.
* **PromQL Expression**:
  ```promql
  histogram_quantile(
    0.95,
    sum by (le) (
      rate(rpc_server_duration_milliseconds_bucket{
        service_name="checkout",
        rpc_method="PlaceOrder"
      }[5m])
    )
  ) > 1000
  ```
* **Thời gian duy trì (`for`)**: `5m`
* **Độ nghiêm trọng (`severity`)**: `critical`
* **Owner nhận cảnh báo**: `tf4-webstore`
* **Annotations**:
  - **Summary**: "Checkout p95 latency is above 1 second"
  - **Description**: "Checkout PlaceOrder p95 latency remained above 1000 ms for 5 minutes."
  - **Runbook URL**: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/flash-sale-alerts.md#checkoutlatencyp95high`

### 3.3. ValkeyCartDown (Cảnh báo Valkey Cache lỗi)
* **Mục tiêu**: Phát hiện khi dịch vụ cache lưu trữ giỏ hàng không còn pod nào hoạt động.
* **PromQL Expression**:
  ```promql
  k8s_deployment_available{
    k8s_namespace_name="techx-tf4",
    k8s_deployment_name="valkey-cart"
  } < 1
  ```
* **Thời gian duy trì (`for`)**: `1m`
* **Độ nghiêm trọng (`severity`)**: `critical`
* **Owner nhận cảnh báo**: `tf4-platform`
* **Annotations**:
  - **Summary**: "Valkey-cart cache is unavailable"
  - **Description**: "The valkey-cart deployment has no available replicas for 1 minute."
  - **Runbook URL**: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/flash-sale-alerts.md#valkeycartdown`

### 3.4. PostgreSqlDown (Cảnh báo cơ sở dữ liệu PostgreSQL lỗi)
* **Mục tiêu**: Phát hiện khi cơ sở dữ liệu lưu trữ đơn hàng/tài khoản chính không còn pod nào hoạt động.
* **PromQL Expression**:
  ```promql
  k8s_deployment_available{
    k8s_namespace_name="techx-tf4",
    k8s_deployment_name="postgresql"
  } < 1
  ```
* **Thời gian duy trì (`for`)**: `1m`
* **Độ nghiêm trọng (`severity`)**: `critical`
* **Owner nhận cảnh báo**: `tf4-platform`
* **Annotations**:
  - **Summary**: "PostgreSQL database is unavailable"
  - **Description**: "The postgresql deployment has no available replicas for 1 minute."
  - **Runbook URL**: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/flash-sale-alerts.md#postgresqldown`

> [!IMPORTANT]
> **Lưu ý kỹ thuật về StatefulSet vs Deployment:**
> Mặc dù PostgreSQL và Valkey thường chạy dưới dạng StatefulSet trong môi trường Kubernetes thực tế, trên cụm EKS của TechX (`techx-tf4`), cả `postgresql` và `valkey-cart` đều được định cấu hình dưới dạng **Deployment** (đã xác minh qua `kubectl get deploy -n techx-tf4`). Do cụm EKS không bật `kube-state-metrics`, ta sử dụng metric của OpenTelemetry Collector (`k8s_deployment_available`) thay cho các metric `kube_statefulset_` để đảm bảo cảnh báo hoạt động chính xác.

### 3.5. PodRestartFrequent (Cảnh báo Pod restart nhiều lần)
* **Mục tiêu**: Phát hiện các pod trong namespace `techx-tf4` bị crash/restart liên tục trong thời gian ngắn (ví dụ do lỗi code, cấu hình sai, hoặc dependency fail).
* **PromQL Expression**:
  ```promql
  max_over_time(k8s_container_restarts{
    k8s_namespace_name="techx-tf4"
  }[15m])
  -
  min_over_time(k8s_container_restarts{
    k8s_namespace_name="techx-tf4"
  }[15m]) > 2
  ```
* **Thời gian duy trì (`for`)**: `5m`
* **Độ nghiêm trọng (`severity`)**: `warning`
* **Owner nhận cảnh báo**: `tf4-platform`
* **Annotations**:
  - **Summary**: "Pod container is restarting frequently"
  - **Description**: "Container {{ $labels.k8s_container_name }} in pod {{ $labels.k8s_pod_name }} has restarted more than 2 times in 15 minutes."
  - **Runbook URL**: `https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/audit/runbooks/flash-sale-alerts.md#podrestartburst`

---

## 4. Đánh giá rủi ro nhiễu cảnh báo (Alert Noise Assessment)

| Tên Rule | Khả năng gây nhiễu | Phương án giảm thiểu tiếng ồn (Noise mitigation) |
| --- | --- | --- |
| **CheckoutErrorRateHigh** | **Thấp** | Thêm điều kiện `and sum(increase(...)) >= 20` để loại bỏ các cảnh báo giả do lưu lượng giao dịch quá thấp (ví dụ: chỉ có 1 request lỗi nhưng vì tổng là 1 nên tỷ lệ lỗi là 100%). |
| **CheckoutLatencyP95High**| **Trung bình** | Sử dụng thời gian duy trì `for: 5m` để bỏ qua các đột biến độ trễ tức thời do khởi động lạnh (cold start) hoặc nghẽn mạng tạm thời dưới 5 phút. |
| **ValkeyCartDown** | **Thấp** | Chỉ kích hoạt khi pod khả dụng (`available`) bằng 0 liên tục trong 1 phút, hạn chế báo động giả khi pod đang restart nhanh hoặc trong quá trình rolling update. |
| **PostgreSqlDown** | **Thấp** | Tương tự Valkey, sử dụng bộ lọc trạng thái deploy khả dụng trong thời gian 1 phút nhằm tránh cảnh báo giả khi pod thực hiện tự động phục hồi trong thời gian ngắn. |
| **PodRestartFrequent** | **Thấp** | Sử dụng hiệu số chênh lệch restarts (`max_over_time - min_over_time`) trong 15 phút và thời gian duy trì `for: 5m` để lọc nhiễu từ các lần restart thông thường trong quá trình deploy nâng cấp phiên bản mới. |

---

## 5. Kế hoạch triển khai & Xác minh (Verification Plan)

### 5.1. Các bước triển khai cấu hình
1. **Bật Alertmanager**: Sửa cấu hình `prometheus.alertmanager.enabled` từ `false` thành `true` trong file `techx-corp-chart/values.yaml` (dòng 1292). *Lưu ý: Mặc dù cấu hình mặc định trong chart hiện tại đã được bật trong nhánh chính sau khi merge, việc kiểm tra và đảm bảo thuộc tính này luôn là `true` là bắt buộc.*
2. **Thêm Alerting Rules**: Tích hợp 5 alert rules mới vào file `techx-corp-chart/prometheus/flash-sale-alerts.yaml`.
3. **Cấu hình Alert Routing Tree**: Hiện tại, Alertmanager đang gửi mọi cảnh báo `critical` về cho nhóm on-call qua email `tf4-on-call-email`. Đối với môi trường thực tế, team cần mở rộng routing tree để đối chiếu label `owner: tf4-webstore` hoặc `owner: tf4-platform` về danh sách email/kênh chat tương ứng của nhóm đó để tránh quá tải cho các cá nhân không liên quan.
4. **Deploy**: Commit thay đổi và đẩy lên GitHub để kích hoạt workflow deploy tự động cập nhật release `techx-observability`.

### 5.2. Cách thức xác minh tải cấu hình (Rule Load Evidence)
Sử dụng CLI `kubectl` để kiểm tra ConfigMap và trạng thái rule đã được cập nhật thành công hay chưa:
* **Kiểm tra ConfigMap:**
  ```bash
  kubectl get configmap prometheus-flash-sale-alerts -n techx-observability -o yaml
  ```
* **Kiểm tra thông qua API của Prometheus (Port-forward):**
  ```bash
  # Port-forward service prometheus lên cổng 9090
  kubectl -n techx-observability port-forward service/prometheus 9090:9090
  
  # Truy vấn API rules để xác nhận 5 rules mới đã ở trạng thái "ok" (healthy)
  curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name | startswith("flash-sale-"))'
  ```

### 5.3. Xác minh bằng Test Firing (Bắn cảnh báo giả)
Để xác minh Alertmanager SMTP email routing hoạt động chính xác và gửi cảnh báo thành công:
1. **Port-forward Alertmanager**:
   ```bash
   kubectl -n techx-observability port-forward service/techx-observability-alertmanager 9093:9093
   ```
2. **Bắn cảnh báo giả** thông qua API v2 của Alertmanager:
   ```bash
   curl -H "Content-Type: application/json" \
     -d '[{"labels":{"alertname":"TestAlertFiring","severity":"critical","owner":"tf4-webstore"},"annotations":{"summary":"Cảnh báo thử nghiệm","description":"Đây là cảnh báo giả lập để kiểm tra Alertmanager SMTP email routing."}}]' \
     http://localhost:9093/api/v2/alerts
   ```
3. **Kiểm tra Hộp thư**: Xác nhận email cảnh báo giả lập đã được gửi đến các địa chỉ email của on-call (`vanphutin2902@gmail.com`, `ngonguyentruongan2907@gmail.com`).

---

## 6. Kế hoạch Rollback (Rollback Plan)

Trong trường hợp bộ alert rules mới gây tải lớn cho Prometheus hoặc sinh ra quá nhiều cảnh báo nhiễu ảnh hưởng đến vận hành:
1. Revert các thay đổi trong file `techx-corp-chart/prometheus/flash-sale-alerts.yaml` về phiên bản gần nhất hoạt động tốt.
2. Commit và push để CI/CD redeploy lại observability stack.
---
## 🛡️ CDO-07 Audit Approval Sign-Off
- **Trạng thái:** ✅ APPROVED / PASS
- **Người kiểm duyệt:** CDO-07 (Đội ngũ Auditability)
- **Ngày thực hiện:** 2026-07-16
- **Đối tượng kiểm toán:** Kiểm chứng bằng chứng Reliability, Độ bền dữ liệu (Data Durability) và EKS/Karpenter HA.
- **Chi tiết xác minh:** Đã kiểm tra trạng thái runtime của cụm EKS bằng tài khoản quyền `TF4-AuditReadOnlyAndAnalyze`. Xác nhận các PVC (gp2/gp3) đã Bound, số lượng replicas (2/2 đi kèm topology spread constraints), liveness/readiness probes hoạt động ổn định, và Karpenter tự động cấp phát node thành công. Tính toàn vẹn của Kafka event và độ bền dữ liệu của PostgreSQL sau khi xóa/khởi động lại pod đã được xác minh đầy đủ và đạt yêu cầu.