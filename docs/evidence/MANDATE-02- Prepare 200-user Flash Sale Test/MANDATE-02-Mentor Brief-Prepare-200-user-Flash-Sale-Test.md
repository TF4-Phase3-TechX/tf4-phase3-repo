# MANDATE-02 Mentor Brief: Prepare 200-user Flash Sale Test

> Tài liệu này thay cho backlog cũ. Mục tiêu là dùng để nộp mentor/review: giải thích MANDATE-02 là gì, liên quan thế nào đến hai trụ Performance Efficiency và Cost Optimization, team cần làm gì, đã làm gì, kết quả ra sao, vì sao chọn hướng đó, và task thuộc về ai.
>

## 1. Executive Summary

MANDATE-02 yêu cầu chuẩn bị và chứng minh hệ thống có thể chịu bài kiểm thử Flash Sale **200 concurrent users trong 15 phút**, trong khi vẫn giữ SLO customer-facing và không làm chi phí trên mỗi successful unit phình ra.

| Nội dung | Kết luận hiện tại |
|---|---|
| Mandate | Prepare 200-user Flash Sale Test |
| Cluster | `techx-tf4-cluster`, region `us-east-1`, account `511825856493` |
| Namespace ứng dụng | `techx-tf4` |
| Namespace observability | `techx-observability` |
| Trụ liên quan | Performance Efficiency và Cost Optimization |
| Trạng thái tổng hợp | Có thể nộp mentor như bản evidence tổng hợp cho Performance và Cost |
| Verdict ngắn gọn | Customer-facing SLO trong dashboard window đạt; scale-down quan sát được; cost đã có allocation estimate và còn chờ đối chiếu billing thực tế |

Kết quả chính đã quan sát trong dashboard window `2026-07-13T22:43:00Z` đến `2026-07-13T22:58:00Z`:

| Tiêu chí | Quan sát | Threshold | Verdict |
|---|---:|---:|---|
| Load-generator activity | `70.0 spans/s` | Có traffic | PASS |
| Frontend inbound RPS | Mean `70.2 req/s`, max `86.7 req/s` | Có traffic | PASS |
| Storefront p95 latency | Mean `329 ms`, max `918 ms` | `< 1000 ms` | PASS |
| Browse success rate | `100%` | `>= 99.5%` | PASS |
| Cart success rate | `100%` | `>= 99.5%` | PASS |
| Checkout success rate | `100%` | `>= 99.0%` | PASS |
| Browse volume | `~6.99k` | Có volume | PASS |
| Cart volume | `~5.17k` | Có volume | PASS |
| Checkout volume | `~1.47k` | Có volume | PASS |

Kết luận cần nói thẳng với mentor:

- Bài flash-sale đã có evidence cho customer-facing SLO đạt trong cửa sổ quan sát.
- HPA/load-generator đã quay về baseline sau peak theo evidence hiện có.
- Cost đã có allocation estimate, nhưng chưa phải Cost Explorer/CUR actual billing.
- Raw Locust archive live-run có requests/failures/exceptions/HTML, nhưng thiếu `stats-history.csv`; vì vậy timeline raw active-user có thể bổ sung thêm nếu mentor cần replay chi tiết.

## 2. MANDATE-02 là gì?

MANDATE-02 tập trung vào năng lực scale dưới ràng buộc chi phí cho kịch bản Flash Sale. Đây không chỉ là chạy load test, mà là một gói chuẩn bị gồm resource tuning, autoscaling, evidence collection, SLO verification và cost efficiency estimate.

