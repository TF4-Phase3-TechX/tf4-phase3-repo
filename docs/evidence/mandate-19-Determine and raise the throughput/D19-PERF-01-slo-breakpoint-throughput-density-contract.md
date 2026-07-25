# D19-PERF-01 — Định nghĩa SLO, Breakpoint và Quy tắc đo Throughput Density

## 1. Mục đích

Tài liệu này là execution contract dùng chung cho các lần kiểm thử throughput của Directive #19.

Mục tiêu:

1. xác định khi nào hệ thống còn giữ SLO;
2. xác định breakpoint thực tế;
3. chuẩn hóa cách tính RPS và throughput density;
4. bảo đảm baseline và post-tuning run có thể so sánh trực tiếp;
5. ngăn việc tăng throughput bằng cách tăng số node hoặc thay đổi hạ tầng;
6. giữ tính đúng đắn của Browse, Cart và Checkout trong toàn bộ test.

Tài liệu này chỉ định nghĩa contract. Các giá trị runtime và evidence phải được điền trong change window đã được duyệt.

---

## 2. Phạm vi

Contract áp dụng cho:

- baseline breakpoint run;
- post-tuning breakpoint run;
- overload/load-shedding demonstration;
- throughput-density comparison;
- bottleneck and saturation analysis.

Phạm vi customer flow:

- Browse;
- Cart;
- Checkout.

Phạm vi hạ tầng:

- EKS worker nodes;
- application workloads trong `techx-tf4`;
- các dependency phục vụ trực tiếp customer path;
- load generator;
- HPA, ResourceQuota và scheduler state;
- Prometheus/Grafana evidence.

---

## 3. Nguyên tắc so sánh bất biến

Baseline và post-tuning run phải dùng cùng:

| Tham số | Quy tắc |
|---|---|
| Load generator | Cùng implementation và image digest |
| Load profile | Cùng các step, duration và ramp behavior |
| Endpoint mix | Cùng task weights |
| Test data | Cùng cách tạo dữ liệu và randomization |
| Feature flags | Không thay đổi trong hai run |
| Timeout/retry | Cùng cấu hình |
| SLO query | Cùng PromQL và aggregation |
| Request mapping | Cùng Browse/Cart/Checkout mapping |
| Evaluation window | Cùng thời lượng |
| Infrastructure | Cùng node count, instance type và allocatable capacity |
| Namespace quota | Không tăng giữa hai run |
| Storefront access | Public |
| Operational access | Private |
| `flagd` | Không thay đổi |

Mọi khác biệt phải được ghi lại và được reviewer chấp thuận trước khi dùng kết quả để so sánh.

---

## 4. Hạ tầng cố định

Các trường sau phải được điền trước mỗi run:

```text
RUN_ID=
RUN_TYPE=baseline|post-tuning|overload
RUN_START_UTC=
RUN_END_UTC=
CHANGE_TICKET=
OPERATOR=
REVIEWED_GIT_SHA=
LOAD_GENERATOR_IMAGE_DIGEST=

CLUSTER_NAME=
KUBERNETES_CONTEXT=
WORKER_NODE_COUNT=
WORKER_INSTANCE_TYPES=
TOTAL_WORKER_VCPU=
TOTAL_WORKER_MEMORY_GIB=
TOTAL_WORKER_ALLOCATABLE_CPU_CORES=
TOTAL_WORKER_ALLOCATABLE_MEMORY_GIB=
RESOURCE_QUOTA_CPU_REQUESTS=
RESOURCE_QUOTA_CPU_LIMITS=
RESOURCE_QUOTA_MEMORY_REQUESTS=
RESOURCE_QUOTA_MEMORY_LIMITS=
```

### Quy tắc cố định capacity

Trong khoảng thời gian test:

- không thêm worker node;
- không tăng instance size;
- không thay node group;
- không mở rộng quota để vượt breakpoint;
- không thay đổi cluster topology ngoài tuning đã được review;
- không chạy workload không liên quan gây nhiễu;
- phải ghi node count theo timeline;
- nếu autoscaler tạo thêm node ngoài fingerprint đã duyệt, run không hợp lệ.

---

## 5. Customer-flow mapping

Sử dụng HTTP method cộng normalized request name.

Dynamic identifiers phải được chuẩn hóa trước khi tổng hợp.

| Flow | Request mapping |
|---|---|
| Browse | `GET /`, product list/detail, recommendations, reviews và request đọc storefront khác |
| Cart | `GET /api/cart`, `POST /api/cart`, cart update/remove nếu có |
| Checkout | `POST /api/checkout` và request hoàn tất giao dịch được review |
| Setup request | Được tính vào flow thực tế mà request phục vụ; không gộp tùy ý vào Checkout |

