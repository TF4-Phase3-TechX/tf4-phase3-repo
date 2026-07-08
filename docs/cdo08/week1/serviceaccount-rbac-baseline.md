# CDO08 Week 1 - ServiceAccount Và RBAC Baseline

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
| Business Impact | Kiểm tra workload identity có đang quá rộng hoặc thiếu least privilege không. |
| Current Risk | ServiceAccount/RBAC quá rộng làm tăng blast radius nếu pod bị compromise. |
| Scope | Đọc `templates/serviceaccount.yaml`, chart templates và deploy files; kiểm tra có Role/RoleBinding/ClusterRole không; ghi serviceAccount pattern, workload nào dùng chung identity, permission surface hiện tại, missing/overbroad concerns. |
| Out of Scope | Không tạo RBAC mới. |
| Dependencies | Cần CDO07 nếu sau này muốn audit trail sâu hơn; Nguyên review. |
| Cost / Perf Impact | Không ảnh hưởng runtime vì task này chỉ audit tài liệu. |
| Output / Artifact | `docs/cdo08/week1/serviceaccount-rbac-baseline.md` |
| Consumer | Nhân / Nguyên / CDO07 |

## Definition Of Done Status

| DoD item | Status | Note |
|---|---|---|
| ServiceAccount model documented | Done | Custom chart dùng một ServiceAccount chung theo Helm release name nếu không override. |
| RBAC resources checked | Done | Custom chart/deploy không thấy Role/RoleBinding/ClusterRole/ClusterRoleBinding; observability subcharts có RBAC templates riêng. |
| Risks listed | Done | Risk nằm ở dùng chung identity và chưa có rendered/runtime RBAC evidence. |
| Follow-up proposed | Done | Có recommendation cho render manifest, runtime `kubectl auth can-i`, và tách identity nếu cần. |
| Output artifact linked | Done | File này là artifact chính của task. |
| Minimum coverage satisfied | Partial | ServiceAccount/RBAC đã đủ static coverage; securityContext và network exposure nằm ở artifact liên quan, xem phần Minimum Coverage Cross-Check. |

## Runtime Verification / Blocker

Runtime verification hiện được đánh dấu:

```text
BLOCKED-BY: TF4 deployment readiness
```

Static analysis từ source/chart/docs đã hoàn thành trong scope task. Khi EKS environment sẵn sàng, cần re-run runtime verification trong vòng 24h bằng `helm template`, `kubectl get sa`, `kubectl get role,rolebinding`, `kubectl get clusterrole,clusterrolebinding` và `kubectl auth can-i`.

## Phạm Vi Và Nguồn Bằng Chứng

- Custom chart tạo ServiceAccount khi `serviceAccount.create: true`: `techx-corp-chart/templates/serviceaccount.yaml`.
- Tên ServiceAccount mặc định lấy theo release name nếu `serviceAccount.name` rỗng: `techx-corp-chart/templates/_helpers.tpl`.
- Mọi custom workload dùng `serviceAccountName: {{ include "techx-corp.serviceAccountName" . }}`: `techx-corp-chart/templates/_objects.tpl`.
- Values hiện tại bật `serviceAccount.create: true`, `name: ""`, `annotations: {}`: `techx-corp-chart/values.yaml`.
- Search trong `techx-corp-chart` và `deploy` chỉ thấy ServiceAccount pattern, không thấy Role/RoleBinding/ClusterRole/ClusterRoleBinding custom cho app workload.
- Packaged observability charts có RBAC templates riêng: `opentelemetry-collector`, `prometheus`, `grafana`, `opensearch`; cần render để biết quyền cuối cùng.

## Báo Cáo Hiện Trạng

Custom application components đang dùng chung một ServiceAccount do Helm release tạo ra. Với release name dự kiến `techx-corp`, ServiceAccount mặc định sẽ là `techx-corp`.

Nếu `serviceAccount.create` bị tắt và không set name, helper sẽ dùng Kubernetes `default` ServiceAccount. Hiện tại repo không bật mode này.

Không thấy custom Role/RoleBinding/ClusterRole/ClusterRoleBinding trong `techx-corp-chart/templates` hoặc `deploy`. Điều này nghĩa là app workload tự viết trong chart hiện không được cấp Kubernetes API permissions từ chart này, nhưng vẫn cần verify runtime vì quyền có thể đến từ subchart hoặc manifest ngoài repo.

## Workload Identity Model

