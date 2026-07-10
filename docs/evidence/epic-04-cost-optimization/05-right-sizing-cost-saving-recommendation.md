# COST-05: Right-sizing & Cost Saving Recommendation

Capture date: 2026-07-09

## 1. Mục tiêu

Tài liệu này tổng hợp các recommendation cho COST-05 dựa trên:

- `docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md`
- `docs/evidence/epic-04-cost-optimization/06-cost-quick-wins.md`
- `docs/evidence/epic-03-performance-efficiency/04-runtime-performance-evidence.md`
- `docs/evidence/epic-03-performance-efficiency/runtime/`

Nguyên tắc chính: chỉ đề xuất tiết kiệm chi phí khi có bằng chứng đủ rõ ràng về cost driver, runtime health và khả năng rollback. Không giảm CPU/memory limit của workload chỉ dựa trên cảm tính hoặc snapshot ngắn, đặc biệt khi runtime đang có dấu hiệu restart/OOM.

---

## 2. Tổng hợp input evidence

### 2.1. COST-01 — Baseline cost

Baseline hiện tại:

| Hạng mục | Finding | Ý nghĩa với COST-05 |
|---|---|---|
| EKS cluster | `techx-tf4-cluster`, ACTIVE | Fixed control plane cost |
| Node group | `techx-general-ng-20260707091432750200000017` | Main compute cost driver |
| Instance type | `t3.large` | Chỉ nên right-size sau khi CPU/memory evidence ổn định |
| Scaling config | min=2, desired=2, max=4 | Chi phí hiện tại dựa trên 2 nodes; max=4 là cost risk |
| Worker nodes | 2 nodes across `us-east-1a` and `us-east-1b` | Duy trì basic multi-AZ placement |
| NAT Gateway | 1 NAT Gateway | Fixed cost driver đã được tối ưu theo hướng Single NAT cho Week 1 |
| ALB | 1 internet-facing ALB | Entry point cần thiết; có hourly cost và LCU cost |
| EBS | 2 x 20 GiB gp3 root volumes, total 40 GiB | Storage cost cố định ở mức thấp/trung bình |
| ECR | 1 repo `techx-corp` | Cần lifecycle cleanup nếu số lượng image tăng |
| CloudWatch Logs | 8 log groups, một số group chưa set retention | Cost risk nếu log ingestion/storage tăng |
| PVC | Không có PVC trong `techx-tf4` | Chi phí PVC hiện tại thấp, nhưng có persistence risk cho stateful workload |

Current estimate:

| Scenario | Monthly estimate | Weekly estimate | Budget comparison |
|---|---:|---:|---|
| Fixed baseline current | `$246.95/month` | `$56.83/week` | Below `$300/week` |
| Fixed baseline + average 1 ALB LCU | `$252.79/month` | `$58.18/week` | Below `$300/week` |
| Node group max scenario, 4 x `t3.large` | `$368.42/month` | `$84.79/week` | Still below `$300/week`, but compute nearly doubles |

Kết luận từ COST-01:

- Baseline hiện tại vẫn nằm dưới budget `$300/week`.
- Cost driver cố định lớn nhất có thể kiểm soát là EC2 worker nodes.
- NAT Gateway và ALB là fixed cost đáng chú ý, nhưng hiện tại đều gắn với quyết định kiến trúc cần thiết.
- Cost risk quan trọng nhất hiện tại không phải là overspend ngay lập tức, mà là uncontrolled runtime behavior có thể làm tăng compute, logs, traces, NAT data processing, ALB LCU và future node scaling.

### 2.2. COST-06 — Quick wins

Key findings:

| Area | Evidence | COST-05 decision |
|---|---|---|
| Load Generator | `LOCUST_AUTOSTART=true`, `load-generator` enabled, memory limit khoảng `1500Mi` | Disable autostart; chỉ chạy khi có controlled test |
| Jaeger | Existing evidence cho thấy Jaeger từng bị `OOMKilled` ở current limit | Không giảm Jaeger memory; điều tra hoặc tăng nếu OOM tiếp tục |
| Prometheus | Chưa đủ long-window runtime evidence để giảm limit an toàn | Không giảm trong Week 1 |
| OpenSearch | Chưa đủ long-window runtime evidence để giảm limit an toàn | Không giảm trong Week 1 |
| Grafana | COST-06 đang conservative; PERF runtime evidence sau đó cho thấy memory/restart risk | Không giảm; đánh giá tăng dựa trên OOM/restart evidence |

