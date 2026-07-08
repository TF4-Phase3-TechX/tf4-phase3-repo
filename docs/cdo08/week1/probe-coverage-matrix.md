# Probe Coverage Matrix - Readiness & Liveness

## 0. Task metadata

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Jira task        | `[Runtime] Audit readiness và liveness probe coverage`                     |
| Owner / Assignee | Hoàng Nam                                                                  |
| Area / Ownership | Kubernetes Runtime Reliability                                             |
| Pillar           | Reliability                                                                |
| Priority         | P0                                                                         |
| Reviewer         | Nguyên                                                                     |
| Output artifact  | `docs/cdo08/week1/probe-coverage-matrix.md`                                |
| Current status   | Static analysis completed; runtime probe verification completed            |
| Runtime blocker  | N/A for probe coverage; runtime evidence captured in namespace `techx-tf4` |
| Last updated     | 2026-07-08                                                                 |

## 1. Mục tiêu

Task này audit readiness/liveness probe coverage hiện tại của các service critical trong chart Phase 3 để xác định service nào có nguy cơ nhận traffic khi chưa sẵn sàng hoặc không được Kubernetes restart khi container unhealthy.

Scope của task này là **static analysis từ source/chart**, chưa thêm hoặc thay đổi probe trong manifest.

## 2. Nguồn evidence

### 2.1 Probe support trong Helm template

| File                                      |    Line | Evidence                                                             | Ý nghĩa                                                    |
| ----------------------------------------- | ------: | -------------------------------------------------------------------- | ---------------------------------------------------------- |
| `techx-corp-chart/templates/_objects.tpl` |   73-79 | Render `livenessProbe` và `readinessProbe` nếu component có cấu hình | Chart có hỗ trợ probe cho main container                   |
| `techx-corp-chart/templates/_objects.tpl` | 125-131 | Render `livenessProbe` và `readinessProbe` nếu component có cấu hình | Chart có hỗ trợ probe cho sidecar/container path khác      |
| `techx-corp-chart/values.yaml`            | 152-154 | Chỉ có comment mẫu `livenessProbe: {}` và `readinessProbe: {}`       | Baseline values chưa cấu hình probe thực tế cho components |

Kết luận evidence: chart **có khả năng render readiness/liveness probes**, nhưng baseline `values.yaml` **không cấu hình probes cho các service trong scope**. Không tìm thấy `startupProbe` trong chart template/values baseline.

### 2.2 Health capability trong source

| Service           | Source evidence                                                                                              | Ghi chú                                                                                        |
| ----------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `checkout`        | `src/checkout/main.go:252-253`, `src/checkout/main.go:281-286`                                               | Có gRPC health service, nhưng `Check` trả `SERVING` tĩnh                                       |
| `cart`            | `src/cart/src/Program.cs:90-102`, `src/cart/src/services/HealthCheckService.cs:30-43`                        | Có gRPC health/readinessCheck; readiness hiện chủ yếu theo feature flag, chưa ping Valkey thật |
| `payment`         | `src/payment/index.js:41-42`                                                                                 | Có gRPC health service, nhưng trạng thái luôn `SERVING`                                        |
| `product-catalog` | `src/product-catalog/main.go:250-251`, `src/product-catalog/main.go:409-414`                                 | Có gRPC health service, nhưng `Check` trả `SERVING` tĩnh, chưa ping DB                         |
| `product-reviews` | `src/product-reviews/product_reviews_server.py:109-115`, `src/product-reviews/product_reviews_server.py:366` | Có gRPC health service, nhưng `Check` trả `SERVING` tĩnh                                       |
| `currency`        | `src/currency/src/server.cpp:91-98`, `src/currency/src/server.cpp:253-257`                                   | Có gRPC health service, trả `SERVING`                                                          |

Kết luận source: một số service đã có health endpoint/protocol ở application layer, nhưng Kubernetes chart hiện chưa nối các health check đó thành readiness/liveness probes.

## 3. Probe coverage matrix

