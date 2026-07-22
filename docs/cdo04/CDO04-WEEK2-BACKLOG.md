# CDO-04 Week 2 Backlog: Performance Efficiency và Cost Optimization

## 1. Mục đích, phạm vi và trạng thái Week 2

Tài liệu này là backlog/tổng hợp thực thi Week 2 cho CDO-04, bám theo hai trụ CDO-04 phụ trách:

| Trụ | Finding / workstream Week 2 | Mục tiêu Week 2 |
|---|---|---|
| Performance Efficiency | `COST-01`, `K8S-03`, `COST-02`, `C0G-39` | Làm sạch baseline, ổn định workload runtime, bảo vệ observability và database trước khi tiếp tục load/performance decision. |
| Cost Optimization | `COST-01`, `COST-02`, `K8S-03`, `C0G-21` | Không tối ưu cost bằng cách cắt tài nguyên mù quáng; xây cost model, guardrail và trial plan dựa trên evidence. |
| Delivery / GitOps guardrail | GitOps, Argo CD, CI/CD | Chứng minh production deployment đi qua GitOps/CI-CD, không sửa live tùy tiện khi xử lý performance/cost. |

Week 2 không chỉ là danh sách việc cần làm. Đây là trạng thái chuyển từ Week 1 backlog sang bằng chứng runtime cụ thể: việc nào đã xử lý, kết quả ra sao, còn thiếu gì, và định làm gì tiếp theo.

### Evidence chính đã đọc

- `docs/evidence/epic-03-performance-efficiency/runtime/c0g-17/no-synthetic-traffic.md`
- `docs/evidence/epic-03-performance-efficiency/runtime/c0g-18/accounting-oomkilled-monitoring.md`
- `docs/evidence/epic-03-performance-efficiency/runtime/c0g-19/jaeger-grafana-oom.md`
- `docs/evidence/epic-03-performance-efficiency/runtime/c0g-39/postgresql-oomkilled-investigation.md`
- `docs/cdo04/C0G-21-EKS-WORKER-NODE-COST-ESTIMATE-PLAN.md`
- `docs/cdo04/baocao-gitops-cicd.md`
- `docs/cdo04/CDO04-BACKLOG.md`

## 2. Week 2 status snapshot

| Work item | Finding liên quan | Trụ | Trạng thái Week 2 | Kết quả ngắn gọn |
|---|---|---|---|---|
| `C0G-17` No synthetic traffic baseline | `COST-01` | Performance + Cost | Runtime verification passed | `LOCUST_AUTOSTART=false`, Locust idle, Grafana/Jaeger không có load-generator traffic trong bounded window. |
| `C0G-18` Accounting OOMKilled monitoring | `K8S-03` | Performance | Đã tăng resource, đang theo dõi 24h | `accounting` chạy acceptance 200-user/15 phút không OOM/restart; vẫn cần trend 24h để loại leak. |
| `C0G-19` Jaeger/Grafana OOM | `COST-02` | Performance + Cost | Completed & Implemented | Tăng resource, chuyển Jaeger sang OpenSearch persistent backend, bật index cleaner 3 ngày. |
| `C0G-39` PostgreSQL OOMKilled investigation | `K8S-03`, `COST-02` | Performance + Cost | Đã điều tra, đề xuất chờ áp dụng | OOM không tái hiện trong acceptance run; khả năng cao là victim cùng node với Jaeger; đề xuất anti-affinity + resource guardrail + PVC dài hạn. |
| `C0G-21` Worker node cost estimate plan | `K8S-03`, `COST-02` | Cost | Estimate/trial plan hoàn tất | Có model cho `t3.large`, `t3a.large`, `t4g.large`, `t3.medium`; `t3.medium` NO-GO; `t3a.large` là first controlled-trial candidate. |
| GitOps/CI-CD report | Delivery guardrail | Performance + Cost | Implementation state documented | Xác nhận two-repo GitOps, CI build/promotion, Argo CD ordered waves, Terraform/GitOps source-of-truth boundary. |

## 3. Business context theo finding Week 2

