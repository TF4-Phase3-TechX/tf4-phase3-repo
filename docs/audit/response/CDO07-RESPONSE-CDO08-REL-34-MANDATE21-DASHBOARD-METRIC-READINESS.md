# Phản hồi CDO07 cho CDO08-REL-34: Mức sẵn sàng metric cho dashboard Mandate 21

**Ngày:** 2026-07-29  
**Người tạo:** Trần Minh Quang  
**Đơn vị phản hồi:** CDO07 - Auditability  
**Requester:** CDO08
**Request liên quan:** `CDO08-REL-34-REQUEST-CDO07-MANDATE21-DASHBOARD.md`  
**Mandate:** `MANDATE-21 - DR Failover`

## 1. Phạm vi đối chiếu

CDO07 kiểm tra yêu cầu dashboard của CDO08 theo 3 nguồn:

- Yêu cầu Mandate 21 trong `MANDATE-21-dr-failover.md`.
- Yêu cầu dashboard trong `CDO08-REL-34-REQUEST-CDO07-MANDATE21-DASHBOARD.md`.
- Dashboard hiện tại `Single-AZ Loss Drill (Mandate 21)` trong `techx-corp-chart/grafana/provisioning/dashboards/mandate21-drill-dashboard.json`.

Mục tiêu của dashboard là hỗ trợ trình bày bằng chứng cho Single-AZ loss drill: hệ thống vẫn phục vụ được traffic, workload tự phục hồi, đơn hàng không mất/không trùng, và các thành phần phụ thuộc như RDS, Valkey, MSK không làm gãy luồng nghiệp vụ.

## 2. Kết quả kiểm tra metric live từ Prometheus

Các query sau đã được kiểm tra trong Grafana Explore với datasource Prometheus và không trả về data:

```promql
count(kube_horizontalpodautoscaler_status_current_replicas{namespace="techx-tf4"})
count(k8s_node_condition{condition="Ready"})
count(k8s_node_condition{condition="Ready", cloud_availability_zone!=""})
count(k8s_pod_phase{k8s_namespace_name="techx-tf4", cloud_availability_zone!=""})
count(kube_node_labels)
count(postgresql_backends)
count(redis_connected_clients)
count(kafka_consumergroup_current_offset)
count(kafka_topic_partition_current_offset)
```

Kết luận: hệ thống hiện tại có đủ metric cho phần Golden Signals và một phần workload Kubernetes, nhưng chưa đủ metric để chứng minh đầy đủ các yêu cầu failover cấp AZ, database writer failover, Valkey, MSK lag, và tính đúng đắn đơn hàng.

## 3. Panel có thể triển khai ngay bằng metric hiện có

| Panel | Mục đích | Metric có thể dùng | Trạng thái |
|---|---|---|---|
| Frontend / Storefront RPS | Chứng minh hệ thống vẫn nhận traffic trong drill | `traces_span_metrics_calls_total` | Đủ |
| Load Generator Request Rate | Chứng minh traffic test đang chạy | `traces_span_metrics_calls_total{service_name="load-generator"}` | Đủ |
| Browse / Cart / Checkout Success Rate | Theo dõi các luồng nghiệp vụ chính có còn thành công không | Span metrics theo service/span/status | Đủ |
| Error Rate theo service | Phát hiện lỗi tăng trong lúc AZ loss | `traces_span_metrics_calls_total` với status/error | Đủ |
| Latency p95/p99 | Chứng minh SLO không suy giảm quá mức | `traces_span_metrics_duration_*` | Đủ nếu histogram span metrics đang có data |
| Checkout throughput timeline | Theo dõi luồng checkout trong suốt drill | Span metrics của checkout/order path | Đủ cho request-level evidence |
| Deployment available replicas | Chứng minh workload còn replica available sau sự cố | `k8s_deployment_available` | Đủ |
| Pod phase theo workload | Theo dõi pod Running/Pending/Failed | `k8s_pod_phase` | Đủ ở mức namespace/workload |
| Container restarts | Phát hiện pod restart bất thường | `k8s_container_restarts` | Đủ |
| Node CPU / Memory | Theo dõi áp lực node trong drill | `k8s_node_cpu_usage`, `k8s_node_memory_*` | Đủ nếu metric đang có data |

Các panel trên nên là phần lõi của dashboard mới vì có thể dựng ngay và phục vụ được phần lớn bằng chứng vận hành: traffic, lỗi, latency, replica, pod health, và resource pressure.

## 4. Panel bắt buộc nhưng chưa đủ metric

