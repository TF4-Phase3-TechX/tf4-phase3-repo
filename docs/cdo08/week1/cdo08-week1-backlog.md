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
- Finding cũ về nhiều service `ImagePullBackOff` không còn là current finding.
- Namespace `techx-tf4` không có PVC.

## Backlog Items

| ID | Epic | Pillar | Priority gợi ý | Owner chính | Finding | Impact | Evidence | Next action | Verification | Rollback / Safety note | Coordination |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CDO08-REL-01 | Epic 08 | Reliability | P1 | Nam | Critical services đều chỉ có `1 replica` | Pod restart, node drain hoặc rollout lỗi có thể làm downtime service quan trọng | `kubectl -n techx-tf4 get deploy`; `techx-corp-chart/values.yaml:27` default `replicas: 1` | Xác định services critical cần tăng replica: `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog` | `kubectl -n techx-tf4 get deploy` sau thay đổi phải thấy replicas tăng và pods ready | Rollback replica count về 1 nếu cost/resource hoặc scheduling lỗi | CDO04 review cost; Nguyên review technical risk |
| CDO08-REL-02 | Epic 08 | Reliability | P1 | Nam | App pods chưa cấu hình readiness/liveness probe | Pod có thể nhận traffic khi chưa ready; app treo nhưng Kubernetes không restart đúng lúc | Runtime jsonpath readiness/liveness trả rỗng; `techx-corp-chart/values.yaml:152-153` chỉ có probe dạng comment | Thiết kế probe tối thiểu cho checkout path và service critical | `kubectl -n techx-tf4 describe pod` hoặc jsonpath phải thấy readiness/liveness configured; rollout không làm pod stuck | Rollback probe config nếu probe sai làm pod không ready | Nguyên review; Quân validate checkout smoke test |
| CDO08-REL-03 | Epic 08 | Reliability | P1 | Phương | PostgreSQL, Valkey, Kafka single replica và namespace app không có PVC | Stateful/data components là SPOF; restart có rủi ro mất hoặc gián đoạn cart/order/event | `kubectl -n techx-tf4 get pvc` không có resources; `postgresql`, `valkey-cart`, `kafka` replicas `1` | Xác nhận dữ liệu nào cần persistent, backup/restore gap, HA candidate | Evidence bằng `kubectl get pvc`, chart values, và restore/backup plan nếu có | Không bật persistence/HA nếu chưa có migration/rollback plan | CDO04 review cost nếu dùng HA/managed service |
| CDO08-REL-05 | Epic 08 | Reliability | P1/P2 | Quyết | Prometheus/OpenSearch persistence disabled | Metric/log/trace có thể mất sau restart; khó điều tra incident | `techx-corp-chart/values.yaml:1174-1175` Prometheus PV disabled; `1222-1223` OpenSearch persistence disabled | Xác định yêu cầu retention và strategy lưu evidence | Restart test hoặc config review chứng minh metric/log retention đáp ứng yêu cầu | Không bật PVC nếu storage class/cost chưa được review | CDO04 review storage cost |
| CDO08-REL-06 | Epic 08 | Reliability | P1 | Quyết | Alertmanager disabled | Thiếu cảnh báo tự động cho checkout/runtime/data; phát hiện sự cố phụ thuộc manual check | `techx-corp-chart/values.yaml:1118-1121` có `alertmanager.enabled: false` | Đề xuất alert tối thiểu cho checkout error rate, latency p95, pod restart, dependency unavailable | Alert rule load được và có test firing hoặc screenshot Grafana/Prometheus | Rollback alert rules nếu noise quá cao | Nam/Phương cung cấp runtime/data signals |
| CDO08-REL-07 | Epic 08 | Reliability | P1 | Quân | Checkout trả lỗi nếu Kafka publish fail sau payment/shipping | Khách có thể thấy checkout fail dù payment/shipping đã xảy ra; rủi ro consistency và support | `techx-corp-platform/src/checkout/main.go:331-347` payment/shipping trước; `387-392` Kafka publish fail thì return `codes.Unavailable` | Nguyên/Quân review design tradeoff consistency vs availability; đề xuất outbox/retry/compensation | Smoke/fault evidence hoặc unit/integration test cho Kafka failure path | Không đổi behavior payment/checkout nếu chưa có rollback và test rõ | Nguyên review technical risk; Phương review Kafka/data impact |
| CDO08-SEC-01 | Epic 07 | Security | P1 | Thủy | Hardcoded DB credentials/API key trong Helm values | Secret/config nhạy cảm nằm trong repo; dễ lộ qua Git/diff/PR; khó rotate an toàn | `techx-corp-chart/values.yaml:182-183`, `581-582`, `618-619`, `600-601`, `870-871` | Phân loại secret thật vs demo/dummy; chọn migration candidates | Secret không còn hardcoded trong values; service vẫn start sau deploy | Rollback về values cũ nếu service không đọc được secret mới | Nhân review security; Deploy Operator hỗ trợ deploy |
| CDO08-SEC-02 | Epic 07 | Security | P1; P0 nếu public expose | Nhân / Quyết | Grafana anonymous user có quyền Admin nếu Grafana được expose lại | Nếu Grafana expose qua ALB/path, người ngoài có thể có quyền admin dashboard/datasource | `techx-corp-chart/values.yaml:1190-1193` anonymous enabled và `org_role: Admin`; `1197` admin password `admin` | Xác nhận Grafana đang ở namespace nào và có public route không; tắt anonymous Admin | Grafana không còn anonymous Admin; login/access policy rõ ràng | Rollback access config nếu team mất access, nhưng không rollback về anonymous Admin nếu public | Quyết xác nhận observability; Deploy Operator nếu cần deploy |
| CDO08-SEC-03 | Epic 07 | Security | P1/P2 | Nhân / Quyết | OpenSearch security plugin disabled | Logs/traces có thể không được bảo vệ ở layer OpenSearch; rủi ro tăng nếu network exposure sai | `techx-corp-chart/values.yaml:1227-1230` có `DISABLE_SECURITY_PLUGIN=true` | Xác nhận OpenSearch chỉ internal hay có access path khác; đề xuất hardening phù hợp | OpenSearch access path được kiểm chứng; security plugin/network policy được review | Không bật security plugin trực tiếp nếu có nguy cơ làm ingestion/query lỗi | Quyết review log pipeline; Nguyên review technical risk |

## Suggested Week 2-3 Priority

| Priority bucket | Items | Reason |
|---|---|---|
| Do first | `CDO08-REL-01`, `CDO08-REL-02`, `CDO08-SEC-01`, `CDO08-SEC-02` | Impact trực tiếp tới availability/security exposure; có evidence rõ |
| Do next | `CDO08-REL-03`, `CDO08-REL-06`, `CDO08-REL-07` | Quan trọng nhưng cần thêm design review hoặc phối hợp owner khác |
| Track / verify | `CDO08-REL-05`, `CDO08-SEC-03` | Cần thêm context về retention hoặc exposure trước khi triển khai |

## Items Not Treated As Current Backlog

### Historical ImagePullBackOff

Screenshot trước đó từng cho thấy nhiều service `ImagePullBackOff`, nhưng scan hiện tại không còn thấy lỗi này.

Current evidence:

```bash
kubectl -n techx-tf4 get pods -o wide
```

Kết quả hiện tại:

- Tất cả app pods trong `techx-tf4` đều `Running 1/1`.

Decision:

- Không đưa vào backlog như current issue.
- Nếu owner muốn giữ, cần ghi thành historical incident với timeline, root cause và deploy/commit đã fix.

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
