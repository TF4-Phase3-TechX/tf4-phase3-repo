# CDO08 Week 1 - Báo Cáo Security Baseline Nền Tảng Kubernetes

Owner: Nhân
Pillar: Security
Priority: P1
Phạm vi: Kubernetes/platform baseline cho CDO08 Week 1
Thời điểm review: 2026-07-09 08:21:41 +07:00
Runtime context phát hiện: `arn:aws:eks:us-east-1:511825856493:cluster/techx-tf4-cluster`

## Tóm Tắt Điều Hành

Đợt scan baseline phát hiện một số hardening gap có thể đưa thẳng vào backlog Week 1. Các rủi ro đáng chú ý nhất là: `frontend-proxy` có thể trở thành điểm expose admin/observability, Grafana đang bật anonymous Admin, OpenSearch tắt security plugin, Grafana ClusterRole có quyền đọc Secrets toàn cluster, và securityContext giữa các workload chưa đồng đều.

Runtime evidence đã lấy được một phần ở namespace app `techx-tf4` lúc 2026-07-09 09:08:14 +07:00. Kubeconfig dùng `AWS_PROFILE=tf4-cdo08-readonly`; lệnh discovery cluster-scope `kubectl get ns` bị `Forbidden`, và audit role hiện tại cũng bị `Forbidden` khi đọc `techx-observability`. Vì vậy phần app baseline có runtime evidence trực tiếp, còn observability/RBAC cluster-scope vẫn dựa trên Helm-rendered evidence và ghi rõ access limitation.

Các lệnh đã dùng để lấy static/rendered evidence trong báo cáo này:

```powershell
helm template techx-corp ./techx-corp-chart -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml
helm template observability ./techx-corp-chart -f deploy/values-observability.yaml
kubectl config current-context
kubectl config view --minify --raw
aws configure get sso_session --profile tf4-cdo08-readonly
kubectl -n techx-tf4 get deploy -o jsonpath="{range .items[*]}{.metadata.name}{'\t'}{.spec.template.spec.serviceAccountName}{'\t'}{.spec.template.spec.securityContext}{'\t'}{.spec.template.spec.containers[*].securityContext}{'\n'}{end}"
kubectl -n techx-tf4 get svc,ingress -o wide
```

## 1. Security Baseline

### 1.1 Ma Trận securityContext

