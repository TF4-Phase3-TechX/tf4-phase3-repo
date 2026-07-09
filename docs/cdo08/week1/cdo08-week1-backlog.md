# CDO08 Week 1 Backlog

**Owner:** Hai / CDO08 PM  
**Scope:** Security + Reliability findings from Week 1 scan  
**Last updated:** 2026-07-09  
**Source evidence:**

- `docs/evidence/epic-07-security/security-scan-findings.md`
- `docs/evidence/epic-08-reliability/reliability-scan-findings.md`

## Purpose

Backlog này tổng hợp các findings CDO08 đã scan trong Week 1 để đưa vào Jira tổng và dùng làm input cho kế hoạch Week 2-3.

Week 1 chưa phải là giai đoạn sửa toàn bộ vấn đề. Mục tiêu hiện tại là:

1. Ghi nhận rủi ro Security/Reliability có evidence rõ.
2. Chuẩn hóa từng rủi ro thành backlog item có owner, impact, evidence, cách kiểm tra và rollback note.
3. Dùng rubric ưu tiên để chọn việc nào nên làm trước trong Week 2-3.

## Epic Mapping

| Epic | Pillar | Evidence doc |
|---|---|---|
| Epic 07 | Security | `docs/evidence/epic-07-security/security-scan-findings.md` |
| Epic 08 | Reliability | `docs/evidence/epic-08-reliability/reliability-scan-findings.md` |

## Current Runtime Summary

Scan time gần nhất: `2026-07-09 09:31 ICT`.

Kết quả runtime chính:

- App pods trong namespace `techx-tf4` đang `Running 1/1`.
- Public ALB frontend trả `HTTP/1.1 200 OK`.
- Namespace `techx-tf4` không có PVC.
- Namespace `techx-tf4` không có PodDisruptionBudget.
- `flagd` đang chạy nhưng evidence của Thuỷ cho thấy central sync bị vô hiệu hóa/comment và runtime đọc flag từ file local.

## Backlog Items

