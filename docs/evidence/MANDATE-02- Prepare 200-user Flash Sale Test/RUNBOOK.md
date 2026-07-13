# Runbook — Official 200-user Flash Sale Test (MANDATE-02)

## 1. Mục tiêu và nguyên tắc evidence

Chạy Flash Sale chính thức trên EKS với **200 concurrent users**, giữ **15 phút steady-state**, sau đó kết luận PASS/FAIL cho từng SLO và operational gate.

- Application namespace: `techx-tf4`
- Observability namespace: `techx-observability`
- Approved load configuration: [`deploy/values-load-test-task4.yaml`](../../../deploy/values-load-test-task4.yaml)
- Baseline cần đối chiếu: [`TASK-5-Pre-Load-Test-Baseline.md`](TASK-5-Pre-Load-Test-Baseline.md)
- Alert response: [`docs/audit/runbooks/flash-sale-alerts.md`](../../../docs/audit/runbooks/flash-sale-alerts.md)

> **Không dùng** `scripts/monitor-load-test.sh` và **không chạy** `scripts/run-load-test-task4.sh full`, vì full script gọi monitor này.

Evidence operational phải là số liệu quan sát trực tiếp trong **Grafana dashboard / Grafana Explore, Jaeger UI, OpenSearch UI, Alertmanager UI và Locust report/UI**. Không thu checkpoint bằng `*.txt`, không archive CLI output, không lưu Prometheus/Alertmanager raw JSON, và không dùng ảnh terminal làm evidence chính.

`kubectl` chỉ dùng để pre-flight, chạy Locust, scale load-generator và xử lý safety stop. Các lệnh này không tạo evidence artifact. Locust CSV/HTML là ngoại lệ bắt buộc vì là raw output của load-generator.

Evidence local Minikube tại `artifacts/lean-v2-20260713T163957Z/` chỉ là local runtime, không được dùng để kết luận EKS PASS.

## 2. Test contract — giữ cấu hình bất biến

Sau khi pre-flight PASS, không thay Helm values, environment variables, replica, requests/limits, feature flag, node group hoặc alert rules trong suốt test. Nếu phải dừng, dừng load trước, ghi lý do và dùng UI cùng time window để lưu hiện trạng; không chạy lại hoặc ghi đè RUN_ID đó.

| Thuộc tính | Giá trị được review |
|---|---|
| Load shape | `LOCUST_LOAD_SHAPE=task4` |
| Autostart | `LOCUST_AUTOSTART=false` |
| Target | `200` users |
| Traffic | API-only, browser traffic disabled |
| Target host | `http://frontend-proxy:8080` |
| Ramp-up | 60 giây |
| Steady-state | 900 giây / 15 phút |
| Ramp-down | 20 giây |
| Tổng runtime | 16 phút 20 giây |

`Task4FlashSaleShape` trong `src/load-generator/locustfile.py` là source of truth: target 200, 60 giây ramp-up, 900 giây steady-state, 20 giây ramp-down. Shape dùng `3.33` users/s; CLI `--spawn-rate 5` vẫn được ghi trong command nhưng không thay đổi profile của shape.

| Flow | Tasks | Weight | Tỷ lệ |
|---|---|---:|---:|
| Browse/search | index, product list/detail, recommendations, reviews | 44 | 43.6% |
| Cart | view cart, add to cart | 25 | 24.8% |
| Checkout | single-item, multi-item checkout | 15 | 14.9% |
| Navigation/AI | ads, product AI assistant | 16 | 15.8% |
| Feature-flag gated | `flood_home` | 1 | 1.0% tối đa |

Locust dùng UUID synthetic users và OpenTelemetry baggage `synthetic_request=true`. Dùng giá trị này để lọc Jaeger/OpenSearch. Giữ `flagd` chạy; không tắt feature flag mechanism để làm test dễ pass.

## 3. Evidence package — UI-first

Tạo một thư mục mới trước run; `<RUN_ID>` dùng UTC. Chỉ lưu PNG/JPG từ UI và raw Locust CSV/HTML.