| Nhóm | Components | securityContext hiện tại | Gap |
|---|---|---|---|
| Đã cấu hình non-root cơ bản | `frontend`, `frontend-proxy`, `payment`, `quote`, `kafka`, `valkey-cart` | Có `runAsUser`, `runAsGroup`, `runAsNonRoot: true` trong `techx-corp-chart/values.yaml` | Chưa có `allowPrivilegeEscalation: false`, `readOnlyRootFilesystem`, `capabilities.drop: ["ALL"]`, `seccompProfile` |
| Chưa có container securityContext rõ ràng | `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `fraud-detection`, `flagd`, `image-provider`, `llm`, `load-generator`, `postgresql`, `product-catalog`, `product-reviews`, `recommendation`, `shipping` | Helm render không sinh container-level `securityContext` cho các deployment này | Có thể chạy theo user mặc định của image, bao gồm root; thiếu hardening baseline |
| Chưa có podSecurityContext rõ ràng | Toàn bộ app components | `default.podSecurityContext` chưa cấu hình; template chỉ render pod securityContext khi default/component có value | Chưa có baseline global cho `runAsNonRoot`, `seccompProfile`, `fsGroup`, supplemental group |
| Init containers | `accounting`, `cart`, `checkout`, `fraud-detection`, `flagd` | BusyBox init containers lấy trực tiếp từ values, không có securityContext | Có thể chạy root; nếu đổi non-root cần test vì có lệnh shell/copy/network check |

Evidence:

- `techx-corp-chart/values.yaml:36` đặt `default.securityContext: {}`.
- `techx-corp-chart/templates/_objects.tpl:49-51` chỉ render pod securityContext nếu có default/component podSecurityContext.
- `techx-corp-chart/templates/_objects.tpl:69-71` chỉ render container securityContext nếu có default/component securityContext.
- `techx-corp-chart/values.yaml:406-409`, `468-471`, `559-562`, `654-657`, `812-815`, `903-906` cấu hình non-root cho 6 component.
- Helm render app stamp với release `techx-corp` và runtime namespace `techx-tf4` đều cho thấy mọi Deployment dùng cùng ServiceAccount `techx-corp`.
- Rendered manifest evidence từ `rendered.yaml`: chỉ có 6 block `securityContext` tại các dòng `1525`, `1633`, `1781`, `2001`, `2319`, `2519`, tương ứng `frontend`, `frontend-proxy`, `kafka`, `payment`, `quote`, `valkey-cart`; các block này đều có `runAsNonRoot: true`.
- Runtime check lúc 2026-07-09 09:08:14 +07:00: `kubectl -n techx-tf4 get deploy -o jsonpath=...` trả về podSecurityContext `{}` cho toàn bộ app Deployment; chỉ `frontend`, `frontend-proxy`, `kafka`, `payment`, `quote`, `valkey-cart` có container securityContext `runAsNonRoot: true`.

### 1.2 Ma Trận ServiceAccount/RBAC

| Khu vực | ServiceAccount | RBAC quan sát được | Nhận định rủi ro |
|---|---|---|---|
| App stamp | `techx-corp` runtime; release-dependent trong Helm template | Không thấy app Role/RoleBinding/ClusterRole trong repo scan; runtime cho thấy mọi app Deployment dùng chung ServiceAccount `techx-corp` | Hiện tại tốt vì app không có RBAC rộng, nhưng mọi workload dùng chung identity; nếu sau này grant quyền cho SA này thì mọi app đều hưởng quyền |
| Grafana | `grafana` | Rendered `grafana-clusterrole` có quyền `get`, `watch`, `list` với `configmaps` và `secrets` toàn cluster | Nếu Grafana/sidecar bị compromise, blast radius chạm tới Secrets toàn cluster |
| OpenTelemetry Collector | `otel-collector` | ClusterRole đọc pods, namespaces, nodes, services, workloads, jobs, HPAs, node stats; lease verbs có create/update/delete | Hợp lý cho telemetry cluster-wide, nhưng cần giữ cô lập trong observability namespace và review trước khi mở rộng |
| Prometheus | `prometheus` | Rendered ClusterRole từ subchart | Hợp lý cho scraping/discovery; không nên trộn với app SA |

Evidence:

- `techx-corp-chart/templates/serviceaccount.yaml:3-6` tạo một ServiceAccount ở chart level.
- `techx-corp-chart/templates/_objects.tpl:35` inject `serviceAccountName` vào mọi app workload.
- `_helpers.tpl` resolve ServiceAccount thành release name khi `serviceAccount.create` là true.
- Runtime check lúc 2026-07-09 09:08:14 +07:00 cho thấy toàn bộ app Deployment trong namespace `techx-tf4` dùng `serviceAccountName: techx-corp`.
- Repo scan `rg -n "kind:\s*(Role|ClusterRole|RoleBinding|ClusterRoleBinding)|apiVersion:\s*rbac"` không tìm thấy app-level RBAC files.
- Rendered Grafana ClusterRole có `resources: ["configmaps", "secrets"]`, `verbs: ["get", "watch", "list"]`.
- Rendered OpenTelemetry Collector ClusterRole đọc pods, namespaces, services, nodes, workloads, node stats, và leases.

### 1.3 Inventory Network Exposure

| Component | Service type | Ports | Đường expose |
|---|---:|---|---|
| `frontend-proxy` | `ClusterIP` | 8080 | Expose ra ngoài bằng `deploy/ingress.yaml` qua internet-facing ALB HTTP 80 path `/` |
| `frontend` | `ClusterIP` | 8080 | Nội bộ; route qua `frontend-proxy` |
| `ad`, `cart`, `checkout`, `currency`, `email`, `payment`, `product-catalog`, `quote`, `recommendation`, `shipping` | `ClusterIP` | 8080 | Nội bộ |
| `product-reviews` | `ClusterIP` | 3551 | Nội bộ |
| `image-provider` | `ClusterIP` | 8081 | Nội bộ nhưng có target trong `frontend-proxy` |
| `load-generator` | `ClusterIP` | 8089 | Nội bộ nhưng có target Locust web trong `frontend-proxy` |
| `flagd` | `ClusterIP` | 8013 RPC, 8016 OFREP | Nội bộ. `flagd-ui` sidecar đang disabled trong runtime values |
| `kafka` | `ClusterIP` | 9092 plaintext, 9093 controller | Nội bộ |
| `postgresql` | `ClusterIP` | 5432 | Nội bộ |
| `valkey-cart` | `ClusterIP` | 6379 | Nội bộ |
| `llm` | `ClusterIP` | 8000 | Nội bộ, mock nếu không dùng AIO overlay |
| `grafana` | `ClusterIP` | 80/3000 target | Observability internal service; có route target trong `frontend-proxy` |
| `jaeger` | `ClusterIP` | 16686 UI và collector/query ports | Observability internal service; có route target trong `frontend-proxy` |
| `prometheus` | `ClusterIP` | 9090 | Observability internal |
| `opensearch` | `ClusterIP` | 9200/9300/9600 | Observability internal |
| `otel-collector` | `ClusterIP`/DaemonSet | 4317, 4318, 8888, 9411, Jaeger-compatible ports | Observability internal; OTLP HTTP CORS cho phép `http://*` và `https://*` |

