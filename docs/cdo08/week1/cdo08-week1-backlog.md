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

## Backlog Items

| ID | Epic | Pillar | Priority gợi ý | Owner chính | Finding | Impact | Evidence | Next action | Verification | Rollback / Safety note | Coordination |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CDO08-REL-01 | Epic 08 | Reliability | P1 | Nam | Critical services đều chỉ có `1 replica` | Pod restart, node drain hoặc rollout lỗi có thể làm downtime service quan trọng | `kubectl -n techx-tf4 get deploy`; `techx-corp-chart/values.yaml:27` default `replicas: 1` | Xác định services critical cần tăng replica: `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog` | `kubectl -n techx-tf4 get deploy` sau thay đổi phải thấy replicas tăng và pods ready | Rollback replica count về 1 nếu cost/resource hoặc scheduling lỗi | CDO04 review cost; Nguyên review technical risk |
| CDO08-REL-02 | Epic 08 | Reliability | P1 | Nam | App pods chưa cấu hình readiness/liveness probe | Pod có thể nhận traffic khi chưa ready; app treo nhưng Kubernetes không restart đúng lúc | Runtime jsonpath readiness/liveness trả rỗng; `techx-corp-chart/values.yaml:152-153` chỉ có probe dạng comment | Thiết kế probe tối thiểu cho checkout path và service critical | `kubectl -n techx-tf4 describe pod` hoặc jsonpath phải thấy readiness/liveness configured; rollout không làm pod stuck | Rollback probe config nếu probe sai làm pod không ready | Nguyên review; Quân validate checkout smoke test |
| CDO08-REL-03 | Epic 08 | Reliability | P1 | Phương | PostgreSQL, Valkey, Kafka single replica và namespace app không có PVC | Stateful/data components là SPOF; restart có rủi ro mất hoặc gián đoạn cart/order/event | `kubectl -n techx-tf4 get pvc` không có resources; `postgresql`, `valkey-cart`, `kafka` replicas `1` | Xác nhận dữ liệu nào cần persistent, backup/restore gap, HA candidate | Evidence bằng `kubectl get pvc`, chart values, và restore/backup plan nếu có | Không bật persistence/HA nếu chưa có migration/rollback plan | CDO04 review cost nếu dùng HA/managed service |
| CDO08-REL-05 | Epic 08 | Reliability | P2 | Quyết | Prometheus/OpenSearch persistence disabled | Metric/log/trace có thể mất sau restart; khó điều tra incident | `techx-corp-chart/values.yaml:1174-1175` Prometheus PV disabled; `1222-1223` OpenSearch persistence disabled | Xác định yêu cầu retention và strategy lưu evidence | Restart test hoặc config review chứng minh metric/log retention đáp ứng yêu cầu | Không bật PVC nếu storage class/cost chưa được review | CDO04 review storage cost |
| CDO08-REL-06 | Epic 08 | Reliability | P1 | Quyết | Alertmanager disabled | Thiếu cảnh báo tự động cho checkout/runtime/data; phát hiện sự cố phụ thuộc manual check | `techx-corp-chart/values.yaml:1118-1121` có `alertmanager.enabled: false` | Đề xuất alert tối thiểu cho checkout error rate, latency p95, pod restart, dependency unavailable | Alert rule load được và có test firing hoặc screenshot Grafana/Prometheus | Rollback alert rules nếu noise quá cao | Nam/Phương cung cấp runtime/data signals |
| CDO08-REL-07 | Epic 08 | Reliability | P1 | Quân | Checkout trả lỗi nếu Kafka publish fail sau payment/shipping | Khách có thể thấy checkout fail dù payment/shipping đã xảy ra; rủi ro consistency và support | `techx-corp-platform/src/checkout/main.go:331-347` payment/shipping trước; `387-392` Kafka publish fail thì return `codes.Unavailable` | Nguyên/Quân review design tradeoff consistency vs availability; đề xuất outbox/retry/compensation | Smoke/fault evidence hoặc unit/integration test cho Kafka failure path | Không đổi behavior payment/checkout nếu chưa có rollback và test rõ | Nguyên review technical risk; Phương review Kafka/data impact |
| CDO08-SEC-01 | Epic 07 | Security | P1 | Thủy | Hardcoded DB credentials/API key trong Helm values | Secret/config nhạy cảm nằm trong repo; dễ lộ qua Git/diff/PR; khó rotate an toàn | `techx-corp-chart/values.yaml:182-183`, `581-582`, `618-619`, `600-601`, `870-871` | Phân loại secret thật vs demo/dummy; chọn migration candidates | Secret không còn hardcoded trong values; service vẫn start sau deploy | Rollback về values cũ nếu service không đọc được secret mới | Nhân review security; Deploy Operator hỗ trợ deploy |
| CDO08-SEC-02 | Epic 07 | Security | P1; P0 nếu public expose | Nhân / Quyết | Grafana anonymous user có quyền Admin nếu Grafana được expose lại | Nếu Grafana expose qua ALB/path, người ngoài có thể có quyền admin dashboard/datasource | `techx-corp-chart/values.yaml:1190-1193` anonymous enabled và `org_role: Admin`; `1197` admin password `admin` | Xác nhận Grafana đang ở namespace nào và có public route không; tắt anonymous Admin | Grafana không còn anonymous Admin; login/access policy rõ ràng | Rollback access config nếu team mất access, nhưng không rollback về anonymous Admin nếu public | Quyết xác nhận observability; Deploy Operator nếu cần deploy |
| CDO08-SEC-03 | Epic 07 | Security | P2 | Nhân / Quyết | OpenSearch security plugin disabled | Logs/traces có thể không được bảo vệ ở layer OpenSearch; rủi ro tăng nếu network exposure sai | `techx-corp-chart/values.yaml:1227-1230` có `DISABLE_SECURITY_PLUGIN=true` | Xác nhận OpenSearch chỉ internal hay có access path khác; đề xuất hardening phù hợp | OpenSearch access path được kiểm chứng; security plugin/network policy được review | Không bật security plugin trực tiếp nếu có nguy cơ làm ingestion/query lỗi | Quyết review log pipeline; Nguyên review technical risk |

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
| CDO08-SEC-01 | 4 | 4 | 3 | 2 | 5 | 4 | 22 | P1 | Hardcoded credentials/config là rủi ro security trực tiếp; evidence chỉ rõ file/key; cần phân loại secret thật vs placeholder trước khi migrate | Low cost, nhưng cần rollout/rollback cho secret injection | Approved |
| CDO08-SEC-02 | 3 | 5 | 3 | 1 | 5 | 4 | 21 | P1 | Grafana anonymous Admin là security exposure nghiêm trọng nếu Grafana được expose; hiện cần verify public exposure trước khi nâng P0 | Low cost nếu đổi config; cần tránh làm team mất access | Needs Info |
| CDO08-SEC-03 | 2 | 3 | 2 | 1 | 4 | 4 | 16 | P2 | OpenSearch security plugin disabled là hardening gap; priority phụ thuộc network exposure thực tế nên chưa đủ mạnh để P1 mặc định | Có thể ảnh hưởng ingestion/query nếu bật plugin sai | Needs Info |