```text
docs/evidence/MANDATE-02- Prepare 200-user Flash Sale Test/
  official-<YYYYMMDDTHHMMSSZ>/
    SUMMARY.md
    locust/
      stats.csv
      stats-history.csv
      failures.csv
      exceptions.csv
      report.html
    dashboard/
      01-loadgen-and-rps.png
      02-slo-and-error-rate.png
      03-pod-and-node-resources.png
      04-restarts-oom-replicas-nodes.png
      05-postgresql-valkey-explore.png
      06-kafka-status.png
    alerts/
      01-alert-state-pre.png
      02-alert-state-during.png
      03-alert-state-post.png
    traces/
      01-checkout-steady-state.png
      02-cart-steady-state.png
    logs/
      01-synthetic-checkout-cart.png
    incident/
      timeline.md
      <additional-ui-screenshots>.png
```

Mọi screenshot UI phải:

1. Hiển thị timezone/timestamp hoặc absolute time range bằng UTC.
2. Dùng cùng range T0–T1; nếu stop sớm, dùng T0–stop time.
3. Hiển thị panel title, legend và giá trị/tooltip cần kết luận.
4. Không crop mất time picker, threshold, data source hoặc alert state.

`SUMMARY.md` chỉ là bảng verdict và link tới PNG/CSV/HTML. Không paste output CLI, log text, JSON hay số liệu chưa xuất hiện trên UI vào summary.

## 4. Pre-flight (không tạo CLI evidence)

Trước test, operator dùng `kubectl` để xác nhận cluster reachable, pod application không ở `Error`, `CrashLoopBackOff`, `ImagePullBackOff`, `Pending` hoặc `CreateContainerError`; `flagd` đang chạy; Metrics API và `kubectl top` hoạt động; Grafana/Prometheus/Jaeger ready.

Trước full run, Helm release phải đã áp dụng đúng [`values-load-test-task4.yaml`](../../../deploy/values-load-test-task4.yaml) và chart values đã review. Xác nhận deployment load-generator có `replicas=1`, `LOCUST_AUTOSTART=false`, `LOCUST_HEADLESS=true`, `LOCUST_USERS=200`, `LOCUST_SPAWN_RATE=5`, `LOCUST_RUN_TIME=16m20s`, `LOCUST_LOAD_SHAPE=task4` và `LOCUST_BROWSER_TRAFFIC_ENABLED=false`. Xác nhận `cart`, `frontend-proxy`, `payment`, `product-catalog` và `shipping` có một replica; HPA `frontend`/`checkout` có `minReplicas=1`, `maxReplicas=3`. Nếu một giá trị khác, **BLOCKED**: dừng tại đây, sửa qua Helm/Git workflow đã review, chụp lại baseline rồi mới tạo RUN_ID mới. Không sửa live bằng `kubectl set env`.

Chụp UI baseline theo `TASK-5-Pre-Load-Test-Baseline.md`, không tạo thêm file text. Trong Grafana Flash Sale Verification Dashboard, đặt range 30 phút ngay trước T0 và chụp các panel tương ứng vào `dashboard/` của RUN_ID.

Các limitation phải giữ nguyên nếu còn xảy ra trên UI:

- **Active Worker Nodes Count** từng `No data`; dùng Grafana panel screenshot ghi `No data`, không suy ra node count.
- **Critical Pods CPU Usage** từng hiển thị unit `min`; không diễn giải unit này là duration. Dùng giá trị series/tooltip và ghi limitation trong `SUMMARY.md`.
- Baseline hiện không có HPA runtime; không khẳng định scaling PASS nếu UI không cho thấy HPA/replica transition.
- Repository không có node autoscaler; node count giữ nguyên phải được ghi `not triggered` hoặc `not available`, không tự động là PASS.

## 5. Port-forward cho các UI cần quan sát

Chạy từng lệnh trong **terminal riêng** và giữ terminal mở đến hết thời điểm chụp evidence. Nếu truy cập cluster qua SSM bastion, chạy `kubectl port-forward` trên bastion rồi dùng SSH/SSM tunnel theo mapping của team; không mở public route cho observability.

