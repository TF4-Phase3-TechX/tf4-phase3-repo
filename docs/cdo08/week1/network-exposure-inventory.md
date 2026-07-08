# CDO08 Week 1 - Network Exposure Inventory

Owner: Nhân  
Assignee: Nhân  
Area / Ownership: Platform Security  
Pillar: Security  
Priority: P1  
Status: Needs Info - Static Analysis Complete, Runtime Verification Pending  
Reviewer: Nguyên  
Review Gate: Approved / Needs Info / Defer  
ADR Required: No

## Task Metadata

| Field | Value |
|---|---|
| Business Impact | Giảm rủi ro internal/admin endpoints bị expose quá rộng. |
| Current Risk | Service hoặc route không cần public có thể tăng attack surface. |
| Scope | Đọc `values.yaml` services/ingress comments, service/ingress templates, `frontend-proxy/envoy.tmpl.yaml`; tạo inventory gồm service, type, port, route/path nếu qua proxy, intended audience, admin/observability flag, risk level. |
| Out of Scope | Không implement NetworkPolicy/Ingress change. |
| Dependencies | Cần Quyết input observability routes; Nguyên review risk. |
| Cost / Perf Impact | Không ảnh hưởng runtime vì task này chỉ audit tài liệu. |
| Output / Artifact | `docs/cdo08/week1/network-exposure-inventory.md` |
| Consumer | Nhân / Quyết / Nguyên |

## Definition Of Done Status

| DoD item | Status | Note |
|---|---|---|
| Inventory service/ports/routes completed | Done | Bao phủ custom app services, data services, observability endpoints, `flagd` và `flagd-ui` path. |
| Admin/observability paths marked | Done | `/grafana/`, `/jaeger/`, `/loadgen/`, `/otlp-http/`, `/feature`, `/flagservice/` được đánh dấu riêng. |
| Risks ranked | Done | P1/P2 risk được ghi ở service inventory, path inventory và finding draft. |
| Review completed | Needs Info | Chờ Quyết xác nhận intended observability routes và Nguyên review risk. |
| Output artifact linked | Done | File này là artifact chính của task. |
| Minimum coverage satisfied | Partial | Network exposure đã đủ static coverage; securityContext và ServiceAccount/RBAC nằm ở artifact liên quan, xem phần Minimum Coverage Cross-Check. |

## Runtime Verification / Blocker

Runtime verification hiện được đánh dấu:

```text
BLOCKED-BY: TF4 deployment readiness
```

Static analysis từ source/chart/docs đã hoàn thành trong scope task. Khi EKS environment sẵn sàng, cần re-run runtime verification trong vòng 24h bằng `kubectl get svc,ingress`, `kubectl describe ingress`, endpoint checks và public path checks qua ALB.

## Phạm Vi Và Nguồn Bằng Chứng

- Service template mặc định dùng `ClusterIP` nếu không set type: `techx-corp-chart/templates/_objects.tpl`.
- Ingress template tồn tại trong chart nhưng chỉ render khi component có `ingress.enabled`: `techx-corp-chart/templates/_objects.tpl`.
- Custom service ports lấy từ `techx-corp-chart/values.yaml`.
- Public ALB Ingress hiện nằm ở `deploy/ingress.yaml`: `internet-facing`, HTTP 80, route `/` tới `frontend-proxy:8080`.
- Envoy frontend-proxy routes lấy từ `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`.
- Onboarding architecture xác nhận entrypoint là `frontend-proxy:8080` và observability UI đi qua `/grafana/`, `/jaeger/ui`, `/loadgen/`: `docs/requirements/onboarding/ARCHITECTURE.md`.

## Tóm Tắt Hiện Trạng

Network exposure hiện có hai lớp:

1. Kubernetes Services cho app/data/ops components. Với custom chart, Service type mặc định là `ClusterIP`.
2. Public ALB trong `deploy/ingress.yaml` expose HTTP 80 ra Internet và forward mọi path `/` tới `frontend-proxy:8080`.

Rủi ro chính nằm ở việc `frontend-proxy` không chỉ route storefront public traffic, mà còn route observability/admin-like paths như Grafana, Jaeger, load generator, OTLP HTTP, flag service và `flagd-ui` route.

## Service Inventory

