# Epic 08 - Reliability Scan Findings

**Owner:** CDO08  
**Pillar:** Reliability  
**Scan time:** 2026-07-09 09:31 ICT  
**Environment:** EKS `techx-tf4-cluster`, namespace `techx-tf4`  
**Purpose:** Tổng hợp các lỗ hổng/gap reliability hiện tại để đưa vào Jira tổng và backlog tuần sau.

## Scope

Scan này tập trung vào các rủi ro reliability có evidence từ runtime, source hoặc Helm chart:

- Replica coverage của service critical.
- Readiness/liveness probe coverage.
- Stateful reliability cho PostgreSQL, Valkey, Kafka.
- Alerting.
- Checkout consistency/availability risk.

## Runtime Context

Finding cũ về nhiều service `ImagePullBackOff` không còn đúng ở thời điểm scan này.

Commands đã kiểm tra:

```bash
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get deploy,sts,svc,ingress,pvc
curl -I http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com
```

Kết quả chính:

- Toàn bộ app pods trong `techx-tf4` đang `Running 1/1`.
- Toàn bộ deployments trong `techx-tf4` đang `READY 1/1`, `AVAILABLE 1`.
- Không có PVC trong namespace `techx-tf4`.
- Frontend public ALB trả `HTTP/1.1 200 OK`.

## Findings

| ID | Finding | Evidence | Impact | Priority gợi ý | Backlog candidate |
|---|---|---|---|---|---|
| REL-01 | Critical services đều chỉ có `1 replica` | `kubectl -n techx-tf4 get deploy` cho thấy toàn bộ deploy `1/1`; chart default `techx-corp-chart/values.yaml:27` có `replicas: 1` | Pod restart, node drain hoặc rollout lỗi có thể làm downtime service quan trọng | P1 | Tăng replica cho service critical sau khi đánh giá cost/resource |
| REL-02 | App pods không có readiness/liveness probe | Runtime jsonpath cho deploy trả rỗng readiness/liveness; chart chỉ có probe dạng comment ở `techx-corp-chart/values.yaml:152-153`; template có support probe nhưng values chưa cấu hình | Pod có thể nhận traffic khi chưa ready; app treo nhưng Kubernetes không restart đúng lúc | P1 | Bổ sung readiness/liveness probes cho checkout path và service critical |
| REL-03 | PostgreSQL, Valkey, Kafka single replica và không có PVC trong `techx-tf4` | `kubectl -n techx-tf4 get pvc` không có resources; `postgresql`, `valkey-cart`, `kafka` đều replicas `1`; PostgreSQL chỉ mount `configMap` `postgresql-init` | Stateful/data components là SPOF; restart có rủi ro mất hoặc gián đoạn dữ liệu cart/order/event | P1 | Đánh giá persistence/backup/restore và HA candidates |
| REL-05 | Prometheus/OpenSearch persistence disabled | `techx-corp-chart/values.yaml:1174-1175` Prometheus PV disabled; `techx-corp-chart/values.yaml:1222-1223` OpenSearch persistence disabled | Metric/log/trace có thể mất sau restart; khó điều tra incident và chứng minh reliability | P1/P2 | Bổ sung persistence hoặc xác định retention/evidence strategy |
| REL-06 | Alertmanager disabled | `techx-corp-chart/values.yaml:1118-1121` có `alertmanager.enabled: false` | Có dashboard nhưng thiếu cảnh báo tự động cho checkout/runtime/data; phát hiện sự cố phụ thuộc manual check | P1 | Bật alerting cho checkout error rate/latency và runtime health |
| REL-07 | Checkout trả lỗi nếu Kafka publish fail sau payment/shipping | `techx-corp-platform/src/checkout/main.go:331-347` payment/shipping xảy ra trước; `387-392` Kafka publish fail thì return `codes.Unavailable` | Khách có thể thấy checkout fail dù payment/shipping đã xảy ra; rủi ro consistency và support | P1 | Thiết kế lại post-payment event handling hoặc compensation strategy |

## Evidence Details

### REL-01 - Single replica coverage

Commands:

```bash
kubectl -n techx-tf4 get deploy
```

Kết quả:

- Các services quan trọng như `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog`, `postgresql`, `kafka`, `valkey-cart` đều chỉ có `1` available replica.

Chart evidence:

```yaml
default:
  replicas: 1
```

Việc cần làm tuần sau:

- Nam xác định danh sách service critical nên tăng replica.
- CDO04 review cost impact nếu tăng replica.
- Nguyên review technical risk trước khi rollout.