| UI | Local URL | Port-forward |
|---|---|---|
| Grafana — dashboard, Explore, OpenSearch datasource, alert state | `http://localhost:13000/grafana/` | `kubectl -n techx-observability port-forward svc/grafana 13000:80` |
| Jaeger — trace UI | `http://localhost:16686/jaeger/ui` | `kubectl -n techx-observability port-forward svc/jaeger 16686:16686` |
| Prometheus — chỉ dùng để kiểm tra UI/rule khi Grafana Explore không đủ | `http://localhost:19090/` | `kubectl -n techx-observability port-forward svc/prometheus 19090:9090` |
| Alertmanager — chỉ dùng để kiểm tra silence/firing UI trực tiếp | `http://localhost:19093/` | `kubectl -n techx-observability port-forward pod/techx-observability-alertmanager-0 19093:9093` |
| Locust UI — **chỉ dry-run**, không dùng để chạy official headless test | `http://localhost:18089/` | `kubectl -n techx-tf4 port-forward svc/load-generator 18089:8089` |

Mở Grafana trước để kiểm tra hai dashboard UID `flash-sale-verification` và `flash-sale-alert-state`, Jaeger để truy vấn trace, và Grafana Explore với datasource OpenSearch (`webstore-logs`) để truy vấn `otel-logs-*`. Không cần port-forward OpenSearch riêng: evidence logs được lấy qua Grafana OpenSearch datasource UI. Official test dùng Locust headless, vì vậy không cần mở Locust UI trong full run.

Khi port-forward mất kết nối, khởi động lại cùng lệnh trong terminal mới và ghi khoảng thời gian mất UI vào `SUMMARY.md`. Nếu mất Grafana/Jaeger/Prometheus trong lúc test, áp dụng safety stop tại mục 10.

## 6. Chạy load test và giữ raw output của Locust

Thực hiện dry-run trước theo quy trình đã review. Nếu dry-run fail, không chạy full test.

Dùng `kubectl` chỉ để vận hành load-generator; không redirect output vào `.txt` hoặc `.log`. Raw output bắt buộc được lấy từ Locust-generated CSV/HTML sau run.

```bash
export NS=techx-tf4
export RUN_ID="official-$(date -u +%Y%m%dT%H%M%SZ)"
export EVIDENCE="docs/evidence/MANDATE-02- Prepare 200-user Flash Sale Test/$RUN_ID"
mkdir -p "$EVIDENCE/locust" "$EVIDENCE/dashboard" "$EVIDENCE/alerts" "$EVIDENCE/traces" "$EVIDENCE/logs" "$EVIDENCE/incident"

kubectl -n "$NS" scale deployment/load-generator --replicas=1
kubectl -n "$NS" rollout status deployment/load-generator --timeout=120s

# Ghi T0/T1 trong Grafana time picker và SUMMARY.md, không tạo T0/T1 text artifact.
kubectl -n "$NS" exec deploy/load-generator -- \
  env LOCUST_LOAD_SHAPE=task4 LOCUST_AUTOSTART=false locust --headless \
    --users 200 --spawn-rate 5 --run-time 16m20s \
    --host http://frontend-proxy:8080 \
    --csv /tmp/task4-results --html /tmp/task4-report.html \
    --skip-log-setup -f locustfile.py --only-summary
```

Ngay khi Locust hoàn thành, copy raw artifact vào `locust/`. Không coi artifact thiếu là PASS.

```bash
LOADGEN_POD=$(kubectl -n "$NS" get pod -l app.kubernetes.io/name=load-generator -o jsonpath='{.items[0].metadata.name}')
kubectl -n "$NS" cp "$LOADGEN_POD:/tmp/task4-results_stats.csv" "$EVIDENCE/locust/stats.csv"
kubectl -n "$NS" cp "$LOADGEN_POD:/tmp/task4-results_stats_history.csv" "$EVIDENCE/locust/stats-history.csv"
kubectl -n "$NS" cp "$LOADGEN_POD:/tmp/task4-results_failures.csv" "$EVIDENCE/locust/failures.csv" || true
kubectl -n "$NS" cp "$LOADGEN_POD:/tmp/task4-results_exceptions.csv" "$EVIDENCE/locust/exceptions.csv" || true
kubectl -n "$NS" cp "$LOADGEN_POD:/tmp/task4-report.html" "$EVIDENCE/locust/report.html"
kubectl -n "$NS" scale deployment/load-generator --replicas=0
```

