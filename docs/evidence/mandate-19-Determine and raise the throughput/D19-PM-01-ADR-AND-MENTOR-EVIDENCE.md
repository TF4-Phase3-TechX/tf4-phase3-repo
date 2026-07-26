# D19-PM-01 — ADR và Mentor Evidence cho Throughput Ceiling

> Directive: #19 — Determine and raise the throughput ceiling  
> Owner: CDO-04 (Performance & Cost)  
> ADR status: **ACCEPTED**  
> Package verdict: **PASS — verified ceiling increased on the same five worker nodes**  
> Canonical post-tuning statement: **Verified sustainable load is at least 350 concurrent users; the new first-failing step has not yet been identified.**

## 1. Executive verdict

| Decision question | Answer |
|---|---|
| Trần cũ | Last Passing Step `75 users`, `22.28 successful RPS`; First Failing Step `125 users`; breakpoint interval `(75, 125]` |
| Trần mới | Ít nhất `350 users`, `48.61 successful RPS`; chưa tìm thấy First Failing Step mới trong profile đã chạy |
| Bottleneck đầu tiên | Amazon RDS PostgreSQL trên critical dependency path |
| Resource saturation | RDS CPU đạt đỉnh `98.92%`, database connections đạt `54`; product-reviews throttling phụ đạt `15.55%` |
| Tuning chính | Giới hạn Go DB pool; thêm Python `ThreadedConnectionPool`; tăng gRPC workers `10 → 50` |
| Worker capacity | Cùng `5 nodes`: `2x t3.large + 3x t3a.large` |
| Successful RPS/node | `4.456 → 9.722`, tăng `118.18%` |
| Successful requests/node trong step | `1,285.0 → 2,916.6`, tăng `126.97%` |
| Overload behavior | Envoy local rate limit shed AI/Browse bằng HTTP `429` và `Retry-After: 1`; Cart/Checkout không bị proxy reject |
| Checkout protection | Cart/Checkout token bucket ở mức không chặn `10,000 RPS/proxy`; Browse/AI nhận shedding trước |
| Correctness | Cart không lỗi; không phát hiện duplicate/missing order; Checkout giữ `0%` error tại same-step 275-user post-tuning run |

## 2. Measurement contract và canonical source

Breakpoint và throughput density tuân theo
[D19-PERF-01](./D19-PERF-01-slo-breakpoint-throughput-density-contract.md):

- Last Passing Step là mức tải cao nhất đạt toàn bộ SLO, correctness và capacity gates.
- First Failing Step là mức đầu tiên vi phạm SLO hoặc xuất hiện saturation/throughput plateau.
- Conservative breakpoint là successful RPS tại Last Passing Step.
- Primary density metric là successful RPS/node.
- Baseline và post-tuning phải giữ cùng load profile, endpoint mix, SLO queries, node count và instance types.

Load schedule được khóa tại
[D19-PERF-02](./D19-PERF-02-stepped-load-profile.md).

### 2.1. Quy tắc chuẩn hóa evidence

Package này dùng canonical runtime dataset gồm `5 worker nodes` trong
[D19-PERF-04](./D19-PERF-04-baseline-report.md),
[D19-PERF-06](./D19-PERF-06-post-tuning-report.md) và
[D19-PERF-07](./D19-PERF-07-post-tuning-ramp-test.md).

Evidence 2-node tại PR #413 thuộc một test window và environment footprint khác nên
không được dùng làm denominator cho so sánh D19-PERF-04/D19-PERF-06.

Giá trị `85.50 RPS` hoặc `17.10 RPS/node` trong comment trung gian không được dùng.
Giá trị canonical là `48.61 successful RPS` và `9.72 successful RPS/node`, khớp
D19-PERF-06, D19-PERF-07 và phép tính D19-COST-01.

## 3. ADR

### 3.1. Context

Baseline ramp test cho thấy hệ thống vẫn nhận request nhưng Browse tail latency gãy
trước khi worker nodes cạn CPU/memory. Ở mức overload, lỗi và latency lan sang Checkout.
Telemetry chỉ ra pressure tập trung tại RDS PostgreSQL và vòng đời connection của
product-reviews/product-catalog, không phải thiếu worker node.

### 3.2. Baseline ceiling

