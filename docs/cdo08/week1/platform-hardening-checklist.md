# CDO08 Week 1 - Platform Hardening Checklist

Owner: Nhân  
Assignee: Nhân  
Area / Ownership: Platform Security  
Pillar: Security  
Priority: P2  
Status: Needs Info - Static Analysis Complete, Review Pending  
Reviewer: Nguyên  
Review Gate: Approved / Needs Info / Defer  
ADR Required: Yes

## Task Metadata

| Field | Value |
|---|---|
| Business Impact | Biến audit security thành checklist implementation an toàn cho Tuần 2-3. |
| Current Risk | Nếu chỉ audit mà không chuyển thành checklist, security work sẽ khó thực thi và khó kiểm chứng. |
| Scope | Từ securityContext/RBAC/exposure audits, tạo checklist hardening gồm candidate, affected components, expected security benefit, compatibility risk, test command/check, rollback plan, ADR need, priority. |
| Out of Scope | Không apply hardening. |
| Dependencies | Phụ thuộc 3 task audit security; cần Nam/Nguyên review. |
| Cost / Perf Impact | Không ảnh hưởng runtime vì task này chỉ audit/tổng hợp tài liệu. |
| Output / Artifact | `docs/cdo08/week1/platform-hardening-checklist.md` |
| Consumer | Nhân / Nguyên / Nam |

## Definition Of Done Status

| DoD item | Status | Note |
|---|---|---|
| Checklist có candidates cụ thể | Done | Candidate gắn với service/file/risk cụ thể, không chỉ best practice chung. |
| Mỗi candidate có test/rollback | Done | Có verification command/check và rollback plan cho từng nhóm. |
| ADR need marked | Done | Mỗi candidate có cột ADR. |
| Review completed | Needs Info | Chờ Nguyên/Nam review, đặc biệt các item có runtime compatibility risk. |
| Output artifact linked | Done | File này là artifact chính của task. |
| Minimum coverage satisfied | Partial | Checklist bao phủ securityContext, ServiceAccount/RBAC và network exposure theo static evidence; runtime verification còn pending. |

## Runtime Verification / Blocker

Runtime verification hiện được đánh dấu:

```text
BLOCKED-BY: TF4 deployment readiness
```

Static analysis từ source/chart/docs đã hoàn thành trong scope task. Khi EKS environment sẵn sàng, cần re-run runtime verification trong vòng 24h bằng `helm template`, `kubectl get svc,ingress`, `kubectl get deploy`, `kubectl auth can-i`, rollout/smoke checks và public path checks.

## Evidence Inputs

Checklist này tổng hợp từ các audit sau:

| Area | Artifact / source | Static evidence used |
|---|---|---|
| SecurityContext | `docs/cdo08/week1/securitycontext-coverage-matrix.md`; `techx-corp-chart/values.yaml`; `techx-corp-chart/templates/_objects.tpl` | `default.securityContext: {}`; only selected workloads have `runAsUser/runAsGroup/runAsNonRoot`; no baseline `allowPrivilegeEscalation`, `capabilities.drop`, `readOnlyRootFilesystem`. |
| ServiceAccount/RBAC | `docs/cdo08/week1/serviceaccount-rbac-baseline.md`; `techx-corp-chart/templates/serviceaccount.yaml`; `_helpers.tpl`; `_objects.tpl` | Custom workloads share one Helm release ServiceAccount; custom chart/deploy search does not show app Role/Binding; observability subcharts include RBAC templates that need rendering. |
| Network exposure | `docs/cdo08/week1/network-exposure-inventory.md`; `deploy/ingress.yaml`; `frontend-proxy/envoy.tmpl.yaml`; `values.yaml` | Internet-facing ALB routes `/` to `frontend-proxy`; Envoy routes ops/admin-like paths `/grafana/`, `/jaeger/`, `/loadgen/`, `/feature`, `/otlp-http/`, `/flagservice/`. |