Evidence:

- `deploy/ingress.yaml:9` đặt ALB scheme là `internet-facing`.
- `deploy/ingress.yaml:11` expose HTTP 80, chưa thấy HTTPS.
- `deploy/ingress.yaml:16-20` route `/` tới service `frontend-proxy:8080`.
- `techx-corp-chart/templates/_objects.tpl:169-179` default generated Services là `ClusterIP`.
- Runtime check lúc 2026-07-09 09:08:14 +07:00: `kubectl -n techx-tf4 get svc,ingress -o wide` cho thấy toàn bộ app Services là `ClusterIP`, không có `EXTERNAL-IP`; `techx-alb-ingress` trỏ tới ALB `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com` trên port `80`.
- `techx-corp-chart/values.yaml:437`, `445`, `453`, `457` cấu hình `FLAGD_UI_PORT`, `GRAFANA_PORT`, `JAEGER_UI_PORT`, `LOCUST_WEB_PORT` trong `frontend-proxy`.
- `techx-corp-chart/values.yaml:940-944` cấu hình OTLP HTTP CORS cho `http://*` và `https://*`.

## 2. Findings

### 2.1 Cách Xếp Priority

Priority trong báo cáo này được xếp theo rủi ro thực tế, khả năng bị khai thác qua exposure hiện có, blast radius nếu bị compromise, và mức độ cần xử lý sớm trong Week 1/Week 2.

| Priority | Cách hiểu trong audit này | Finding áp dụng | Lý do |
|---|---|---|---|
| P1 | Gap có exposure hoặc blast radius rõ, nên đưa vào backlog xử lý sớm | `SEC-PLAT-001`, `SEC-PLAT-002`, `SEC-PLAT-003`, `SEC-PLAT-004` | Thiếu hardening trên nhiều workload, internet-facing ALB/HTTP route qua `frontend-proxy`, Grafana anonymous Admin/OpenSearch disabled security, và Grafana ClusterRole đọc Secrets toàn cluster đều có tác động security trực tiếp |
| P2 | Gap có rủi ro thật nhưng cần thêm điều kiện khai thác, hoặc nên xử lý theo hardening batch có test | `SEC-PLAT-005`, `SEC-PLAT-006` | Shared ServiceAccount hiện chưa thấy RBAC rộng nhưng sẽ tăng blast radius nếu sau này bind quyền; OTLP CORS rộng chỉ trở thành rủi ro cao hơn nếu OTLP HTTP endpoint bị expose |
| P3 | Theo dõi hoặc cleanup sau, chưa thấy ảnh hưởng security đáng kể trong baseline hiện tại | Chưa dùng cho finding chính | Không có finding nào trong scan này đủ thấp để chỉ ghi nhận P3 |

Không có finding P0 vì chưa quan sát thấy bằng chứng runtime về secret leakage, public admin endpoint đang truy cập thành công, hoặc quyền cluster-admin bị cấp nhầm cho app workload.

### SEC-PLAT-001 - Container hardening chưa đồng đều và phần lớn còn thiếu

Pillar: Security / Reliability
Service/Component ảnh hưởng: Phần lớn app workloads và init containers
Priority đề xuất: P1
Owner phối hợp: Nhân, service owners theo từng image/runtime

Mô tả:
Chỉ 6 app components có cấu hình non-root identity. Phần lớn workload render ra không có container securityContext, podSecurityContext, privilege escalation guard, capability drop, seccomp profile, hoặc read-only root filesystem.

Evidence:

- `techx-corp-chart/values.yaml:36` có default container securityContext rỗng.
- `techx-corp-chart/templates/_objects.tpl:69-71` chỉ emit container securityContext khi được cấu hình.
- Helm app render không thấy securityContext cho `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `fraud-detection`, `flagd`, `image-provider`, `llm`, `load-generator`, `postgresql`, `product-catalog`, `product-reviews`, `recommendation`, `shipping`.
- Rendered manifest evidence từ `rendered.yaml`: `grep -n "securityContext" rendered.yaml` chỉ trả về 6 dòng `1525`, `1633`, `1781`, `2001`, `2319`, `2519`; grep context map được 6 component là `frontend`, `frontend-proxy`, `kafka`, `payment`, `quote`, `valkey-cart`.
- Runtime check lúc 2026-07-09 09:08:14 +07:00 xác nhận các Deployment `accounting`, `ad`, `cart`, `checkout`, `currency`, `email`, `flagd`, `fraud-detection`, `image-provider`, `llm`, `load-generator`, `postgresql`, `product-catalog`, `product-reviews`, `recommendation`, `shipping` không có container securityContext; các Deployment `frontend`, `frontend-proxy`, `kafka`, `payment`, `quote`, `valkey-cart` có `runAsNonRoot: true`.

Impact:
Nếu image mặc định chạy root hoặc cho phép privilege escalation/capabilities, blast radius khi container bị compromise sẽ cao hơn. Ngoài ra có reliability risk: nếu áp hardening muộn và áp hàng loạt, service có thể crash do thiếu quyền ghi file, cache, config, hoặc path runtime.

Đề xuất xử lý:
Áp securityContext theo từng batch. Nên bắt đầu với các stateless app container có port cao và ít khả năng cần root: `ad`, `checkout`, `currency`, `email`, `product-catalog`, `recommendation`, `shipping`.

Candidate baseline:

```yaml
securityContext:
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  seccompProfile:
    type: RuntimeDefault