| Step | Successful RPS | Aggregate p99 | Error | Verdict |
|---:|---:|---:|---:|---|
| 75 users | `22.28` | `1,000 ms` | `1/6,426` (`0.02%`) | Last Passing Step |
| 125 users | `34.95` | `1,600 ms` | `1/10,486` (`0.01%`) | First Failing Step: Browse p99 vượt `<1,500 ms` |
| 275 users | `48.33` | `11,000 ms` | `225/14,729` (`1.53%`) | Peak overload; Checkout success `96.86%` |

Nguồn:

- [Baseline report](./D19-PERF-04-baseline-report.md)
- [75-user raw Locust CSV](./log/bf/75/Locust_2026-07-22-23h45_locustfile.py_http___frontend-proxy_8080_requests.csv)
- [125-user raw Locust CSV](./log/bf/125/Locust_2026-07-22-23h52_locustfile.py_http___frontend-proxy_8080_requests.csv)
- [275-user raw Locust CSV](./log/bf/275/Locust_2026-07-23-00h11_locustfile.py_http___frontend-proxy_8080_requests.csv)

### 3.3. First saturated dependency và root cause

| Service/dependency | Signal | Observed value | Verdict |
|---|---|---:|---|
| Amazon RDS PostgreSQL | CPUUtilization | peak `98.92%` | Primary saturated dependency |
| Amazon RDS PostgreSQL | DatabaseConnections | peak `54` | Connection/TLS pressure |
| product-reviews | CPU throttling | peak `15.55%` | Secondary congestion |
| product-reviews | Memory | max `87.54 MiB` of `256 MiB` | Not saturated |
| product-catalog | CPU | max `0.1395 core` | Not saturated |

Root cause:

1. Python product-reviews tạo connection mới cho query, làm lặp TCP/TLS handshake.
2. Go `database/sql` của product-catalog không có upper bound rõ cho open connections.
3. gRPC `ThreadPoolExecutor(max_workers=10)` làm request I/O-bound xếp hàng.
4. Khi overload, DB CPU và connection pressure kéo dài response time trên critical path.

Evidence:

- [First saturated service report](./D19-PERF-05-first-saturated-service.md)
- [Raw bottleneck telemetry](./telemetry-bottleneck-raw.json)

### 3.4. Decision và tuning đã chọn

| Tuning | Before | After | Vì sao nâng throughput |
|---|---|---|---|
| Go product-catalog DB pool | `MaxOpenConns=0`/unbounded | `MaxOpenConns=20`, `MaxIdleConns=5` | Bound concurrent DB work, tránh connection storm và cascade failure |
| Python product-reviews DB access | Mở/đóng connection theo query | `ThreadedConnectionPool(min=5,max=50)` | Tái sử dụng TLS connection, giảm handshake CPU trên RDS |
| product-reviews gRPC workers | `10` | `50` | Cho phép xử lý nhiều I/O-bound requests đồng thời, giảm thread starvation |
| Shipping → Quote HTTP | Tạo `awc::Client` mỗi request | Một client trên mỗi Actix worker | Tái sử dụng keep-alive/pool; terminal failures `192 → 0` |
| Frontend/Product Catalog routing | Có nguy cơ hotspot | Round-robin endpoint discovery | Phân phối request đồng đều giữa replicas |

Implementation:

- [Tuning design](./D19-PERF-05-tuning-design.md)
- [Implementation commit `b2119c7`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/b2119c7d5307c9dbc113fc1682e1b8d4038da7ed)
- [Shipping reuse commit `c98b2f3`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/c98b2f3)
- [Frontend balancing commit `b536a75`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/b536a75baab24f703209c79ed561d8808b8cf96a)

### 3.5. Alternatives rejected

| Alternative | Decision | Reason |
|---|---|---|
| Tăng worker nodes | Rejected | Vi phạm Directive #19 và làm sai density comparison |
| Nâng instance type RDS/EKS để vượt trần | Rejected | Mua throughput bằng capacity thay vì xử root cause |
| Tăng HPA min/max trước khi sửa pool | Rejected | Nhân số client connections và làm RDS pressure nặng hơn |
| PgBouncer trong scope tuning đầu tiên | Deferred | Application-level pool giải quyết connection reuse mà không thêm service vận hành |
| Retry khi overload | Rejected | Có thể khuếch đại retry storm và duplicate side effect |
| Shed Cart/Checkout như Browse | Rejected sau thử nghiệm | Làm gián đoạn purchase flow; Cart/Checkout được exempt |

### 3.6. Post-tuning ceiling và density

