# CDO-04 Backlog: Performance Efficiency và Cost Optimization

## 1. Mục đích, phạm vi và hai trụ CDO-04

Tài liệu này là backlog thực thi tập trung cho các khoảng trống do CDO-04 phụ trách. Phạm vi chỉ gồm hai trụ sau:

| Trụ | Finding thuộc CDO-04 | Mục tiêu backlog |
|---|---|---|
| Performance Efficiency | `PERF-01`, `PERF-02` | Giảm latency và loại bỏ bottleneck có thể kiểm chứng bằng trace, query plan và runtime metrics. |
| Cost Optimization | `COST-01`, `COST-02`, `K8S-03` | Bảo vệ baseline, kiểm soát cost driver, và right-size chỉ khi có evidence cùng rollback plan. |

Tổng cộng có năm finding thuộc phạm vi: `PERF-01`, `PERF-02`, `COST-01`, `COST-02` và `K8S-03`.

### Business context theo finding

| Finding | Business impact |
|---|---|
| `PERF-01` | Browse là luồng traffic cao và có mục tiêu p95 dưới 1 giây. N currency call cho một lần browse bằng non-USD có thể làm `currency` bão hòa, tăng browse p95/p99, làm trải nghiệm tìm sản phẩm chậm hơn và giảm conversion trước khi người dùng đi tới checkout. |
| `PERF-02` | Search broad có thể full scan, trả response lớn và làm PostgreSQL bão hòa. Vì database này còn phục vụ catalog và các bước chuẩn bị item cho checkout, sự cố search có thể lan sang luồng doanh thu. Giới hạn kết quả và pagination giúp giữ browse/search responsive khi dữ liệu tăng. |
| `COST-01` | Nếu Locust tự chạy trong baseline, team không thể phân biệt chi phí, latency, request rate và trace volume do khách hàng thật với synthetic traffic. Baseline sai có thể dẫn đến right-sizing sai, cost per successful checkout sai và quyết định budget không đáng tin cậy. |
| `COST-02` | Observability dùng capacity thường trực trên worker nodes. Nếu persistence/retention chưa rõ, doanh nghiệp vẫn trả compute cost nhưng có thể mất metrics, logs và traces đúng lúc cần điều tra incident hoặc bảo vệ SLO. |
| `K8S-03` | Resource plan không đầy đủ có thể làm Helm rollout bị từ chối khi áp dụng quota hoặc làm checkout/browse bị CPU contention khi tải tăng. Nếu chưa có measured requests/limits, việc giảm node hoặc đổi instance type có thể làm latency, checkout success và trải nghiệm khách hàng giảm thay vì tạo cost saving. |


"Hoàn tất baseline" chỉ xác nhận rằng Week 1 đã ghi nhận vấn đề, tác động, hướng xử lý và evidence. Trạng thái này không có nghĩa là thay đổi mã nguồn hoặc cấu hình đã hoàn tất.

Nguyên tắc chung:

- Prometheus, Grafana và PromQL là nguồn CPU/memory runtime evidence.
- Không coi estimate là actual AWS billing. Cost Explorer mới là nguồn đối chiếu actual billing.
- Không giảm resource chỉ để tiết kiệm cost khi workload còn `OOMKilled`, restart bất thường hoặc chưa có cửa sổ evidence từ 48 đến 72 giờ.
- Mỗi backlog item chỉ được đóng sau khi có evidence path, kết quả validation, rủi ro còn lại và so sánh trước/sau nếu thay đổi ảnh hưởng performance hoặc cost.

## 2. Quy tắc ưu tiên và trạng thái hiện tại