Mở `locust/report.html` để xác nhận peak **200 active users**, tổng duration và request/failure distribution. `stats-history.csv` là raw time-series chứng minh ramp/steady/ramp-down; `report.html` và CSV là raw load-generator output bắt buộc.

## 7. Dashboard evidence — số liệu thật theo cùng time window

Mở Grafana dashboard UID `flash-sale-verification`. Sau khi có T1, đặt **absolute UTC range T0–T1**; refresh panel cho đến khi OTel metrics flush hoàn tất. Chụp các nhóm panel sau, không dùng ảnh terminal thay thế.

| File | Panel/UI cần hiển thị | Kết luận lấy từ UI |
|---|---|---|
| `01-loadgen-and-rps.png` | `Load-generator traffic activity (spans/s)`, `Frontend Inbound RPS`, `Services RPS & Error Rate` | Có traffic trong window; request rate và frontend/service error rate |
| `02-slo-and-error-rate.png` | `Storefront (Browse) Latency Percentiles`, Browse/Cart/Checkout Success Rate, request volumes, `Services RPS & Error Rate` | Storefront p95, 3 success rate, volume guard, error rate |
| `03-pod-and-node-resources.png` | `Critical Pods CPU Usage`, `Critical Pods Memory Usage`, `Node CPU Usage %`, `Node Memory Usage %` | Peak resource values và headroom pod/node |
| `04-restarts-oom-replicas-nodes.png` | `Pod Restarts (10m Delta)`, `Pod OOMKilled Events (10m)`, `Pod Replica Count (HPA)`, `Active Worker Nodes Count` | Restart/OOM delta và replica/node behavior |
| `05-postgresql-valkey-explore.png` | Grafana Explore result của `postgresql_backends` và `redis_connected_clients` nếu query trả data | Connection signal hoặc `No data` thật từ UI |
| `06-kafka-status.png` | Grafana dashboard/Explore thể hiện Kafka không có configured metric, hoặc Kubernetes/EKS console UI trạng thái Kafka pod | Kafka metric gap hoặc trạng thái runtime quan sát được |

Ở mỗi panel time-series, hover peak và steady-state point để screenshot tooltip có timestamp/giá trị. Đối với gauge/table, screenshot phải cho thấy giá trị cuối cùng trong exact range. Nếu panel `No data`, đó là finding cần lưu, không được thay bằng giá trị tự tính.

### Required checkpoint screenshots

Không chụp CLI checkpoint. Dùng cùng dashboard, ghi timestamp trên `SUMMARY.md`, và chụp tối thiểu tại:

| Checkpoint | UI evidence cần kiểm tra |
|---|---|
| T0 trước swarm | Load-generator activity idle, alert state baseline, resource/restart/OOM baseline |
| Khoảng phút 1 | Load-generator activity, frontend RPS, request/error rate |
| Khoảng phút 7–8 | SLO, pod/node resource peak, replica/node behavior, pending/firing alerts |
| Khoảng phút 14–15 | SLO vẫn giữ, error rate, restart/OOM, alert state |
| T2 sau ramp-down | Load-generator activity trở về idle, final alert state, resource/restart/OOM/replica state |

Nếu HPA hiện diện, chụp lại dashboard sau tối thiểu 300 giây post-peak để thấy scale-down. Nếu không có HPA, ghi `not available` trong `SUMMARY.md`. Không gọi trạng thái replica tĩnh là “scale-down PASS”.

## 8. SLO verdict từ Grafana UI

Dùng dashboard panels và Grafana Explore với PromQL source từ [`flash-sale-alerts.yaml`](../../../techx-corp-chart/prometheus/flash-sale-alerts.yaml). Số kết luận ghi vào `SUMMARY.md` phải là số nhìn thấy trong UI cùng T0–T1 range.