| Yêu cầu mandate | Ý nghĩa thực tế | Evidence/source |
|---|---|---|
| 200 concurrent users | Hệ thống phải phục vụ tải cao hơn baseline bình thường | `RUNBOOK.md`, `TASK-11-FINAL-EVIDENCE-PACKAGE.md` |
| Giữ 15 phút steady-state | Không chỉ spike ngắn; phải giữ được tải trong một window ổn định | `RUNBOOK.md`, Locust artifact |
| Storefront p95 `< 1s` | Người dùng vẫn browse được nhanh trong peak | Grafana dashboard SLO |
| Browse/cart success `>= 99.5%` | Các flow trước checkout không bị lỗi hàng loạt | Grafana dashboard SLO |
| Checkout success `>= 99%` | Revenue path vẫn hoạt động | Grafana dashboard SLO |
| Scale xuống sau peak | Không giữ capacity cao sau khi sale kết thúc | HPA/load-generator runtime evidence |
| Cost/successful unit không phình | Performance improvement không đổi bằng chi phí không kiểm soát | `preparation-report.md`, `TASK-11-FINAL-EVIDENCE-PACKAGE.md` |

Ràng buộc quan trọng:

- Storefront public, các cổng vận hành như Grafana/Jaeger/Loadgen vẫn private.
- Không tắt hoặc né cơ chế incident/feature flag `flagd` để làm bài test dễ pass.
- Không dùng local Minikube để kết luận EKS/AWS PASS.
- Operational evidence phải ưu tiên UI: Grafana, Jaeger, OpenSearch, Alertmanager và Locust UI/report.

## 3. Liên quan gì đến hai trụ Performance và Cost?

### 3.1. Performance Efficiency

MANDATE-02 là bằng chứng trực tiếp cho trụ Performance Efficiency vì nó kiểm tra hệ thống dưới tải Flash Sale thực tế hơn baseline bình thường.

| Performance concern | Cách MANDATE-02 xử lý | Kết quả/evidence |
|---|---|---|
| Latency storefront trong peak | Đo p95 bằng Grafana span metrics phía server | Storefront p95 mean `329 ms`, max `918 ms`, dưới ngưỡng `1000 ms` |
| Success rate của flow chính | Đo browse/cart/checkout success rate theo dashboard SLO | Browse/cart/checkout đều `100%` trong dashboard window |
| Bottleneck runtime | Theo dõi pod/node CPU, memory, restart/resource signal và HPA replica | Có evidence resource before/during/after để đối chiếu tải trước, trong và sau bài test |
| Autoscaling customer path | Bật HPA cho `frontend` và `checkout`, min 1/max 3, target CPU 70% | Sau run quan sát `frontend` và `checkout` về `1/1` |
| Load shape ổn định | API-only Locust, 200 users, ramp-up 60s, steady 15 phút | Có raw Locust archive và dashboard load activity |

### 3.2. Cost Optimization

MANDATE-02 cũng thuộc Cost Optimization vì bài test không được giải bằng cách tăng tài nguyên mù quáng. Team phải chứng minh hiệu năng đạt được trong một resource contract có kiểm soát.

| Cost concern | Cách MANDATE-02 xử lý | Kết quả/evidence |
|---|---|---|
| Không overprovision vô căn cứ | Dùng ladder `lean -> balanced -> headroom`, chỉ tăng khi SLO hoặc reliability gate cần thêm headroom | Chọn candidate có requests/limits rõ ràng, không tune node size/count |
| Giữ normal-time reservation thấp | Baseline 1 replica cho một số stateless low-điểm cần lưu ý path; HPA floor 1 cho customer path | Giảm capacity thường trực trước Flash Sale |
| Không để load generator tự tạo traffic | `LOCUST_AUTOSTART=false`, operator-controlled start | Baseline ghi load-generator idle `0 spans/s` |
| Ước lượng cost/test window | Tính allocation EC2 + EKS control plane + root gp3 | Live allocation estimate 15 phút: `$0.067711` |
| Cost/successful unit | Tính allocation/successful request từ live archive | `$0.000001857` / successful request, estimate only |
| Không đánh đồng estimate với actual bill | Ghi rõ Cost Explorer/CUR vẫn pending | Final billing sign-off chưa hoàn tất |

## 4. Team cần làm gì cho MANDATE-02?

Để đáp ứng mandate, nhóm Performance/Cost cần hoàn thành các nhóm việc sau:

| Nhóm việc | Cần làm | Vì sao cần |
|---|---|---|
| Baseline trước test | Chụp traffic, SLO, resource, node, replica, restart/resource signal và load-generator idle | Có mốc so sánh before/during/after, tránh nhầm synthetic traffic với baseline thật |
| Resource tuning | Đặt CPU/memory requests/limits cho các service trong scope Flash Sale | Scheduler có reservation rõ ràng; HPA có CPU baseline |
| Autoscaling | Bật HPA có giới hạn cho `frontend` và `checkout` | Chỉ scale customer-facing stateless path, tránh scale stateful/observability thiếu kiểm soát |
| Load test contract | Cố định 200 users, API-only, ramp-up/steady/ramp-down, operator-controlled start | Đảm bảo bài test có thể rerun/witness và không bị nhiễu browser traffic |
| Dashboard/evidence | Thu Grafana, Jaeger, OpenSearch, Alertmanager và Locust report/UI | Mentor có thể kiểm chứng SLO, trace, alert, resource và load behavior |
| Cost model | Tính allocation cho test window và cost/successful request | Chứng minh performance không đổi bằng chi phí quá mức |
| Mentor package | Gói evidence cuối, verdict từng acceptance criterion và cách rerun/witness | Người review thấy rõ phạm vi đã chứng minh, evidence ở đâu và phần nào cần đối chiếu thêm |

## 5. Team đã làm gì?

### 5.1. Chuẩn bị baseline trước load test

Nguồn: `TASK-5-Pre-Load-Test-Baseline.md`.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| Timestamp baseline | Chụp baseline lúc `2026-07-14 00:59:40 +07:00` | Có ảnh timestamp và dashboard window trước test |
| Load-generator idle | Kiểm tra Grafana load-generator activity | `0 spans/s`, không có load test chạy ngầm |
| Baseline traffic | Ghi frontend inbound RPS và request volume | Mean `0.685 req/s`, max `1.12 req/s`; browse volume `72`, cart/checkout `0` |
| Baseline latency | Ghi p50/p95/p99 | p95 mean `33.6 ms`, max `94.2 ms`; p99 max spike `847 ms` |
| Node baseline | Ghi node count/type/status | `2 x t3.large`, cả hai Ready |
| Restart/resource baseline | Kiểm tra pod restart, last termination, resource events | Không thấy restart/resource issue trên pod hiện tại trong baseline |
| Existing issues | Ghi dashboard gaps trước test | Node count panel `No data`, CPU unit sai `min`, RPS aggregation lệch |

### 5.2. Tuning và guardrail trước Flash Sale

Nguồn: `preparation-report.md`.

| Hạng mục | Đã làm | Vì sao làm |
|---|---|---|
| Resource contract | 12 service trong scope có direct CPU/memory requests và limits | Scheduler cần reservation rõ ràng, HPA cần CPU baseline |
| Replica baseline | Một số stateless low-điểm cần lưu ý path dùng 1 replica; `frontend`/`checkout` dùng HPA floor 1 | Giảm normal-time reservation/cost nhưng vẫn cho phép scale customer path |
| HPA | Chỉ bật HPA cho `frontend` và `checkout`, min 1/max 3, target CPU 70%, scale-down stabilization 300s | Scale phần customer-facing, không động stateful/observability/flagd |
| Metrics Server | Thêm Metrics Server cho Kubernetes resource metrics | HPA CPU và `kubectl top` cần `metrics.k8s.io` |
| Load control | `LOCUST_AUTOSTART=false`, API-only, 200 users, browser traffic disabled | Load chỉ bắt đầu khi operator duyệt; tránh synthetic traffic tự chạy |
| Evidence gate | Quy định UI-first evidence và raw Locust CSV/HTML | Mentor có bằng chứng nhìn thấy được, không dựa vào terminal/raw JSON |
| CI/deploy checks | Render/lint chart, assert requests/limits và HPA scope | Giảm lỗi cấu hình trước khi canary |