| Priority | Ý nghĩa | Lý do xếp priority |
|---|---|---|
| P0 | Bảo vệ baseline và xử lý blocker | Có runtime failure đã xác nhận, hoặc là thay đổi ít rủi ro giúp loại dữ liệu nhiễu ngay. Nếu trì hoãn, team có thể right-size từ baseline sai hoặc làm reliability/observability xấu hơn. |
| P1 | Hoàn thiện evidence và guardrail | Cần cho rollout, cost guardrail và performance decision có thể kiểm chứng. Các việc này cần runtime evidence, owner sign-off hoặc validation trước khi thay đổi production-like baseline. |
| P2 | Tối ưu có điều kiện | Có thể tiết kiệm cost hoặc tăng scale capacity, nhưng có blast radius cao hoặc chưa đủ prerequisite. Chỉ thực hiện sau P0/P1 và khi đã có rollback evidence. |

| Finding | Trụ | Trạng thái hiện tại | Priority áp dụng | Việc kế tiếp ngắn gọn |
|---|---|---|---|---|
| `PERF-01` | Performance Efficiency | Hoàn tất baseline | P1 | Cache exchange rate, rồi so sánh currency fan-out và browse p95. |
| `PERF-02` | Performance Efficiency | Hoàn tất baseline | P1 | Thêm `LIMIT`/pagination, chạy `EXPLAIN ANALYZE`, đo search p95/p99. |
| `COST-01` | Cost Optimization | Đang kiểm chứng | P0 | Đặt `LOCUST_AUTOSTART=false` và xác nhận baseline không còn synthetic traffic tự chạy. |
| `COST-02` | Cost Optimization | Đang kiểm chứng | P0 và P1 | Bảo vệ Jaeger/Grafana trước OOM; sau đó chốt evidence, retention và persistence. |
| `K8S-03` | Cost Optimization | Đang kiểm chứng | P0, P1 và P2 có điều kiện | Ổn định `accounting`, xây resource baseline, kiểm tra `ResourceQuota`, rồi mới đánh giá scaling. |

## 3. P0: Bảo vệ baseline và xử lý blocker

### 3.1. `COST-01`: Tắt `load-generator` tự khởi động

| Hạng mục | Nội dung |
|---|---|
| Priority | P0 |
| Trạng thái | Đang kiểm chứng |
| Vì sao là P0 | `LOCUST_AUTOSTART=true` tạo synthetic traffic liên tục, làm nhiễu request rate, latency, error rate, trace volume và cost/performance baseline. Đây là thay đổi cấu hình ít rủi ro có thể loại nhiễu ngay. |
| Business impact | Nếu Locust tự chạy trong baseline, team không thể phân biệt chi phí, latency, request rate và trace volume do khách hàng thật với synthetic traffic. Baseline sai có thể dẫn đến right-sizing sai, cost per successful checkout sai và quyết định budget không đáng tin cậy. Load generator vẫn cần được giữ, nhưng chỉ dùng cho controlled load test có thời điểm bắt đầu/kết thúc rõ ràng. |
| Evidence hiện có | `load-generator` đang được bật với `LOCUST_AUTOSTART=true`; pod từng có một lần `OOMKilled`; synthetic traffic làm tăng áp lực lên application và observability stack. Locust gọi `frontend-proxy` nội bộ, nên không phải bằng chứng trực tiếp cho ALB LCU hoặc NAT data processing tăng. |
| Hướng xử lý | Đặt `LOCUST_AUTOSTART=false` cho baseline EKS và local path nếu path đó còn được team sử dụng. Chỉ bật lại trong controlled load test có thời điểm bắt đầu/kết thúc rõ ràng. |
| Dependency | Không có. Đây là bước đầu để các metric sau đó phản ánh idle baseline hoặc controlled load test rõ ràng. |
| Validation | Kiểm tra rendered configuration; xác nhận `load-generator` không tự tạo traffic sau redeploy; đối chiếu Grafana request rate và Jaeger trace volume khi không chạy test. |
| Điều kiện đóng | Cấu hình baseline đã render đúng, telemetry không còn traffic tự phát, và không có application flow phụ thuộc vào việc load-generator chạy 24/7. |

### 3.2. `K8S-03`: Ổn định `accounting` trước compute right-sizing