| SLO | PASS | UI kiểm tra |
|---|---:|---|
| Storefront p95 | `< 1000 ms` | `Storefront (Browse) Latency Percentiles` / Explore |
| Browse success | `>= 99.5%` | Browse Success Rate + Browse Request Volume |
| Cart success | `>= 99.5%` | Cart Success Rate + Cart Request Volume |
| Checkout success | `>= 99.0%` | Checkout Success Rate + Checkout Request Volume |
| Frontend error rate | `<= 5%` | `Services RPS & Error Rate` / Explore |

Browse, cart và checkout chỉ evaluable khi request volume đạt **ít nhất 20 requests trong cửa sổ 5 phút**, đúng điều kiện alert rule. Nếu volume không đủ, ghi `NOT EVALUABLE`, không điền PASS.

PromQL để paste vào **Grafana Explore** (chụp Explore result với range T0–T1, không export JSON):

```promql
# Storefront p95
histogram_quantile(0.95, sum by (le) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"}[5m])))

# Checkout success ratio; nhân 100 ở Grafana để hiển thị phần trăm
sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout",status_code!="STATUS_CODE_ERROR"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",span_name="POST /api/checkout"}[5m]))

# Frontend error ratio
sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER",status_code="STATUS_CODE_ERROR"}[5m])) / sum(rate(traces_span_metrics_calls_total{service_name="frontend",span_kind="SPAN_KIND_SERVER"}[5m]))
```

Locust CSV/HTML là client-side result; Grafana span metrics là server-side result. Ghi cả hai verdict, điều tra lệch đáng kể trong `SUMMARY.md`, không dùng một nguồn thay thế nguồn còn lại.

## 9. Alert, trace, log và middleware UI evidence

### Alert state

Mở dashboard UID `flash-sale-alert-state`, dùng cùng absolute UTC range, chụp:

1. `01-alert-state-pre.png`: trước T0 — active count và pending/firing table.
2. `02-alert-state-during.png`: phút 7–8 — active count, alert instances và alert-state timeline.
3. `03-alert-state-post.png`: T2 — final state sau test.

Theo dõi đủ 15 rule: `StorefrontP95High`, `CheckoutSuccessRateLow`, `BrowseSuccessRateLow`, `CartSuccessRateLow`, `FrontendErrorRateHigh`, `PodOOMKilled`, `PodRestartBurst`, `NodeCPUPressure`, `NodeMemoryPressure`, `NodeNotReady`, `PodPendingOrNotRunning`, `GrafanaUnavailable`, `PrometheusUnavailable`, `JaegerUnavailable`, `LoadGeneratorTrafficOutsideTestWindow`.

`LoadGeneratorTrafficOutsideTestWindow` có thể pending/firing trong approved test window vì rule có duration 10 phút. Nếu tạo Alertmanager silence, chỉ silence rule này, ghi approval window và expiry T1 trong screenshot UI; không dùng silence mở.

### Jaeger và OpenSearch

- Trong **Jaeger UI**, filter service/time range đúng T0–T1 và `synthetic_request=true` nếu searchable. Lưu ít nhất một checkout trace và một cart trace ở steady-state. Screenshot phải thấy trace timestamp, total duration, critical path/dependency span và lỗi nếu có.
- Trong **OpenSearch UI**, query index `otel-logs-*` theo exact UTC range và synthetic trace context. Lưu screenshot `01-synthetic-checkout-cart.png` thấy query/filter, số hit và log error (hoặc `0` error) của browse/cart/checkout.
- Nếu restart/OOM/alert xảy ra, bổ sung screenshot Jaeger/OpenSearch/Kubernetes or EKS console UI tại đúng time range trước khi thao tác remediation. Không dùng terminal log dump làm evidence chính.

### PostgreSQL, Kafka và Valkey

| Component | UI evidence |
|---|---|
| PostgreSQL | Grafana Explore `postgresql_backends`; nếu `No data`, chụp đúng UI state và ghi `postgres exporter unavailable` |
| Valkey | Grafana Explore `redis_connected_clients`; nếu `No data`, chụp đúng UI state và ghi `redis exporter unavailable` |
| Kafka | Không có Kafka metric configured trong dashboard. Chụp Grafana Explore/verification dashboard statement về gap và Kafka workload state trong Kubernetes/EKS console UI; không bịa consumer lag hoặc throughput |

