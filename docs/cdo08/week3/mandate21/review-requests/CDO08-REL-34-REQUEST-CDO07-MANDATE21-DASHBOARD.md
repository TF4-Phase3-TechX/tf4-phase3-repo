# CDO08-REL-34 Request CDO07: Dashboard cho Mandate 21 AZ-loss drill

**Ngày yêu cầu:** 2026-07-29  
**Requester:** CDO08 - Reliability / Platform  
**Reviewer/Owner mong muốn:** CDO07 - Observability / Auditability  
**Mandate:** MANDATE-21 - DR Failover  
**Task liên quan:** CDO08-REL-34, CDO08-REL-35  
**Mức độ:** P0 trước witnessed AZ-loss drill

## 1. Bối cảnh

CDO08 cần chạy drill mất 1 Availability Zone dưới tải thật cho Mandate 21. Mentor sẽ quan sát hệ thống live và cần thấy bằng số liệu:

- traffic vẫn có tải thật trong suốt drill;
- luồng browse -> cart -> checkout có thể dip rồi recover trong RTO đã cam kết;
- pod/node chuyển dịch khỏi AZ lỗi;
- RDS, Valkey và MSK vẫn healthy hoặc failover/recover đúng kỳ vọng;
- không mất confirmed order.

Dashboard thử nghiệm hiện tại của CDO08 không query được data ổn định, nên CDO08 request CDO07 hỗ trợ tạo dashboard Grafana chính thức cho Mandate 21 dựa trên metric live đang có trong Prometheus/Grafana.

## 2. Dashboard cần tạo

**Tên đề xuất:** `Mandate 21 AZ Loss Drill Dashboard`

**Datasource:** Prometheus hiện tại của `techx-observability`.

**Yêu cầu chung:**

- Các panel phải query được data live, không dùng mock/static value.
- Time range phục vụ quay demo: `Last 30 minutes` hoặc `Last 1 hour`.
- Auto-refresh đề xuất: `5s` hoặc `10s`.
- Dashboard phải đủ rõ để quay màn hình trong lúc mentor gây AZ loss.
- Nếu một metric chưa tồn tại, CDO07 vui lòng ghi rõ metric thiếu và đề xuất metric thay thế đang có sẵn.

## 3. Các panel bắt buộc