## Làm Trước Vì Tương Đối An Toàn

| Priority | Candidate | Affected components/files | Security benefit | Compatibility risk | Verification | Rollback | ADR? |
|---|---|---|---|---|---|---|---|
| P1 | Render and store security/RBAC/exposure evidence snapshots | `techx-corp-chart`, `deploy`, generated manifests for CDO07 evidence | Chốt baseline trước khi sửa, tránh tranh luận bằng cảm tính | Low; docs/evidence only | `helm template techx-corp ./techx-corp-chart ...`; search `securityContext`, RBAC kinds, Service/Ingress | Delete/regenerate evidence artifact | No |
| P1 | Add `allowPrivilegeEscalation: false` to default custom container securityContext candidate | `techx-corp-chart/values.yaml`; all custom app workloads | Giảm khả năng leo thang quyền khi container bị compromise | Low-Medium; usually safer than UID/read-only changes but still needs canary | `helm template`; rollout `frontend`, `cart`, `checkout`; smoke storefront/checkout | Remove field or Helm rollback | No |
| P1 | Restrict public access to ops/admin-like paths while keeping storefront public | `deploy/ingress.yaml`, `frontend-proxy` route policy, paths `/grafana/`, `/jaeger/`, `/loadgen/`, `/feature` | Giảm attack surface public cho observability/admin tools | Medium; ops access workflow can break | Public `curl -I` for `/`, `/images/`, `/grafana/`, `/jaeger/ui/`, `/loadgen/`; confirm port-forward/private path | Revert route/Ingress rule; use port-forward during fix | Yes |
| P1 | Review and remove Grafana anonymous Admin from public path | `techx-corp-chart/values.yaml` Grafana config; Envoy `/grafana/` | Tránh public admin-level dashboard access | Medium; team may need credentials/private access | Login/access smoke test; verify dashboards still load for intended users | Restore prior Grafana auth values or rollback release | Yes |
| P1 | Produce live ServiceAccount/RBAC matrix before changing permissions | `kubectl get sa,role,rolebinding`; subchart rendered RBAC | Xác nhận quyền thực tế và giảm nguy cơ cắt nhầm quyền observability | Low; read-only verification | `kubectl auth can-i --as=...`; rendered RBAC map | No production rollback needed | No |

## Cần Test Kỹ Trước Khi Apply Rộng

| Priority | Candidate | Affected components/files | Security benefit | Compatibility risk | Verification | Rollback | ADR? |
|---|---|---|---|---|---|---|---|
| P1 | Add `seccompProfile.type: RuntimeDefault` at pod level | `default.podSecurityContext` or per component podSecurityContext | Giảm syscall surface mặc định | Medium; can vary by runtime/image | Canary on `frontend`, `cart`, `checkout`; check logs, rollout, smoke checkout | Remove `podSecurityContext` field or Helm rollback | No |
| P1 | Add `runAsNonRoot` to missing critical stateless services | `cart`, `checkout`, `product-catalog`, `shipping`, plus `ad`, `currency`, `email`, `recommendation` | Tránh app chạy root trong container | Medium-High; wrong UID/GID can CrashLoop or break writable paths | Identify image user/UID from Dockerfile/image; rollout one service at a time | Revert service `securityContext` block | No |
| P1 | Split ServiceAccounts for sensitive workloads if any Kubernetes API permissions are required | `frontend-proxy`, `flagd`, `load-generator`, data services, chart SA helper/values | Giảm blast radius khi một pod bị compromise | Medium; template/values mistake can affect rollout | Render Deployment `serviceAccountName`; `kubectl auth can-i`; rollout per workload | Revert to shared ServiceAccount | Yes |
| P2 | Drop Linux capabilities for stateless app containers | Custom app containers in `values.yaml` | Giảm kernel capability mặc định | Medium; proxy/data images may need exceptions | Add `capabilities.drop: ["ALL"]` for stateless canary; rollout and logs | Remove capability block for failing service | No |
| P2 | Restrict `/otlp-http/` browser telemetry ingest route | `frontend-proxy/envoy.tmpl.yaml`; OTel collector CORS in `values.yaml`; frontend public OTLP endpoint | Giảm abuse surface cho telemetry ingest | Medium; browser traces may stop | Browser flow smoke; collector logs; check traces in Jaeger/Grafana | Revert `/otlp-http/` route/CORS change | Yes |
| P2 | Validate `flagd` and `/flagservice/` exposure contract before tightening | `flagd`, Envoy `/flagservice/`, protected fault-injection path | Kiểm soát public flag exposure without breaking required incident mechanism | Medium-High; changing flag path can violate Phase 3 rules | Verify app/browser flag evaluation; confirm protected path with Nguyên | Revert proxy rule immediately | Yes |
| P2 | Design NetworkPolicy by dependency graph | App namespace services: checkout/cart/payment/product-catalog/postgresql/kafka/valkey/observability | Giảm lateral movement between compromised pods | High; missing egress/ingress breaks app/telemetry | Apply in staging/canary; E2E checkout/browse; observability smoke | Delete NetworkPolicy or rollback manifest | Yes |