| Service           | Has readiness | Has liveness | Probe type hiện tại | Port/path/command hiện tại | Criticality | Startup/rollout risk                                                                                        | Proposed follow-up                                                                                  | Test idea                                                                   |
| ----------------- | ------------- | ------------ | ------------------- | -------------------------- | ----------- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `frontend-proxy`  | No            | No           | N/A                 | N/A                        | P0          | Public entrypoint có thể nhận traffic khi Envoy/config chưa sẵn sàng; rollout lỗi ảnh hưởng toàn storefront | Thêm readiness/liveness cho Envoy hoặc HTTP check qua proxy route an toàn                           | Render manifest, rollout restart, check ALB route vẫn trả 200               |
| `frontend`        | No            | No           | N/A                 | N/A                        | P0          | UI/API frontend có thể nhận traffic trước khi Next.js sẵn sàng                                              | Thêm HTTP readiness/liveness nếu app có endpoint phù hợp; nếu chưa có, tạo lightweight health route | Curl health route qua service/pod trong rollout                             |
| `checkout`        | No            | No           | N/A                 | N/A                        | P0          | Revenue path nhận traffic khi gRPC server/downstream chưa sẵn sàng; khớp risk deploy incident               | Dùng gRPC health probe cho readiness/liveness; readiness cần cân nhắc dependency tối thiểu          | `grpc-health-probe` vào checkout port; checkout smoke test sau rollout      |
| `cart`            | No            | No           | N/A                 | N/A                        | P0          | Cart có thể nhận traffic khi app hoặc Valkey dependency chưa sẵn sàng                                       | Dùng gRPC health readiness; cải thiện readiness để ping Valkey thật                                 | Add/read/get cart smoke test; simulate Valkey unavailable nếu có môi trường |
| `product-catalog` | No            | No           | N/A                 | N/A                        | P0          | Browse/checkout lookup có thể route vào pod chưa sẵn sàng hoặc DB chưa kết nối                              | Dùng gRPC health probe; readiness nên kiểm tra DB ping nhẹ                                          | Product browse/get product smoke test; DB readiness validation              |
| `payment`         | No            | No           | N/A                 | N/A                        | P0          | Payment từng có incident traffic vào pod trước ready; checkout có thể fail trong rollout                    | Dùng gRPC health probe + graceful shutdown/preStop follow-up                                        | Checkout payment path smoke test trong rollout                              |
| `shipping`        | No            | No           | N/A                 | N/A                        | P0          | Checkout phụ thuộc shipping; pod chưa ready có thể làm checkout fail                                        | Xác định health capability; thêm TCP/gRPC/HTTP probe phù hợp                                        | Checkout shipping path smoke test                                           |
| `quote`           | No            | No           | N/A                 | N/A                        | P0          | Checkout cần quote; rollout pod lỗi có thể fail checkout                                                    | Xác định health capability; thêm probe phù hợp với protocol                                         | Quote/shipping quote request smoke test                                     |
| `currency`        | No            | No           | N/A                 | N/A                        | P0          | Currency conversion nằm trong checkout/product price flow                                                   | Dùng gRPC health probe nếu image hỗ trợ probe binary hoặc probe sidecar/tooling                     | Currency conversion smoke test                                              |
| `postgresql`      | No            | No           | N/A                 | N/A                        | P0          | Stateful DB pod chưa ready có thể làm product-catalog/reviews/accounting lỗi                                | Dùng chart/native DB readiness nếu in-cluster DB tiếp tục được dùng; tránh liveness quá aggressive  | `pg_isready` readiness; DB query smoke test                                 |
| `valkey-cart`     | No            | No           | N/A                 | N/A                        | P0          | Cart state dependency chưa ready có thể làm cart/readiness fail                                             | Dùng Valkey/Redis ping readiness; liveness thận trọng để tránh restart loop                         | Redis/Valkey PING; cart smoke test                                          |
| `kafka`           | No            | No           | N/A                 | N/A                        | P1          | Kafka chưa ready có thể làm order event backlog/loss hoặc consumer errors                                   | Dùng broker readiness phù hợp; liveness thận trọng                                                  | Produce/consume test hoặc broker API readiness                              |
| `flagd`           | No            | No           | N/A                 | N/A                        | P1          | Feature flag/incident mechanism có thể không sẵn sàng; không được phá flagd sync                            | Thêm probe sau khi xác nhận flagd sync source hoạt động ổn định                                     | Check flag evaluation/sync state sau rollout                                |
| `product-reviews` | No            | No           | N/A                 | N/A                        | P1          | AI review feature có thể nhận request trước khi DB/LLM/product-catalog client sẵn sàng                      | Dùng gRPC health probe; readiness nên cân nhắc DB/LLM fallback nhẹ                                  | Product reviews/summary smoke test                                          |
| `recommendation`  | No            | No           | N/A                 | N/A                        | P2          | Recommendation degrade UX, không block checkout chính                                                       | Dùng health probe nếu có sẵn; ưu tiên sau checkout path                                             | Recommendation response smoke test                                          |
| `email`           | No            | No           | N/A                 | N/A                        | P2          | Email confirmation failure nên degrade, không nên block checkout nếu thiết kế đúng                          | Thêm probe nếu service có endpoint; ưu tiên sau checkout path                                       | Order email path/log check                                                  |
| `ad`              | No            | No           | N/A                 | N/A                        | P2          | Ad failure ít ảnh hưởng checkout trực tiếp                                                                  | Defer probe hardening nếu chưa ảnh hưởng UX/SLO                                                     | Ad response smoke test                                                      |