```

Chưa nên bật `readOnlyRootFilesystem: true` global trước khi test write path từng image. Các component `postgresql`, `kafka`, `valkey-cart`, `flagd`, `image-provider`, `load-generator`, và BusyBox init containers cần test kỹ.

### SEC-PLAT-002 - Internet-facing HTTP ingress có thể expose frontend-proxy và route admin/observability

Pillar: Security / Reliability
Service/Component ảnh hưởng: `frontend-proxy`, `grafana`, `jaeger`, `load-generator`, route placeholder `flagd-ui`
Priority đề xuất: P1
Owner phối hợp: Nhân, Huy Hoàng/CDO04 cho ALB/TLS/security group, Observability owner

Mô tả:
Platform có internet-facing ALB trên HTTP 80 route toàn bộ path `/` vào `frontend-proxy`. Proxy đang có target env cho Grafana, Jaeger UI, Locust web và flagd-ui. Dù các backend Service là ClusterIP, `frontend-proxy` vẫn là choke point có thể đưa admin/observability endpoint ra ngoài.

Evidence:

- `deploy/ingress.yaml:9` dùng `alb.ingress.kubernetes.io/scheme: internet-facing`.
- `deploy/ingress.yaml:11` listen `HTTP: 80`.
- `deploy/ingress.yaml:16-20` route path `/` tới `frontend-proxy:8080`.
- Runtime check lúc 2026-07-09 09:08:14 +07:00 cho thấy `techx-alb-ingress` có ADDRESS `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com`, PORTS `80`, backend service path từ manifest là `frontend-proxy:8080`.
- `techx-corp-chart/values.yaml:437`, `445`, `453`, `457` cấu hình `FLAGD_UI_PORT`, `GRAFANA_PORT`, `JAEGER_UI_PORT`, `LOCUST_WEB_PORT` trong `frontend-proxy`.
- `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml:40-53` có route `/loadgen/` tới cluster `loadgen`, `/jaeger/` tới cluster `jaeger`, và `/grafana/` tới cluster `grafana`.
- `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml:56-61` có route `/flagservice/` tới cluster `flagservice` và `/feature` tới cluster `flagd-ui`.
- `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml:221-244` định nghĩa các upstream cluster `grafana` và `jaeger` bằng `${GRAFANA_HOST}:${GRAFANA_PORT}` và `${JAEGER_HOST}:${JAEGER_UI_PORT}`; `loadgen` và `flagd-ui` cũng được định nghĩa bằng env host/port ở dòng 197-220.
- `techx-corp-chart/values.yaml:744-748` ghi rõ `flagd-ui` sidecar disabled hiện tại, nhưng proxy env vẫn có host/port cho flagd-ui.

Impact:
Admin/observability tool có thể reachable qua Envoy route/path behavior. Grafana, Jaeger traces, Locust UI, và feature flag UI có thể lộ dữ liệu vận hành, traces, topology, hoặc control plane không dành cho public. HTTP-only ingress cũng làm traffic tới ALB listener chưa được mã hóa.

Đề xuất xử lý:
Giới hạn public ALB chỉ cho storefront/customer-facing paths. Chuyển Grafana, Jaeger, Locust, và flagd-ui tương lai sang VPN, private ALB, port-forward, hoặc authenticated internal ingress. Bổ sung TLS listener và HTTP-to-HTTPS redirect trước review production-like. Cần verify route table trong `src/frontend-proxy/envoy.tmpl.yaml` trước rollout.

### SEC-PLAT-003 - Grafana anonymous Admin và OpenSearch security plugin disabled

Pillar: Security
Service/Component ảnh hưởng: `grafana`, `opensearch`, `frontend-proxy` nếu expose `/grafana`
Priority đề xuất: P1
Owner phối hợp: Nhân, Observability owner, PM Hải để xếp backlog

Mô tả:
Grafana đang tắt login form và bật anonymous Admin. OpenSearch đang disable security plugin. Cấu hình này chỉ nên chấp nhận trong demo network cô lập; nếu reachable qua `frontend-proxy`, port-forward chia sẻ, hoặc internal access quá rộng thì rủi ro cao.

Evidence:

- `techx-corp-chart/values.yaml:1189` đặt `auth.disable_login_form: true`.
- `techx-corp-chart/values.yaml:1190-1193` bật anonymous auth với `org_role: Admin`.
- `techx-corp-chart/values.yaml:1197` đặt `adminPassword: admin`.
- `techx-corp-chart/values.yaml:1229` đặt `DISABLE_SECURITY_PLUGIN`.
- `deploy/values-observability.yaml:2-6` bật OTel Collector, Jaeger, Prometheus, Grafana, và OpenSearch trong observability stamp.

Impact:
Người truy cập được Grafana có thể admin dashboards, datasources, alerting, và có thể đọc traces/logs/metrics. OpenSearch không bật security plugin sẽ thiếu authn/authz native, tăng rủi ro lộ hoặc sửa log data qua bất kỳ route nào reachable.

Đề xuất xử lý:
Trong hardening Week 2, đổi Grafana anonymous role xuống Viewer hoặc disable anonymous auth và yêu cầu SSO/basic auth qua internal ingress. Chuyển admin password sang Kubernetes Secret. Giữ OpenSearch private; không expose qua proxy. Nếu cần query OpenSearch ngoài namespace, bật security plugin hoặc đặt authenticated gateway phía trước.

### SEC-PLAT-004 - Grafana ClusterRole có quyền đọc Secrets toàn cluster

Pillar: Security
Service/Component ảnh hưởng: Grafana sidecar discovery, toàn bộ namespace có Secrets
Priority đề xuất: P1
Owner phối hợp: Nhân, Observability owner

Mô tả:
Rendered Grafana RBAC tạo `grafana-clusterrole` với quyền `get`, `watch`, `list` trên `configmaps` và `secrets`. Quyền này rộng so với nhu cầu dashboard sidecar nếu không có yêu cầu chắc chắn về discovery datasource/secret cross-namespace.

Evidence:

- Helm observability render có `kind: ClusterRole`, `name: grafana-clusterrole`.
- Rendered rule có `resources: ["configmaps", "secrets"]`, `verbs: ["get", "watch", "list"]`.
- `techx-corp-chart/values.yaml:1200-1207` bật Grafana sidecars cho alerts, dashboards, datasources.

Impact:
Nếu Grafana hoặc sidecar bị compromise, attacker có thể đọc Kubernetes Secrets toàn cluster. Đây là rủi ro blast radius trực tiếp.

Đề xuất xử lý:
Scope Grafana sidecar discovery về `techx-observability` nếu có thể. Ưu tiên Role/RoleBinding namespace-level thay vì ClusterRoleBinding. Nếu bắt buộc discovery cluster-wide, tắt Secret discovery và dùng ConfigMaps cho dashboard/datasource không nhạy cảm; credential datasource nên mount từ Secret namespace-local.

### SEC-PLAT-005 - App workloads dùng chung ServiceAccount tạo rủi ro blast radius về sau

Pillar: Security / Reliability
Service/Component ảnh hưởng: Tất cả app deployments dùng chung runtime ServiceAccount `techx-corp`
Priority đề xuất: P2
Owner phối hợp: Nhân, service owners

Mô tả:
Mọi app workload runtime đang dùng cùng ServiceAccount `techx-corp`. Hiện tại app chart không định nghĩa RBAC rộng nên chưa phải privilege escalation tức thời. Tuy nhiên, nếu sau này một service cần quyền Kubernetes API và RoleBinding được gắn vào shared account, toàn bộ app component sẽ có quyền đó.

Evidence:

- `techx-corp-chart/templates/_objects.tpl:35` đặt `serviceAccountName: {{ include "techx-corp.serviceAccountName" . }}` cho mọi deployment.
- Runtime check lúc 2026-07-09 09:08:14 +07:00 cho thấy mọi app Deployment trong `techx-tf4` dùng `serviceAccountName: techx-corp`.
- Repo RBAC scan không thấy app Role/RoleBinding/ClusterRole/ClusterRoleBinding files.

Impact:
Một nhu cầu RBAC của một service có thể vô tình mở quyền cho mọi workload dùng chung ServiceAccount, làm tăng blast radius nếu một pod bị compromise.

Đề xuất xử lý:
Giữ posture hiện tại là app không có RBAC. Trước khi thêm bất kỳ app RBAC nào, bổ sung per-component ServiceAccount override trong chart và chỉ bind quyền cho component thật sự cần.

### SEC-PLAT-006 - OTLP HTTP receiver cho phép browser origin quá rộng

Pillar: Security / Reliability
Service/Component ảnh hưởng: `otel-collector`, `frontend`, browser OTLP traces
Priority đề xuất: P2
Owner phối hợp: Nhân, Observability owner, frontend owner

Mô tả:
OTel Collector HTTP receiver cho phép CORS từ `http://*` và `https://*`. Cấu hình này tiện cho demo/browser telemetry, nhưng quá rộng cho baseline production-like.