| Hạng mục | Nội dung |
|---|---|
| Priority | P0, là subtask blocker của `K8S-03` |
| Trạng thái | Đang kiểm chứng |
| Vì sao là P0 | `accounting` đã có runtime failure xác nhận: `OOMKilled`, exit code `137`, restart hơn 118 lần trong khoảng 15 giờ với memory limit `120Mi`. Right-sizing khi async accounting pipeline chưa ổn định có thể che khuất lỗi reliability thay vì tạo tiết kiệm thực. |
| Business impact | `accounting` xử lý hậu kỳ từ order event. Nếu consumer OOM/restart liên tục, dữ liệu accounting/audit/fraud-related processing có thể bị delay hoặc thiếu tin cậy. Việc right-size compute khi pipeline async chưa ổn định có thể làm mất khả năng đánh giá đúng cost saving và reliability của hệ thống sau checkout. |
| Hướng xử lý | Điều tra .NET runtime, Kafka consumer workload và telemetry. Thực hiện measured memory trial có rollback, ví dụ request/limit `200Mi` đến `256Mi`; đây là khoảng thử nghiệm, chưa phải final size. |
| Dependency | Không được thực hiện compute/node right-sizing trước khi nguyên nhân và độ ổn định của `accounting` được xác nhận. |
| Validation | Theo dõi memory trend bằng Prometheus/Grafana, `OOMKilled`, restart count và Kafka consumer behavior trong ít nhất 24 giờ. |
| Điều kiện đóng | Không có `OOMKilled` mới, restart count không tăng trong ít nhất 24 giờ và consumer vẫn xử lý bình thường. |

### 3.3. `COST-02`: Điều tra OOM/restart của Jaeger và Grafana

| Hạng mục | Nội dung |
|---|---|
| Priority | P0, phần bảo vệ observability reliability của `COST-02` |
| Trạng thái | Đang kiểm chứng |
| Vì sao là P0 | Jaeger đã có một lần `OOMKilled`. Grafana có `OOMKilled`, exit `137` và restart count `7` tại memory request/limit `300Mi`. Nếu giảm memory lúc này, team có thể mất trace hoặc dashboard đúng thời điểm cần điều tra incident và làm sai right-sizing evidence. |
| Business impact | Observability là nguồn bằng chứng để bảo vệ SLO, điều tra checkout/browse incident và chứng minh tác động của cost optimization. Nếu Jaeger/Grafana không ổn định, team có thể mất trace/dashboard đúng lúc cần xác định nguyên nhân SLO degradation hoặc rollback một thay đổi không an toàn. |
| Hướng xử lý | Không giảm memory của Jaeger hoặc Grafana. Correlate OOM timestamp với traffic, synthetic traffic, peak CPU/memory usage và restart history. Với Grafana, `512Mi` request và `768Mi` limit chỉ là reliability trial cần kiểm chứng, không phải cost-saving action. |
| Dependency | Cần `COST-01` để loại synthetic traffic tự chạy khỏi baseline; cần Prometheus/Grafana evidence để xác định peak usage. |
| Validation | Có timeline OOM/restart, traffic correlation, peak-memory evidence và dashboard availability sau thay đổi. |
| Điều kiện đóng | Root cause hoặc giới hạn evidence được ghi rõ; không có OOM/restart regression trong cửa sổ theo dõi đã chọn; mọi thay đổi resource có rollback result. |

## 4. P1: Hoàn thiện evidence, guardrail và performance work