## Suggested Week 2-3 Order

| Order | Items | Reason |
|---|---|---|
| Do first | `CDO08-REL-01`, `CDO08-REL-02`, `CDO08-SEC-01`, `CDO08-SEC-02` | Score P1 cao, impact rõ lên availability/security exposure, evidence đủ mạnh hoặc cần verify exposure ngay |
| Do next | `CDO08-REL-03`, `CDO08-REL-06`, `CDO08-REL-07` | Đều là P1 nhưng cần thêm design/cost review hoặc phối hợp owner khác trước khi triển khai |
| Track / verify | `CDO08-REL-05`, `CDO08-SEC-03` | Score P2; cần thêm context về retention hoặc network exposure trước khi nâng priority |

## Open Questions

| Question | Owner cần trả lời |
|---|---|
| Grafana/OpenSearch có public exposure qua ALB/path nào không? | Quyết + Nhân |
| Các DB credentials trong values là demo-only hay secret thật của environment? | Thủy |
| Tăng replica cho critical services có vượt budget/resource không? | Nam + CDO04 |
| Stateful persistence/backup strategy kỳ vọng cho PostgreSQL, Valkey, Kafka là gì? | Phương + CDO04 |
| Checkout Kafka failure sau payment/shipping nên ưu tiên consistency hay user-facing availability? | Quân + Nguyên |

## Definition Of Ready For Week 2 Implementation

Một backlog item chỉ nên chuyển sang triển khai khi có đủ:

- Evidence hiện tại có timestamp.
- Owner chính và owner phối hợp.
- Service/file bị ảnh hưởng.
- Cách verify sau khi sửa.
- Rollback hoặc mitigation nếu thay đổi gây lỗi.
- Priority đã được PM chấm lại bằng `pm-priority-rubric.md`.