| Finding / workstream | Business impact |
|---|---|
| `COST-01` / `C0G-17` | Nếu load-generator tự chạy, mọi metric baseline, cost per request, latency và trace volume đều bị nhiễu. Week 2 đã chứng minh baseline không còn synthetic traffic tự phát, giúp các quyết định cost/performance đáng tin hơn. |
| `K8S-03` / `C0G-18` | `accounting` là consumer hậu kỳ của order event. Nếu tiếp tục OOM/restart, dữ liệu accounting/audit/fraud-related processing có thể bị delay hoặc không đáng tin. Tăng resource chỉ là bước ổn định; cần trend 24h để phân biệt thiếu đệm với memory leak. |
| `COST-02` / `C0G-19` | Observability mất ổn định thì team mất trace/dashboard đúng lúc cần chứng minh SLO, điều tra incident và bảo vệ rollback. Chuyển Jaeger khỏi in-memory sang OpenSearch persistent storage vừa tăng reliability vừa kiểm soát retention/cost. |
| `C0G-39` PostgreSQL | PostgreSQL OOM có thể làm mất schema `accounting` vì chưa có PVC. Dù OOM không tái hiện trong acceptance run, risk data durability vẫn cần backlog sớm vì chi phí PVC nhỏ hơn rất nhiều so với rủi ro mất dữ liệu. |
| `C0G-21` Worker node cost | EC2 worker nodes là cost driver lớn. Nếu đổi instance hoặc giảm node quá sớm, hệ thống có thể mất capacity/HA; nếu không có model, team không biết option nào thực sự tiết kiệm. |
| GitOps/CI-CD | Trong production, sửa live bằng tay dễ tạo drift và làm evidence mất giá trị. Week 2 cần chứng minh các thay đổi performance/cost đi qua GitOps, CI, promotion PR và Argo CD. |

## 4. Đã xử lý trong Week 2

### 4.1. `C0G-17`: Baseline EKS không còn automatic Locust traffic

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `COST-01` |
| Priority từ backlog gốc | P0 |
| Đã xử lý | Áp dụng `LOCUST_AUTOSTART=false` qua `deploy/values-app-stamp.yaml`; giữ `load-generator` deployed nhưng không tự swarm sau rollout. |
| Evidence cấu hình | Helm revision `14`; image tag `06c7031-load-generator`; runtime artifact ghi `locustAutostart="false"`; generation `7`, observedGeneration `7`, ready/available replicas `1`. |
| Evidence runtime | Window `2026-07-12T18:19:31Z` → `2026-07-12T18:29:32Z`: Locust UI `ready`, `user_count=0`; Grafana five-minute rate `0/0`; ten-minute increment `0/0`; Jaeger `0 traces / 0 spans` cho service `load-generator`. |
| Kết quả | Runtime verification passed. Baseline không còn synthetic traffic tự phát trong bounded window. |
| Vì sao quan trọng | Cho phép các metric latency, request rate, trace volume và cost estimate sau đó phản ánh workload thật hoặc controlled test, không bị Locust tự chạy làm nhiễu. |
| Evidence path | `docs/evidence/epic-03-performance-efficiency/runtime/c0g-17/no-synthetic-traffic.md` |