### 4.1. Shared evidence window: Prometheus/Grafana baseline trong 48 đến 72 giờ

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `COST-02`, `K8S-03`, `PERF-01`, `PERF-02` |
| Priority | P1 |
| Vì sao là P1 | Đây là prerequisite cho measured right-sizing, capacity decision và HPA, nhưng không tự khắc phục runtime failure đã xác nhận như các mục P0. |
| Business impact | Nếu không có evidence window đủ dài, team có thể đưa ra quyết định tăng/giảm tài nguyên dựa trên snapshot sai. Điều này có thể làm checkout success, browse latency hoặc cost baseline xấu đi mà không có dữ liệu để chứng minh nguyên nhân. |
| Hướng xử lý | Dùng Prometheus/Grafana và PromQL trong 48 đến 72 giờ. Tách idle baseline khỏi controlled load test; ghi CPU/memory trend theo pod và node, restart/OOM history, latency, error rate, request rate và node headroom. |
| Dependency | Bắt đầu sau khi tắt autostart và triển khai các P0 trial cần thiết để baseline không bị nhiễu hoặc che khuất bởi failure chưa xử lý. |
| Validation | Có evidence cho cùng time window, ghi rõ load condition và các workload chịu áp lực. |
| Điều kiện đóng | Evidence đủ để lựa chọn resource theo từng service, đánh giá node headroom, và so sánh trước/sau các thay đổi P1. |

### 4.2. `K8S-03`: Measured resource plan và `ResourceQuota` compatibility

| Hạng mục | Nội dung |
|---|---|
| Priority | P1 |
| Trạng thái | Đang kiểm chứng |
| Vì sao là P1 | `ResourceQuota` có thể khiến Helm rollout bị admission từ chối. Nhiều service thiếu CPU request/limit, một số chỉ có memory limit mà chưa có memory request. Resource plan là prerequisite cho right-sizing an toàn, nhưng cần runtime evidence trước khi chốt số liệu. |
| Business impact | Resource plan không đầy đủ có thể làm rollout bị fail khi áp quota hoặc làm checkout/browse bị CPU contention khi tải tăng. Nếu chưa có measured requests/limits, việc giảm node hoặc đổi instance type có thể làm latency, checkout success và trải nghiệm khách hàng giảm thay vì tạo cost saving. |
| Evidence hiện có | `checkout` có memory limit `20Mi` và `GOMEMLIMIT=16MiB`, chỉ khoảng `4Mi` headroom. Đây là config-based risk, không phải OOM đã xác nhận. Bốn restart đã quan sát của `checkout` liên quan Kafka startup race, không phải OOM. |
| Hướng xử lý | Đặt CPU/memory requests và limits theo từng service từ evidence 48 đến 72 giờ. Tách hai thay đổi của `checkout`: điều chỉnh memory trial, ví dụ limit `64Mi` với `GOMEMLIMIT` khoảng 80% limit; thêm retry/backoff khi tạo Kafka producer lúc startup. Render manifest rồi chạy server-side dry-run hoặc controlled apply với `deploy/quota.yaml`. |
| Dependency | Phải hoàn tất P0 `accounting` stabilization và shared evidence window trước khi chốt resource values. |
| Validation | Rendered resources phản ánh giá trị mong muốn; quota dry-run/apply được admission; theo dõi latency, error rate, restart/OOM sau thay đổi. |
| Điều kiện đóng | Resource plan có evidence theo service, quota validation thành công, `accounting` ổn định, và checkout không còn restart do startup race trong validation window. |

### 4.3. `COST-02`: Retention, persistence và ECR lifecycle guardrail

| Hạng mục | Nội dung |
|---|---|
| Priority | P1 |
| Trạng thái | Đang kiểm chứng |
| Vì sao là P1 | Cost guardrail này ít rủi ro hơn cắt runtime memory, nhưng cần owner sign-off, AWS verification và evidence trước khi thay đổi retention/persistence. |
| Business impact | Observability dùng capacity thường trực trên worker nodes, nhưng nếu persistence/retention chưa rõ thì doanh nghiệp vẫn trả compute cost mà có thể mất metrics, logs và traces đúng lúc cần điều tra incident. Retention/persistence rõ ràng giúp bảo vệ bằng chứng SLO, kiểm soát log/image growth và tránh mất dữ liệu vận hành quan trọng. |
| Evidence hiện có | Observability stack dùng capacity trên worker nodes; không tìm thấy PVC trong namespace ứng dụng. Prometheus, Jaeger và các store có thể mất dữ liệu khi restart. Có 8 CloudWatch log groups và một số chưa đặt retention. Terraform đã khai báo ECR lifecycle policy. |
| Hướng xử lý | Chốt retention cho approved non-critical CloudWatch log groups; quyết định data nào được phép mất khi restart và data nào phải durable; verify policy ECR đã apply, xem lifecycle preview, và harden rule để bảo vệ release/rollback tags. Không tạo ECR lifecycle policy mới vì policy đã tồn tại trong Terraform. |
| Dependency | Cần owner xác nhận retention/persistence; cần Cost Explorer để đối chiếu estimate với actual burn rate khi đánh giá tác động cost. |
| Validation | Có policy và owner approval; `aws ecr get-lifecycle-policy` cùng lifecycle preview xác nhận Terraform policy; protected tags không match cleanup rule. |
| Điều kiện đóng | Retention/persistence decision được ghi nhận, policy deployment được verify, và rollback/release image tags được bảo vệ. |