| Service | Type | Port/path | Intended access | Admin/observability? | Risk | Proposed follow-up |
|---|---|---|---|---|---|---|
| `frontend-proxy` | `ClusterIP`; public qua ALB | Service `8080`; ALB HTTP `80` path `/` | Public users for storefront; ops-only for admin/observability paths | Yes, routes multiple ops paths | High | Split or restrict ops paths from public ALB; keep storefront public. |
| `frontend` | `ClusterIP` | `8080`; Envoy `/` | Only `frontend-proxy` | No | Medium | Keep internal; verify no direct public Service/Ingress. |
| `image-provider` | `ClusterIP` | `8081`; Envoy `/images/` | Public through proxy for product images | No | Low-Medium | Keep direct service internal; ensure images are non-sensitive. |
| `ad` | `ClusterIP` | `8080` | Internal app calls | No | Low | No public exposure needed. |
| `cart` | `ClusterIP` | `8080` | `frontend`/`checkout` internal | No | Medium | Keep internal; candidate for NetworkPolicy later. |
| `checkout` | `ClusterIP` | `8080` | `frontend` internal | No | Medium-High | Keep internal; protect revenue path dependencies. |
| `currency` | `ClusterIP` | `8080` | Internal app calls | No | Low | No public exposure needed. |
| `email` | `ClusterIP` | `8080` | `checkout` internal | No | Medium | No public exposure needed. |
| `payment` | `ClusterIP` | `8080` | `checkout` internal | No | High | No public exposure; treat as sensitive checkout dependency. |
| `product-catalog` | `ClusterIP` | `8080` | `frontend`, `recommendation`, `product-reviews` internal | No | Medium | Keep internal. |
| `product-reviews` | `ClusterIP` | `3551` | `frontend` internal | No | Medium | Keep internal; review egress/secret separately if real LLM is enabled. |
| `quote` | `ClusterIP` | `8080` | `shipping` internal | No | Low | Keep internal. |
| `recommendation` | `ClusterIP` | `8080` | `frontend` internal | No | Low | Keep internal. |
| `shipping` | `ClusterIP` | `8080` | `frontend`/`checkout` internal | No | Medium | Keep internal. |
| `accounting` | No Service in values | Kafka consumer only | No inbound service expected | No | Low | Keep service absent unless required. |
| `fraud-detection` | No Service in values | Kafka consumer only | No inbound service expected | No | Low | Keep service absent unless required. |
| `kafka` | `ClusterIP` | `9092` plaintext, `9093` controller | App producers/consumers and broker control internal | Internal infra | High if exposed | Keep internal; no ALB/proxy route. |
| `postgresql` | `ClusterIP` | `5432` | App DB clients only | Data/admin-sensitive | High if exposed | Keep internal; consider NetworkPolicy later. |
| `valkey-cart` | `ClusterIP` | `6379` | `cart` only | Data/admin-sensitive | High if exposed | Keep internal; consider NetworkPolicy later. |
| `flagd` | `ClusterIP` | `8013` rpc, `8016` ofrep; Envoy `/flagservice/` | App/server OpenFeature; browser flag evaluation if required | Feature/fault-control | High | Keep flag mechanism intact but restrict non-required public surface. |
| `flagd-ui` | Sidecar disabled in active values | Envoy route `/feature` targets `flagd-ui:4000` | Ops only if re-enabled | Admin | High if public | If re-enabled, require auth/private access; do not expose public unauthenticated UI. |
| `load-generator` | `ClusterIP` | `8089`; Envoy `/loadgen/` | Perf/ops only | Admin-like test tool | High | Remove from public path or require private access/auth. |
| `opentelemetry-collector` | Subchart Service | `4317`, `4318`, metrics; Envoy `/otlp-http/` | App/browser telemetry only | Observability ingest | Medium-High | Restrict ingest route/origins; verify browser tracing need. |
| `grafana` | Subchart Service | `80`; Envoy `/grafana/` | Ops/team only | Observability/admin | High | Do not expose public anonymous Admin; private access or auth required. |
| `jaeger` | Subchart Service | `16686` UI via `/jaeger/`; `4317` internal ingest | Ops/team only | Observability | High | Do not expose public trace UI if traces may contain sensitive data. |
| `prometheus` | Subchart Service | `9090` internal | Grafana/collector/ops only | Observability | Medium-High | Keep internal; no direct public route. |
| `opensearch` | Subchart Service | `9200` internal | Observability stack only | Logs/search admin-sensitive | High | Keep internal; security plugin currently disabled, so avoid public exposure. |