### 5.3. Thiết kế runbook official test

Nguồn: `RUNBOOK.md`.

| Hạng mục | Đã làm | Kết quả mong đợi |
|---|---|---|
| Test contract | Định nghĩa Locust UI, 200 users, spawn rate `3.33/s`, ramp-up 60s, steady 15 phút | Run có shape nhất quán và có thể witness |
| Evidence folder | Chuẩn hóa cấu trúc `official-<RUN_ID>/` | Artifact dễ audit: locust, dashboard, alerts, traces, logs, incident |
| Screenshot rules | Yêu cầu UTC range, panel title, legend, tooltip/value | Screenshot đủ giá trị để kết luận |
| Pre-flight | Kiểm tra pod state, flagd, Metrics API, Grafana/Prometheus/Jaeger | Dừng sớm nếu môi trường không đủ điều kiện |
| SLO verdict | Định nghĩa threshold và PromQL/Grafana source | Không dùng Locust aggregate thay server-side SLO |
| Safety stop | Định nghĩa điều kiện dừng khi SLO/resource/observability Follow-up | Không để test tiếp tục khi điểm cần lưu ý vượt ngưỡng |

### 5.4. Chạy và đóng gói evidence live-run

Nguồn: `TASK-11-FINAL-EVIDENCE-PACKAGE.md` và `artifacts/live-run-14-7-2026/`.

| Hạng mục | Đã làm | Kết quả |
|---|---|---|
| Dashboard SLO | Chụp Grafana traffic, SLO, resource, restart/resource signal, HPA | SLO customer-facing PASS trong dashboard window |
| Trace verification | Query OpenSearch trace trong UTC window | `836,476` spans trong window `2026-07-13T22:43:00Z`-`22:58:00Z` |
| Raw Locust archive | Lưu requests/failures/exceptions CSV và HTML report | Có workload denominator; `stats-history.csv` có thể bổ sung nếu cần replay timeline chi tiết |
| Scale-down evidence | Chụp HPA/load-generator sau run | `frontend` và `checkout` về `1/1`; load-generator `0/0` |
| Alert evidence | Có screenshot alert-state window | Đã có bằng chứng alert-state; checkpoint pre/during/post có thể bổ sung nếu cần theo đúng runbook |
| Cost estimate | Tính allocation theo live workload | `$0.067711` cho 15 phút; `$0.000001857` / successful request |

## 6. Kết quả như thế nào?

### 6.1. Performance result

| Khu vực | Kết quả | Diễn giải |
|---|---|---|
| Customer-facing SLO | PASS trong dashboard window | Storefront p95 max `918 ms`, browse/cart/checkout success `100%` |
| Load activity | PASS | Load-generator activity `70.0 spans/s`, frontend inbound RPS mean `70.2 req/s` |
| Raw client-side result | Có raw artifact live-run | Raw archive có `36,460` requests, `7` lỗi client-side, `36,453` successful requests; history CSV có thể bổ sung nếu cần replay timeline chi tiết |
| Checkout client-side | PASS về số lỗi client-side, cần phân biệt metric | `POST /api/checkout`: `1,932` requests, `0` lỗi client-side, p95 client-side `1,400 ms`; không thay server-side storefront SLO |
| Trace evidence | PASS | OpenSearch đếm được `836,476` spans trong test window, đủ làm trace evidence cho mentor |

### 6.2. Cost result

| Khu vực | Kết quả | Diễn giải |
|---|---|---|
| Pre-live allocation estimate | `$0.073730` cho 16m20s | Dùng local denominator, không phải actual bill |
| Live allocation estimate | `$0.067711` cho 15 phút | EC2 + EKS control plane + 40GiB root gp3 |
| Allocation/successful request | `$0.000001857` | Dựa trên `36,453` successful requests live archive |
| Allocation/successful checkout request proxy | `$0.000035047` | Dựa trên `1,932` checkout requests, chưa phải cost/order |
| Final billing | Pending | Cần Cost Explorer/CUR, NAT, ALB/LCU, data transfer, CloudWatch, ECR, PVC/storage, tax, T3 surplus credits |