### 4.4. `PERF-01`: Giảm N+1 currency conversion trong browse flow

| Hạng mục | Nội dung |
|---|---|
| Priority | P1 |
| Trạng thái | Hoàn tất baseline; implementation nằm trong backlog |
| Vì sao là P1 | Browse là flow traffic cao, có mục tiêu p95 dưới 1 giây. Mỗi product có thể tạo một gRPC call đến `currency` khi người dùng dùng currency khác USD; fan-out tăng theo số product, có thể tăng browse p95/p99 và ảnh hưởng conversion. Chưa có SLO breach hiện tại nên không phải P0. |
| Business impact | Browse chậm xảy ra trước checkout nên có thể làm người dùng bỏ luồng mua hàng sớm, giảm conversion và giảm số user đi tới revenue path. Cache exchange rate giúp giảm fan-out mà không cần thêm hạ tầng lớn trong ngắn hạn. |
| Evidence hiện có | Source analysis và Jaeger trace xác nhận rủi ro per-product currency conversion trong non-USD browse flow. |
| Hướng xử lý | Cache exchange rate ngắn hạn theo cặp tiền, ví dụ `USD -> VND`, để nhiều product dùng cùng tỷ giá trong cache window. Batch conversion API chỉ đánh giá nếu cache chưa đủ. |
| Dependency | Cần browse baseline và Jaeger trace để so sánh fan-out. |
| Validation | So sánh số currency call, browse p95 và error rate trước/sau. Kiểm tra correctness của tỷ giá trong TTL đã chọn. |
| Điều kiện đóng | Cache được deploy và evidence cho thấy fan-out giảm mà không làm browse p95, error rate hoặc currency correctness regress. |

### 4.5. `PERF-02`: Bound product catalog search trước khi cân nhắc index mới

| Hạng mục | Nội dung |
|---|---|
| Priority | P1 |
| Trạng thái | Hoàn tất baseline; implementation nằm trong backlog |
| Vì sao là P1 | Search dùng `LOWER()` cùng `LIKE %query%`, chưa có `LIMIT` hoặc pagination. Khi catalog tăng, query có thể full scan, tăng PostgreSQL CPU/IO và lan ảnh hưởng sang browse hoặc checkout. Chưa có runtime SLO breach hiện tại nên cần query evidence trước khi thực hiện thay đổi lớn. |
| Business impact | Search broad trả response lớn hoặc làm PostgreSQL bão hòa có thể khiến browse/search kém responsive và lan sang catalog dependency của checkout. Bounded result và pagination giúp giảm nguy cơ khách hàng bỏ luồng khi tìm sản phẩm, đồng thời tránh bổ sung OpenSearch/search infrastructure quá sớm. |
| Hướng xử lý | Thêm bounded result bằng `LIMIT` và pagination. Chạy `EXPLAIN ANALYZE` với data thực tế, đo search p95/p99. Chỉ đánh giá trigram index hoặc full-text search nếu query plan và latency evidence chứng minh cần thiết. |
| Dependency | Cần query plan và search runtime baseline. Không đưa OpenSearch hoặc search infrastructure mới vào hướng xử lý ngắn hạn. |
| Validation | Có `EXPLAIN ANALYZE` trước/sau, bounded result hoạt động đúng API contract, search p95/p99 và database pressure không regress. |
| Điều kiện đóng | Query có giới hạn kết quả, evidence xác nhận plan/latency sau thay đổi, và mọi quyết định về index có lý do từ runtime evidence. |