| Metric | Before: 75 users | After: 350 users | Delta |
|---|---:|---:|---:|
| Successful RPS | `22.28` | `48.61` | `+118.18%` |
| Successful RPS/node | `4.456` | `9.722` | `+118.18%` |
| Successful requests/node trong 300-second step | `1,285.0` | `2,916.6` | `+126.97%` |
| Successful RPS/vCPU | `2.228` | `4.861` | `+118.18%` |
| Node-hours/1M successful requests | `64.85` | `28.57` | `-55.94%` |
| Worker nodes | `5` | `5` | Không đổi |
| Instance types | `2x t3.large + 3x t3a.large` | Giống baseline | Không đổi |

Post-tuning profile đạt SLO đến mức cao nhất đã chạy là `350 users`. Vì chưa chạy
bước cao hơn làm gãy SLO, ADR không gọi 350 là exact maximum; verdict đúng là:

> **New verified ceiling ≥350 concurrent users and ≥48.61 successful RPS.**

Nguồn:

- [Post-tuning report](./D19-PERF-06-post-tuning-report.md)
- [Density report](./D19-PERF-07-post-tuning-ramp-test.md)
- [D19-COST-01 PR #613](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/613)
- [Post-tuning full-ramp raw export](./log/aftunning/350/Locust_2026-07-24-01h05_locustfile.py_http___frontend-proxy_8080.html)

### 3.7. Graceful overload và Checkout protection

Envoy `local_ratelimit` phân loại traffic thành Checkout, Cart, AI và Browse:

| Class | Burst | Refill | Overload behavior |
|---|---:|---:|---|
| Checkout | `10,000` | `10,000 RPS/proxy` | Không bị local rate limit |
| Cart | `10,000` | `10,000 RPS/proxy` | Không bị local rate limit |
| AI | `6` | `3 RPS/proxy` | Shed trước bằng HTTP 429 |
| Browse | `40` | `20 RPS/proxy` | Hấp thụ phần lớn shedding bằng HTTP 429 |

Overload demo tại `350 users`:

| Metric | Result |
|---|---:|
| Aggregate RPS | `78.74` |
| Aggregate success | `91.118%` |
| Checkout success | `99.538%` |
| Checkout HTTP 429 | `0` |
| Browse success | `84.335%` |
| Browse HTTP 429 | `1,695` |
| AI HTTP 429 | `19` |
| frontend-proxy | `2/2 Ready`, `0 restart` |

Mechanism:

- request ưu tiên thấp nhận `429` và `Retry-After: 1`;
- Checkout/Cart không bị Envoy reject;
- khi load giảm, token bucket tự refill, không cần restart hoặc manual recovery;
- proxy vẫn healthy sau overload.

Implementation evidence:

- [PR #612 — local load shedding](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/612)
- [PR #615 — exempt Checkout](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/615)
- [PR #620 — burst capacity](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/620)
- [Envoy configuration](../../../techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml)

Checkout còn upstream `503` và latency vượt SLO tại overload 350-user demo; đây là
residual downstream saturation, không phải rate limiter vì Checkout có `0` response 429.

### 3.8. Correctness

Correctness được xác minh bằng:

- Cart GET/POST không có business error trong canonical post-tuning step.
- Checkout tại same-step `275 users` post-tuning có `0%` error, p95 `450 ms`,
  p99 `640 ms`.
- Checkout/Payment/order reconciliation không phát hiện duplicate hoặc missing order.
- Không có OOM, Pending hoặc pod restart regression trong fixed-node run.
- Shipping → Quote runtime verification có `2,249/2,249` outbound HTTP 200 và
  `0` terminal failure sau connection reuse.

### 3.9. Rollback

1. Revert application tuning commit `b2119c7` nếu pool exhaustion, transaction-state
   hoặc latency regression xuất hiện.
2. Revert Shipping commit `c98b2f3` nếu client reuse thay đổi error semantics.
3. Revert Envoy commits theo thứ tự `f170d04`, `307a13f`, `f1e4f66` nếu 429 classification
   hoặc proxy behavior sai.
4. Giữ node count và instance types không đổi trong rollback validation.
5. Chạy Browse/Cart/Checkout smoke test, duplicate-order check và recovery observation.

### 3.10. Residual risks

1. Exact new First Failing Step chưa được tìm; 350 users là verified lower bound.
2. Tổng pool ceiling lý thuyết `2x20 + 50 = 90` lớn hơn RDS connection limit `79`;
   phải kiểm soát replica count và đo active/waiting connections.
3. Improvement attribution gồm software tuning và environment footprint sau Mandate 08;
   không quy toàn bộ delta cho một code change.
4. Local rate limit là per Envoy process; traffic skew giữa hai proxies có thể tạo
   shedding không đồng đều.
5. Hai thư mục `aftunning/275` và `aftunning/350` chứa cùng full-ramp export; chúng
   không phải hai independent per-step exports. Step summaries canonical nằm trong
   D19-PERF-06/D19-PERF-07.
6. Checkout vẫn có downstream 503 khi vượt xa trần dù không bị proxy rate limit.

## 4. Mentor evidence index

| Mentor evidence | Evidence link | Mentor verification |
|---|---|---|
| Baseline ramp graph | [D19-PERF-04](./D19-PERF-04-baseline-report.md), [raw baseline folders](./log/bf/) | Xem 75/125/275-user RPS, errors và p99 |
| First failing step | [125-user CSV](./log/bf/125/Locust_2026-07-22-23h52_locustfile.py_http___frontend-proxy_8080_requests.csv) | Aggregated p99=`1600 ms`; Browse gate `<1500 ms` |
| Bottleneck dashboard/data | [Bottleneck report](./D19-PERF-05-first-saturated-service.md), [raw JSON](./telemetry-bottleneck-raw.json) | RDS CPU peak `98.92%`, connections `54` |
| Tuning diff | [Commit `b2119c7`](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/commit/b2119c7d5307c9dbc113fc1682e1b8d4038da7ed) | Review Go/Python pool và worker diff |
| Post-tuning ramp graph | [D19-PERF-06](./D19-PERF-06-post-tuning-report.md), [full-ramp HTML](./log/aftunning/350/Locust_2026-07-24-01h05_locustfile.py_http___frontend-proxy_8080.html) | Xem ramp đến 350 users |
| Before/after RPS | [D19-PERF-07](./D19-PERF-07-post-tuning-ramp-test.md) | `22.28 → 48.61 successful RPS` |
| Requests per node | [D19-COST-01 PR #613](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/613) | `4.456 → 9.722 RPS/node` |
| Node count timeline | [D19-COST-01 PR #613](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/613) | 5 fixed node IDs và instance types |
| Overload demo | [PR #612](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/612), [#615](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/615), [#620](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/620) | Browse/AI 429; Checkout/Cart 0 rate-limit 429 |
| Checkout success | [D19-PERF-07](./D19-PERF-07-post-tuning-ramp-test.md) | Same-step 275 users: Checkout error `0%` |
| Browse shedding | [Envoy config](../../../techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml) | Route-specific local token bucket |
| Recovery evidence | [PR #620 validation record](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/620) | Proxy `2/2 Ready`, zero restart; token refill without restart |
| Signed ADR | Section 5 | Owner/approver and approval record |

## 5. ADR sign-off

| Role | Sign-off | Date/evidence |
|---|---|---|
| ADR owner | **CDO-04 — ACCEPTED** | Runtime package D19-PERF-04 through D19-PERF-07 |
| Technical approver | **Tech Lead — APPROVED** | Approval recorded in [D19-PERF-05 tuning design](./D19-PERF-05-tuning-design.md); implementation merged as PR #544 |
| Performance/Cost reviewer | **CDO-04 — VERIFIED** | Density calculation in [PR #613](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/613) |
| Mentor | **READY FOR MENTOR REVIEW** | This package and linked raw evidence |

Decision date: `2026-07-24`  
Implementation SHA: `b2119c7d5307c9dbc113fc1682e1b8d4038da7ed`  
Documentation PR: [#598](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/598)  
Density PR: [#607](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/607)  
Cost/density calculation PR: [#613](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/613)

## 6. Acceptance criteria

- [x] Trần cũ được ghi: `75 users / 22.28 successful RPS`, breakpoint `(75,125]`.
- [x] Trần mới được ghi chính xác dưới dạng lower bound: `≥350 users / ≥48.61 successful RPS`.
- [x] Bottleneck và saturation resource được ghi.
- [x] Tuning và implementation diff được ghi.
- [x] Node count proof dùng canonical five-node runs.
- [x] Density improvement và công thức được ghi.
- [x] Overload demo và graceful shedding được ghi.
- [x] Checkout protection và zero rate-limit 429 được ghi.
- [x] Correctness và duplicate/missing-order verdict được ghi.
- [x] ADR có owner, technical approval record và implementation SHA.
- [x] Mentor package có index và đường dẫn tự xác minh.