## Public Path Inventory Qua Frontend-Proxy

| Public path | Upstream cluster | Purpose | Intended audience | Admin/observability? | Risk | Proposed follow-up |
|---|---|---|---|---|---|---|
| `/` | `frontend` | Storefront | Public users | No | Expected | Keep public. |
| `/images/` | `image-provider` | Product/static images | Public users | No | Low | Keep public if content remains non-sensitive. |
| `/grafana/` | `grafana` | Dashboard UI | Ops/team only | Yes | High | Restrict from public ALB or require auth/private access. |
| `/jaeger/` | `jaeger` | Trace UI | Ops/team only | Yes | High | Restrict from public ALB or require auth/private access. |
| `/loadgen/` | `load-generator` | Locust load test UI | Perf/ops only | Admin-like | High | Do not expose public; use port-forward/VPN/private route. |
| `/otlp-http/` | `opentelemetry_collector_http` | Browser telemetry ingest | Browser app only if required | Observability ingest | Medium-High | Restrict origin/path; verify CORS and ingestion need. |
| `/flagservice/` | `flagservice` (`flagd`) | Flag evaluation | Browser/app if required by design | Feature/fault-control | High | Keep required flag evaluation but verify it exposes only expected evaluate API. |
| `/feature` | `flagd-ui` | Feature flag UI | Ops only | Admin | High | Sidecar is disabled now; if enabled later, require private/auth access. |

## P0/P1 Finding Drafts

| Finding | Priority draft | Risk | Affected service/file | Evidence | Proposed follow-up | Compatibility note | Reviewer status |
|---|---|---|---|---|---|---|---|
| Public ALB forwards all paths to `frontend-proxy` | P1 | Ops/admin-like paths behind the proxy may become internet-reachable with the same boundary as storefront traffic. | `deploy/ingress.yaml`; `frontend-proxy`; Envoy routes in `envoy.tmpl.yaml`. | `deploy/ingress.yaml` has `alb.ingress.kubernetes.io/scheme: internet-facing` and path `/` to `frontend-proxy:8080`; Envoy routes `/grafana/`, `/jaeger/`, `/loadgen/`, `/otlp-http/`, `/feature`, `/flagservice/`. | Create Week 2-3 task to split public storefront paths from ops paths or add auth/private access. | Must preserve customer storefront and required browser telemetry/flag paths; needs Quyết input for observability routes. | Needs Info |
| Grafana route may expose anonymous Admin UI if reachable through public proxy | P1 | Public dashboard/admin access can expose operational data and control surfaces. | `techx-corp-chart/values.yaml`; Envoy `/grafana/`. | `grafana.ini.auth.anonymous.enabled: true`, `org_role: Admin`; Envoy routes `/grafana/` to `grafana`. | Disable anonymous Admin or restrict Grafana route to private access. | Changing auth/access can affect team operations; coordinate with Quyết/Nguyên. | Needs Info |
| Load generator UI is routed through frontend-proxy | P1 | Public load test control surface could be abused to generate traffic or change test behavior. | `techx-corp-chart/values.yaml`; `envoy.tmpl.yaml`. | `load-generator` service port `8089`; Envoy routes `/loadgen/` to `loadgen`; architecture docs list `/loadgen/` via proxy. | Remove public route or require private/auth access. | Ensure perf team still has port-forward/VPN workflow. | Needs Info |
| OpenSearch security plugin disabled while observability data exists in cluster | P1 if exposed, otherwise P2 | If OpenSearch is ever exposed, logs/search data may be accessible without the expected security layer. | `techx-corp-chart/values.yaml`; opensearch service. | `DISABLE_SECURITY_PLUGIN: true`; collector exports logs to `http://opensearch:9200`. | Keep service internal; create follow-up before any external exposure. | Enabling security later may break Grafana datasource/collector exporter until credentials are configured. | Needs Info |

## Proposed Follow-Up

| Priority | Recommendation | Why | Test / evidence |
|---|---|---|---|
| P1 | Confirm which Envoy paths are intended to be public with Quyết | Avoid blocking required observability or browser telemetry while reducing attack surface. | Route review against `envoy.tmpl.yaml` and runtime ALB checks. |
| P1 | Split storefront public access from ops/admin paths | Storefront should be public; Grafana/Jaeger/loadgen/feature UI should be private or authenticated. | Public `curl -I` checks for expected 200/403/404. |
| P1 | Review Grafana anonymous Admin setting | Anonymous Admin is risky if reachable beyond trusted users. | Config review and access smoke test. |
| P2 | Add NetworkPolicy candidate after dependency graph is verified | Reduce lateral movement across internal services. | E2E checkout/browse/loadgen and observability smoke test. |
| P2 | Document `flagd` and `/flagservice/` as protected fault-injection path | Avoid breaking required incident mechanism while controlling exposure. | Verify flag evaluation still works. |