| ID | Epic | Pillar | Priority gợi ý | Owner chính | Finding | Impact | Evidence | Next action | Verification | Rollback / Safety note | Coordination |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CDO08-REL-01 | Epic 08 | Reliability | P1 | Nam | Critical services đều chỉ có `1 replica` | Pod restart, node drain hoặc rollout lỗi có thể làm downtime service quan trọng | `kubectl -n techx-tf4 get deploy`; `techx-corp-chart/values.yaml:27` default `replicas: 1` | Xác định services critical cần tăng replica: `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog` | `kubectl -n techx-tf4 get deploy` sau thay đổi phải thấy replicas tăng và pods ready | Rollback replica count về 1 nếu cost/resource hoặc scheduling lỗi | CDO04 review cost; Nguyên review technical risk |
| CDO08-REL-02 | Epic 08 | Reliability | P1 | Nam | App pods chưa cấu hình readiness/liveness probe | Pod có thể nhận traffic khi chưa ready; app treo nhưng Kubernetes không restart đúng lúc | Runtime jsonpath readiness/liveness trả rỗng; `techx-corp-chart/values.yaml:152-153` chỉ có probe dạng comment | Thiết kế probe tối thiểu cho checkout path và service critical | `kubectl -n techx-tf4 describe pod` hoặc jsonpath phải thấy readiness/liveness configured; rollout không làm pod stuck | Rollback probe config nếu probe sai làm pod không ready | Nguyên review; Quân validate checkout smoke test |
| CDO08-REL-03 | Epic 08 | Reliability | P1 | Phương | PostgreSQL, Valkey, Kafka single replica và namespace app không có PVC | Stateful/data components là SPOF; restart có rủi ro mất hoặc gián đoạn cart/order/event | `kubectl -n techx-tf4 get pvc` không có resources; `postgresql`, `valkey-cart`, `kafka` replicas `1` | Xác nhận dữ liệu nào cần persistent, backup/restore gap, HA candidate | Evidence bằng `kubectl get pvc`, chart values, và restore/backup plan nếu có | Không bật persistence/HA nếu chưa có migration/rollback plan | CDO04 review cost nếu dùng HA/managed service |
| CDO08-REL-05 | Epic 08 | Reliability | P2 | Quyết | Prometheus/OpenSearch persistence disabled | Metric/log/trace có thể mất sau restart; khó điều tra incident | `techx-corp-chart/values.yaml:1174-1175` Prometheus PV disabled; `1222-1223` OpenSearch persistence disabled | Xác định yêu cầu retention và strategy lưu evidence | Restart test hoặc config review chứng minh metric/log retention đáp ứng yêu cầu | Không bật PVC nếu storage class/cost chưa được review | CDO04 review storage cost |
| CDO08-REL-06 | Epic 08 | Reliability | P1 | Quyết | Alertmanager disabled | Thiếu cảnh báo tự động cho checkout/runtime/data; phát hiện sự cố phụ thuộc manual check | `techx-corp-chart/values.yaml:1118-1121` có `alertmanager.enabled: false` | Đề xuất alert tối thiểu cho checkout error rate, latency p95, pod restart, dependency unavailable | Alert rule load được và có test firing hoặc screenshot Grafana/Prometheus | Rollback alert rules nếu noise quá cao | Nam/Phương cung cấp runtime/data signals |
| CDO08-REL-07 | Epic 08 | Reliability | P1 | Quân | Checkout trả lỗi nếu Kafka publish fail sau payment/shipping | Khách có thể thấy checkout fail dù payment/shipping đã xảy ra; rủi ro consistency và support | `techx-corp-platform/src/checkout/main.go:331-347` payment/shipping trước; `387-392` Kafka publish fail thì return `codes.Unavailable` | Nguyên/Quân review design tradeoff consistency vs availability; đề xuất outbox/retry/compensation | Smoke/fault evidence hoặc unit/integration test cho Kafka failure path | Không đổi behavior payment/checkout nếu chưa có rollback và test rõ | Nguyên review technical risk; Phương review Kafka/data impact |
| CDO08-REL-08 | Epic 08 | Reliability | P0 | Thuỷ / Nam | `flagd` central sync đang bị vô hiệu hóa và runtime đọc flag từ file local | Các flag điều khiển sự cố/fault injection của BTC có thể không đồng bộ; vi phạm rule flagd và làm sai evidence khi test incident | `deploy/values-flagd-sync.yaml:10-23` sync command/token đang comment; log `flagd` đọc `./etc/flagd/demo.flagd.json`; Secret `flagd-sync` là `placeholder` | Sửa cấu hình sync không dùng shell wrapper; xác nhận token thật; deploy với `deploy/values-flagd-sync.yaml` | `kubectl logs` phải thấy sync từ central provider thành công; các service có `FLAGD_HOST=flagd` vẫn running | Không bật lại command cũ dùng `/bin/sh -c`; rollback về bản local only nếu sync fix làm `flagd` crash, nhưng phải ghi rõ rule risk | Thuỷ owner config; Nam deploy/runbook; Nguyên review |
| CDO08-REL-09 | Epic 08 | Reliability | P1 | Quân | Checkout path thiếu timeout/deadline/retry cho nhiều dependency sync | Dependency chậm có thể kéo dài checkout request, tăng p95 latency hoặc làm cạn worker/goroutine | Quân report F01-F04/G1-G7/G10: `checkout/main.go` dùng gRPC/HTTP call không có per-call timeout; `shipping/quote.rs` dùng `awc::Client::new()` | Thiết kế timeout budget cho cart/product-catalog/currency/payment/shipping/quote; thêm test fault-injection | Fault test dependency chậm phải fail bounded theo timeout thay vì treo request | Rollback từng service timeout nếu gây false failure; không rollout global nếu chưa smoke test checkout | Nguyên review; Quyết hỗ trợ SLO query |
| CDO08-REL-10 | Epic 08 | Reliability | P1 | Nguyên / Quân | Payment khởi tạo OpenFeature provider trong mỗi request thanh toán | Tạo lại provider/kết nối flagd trên hot path có thể làm tăng latency và tạo bottleneck khi checkout load cao | `docs/cdo08/week1/nguyen-architecture-technical-risk-findings.md` CDO08-REL-03; `techx-corp-platform/src/payment/charge.js` gọi `OpenFeature.setProviderAndWait(flagProvider)` trong `charge` | Di chuyển provider init sang startup; giữ per-request chỉ đọc flag value | Load/smoke test payment cho thấy provider init chỉ chạy một lần và checkout vẫn đọc `paymentFailure` flag | Rollback payment change nếu SDK init lifecycle gây service start lỗi | Thuỷ/flagd owner xác nhận flag behavior |
| CDO08-REL-11 | Epic 08 | Reliability | P1 | Phương | Chưa có backup/restore proof cho PostgreSQL, Valkey, Kafka | Khi data/stateful component lỗi, team chưa chứng minh được RPO/RTO hoặc cách khôi phục cart/order/event data | Phương `DR-003`, `DR-010`; hiện không thấy PVC/backup/restore runbook trong namespace app | Tạo backup/restore baseline và test restore tối thiểu hoặc ghi rõ gap cần CDO04 hỗ trợ | Có runbook, evidence backup location, và kết quả restore test hoặc documented blocker | Không thay đổi storage mode nếu chưa có migration/restore plan | CDO04 review cost/storage; Nguyên review risk |
| CDO08-REL-12 | Epic 08 | Reliability | P2 | Nam | Revenue path chưa có PodDisruptionBudget | Khi node drain/maintenance, service critical không có policy bảo vệ voluntary disruption; chỉ nên xử lý sau khi có >=2 replicas/readiness | `kubectl -n techx-tf4 get pdb` trả `No resources found`; Nam `NAM-RUNTIME-007` | Tạo PDB candidates sau khi tăng replica và thêm readiness | `kubectl get pdb` có minAvailable phù hợp và rollout/node drain không bị block sai | Không tạo PDB cho single-replica workload gây kẹt node drain | CDO04 cost; Nguyên review |
| CDO08-SEC-01 | Epic 07 | Security | P1 | Thủy | Hardcoded DB credentials/API key trong Helm values | Secret/config nhạy cảm nằm trong repo; dễ lộ qua Git/diff/PR; khó rotate an toàn | `techx-corp-chart/values.yaml:182-183`, `581-582`, `618-619`, `600-601`, `870-871` | Phân loại secret thật vs demo/dummy; chọn migration candidates | Secret không còn hardcoded trong values; service vẫn start sau deploy | Rollback về values cũ nếu service không đọc được secret mới | Nhân review security; Deploy Operator hỗ trợ deploy |
| CDO08-SEC-02 | Epic 07 | Security | P1; P0 nếu public expose | Nhân / Quyết | Grafana anonymous user có quyền Admin nếu Grafana được expose lại | Nếu Grafana expose qua ALB/path, người ngoài có thể có quyền admin dashboard/datasource | `techx-corp-chart/values.yaml:1190-1193` anonymous enabled và `org_role: Admin`; `1197` admin password `admin` | Xác nhận Grafana đang ở namespace nào và có public route không; tắt anonymous Admin | Grafana không còn anonymous Admin; login/access policy rõ ràng | Rollback access config nếu team mất access, nhưng không rollback về anonymous Admin nếu public | Quyết xác nhận observability; Deploy Operator nếu cần deploy |
| CDO08-SEC-03 | Epic 07 | Security | P1 | Nhân / Quyết | OpenSearch security plugin disabled | Logs/traces có thể không được bảo vệ ở layer OpenSearch; rủi ro tăng nếu network exposure sai | `techx-corp-chart/values.yaml:1227-1230` có `DISABLE_SECURITY_PLUGIN=true`; Nhân `SEC-PLAT-003` | Xác nhận OpenSearch chỉ internal hay có access path khác; đề xuất hardening phù hợp | OpenSearch access path được kiểm chứng; security plugin/network policy được review | Không bật security plugin trực tiếp nếu có nguy cơ làm ingestion/query lỗi | Quyết review log pipeline; Nguyên review technical risk |
| CDO08-SEC-10 | Epic 07 | Security | P1 | Nhân | Container securityContext hardening chưa đồng đều | Nhiều workload có thể chạy theo default image user/root và thiếu guard như `allowPrivilegeEscalation: false`, drop capabilities, seccomp | Nhân `SEC-PLAT-001`; `values.yaml:36` default securityContext rỗng; runtime chỉ 6 components có `runAsNonRoot` | Áp hardening theo batch, ưu tiên stateless services ít rủi ro crash | Runtime pod specs có securityContext; smoke test service pass | Không bật `readOnlyRootFilesystem` global trước khi test write path từng image | Nguyên review; service owner smoke test |
| CDO08-SEC-11 | Epic 07 | Security | P1 | Nhân | Internet-facing HTTP ingress/frontend-proxy có route target admin/observability/flagd-ui | Nếu các route này được expose, admin/observability surface có thể đi qua public ALB HTTP 80 | Nhân `SEC-PLAT-002`; `deploy/ingress.yaml:16-20`; `frontend-proxy/envoy.tmpl.yaml:40-61`, `197-244` | Giới hạn public ALB cho storefront/customer paths; admin UI chuyển private/authenticated access | Route validation chứng minh `/grafana`, `/jaeger`, `/loadgen`, `/feature` không public hoặc có auth | Rollback proxy route change nếu demo flow cần, nhưng không expose admin public mặc định | Quyết/observability owner; Deploy Operator |
| CDO08-SEC-12 | Epic 07 | Security | P1 | Nhân / Quyết | Grafana ClusterRole có quyền đọc Secrets toàn cluster trong rendered observability manifest | Nếu Grafana/sidecar bị compromise hoặc misconfig, blast radius có thể mở tới Secrets ngoài namespace | Nhân `SEC-PLAT-004`; rendered `grafana-clusterrole` có `resources: [configmaps, secrets]`, `verbs: [get, watch, list]` | Scope discovery về namespace observability hoặc bỏ Secret discovery cluster-wide | Rendered manifest không còn ClusterRole đọc Secrets toàn cluster; dashboard provisioning vẫn hoạt động | Rollback sang Role/ClusterRole cũ nếu dashboard provisioning fail, nhưng ghi rõ exception | Quyết review dashboard provisioning |
| CDO08-SEC-13 | Epic 07 | Security | P2 | Nhân | App workloads dùng chung ServiceAccount `techx-corp` | Hiện chưa thấy RBAC rộng, nhưng nếu sau này bind quyền cho shared SA thì mọi workload cùng hưởng quyền | Runtime deployment serviceAccountName đều `techx-corp`; Nhân `SEC-PLAT-005` | Chuẩn bị per-component ServiceAccount override trước khi thêm app RBAC | Service cần RBAC có SA riêng; các service khác không inherit quyền | Không refactor toàn bộ SA nếu chưa có test/deploy window | Nguyên review chart impact |
| CDO08-SEC-14 | Epic 07 | Security | P2 | Nhân | OTLP HTTP receiver CORS quá rộng | Nếu OTLP HTTP endpoint bị expose, browser origins ngoài ý muốn có thể gửi telemetry vào collector | `techx-corp-chart/values.yaml:940-944` allowed origins `http://*`, `https://*`; Nhân `SEC-PLAT-006` | Giới hạn CORS về storefront domain/dev origins được duyệt | OTel browser telemetry vẫn hoạt động với origin hợp lệ; origin ngoài bị chặn | Rollback CORS nếu làm mất web traces, nhưng chỉ trong dev overlay | Quyết/AIO xác nhận telemetry need |