## Để Sau Hoặc Spike Vì Rủi Ro Crash Cao

| Priority | Candidate | Affected components/files | Security benefit | Why defer / spike | Verification when ready | Rollback | ADR? |
|---|---|---|---|---|---|---|---|
| P3 | Add `readOnlyRootFilesystem: true` service-by-service | All custom workloads | Chặn ghi filesystem ngoài mount được kiểm soát | High crash risk: many runtimes need temp/cache/log/write paths | Writable path inventory; add `emptyDir` only where needed; rollout one service | Disable field or restore writable mount | No |
| P3 | Harden Postgres/Kafka/Valkey with non-root/capability/read-only changes | `postgresql`, `kafka`, `valkey-cart` | Giảm data/broker compromise blast radius | Data/broker images are sensitive to UID, volume and writable path behavior | Restart tests, connection tests, metrics checks | Revert component securityContext | Yes if changing data path/security model |
| P3 | Enable OpenSearch security plugin | `opensearch.extraEnvs`; Grafana datasource; collector exporter | Bảo vệ logs/search API if exposure changes later | Can break datasource/exporter until credentials are configured | Test collector log pipeline and Grafana dashboards | Restore `DISABLE_SECURITY_PLUGIN: true` temporarily | Yes |
| P3 | Re-enable `flagd-ui` with protected access | `flagd` sidecar, `/feature` route | Gives managed UI only if needed | Current values disable it; public unauthenticated UI is high risk and image availability was noted as missing | Build/push image, private/auth access, verify flag config path | Disable sidecar again | Yes |

## P0/P1 Follow-Up Candidate Drafts