Evidence:

- `techx-corp-chart/values.yaml:940-944` cấu hình receiver CORS `allowed_origins` là `http://*` và `https://*`.
- `techx-corp-chart/values.yaml:394` đặt frontend public OTLP traces endpoint là `http://localhost:8080/otlp-http/v1/traces` cho port-forward.

Impact:
Nếu OTLP HTTP endpoint bị expose qua proxy/ingress, browser origin bất kỳ có thể gửi telemetry vào collector. Điều này có thể làm nhiễu traces/metrics, tăng noise/cost, và gây khó điều tra incident.

Đề xuất xử lý:
Giới hạn CORS về storefront domain thật và local dev origin cần thiết. Xác nhận không có public ingress route tới `otel-collector:4318` trước khi đổi. Chỉ giữ broad CORS trong dev overlay.

## 3. Hardening Evidence

### Candidate nên làm trước

| Candidate | Component/config | Vì sao làm trước | Nguy cơ crash |
|---|---|---|---|
| Gỡ public/admin route khỏi `frontend-proxy` hoặc thêm auth gate | `frontend-proxy`, `deploy/ingress.yaml`, `src/frontend-proxy/envoy.tmpl.yaml` | Giảm external exposure mà không đổi process user của app | Medium: có thể làm hỏng link demo Grafana/Jaeger/Locust |
| Đổi Grafana anonymous Admin xuống Viewer hoặc tắt anonymous | Grafana block trong `techx-corp-chart/values.yaml` | Rủi ro security trực tiếp, phạm vi thay đổi gọn trong observability | Medium: dashboard vẫn view được, nhưng admin workflow/provisioning cần test |
| Scope Grafana RBAC | Grafana sidecar/RBAC values | Giảm blast radius với Secrets | Medium: sidecar có thể ngừng discover dashboard/datasource nếu namespace labels sai |
| Thêm `allowPrivilegeEscalation: false`, `capabilities.drop: ["ALL"]`, `seccompProfile: RuntimeDefault` cho stateless app services | `ad`, `checkout`, `currency`, `email`, `product-catalog`, `recommendation`, `shipping` | Hardening giá trị cao, ít kỳ vọng phụ thuộc root | Low-medium: runtime thường chịu được, nhưng cần rollout smoke test |