## Rubric-Based Priority Assessment

Priority dưới đây được chấm theo `docs/cdo08/week1/pm-priority-rubric.md`.

Formula:

```
Evidence Adjusted Score = Likelihood + Severity + Business Impact + SLO Impact + Security Impact + Evidence Confidence
```

Cost / Performance Impact không cộng trực tiếp vào điểm, nhưng được dùng làm cờ phối hợp CDO04.

| ID | L | Sev | Biz | SLO | Sec | Evidence | Score | Priority | Vì sao priority như vậy | Cost / Perf flag | Review status |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|
| CDO08-REL-01 | 4 | 4 | 4 | 4 | 1 | 4 | 21 | P1 | Single replica trên nhiều service critical có thể gây downtime khi pod restart, node drain hoặc rollout lỗi; evidence có cả runtime và chart | Needs CDO04 Review vì tăng replica làm tăng resource/cost | Approved |
| CDO08-REL-02 | 4 | 4 | 5 | 5 | 1 | 4 | 23 | P1 | Thiếu readiness/liveness probe trên checkout path có thể route traffic vào pod chưa ready và ảnh hưởng trực tiếp SLO/customer flow | Low cost, nhưng cần test threshold để tránh false restart | Approved |
| CDO08-REL-03 | 3 | 4 | 4 | 4 | 1 | 4 | 20 | P1 | PostgreSQL/Valkey/Kafka là stateful components, đang single replica và không có PVC trong namespace app; rủi ro ảnh hưởng cart/order/event khi restart | Needs CDO04 Review nếu bật persistence, HA hoặc managed service | Approved |
| CDO08-REL-05 | 3 | 3 | 2 | 3 | 1 | 4 | 16 | P2 | Persistence disabled cho Prometheus/OpenSearch ảnh hưởng điều tra incident và evidence retention, nhưng không trực tiếp làm checkout outage | Needs CDO04 Review nếu thêm storage retention | Approved |
| CDO08-REL-06 | 4 | 3 | 3 | 4 | 1 | 4 | 19 | P1 | Alertmanager disabled làm phát hiện checkout/runtime/data issue phụ thuộc manual check; ảnh hưởng khả năng bảo vệ SLO khi vận hành | Low/medium cost; chủ yếu cần thiết kế alert tránh noise | Approved |
| CDO08-REL-07 | 3 | 4 | 5 | 4 | 1 | 4 | 21 | P1 | Checkout có thể trả lỗi sau khi payment/shipping đã xảy ra nếu Kafka publish fail; ảnh hưởng customer-facing flow và consistency | Cần design review, không nhất thiết tăng cost | Approved |
| CDO08-REL-08 | 5 | 5 | 4 | 4 | 5 | 5 | 28 | P0 | flagd central sync bị vô hiệu hóa/comment và runtime đọc local file; đây là protected control-plane/rule risk, đồng thời ảnh hưởng fault injection evidence của nhiều service | Low cost nếu sửa config đúng; high risk nếu command sai làm flagd crash | Approved |
| CDO08-REL-09 | 4 | 4 | 5 | 5 | 1 | 4 | 23 | P1 | Checkout dependency calls thiếu timeout/deadline/retry; impact trực tiếp tới latency/SLO khi dependency chậm, nhưng cần fault evidence trước khi nâng P0 | Có thể tăng latency fail-fast; cần test timeout budget | Approved |
| CDO08-REL-10 | 4 | 3 | 4 | 4 | 1 | 4 | 20 | P1 | Payment init OpenFeature provider trong mỗi request có thể tạo bottleneck trên checkout hot path; source evidence rõ nhưng cần load evidence để định lượng | Low cost; cần đảm bảo SDK init lifecycle đúng | Approved |
| CDO08-REL-11 | 3 | 4 | 4 | 4 | 2 | 4 | 21 | P1 | Backup/restore proof thiếu cho PostgreSQL/Valkey/Kafka; impact lớn khi data/stateful component lỗi, cần làm trước thay đổi storage/HA | Needs CDO04 Review nếu thêm backup storage/managed service | Approved |
| CDO08-REL-12 | 3 | 3 | 3 | 3 | 1 | 4 | 17 | P2 | PDB thiếu là rủi ro voluntary disruption thật, nhưng chỉ có ý nghĩa sau khi service có >=2 replicas và readiness đúng | Có thể block node drain nếu cấu hình sai | Approved |
| CDO08-SEC-01 | 4 | 4 | 3 | 2 | 5 | 4 | 22 | P1 | Hardcoded credentials/config là rủi ro security trực tiếp; evidence chỉ rõ file/key; cần phân loại secret thật vs placeholder trước khi migrate | Low cost, nhưng cần rollout/rollback cho secret injection | Approved |
| CDO08-SEC-02 | 3 | 5 | 3 | 1 | 5 | 4 | 21 | P1 | Grafana anonymous Admin là security exposure nghiêm trọng nếu Grafana được expose; hiện cần verify public exposure trước khi nâng P0 | Low cost nếu đổi config; cần tránh làm team mất access | Needs Info |
| CDO08-SEC-03 | 3 | 4 | 2 | 1 | 4 | 4 | 18 | P1 | OpenSearch security plugin disabled có security impact rõ; vẫn cần network exposure validation trước khi triển khai hardening | Có thể ảnh hưởng ingestion/query nếu bật plugin sai | Needs Info |
| CDO08-SEC-10 | 4 | 3 | 2 | 1 | 4 | 4 | 18 | P1 | SecurityContext thiếu trên nhiều workload là hardening gap diện rộng; nên xử lý theo batch có smoke test | Low/medium cost; crash risk nếu hardening quá mạnh | Approved |
| CDO08-SEC-11 | 3 | 4 | 3 | 2 | 5 | 4 | 21 | P1 | Internet-facing HTTP ingress/proxy route tới admin/observability targets có thể mở attack surface nếu route reachable; cần validate route và lock down sớm | Có thể ảnh hưởng demo access nếu gỡ route | Needs Info |
| CDO08-SEC-12 | 3 | 4 | 2 | 1 | 5 | 4 | 19 | P1 | Grafana ClusterRole đọc Secrets toàn cluster làm tăng blast radius; evidence từ rendered manifest đủ mạnh để đưa vào backlog | Có thể ảnh hưởng dashboard/datasource provisioning | Needs Info |
| CDO08-SEC-13 | 2 | 3 | 2 | 1 | 3 | 4 | 15 | P2 | Shared ServiceAccount chưa có RBAC rộng hiện tại, nhưng là preventive architecture gap trước khi thêm quyền cho app | Low cost nếu chart hỗ trợ gradual override | Approved |
| CDO08-SEC-14 | 2 | 3 | 2 | 1 | 3 | 4 | 15 | P2 | OTLP CORS rộng chỉ thành rủi ro cao nếu OTLP HTTP endpoint bị expose; nên track cùng network exposure hardening | Có thể làm mất browser telemetry nếu restrict sai | Needs Info |