| Panel CDO08 yêu cầu | Vì sao cần cho Mandate 21 | Vấn đề hiện tại | CDO07 cần request CDO08 |
|---|---|---|---|
| Active Load Generator Users | Cần biết tải giả lập có đúng mức trong drill không | Dashboard hiện tại dùng `vector(200)`, là số tĩnh, không phải metric live | Cung cấp metric users thật từ load generator/Locust, hoặc đổi yêu cầu sang request rate nếu không có active users |
| HPA Current / Desired Replicas | Cần chứng minh autoscaling phản ứng khi AZ loss làm giảm capacity | `kube_horizontalpodautoscaler_status_current_replicas` không có data; kube-state-metrics hiện không khả dụng cho HPA | Bật kube-state-metrics/HPA metrics hoặc cung cấp nguồn metric thay thế |
| Node Ready by AZ | Cần chứng minh AZ nào mất node và các AZ còn lại vẫn Ready | `k8s_node_condition{condition="Ready"}` không có data | Cung cấp node readiness metric hoặc bằng chứng từ REL-33 observer/kubectl/AWS |
| Pod Placement by AZ | Cần chứng minh workload được phân bố/chuyển dịch qua AZ còn lại | `k8s_pod_phase` không có label `cloud_availability_zone`; `kube_node_labels` không có data | Cung cấp node-to-AZ label/metric hoặc mapping node -> AZ để join vào dashboard |
| RDS Writer / Failover State | Cần chứng minh database không mất writer và failover đúng | `postgresql_backends` không có data; kể cả có thì chỉ là connection count, không chứng minh writer/AZ failover | Cung cấp CloudWatch/RDS metric hoặc observer metric về writer endpoint/role/AZ |
| Valkey Connections / Ops | Cần chứng minh cache/session/cart không làm gãy luồng khi failover | `redis_connected_clients` không có data | Cung cấp ElastiCache/Valkey metric hoặc thống nhất dùng cart SLO làm bằng chứng thay thế |
| MSK Consumer Lag / Offsets | Cần chứng minh event pipeline không backlog/mất event | `kafka_consumergroup_current_offset` và `kafka_topic_partition_current_offset` không có data | Cung cấp MSK exporter/CloudWatch metric cho lag/offset |
| Confirmed Orders | Cần chứng minh không mất đơn hàng, không chỉ là có request checkout | Dashboard hiện tại đếm request checkout/frontend, chưa chứng minh order đã persist/confirmed | Cung cấp metric order confirmed từ backend hoặc query reconciliation |
| Missing / Duplicate Orders | Đây là bằng chứng trực tiếp cho RPO/no data loss/no duplicate | Chưa thấy metric hoặc query đối soát | Cung cấp reconciliation metric/query cho missing/duplicate order |
| RTO Drill Markers | Cần xác định thời điểm fault injection, detection, recovery để tính RTO | Dashboard có timeline metric nhưng thiếu marker sự kiện drill | Cung cấp drill annotation/marker metric hoặc timestamp chuẩn từ runbook |

## 5. Panel chưa đủ metric nhưng vẫn cần triển khai

Các panel chưa đủ metric không nên bị bỏ hẳn khỏi scope, vì chúng map trực tiếp vào yêu cầu Mandate 21:

- HPA, Node Ready by AZ, Pod Placement by AZ: cần để chứng minh recovery ở tầng Kubernetes khi mất một AZ.
- RDS Writer / Failover State: cần để chứng minh database vẫn có writer hợp lệ sau failover.
- MSK Lag / Offsets: cần để chứng minh event pipeline không bị backlog hoặc mất tiến trình xử lý.
- Confirmed Orders và Missing / Duplicate Orders: cần để chứng minh yêu cầu quan trọng nhất của Mandate 21 là không mất đơn, không trùng đơn.
- RTO Drill Markers: cần để tính recovery time bằng mốc thời gian rõ ràng, thay vì nhìn biểu đồ thủ công.

CDO07 có thể dựng dashboard mới với phần panel có data trước, nhưng các panel trên cần được đánh dấu là `Blocked by missing metric` hoặc `Pending CDO08 data source`. Nếu bỏ khỏi dashboard mà không có ghi chú, dashboard sẽ không đủ sức làm bằng chứng cho Mandate 21.

## 6. Khuyến nghị của CDO07

CDO07 đề xuất chia dashboard mới thành 2 nhóm:

1. **Metric-ready panels:** triển khai ngay bằng Prometheus metric hiện có, dùng để trình bày traffic, latency, error rate, pod health, deployment availability, và resource pressure.
2. **Evidence-required panels:** vẫn đặt trong thiết kế dashboard nhưng hiển thị trạng thái blocked/pending cho đến khi CDO08 cung cấp metric hoặc nguồn dữ liệu thay thế.

Với các metric chưa có, CDO07 cần CDO08 xác nhận một trong hai hướng:

- CDO08 bổ sung metric/source cần thiết để panel chạy live trong Grafana.
- CDO08 chấp nhận bằng chứng thay thế, ví dụ screenshot AWS Console, output runbook, query đối soát, hoặc annotation thủ công kèm timestamp.

## 7. Quyết định cần từ CDO08

CDO07 cần CDO08 phản hồi rõ các điểm sau:

- Active users có bắt buộc là số user live không, hay request rate từ load generator là đủ?
- HPA panel có bắt buộc cho bài trình bày Mandate 21 không? Nếu có, CDO08 cần cung cấp HPA metrics.
- AZ-level evidence lấy từ Prometheus, REL-33 observer, hay AWS/kubectl output?
- RDS writer failover sẽ được chứng minh bằng metric nào?
- Valkey và MSK có bắt buộc xuất hiện trong dashboard live không, hay có thể dùng evidence ngoài dashboard?
- Confirmed/missing/duplicate orders sẽ lấy từ metric backend hay query đối soát database?

