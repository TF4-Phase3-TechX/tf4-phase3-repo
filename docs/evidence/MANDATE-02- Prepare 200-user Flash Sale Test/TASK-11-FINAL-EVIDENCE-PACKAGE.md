# Task 11 - Gói Evidence Cuối Cho Mentor

## Phạm vi

* Bàn giao evidence cuối cho Directive #1 và Directive #2
* Cluster: `techx-tf4-cluster` / `us-east-1` / account `511825856493`
* Namespace ứng dụng: `techx-tf4`
* Namespace observability: `techx-observability`
* Ngày tổng hợp: `2026-07-14`
* Trạng thái evidence: Bản nháp có thể nộp mentor, kèm known risks rõ ràng

> Tài liệu này ghi lại bài flash-sale đã chạy xong và trạng thái xác minh hiện tại. Trong cửa sổ dashboard, SLO customer-facing và scale-down đều được quan sát là đạt. Các sự cố OOM sau cửa sổ test được ghi thành known risks / follow-up và không bị ẩn đi.

---

# 1. Directive #1 – Storefront Public, Cổng Vận Hành Private

## 1.1 URL Storefront Public

Storefront public URL:

```text
http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com/
```

Kết quả verify public route mới nhất:

| Route           | Mong đợi | Quan sát | Verdict |
| --------------- | -------- | -------- | ------- |
| `/`             | HTTP 200 | HTTP 200 | PASS    |
| `/grafana/`     | HTTP 404 | HTTP 404 | PASS    |
| `/jaeger/ui/`   | HTTP 404 | HTTP 404 | PASS    |
| `/loadgen/`     | HTTP 404 | HTTP 404 | PASS    |
| `/feature`      | HTTP 404 | HTTP 404 | PASS    |
| `/flagservice/` | HTTP 404 | HTTP 404 | PASS    |
| `/otlp-http/`   | HTTP 404 | HTTP 404 | PASS    |

Evidence liên quan:

* `../mandate-01-network-exposure/VERIFICATION-REPORT.md`
* `TASK-5-Pre-Load-Test-Baseline.md`

## 1.2 Hướng Dẫn Truy Cập Private

Các UI vận hành không public. Mentor cần sử dụng AWS credentials có quyền EKS/SSM, sau đó mở tunnel riêng hoặc Kubernetes port-forward.

### Grafana

```powershell
kubectl -n techx-observability port-forward svc/grafana 13000:80

# Mở:
http://localhost:13000/grafana/
```

### Jaeger

```powershell
kubectl -n techx-observability port-forward svc/jaeger 16686:16686

# Mở:
http://localhost:16686/jaeger/ui
```

### Prometheus

Chỉ dùng khi Grafana Explore không đủ:

```powershell
kubectl -n techx-observability port-forward svc/prometheus 19090:9090

# Mở:
http://localhost:19090/
```

### Alertmanager

```powershell
kubectl -n techx-observability port-forward pod/techx-observability-alertmanager-0 19093:9093

# Mở:
http://localhost:19093/
```

## 1.3 Dashboard Và Trace Còn Hoạt Động

| Thành phần                   | Evidence                                                                                           | Verdict        |
| ---------------------------- | -------------------------------------------------------------------------------------------------- | -------------- |
| Grafana dashboard            | Screenshot dashboard có traffic, SLO, resource, restart/OOM và HPA                                 | PASS           |
| Jaeger/OpenSearch trace data | OpenSearch đếm được 836,476 span Jaeger trong window 2026-07-13T22:43:00Z đến 2026-07-13T22:58:00Z | PASS with risk |
| OpenSearch hiện tại          | Cluster truy vấn được, PVC 8Gi, đang dùng khoảng 2.8Gi / 7.8Gi                                     | PASS with risk |

### Known Risks

* OpenSearch từng restart với lỗi `Java heap space`.
* Log cũ của Jaeger có lỗi bulk-write vào OpenSearch do:

  * `disk usage exceeded flood-stage watermark`
  * index bị `read-only-allow-delete` block
* Khi verify lại, OpenSearch index block trả về `{}`, nghĩa là block không còn active tại thời điểm kiểm tra.

---

# 2. Directive #2 – Evidence Load Test Flash-Sale

## 2.1 Test Contract

Source of truth:

* `../../../deploy/values-load-test-task4.yaml`
* `../../../techx-corp-platform/src/load-generator/locustfile.py`
* `RUNBOOK.md`