| Nhóm | Workload | ServiceAccount hiện tại | Có dùng default ServiceAccount không | Quyền được cấp trong custom chart | Risk |
|---|---|---|---|---|---|
| Critical app path | `frontend`, `frontend-proxy`, `cart`, `checkout`, `payment`, `product-catalog`, `shipping` | Helm release SA, ví dụ `techx-corp` | Không, nếu deploy theo values hiện tại | Không thấy Role/Binding custom | Medium |
| Supporting app | `ad`, `currency`, `email`, `quote`, `recommendation`, `product-reviews`, `llm`, `image-provider` | Helm release SA | Không | Không thấy Role/Binding custom | Low-Medium |
| Async/data path | `accounting`, `fraud-detection`, `kafka`, `postgresql`, `valkey-cart` | Helm release SA | Không | Không thấy Role/Binding custom | Medium |
| Feature/fault path | `flagd` | Helm release SA | Không | Không thấy Role/Binding custom | Medium |
| Load/test tool | `load-generator` | Helm release SA | Không | Không thấy Role/Binding custom | Medium |
| Observability subcharts | `otel-collector`, `prometheus`, `grafana`, `jaeger`, `opensearch` | Subchart-specific SA tùy rendered chart | Cần render để xác nhận | Có RBAC templates trong packaged charts, trừ Jaeger package chủ yếu thấy serviceaccount templates | Medium-High |

## RBAC Resources Found / Not Found

| Area | Result | Evidence | Risk / note |
|---|---|---|---|
| Custom ServiceAccount | Found | `techx-corp-chart/templates/serviceaccount.yaml` | Một SA chung cho custom workload nếu không override. |
| Custom workload `serviceAccountName` | Found | `techx-corp-chart/templates/_objects.tpl` | Mọi Deployment custom dùng cùng helper. |
| Custom Role/RoleBinding | Not found in chart/deploy search | `rg -n "kind: Role|kind: RoleBinding" techx-corp-chart deploy` | App workload hiện không có quyền Kubernetes API từ custom chart; cần runtime verify. |
| Custom ClusterRole/ClusterRoleBinding | Not found in chart/deploy search | `rg -n "kind: ClusterRole|kind: ClusterRoleBinding" techx-corp-chart deploy` | Ít blast radius hơn nếu đúng runtime. |
| OpenTelemetry Collector RBAC | Found in packaged chart | `opentelemetry-collector/templates/clusterrole.yaml`, `clusterrolebinding.yaml`, `serviceaccount.yaml` | Collector thường cần đọc cluster metadata; quyền cần map bằng rendered manifest. |
| Prometheus RBAC | Found in packaged chart | `prometheus/templates/clusterrole.yaml`, `clusterrolebinding.yaml`, `rolebinding.yaml`, `serviceaccount.yaml` | Metrics discovery có thể cần quyền rộng; cần CDO07 evidence. |
| Grafana RBAC | Found in packaged chart | `grafana/templates/role.yaml`, `rolebinding.yaml`, `clusterrole.yaml`, `clusterrolebinding.yaml`, `serviceaccount.yaml` | Cần render để biết RBAC bật/tắt theo values. |
| OpenSearch RBAC | Found in packaged chart | `opensearch/templates/role.yaml`, `rolebinding.yaml`, `serviceaccount.yaml` | Cần render để biết final permission surface. |

## Risk

| Finding | Priority draft | Risk | Affected service/file | Evidence | Proposed follow-up | Compatibility note | Reviewer status |
|---|---|---|---|---|---|---|---|
| Custom app workloads share one ServiceAccount | P1 | Nếu SA này được bind quyền sau này, compromise một pod có thể dùng cùng identity để ảnh hưởng rộng hơn. | All custom workloads via `techx-corp-chart/templates/_objects.tpl`; SA from `templates/serviceaccount.yaml`. | Helper `techx-corp.serviceAccountName` dùng chung `.Values.serviceAccount`; values `name: ""`. | Week 2-3 candidate: tách SA cho `frontend-proxy`, `flagd`, `load-generator`, data services nếu cần quyền riêng. | Docs-only hiện không ảnh hưởng runtime; tách SA sau này cần rollout test. | Needs Info |
| Observability subcharts include RBAC templates that are not yet rendered into an evidence matrix | P1 | Collector/Prometheus/Grafana/OpenSearch có thể có ClusterRole/RoleBinding rộng hơn app workload. | Packaged charts under `techx-corp-chart/charts/*.tgz`. | Tar listing thấy RBAC templates trong collector, prometheus, grafana, opensearch charts. | Render full manifest and map serviceAccount -> Role/ClusterRole -> verbs/resources for CDO07. | Rendering is safe; reducing permissions later can break metrics/logs/dashboards. | Needs Info |
| Fallback to Kubernetes `default` ServiceAccount if `serviceAccount.create=false` and no name is set | P2 | Misconfig có thể làm workload dùng identity khó kiểm soát. | `techx-corp-chart/templates/_helpers.tpl`. | Helper returns `default` when create=false and name empty. | Add review guard/documentation before changing serviceAccount config. | No runtime impact unless values are changed. | Needs Info |

## Proposed Follow-Up