| Follow-up task | Priority draft | Risk | Affected service/file | Evidence | Proposed fix | Test | Rollback | Dependencies | Reviewer status |
|---|---|---|---|---|---|---|---|---|---|
| Add low-risk container security baseline for custom stateless apps | P1 | Missing `allowPrivilegeEscalation: false` and non-root gaps increase blast radius. | `techx-corp-chart/values.yaml`; `_objects.tpl`; critical workloads `cart`, `checkout`, `product-catalog`, `shipping`. | `default.securityContext: {}`; limited services have `runAsNonRoot`; no baseline privilege escalation/capability fields found. | Add `allowPrivilegeEscalation: false`; canary `runAsNonRoot` for services with known UID. | Helm render, rollout status, app smoke, logs. | Remove changed fields or Helm rollback. | Nam for runtime compatibility; Nguyên review. | Needs Info |
| Restrict public ops/observability routes behind frontend-proxy | P1 | Grafana/Jaeger/loadgen/feature paths may be reachable via internet-facing ALB. | `deploy/ingress.yaml`; `frontend-proxy/envoy.tmpl.yaml`; Grafana values. | ALB `internet-facing` routes `/` to `frontend-proxy`; Envoy routes ops paths; Grafana anonymous Admin configured. | Split public/private routes or add auth/allowlist; keep storefront public. | Public path `curl -I`; port-forward/private access smoke. | Revert route/Ingress/Auth change. | Quyết for observability routes; Nguyên risk review; possibly CDO04 for ALB changes. | Needs Info |
| Render and review observability RBAC permission surface | P1 | Subchart ClusterRole/RoleBinding may be broad and is not yet mapped to actual workload identity. | `techx-corp-chart/charts/*`; rendered manifests; live RBAC. | Packaged collector/prometheus/grafana/opensearch charts include RBAC templates; custom app chart has shared SA. | Create RBAC matrix serviceAccount -> role -> verbs/resources; reduce only after proof. | `helm template`, `kubectl auth can-i`, dashboard/metrics/log smoke. | Restore previous RBAC/subchart values. | CDO07 audit trail; Nguyên review. | Needs Info |

## Minimum Coverage Cross-Check

| Coverage area | Artifact | Status |
|---|---|---|
| SecurityContext | `docs/cdo08/week1/securitycontext-coverage-matrix.md` | Referenced for container hardening candidates; static source evidence also checked from chart values/templates. |
| ServiceAccount/RBAC | `docs/cdo08/week1/serviceaccount-rbac-baseline.md` | Referenced for identity/RBAC candidates; static source evidence also checked from chart templates/subchart package list. |
| Network exposure | `docs/cdo08/week1/network-exposure-inventory.md` | Referenced for exposure candidates; present on this branch and used as source. |

## Review Plan

| Reviewer / input | What to review | Status |
|---|---|---|
| Nguyên | Risk ranking, P1 follow-up candidates, review gate | Needs Info |
| Nam | Runtime compatibility for securityContext changes and rollout sequencing | Needs Info |
| Quyết | Observability route intent for Grafana/Jaeger/loadgen/OTLP | Needs Info |
| CDO07 | RBAC/evidence audit trail if follow-up requires formal evidence | Needs Info |
| CDO04 | ALB/Ingress or cost/perf tradeoff if route split changes infra | Defer until implementation planning |

## PR Guidance

Branch:

```text
cdo08/week1/security/de-xuat-baseline-hardening-checklist
```

Commit / PR title:

```text
docs(cdo08): de xuat baseline hardening checklist
```

PR body:

```md
## Summary
- Add CDO08 Week 1 platform hardening checklist and backlog candidates.

## Why
- Convert security audit findings into concrete Week 2-3 hardening candidates.
- Prioritize safe changes first while deferring high crash-risk changes for spike/canary.
- Keep this task docs-only because implementation needs runtime verification and review.

## Changes
- Added `docs/cdo08/week1/platform-hardening-checklist.md`.
- Grouped hardening candidates into safe-first, test-carefully and defer/spike sections.
- Added affected components, security benefit, compatibility risk, verification, rollback, ADR need and priority for each candidate.
- Added P1 follow-up task drafts covering container hardening, network exposure and RBAC evidence.

## Verification
- [x] Reviewed securityContext findings from chart values/templates
- [x] Reviewed ServiceAccount/RBAC findings from chart templates and packaged subchart evidence
- [x] Reviewed network exposure findings from Ingress and Envoy routes
- [x] Confirmed checklist is docs-only and does not apply hardening
- [ ] Runtime verification pending: BLOCKED-BY TF4 deployment readiness
- [ ] Review with Nguyên/Nam before Week 2-3 implementation

## Risk & rollback
- Risk: Low, docs-only change. No production configuration is changed.
- Rollback: Revert this documentation commit.

## Scope
- Team: CDO08
- Area: Platform Security
- Artifact: `docs/cdo08/week1/platform-hardening-checklist.md`
```