Request name mới hoặc chưa map sẽ làm kết quả flow aggregation không hợp lệ cho tới khi bảng mapping được review.

---

## 6. Request denominator và error accounting

Với mỗi flow:

```text
flow_total = flow_success + flow_failure

flow_success_rate_percent =
  100 × flow_success / flow_total

flow_error_rate_percent =
  100 × flow_failure / flow_total
```

Toàn hệ thống:

```text
successful_rps =
  successful_requests_in_window / window_seconds

offered_rps =
  total_requests_started_in_window / window_seconds

achieved_rps =
  completed_requests_in_window / window_seconds
```

### Quy tắc

- `flow_total` phải lớn hơn 0;
- Locust failed requests là authoritative customer error count;
- HTTP 5xx, timeout, connection reset và exception được lưu làm diagnostic breakdown;
- không cộng lại các diagnostic category vào failure total;
- không dùng dashboard sampling làm denominator;
- không xóa hoặc chỉnh tay raw CSV;
- request bị rate-limit hoặc shed vẫn phải được ghi đúng response code và flow;
- correctness failure được tính là failure dù HTTP status là 2xx.

---

## 7. SLO contract

### 7.1. Browse

| Chỉ số | SLO |
|---|---:|
| Success rate | `≥ 99.5%` |
| Error rate | `≤ 0.5%` |
| p95 latency | `< 1000 ms` |
| p99 latency | `< 1500 ms` |
| Timeout ratio | `≤ 0.2%` |

### 7.2. Cart

| Chỉ số | SLO |
|---|---:|
| Success rate | `≥ 99.5%` |
| Error rate | `≤ 0.5%` |
| p95 latency | `< 1000 ms` |
| p99 latency | `< 1500 ms` |
| Timeout ratio | `≤ 0.2%` |
| Correctness | Cart state đúng sau add/update/remove |

### 7.3. Checkout

| Chỉ số | SLO |
|---|---:|
| Success rate | `≥ 99.0%` |
| Error rate | `≤ 1.0%` |
| p95 latency | `< 1000 ms` |
| p99 latency | `< 2000 ms` |
| Timeout ratio | `≤ 0.2%` |
| Duplicate order | `0` |
| Incorrect order/payment result | `0` |

### 7.4. System-wide safety gates

- không có `OOMKilled` mới;
- không có `CrashLoopBackOff` mới;
- không có `Pending` hoặc `FailedScheduling` kéo dài;
- không có node pressure ảnh hưởng serving capacity;
- không có queue tăng vô hạn;
- không có retry storm;
- HPA có metrics hợp lệ;
- observability signals không bị mất;
- không có correctness regression.

---

## 8. Evaluation window

Mỗi load step phải có:

| Thành phần | Giá trị |
|---|---:|
| Warm-up tối thiểu | 2 phút |
| Step duration tối thiểu | 5 phút |
| Evaluation window | 3 phút cuối step |
| Rolling latency window | 5 phút |
| Evaluation frequency | 1 phút |
| Minimum requests per latency window | 20 request cho flow được đánh giá |

Một latency window thiếu request không được dùng để kết luận PASS hoặc FAIL.

### Hard-gate rule

- error/correctness breach: FAIL ngay khi đủ dữ liệu;
- p99 hoặc p95 breach: FAIL khi có 2 evaluation window hợp lệ liên tiếp;
- OOM, widespread restart hoặc serving-capacity loss: FAIL ngay;
- một scrape lỗi hoặc missing metric: run incomplete cho đến khi signal phục hồi;
- missing evidence không được coi là PASS.

---

## 9. Định nghĩa breakpoint

### 9.1. Last Passing Step

Mức tải cao nhất mà trong toàn evaluation window:

- Browse đạt SLO;
- Cart đạt SLO;
- Checkout đạt SLO;
- system-wide safety gates đạt;
- achieved throughput không giảm bất thường;
- queue/connection backlog không tăng liên tục;
- node count vẫn đúng fingerprint.

### 9.2. First Failing Step

Mức tải đầu tiên xuất hiện một hoặc nhiều điều kiện:

- Browse, Cart hoặc Checkout vi phạm SLO;
- p99/p95 vi phạm theo hard-gate rule;
- customer error tăng vượt threshold;
- timeout tăng vượt threshold;
- achieved RPS plateau hoặc giảm dù offered load tăng;
- queue depth tăng liên tục;
- connection pool cạn;
- worker/thread pool đạt saturation;
- CPU saturation hoặc throttling làm throughput không tăng;
- memory pressure/OOM;
- HPA đạt max nhưng throughput không tăng;
- dependency bắt đầu reject hoặc lag tăng không hồi phục;
- scheduler không thể đặt pod trong capacity cố định.