### 4.2. `C0G-18`: Ổn định và theo dõi `accounting` OOMKilled

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `K8S-03` |
| Priority từ backlog gốc | P0 |
| Sự cố ban đầu | Pod `accounting` từng `CrashLoopBackOff` do `OOMKilled`, exit code `137`; restart count từng được ghi nhận `89`, sau đó `41` trong khoảng đầu vòng đời pod. Cấu hình cũ chỉ có `limits.memory: 120Mi`. |
| Root-cause hypotheses | Nghi vấn `DBContext` sống lâu không clear tracker; burst catch-up do `AutoOffsetReset.Earliest`; .NET + OTel overhead; thiếu request memory tường minh. |
| Đã xử lý | Tăng memory cho `accounting` lên `256Mi`; runtime pod mới `accounting-55d8fcbb67-n7zmd` có restart count `0`, limit/request memory `256Mi`, QoS `Burstable`. |
| Kết quả acceptance | Đã chạy 2 lần Directive #2, 200 users / ramp-up 20 / 15 phút; `accounting` không restart, không OOM trong suốt bài test. |
| Chưa đóng hoàn toàn vì | Nếu root cause là leak chậm, tăng RAM có thể chỉ trì hoãn OOM. Cần trend Prometheus tối thiểu 24h để xác nhận memory phẳng. |
| Việc tiếp theo | Theo dõi `container_memory_working_set_bytes`, % so với limit, `deriv(...)`, `predict_linear(...)`, và restart delta. Nếu trend vẫn leo, mở follow-up sửa `Consumer.cs` với `ChangeTracker.Clear()` sau `SaveChanges()`. |
| Evidence path | `docs/evidence/epic-03-performance-efficiency/runtime/c0g-18/accounting-oomkilled-monitoring.md` |

### 4.3. `C0G-19`: Jaeger/Grafana OOM và persistent observability backend

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `COST-02` |
| Priority từ backlog gốc | P0/P1 |
| Sự cố ban đầu | Jaeger restart 16 lần trong 3h54 do `OOMKilled`, RAM peak ~`762Mi`; Grafana restart 5 lần do vượt memory limit `300Mi`, peak `500Mi+`. |
| Nguyên nhân chính | Jaeger dùng `storage.type=memory`, `MEMORY_MAX_TRACES=25000`; bài test 200 users/15 phút sinh khoảng `36,540 traces`, span rate `1,200-1,600 spans/s`, làm in-memory trace storage không bền. |
| Đã xử lý | Grafana tăng lên `requests: 512Mi` / `limits: 768Mi`; Jaeger tăng lên `requests: 768Mi` / `limits: 768Mi`; Jaeger chuyển từ memory backend sang OpenSearch/elasticsearch backend; OpenSearch bật PVC `8Gi`. |
| Cost guardrail | Bật `esIndexCleaner` xóa trace cũ hơn 3 ngày, tránh OpenSearch PVC tăng không kiểm soát. |
| Kết quả | Completed & Implemented; trace được lưu xuống OpenSearch persistent storage, survive khi Jaeger restart; observability không còn chỉ phụ thuộc RAM. |
| Phối hợp liên nhóm | CDO-08 triển khai persistent backend; CDO-07 thẩm định trace tồn tại, redaction/audit; CDO-04 điều tra OOM, trace volume và cost impact. |
| Evidence path | `docs/evidence/epic-03-performance-efficiency/runtime/c0g-19/jaeger-grafana-oom.md` |

### 4.4. `C0G-39`: PostgreSQL OOMKilled investigation

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `K8S-03`, `COST-02` |
| Priority Week 2 | P1, vì đã tự phục hồi và không tái hiện trong acceptance run, nhưng data durability risk còn đáng chú ý. |
| Quan sát | `postgresql` chạy ổn định 4 ngày rồi OOMKilled 1 lần, tự phục hồi. Cấu hình hiện tại chỉ có `limits.memory: 100Mi`, không có request/PVC. |
| Đối chiếu tải thật | Acceptance run 200 users / ramp-up 20 / 15 phút trên config cũ `100Mi` không tái hiện OOM, nên chưa chứng minh PostgreSQL thiếu compute per-se. |
| Đối chiếu vị trí | PostgreSQL cùng node với Jaeger (`ip-10-0-11-40`), trong khi Jaeger đang crash-loop và peak `762Mi`; hai OOM gần nhất cách nhau khoảng 7 phút. |
| Phát hiện | Root cause khả dĩ nhất: PostgreSQL là victim cùng node của Jaeger, không phải PostgreSQL tự thiếu compute. |
| Đề xuất ưu tiên 1 | Thêm `podAntiAffinity` để PostgreSQL không schedule cùng node với Jaeger. Đây là fix cost $0, đúng hướng cost-efficient. |
| Đề xuất ưu tiên 2 | Tăng resource phòng ngừa: request `192Mi`, limit `384Mi`, và tune Postgres `shared_buffers=96MB`, `max_connections=50`, `work_mem=4MB`. |
| Dài hạn | PVC/StatefulSet cho PostgreSQL theo ADR-004, ước tính ~$8-16/tuần, vì restart hiện có thể mất schema `accounting`. |
| Evidence path | `docs/evidence/epic-03-performance-efficiency/runtime/c0g-39/postgresql-oomkilled-investigation.md` |