### Runtime Configuration

| Setting                        | Giá trị                    |
| ------------------------------ | -------------------------- |
| LOCUST_USERS                   | 200                        |
| LOCUST_RUN_TIME                | 16m20s                     |
| LOCUST_LOAD_SHAPE              | task4                      |
| LOCUST_BROWSER_TRAFFIC_ENABLED | false                      |
| LOCUST_HOST                    | http://frontend-proxy:8080 |
| Image tag                      | 6b5058f-task4-shape-fix    |

### Shape Contract

| Phase        | Thời lượng     |
| ------------ | -------------- |
| Ramp-up      | 60s            |
| Steady-state | 900s (15 phút) |
| Ramp-down    | 20s            |
| Tổng         | 16m20s         |

## 2.2 Test Window Quan Sát Được

Dashboard evidence cho thấy main test window:

```text
2026-07-14 05:43–05:58 +07
2026-07-13 22:43–22:58Z
```

OpenSearch trace query cùng UTC window:

```text
Index: jaeger-span-2026-07-13

Range:
startTimeMillis 1783982580000
to
1783983480000

Count:
836,476 spans

Sample source pod:
load-generator-6fc7b94876-thsps

Sample image tag:
6b5058f-task4-shape-fix
```

## 2.3 Kết Quả SLO Trên Dashboard

| Metric                  | Quan sát                        | Threshold  | Verdict |
| ----------------------- | ------------------------------- | ---------- | ------- |
| Load-generator activity | 70.0 spans/s                    | Có traffic | PASS    |
| Frontend inbound RPS    | Mean 70.2 req/s, max 86.7 req/s | Có traffic | PASS    |
| Storefront p95 latency  | Mean 329 ms, max 918 ms         | < 1000 ms  | PASS    |
| Browse success rate     | 100%                            | >= 99.5%   | PASS    |
| Cart success rate       | 100%                            | >= 99.5%   | PASS    |
| Checkout success rate   | 100%                            | >= 99.0%   | PASS    |
| Browse volume           | ~6.99k                          | Có volume  | PASS    |
| Cart volume             | ~5.17k                          | Có volume  | PASS    |
| Checkout volume         | ~1.47k                          | Có volume  | PASS    |

### Screenshot Hỗ Trợ

* `screenshots/01-grafana-traffic-loadgen.jpg`
* `screenshots/02-grafana-slo-resources.jpg`
* `screenshots/03-grafana-restarts-oom-replicas.jpg`
* `screenshots/Replica count trên Grafana.jpg`

## 2.4 Resource Before, During Và After

### Baseline

* Timestamp: `2026-07-14 00:59:40 +07`
* Evidence: `TASK-5-Pre-Load-Test-Baseline.md`
* Worker nodes: `2 x t3.large`
* Không quan sát restart/OOM trong pod set hiện tại.

### During Run

* Node CPU có lúc tăng cao trong peak.
* Node memory không chạm mức full exhaustion.
* Grafana restart/OOM delta panel hiển thị 0.

### After Run

| Resource                  | Quan sát                                   |
| ------------------------- | ------------------------------------------ |
| frontend HPA              | 1 current / 1 desired, CPU khoảng 9% / 70% |
| checkout HPA              | 1 current / 1 desired, CPU khoảng 2% / 70% |
| load-generator deployment | 0/0                                        |
| Node ip-10-0-10-231       | ~9% CPU, ~45% memory                       |
| Node ip-10-0-11-40        | ~6% CPU, ~61% memory                       |


### Evidence Runtime

![Evidence Runtime-1](screenshots/Evidence%20Runtime-1.jpg)
![Evidence Runtime-2](screenshots/Evidence%20Runtime-2.jpg)
![Evidence Runtime-3](screenshots/Evidence%20Runtime-3.jpg)
### Scale-Down Verdict
| Requirement                    | Verdict | Evidence                  |
| ------------------------------ | ------- | ------------------------- |
| Frontend scale-down sau peak   | PASS    | HPA current/desired = 1/1 |
| Checkout quay về baseline      | PASS    | HPA current/desired = 1/1 |
| Load-generator đã stop sau run | PASS    | Deployment = 0/0          |

## 2.5 Alert Và Incident Evidence

### Grafana Alert-State Evidence

Evidence hiện có:

* `screenshots/Grafana alert-state window.jpg`
* Dashboard: `Flash-sale alert runbook`
* Time range hiển thị trên UI: `2026-07-14 05:46:58–06:46:58 +07`
* `Active Task-3 alerts` tại thời điểm chụp: `0`
* Panel `Alert state over time` cho thấy đã có trạng thái pending/firing quanh khoảng `06:00 +07`, sau đó trở về `0`.

![Grafana alert-state window](screenshots/Grafana%20alert-state%20window.jpg)

**Verdict:** `PARTIAL`. Ảnh này chứng minh alert monitoring hoạt động và bao phủ một phần thời gian test/post-run, nhưng chưa thay thế đầy đủ bộ ba checkpoint riêng biệt theo runbook:

* `alerts/01-alert-state-pre.jpg` — ngay trước T0
* `alerts/02-alert-state-during.jpg` — khoảng phút 7–8 của steady-state
* `alerts/03-alert-state-post.jpg` — sau ramp-down và thời gian chờ scale-down

Không diễn giải panel `Pending and firing alert instances: No data` là không từng có alert trong toàn bộ window; panel lịch sử cho thấy đã có alert state quanh `06:00 +07`.

### Incident Runtime Sau Bài Test

| Component  | Restart | Last Reason                        | Thời điểm               |
| ---------- | ------- | ---------------------------------- | ----------------------- |
| PostgreSQL | 3       | OOMKilled (exit 137); xem `official-20260713T224300Z/runtime/07-post-run-kubectl-pods-20260713T230842Z.jpg` | 2026-07-14 06:01:12 +07 |
| Jaeger     | 2       | OOMKilled (exit 137)               | 2026-07-14 06:02:31 +07 |
| OpenSearch | 1       | Error (Java heap OOM trong log cũ) | 2026-07-14 01:44:20 +07 |

### Diễn Giải

* Customer-facing SLO đạt trong cửa sổ test đã chụp.
* Reliability/observability gate chưa sạch vì PostgreSQL và Jaeger bị OOMKilled ngay sau main test window.
* Cần ghi nhận đây là post-run incident và follow-up risk.

## 2.6 Cost Estimate

Cost evidence hiện có:

* Pre-live allocation model trong `preparation-report.md`
* Estimated allocated infrastructure cho window 16m20s:

  * `$0.073730`
* Estimated weekly baseline:

  * `$45.501867/week`

Final billing sign-off vẫn cần Cost Explorer hoặc CUR cho đúng UTC window. Acceptance hiện chỉ xác nhận đã có **cost estimate**, không xác nhận actual billed cost.

Trước khi có số liệu đó, cost chỉ được xem là:

```text
ESTIMATED
```

không phải final billing evidence.

## 2.7 Cơ sở chọn tuning