## 5. P2: Tối ưu có điều kiện

### 5.1. HPA cho workload có biến động tải

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `K8S-03` |
| Priority | P2 |
| Vì sao là P2 | HPA có blast radius về capacity và cost. Repository chưa có HPA manifest/template; CPU requests, probes ổn định và controlled load-test evidence vẫn là prerequisite. |
| Business impact | HPA có thể bảo vệ SLO khi traffic tăng, nhưng nếu bật quá sớm có thể scale sai, đẩy thêm tải xuống PostgreSQL/Kafka/downstream hoặc làm tăng compute cost ngoài dự kiến. Vì vậy HPA chỉ nên áp dụng khi đã có resource baseline, probes và load-test evidence. |
| Hướng xử lý | Chỉ đánh giá HPA cho workload phù hợp, như `frontend` và `checkout`, sau khi resource request/limit đã được measured. Đặt min/max replica và scaling target dựa trên load-test evidence, không dùng số mặc định không có evidence. |
| Prerequisite | Mọi container được tính metric có CPU request; Prometheus/Grafana evidence ổn định; probes ổn định; controlled load test đạt mục tiêu. |
| Validation | So sánh p95/p99, error rate, restart/OOM, replica behavior và node headroom trong scale-out/scale-in test. |

### 5.2. Instance type, node count và `max_size`

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `K8S-03`, `COST-02` |
| Priority | P2 |
| Vì sao là P2 | EC2 worker nodes là cost driver lớn, nhưng thay đổi node capacity có thể gây latency, OOM hoặc giảm HA. Baseline hiện có là 2 x `t3.large` trên hai Availability Zones; không giảm xuống một node mặc định. |
| Business impact | Compute right-sizing có thể tiết kiệm cost, nhưng downsize sai có thể làm checkout success, browse latency hoặc observability reliability xấu đi. Giảm node count từ 2 xuống 1 còn làm giảm basic multi-AZ capacity và tăng rủi ro khi có node issue. |
| Hướng xử lý | Sau evidence window, đánh giá smaller instance type, giảm `max_size`, hoặc scheduled scale-down cho môi trường phù hợp. Chỉ chọn phương án có rollback và acceptance rõ ràng về capacity/HA. |
| Prerequisite | 48 đến 72 giờ evidence, node headroom healthy, không còn OOM/restart chưa giải quyết, controlled load test đạt target và có rollback test. |
| Validation | Đo latency, error rate, restart/OOM, node CPU/memory headroom và cost estimate trước/sau. |

### 5.3. ALB LCU và NAT data processing

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `COST-02` |
| Priority | P2 |
| Vì sao là P2 | Đây là usage-based cost. ALB hiện là public entry point cần thiết và NAT Gateway phục vụ outbound path. Chưa đủ Cost Explorer và usage evidence để khẳng định tối ưu nào sẽ tiết kiệm thực. |
| Business impact | ALB và NAT là thành phần cần thiết cho inbound/outbound path. Tối ưu sai có thể ảnh hưởng khả năng truy cập hệ thống hoặc làm outbound dependency thất bại. Cần Cost Explorer và usage metrics để tránh thay đổi kiến trúc chỉ dựa trên estimate. |
| Evidence hiện có | Hệ thống có một internet-facing ALB do EKS load balancer controller tạo từ ingress `techx-alb-ingress`. Quan sát `ConsumedLCUs` ngày 2026-07-09 thấp hơn nhiều so với scenario trung bình 1 LCU. Scenario 1 LCU chỉ là estimate, không phải observed baseline. |
| Hướng xử lý | Dùng Cost Explorer cùng ALB/NAT usage metric để xác định cost driver, traffic pattern và candidate optimization. Không suy luận internal Locust traffic là nguyên nhân trực tiếp làm tăng ALB LCU hoặc NAT data processing. |
| Prerequisite | Actual billing từ Cost Explorer và usage metrics trong time window đủ dài. |
| Validation | Có mapping giữa billing line item, usage metric, traffic path và expected saving trước khi thay đổi kiến trúc hoặc traffic flow. |