## Suggested Week 2-3 Order

| Order | Items | Reason |
|---|---|---|
| Do first | `CDO08-REL-08`, `CDO08-REL-02`, `CDO08-SEC-01`, `CDO08-SEC-02`, `CDO08-SEC-11` | `REL-08` là P0 vì rule/control-plane flagd; các item còn lại có score cao, impact rõ lên availability/security exposure, hoặc cần verify public exposure ngay |
| Do next | `CDO08-REL-01`, `CDO08-REL-03`, `CDO08-REL-07`, `CDO08-REL-09`, `CDO08-REL-10`, `CDO08-REL-11`, `CDO08-SEC-03`, `CDO08-SEC-10`, `CDO08-SEC-12` | Đều là P1, có evidence tốt nhưng cần design/cost/runtime validation hoặc phối hợp owner khác trước khi triển khai |
| Track / verify | `CDO08-REL-05`, `CDO08-REL-12`, `CDO08-SEC-13`, `CDO08-SEC-14` | P2 hoặc phụ thuộc điều kiện khác; nên track để không mất context nhưng không làm trước P0/P1 |

## Open Questions

| Question | Owner cần trả lời |
|---|---|
| Grafana/OpenSearch có public exposure qua ALB/path nào không? | Quyết + Nhân |
| Các DB credentials trong values là demo-only hay secret thật của environment? | Thủy |
| Tăng replica cho critical services có vượt budget/resource không? | Nam + CDO04 |
| Stateful persistence/backup strategy kỳ vọng cho PostgreSQL, Valkey, Kafka là gì? | Phương + CDO04 |
| Checkout Kafka failure sau payment/shipping nên ưu tiên consistency hay user-facing availability? | Quân + Nguyên |
| Token/cấu hình central flagd sync thật nằm ở đâu và ai được quyền deploy? | Thuỷ + Nam |
| Các route `/grafana`, `/jaeger`, `/loadgen`, `/feature` có public reachable qua ALB hiện tại không? | Nhân + Quyết |

## Definition Of Ready For Week 2 Implementation

Một backlog item chỉ nên chuyển sang triển khai khi có đủ:

- Evidence hiện tại có timestamp.
- Owner chính và owner phối hợp.
- Service/file bị ảnh hưởng.
- Cách verify sau khi sửa.
- Rollback hoặc mitigation nếu thay đổi gây lỗi.
- Priority đã được PM chấm lại bằng `pm-priority-rubric.md`.