### 4.5. `C0G-21`: EKS worker node cost estimate và Karpenter plan

| Hạng mục | Nội dung |
|---|---|
| Finding liên quan | `K8S-03`, `COST-02` |
| Priority từ backlog gốc | P2 có điều kiện, nhưng Week 2 đã hoàn tất estimate/trial plan. |
| Current baseline | Managed Node Group `techx-general-ng`, `t3.large`, On-Demand, `min=2`, `desired=2`, `max=4`, 20GiB gp3/node; Karpenter NodePool `techx-general`, AMD64 Linux On-Demand, chỉ `t3.large`/`t3a.large`, `limits.cpu=16`. |
| Budget blocker | Onboarding mandate khoảng `$300/week/TF`; Terraform AWS Budget là `$300/month`. Cần chốt guardrail áp dụng trước controlled trial. |
| Known all-in baseline | Current known subtotal khoảng `$237.47/month`, chưa gồm Karpenter actual node-hours/root volumes, ALB/NLB/LCU, CloudWatch, transfer, ECR, NAT data processing và chi phí khác. |
| Option comparison | `2 × t3.large`: `$121.47/month` EC2; `2 × t3a.large`: `$109.79/month` (-9.6%); `2 × t4g.large`: `$98.11/month` (-19.2%); `2 × t3.medium`: `$60.74/month` nhưng NO-GO do CPU/memory headroom. |
| Karpenter runtime evidence | Karpenter đã provision `t3a.large` để xử lý `Insufficient cpu`; observed full worker cost khoảng `$0.0773918/hour`; đã thấy consolidation 4→3 workers. |
| Recommendation | Không trial `t3.medium`; không giảm `max_size` chỉ để tiết kiệm; first controlled trial candidate là `t3.large` → `t3a.large`; `t4g.large` là phase 2 sau ARM64 validation. |
| Chưa làm | Chưa đổi instance type/node count/Karpenter limit; controlled trial bị blocked đến khi budget guardrail, Cost Explorer và live evidence đủ. |
| Evidence path | `docs/cdo04/C0G-21-EKS-WORKER-NODE-COST-ESTIMATE-PLAN.md` |

### 4.6. GitOps, Argo CD và CI/CD guardrail

| Hạng mục | Nội dung |
|---|---|
| Workstream liên quan | Delivery guardrail cho performance/cost change |
| Đã xử lý | Ghi nhận implementation thực tế của two-repository GitOps: `tf4-phase3-repo` build/chart/Terraform, `tf4-phase3-gitops-manifests` production desired state. |
| CI evidence | PR chỉ validation; build-and-push build image, push ECR, verify digest, mở GitOps promotion PR; không direct deploy production. |
| GitOps evidence | GitOps repo validate chart-at-pinned-SHA, image revisions, duplicate resources, plaintext credential, PVC/PV/Service/Namespace/CRD deletion rules. |
| Argo CD evidence | Ordered waves: ESO, platform secrets, raw resources, observability, application. `prune=false`, `selfHeal=true`, `FailOnSharedResource=true`, `ApplyOutOfSyncOnly=true`. |
| Vì sao quan trọng | Các thay đổi resource/cost/performance không nên sửa live bằng `kubectl set env` hoặc patch tay, vì sẽ tạo Helm/Argo drift và làm evidence khó bảo vệ. |
| Evidence path | `docs/cdo04/baocao-gitops-cicd.md` |

## 5. Chưa làm / còn mở sau Week 2