| Group | Panel | Vì sao cần |
|---|---|---|
| Load | Request rate tổng qua storefront/frontend-proxy | Chứng minh drill đang chạy dưới tải thật, tránh trường hợp SLO đẹp vì không có traffic. |
| Load | Load-generator active users / request count / error count | Xác nhận nguồn tải còn sống và workload đang bơm traffic ổn định trong failure window. |
| Business SLO | Browse success rate (%) | Browse là customer-facing path. Cần thấy browse có bị ảnh hưởng khi mất AZ không. |
| Business SLO | Cart success rate (%) | Cart nằm trong purchase funnel. Cần biết user còn thêm/xem giỏ hàng được trong lúc failover không. |
| Business SLO | Checkout success rate (%) | Checkout là revenue-critical path. Đây là chỉ số chính để tính RTO và pass/fail Mandate 21. |
| Business SLO | Browse/Cart/Checkout error rate | Giúp nhìn spike lỗi rõ hơn success rate, nhất là lỗi ngắn trong lúc endpoint bị gỡ hoặc client reconnect. |
| Latency | Browse/Cart/Checkout p95 latency | Success rate có thể vẫn đạt nhưng latency tăng mạnh. Panel này chứng minh khách hàng "gần như không hay biết". |
| Latency | Checkout p99 latency nếu metric đủ ổn định | Checkout có thể bị tail latency trong lúc RDS/Valkey/MSK reconnect. p99 giúp phát hiện ảnh hưởng xấu bị p95 che mất. |
| RTO | SLO dip timestamp và recovery timestamp | Cần marker/timeline để tính RTO thực tế: từ lúc SLO dip hoặc mentor fault start đến khi checkout phục hồi. |
| K8s Runtime | Ready replicas theo workload revenue path | Chứng minh các service quan trọng vẫn còn đủ replica hoặc tự phục hồi sau khi mất AZ. |
| K8s Runtime | Pod restart count / restart rate theo workload | Phát hiện crash/restart bất thường do mất AZ, dependency reconnect hoặc cấu hình sai. |
| K8s Runtime | Pending / FailedScheduling / CrashLoopBackOff pods | Đây là hard-stop runtime gate. Nếu xuất hiện trong drill thì cần thấy ngay. |
| HPA | Current replicas vs desired/max replicas cho frontend, frontend-proxy, cart, checkout, product-catalog, currency | Khi traffic dồn sang AZ còn sống, HPA có thể scale. Panel này chứng minh autoscaling không bị quota/admission chặn. |
| Node/AZ | Node Ready count grouped by AZ | Chứng minh đúng là một AZ bị mất/không còn node ready, và AZ còn lại vẫn còn capacity. |
| Node/AZ | Pod placement grouped by node/AZ cho workload revenue path | Chứng minh pod được trải AZ trước drill và reschedule/sống ở AZ còn lại sau fault. |
| Node/AZ | CPU/memory usage hoặc pressure theo node | Khi mất một AZ, tải dồn vào node còn lại. Panel này cho biết có nghẽn tài nguyên không. |
| Data Store | RDS availability / connection count / primary or writer health nếu có metric | RDS là store confirmed order. Cần thấy connection phục hồi và không biến thành SPOF. |
| Data Store | Valkey availability / connected clients / operation rate nếu có metric | Cart dùng Valkey. Cần thấy client reconnect/failover không làm cart path sập lâu. |
| Data Store | MSK broker/topic health và consumer lag cho orders/accounting/fraud nếu có metric | RPO confirmed order phụ thuộc order event không mất và consumer catch up. Lag giúp chứng minh async path phục hồi. |
| RPO | Confirmed checkout/order count trong failure window | Đối chiếu với MSK/accounting để chứng minh RPO = 0 cho confirmed orders. |
| RPO | Missing/duplicate order indicator nếu có query sẵn | Mandate 21 không chỉ cần service sống, mà còn không mất hoặc nhân đôi confirmed order. |

## 4. Panel ưu tiên nếu không đủ metric

Nếu không đủ thời gian hoặc metric chưa đủ, CDO07 vui lòng ưu tiên theo thứ tự:

1. Request rate + checkout success rate + checkout error rate + checkout p95.
2. Browse/cart success rate.
3. Ready replicas + pod restarts + pod placement theo node/AZ.
4. Node Ready grouped by AZ.
5. RDS/Valkey/MSK health hoặc metric thay thế.
6. Order count / consumer lag cho RPO evidence.

## 5. Output mong muốn từ CDO07

CDO07 vui lòng cung cấp:

- Dashboard JSON hoặc PR vào source repo chứa dashboard Grafana.
- Tên dashboard và URL sau khi sync.
- Danh sách panel nào query được live.
- Danh sách panel nào chưa query được, lý do và metric thay thế nếu có.
- Query/PromQL chính dùng cho:
  - checkout success rate;
  - checkout p95/p99;
  - request rate;
  - pod/node AZ visibility;
  - MSK consumer lag/order event count nếu có.

## 6. Acceptance criteria

- Dashboard mở được qua private Grafana path: `https://grafana.techx-tf4.site/grafana`.
- Trong lúc có load-generator chạy, các panel chính có data trong vòng `Last 5 minutes`.
- Không có panel quan trọng nào hiển thị `No data` mà không có giải thích.
- Dashboard đủ để quay video evidence cho REL-35:
  - thấy tải đang chạy;
  - thấy SLO dip/recover;
  - thấy node/pod/AZ thay đổi;
  - thấy managed store/order path không mất dữ liệu hoặc có query đối chiếu riêng.

## 7. Ghi chú scope

- CDO08 không yêu cầu CDO07 mở public ingress cho Grafana.
- Không cần publish OpenSearch, OTLP, Kubernetes API hoặc ArgoCD.
- Nếu cần metric mới từ app/runtime, CDO07 vui lòng ghi rõ để CDO08/owner liên quan tạo task bổ sung.