Kết luận từ COST-06:

- Quick win tốt nhất có thể làm ngay là operational quick win: disable load-generator autostart.
- Observability stack không nên được xem là mục tiêu cắt giảm chi phí nhanh.
- Memory pressure của Jaeger/Grafana cho thấy việc giảm memory quá mạnh sẽ làm tăng reliability risk và có thể làm xấu đi performance evidence.

### 2.3. PERF-04 — Runtime performance evidence

Runtime findings từ `runtime/` evidence:

| Evidence | Finding | COST-05 implication |
|---|---|---|
| `runtime/kubectl/deployments-2026-07-09.md` | 22 application deployments are `READY 1/1` | Baseline app deployable và available |
| `runtime/kubectl/pods-wide-2026-07-09.md` | All app pods are `Running`; `accounting` có 31 restarts, `checkout` có 4, `load-generator` có 1 | Không giảm resource một cách mù quáng; cần điều tra các pod có restart cao trước |
| `runtime/kubectl/nodes-zones-2026-07-09.md` | 2 ready nodes across `us-east-1a` and `us-east-1b` | Không giảm node count xuống dưới 2 nếu chưa chấp nhận lower HA |
| Grafana/Prometheus resource dashboards | CPU-memory trend được lấy từ Prometheus/Grafana thay vì lệnh Kubernetes resource snapshot | Node/pod right-sizing cần dựa trên 48-72h metrics window, không dựa vào một snapshot ngắn |
| `runtime/kubectl/warning-events-2026-07-09.md` | `accounting` BackOff warning; Grafana previous readiness warning | Đang có runtime stability issues trước khi cost cuts |
| `runtime/grafana/grafana-resource-evidence-2026-07-09.md` | Grafana main container had `OOMKilled`, exit code 137, restart count 7, memory request/limit 300Mi | Không giảm Grafana; tăng lên 512Mi/768Mi là reliability fix |
| `04-runtime-performance-evidence.md` | Grafana/APM traces exist; checkout/payment/product-catalog và các service khác có trace coverage | Dùng traces này để bảo vệ performance trong quá trình tối ưu cost |

Known gaps:

- Prometheus/Grafana là source metrics chính cho CPU/RAM, nhưng vẫn cần một cửa sổ quan sát 48-72 giờ trước khi right-sizing.
- Kafka runtime metrics chưa đủ hoàn chỉnh để tuning cost/performance.
- Jaeger self-metrics cần follow-up, đặc biệt vì đã quan sát được OOMKilled.
- Grafana memory/restart risk đã được xác nhận; tránh mọi đề xuất giảm memory cho Grafana.
- Vẫn cần Cost Explorer actual billing data để validate estimate so với daily/weekly burn rate thực tế.

---

## 3. Recommendation summary

| Priority | Recommendation | Decision | Expected impact | Risk |
|---|---|---|---|---|
| P0 | Disable `load-generator` autostart | Do now | Giảm synthetic traffic, log/trace noise và indirect resource pressure | Low |
| P0 | Không giảm Jaeger/Grafana memory | Do now | Bảo vệ observability reliability | Low |
| P0 | Điều tra các pod có restart cao trước khi right-sizing | Do now | Tránh cost changes che khuất reliability bugs | Medium |
| P1 | Chuẩn hóa Prometheus/Grafana CPU-memory dashboards và PromQL queries | Do next | Cho phép resource/node right-sizing dựa trên evidence | Low |
| P1 | Set CloudWatch log retention cho non-critical log groups | Do next | Ngăn log storage cost tăng không kiểm soát | Low |
| P1 | Thêm ECR lifecycle policy | Do next | Ngăn image storage tăng không kiểm soát | Low |
| P2 | Review node group size/type sau 48–72h metrics | Conditional | Có khả năng tiết kiệm EC2 nếu workload underutilized | Medium/High |
| P2 | Review ALB/NAT data processing sau khi có Cost Explorer data | Conditional | Giảm usage-based cost nếu traffic pattern phù hợp | Medium |

---

## 4. Recommended actions

### 4.1. Action 1 — Disable load-generator autostart

Decision: implement.

Rationale:

- `load-generator` hữu ích cho controlled performance tests, nhưng không nên liên tục tạo synthetic traffic.
- Synthetic traffic liên tục có thể làm tăng application CPU, memory, traces, logs, ALB LCU, NAT data processing và observability workload pressure.
- Nó cũng làm nhiễu SLO/SLI dashboards và khiến performance/cost analysis kém tin cậy hơn.

Recommended config change:

```text
LOCUST_AUTOSTART=true -> LOCUST_AUTOSTART=false
```

Scope:

- Helm/chart value nếu deployment dùng chart-controlled env.
- `.env` value nếu local/docker-compose path vẫn được team sử dụng.

Expected saving:

- Direct AWS bill reduction có thể chưa xuất hiện ngay vì node group vẫn giữ 2 x `t3.large`.
- Indirect saving có giá trị cao: giảm trace/log noise, giảm artificial requests, giảm pressure lên Jaeger/Grafana/Prometheus/OpenSearch và giảm khả năng scale-up không cần thiết lên max nodes.

Validation:

- Confirm `load-generator` không tự động start traffic sau khi redeploy.
- Confirm Grafana request rate giảm về real-user/test-only traffic.
- Confirm Jaeger trace volume không bị Locust đẩy liên tục.
- Confirm không có application flow nào phụ thuộc vào việc load-generator chạy 24/7.

Rollback:

```text
LOCUST_AUTOSTART=false -> LOCUST_AUTOSTART=true
```

Chỉ rollback khi có planned load test cần bật lại.

### 4.2. Action 2 — Keep current 2-node baseline for Week 1

Decision: giữ `min=2`, `desired=2` trong giai đoạn hiện tại.

Rationale:

- Current 2-node layout cung cấp basic spread across `us-east-1a` và `us-east-1b`.
- Runtime evidence cho thấy tất cả pods đang Running, nhưng vẫn có restarts và warning events.
- Cần thêm 48-72 giờ CPU/memory trend từ Prometheus/Grafana trước khi chuyển sang smaller instances hoặc fewer nodes một cách an toàn.
- Observability components đang có memory risk, nên giảm node capacity lúc này sẽ làm tăng operational risk.

Do not do now:

- Không giảm xuống 1 node trừ khi team chấp nhận rõ ràng đây là non-HA cost-saving mode.
- Không chuyển từ `t3.large` sang `t3.medium` cho đến khi pod memory usage, node memory headroom và restart/OOM patterns được đo trong ít nhất 48–72 giờ.
- Không tăng `maxSize` vượt 4 nếu chưa có budget approval.

Conditional future option:

| Option | Estimated EC2 impact | Conditions before applying |
|---|---:|---|
| 2 x `t3.large` -> 2 x smaller instance type | Có thể giảm EC2 cost đáng kể | Cần stable CPU/memory headroom, không có OOM, không tăng restart |
| `maxSize=4` -> `maxSize=3` | Giới hạn scale-out cost risk | Chỉ thực hiện nếu load test xác nhận 3 nodes chịu được peak |
| Scheduled scale-down | Tiết kiệm compute ngoài business hours | Chỉ phù hợp nếu đây là non-production hoặc team chấp nhận downtime/lower capacity |

### 4.3. Action 3 — Do not cut observability memory limits yet

Decision: không giảm Jaeger, Prometheus, OpenSearch hoặc Grafana limits trong COST-05 cycle này.

Rationale:

- COST-06 đã flag Jaeger OOMKilled risk.
- PERF runtime evidence xác nhận Grafana từng bị `OOMKilled`, exit code 137 và restart count 7 ở mức 300Mi.
- Memory usage trend và peak data cần được chốt lại bằng Prometheus/Grafana trong cửa sổ 48-72 giờ.
- Observability stack cần thiết để tạo performance evidence cho PERF-04 và các right-sizing work sau này.

Specific decisions:

| Component | Current direction | Reason |
|---|---|---|
| Jaeger | Không giảm; điều tra OOM; cân nhắc tăng nếu OOM lặp lại | Đã có OOMKilled evidence |
| Grafana | Không giảm; cân nhắc tăng request/limit lên 512Mi/768Mi | OOMKilled, exit 137, restart count 7 |
| Prometheus | Giữ current limit cho đến khi có 48–72h metrics | Chưa có safe reduction evidence |
| OpenSearch | Giữ current limit cho đến khi có storage/memory/index evidence | Stateful/search workload, chưa có safe reduction evidence |

Grafana reliability recommendation from PERF-04:

```yaml
grafana:
  resources:
    requests:
      memory: 512Mi
    limits:
      memory: 768Mi
```

Cost note:

- Tăng Grafana memory tự nó không phải là cost saving.
- Tuy nhiên, đây vẫn là một cost optimization decision vì observability ổn định giúp tránh right-sizing sai và tránh repeated restarts làm méo metrics/traces.

### 4.4. Action 4 — Chuẩn hóa metrics evidence path trước khi compute right-sizing

Decision: cần hoàn thành trước khi EC2/node right-sizing.

Required evidence:

- Prometheus/Grafana pod CPU và memory trong 48-72 giờ.
- Node CPU/memory dashboard hoặc PromQL tương đương cho cùng cửa sổ đo.
- Restart count và OOMKilled history của app pods và observability pods.
- Load-test window với `load-generator` được bật thủ công rồi tắt lại sau test.

Acceptance criteria before changing node size/type:

- Không có OOMKilled event mới cho Jaeger/Grafana.
- `accounting` BackOff/restart issue đã được giải thích hoặc fix.
- Node memory headroom vẫn healthy trong baseline và controlled load test.
- Checkout/payment/product-catalog traces vẫn nằm trong performance targets sau bất kỳ resource change nào.

### 4.5. Action 5 — Add CloudWatch log retention

Decision: implement cho non-critical log groups sau khi owner confirm.

Rationale:

- COST-01 ghi nhận có 8 log groups và một số group chưa set retention.
- Current stored bytes còn thấp, nhưng log storage cost có thể tăng theo thời gian.
- Đây là cost guardrail ít rủi ro hơn so với việc cắt runtime memory.

Recommended policy:

| Log type | Suggested retention |
|---|---:|
| Temporary/test logs | 1–7 days |
| Application troubleshooting logs | 14–30 days |
| Audit/security-required logs | Follow compliance requirement |
| EKS control plane logs | Giữ current policy trừ khi owner approve change |

Validation:

- Confirm retention chỉ được set cho approved log groups.
- Verify không rút ngắn nhầm các log cần cho audit.

### 4.6. Action 6 — Add ECR lifecycle cleanup

Decision: implement sau khi confirm image promotion policy.

Rationale:

- ECR storage hiện chưa phải main cost driver, nhưng có thể tăng âm thầm khi build image tích lũy.
- Lifecycle policy có rủi ro thấp nếu release tags được bảo vệ.

Recommended policy:

- Giữ toàn bộ protected release tags.
- Giữ latest N development images theo branch/environment.
- Expire untagged images sau một short retention window.

Validation:

- Confirm rollback image tags được giữ lại.
- Confirm production release tags không match cleanup rule.

---

## 5. Do-not-do list

Các thay đổi dưới đây không được khuyến nghị trong cycle này:

| Change | Reason |
|---|---|
| Reduce Jaeger memory | Jaeger có OOMKilled evidence |
| Reduce Grafana memory | Grafana có OOMKilled, exit 137 và restart count 7 |
| Reduce Prometheus/OpenSearch memory without long-window runtime metrics | Chưa có đủ evidence |
| Downsize from `t3.large` immediately | Chưa có đủ 48-72h Prometheus/Grafana trend và runtime restarts vẫn tồn tại |
| Scale node group min/desired from 2 to 1 by default | Sẽ làm giảm HA và có thể overload remaining node |
| Remove NAT Gateway | Private subnet outbound traffic đang phụ thuộc NAT; cần architecture change |
| Remove ALB | ALB là public entry point cho Webstore/Grafana/Jaeger routes |
| Treat current estimate as actual billing | Vẫn cần Cost Explorer actual data |

---

## 6. Cost impact model

### 6.1. Immediate expected impact

| Action | Direct AWS bill impact | Indirect impact | Confidence |
|---|---|---|---|
| Disable load-generator autostart | Thấp ngay lập tức, trừ khi nó ngăn scale-up hoặc giảm usage-based charges | Cao: giảm traffic, traces, logs, observability pressure | High |
| CloudWatch retention | Thấp hiện tại, ngăn future growth | Medium | High |
| ECR lifecycle | Thấp hiện tại, ngăn future growth | Low/Medium | High |
| Do not reduce observability memory | Không có direct saving | Cao về reliability protection | High |

### 6.2. Conditional future savings