| Item | Trạng thái | Vì sao chưa đóng | Việc định làm |
|---|---|---|---|
| `C0G-18` accounting 24h trend | Open | Acceptance run 15 phút chưa đủ để loại memory leak chậm. | Thu Prometheus trend ≥24h; nếu slope leo, mở code fix `Consumer.cs`. |
| PostgreSQL anti-affinity | Proposed | Đã có root-cause khả dĩ, nhưng chưa thấy evidence đã apply. | Apply qua GitOps PR: anti-affinity PostgreSQL vs Jaeger; validate placement. |
| PostgreSQL resource/PVC | Proposed | Resource tăng là phòng ngừa; PVC/StatefulSet cần CDO-08/data durability alignment. | Chốt phương án request/limit và ADR-004 PVC/StatefulSet. |
| Cost Explorer reconciliation | Pending | C0G-21 hiện là estimate, không phải actual billing. | Chờ Cost Explorer 24-48h và tách EC2/EBS/Karpenter/NAT/LB/logging/transfer. |
| Budget guardrail | Blocker | `$300/week` và `$300/month` chưa thống nhất. | Xác nhận guardrail chính thức, cập nhật Terraform Budget hoặc tài liệu governance. |
| Controlled trial `t3.large` → `t3a.large` | Blocked | Cần budget, runtime evidence, smoke/load test, rollback window. | Làm Terraform change cô lập sau khi entry gates pass. |
| ARM64 `t4g.large` phase 2 | Future | Cần verify toàn bộ image/platform dependency có `linux/arm64`. | Inspect image manifests; chỉ trial sau `t3a.large` hoặc khi ARM64 evidence pass. |
| Performance backlog `PERF-01` currency cache | Chưa thấy Week 2 implementation trong các evidence được cung cấp | Week 2 tập trung runtime reliability/cost guardrail. | Tiếp tục cache exchange rate và đo fan-out/browse p95 trước/sau. |
| Performance backlog `PERF-02` bounded search | Chưa thấy Week 2 implementation trong các evidence được cung cấp | Chưa có query plan/runtime evidence mới trong file đã đọc. | Thêm `LIMIT`/pagination, chạy `EXPLAIN ANALYZE`, đo search p95/p99. |

## 6. Week 2 priority backlog

### 6.1. P0: Hoàn tất các guardrail đang bảo vệ baseline

| Backlog item | Owner/source | Trạng thái | Điều kiện đóng |
|---|---|---|---|
| Baseline không synthetic traffic | `C0G-17` | Done | Giữ `LOCUST_AUTOSTART=false` qua GitOps; mỗi load test phải có approved T0/T1 và Locust UI action. |
| Observability persistent backend | `C0G-19` | Done | Jaeger/Grafana healthy, OpenSearch PVC và index cleaner hoạt động, trace tồn tại sau run. |
| Accounting resource stabilization | `C0G-18` | In progress | Memory trend ≥24h phẳng, restart count không tăng, acceptance/load run không OOM. |

### 6.2. P1: Đóng các evidence còn thiếu để quyết định resource/cost

| Backlog item | Evidence hiện có | Việc tiếp theo |
|---|---|---|
| PostgreSQL anti-affinity | `C0G-39` đã đề xuất fix cost $0 | Tạo GitOps PR, validate PostgreSQL không colocate với Jaeger. |
| PostgreSQL durability | `C0G-39` ghi risk không PVC | Chốt PVC/StatefulSet với CDO-08; estimate $8-16/tuần; cập nhật ADR-004 evidence. |
| Cost Explorer | `C0G-21` có estimate | Lấy actual billing theo service/usage type, node-hours, Karpenter root volume, NAT/LB/logging/transfer. |
| Budget guardrail | `C0G-21` ghi conflict | Xác nhận `$300/month` hay `$300/week`; đồng bộ Terraform Budget và mandate wording. |
| GitOps source-of-truth | `baocao-gitops-cicd.md` | Áp dụng mọi resource/cost change qua GitOps PR, tránh live drift. |

### 6.3. P2: Tối ưu có điều kiện sau khi gates pass

