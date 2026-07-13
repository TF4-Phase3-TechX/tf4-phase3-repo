# Epic 07 - Security Scan Findings

**Owner:** CDO08  
**Pillar:** Security  
**Scan time:** 2026-07-09 09:31 ICT  
**Environment:** EKS `techx-tf4-cluster`, namespace `techx-tf4`  
**Purpose:** Tổng hợp các lỗ hổng/gap bảo mật hiện tại để đưa vào Jira tổng và backlog tuần sau.

## Scope

Scan này tập trung vào các rủi ro bảo mật có evidence từ source/chart hoặc runtime:

- Secret/config nhạy cảm trong Helm values.
- Grafana/OpenSearch security posture.
- Network exposure risk khi observability hoặc admin UI được expose.
- Container securityContext baseline.
- ServiceAccount/RBAC blast radius.
- Public ingress/proxy route và OTLP CORS posture.

## Runtime Context

App hiện đang chạy trong namespace `techx-tf4`.

Commands đã kiểm tra:

```bash
kubectl -n techx-tf4 get pods -o wide
kubectl -n techx-tf4 get svc grafana prometheus jaeger opensearch otel-collector
```

Kết quả chính:

- App pods trong `techx-tf4` đang `Running 1/1`.
- `grafana`, `prometheus`, `jaeger`, `opensearch`, `otel-collector` không còn service trong namespace `techx-tf4` tại thời điểm scan.

## Findings

| ID | Finding | Evidence | Impact | Priority gợi ý | Backlog candidate |
|---|---|---|---|---|---|
| SEC-01 | Hardcoded DB credentials/API key trong Helm values | `techx-corp-chart/values.yaml:182-183`, `581-582`, `618-619`, `600-601`, `870-871` chứa DB password/API key/config nhạy cảm | Secret/config nhạy cảm nằm trong repo; dễ lộ qua Git/diff/PR; khó rotate an toàn | P1 | Migrate sensitive config sang Kubernetes Secret hoặc secret manager phù hợp |
| SEC-02 | Grafana anonymous user có quyền Admin nếu Grafana được expose lại | `techx-corp-chart/values.yaml:1190-1193` bật anonymous và `org_role: Admin`; `1197` có `adminPassword: admin` | Nếu Grafana được expose qua ALB/path, người ngoài có thể có quyền admin dashboard/datasource | P1; P0 nếu public expose được xác nhận | Tắt anonymous Admin, đổi admin password, giới hạn access Grafana |
| SEC-03 | OpenSearch security plugin disabled | `techx-corp-chart/values.yaml:1227-1230` có `DISABLE_SECURITY_PLUGIN=true`; Nhân `SEC-PLAT-003` | Logs/traces có thể không được bảo vệ ở layer OpenSearch; rủi ro cao hơn nếu network exposure sai | P1 | Bật security plugin hoặc giới hạn network access chặt hơn |
| SEC-04 | Container securityContext hardening chưa đồng đều | Nhân `SEC-PLAT-001`; `techx-corp-chart/values.yaml:36` default securityContext rỗng; runtime chỉ một số ít component có `runAsNonRoot` | Nhiều workload có thể chạy theo default image user/root và thiếu guard như drop capabilities, seccomp, privilege escalation guard | P1 | Áp securityContext theo batch cho stateless services trước, có smoke test |
| SEC-05 | Internet-facing HTTP ingress/frontend-proxy có route target admin/observability/flagd-ui | Nhân `SEC-PLAT-002`; `deploy/ingress.yaml:16-20`; `frontend-proxy/envoy.tmpl.yaml:40-61`, `197-244` | Nếu các route này reachable qua public ALB, admin/observability surface có thể bị expose qua HTTP 80 | P1 | Giới hạn public ALB cho storefront paths; chuyển admin UI sang private/authenticated access |
| SEC-06 | Grafana ClusterRole có quyền đọc Secrets toàn cluster trong rendered observability manifest | Nhân `SEC-PLAT-004`; rendered `grafana-clusterrole` có `resources: [configmaps, secrets]`, `verbs: [get, watch, list]` | Nếu Grafana/sidecar bị compromise hoặc misconfig, blast radius có thể mở tới Secrets ngoài namespace | P1 | Scope Grafana discovery về namespace observability hoặc bỏ Secret discovery cluster-wide |
| SEC-07 | App workloads dùng chung ServiceAccount `techx-corp` | Runtime deployments dùng chung `serviceAccountName=techx-corp`; Nhân `SEC-PLAT-005` | Hiện chưa thấy RBAC rộng, nhưng nếu sau này bind quyền cho shared SA thì mọi workload cùng hưởng quyền | P2 | Chuẩn bị per-component ServiceAccount trước khi thêm app RBAC |
| SEC-08 | OTLP HTTP receiver CORS quá rộng | `techx-corp-chart/values.yaml:940-944` cho phép `http://*` và `https://*`; Nhân `SEC-PLAT-006` | Nếu OTLP HTTP endpoint bị expose, browser origins ngoài ý muốn có thể gửi telemetry vào collector | P2 | Giới hạn CORS về storefront domain/dev origins được duyệt |

## Evidence Details

### SEC-01 - Hardcoded credentials/config

Các vị trí cần review:

- `techx-corp-chart/values.yaml:182-183`: `DB_CONNECTION_STRING` chứa username/password.
- `techx-corp-chart/values.yaml:581-582`: product catalog DB connection string chứa password.
- `techx-corp-chart/values.yaml:618-619`: product reviews DB connection string chứa password.
- `techx-corp-chart/values.yaml:600-601`: `OPENAI_API_KEY` đang có value `dummy`.
- `techx-corp-chart/values.yaml:870-871`: `POSTGRES_PASSWORD` hardcoded.

Việc cần làm tuần sau:

- Phân loại item nào là secret thật, item nào chỉ là demo/dummy.
- Chọn migration candidates có rủi ro cao nhất.
- Đề xuất rollback path trước khi migrate.

### SEC-02 - Grafana anonymous Admin

Evidence:

```yaml
auth.anonymous:
  enabled: true
  org_role: Admin
adminPassword: admin
```

Việc cần làm tuần sau:

- Xác nhận Grafana đang deploy ở namespace nào.
- Xác nhận Grafana có public route/path qua ALB không.
- Nếu public exposure tồn tại, nâng priority lên P0.

### SEC-03 - OpenSearch security disabled

Evidence:

```yaml
- name: "DISABLE_SECURITY_PLUGIN"
  value: "true"
```

Việc cần làm tuần sau:

- Xác nhận OpenSearch chỉ internal hay có route/access path khác.
- Nếu cần giữ plugin disabled cho demo, phải có network restriction rõ ràng.

### SEC-04 - Container securityContext hardening gap

Evidence:

- `techx-corp-chart/values.yaml:36` đặt default securityContext rỗng.
- Template chỉ render securityContext khi default/component có value.
- Runtime check của Nhân cho thấy `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `flagd`, `fraud-detection`, `image-provider`, `llm`, `load-generator`, `postgresql`, `product-catalog`, `product-reviews`, `recommendation`, `shipping` chưa có container securityContext rõ ràng.

Việc cần làm tuần sau:

- Không harden global một lần.
- Ưu tiên stateless services trước: `ad`, `checkout`, `currency`, `email`, `product-catalog`, `recommendation`, `shipping`.
- Với stateful/vendor/init containers, cần test riêng trước khi bật `readOnlyRootFilesystem` hoặc non-root strict mode.

### SEC-05 - Public ingress/proxy route exposure risk

Evidence:

- `deploy/ingress.yaml:16-20` route public ALB path `/` tới `frontend-proxy:8080`.
- `frontend-proxy/envoy.tmpl.yaml` có route/cluster target cho `/loadgen/`, `/jaeger/`, `/grafana/`, `/flagservice/`, `/feature`.
- `techx-corp-chart/values.yaml` vẫn cấu hình host/port target cho Grafana, Jaeger UI, Locust web, flagd-ui trong `frontend-proxy`.

Việc cần làm tuần sau:

- Validate bằng runtime request hoặc proxy config render xem các route admin/observability có reachable không.
- Nếu reachable, khóa lại bằng private access/auth hoặc remove khỏi public proxy.
- Không tính đây là finding runtime outage; đây là rủi ro route/proxy exposure nếu các backend admin/observability được bật lại.

### SEC-06 - Grafana ClusterRole reads cluster Secrets

Evidence:

- Rendered observability manifest có `grafana-clusterrole`.
- ClusterRole này có quyền `get`, `watch`, `list` trên `configmaps` và `secrets`.

Việc cần làm tuần sau:

- Xác nhận Grafana dashboard/datasource provisioning có thật sự cần đọc Secret cluster-wide không.
- Ưu tiên Role/RoleBinding namespace-level.
- Nếu phải giữ cluster-wide discovery, bỏ Secret discovery và dùng ConfigMap cho dashboard không nhạy cảm.

### SEC-07 - Shared app ServiceAccount blast radius

Evidence:

- Runtime deployments dùng chung ServiceAccount `techx-corp`.
- Repo scan không thấy app-level Role/RoleBinding rộng, nên hiện chưa phải privilege escalation tức thời.

Việc cần làm tuần sau:

- Giữ nguyên posture hiện tại là app không có RBAC rộng.
- Trước khi thêm quyền Kubernetes API cho bất kỳ service nào, cần tách per-component ServiceAccount.

### SEC-08 - Broad OTLP CORS

Evidence:

```yaml
allowed_origins:
  - http://*
  - https://*
```

Việc cần làm tuần sau:

- Xác nhận OTLP HTTP endpoint có public exposure không.
- Giới hạn origin về storefront domain thật và local dev origin cần thiết.
- Nếu restrict CORS làm mất web traces, rollback trong dev overlay thay vì mở rộng trên runtime chung.

## Suggested Backlog Items

| Backlog ID | Title | Suggested Owner | Priority |
|---|---|---|---|
| SEC-BL-01 | Move hardcoded DB credentials from Helm values to Secret-backed config | Thủy + Nhân + Deploy Operator | P1 |
| SEC-BL-02 | Disable Grafana anonymous Admin and rotate default admin password | Quyết + Nhân | P1/P0 nếu expose public |
| SEC-BL-03 | Review OpenSearch security posture and network exposure | Quyết + Nhân | P1 |
| SEC-BL-04 | Apply staged container securityContext hardening | Nhân + service owners | P1 |
| SEC-BL-05 | Restrict public frontend-proxy routes for admin/observability/flagd-ui targets | Nhân + Quyết + Deploy Operator | P1 |
| SEC-BL-06 | Scope Grafana RBAC away from cluster-wide Secrets | Nhân + Quyết | P1 |
| SEC-BL-07 | Prepare per-component ServiceAccount before adding app RBAC | Nhân + Nguyên | P2 |
| SEC-BL-08 | Restrict OTLP HTTP CORS to approved origins | Nhân + Quyết | P2 |

## Notes For Jira Epic

Security Week 1 scan đã tìm thấy các rủi ro có thể đưa vào backlog tuần sau: hardcoded credentials, Grafana anonymous Admin, OpenSearch security disabled, container hardening gap, frontend-proxy route exposure risk, Grafana ClusterRole đọc Secrets, shared ServiceAccount blast radius và OTLP CORS rộng. Các item liên quan public exposure cần được validate thêm bằng runtime route evidence trước khi triển khai thay đổi.