## Test Plan

Static checks already completed:

```bash
rg -n "service:|ports:|port:|type:|ingress|frontend-proxy|grafana|jaeger|load-generator|flagd|flagd-ui|opentelemetry-collector|prometheus|opensearch" techx-corp-chart/values.yaml deploy techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml
```

Runtime checks pending EKS readiness:

```bash
kubectl -n techx-tf4 get svc,ingress
kubectl -n techx-tf4 describe ingress techx-alb-ingress
kubectl -n techx-tf4 get endpoints frontend-proxy grafana jaeger load-generator flagd
```

Public route checks after ALB is available:

```bash
curl -I http://<alb-host>/
curl -I http://<alb-host>/images/
curl -I http://<alb-host>/grafana/
curl -I http://<alb-host>/jaeger/ui/
curl -I http://<alb-host>/loadgen/
curl -I http://<alb-host>/feature
curl -I http://<alb-host>/flagservice/
curl -I http://<alb-host>/otlp-http/
```

## Rollback Plan

Không có thay đổi production trong task này.

Nếu follow-up sau này thay đổi Ingress/Envoy/NetworkPolicy làm lỗi truy cập:

- Rollback Helm release:

```bash
helm -n techx-tf4 rollback techx-corp <REVISION>
```

- Nếu chỉ đổi `deploy/ingress.yaml`, revert manifest và re-apply phiên bản trước.
- Nếu ops mất truy cập Grafana/Jaeger/loadgen, dùng tạm `kubectl port-forward` trong namespace trong lúc sửa route.
- Nếu browser telemetry hoặc flag evaluation lỗi sau khi restrict path, rollback riêng `/otlp-http/` hoặc `/flagservice/` rule và tạo allowlist đúng hơn.

## Minimum Coverage Cross-Check

| Coverage area | Artifact | Status |
|---|---|---|
| SecurityContext | `docs/cdo08/week1/securitycontext-coverage-matrix.md` | Required by common minimum coverage; create/commit as separate task artifact if not already merged. |
| ServiceAccount/RBAC | `docs/cdo08/week1/serviceaccount-rbac-baseline.md` | Done in separate task artifact. |
| Network exposure | File này | Done for static service/Ingress/Envoy route inventory; runtime checks pending. |

## PR Guidance

Branch:

```text
cdo08/week1/security/audit-service-va-network-exposure
```

Commit / PR title:

```text
docs(cdo08): audit service va network exposure
```

PR body:

```md
## Summary
- Add CDO08 Week 1 service and network exposure inventory.

## Why
- Identify internal, admin-like, observability and feature-flag endpoints that may be exposed too broadly.
- Reduce attack surface before proposing Ingress, proxy, auth or NetworkPolicy changes.
- Keep this task docs-only because runtime changes require review and compatibility checks.

## Changes
- Added `docs/cdo08/week1/network-exposure-inventory.md`.
- Documented service type, ports, proxy routes, intended audience and risk levels.
- Marked admin/observability paths including Grafana, Jaeger, load generator, OTLP HTTP, flagd and flagd-ui.
- Added P1 finding drafts, runtime blocker, follow-up recommendations and rollback guidance.

## Verification
- [x] Reviewed `techx-corp-chart/values.yaml`
- [x] Reviewed `techx-corp-chart/templates/_objects.tpl`
- [x] Reviewed `deploy/ingress.yaml`
- [x] Reviewed `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`
- [x] Searched service, ingress and route references in chart/deploy/docs
- [ ] Runtime verification pending: BLOCKED-BY TF4 deployment readiness
- [ ] Re-run `kubectl get svc,ingress` and public path checks when EKS/ALB is ready

## Risk & rollback
- Risk: Low, docs-only change. No production configuration is changed.
- Rollback: Revert this documentation commit.

## Scope
- Team: CDO08
- Area: Platform Security
- Artifact: `docs/cdo08/week1/network-exposure-inventory.md`
```