Tuning được chọn theo ladder `lean → balanced → headroom`: bắt đầu từ reservation thấp nhất có `requests`/`limits` rõ ràng, chỉ tăng khi client SLO hoặc reliability gate fail. Local `lean-v2` chỉ là canary để chọn candidate; không được dùng để kết luận EKS pass. Chi tiết pre-live: [`preparation-report.md` §3](preparation-report.md#3-lý-do-chọn-tuning-hiện-tại).

| Tuning đã chọn | Cơ sở / source | Lý do performance ⇄ cost | Giới hạn giữ nguyên |
| --- | --- | --- | --- |
| Direct CPU/memory `requests` và `limits` cho 12 service trong scope | [`values.yaml`](../../../techx-corp-chart/values.yaml) | Scheduler có reservation rõ ràng và HPA có CPU baseline, thay vì tăng node mù quáng | Không chứng minh stateful/observability hết memory pressure |
| Baseline 1 replica cho stateless low-risk path | [`values.yaml`](../../../techx-corp-chart/values.yaml) | Giữ normal-time reservation/cost thấp | Không scale stateful service, `flagd` hoặc observability để lấy điểm ngắn hạn |
| HPA chỉ cho `frontend` và `checkout`: min 1, max 3, CPU target 70%, scale-down stabilization 300s | [`values.yaml`](../../../techx-corp-chart/values.yaml), [`hpa.yaml`](../../../techx-corp-chart/templates/hpa.yaml) | Chỉ customer path được co giãn; sau peak trả về floor 1 | Repository không có Cluster Autoscaler/Karpenter nên HPA không tự tạo worker node |
| API-only Locust, 200 users, operator-controlled start | [`RUNBOOK.md` §2](RUNBOOK.md#2-test-contract--giữ-cấu-hình-bất-biến) | Giữ traffic mix cố định và tránh browser traffic/noise không thuộc mục tiêu | Raw archive hiện thiếu `stats-history.csv`, nên không replay được active-user timeline từ artifact |
| Metrics Server cho HPA; Prometheus/Grafana cho SLO | [`values-observability.yaml`](../../../deploy/values-observability.yaml), [dashboard design](../epic-03-performance-efficiency/runtime/c0g-29/flash-sale-dashboard-design.md) | Dùng native Kubernetes metrics cho autoscaling, OTel span metrics cho customer-facing SLO | Panel `No data` là finding, không được diễn giải là healthy |

Capacity boundary không đổi: node group EKS dùng `2 x t3.large` desired (max 4) và namespace quota là requests `4 CPU / 8Gi`, limits `8 CPU / 12Gi`; xem [`preparation-report.md` §3.3](preparation-report.md#33-capacity-boundaries-và-open-risk). Vì không có node autoscaler, `max=4` không phải bằng chứng node sẽ tự scale.

## 2.8 Raw Locust Result, PromQL Workload Và Đối Chiếu SLO

### Raw EKS Locust Artifact

Raw artifact của live run nằm tại [`artifacts/live-run-14-7-2026/`](artifacts/live-run-14-7-2026/):

* [requests CSV](artifacts/live-run-14-7-2026/Locust_2026-07-14-08h13_locustfile.py_http___frontend-proxy_8080_requests.csv)
* [failures CSV](artifacts/live-run-14-7-2026/Locust_2026-07-14-08h13_locustfile.py_http___frontend-proxy_8080_failures.csv)
* [exceptions CSV](artifacts/live-run-14-7-2026/Locust_2026-07-14-08h13_locustfile.py_http___frontend-proxy_8080_exceptions.csv) — header only, không có exception
* [Locust HTML report](artifacts/live-run-14-7-2026/Locust_2026-07-14-08h13_locustfile.py_http___frontend-proxy_8080.html)

| Client-side metric từ aggregated row | Giá trị | Cách dùng trong report |
| --- | ---: | --- |
| Total requests | 36,460 | Workload denominator của live archive |
| Failures | 7 | Tất cả là HTTP 503 trong failures CSV; không che giấu bằng dashboard gauge |
| Successful requests | 36,453 | `36,460 - 7`; dùng cho allocation/request tại §2.9 |
| Aggregate success | 99.9808% | Aggregate gồm cả route ngoài SLO group |
| Mean request rate | 40.507 req/s | `36,460 / 40.507 ≈ 900s`, tương ứng khoảng 15 phút steady workload |
| Aggregate p95 | 800 ms | Không thay thế storefront SLO metric vì route population khác |
| `POST /api/checkout` | 1,932 requests, 0 failures, p95 1,400 ms | Client-side endpoint result, không thay thế frontend-span SLO |

### Server-side Workload Và SLO Từ Grafana/PromQL

Dashboard SLO đo **customer-facing frontend server spans** (`service_name="frontend"`, `span_kind="SPAN_KIND_SERVER"`), không đo Locust aggregate. Đây là query dùng để lấy server-side workload và SLO trong Grafana Explore, theo [dashboard design](../epic-03-performance-efficiency/runtime/c0g-29/flash-sale-dashboard-design.md):

```promql
# Storefront p95
histogram_quantile(0.95, sum by (le) (rate(
  traces_span_metrics_duration_milliseconds_bucket{
    service_name="frontend", span_kind="SPAN_KIND_SERVER",
    span_name=~"GET /|GET /product.*|GET /api/products.*|GET /api/data.*"
  }[5m])))

# Checkout workload trong 15-minute window
sum(increase(traces_span_metrics_calls_total{
  service_name="frontend", span_kind="SPAN_KIND_SERVER",
  span_name="POST /api/checkout"
}[15m]))

# Checkout success ratio
100 * sum(rate(traces_span_metrics_calls_total{
  service_name="frontend", span_kind="SPAN_KIND_SERVER",
  span_name="POST /api/checkout", status_code!="STATUS_CODE_ERROR"
}[5m]))
/ sum(rate(traces_span_metrics_calls_total{
  service_name="frontend", span_kind="SPAN_KIND_SERVER",
  span_name="POST /api/checkout"
}[5m]))
```

Dùng cùng pattern `increase(...)` cho browse/cart để lấy volume server-side, và `rate(...)` success ratio để xét SLO. PromQL xác nhận workload/SLO phía server, **không phải** nguồn AWS billing.

Dashboard evidence đã lưu quan sát window `2026-07-13T22:43:00Z`–`22:58:00Z`: storefront p95 mean 329 ms, max 918 ms; browse/cart/checkout gauge 100% với volume tương ứng ~6.99k/~5.17k/~1.47k. Đây là PASS cho **dashboard window** trong §2.3.

> **Không gộp hai window:** Locust filename là `2026-07-14-08h13`, còn dashboard observation đã ghi là `22:43–22:58Z`. Report giữ chúng là hai evidence line riêng. Không dùng raw Locust aggregate thay dashboard SLO, và không dùng dashboard gauge để che 7 raw 503s. Closing rerun phải archive `stats-history.csv` cùng T0–T1 UTC và screenshot PromQL/Grafana cùng range.

### Live-run Dashboard Screenshots

![Live run dashboard end window 1](artifacts/live-run-14-7-2026/liverun-dashboard-end-30m-window-1.png)

![Live run dashboard end window 2](artifacts/live-run-14-7-2026/liverun-dashboard-end-30m-window-2.png)

## 2.9 Cost Estimate Theo Workload Live Archive

`preparation-report.md` §5 là **pre-live allocation estimate** dùng local denominator. Bảng dưới đây tính lại bằng workload từ raw EKS Locust archive: 36,453 successful requests trong 15 phút. Đơn giá giữ nguyên AWS Price List `us-east-1` On-Demand đã lưu: `t3.large = $0.0832/hour`, EKS control plane `$0.1000/hour`, và 40 GiB root gp3 `$0.0800/GB-month`.

```text
window = 15 minutes = 0.25 hour
EC2 allocation  = 2 × $0.0832 × 0.25              = $0.041600
EKS allocation  = 1 × $0.1000 × 0.25              = $0.025000
gp3 allocation  = 40 GiB × $0.0800 × (0.25 / 720) = $0.001111
allocated total                                   = $0.067711
```

| Chỉ số cost efficiency | Công thức | Allocated estimate |
| --- | --- | ---: |
| Infrastructure allocation / 15-minute workload | EC2 + EKS + root gp3 | **$0.067711** |
| Allocation / successful request | `$0.067711 / 36,453` | **$0.000001857** (~$0.001857 / 1,000 requests) |
| Allocation / successful checkout request proxy | `$0.067711 / 1,932` | **$0.000035047** |

`1,932` là successful checkout **request**, không phải confirmed successful order; không gọi là cost/order trước khi export order success/deduplication đúng cùng window. Allocation thấp hơn estimate 16m20s trước live vì chỉ dùng measured 15-minute workload; đây **không** phải actual AWS bill và cũng không chứng minh marginal charge.

Cost Explorer/CUR final sign-off vẫn cần filter đúng UTC window và bổ sung NAT Gateway/data processing, ALB/LCU, data transfer, CloudWatch, ECR, workload/PVC storage, tax, T3 Unlimited surplus credits. Sau đó mới tính lại cost/successful request và cost/successful order để kết luận “cost không phình”.

---

# 3. Hướng Dẫn Mentor Rerun / Witness

## 3.1 Verify Public / Private Route Split

```powershell
$ALB = "http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"

foreach ($p in @(
"/",
"/grafana/",
"/jaeger/ui/",
"/loadgen/",
"/feature",
"/flagservice/",
"/otlp-http/"
)) {

    $code = try {
        (Invoke-WebRequest "$ALB$p" `
            -UseBasicParsing `
            -MaximumRedirection 0 `
            -TimeoutSec 5 `
            -ErrorAction Stop).StatusCode
    }
    catch {
        [int]$_.Exception.Response.StatusCode
    }

    Write-Output "$p -> HTTP $code"
}
```

Expected result:

```text
/ -> HTTP 200
/grafana/ -> HTTP 404
/jaeger/ui/ -> HTTP 404
/loadgen/ -> HTTP 404
/feature -> HTTP 404
/flagservice/ -> HTTP 404
/otlp-http/ -> HTTP 404
```

## 3.2 Verify Runtime State Hiện Tại

```powershell
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get deploy,hpa

kubectl -n techx-observability get pods -o wide

kubectl top nodes

kubectl -n techx-tf4 top pods
kubectl -n techx-observability top pods
```

## 3.3 Verify Restart Reasons

```powershell
kubectl -n techx-tf4 describe pod postgresql-879c5bd4-5fpq4

kubectl -n techx-observability describe pod jaeger-5f4f88c588-5wk48

kubectl -n techx-observability describe pod opensearch-0
```

## 3.4 Verify Trace Data Trong Run Window

```powershell
$start = [DateTimeOffset]::Parse(
"2026-07-13T22:43:00Z"
).ToUnixTimeMilliseconds()

$end = [DateTimeOffset]::Parse(
"2026-07-13T22:58:00Z"
).ToUnixTimeMilliseconds()

kubectl -n techx-observability exec opensearch-0 -- `
curl -g -s `
"http://localhost:9200/jaeger-span-2026-07-13/_count?q=startTimeMillis:[$start%20TO%20$end]&pretty"
```

Count đã quan sát khi verify:

```text
836,476 spans
```

---

# 4. Bảng Acceptance Criteria

| Acceptance Criteria                               | Verdict | Evidence / Ghi chú                                           |
| ------------------------------------------------- | ------- | ------------------------------------------------------------ |
| Mentor truy cập được storefront                   | PASS    | Public `/` trả HTTP 200                                      |
| Grafana không public                              | PASS    | Public `/grafana/` trả HTTP 404                              |
| Jaeger không public                               | PASS    | Public `/jaeger/ui/` trả HTTP 404                            |
| Mentor có hướng dẫn private access                | PASS    | Đã có port-forward instructions                              |
| Mentor có thể rerun hoặc witness test             | PASS    | Có runbook và load config                                    |
| Evidence có timestamp và cùng test window         | PARTIAL | Dashboard và trace window align, baseline và CSV khác window |
| Có bảng pass/fail từng requirement                | PASS    | Bảng này                                                     |
| Không dùng local-only path trong deliverable cuối | PASS    | Dùng relative path và public ALB                             |
| 200 users / 15 minutes đã cấu hình                | PASS    | Runtime env và task4 shape đã verify                         |
| Raw Locust result cho 200 users / 15 minutes      | PARTIAL | `artifacts/live-run-14-7-2026/` có requests/failures/exceptions/HTML; thiếu `stats-history.csv` |
| SLO giữ trong target                              | PASS    | Grafana dashboard SLO panels                                 |
| Dashboard screenshots included                    | PASS    | Đã liệt kê                                                   |
| Alert evidence included                           | PARTIAL | Có `screenshots/04-grafana-alert-state-window.jpg`; còn thiếu checkpoint pre/during/post riêng |
| Resource before/during/after included             | PASS    | Đầy đủ                                                       |
| Scale-down evidence included                      | PASS    | HPA về 1/1 và load-generator = 0/0                           |
| Cost estimate included                            | PASS    | Có allocation estimate; final billing evidence vẫn pending   |
| Reliability gate sạch, không OOM/restart          | FAIL    | PostgreSQL và Jaeger OOMKilled sau window                    |

---

# 5. Final Verdict

| Directive    | Verdict                             | Tóm tắt                                                                                  |
| ------------ | ----------------------------------- | ---------------------------------------------------------------------------------------- |
| Directive #1 | PASS                                | Storefront public, operational portals private                                           |
| Directive #2 | PARTIAL PASS with post-run incident | SLO đạt, scale-down tốt, trace tồn tại; tuy nhiên PostgreSQL và Jaeger OOMKilled sau run |

## Suggested Wording Cho Mentor

```text
Bài 200-user flash-sale đã chạy xong và dashboard customer-facing SLO nằm trong target trong cửa sổ quan sát.

Storefront vẫn public, trong khi Grafana, Jaeger và các route vận hành vẫn private.

HPA đã scale-down sau peak và trace data tồn tại trong OpenSearch cho test window.

Known post-run incident:

- PostgreSQL OOMKilled ngay sau main test window.
- Jaeger OOMKilled ngay sau main test window.
- OpenSearch trước đó từng gặp Java heap pressure và flood-stage block.

Các điểm này được ghi nhận thành follow-up reliability risks trước khi tuyên bố platform đã được harden hoàn toàn.
```