### 9.3. Breakpoint value

```text
BREAKPOINT_INTERVAL =
  (last_passing_load, first_failing_load]

CONSERVATIVE_BREAKPOINT_RPS =
  successful_rps_at_last_passing_step
```

Khi cần tìm breakpoint chính xác hơn, phải chạy thêm các fine-grained step giữa last passing và first failing.

### 9.4. Breakpoint không hợp lệ khi

- chưa tăng tải tới first failing step;
- node count thay đổi;
- load profile thay đổi;
- missing metrics;
- request denominator bằng 0;
- correctness không được kiểm tra;
- test dừng vì lỗi ngoài hệ thống;
- load generator trở thành bottleneck trước application.

---

## 10. Throughput density

### 10.1. Công thức chính

```text
successful_requests_per_node =
  successful_requests / worker_node_count

sustained_successful_rps_per_node =
  sustained_successful_rps / worker_node_count

successful_rps_per_vcpu =
  sustained_successful_rps / total_worker_vcpu

successful_rps_per_allocatable_vcpu =
  sustained_successful_rps / total_worker_allocatable_cpu_cores

successful_rps_per_gib =
  sustained_successful_rps / total_worker_memory_gib

successful_rps_per_allocatable_gib =
  sustained_successful_rps / total_worker_allocatable_memory_gib
```

### 10.2. Cost-efficiency metric

```text
node_hours_per_million_successful_requests =
  total_worker_node_hours
  / (successful_requests / 1_000_000)
```

Trong Directive #19, metric chính là `successful RPS per node`.

`RPS/vCPU`, `RPS/GiB` và `node-hours per million requests` là metric bổ trợ.

### 10.3. Quy tắc node count

- dùng worker node phục vụ workload trong run;
- không tính control plane;
- node count phải được ghi theo timeline;
- nếu node join hoặc leave trong test, phải tính node-hours và đánh dấu run không còn fixed-node comparison;
- mentor evidence phải hiển thị instance type và node count trước, trong và sau peak.

---

## 11. Throughput improvement rule

Post-tuning run được xem là nâng trần thành công khi:

```text
post_tuning_conservative_breakpoint_rps
>
baseline_conservative_breakpoint_rps
```

và đồng thời:

```text
post_tuning_rps_per_node
>
baseline_rps_per_node
```

với:

- cùng số node;
- cùng instance type;
- cùng load profile;
- cùng SLO;
- cùng correctness rules;
- không tăng quota để tạo thêm capacity;
- không giảm traffic mix;
- không bỏ các request khó;
- không thay denominator.

### Improvement percentage

```text
breakpoint_improvement_percent =
  100 × (
    post_tuning_breakpoint_rps
    - baseline_breakpoint_rps
  ) / baseline_breakpoint_rps

density_improvement_percent =
  100 × (
    post_tuning_rps_per_node
    - baseline_rps_per_node
  ) / baseline_rps_per_node
```

---

## 12. Saturation evidence contract

Tại mỗi step gần breakpoint phải thu:

### CPU

- utilization;
- throttling;
- request/limit;
- HPA CPU target;
- replica count.

### Memory

- working set;
- request/limit;
- GC pressure nếu có;
- restart/OOM.

### Connections

- active connections;
- max connections;
- pool wait;
- connection timeout;
- connection creation rate;
- reuse/keep-alive.

### Concurrency

- active workers/threads;
- in-flight requests;
- queue depth;
- queue wait;
- event-loop lag nếu có.

### Downstream

- PostgreSQL connections/query latency;
- Valkey ops/latency/evictions;
- Kafka bytes/lag;
- external call latency;
- retries;
- circuit-breaker state.

Bottleneck chỉ được xác nhận khi saturation signal có cùng timeline với throughput plateau hoặc SLO failure.

---

## 13. Load-generator validity

Load generator phải chứng minh:

- không đạt CPU/memory saturation;
- không bị network bottleneck;
- không có exception nội bộ;
- requested users/RPS được tạo đúng;
- clock và UTC timestamp đồng bộ;
- raw logs/CSV đầy đủ.

Nếu load generator không tạo được offered load mong muốn, step không dùng để xác định breakpoint.

---

## 14. Stop conditions

Dừng test an toàn khi:

- Checkout success dưới `99.0%`;
- Browse hoặc Cart success dưới `99.5%`;
- duplicate order lớn hơn 0;
- incorrect transaction lớn hơn 0;
- p99/p95 vi phạm hai evaluation window liên tiếp;
- OOM hoặc restart burst ảnh hưởng serving capacity;
- queue tăng vô hạn;
- retry storm;
- node pressure;
- ResourceQuota hoặc scheduler ngăn serving capacity;
- observability mất signal bắt buộc;
- load generator bị lỗi;
- node count tăng ngoài contract;
- operational endpoint bị public;
- `flagd` bị thay đổi.

Run bị hard-stop được ghi là `FAIL` và không được dùng làm passing breakpoint.

---

## 15. Result record

| Metric | Baseline | Post-tuning | Pass rule |
|---|---:|---:|---|
| Last passing offered RPS | | | Ghi nhận |
| Last passing successful RPS | | | Post > Baseline |
| First failing offered RPS | | | Ghi nhận |
| Conservative breakpoint RPS | | | Post > Baseline |
| Peak concurrent users giữ SLO | | | Post > Baseline |
| Successful RPS/node | | | Post > Baseline |
| Successful RPS/vCPU | | | Post > Baseline |
| Successful RPS/GiB | | | Post > Baseline |
| Node-hours/1M requests | | | Post < Baseline |
| Browse success | | | Đạt SLO |
| Cart success | | | Đạt SLO |
| Checkout success | | | Đạt SLO |
| Checkout correctness | | | Không có lỗi |
| Node count | | | Không đổi |
| Instance type | | | Không đổi |
| Bottleneck service | | | Được xác định |
| Saturation metric | | | Có evidence |

---

## 16. Evidence checkpoints

| Checkpoint | Evidence |
|---|---|
| Pre-flight | Git SHA, image digest, node count/type, allocatable, pods, HPA, quota |
| Low load | RPS, p95/p99, errors, replicas, node count |
| Mỗi ramp step | Offered/achieved/successful RPS, SLO, saturation signals |
| Last passing step | Full dashboards và raw data |
| First failing step | Full dashboards, error/latency và bottleneck signals |
| Fine-grained step | Evidence xác định breakpoint chính xác |
| Final | Result table, node timeline, raw artifacts và verdict |

### Thư mục evidence đề xuất

```text
docs/evidence/directive-19/runtime/<baseline|post-tuning>-<RUN_ID>/
├── RESULT
├── summary.json
├── run-metadata.env
├── load/
├── kubernetes/
├── prometheus/
├── grafana/
├── saturation/
└── correctness/
```

---

## 17. Pre-flight commands

```bash
export NAMESPACE=techx-tf4

date -u +"CAPTURE_TIMESTAMP_UTC=%Y-%m-%dT%H:%M:%SZ"
printf 'GIT_SHA=' && git rev-parse HEAD
kubectl config current-context

kubectl get nodes \
  -L kubernetes.io/arch,node.kubernetes.io/instance-type,karpenter.sh/capacity-type

kubectl get nodeclaims -o wide
kubectl get hpa -n "$NAMESPACE"
kubectl get resourcequota -n "$NAMESPACE"
kubectl get limitrange -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -o wide
```

Ghi node timeline trong test:

```bash
while true; do
  date -u +"TIMESTAMP_UTC=%Y-%m-%dT%H:%M:%SZ"
  kubectl get nodes \
    -L node.kubernetes.io/instance-type,karpenter.sh/capacity-type \
    --no-headers
  sleep 60
done
```

---

## 18. Acceptance checklist

- [x] Có SLO cho Browse.
- [x] Có SLO cho Cart.
- [x] Có SLO cho Checkout.
- [x] Có p95 và p99 gates.
- [x] Có error và timeout gates.
- [x] Có correctness gates.
- [x] Có request denominator.
- [x] Có raw error accounting.
- [x] Có evaluation window.
- [x] Có hard-gate rule.
- [x] Có định nghĩa last passing step.
- [x] Có định nghĩa first failing step.
- [x] Có breakpoint interval.
- [x] Có conservative breakpoint.
- [x] Có fine-grained breakpoint rule.
- [x] Có throughput-density formulas.
- [x] Có node-hours per million requests.
- [x] Có fixed-infrastructure rules.
- [x] Có load-generator validity rule.
- [x] Có saturation evidence contract.
- [x] Có stop conditions.
- [x] Có before/after result table.
- [x] Có evidence checkpoints.
- [x] Sẵn sàng review kỹ thuật.

---

## 19. Trạng thái

```text
D19-PERF-01 DOCUMENTATION: COMPLETE
SLO CONTRACT: DEFINED
BREAKPOINT RULE: DEFINED
THROUGHPUT DENSITY RULE: DEFINED
RUNTIME VALUES: TO BE POPULATED DURING APPROVED TEST WINDOWS