| Backlog item | Điều kiện bắt đầu | Validation |
|---|---|---|
| Controlled trial `t3.large` → `t3a.large` | Budget confirmed, C0G-18 stable, observability healthy, T0 captured, smoke test pass | So sánh p95, checkout success, restart/OOM, Pending pod, CPU credits, node-hours, cost per request trước/sau 48-72h. |
| ARM64 `t4g.large` trial | Toàn bộ workload/addon/observability/stateful dependency verified `linux/arm64` | Không có `exec format error`, SLO pass, cost benefit khớp estimate. |
| Karpenter `limits.cpu` tuning | Có NodeClaim/node-hour/load evidence đủ dài | Không làm pod Pending, không giảm replacement buffer dưới mức cần thiết. |
| `PERF-01` currency cache | Có browse baseline/trace trước thay đổi | Fan-out currency giảm, browse p95/error không regress. |
| `PERF-02` bounded search | Có query plan/search runtime baseline | Query có `LIMIT`/pagination, DB pressure/search p95 không regress. |

## 7. Trình tự thực hiện đề xuất sau Week 2

| Thứ tự | Việc | Dependency | Output mong đợi |
|---:|---|---|---|
| 1 | Đóng C0G-18 bằng 24h memory/restart trend | Resource đã tăng `256Mi` | Accounting stable evidence hoặc code follow-up. |
| 2 | Apply PostgreSQL anti-affinity với Jaeger | GitOps PR, Argo sync | PostgreSQL placement không còn cùng node với Jaeger. |
| 3 | Chốt PostgreSQL resource/PVC decision | CDO-08/data durability alignment | Giảm risk mất `accounting` schema sau restart. |
| 4 | Reconcile Cost Explorer và Karpenter node-hours | Billing data đủ 24-48h | Actual/estimated cost table rõ ràng. |
| 5 | Chốt budget guardrail | Owner/finance/platform sign-off | Không còn conflict `$300/week` vs `$300/month`. |
| 6 | Chuẩn bị controlled trial `t3a.large` | Bước 1-5 pass | Terraform plan cô lập, rollback plan, T0 evidence. |
| 7 | Tiếp tục PERF-01/PERF-02 | Runtime baseline đã sạch | Performance improvements có before/after evidence. |

## 8. Quy tắc đóng item Week 2

1. Mọi thay đổi resource/cost phải có evidence path, owner, timestamp và source-of-truth rõ ràng.
2. Không dùng estimate thay actual billing khi kết luận cost saving; Cost Explorer/CUR là nguồn final.
3. Không đổi instance type, node count, Karpenter limit, workload requests và observability config trong cùng một trial.
4. Không sửa live bằng `kubectl set env` hoặc patch tay nếu thay đổi thuộc desired state; dùng GitOps PR hoặc emergency flow có record.
5. Với workload từng OOM/restart, cần trend theo thời gian, không đóng item chỉ bằng một snapshot không restart.
6. Với PostgreSQL, xử lý placement/durability trước khi gọi database runtime risk là đã đóng.
7. Với performance optimization, phải có before/after latency, error rate, CPU/memory hoặc query plan.

## 9. Kết luận Week 2

Week 2 đã xử lý được các blocker quan trọng nhất của CDO-04:

- baseline không còn synthetic Locust traffic tự phát;
- `accounting` đã được tăng resource và pass acceptance run ngắn;
- Jaeger/Grafana đã được right-size và Jaeger chuyển sang persistent OpenSearch backend;
- PostgreSQL OOM đã được điều tra theo tải thật, placement và correlation với Jaeger;
- worker node cost model và Karpenter roadmap đã có estimate/trial plan;
- GitOps/CI-CD source-of-truth đã được ghi nhận để tránh drift khi thay đổi production.

Các việc còn mở chủ yếu là đóng evidence dài hơn và chuyển đề xuất thành GitOps-controlled change: accounting 24h trend, PostgreSQL anti-affinity/PVC, Cost Explorer reconciliation, budget guardrail và controlled trial `t3a.large`.