### Candidate cần test kỹ

| Candidate | Component/config | Cần test | Nguy cơ crash |
|---|---|---|---|
| `runAsNonRoot` cho toàn bộ service chưa set | `accounting`, `cart`, `fraud-detection`, `flagd`, `image-provider`, `llm`, `load-generator`, `postgresql`, `product-reviews` | Verify image user, writable dirs, ports, entrypoints | High với DB/stateful/vendor images và BusyBox init containers |
| `readOnlyRootFilesystem: true` | Toàn bộ app và observability containers | Xác định `/tmp`, cache, log, DB/data, generated config write paths | High; nhiều image ghi temp/cache/config lúc runtime |
| Harden BusyBox init containers | Kafka/Valkey waiters và flagd config init | Verify `nc`, `cp`, volume permission khi non-root | High với `flagd` vì init container copy config vào emptyDir |
| Bật OpenSearch security plugin | `opensearch.extraEnvs` | Datasource auth, index bootstrap, Grafana plugin config, migration path | High; có thể làm logs datasource fail ngay |
| Restrict OTLP CORS | OTel Collector receiver | Browser telemetry từ storefront và local dev | Medium; có thể làm mất web traces âm thầm |

### Candidate nên để sau

| Candidate | Component/config | Lý do defer |
|---|---|---|
| Refactor per-component ServiceAccount | Helm chart template và values schema | Hữu ích, nhưng app hiện chưa có RBAC; làm trước khi thêm app RoleBinding là đủ |
| NetworkPolicy allowlist | Tất cả namespaces | Kiểm soát tốt nhưng cần traffic map đầy đủ và exception cho DNS/observability |
| Enforce Pod Security Admission restricted | Namespace `techx-tf4`, `techx-observability` | Nên làm sau khi test hardening từng component để tránh crash hàng loạt |
| mTLS/service mesh policy | Platform-wide | Quá lớn cho Week 1 baseline; cần ADR và cost/perf review |

## 4. Backlog Candidates Cho Hải Review Bằng Rubric

| Backlog candidate | Finding nguồn | Priority đề xuất | Evidence confidence | Ghi chú cho PM |
|---|---|---:|---:|---|
| Restrict public ingress/proxy exposure cho Grafana, Jaeger, Locust, flagd-ui | SEC-PLAT-002 | P1 | 4 | Evidence source/render mạnh; vẫn cần runtime route validation |
| Disable Grafana anonymous Admin và chuyển admin password sang Secret | SEC-PLAT-003 | P1 | 4 | Security hygiene trực tiếp; phù hợp Week 2 |
| Scope Grafana ClusterRole khỏi cluster-wide Secrets | SEC-PLAT-004 | P1 | 4 | Giảm privilege rõ ràng; cần phối hợp owner dashboard provisioning |
| Thêm baseline container hardening cho stateless services | SEC-PLAT-001 | P1 | 3 | Cần staged rollout/smoke test; không nên one-shot global |
| Test non-root/read-only hardening cho stateful/vendor/init containers | SEC-PLAT-001 | P2 | 3 | Đưa vào backlog có test plan vì crash risk thật |
| Tách app ServiceAccounts trước khi thêm app RBAC | SEC-PLAT-005 | P2 | 3 | Preventive architecture hygiene |
| Restrict OTLP browser CORS về approved origins | SEC-PLAT-006 | P2 | 3 | Phụ thuộc storefront domain và telemetry path cuối cùng |
| Thêm namespace NetworkPolicy sau khi có traffic map | Hardening evidence | P2/P3 | 2 | Cần runtime traffic confirmation để không làm hỏng observability |

## 5. Runtime Evidence Và Lệnh Kiểm Tra

### 5.1 Access evidence hiện tại

Trước khi chạy runtime check, refresh AWS SSO session cho profile đang dùng bởi kubeconfig. Evidence ban đầu từ terminal:

```text
2026-07-09 08:30:42 +07:00
kubectl get ns
aws: [ERROR]: Error when retrieving token from sso: Token has expired and refresh failed
getting credentials: exec: executable aws failed with exit code 255
```

Sau khi login đúng profile, cluster credential đã hoạt động nhưng role không có quyền list namespaces ở cluster scope:

```text
kubectl get ns
Error from server (Forbidden): namespaces is forbidden: User "arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/nhan" cannot list resource "namespaces" in API group "" at the cluster scope
```