| Candidate | Why it could save | Why it is not approved yet |
|---|---|---|
| Smaller worker instance type | EC2 worker nodes là main fixed cost driver | Cần CPU/memory headroom và không có OOM/restart growth |
| Lower max node group size | Ngăn accidental scale to 4 nodes | Cần load-test proof rằng smaller max vẫn chịu được peak |
| Scheduled scale-down | Giảm compute trong idle windows | Cần environment classification và downtime/capacity acceptance |
| NAT data optimization | NAT có hourly cost và data processing cost | Cần Cost Explorer/data transfer evidence |
| ALB LCU optimization | ALB usage có thể tăng theo traffic | Cần request/LCU evidence |

---

## 7. Proposed implementation plan

### Phase 1 — Safe quick wins

1. Disable `LOCUST_AUTOSTART`.
2. Confirm load-generator chỉ được dùng thủ công trong planned tests.
3. Set CloudWatch retention cho approved non-critical log groups.
4. Add ECR lifecycle policy cho untagged/dev images.
5. Giữ current node group ở 2 x `t3.large`.
6. Giữ observability limits ổn định; không giảm Jaeger/Grafana/Prometheus/OpenSearch.

### Phase 2 — Runtime evidence window

1. Chuẩn hóa Prometheus/Grafana dashboard và PromQL query làm source of truth cho CPU/RAM.
2. Collect 48-72h CPU/memory data cho app pods và observability pods.
3. Track restart count và OOMKilled history.
4. Run một controlled load test với load-generator được bật thủ công.
5. Compare Grafana/APM traces cho checkout, payment, product-catalog, recommendation, product-reviews và frontend flows trước/sau quick wins.

### Phase 3 — Right-size compute if evidence allows

Chỉ thực hiện sau Phase 2:

1. Evaluate liệu `t3.large` có đang overprovisioned hay không.
2. Test smaller worker node type hoặc reduced max size trong một controlled window.
3. Validate p95/p99 latency, error rate, pod restarts, OOMKilled events và node memory headroom.
4. Roll back ngay nếu latency, restart count hoặc OOM events regress.

---

## 8. Jira evidence comment

```text
EVIDENCE UPDATE - COST-05 Right-sizing & Cost Saving Recommendation

1. Đã làm gì?

Đã hoàn thành recommendation cho COST-05 dựa trên COST-01 baseline cost, COST-06 quick wins và PERF-04 runtime evidence.

2. Kết quả chính

Baseline hiện tại vẫn nằm dưới budget $300/week:
- Fixed baseline current: ~$56.83/week
- Fixed baseline + average 1 ALB LCU: ~$58.18/week
- Node group max scenario 4 x t3.large: ~$84.79/week

Main cost driver:
- EC2 worker nodes: 2 x t3.large
- EKS control plane fixed cost
- NAT Gateway and ALB fixed baseline costs
- Observability stack creates indirect node pressure

Recommendation được approve cho Week 1:
- Disable LOCUST_AUTOSTART / load-generator autostart.
- Keep node group at min=2, desired=2 for now.
- Do not reduce Jaeger/Grafana/Prometheus/OpenSearch memory limits yet.
- Investigate accounting restarts and observability OOM/restart evidence before resource cuts.
- Add CloudWatch log retention for approved non-critical log groups.
- Add ECR lifecycle cleanup after confirming image retention policy.

Recommendation KHÔNG nên làm ngay:
- Không downsize t3.large khi chưa có đủ 48-72h Prometheus/Grafana CPU-memory trend.
- Không giảm node count về 1 nếu chưa chấp nhận mất HA.
- Không giảm Jaeger/Grafana memory vì đã có OOM/restart risk.
- Không giảm Prometheus/OpenSearch khi chưa có 48–72h runtime evidence.

3. Bằng chứng sử dụng

- COST-01 baseline:
docs/evidence/epic-04-cost-optimization/01-baseline-cost-estimate.md

- COST-06 quick wins:
docs/evidence/epic-04-cost-optimization/06-cost-quick-wins.md

- PERF-04 runtime performance evidence:
docs/evidence/epic-03-performance-efficiency/04-runtime-performance-evidence.md
docs/evidence/epic-03-performance-efficiency/runtime/

4. Follow-up

Cần chốt Prometheus/Grafana là source of truth để thu thập CPU/memory trong 48-72h. Sau đó mới thực hiện compute right-sizing như đổi instance type, giảm max node group hoặc scheduled scale-down.
```