## 6. Trình tự thực hiện và dependency

| Thứ tự | Backlog item | Dependency | Kết quả mở khóa |
|---:|---|---|---|
| 1 | Tắt `LOCUST_AUTOSTART` | Không có | Baseline không bị synthetic traffic tự chạy. |
| 2 | Ổn định `accounting` OOM/restart | Không có | Measured right-sizing cho application. |
| 3 | Điều tra Jaeger/Grafana OOM/restart, không giảm memory | Không có; dùng kết quả bước 1 để correlation | Observability evidence đáng tin cậy hơn. |
| 4 | Thu evidence Prometheus/Grafana trong 48 đến 72 giờ | Bước 1 đến 3 | Resource plan, node review, retention và performance comparison. |
| 5 | Measured requests/limits, checkout retry/backoff, quota validation | Bước 2 và 4 | HPA evaluation và compute right-sizing. |
| 6 | CloudWatch retention, persistence decision, ECR lifecycle verification | Bước 4 và owner/AWS validation | Cost guardrail có thể kiểm chứng. |
| 7 | Cache currency conversion; bound search result | Baseline/trace/query evidence từ bước 4 | Performance improvement có before/after evidence. |
| 8 | HPA, node/instance review, ALB/NAT optimization | Các prerequisite P1 tương ứng | Scaling hoặc saving có rollback evidence. |

## 7. Evidence và quy trình đóng backlog item

### 7.1. Nguồn evidence chính

- `tf4-phase3-repo/docs/evidence/epic-03-performance-efficiency/03-bottleneck-analysis.md`
- `tf4-phase3-repo/docs/evidence/epic-03-performance-efficiency/04-runtime-performance-evidence.md`
- `tf4-phase3-repo/docs/evidence/epic-03-performance-efficiency/05-scaling-right-sizing-recommendation.md`
- `tf4-phase3-repo/docs/evidence/epic-03-performance-efficiency/06-performance-risk-backlog.md`
- `tf4-phase3-repo/docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- `tf4-phase3-repo/docs/evidence/epic-04-cost-optimization/05-right-sizing-cost-saving-recommendation.md`
- `tf4-phase3-repo/docs/evidence/epic-04-cost-optimization/06-cost-quick-wins.md`
- `tf4-phase3-repo/docs/evidence/epic-04-cost-optimization/presentation-script-performance-cost-week1.md`
- `docs/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST-CDO04.md`

### 7.2. Quy tắc đóng item

1. Lưu evidence trong đúng thư mục Performance hoặc Cost.
2. Ghi file/configuration đã thay đổi và validation đã chạy.
3. Ghi kết quả thực tế, bao gồm các metric trước/sau nếu thay đổi ảnh hưởng latency, error rate, CPU, memory hoặc cost.
4. Ghi rõ rollback result, giới hạn và rủi ro còn lại.
5. Chỉ đổi trạng thái sang hoàn tất khi toàn bộ điều kiện đóng của item đã có evidence.

## 8. Ghi chú về budget và cost baseline

Terraform AWS Budget guardrail hiện được xác nhận là `$300/month`. Một số tài liệu Week 1 có target `$300/week`; đó là planning-target/governance context, không phải deployed guardrail hiện tại.

Baseline fixed estimate là khoảng `$246.95/month`; scenario cộng trung bình 1 ALB LCU là khoảng `$252.79/month`. Đây đều là estimate. Scenario node group đạt 4 x `t3.large` khoảng `$368.42/month`, vượt guardrail `$300/month`. Mọi quyết định budget hoặc usage-cost phải được đối chiếu lại bằng Cost Explorer actual billing.
