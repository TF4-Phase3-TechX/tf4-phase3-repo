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
- flagd central sync/control-plane risk.
- Timeout/deadline/retry gaps trên checkout path.
- Backup/restore proof và PDB candidates.

## Runtime Context

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
- Không có PodDisruptionBudget trong namespace `techx-tf4`.
- Frontend public ALB trả `HTTP/1.1 200 OK`.
- `flagd` đang chạy, nhưng evidence của Thuỷ cho thấy runtime đọc local flag file thay vì central sync.

## Findings

| ID | Finding | Evidence | Impact | Priority gợi ý | Backlog candidate |
|---|---|---|---|---|---|
| REL-01 | Critical services đều chỉ có `1 replica` | `kubectl -n techx-tf4 get deploy` cho thấy toàn bộ deploy `1/1`; chart default `techx-corp-chart/values.yaml:27` có `replicas: 1` | Pod restart, node drain hoặc rollout lỗi có thể làm downtime service quan trọng | P1 | Tăng replica cho service critical sau khi đánh giá cost/resource |
| REL-02 | App pods không có readiness/liveness probe | Runtime jsonpath cho deploy trả rỗng readiness/liveness; chart chỉ có probe dạng comment ở `techx-corp-chart/values.yaml:152-153`; template có support probe nhưng values chưa cấu hình | Pod có thể nhận traffic khi chưa ready; app treo nhưng Kubernetes không restart đúng lúc | P1 | Bổ sung readiness/liveness probes cho checkout path và service critical |
| REL-03 | PostgreSQL, Valkey, Kafka single replica và không có PVC trong `techx-tf4` | `kubectl -n techx-tf4 get pvc` không có resources; `postgresql`, `valkey-cart`, `kafka` đều replicas `1`; PostgreSQL chỉ mount `configMap` `postgresql-init` | Stateful/data components là SPOF; restart có rủi ro mất hoặc gián đoạn dữ liệu cart/order/event | P1 | Đánh giá persistence/backup/restore và HA candidates |
| REL-05 | Prometheus/OpenSearch persistence disabled | `techx-corp-chart/values.yaml:1174-1175` Prometheus PV disabled; `techx-corp-chart/values.yaml:1222-1223` OpenSearch persistence disabled | Metric/log/trace có thể mất sau restart; khó điều tra incident và chứng minh reliability | P1/P2 | Bổ sung persistence hoặc xác định retention/evidence strategy |
| REL-06 | Alertmanager disabled | `techx-corp-chart/values.yaml:1118-1121` có `alertmanager.enabled: false` | Có dashboard nhưng thiếu cảnh báo tự động cho checkout/runtime/data; phát hiện sự cố phụ thuộc manual check | P1 | Bật alerting cho checkout error rate/latency và runtime health |
| REL-07 | Checkout trả lỗi nếu Kafka publish fail sau payment/shipping | `techx-corp-platform/src/checkout/main.go:331-347` payment/shipping xảy ra trước; `387-392` Kafka publish fail thì return `codes.Unavailable` | Khách có thể thấy checkout fail dù payment/shipping đã xảy ra; rủi ro consistency và support | P1 | Thiết kế lại post-payment event handling hoặc compensation strategy |
| REL-08 | `flagd` central sync đang bị vô hiệu hóa và runtime đọc flag local | `deploy/values-flagd-sync.yaml:10-23` sync command/token đang comment; log flagd đọc `./etc/flagd/demo.flagd.json`; Secret `flagd-sync` là `placeholder` | Fault-injection/control flags từ BTC có thể không đồng bộ; vi phạm rule flagd và làm sai evidence incident | P0 | Sửa flagd sync command/token, deploy với `values-flagd-sync.yaml`, verify logs sync central provider |
| REL-09 | Checkout path thiếu timeout/deadline/retry cho nhiều dependency sync | Quân F01-F04/G1-G7/G10: gRPC/HTTP calls không có per-call timeout; `shipping/quote.rs` dùng `awc::Client::new()` | Dependency chậm có thể kéo dài checkout request, tăng p95 latency hoặc làm cạn worker/goroutine | P1 | Thiết kế timeout budget và fault test cho cart/product-catalog/currency/payment/shipping/quote |
| REL-10 | Payment khởi tạo OpenFeature provider trong mỗi request thanh toán | Nguyên CDO08-REL-03; `payment/charge.js` gọi `OpenFeature.setProviderAndWait(flagProvider)` trong `charge` | Tạo lại provider/kết nối flagd trên hot path có thể làm tăng latency và bottleneck payment | P1 | Di chuyển provider init sang startup, giữ per-request chỉ đọc flag value |
| REL-11 | Chưa có backup/restore proof cho PostgreSQL, Valkey, Kafka | Phương DR-003/DR-010; namespace không có PVC; chưa thấy restore runbook/evidence | Khi data/stateful component lỗi, team chưa chứng minh được RPO/RTO hoặc cách khôi phục cart/order/event data | P1 | Tạo backup/restore baseline và test restore tối thiểu hoặc ghi rõ blocker |
| REL-12 | Revenue path chưa có PodDisruptionBudget | `kubectl -n techx-tf4 get pdb` trả `No resources found`; Nam `NAM-RUNTIME-007` | Voluntary disruption như node drain/maintenance chưa có policy bảo vệ service critical | P2 | Tạo PDB candidates sau khi có >=2 replicas và readiness đúng |

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

### REL-08 - flagd central sync disabled/local-only

Evidence:

- `deploy/values-flagd-sync.yaml:10-23` giữ central sync command/token ở trạng thái comment.
- Command cũ dùng shell wrapper `/bin/sh -c`, trong khi image flagd hiện tại không có shell, nên bật lại nguyên trạng có thể làm container crash.
- Runtime log của Thuỷ cho thấy `flagd` đang watch `./etc/flagd/demo.flagd.json`.
- Secret `flagd-sync` trong runtime chứa value placeholder.

Service impact:

- Runtime có `FLAGD_HOST=flagd`, `FLAGD_PORT=8013` ở các service: `ad`, `cart`, `checkout`, `email`, `fraud-detection`, `frontend`, `frontend-proxy`, `llm`, `load-generator`, `payment`, `product-catalog`, `product-reviews`, `recommendation`.
- Các flag quan trọng gồm `cartFailure`, `paymentFailure`, `paymentUnreachable`, `productCatalogFailure`, `kafkaQueueProblems`, `failedReadinessProbe`.

Việc cần làm tuần sau:

- Sửa command sync theo dạng exec trực tiếp, không dùng shell wrapper.
- Xác nhận token thật và owner được phép deploy.
- Verify bằng `kubectl logs` rằng flagd sync từ central provider thành công, không chỉ đọc local file.

### REL-09 - Checkout dependency timeout/deadline gaps

Evidence:

- Quân F01-F04/G1-G7/G10 ghi nhận checkout gọi `cart`, `product-catalog`, `currency`, `payment`, `shipping` mà chưa có per-call deadline/timeout rõ.
- `shipping` gọi `quote` qua `awc::Client::new()` default.
- Baseline trace cho thấy happy path chạy được, nhưng chưa có fault-injection evidence khi dependency chậm/lỗi.

Việc cần làm tuần sau:

- Thiết kế timeout budget theo dependency.
- Thêm fault test: dependency delay 10s thì checkout phải fail bounded theo timeout, không treo request.
- Không nâng P0 nếu chưa có runtime evidence outage hoặc fault test chứng minh impact.

### REL-10 - Payment OpenFeature provider per request

Evidence:

- Nguyên finding CDO08-REL-03 chỉ ra `payment/charge.js` gọi `OpenFeature.setProviderAndWait(flagProvider)` bên trong request handler `charge`.
- Đây là hot path của checkout vì checkout gọi payment trước khi ship order và publish event.

Việc cần làm tuần sau:

- Di chuyển provider initialization sang startup.
- Giữ request path chỉ đọc giá trị flag `paymentFailure`.
- Load/smoke test payment để verify latency không tăng và flag vẫn hoạt động.

### REL-11 - Backup/restore proof missing

Evidence:

- Phương DR-003/DR-010 ghi nhận PostgreSQL, Valkey, Kafka chưa có evidence backup/restore đầy đủ.
- Runtime `kubectl -n techx-tf4 get pvc` không thấy PVC.
- Data path liên quan cart/order/event, nên cần RPO/RTO hoặc ít nhất documented gap.

Việc cần làm tuần sau:

- Tạo runbook backup/restore cho PostgreSQL, Valkey, Kafka.
- Nếu chưa thể test restore, ghi rõ blocker, quyền cần có, storage cần có, và owner phối hợp.
- Nếu đề xuất HA/managed service, phối hợp CDO04 vì có cost impact.

### REL-12 - PodDisruptionBudget missing

Evidence:

```bash
kubectl -n techx-tf4 get pdb
```

Kết quả:

- `No resources found in techx-tf4 namespace`.

Việc cần làm tuần sau:

- Chỉ tạo PDB sau khi service có >=2 replicas và readiness đúng.
- Ưu tiên candidates cho `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog`.
- Không tạo PDB cho single-replica workload theo cách làm kẹt node drain.

## Suggested Backlog Items

| Backlog ID | Title | Suggested Owner | Priority |
|---|---|---|---|
| REL-BL-01 | Increase replica coverage for checkout path critical services | Nam + CDO04 + Nguyên | P1 |
| REL-BL-02 | Add readiness/liveness probes for critical app services | Nam + service owners | P1 |
| REL-BL-03 | Define persistence/backup/restore baseline for PostgreSQL, Valkey, Kafka | Phương + CDO04 | P1 |
| REL-BL-05 | Enable minimum alerting for checkout/runtime/data health | Quyết + Nam + Phương | P1 |
| REL-BL-06 | Review checkout Kafka post-payment failure behavior | Quân + Nguyên | P1 |
| REL-BL-07 | Restore flagd central sync and verify protected flag control path | Thuỷ + Nam + Nguyên | P0 |
| REL-BL-08 | Add checkout timeout/deadline budget and fault tests | Quân + Nguyên + Quyết | P1 |
| REL-BL-09 | Move Payment OpenFeature provider initialization to startup | Nguyên + Quân | P1 |
| REL-BL-10 | Add PDB candidates after replicas/readiness are fixed | Nam + CDO04 | P2 |

## Notes For Jira Epic

Reliability Week 1 scan đã xác nhận hệ thống app hiện đang chạy, nhưng resilience baseline còn yếu: flagd central sync đang local-only, single replica, thiếu probes, stateful components chưa có PVC/evidence backup, alerting chưa ổn định, checkout thiếu timeout/deadline, payment init flag provider trên request path, và checkout có consistency risk khi Kafka publish fail sau payment/shipping. Các issue này phù hợp để đưa vào backlog tuần sau, trong đó flagd sync là P0 vì liên quan trực tiếp tới protected control path/rule.
