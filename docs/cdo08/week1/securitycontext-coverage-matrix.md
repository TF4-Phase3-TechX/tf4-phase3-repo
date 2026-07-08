# CDO08 Week 1 - SecurityContext Coverage Matrix

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
| Business Impact | Tìm hardening gaps ở container để giảm blast radius khi service bị compromise. |
| Current Risk | Thiếu `runAsNonRoot`, `allowPrivilegeEscalation: false` hoặc capability drop có thể làm container compromise nghiêm trọng hơn. |
| Scope | Đọc `values.yaml` và templates; tạo matrix cho từng component: `runAsUser`, `runAsGroup`, `runAsNonRoot`, `allowPrivilegeEscalation`, capabilities drop, `readOnlyRootFilesystem`, `podSecurityContext`; ghi current state, gap, compatibility risk. |
| Out of Scope | Không apply hardening trong task này. |
| Dependencies | Cần Nam input runtime compatibility; Nguyên review; Thuỷ nếu hardening ảnh hưởng mounted secret/config. |
| Cost / Perf Impact | Không ảnh hưởng runtime vì task này chỉ audit tài liệu. |
| Output / Artifact | `docs/cdo08/week1/securitycontext-coverage-matrix.md` |
| Consumer | Nhân / Nam / Nguyên |

## Definition Of Done Status

| DoD item | Status | Note |
|---|---|---|
| Matrix completed | Done | Matrix bao phủ custom workload trong `techx-corp-chart/values.yaml`. |
| Gaps ranked | Done | Gap được rank P1/P2/P3 trong phần đề xuất hardening. |
| Compatibility risks noted | Done | Có note theo từng nhóm setting/service. |
| Review completed | Needs Info | Chờ Nguyên review và Nam xác nhận runtime compatibility. |
| Output artifact linked | Done | File này là artifact chính của task. |
| Minimum coverage satisfied | Partial | SecurityContext đã đủ static coverage; ServiceAccount/RBAC và network exposure nằm ở artifact liên quan, xem phần Minimum Coverage Cross-Check. |

## Runtime Verification / Blocker

Runtime verification hiện được đánh dấu:

```text
BLOCKED-BY: TF4 deployment readiness
```

Static analysis từ source/chart/docs đã hoàn thành trong scope task. Khi EKS environment sẵn sàng, cần re-run runtime verification trong vòng 24h bằng `helm template`, `kubectl get deploy`, `kubectl get pods` và so sánh rendered pod specs với matrix này.

## Phạm Vi Và Nguồn Bằng Chứng

Audit này dựa trên cấu hình trong repo, chưa dựa trên `kubectl get` runtime.

- Template Deployment render `podSecurityContext` ở pod level và `securityContext` ở container level: `techx-corp-chart/templates/_objects.tpl`.
- Default container securityContext đang là `{}`: `techx-corp-chart/values.yaml:36`.
- ServiceAccount chung được gắn vào mọi custom component qua template: `techx-corp-chart/templates/_objects.tpl`.
- Các workload và securityContext cụ thể lấy từ `techx-corp-chart/values.yaml`.
- Overlay app/observability xác nhận có mode tách app và observability: `deploy/values-app-stamp.yaml`, `deploy/values-observability.yaml`.

## Tóm Tắt Hiện Trạng

SecurityContext coverage hiện mới dừng ở một phần `runAsNonRoot`. Chưa có baseline chung cho:

- `allowPrivilegeEscalation: false`
- `capabilities.drop: ["ALL"]`
- `readOnlyRootFilesystem: true`
- `seccompProfile: { type: RuntimeDefault }`
- `podSecurityContext` mặc định cho toàn bộ pod

Các workload đã có `runAsUser`, `runAsGroup`, `runAsNonRoot`: `frontend`, `frontend-proxy`, `payment`, `quote`, `kafka`, `valkey-cart`.

## Service Criticality Rank