### REL-02 - Missing readiness/liveness probes

Commands:

```bash
kubectl -n techx-tf4 get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].readinessProbe}{"\t"}{.spec.template.spec.containers[0].livenessProbe}{"\n"}{end}'
```

Kết quả:

- Readiness/liveness probe đều rỗng cho app deployments được kiểm tra.

Việc cần làm tuần sau:

- Ưu tiên probes cho `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog`.
- Xác định endpoint health phù hợp từng service.
- Chuẩn bị rollback nếu probe cấu hình sai gây pod không ready.

### REL-03 - Stateful persistence/HA gap

Commands:

```bash
kubectl -n techx-tf4 get pvc
kubectl -n techx-tf4 get deploy postgresql valkey-cart kafka -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.replicas}{"\t"}{.spec.template.spec.volumes}{"\n"}{end}'
```

Kết quả:

- Không có PVC trong namespace `techx-tf4`.
- `postgresql`, `valkey-cart`, `kafka` đều 1 replica.
- PostgreSQL volume hiện thấy là configMap init, không phải persistent data volume.

Việc cần làm tuần sau:

- Phương xác nhận dữ liệu nào cần bền vững.
- Đánh giá backup/restore gap.
- Nếu đề xuất HA/managed service, phối hợp CDO04 vì có impact chi phí.

### REL-05 - Observability persistence disabled

Evidence:

```yaml
prometheus:
  server:
    persistentVolume:
      enabled: false

opensearch:
  persistence:
    enabled: false
```

Việc cần làm tuần sau:

- Xác định yêu cầu retention cho metrics/logs/traces.
- Chọn persistence hoặc external evidence strategy.

### REL-06 - Alertmanager disabled

Evidence:

```yaml
prometheus:
  alertmanager:
    enabled: false
```

Việc cần làm tuần sau:

- Bật hoặc thiết kế alerting tối thiểu cho checkout SLO.
- Định nghĩa alert cho error rate, latency p95, pod restart, dependency unavailable.

### REL-07 - Checkout Kafka failure after payment/shipping

Code evidence:

- `techx-corp-platform/src/checkout/main.go:331-347`: checkout charge card và ship order trước.
- `techx-corp-platform/src/checkout/main.go:387-392`: nếu Kafka publish fail thì return `codes.Unavailable`.

Việc cần làm tuần sau:

- Quân xác nhận behavior bằng smoke/fault evidence nếu có thể.
- Nguyên review design tradeoff: consistency vs availability.
- Đề xuất hướng xử lý: outbox pattern, retry queue, compensation, hoặc user-facing response strategy.

## Findings Không Còn Đúng Ở Thời Điểm Scan

### Historical REL-X - Nhiều service critical `ImagePullBackOff`

Finding này từng xuất hiện trong screenshot/evidence trước đó, nhưng không còn là current finding tại thời điểm scan.

Evidence hiện tại:

```bash
kubectl -n techx-tf4 get pods -o wide
```

Kết quả:

- Tất cả app pods trong `techx-tf4` đều `Running 1/1`.

Khuyến nghị:

- Không đưa vào backlog như lỗi hiện tại.
- Nếu cần giữ làm incident evidence, yêu cầu bổ sung timeline, nguyên nhân, commit/deploy đã fix.

## Suggested Backlog Items

| Backlog ID | Title | Suggested Owner | Priority |
|---|---|---|---|
| REL-BL-01 | Increase replica coverage for checkout path critical services | Nam + CDO04 + Nguyên | P1 |
| REL-BL-02 | Add readiness/liveness probes for critical app services | Nam + service owners | P1 |
| REL-BL-03 | Define persistence/backup/restore baseline for PostgreSQL, Valkey, Kafka | Phương + CDO04 | P1 |
| REL-BL-05 | Enable minimum alerting for checkout/runtime/data health | Quyết + Nam + Phương | P1 |
| REL-BL-06 | Review checkout Kafka post-payment failure behavior | Quân + Nguyên | P1 |

## Notes For Jira Epic

Reliability Week 1 scan đã xác nhận hệ thống app hiện đang chạy, nhưng resilience baseline còn yếu: single replica, thiếu probes, stateful components chưa có PVC/evidence backup, alerting chưa ổn định, và checkout có consistency risk khi Kafka publish fail sau payment/shipping. Các issue này phù hợp để đưa vào backlog tuần sau theo priority P1/P2.