## 4. Critical gaps ranked

| Rank | Priority | Gap                                                           | Affected service/file                                                            | Risk                                                                        | Proposed follow-up                                              | Cost/perf dependency                               |
| ---: | -------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------- |
|    1 | P0       | Missing readiness/liveness at public entrypoint               | `frontend-proxy`, `techx-corp-chart/values.yaml`, `_objects.tpl`                 | ALB/service có thể route vào proxy pod chưa sẵn sàng                        | Add Envoy/HTTP readiness and liveness candidate                 | Low runtime overhead; coordinate with deploy owner |
|    2 | P0       | Missing probes on checkout service                            | `checkout`, `src/checkout/main.go`, `values.yaml`                                | Checkout success SLO bị ảnh hưởng khi rollout/crash                         | Add gRPC health probe; validate with checkout smoke test        | Low overhead; may need image/probe binary support  |
|    3 | P0       | Missing probes on payment service                             | `payment`, `src/payment/index.js`, `values.yaml`                                 | Incident history từng có payment error during deploy                        | Add gRPC health probe + graceful shutdown/preStop follow-up     | Low overhead; coordinate with checkout owner       |
|    4 | P0       | Missing readiness for cart + Valkey dependency                | `cart`, `valkey-cart`, `src/cart/...HealthCheckService.cs`, `ValkeyCartStore.cs` | Cart nhận traffic khi Valkey chưa sẵn sàng; ảnh hưởng checkout precondition | Add cart gRPC readiness and Valkey ping readiness               | Need data/runtime owner validation                 |
|    5 | P0       | Missing readiness for product-catalog + PostgreSQL dependency | `product-catalog`, `postgresql`, `src/product-catalog/main.go`                   | Browse/checkout lookup lỗi nếu DB chưa ready                                | Add gRPC readiness with DB ping; DB `pg_isready` for PostgreSQL | Need DB/data owner validation                      |
|    6 | P0/P1    | Missing probes on checkout downstream services                | `shipping`, `quote`, `currency`                                                  | Checkout can fail if downstream pod is routed before ready                  | Identify protocol and add protocol-appropriate probes           | Low overhead; needs smoke tests                    |
|    7 | P1       | Missing probes on Kafka/flagd                                 | `kafka`, `flagd`, `values.yaml`                                                  | Post-order events/feature flags may be unstable during rollout              | Add cautious readiness after confirming semantics               | Stateful/flag sync behavior needs owner review     |
|    8 | P1/P2    | Missing probes on AI/UX services                              | `product-reviews`, `recommendation`, `email`, `ad`                               | Degraded UX or delayed detection of unhealthy pod                           | Add probes after checkout path priorities                       | Lower priority unless SLO evidence says otherwise  |

## 5. Probe recommendation notes

- Readiness should answer: "Can this pod safely receive traffic now?"
- Liveness should answer: "Is this container stuck/unhealthy enough that Kubernetes should restart it?"
- Liveness should not perform heavy downstream dependency checks. If downstream is temporarily unavailable, restarting the app can make outage worse.
- Readiness may check critical local dependencies, but should remain lightweight and bounded by short timeout.
- For gRPC services, prefer gRPC health probe if the image/runtime supports it.
- For stateful services, prefer native lightweight checks such as `pg_isready` for PostgreSQL or `PING` for Valkey/Redis-compatible service.
- `startupProbe` is not currently supported in chart template. If services have slow startup, add `startupProbe` support as a follow-up before aggressive liveness probes.

## 6. Runtime verification

Status hiện tại: **Completed for probe coverage**.

Runtime verification đã chạy được trong namespace `techx-tf4` sau khi SSO role được cấp quyền namespace-scope vào Kubernetes API. Lưu ý: `kubectl get ns` ở cluster-scope vẫn bị hạn chế RBAC, nhưng không chặn task này vì artifact chỉ cần evidence workload trong namespace deploy app.

### 6.1 Probe summary từ runtime Deployment specs

Command:

```bash
kubectl -n techx-tf4 get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{range .spec.template.spec.containers[*]}{.name}{": readiness="}{.readinessProbe}{" liveness="}{.livenessProbe}{"; "}{end}{"\n"}{end}'
```

Runtime result summary:

| Nhóm workload             | Runtime probe result                                                                                                                                      | Ý nghĩa                                                                                                       |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| App/revenue path services | `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog`, `shipping`, `quote`, `currency` không có `readinessProbe`/`livenessProbe` | Runtime xác nhận finding static: service critical chưa được Kubernetes health-gate                            |
| Stateful dependencies     | `postgresql`, `valkey-cart`, `kafka` không có `readinessProbe`/`livenessProbe`                                                                            | DB/cache/event broker chưa có native runtime readiness như `pg_isready`, Valkey `PING`, hoặc broker readiness |
| Flag/AI/UX services       | `flagd`, `product-reviews`, `recommendation`, `email`, `ad` không có `readinessProbe`/`livenessProbe`                                                     | Các service P1/P2 cũng thiếu probe coverage                                                                   |
| Observability subcharts   | `grafana`, `jaeger`, `prometheus` có HTTP readiness/liveness                                                                                              | Probe support tồn tại ở một số subchart, nhưng chưa được cấu hình cho app components                          |

### 6.2 Critical service describe evidence

Commands đã chạy:

```bash
kubectl -n techx-tf4 describe deploy checkout
kubectl -n techx-tf4 describe deploy cart
kubectl -n techx-tf4 describe deploy payment
kubectl -n techx-tf4 describe deploy frontend-proxy
kubectl -n techx-tf4 describe deploy frontend
kubectl -n techx-tf4 describe deploy postgresql
kubectl -n techx-tf4 describe deploy valkey-cart
kubectl -n techx-tf4 describe deploy kafka
```

Evidence summary:

| Deployment       | Runtime evidence                                                                                                               | Probe finding                                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `checkout`       | `Replicas: 1 desired, 1 available`; init container `wait-for-kafka`; container port `8080`                                     | Không có `Readiness:`/`Liveness:` section trong `describe deploy`                                               |
| `cart`           | `Replicas: 1 desired, 1 available`; init container `wait-for-valkey-cart`; `VALKEY_ADDR=valkey-cart:6379`                      | Không có `Readiness:`/`Liveness:` section; chỉ chờ Valkey lúc startup, không kiểm tra liên tục sau khi pod chạy |
| `payment`        | `Replicas: 1 desired, 1 available`; container port `8080`                                                                      | Không có `Readiness:`/`Liveness:` section                                                                       |
| `frontend-proxy` | `Replicas: 1 desired, 1 available`; public entrypoint route tới frontend/Grafana/Jaeger/load-generator/collector               | Không có `Readiness:`/`Liveness:` section cho entrypoint                                                        |
| `frontend`       | `Replicas: 1 desired, 1 available`; env trỏ tới cart/checkout/currency/product-catalog/product-reviews/recommendation/shipping | Không có `Readiness:`/`Liveness:` section                                                                       |
| `postgresql`     | `Deployment`; `Replicas: 1 desired, 1 available`; image `postgres:17.6`; mount ConfigMap init                                  | Không có `pg_isready` readiness/liveness; không thấy PVC data mount trong runtime spec                          |
| `valkey-cart`    | `Deployment`; `Replicas: 1 desired, 1 available`; image `valkey/valkey:9.0.1-alpine3.23`; no volume mount                      | Không có Redis/Valkey `PING` readiness/liveness                                                                 |
| `kafka`          | `Deployment`; `Replicas: 1 desired, 1 available`; `KAFKA_CONTROLLER_QUORUM_VOTERS=1@kafka:9093`                                | Không có broker readiness/liveness; runtime xác nhận single-node controller quorum                              |

Runtime conclusion: static finding được xác nhận trên cluster. Các app service critical và stateful dependencies trong namespace `techx-tf4` chưa có readiness/liveness probes ở runtime, trong khi một số observability subcharts đã có HTTP probes. Follow-up tuần 2-3 nên ưu tiên probe hardening cho entrypoint, checkout path và stateful dependencies trước.

## 7. Definition of Done checklist

- [x] Matrix readiness/liveness completed từ static chart/source analysis.
- [x] Critical gaps ranked.
- [x] Probe test ideas included.
- [x] Affected service/file/evidence/proposed follow-up có trong matrix.
- [x] Runtime verification bằng `kubectl` trong namespace `techx-tf4`.