Runtime app namespace `techx-tf4` đọc được lúc 2026-07-09 09:08:14 +07:00. Runtime observability namespace bị chặn với cùng role:

```text
kubectl -n techx-observability get svc,ingress -o wide
Error from server (Forbidden): services is forbidden ... in the namespace "techx-observability"
Error from server (Forbidden): ingresses.networking.k8s.io is forbidden ... in the namespace "techx-observability"

kubectl -n techx-observability get deploy,ds,sts,sa,role,rolebinding -o wide
Error from server (Forbidden): deployments.apps is forbidden ... in the namespace "techx-observability"
Error from server (Forbidden): daemonsets.apps is forbidden ... in the namespace "techx-observability"
Error from server (Forbidden): statefulsets.apps is forbidden ... in the namespace "techx-observability"
Error from server (Forbidden): serviceaccounts is forbidden ... in the namespace "techx-observability"
Error from server (Forbidden): roles.rbac.authorization.k8s.io is forbidden ... in the namespace "techx-observability"
Error from server (Forbidden): rolebindings.rbac.authorization.k8s.io is forbidden ... in the namespace "techx-observability"
```

Kubeconfig hiện dùng `AWS_PROFILE=tf4-cdo08-readonly`, vì vậy cần login đúng profile:

```powershell
aws sso login --profile tf4-cdo08-readonly
```

Nếu lệnh login trên vẫn báo thiếu `sso_start_url` hoặc `sso_region`, chạy lại cấu hình SSO cho đúng profile:

```powershell
aws configure sso --profile tf4-cdo08-readonly
```

### 5.2 Lệnh kiểm tra liên quan trực tiếp tới report

Không cần chạy `kubectl get ns` vì role hiện tại không có quyền list namespace cluster-scope. Dùng namespace đã biết và attach output kèm timestamp.

Kiểm tra context/profile đang dùng:

```powershell
Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
kubectl config current-context
kubectl config view --minify --raw
aws configure get sso_session --profile tf4-cdo08-readonly
```

Kiểm tra baseline Service/Ingress exposure cho mục 1.3 và SEC-PLAT-002 trong app namespace:

```powershell
kubectl -n techx-tf4 get svc,ingress -o wide
kubectl -n techx-tf4 describe ingress techx-alb-ingress
```

Kiểm tra Deployment, ServiceAccount, securityContext cho mục 1.1, 1.2, SEC-PLAT-001 và SEC-PLAT-005:

```powershell
kubectl -n techx-tf4 get svc,ingress,deploy,sa,role,rolebinding -o wide
kubectl -n techx-tf4 get deploy -o jsonpath="{range .items[*]}{.metadata.name}{'\t'}{.spec.template.spec.serviceAccountName}{'\t'}{.spec.template.spec.securityContext}{'\t'}{.spec.template.spec.containers[*].securityContext}{'\n'}{end}"
```

Kiểm tra observability workload và ServiceAccount cho mục 1.2, SEC-PLAT-003 và SEC-PLAT-004 nếu audit role được cấp quyền đọc namespace `techx-observability`. Với role hiện tại, các lệnh này đang trả về `Forbidden`, nên report dùng Helm-rendered evidence cho observability:

```powershell
kubectl -n techx-observability get deploy,ds,sts,sa,role,rolebinding -o wide
kubectl -n techx-observability get deploy,ds,sts -o jsonpath="{range .items[*]}{.kind}{'\t'}{.metadata.name}{'\t'}{.spec.template.spec.serviceAccountName}{'\n'}{end}"
kubectl -n techx-observability get svc,ingress -o wide
```

Kiểm tra ClusterRole/ClusterRoleBinding nếu audit role được cấp quyền cluster-scope. Nếu bị `Forbidden`, giữ lại output đó làm evidence về giới hạn RBAC của account audit:

```powershell
kubectl get clusterrole grafana-clusterrole otel-collector prometheus -o yaml
kubectl get clusterrolebinding -o wide
```

Kiểm tra runtime route/admin endpoint exposure cần phối hợp thêm với route/proxy config; nếu chỉ có namespace read-only, tối thiểu attach output Service/Ingress ở trên và đối chiếu với `src/frontend-proxy/envoy.tmpl.yaml`.

Runtime evidence là phần cần có trước khi mark các backlog item là fully verified trong review production-like, đặc biệt với external reachability thực tế, route admin/observability, và live RBAC bindings.