| Rank | Workload | Lý do | SecurityContext priority draft |
|---|---|---|---|
| Critical | `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `product-catalog`, `shipping` | Nằm trên customer-facing hoặc checkout path. | P1 |
| Sensitive support | `flagd`, `load-generator`, `postgresql`, `kafka`, `valkey-cart`, `product-reviews` | Feature/fault path, load tool, data/broker hoặc AI/review data. | P1-P2 |
| Support | `accounting`, `ad`, `currency`, `email`, `fraud-detection`, `image-provider`, `llm`, `quote`, `recommendation` | Hỗ trợ business flow hoặc async/background. | P2 |

## Coverage Matrix Cho Custom Workload

| Workload | File ảnh hưởng | runAsNonRoot/user | allowPrivilegeEscalation | drop capabilities | read-only filesystem | podSecurityContext | Rủi ro |
|---|---|---|---|---|---|---|---|
| accounting | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| ad | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| cart | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| checkout | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| currency | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| email | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| fraud-detection | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| frontend | `techx-corp-chart/values.yaml:407` | Có: UID/GID 1001 | Thiếu | Thiếu | Thiếu | Thiếu | Low-Medium |
| frontend-proxy | `techx-corp-chart/values.yaml:469` | Có: UID/GID 101 | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| image-provider | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| load-generator | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| payment | `techx-corp-chart/values.yaml:560` | Có: UID/GID 1000 | Thiếu | Thiếu | Thiếu | Thiếu | Low-Medium |
| product-catalog | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| product-reviews | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| quote | `techx-corp-chart/values.yaml:655` | Có: UID/GID 33 | Thiếu | Thiếu | Thiếu | Thiếu | Low-Medium |
| recommendation | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| shipping | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| flagd | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium-High |
| kafka | `techx-corp-chart/values.yaml:813` | Có: UID/GID 1000 | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| llm | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium |
| postgresql | `techx-corp-chart/values.yaml` | Thiếu | Thiếu | Thiếu | Thiếu | Thiếu | Medium-High |
| valkey-cart | `techx-corp-chart/values.yaml:904` | Có: UID 999/GID 1000 | Thiếu | Thiếu | Thiếu | Thiếu | Medium |

## Observability Subchart Note

`grafana`, `opentelemetry-collector`, `prometheus`, `jaeger`, `opensearch` được bật qua subchart trong `techx-corp-chart/values.yaml`. Các `.tgz` có template workload và RBAC riêng, nên cần render bằng Helm trước khi chốt coverage cuối:

- `techx-corp-chart/charts/grafana-12.3.0.tgz`
- `techx-corp-chart/charts/opentelemetry-collector-0.153.0.tgz`
- `techx-corp-chart/charts/prometheus-29.6.0.tgz`
- `techx-corp-chart/charts/jaeger-4.7.0.tgz`
- `techx-corp-chart/charts/opensearch-3.6.0.tgz`

## Phần Còn Thiếu

| Gap | Service/file bị ảnh hưởng | Mức rủi ro | Ghi chú |
|---|---|---|---|
| Thiếu default `allowPrivilegeEscalation: false` | Tất cả custom workload qua `values.yaml` | Medium | Nên thêm trước vì thường ít làm app crash. |
| Thiếu `capabilities.drop: ["ALL"]` | Tất cả custom workload | Medium | Cần test kỹ hơn với Envoy, Postgres, Kafka, Valkey, Nginx image-provider. |
| Thiếu `runAsNonRoot` cho đa số app | App services, data services, flagd, llm | Medium-High | Cần xác định UID hợp lệ trong image trước khi bật hàng loạt. |
| Thiếu `readOnlyRootFilesystem` | Tất cả custom workload | Medium | Rủi ro crash nếu app ghi temp/cache/log vào filesystem. |
| Thiếu `seccompProfile: RuntimeDefault` | Tất cả pod | Medium | Candidate an toàn ở pod level nhưng vẫn cần rollout test. |
| Init container `busybox` chưa có securityContext riêng | accounting/cart/checkout/fraud-detection/flagd | Medium | Template đang render initContainers trực tiếp từ values, không kế thừa container securityContext. |

## P0/P1 Finding Drafts

| Finding | Priority draft | Risk | Affected service/file | Evidence | Proposed follow-up | Compatibility note | Reviewer status |
|---|---|---|---|---|---|---|---|
| Missing default `allowPrivilegeEscalation: false` | P1 | Container compromise có thể leo thang quyền dễ hơn nếu runtime/image cho phép. | Tất cả custom workloads qua `techx-corp-chart/values.yaml`; render bởi `techx-corp-chart/templates/_objects.tpl`. | `default.securityContext: {}` tại `values.yaml:36`; matrix cho thấy field thiếu ở mọi workload. | Thêm default container securityContext hoặc override theo nhóm app; render và rollout canary. | Thường ít crash, nhưng vẫn cần Nam xác nhận với Envoy, Nginx, Postgres/Kafka/Valkey. | Needs Info |
| Missing capability drop baseline | P1 | Container giữ Linux capabilities mặc định làm blast radius lớn hơn khi bị exploit. | Tất cả custom workloads, ưu tiên critical path và public entrypoint. | Không thấy `capabilities.drop` trong values/template search; matrix đánh dấu thiếu. | Candidate Week 2-3: `capabilities.drop: ["ALL"]` cho stateless app trước. | Có thể ảnh hưởng proxy/database/broker hoặc process cần capability đặc biệt; test kỹ từng nhóm. | Needs Info |
| Missing `runAsNonRoot` on most services | P1 | Nếu image chạy root, exploit sẽ có quyền root trong container. | `checkout`, `cart`, `product-catalog`, `shipping`, `flagd`, `postgresql`, `llm` và nhiều support services. | Chỉ `frontend`, `frontend-proxy`, `payment`, `quote`, `kafka`, `valkey-cart` có UID/GID/non-root trong `values.yaml`. | Xác định UID hợp lệ từ Dockerfile/image rồi bật từng service critical. | Rủi ro CrashLoop nếu image không có user hoặc cần quyền ghi path. | Needs Info |

## Đề Xuất Hardening

| Ưu tiên | Đề xuất | Lý do | Affected service/file | Compatibility note |
|---|---|---|---|---|
| P1 | Thêm default container `allowPrivilegeEscalation: false` | Giảm khả năng leo thang quyền nếu process bị khai thác | `techx-corp-chart/values.yaml`, custom workloads | Cần test, nhưng rủi ro crash thấp hơn các setting khác. |
| P1 | Thêm `seccompProfile.type: RuntimeDefault` ở `default.podSecurityContext` | Giảm syscall surface mặc định | `default.podSecurityContext` trong values | Cần rollout canary; có thể khác nhau theo image/runtime. |
| P1 | Bổ sung `runAsNonRoot` cho app stateless trước: cart, checkout, product-catalog, shipping, ad, currency, email, recommendation | Giảm blast radius cho service customer-facing | Workload chưa có UID/GID/non-root | Cần UID hợp lệ theo Dockerfile/image; dễ CrashLoop nếu chọn sai user. |
| P2 | `capabilities.drop: ["ALL"]` cho app stateless | Giảm Linux capabilities mặc định | Custom app containers | Cần test kỹ hơn với Envoy, Nginx, Postgres, Kafka, Valkey. |
| P2 | Hardening riêng `frontend-proxy`/Envoy, `flagd`, `load-generator` | Đây là entrypoint, feature/fault path hoặc công cụ vận hành | `frontend-proxy`, `flagd`, `load-generator` | Cần Nam/Nguyên review vì có thể ảnh hưởng route, flag evaluation hoặc load test. |
| P3 | `readOnlyRootFilesystem: true` theo từng service | Chặn ghi filesystem ngoài mount được kiểm soát | Tất cả custom workloads | Rất dễ crash nếu app ghi temp/cache/log; cần inventory writable paths. |
| P3 | Hardening Postgres/Kafka/Valkey sau cùng | Data/broker images nhạy với writable path/user | `postgresql`, `kafka`, `valkey-cart` | Cần test restart, connection, storage/path trước khi apply. |

## Minimum Coverage Cross-Check

| Coverage area | Artifact | Status |
|---|---|---|
| SecurityContext | File này | Done for static chart coverage. |
| ServiceAccount/RBAC | `docs/cdo08/week1/serviceaccount-rbac-baseline.md` | Done for static baseline; runtime `kubectl auth can-i` pending. |
| Network exposure | `docs/cdo08/week1/network-exposure-inventory.md` | Done for static service/Ingress/Envoy route inventory; runtime ALB path check pending. |

## Cách Kiểm Tra

1. Render manifest trước khi apply:

```bash
helm template techx-corp ./techx-corp-chart -n techx-tf4 -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml > /tmp/techx-app.yaml
```

2. Kiểm tra field security:

```bash
rg -n "securityContext|runAsNonRoot|allowPrivilegeEscalation|capabilities|readOnlyRootFilesystem|seccompProfile" /tmp/techx-app.yaml
```

3. Rollout từng nhóm nhỏ:

```bash
kubectl -n techx-tf4 rollout status deploy/frontend
kubectl -n techx-tf4 rollout status deploy/frontend-proxy
kubectl -n techx-tf4 get pods
kubectl -n techx-tf4 logs deploy/<service> --tail=100
```

4. Smoke test qua entrypoint:

```bash
kubectl -n techx-tf4 port-forward svc/frontend-proxy 8080:8080
curl -fsS http://localhost:8080/
curl -fsS http://localhost:8080/grafana/
curl -fsS http://localhost:8080/jaeger/ui/
```

## Cách Quay Lại

- Rollback Helm release:

```bash
helm -n techx-tf4 rollback techx-corp <REVISION>
```

- Nếu chỉ đổi values, revert block securityContext vừa thêm và chạy lại `helm upgrade`.
- Nếu pod crash do `readOnlyRootFilesystem`, tắt field đó trước, sau đó xác định path cần ghi và mount `emptyDir` có kiểm soát.
- Nếu crash do `runAsNonRoot`, rollback UID/GID của service đó và xác định user hợp lệ trong Dockerfile/image trước khi bật lại.