Missing metric không chứng minh healthy. Ghi metric gap là `BLOCKED`/limitation trong `SUMMARY.md`, còn pod/trace/log UI chỉ là supporting evidence.

## 10. Safety stop và incident evidence

Dừng load generation trước, không thay cấu hình để che signal, nếu UI cho thấy một trong các điều kiện:

- Storefront p95 >1000 ms liên tục 5m.
- Checkout success <99% liên tục 5m và đủ 20 requests.
- Browse/cart success <99.5% liên tục 5m và đủ traffic.
- Frontend error >5% liên tục 2m và đủ traffic.
- OOM mới, `PodRestartBurst`, Pending/Failed/Unknown, node NotReady.
- Node CPU hoặc memory >85% liên tục 10m.
- Grafana, Prometheus hoặc Jaeger unavailable làm mất SLO/evidence visibility.

Safety stop command:

```bash
kubectl -n techx-tf4 scale deployment/load-generator --replicas=0
```

Nếu stop sớm, SLO FAIL, OOM/restart mới hoặc alert critical firing, tạo `incident/timeline.md` với link tới screenshot UI đã lưu:

| UTC | Symptom / alert trên UI | Giá trị/pod | Action | Effect | Screenshot / trace / log UI |
|---|---|---|---|---|---|
| `<time>` | `<first signal>` | `<value>` | `<stop/capture>` | `<result>` | `<relative path>` |

## 11. SUMMARY.md và acceptance sign-off

`SUMMARY.md` phải ghi T0/T1 UTC, Grafana absolute range, dashboard URLs/UID, Locust artifact paths và verdict dưới đây. Chỉ nhập giá trị đã quan sát trong UI hoặc Locust CSV/HTML.

| Acceptance criterion | PASS / FAIL / BLOCKED / NOT EVALUABLE | UI/raw artifact evidence | Giá trị quan sát | Ghi chú |
|---|---|---|---|---|
| Đạt 200 active users |  | `locust/report.html` |  |  |
| Steady-state 15 phút |  | `locust/stats-history.csv` |  | Stop sớm phải link incident |
| Raw load-generator output |  | `locust/*.csv`, `locust/report.html` |  | Bắt buộc |
| Request rate và load activity |  | `dashboard/01-loadgen-and-rps.png` |  |  |
| Dashboard SLO evidence cùng window |  | `dashboard/02-slo-and-error-rate.png` |  | Exact UTC range |
| Alert evidence |  | `alerts/*.png` |  | pending/firing state |
| Pod/node resource evidence |  | `dashboard/03-pod-and-node-resources.png` |  | CPU unit limitation nếu có |
| Replica/node scaling behavior |  | `dashboard/04-restarts-oom-replicas-nodes.png` |  | observed/not triggered/not available |
| Restart/OOMKilled |  | `dashboard/04-restarts-oom-replicas-nodes.png` |  | Delta vs baseline |
| Storefront p95 <1s |  | `dashboard/02-slo-and-error-rate.png` |  |  |
| Browse >=99.5% |  | `dashboard/02-slo-and-error-rate.png` |  | volume guard |
| Cart >=99.5% |  | `dashboard/02-slo-and-error-rate.png` |  | volume guard |
| Checkout >=99% |  | `dashboard/02-slo-and-error-rate.png` |  | volume guard |
| Frontend error <=5% |  | `dashboard/02-slo-and-error-rate.png` |  | volume guard |
| PostgreSQL/Valkey/Kafka state |  | `dashboard/05-*`, `dashboard/06-*` |  | Record actual metric gap |
| Checkout/cart trace và synthetic logs |  | `traces/`, `logs/` |  |  |
| Incident timeline khi required |  | `incident/timeline.md` |  | N/A chỉ full PASS, không incident |

Chỉ đóng MANDATE-02 khi mọi criterion bắt buộc có evidence và verdict. `BLOCKED` hoặc `NOT EVALUABLE` không phải `PASS`; ghi owner và follow-up cần thiết thay vì che gap.