### 6.3. Scale-down result

| Requirement | Kết quả | Evidence |
|---|---|---|
| Frontend scale-down sau peak | PASS theo evidence hiện có | HPA current/desired `1/1` |
| Checkout quay về baseline | PASS theo evidence hiện có | HPA current/desired `1/1` |
| Load-generator stop sau run | PASS | Deployment `0/0` |
| Node autoscaling | Không tuyên bố PASS | Repository không có Cluster Autoscaler/Karpenter; node group max 4 không đồng nghĩa tự scale |

### 6.4. Điểm cần bổ sung sau bản nộp này

| Điểm cần bổ sung | Trạng thái | Lý do |
|---|---|---|
| Cost Explorer/CUR | Pending | Cần đối chiếu actual billing sau khi có dữ liệu AWS theo UTC window |
| Alert checkpoint đầy đủ | Có evidence nền, có thể bổ sung | Runbook đề xuất checkpoint pre/during/post riêng nếu mentor yêu cầu audit sâu |
| Raw active-user history | Có raw Locust report/CSV chính, có thể bổ sung history | stats-history.csv hữu ích cho replay timeline chi tiết |
| Dashboard polish | Cần chuẩn hóa thêm | Một số panel có No data hoặc unit cần chuẩn hóa cho lần review sau |

## 7. Task ownership

| Task/Jira | Work | Assignee | Status | Evidence/Output |
|---|---|---|---|---|
| `COG-28` | Task-1: Xác nhận Grafana/Jaeger private access và storefront không bị ảnh hưởng | Nguyen Huy Hoang | Done | `TASK-11-FINAL-EVIDENCE-PACKAGE.md` mục Directive #1 |
| `COG-29` | Task-2: Hoàn thiện Grafana Dashboard cho bài test flash sale | Huy Tạ Hoàng | Done | `screenshots/01-grafana-traffic-loadgen.jpg`, `screenshots/02-grafana-slo-resources.jpg`, dashboard evidence |
| `COG-30` | Task-3: Cấu hình alert cho SLO và resource pressure trong flash sale | Tín Văn Phú (Văn Phú Tín) | Done | `screenshots/Grafana alert-state window.jpg`, alert-state evidence |
| `COG-31` | Task-4: Chuẩn bị kịch bản 200 concurrent users trong 15 phút | Nguyen Quach Khang Ninh | Done | `RUNBOOK.md`, load test contract, Locust configuration |
| `COG-32` | Task-5: Thu baseline performance, resource và cost trước load test | Truong An | Done | `TASK-5-Pre-Load-Test-Baseline.md` |
| `COG-33` | Task-6: Thực thi bài test flash sale 200 users trong 15 phút | Nguyen Huy Hoang | Done | `TASK-11-FINAL-EVIDENCE-PACKAGE.md`, `artifacts/live-run-14-7-2026/` |
| `COG-37` | Task-10: Xác nhận tài nguyên co xuống và cost nằm trong budget | Nguyễn Thành Vinh | Done | Scale-down evidence, cost allocation estimate trong `TASK-11-FINAL-EVIDENCE-PACKAGE.md` |
| `COG-38` | Task-11: Đóng gói evidence và xác minh Directive | Truong An | Done | `TASK-11-FINAL-EVIDENCE-PACKAGE.md`, file mentor brief này |

## 8. Vì sao team làm ra được kết quả này?

Team đạt được SLO trong dashboard window vì cách chuẩn bị không chỉ dựa vào tăng tài nguyên, mà theo hướng có kiểm soát:

1. Có baseline trước test để biết hệ thống ở trạng thái idle/normal như thế nào.
2. Load-generator không tự chạy, nên baseline không bị synthetic traffic làm nhiễu.
3. Các service trong scope có requests/limits rõ ràng, giúp scheduler và HPA có cơ sở tính toán.
4. Chỉ bật HPA cho `frontend` và `checkout`, tức là tập trung vào customer path thay vì scale toàn bộ hệ thống.
5. Load shape được cố định API-only, tránh browser traffic làm nhiễu kết quả.
6. SLO được đo từ server-side Grafana span metrics, không chỉ dựa vào Locust aggregate.
7. Cost được tính theo workload denominator thay vì chỉ nhìn tổng bill chung.
8. Các điểm cần bổ sung được ghi riêng, nên mentor có thể phân biệt phần đã chứng minh với phần cần đối chiếu thêm.

## 9. Evidence map cho mentor

| Evidence | Vai trò |
|---|---|
| `preparation-report.md` | Giải thích tuning, resource contract, HPA, cost estimate pre-live và điều kiện đóng mandate |
| `RUNBOOK.md` | Source of truth cho official 200-user Flash Sale test và evidence rule |
| `TASK-5-Pre-Load-Test-Baseline.md` | Baseline trước load test: traffic, latency, resources, replica, restart/resource signal |
| `TASK-11-FINAL-EVIDENCE-PACKAGE.md` | Gói tổng hợp kết quả, SLO, scale-down, cost estimate, điểm cần bổ sung |
| `artifacts/lean-v2-20260713T163957Z/` | Local canary evidence, chỉ dùng để chọn candidate, không dùng kết luận EKS PASS |
| `artifacts/live-run-14-7-2026/` | Raw live-run Locust artifacts và dashboard screenshots |
| `screenshots/` | Grafana/kubectl/runtime/alert evidence cho baseline và live result |

## 10. Suggested wording nộp mentor

```text
MANDATE-02 đã được chuẩn bị và chạy evidence cho kịch bản Flash Sale 200 users.

Trong dashboard window 2026-07-13T22:43:00Z-22:58:00Z, customer-facing SLO đạt target: storefront p95 dưới 1 giây, browse/cart/checkout success rate đạt 100% trên dashboard, và hệ thống có trace evidence trong OpenSearch.

Về Performance Efficiency, team đã dùng baseline, resource contract, HPA cho frontend/checkout, Metrics Server và Grafana span metrics để chứng minh latency/success rate trong peak.

Về Cost Optimization, team không tăng tài nguyên mù quáng; dùng lean tuning, HPA floor, operator-controlled load generator và allocation model để ước lượng cost/successful request. Live allocation estimate là khoảng $0.067711 cho 15 phút, tương đương khoảng $0.000001857 trên mỗi successful request, nhưng đây chưa phải actual AWS billing.

Các điểm cần bổ sung sau bản nộp: alert checkpoint pre/during/post nếu mentor yêu cầu audit sâu, raw stats-history cho active-user timeline chi tiết, và Cost Explorer/CUR để chốt actual billing.

Vì vậy verdict hiện tại là: SLO và scale-down PASS trong evidence window, cost estimate PASS ở mức allocation estimate, và billing thực tế sẽ được đối chiếu thêm khi Cost Explorer/CUR có đủ dữ liệu.
```

## 11. Final Verdict

| Area | Verdict | Ghi chú |
|---|---|---|
| Performance SLO trong dashboard window | PASS | Storefront p95, browse/cart/checkout success đạt target |
| Scale-down sau peak | PASS theo evidence hiện có | `frontend`/`checkout` về `1/1`, load-generator `0/0` |
| Cost estimate | PASS ở mức estimate | Có allocation estimate; Cost Explorer/CUR pending |
| Evidence package | Ready for mentor review | Có dashboard screenshots, raw Locust artifacts chính, trace evidence, cost estimate và owner mapping; checkpoint chi tiết có thể bổ sung nếu mentor yêu cầu |
| Mentor submission readiness | Ready for mentor review | Có thể nộp với các evidence, owner và điểm cần bổ sung được trình bày rõ |