| Priority | Recommendation | Why | Test / evidence |
|---|---|---|---|
| P1 | Render app and observability manifests for RBAC snapshot | CDO07 cần audit trail chính xác, không chỉ source template. | `helm template ...` then search `ServiceAccount`, `Role`, `RoleBinding`, `ClusterRole`, `ClusterRoleBinding`. |
| P1 | Run runtime permission checks for app SA | Xác nhận app SA không có quyền ngoài chart. | `kubectl auth can-i --as=system:serviceaccount:techx-tf4:techx-corp list secrets -n techx-tf4`. |
| P1 | Build serviceAccount-to-workload matrix from live cluster | Xác nhận Deployment đang dùng identity nào. | `kubectl -n techx-tf4 get deploy -o jsonpath=...`. |
| P2 | Consider separate SA per sensitive workload | Giảm blast radius nếu sau này workload cần quyền riêng. | Render manifest and rollout one workload at a time. |
| P2 | Keep app workload RoleBinding-free unless a concrete API need appears | Duy trì least privilege baseline. | Search rendered manifest and runtime RoleBindings. |

## Test Plan

Static checks already completed:

```bash
rg -n "serviceAccount|serviceAccountName|kind: Role|kind: RoleBinding|kind: ClusterRole|kind: ClusterRoleBinding" techx-corp-chart deploy
tar -tzf techx-corp-chart/charts/opentelemetry-collector-0.153.0.tgz
tar -tzf techx-corp-chart/charts/prometheus-29.6.0.tgz
tar -tzf techx-corp-chart/charts/grafana-12.3.0.tgz
tar -tzf techx-corp-chart/charts/opensearch-3.6.0.tgz
```

Runtime checks pending EKS readiness:

```bash
helm template techx-corp ./techx-corp-chart -n techx-tf4 -f deploy/values-app-stamp.yaml -f deploy/values-flagd-sync.yaml > /tmp/techx-rbac.yaml
rg -n "kind: (ServiceAccount|Role|RoleBinding|ClusterRole|ClusterRoleBinding)|serviceAccountName" /tmp/techx-rbac.yaml
kubectl -n techx-tf4 get sa,role,rolebinding
kubectl get clusterrole,clusterrolebinding | rg "techx|otel|prometheus|grafana|opensearch|jaeger"
kubectl -n techx-tf4 get deploy -o jsonpath='{range .items[*]}{.metadata.name}{" => "}{.spec.template.spec.serviceAccountName}{"\n"}{end}'
```

Permission spot checks:

```bash
kubectl auth can-i --as=system:serviceaccount:techx-tf4:techx-corp get pods -n techx-tf4
kubectl auth can-i --as=system:serviceaccount:techx-tf4:techx-corp list secrets -n techx-tf4
```

## Rollback Plan

Không có thay đổi production trong task này.

Nếu follow-up sau này tách SA hoặc giảm RBAC làm lỗi runtime:

- Rollback Helm release:

```bash
helm -n techx-tf4 rollback techx-corp <REVISION>
```

- Nếu chỉ đổi values/template cho SA, revert serviceAccount block và chạy lại `helm upgrade`.
- Nếu observability mất metrics/logs/traces sau khi giảm quyền, rollback riêng release/subchart observability hoặc thêm lại đúng verb/resource tối thiểu.

## Minimum Coverage Cross-Check

| Coverage area | Artifact | Status |
|---|---|---|
| SecurityContext | `docs/cdo08/week1/securitycontext-coverage-matrix.md` | Done for static chart coverage; runtime pending. |
| ServiceAccount/RBAC | File này | Done for static baseline; runtime `kubectl auth can-i` pending. |
| Network exposure | `docs/cdo08/week1/network-exposure-inventory.md` | Required by common minimum coverage; create/commit as separate task artifact. |

## PR Guidance

Branch:

```text
cdo08/week1/security/audit-serviceaccount-va-rbac-baseline
```

Commit / PR title:

```text
docs(cdo08): audit serviceaccount va rbac baseline
```

PR body:

```md
## Summary
- Add CDO08 Week 1 ServiceAccount and RBAC baseline report.

## Why
- Identify whether workload identity and RBAC permissions are too broad before applying changes.
- Reduce blast radius risk if a pod is compromised.
- Keep this task docs-only because RBAC changes require runtime verification and review.

## Changes
- Added `docs/cdo08/week1/serviceaccount-rbac-baseline.md`.
- Documented current ServiceAccount model for custom workloads.
- Checked custom chart/deploy files for Role, RoleBinding, ClusterRole and ClusterRoleBinding.
- Documented observability subchart RBAC templates that require rendered manifest evidence.
- Added P1 finding drafts, runtime blocker, follow-up recommendations and rollback guidance.

## Verification
- [x] Reviewed `techx-corp-chart/templates/serviceaccount.yaml`
- [x] Reviewed `techx-corp-chart/templates/_helpers.tpl`
- [x] Reviewed `techx-corp-chart/templates/_objects.tpl`
- [x] Searched `techx-corp-chart` and `deploy` for ServiceAccount/RBAC resources
- [x] Checked packaged observability charts for RBAC templates
- [ ] Runtime verification pending: BLOCKED-BY TF4 deployment readiness
- [ ] Re-run rendered manifest and `kubectl auth can-i` checks when EKS is ready

## Risk & rollback
- Risk: Low, docs-only change. No production configuration is changed.
- Rollback: Revert this documentation commit.

## Scope
- Team: CDO08
- Area: Platform Security
- Artifact: `docs/cdo08/week1/serviceaccount-rbac-baseline.md`
```
