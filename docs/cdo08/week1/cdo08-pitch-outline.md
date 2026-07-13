# CDO08 Week 1 Pitch Outline

**Owner:** Hai / CDO08 PM  
**Scope:** Security + Reliability priority pitch  
**Duration target:** 15-20 minutes  
**Input docs:**

- `docs/cdo08/week1/cdo08-week1-backlog.md`
- `docs/cdo08/week1/pm-priority-rubric.md`
- `docs/requirements/onboarding/PITCH_GUIDE.md`
- `docs/requirements/onboarding/INCIDENT_HISTORY.md`
- `docs/evidence/epic-07-security/security-scan-findings.md`
- `docs/evidence/epic-08-reliability/reliability-scan-findings.md`

## 1. Main Narrative

CDO08 không pitch rằng team đã scan nhiều file. CDO08 pitch một câu chuyện rõ:

> Hệ thống hiện đang chạy, nhưng baseline Security/Reliability còn mỏng ở đúng những vùng từng gây incident: checkout chịu tải, mất state khi node reschedule, deploy không an toàn, và protected control path `flagd`. Week 1 của CDO08 đã biến các rủi ro này thành backlog có evidence, priority theo rubric, owner, verification và rollback note.

Thông điệp chính:

1. App hiện `Running`, public frontend trả `200 OK`, nhưng “đang chạy” chưa có nghĩa là “đủ resilient”.
2. Các rủi ro cao nhất nằm ở control path `flagd`, readiness/probe, secret/config, public/admin exposure, checkout timeout/consistency, stateful data durability.
3. Thứ tự ưu tiên không dựa vào cảm tính. Backlog dùng rubric: Likelihood, Severity, Business Impact, SLO Impact, Security Impact, Evidence Confidence.
4. CDO08 cố ý defer một số việc P2 vì chưa trực tiếp đe dọa checkout/security exposure hoặc còn phụ thuộc điều kiện khác.

## 2. Opening - 2 Minutes

### What CDO08 Owns

CDO08 phụ trách 2 pillar:

- **Reliability:** checkout/customer flow vẫn hoạt động khi pod restart, dependency chậm, deploy, node drain hoặc stateful component lỗi.
- **Security:** secret/config không lộ, quyền không quá rộng, admin/observability surface không bị expose sai, protected control path không bị phá.

### Why Checkout And SLO Matter

Theo onboarding pitch guide, priority phải quy về risk x business impact. Checkout là revenue-critical flow:

- Checkout lỗi hoặc chậm ảnh hưởng trực tiếp khách hàng và doanh thu.
- Incident history từng có checkout success rate tụt còn khoảng 95% và p95 latency tăng vài giây khi tải cao.
- Cart state từng mất sau node reschedule.
- Payment từng lỗi trong deploy vì traffic vào pod chưa ready.

Vì vậy CDO08 ưu tiên các việc bảo vệ checkout, data state, deploy safety, observability evidence và security exposure.

## 3. Current Baseline - 2 Minutes

Runtime summary gần nhất:

- App pods trong namespace `techx-tf4` đang `Running 1/1`.
- Public ALB frontend trả `HTTP/1.1 200 OK`.
- Namespace `techx-tf4` không có PVC.
- Namespace `techx-tf4` không có PodDisruptionBudget.
- `flagd` đang chạy nhưng evidence cho thấy central sync bị vô hiệu hóa/comment và runtime đọc flag local.

Interpretation:

- Đây không phải pitch outage.
- Đây là pitch baseline risk: hệ thống chạy ở happy path nhưng thiếu guardrail cho incident, deploy, overload và security exposure.

## 4. Priority Rubric - 2 Minutes

CDO08 dùng `pm-priority-rubric.md`.

Formula:

```text
Evidence Adjusted Score =
Likelihood + Severity + Business Impact + SLO Impact + Security Impact + Evidence Confidence
```

Priority mapping:

| Priority | Meaning |
|---|---|
| P0 | Score >= 24, hoặc vi phạm flagd rule/protected path, trực tiếp làm hỏng checkout, mất dữ liệu, lộ secret thật |
| P1 | Score 19-23, hoặc risk có evidence khá chắc trên service critical |
| P2 | Score 14-18, useful backlog candidate nhưng không cần làm trước P0/P1 |
| P3 | Score <= 13 hoặc cleanup/defer |

Cost/performance không cộng trực tiếp vào score, nhưng dùng để flag CDO04 review.

## 5. Top Risks To Pitch - 8 Minutes

### P0 - `CDO08-REL-08`: flagd central sync local-only

**Owner:** Thuỷ / Nam  
**Risk:** `flagd` central sync bị comment/disabled, runtime đọc flag từ local file, token runtime là placeholder.  
**Why it matters:** `flagd` là protected control path để BTC điều khiển fault injection/incident flags. Nếu sync không đúng, incident evidence và control behavior có thể sai.  
**Evidence:** `deploy/values-flagd-sync.yaml:10-23`, runtime log đọc `./etc/flagd/demo.flagd.json`, Secret `flagd-sync` placeholder.  
**Rubric:** Score 28, P0 vì vi phạm flagd rule/protected path và Evidence Confidence 5.  
**Next:** sửa sync command không dùng shell wrapper, xác nhận token thật, verify logs sync central provider.  
**Rollback/safety:** không bật lại command cũ dùng `/bin/sh -c`; nếu fix làm `flagd` crash thì rollback local-only nhưng phải ghi rõ rule risk.

Pitch line:

> Đây là item làm trước vì nếu control path sự cố sai, mọi evidence fault injection phía sau đều không đáng tin.

### P1 - `CDO08-REL-02`: missing readiness/liveness probes

**Owner:** Nam  
**Risk:** App pods thiếu readiness/liveness probe.  
**Why it matters:** Incident history INC-3 từng có payment lỗi trong deploy vì traffic vào pod chưa sẵn sàng.  
**Evidence:** runtime jsonpath readiness/liveness rỗng; chart chỉ có probe dạng comment.  
**Rubric:** Score 23, P1 vì Business Impact 5 và SLO Impact 5 trên checkout/customer flow.  
**Next:** thiết kế probe tối thiểu cho `frontend-proxy`, `frontend`, `checkout`, `cart`, `payment`, `shipping`, `product-catalog`.  
**Rollback/safety:** rollback probe config nếu threshold sai làm pod không ready.

Pitch line:

> Đây là guardrail deploy safety trước khi Week 2-3 bắt đầu thay đổi hệ thống.

### P1 - `CDO08-SEC-01`: hardcoded sensitive config

**Owner:** Thuỷ  
**Risk:** DB credentials/API key/config nhạy cảm nằm trong Helm values/source config.  
**Why it matters:** Secret trong repo dễ lộ qua Git/diff/PR và khó rotate an toàn.  
**Evidence:** `values.yaml` có DB connection string/password/API key candidates.  
**Rubric:** Score 22, P1 vì Security Impact 5 và evidence rõ. Chưa P0 vì cần phân loại secret thật vs placeholder.  
**Next:** phân loại real secret/placeholder, đề xuất migration candidates.  
**Rollback/safety:** không migrate nếu chưa có deploy/rollback plan.

Pitch line:

> Đây là security hygiene có evidence rõ, nhưng cần phân loại trước khi sửa để tránh phá runtime.

### P1/P0-if-exposed - `CDO08-SEC-02`: Grafana anonymous Admin

**Owner:** Nhân / Quyết  
**Risk:** Grafana anonymous user có quyền Admin, admin password mặc định.  
**Why it matters:** Nếu Grafana reachable public, người ngoài có thể có quyền admin dashboard/datasource.  
**Evidence:** `auth.anonymous.enabled: true`, `org_role: Admin`, `adminPassword: admin`.  
**Rubric:** Score 21, P1; nâng P0 nếu public exposure được xác nhận.  
**Next:** xác nhận route/exposure, tắt anonymous Admin nếu reachable.  
**Rollback/safety:** không rollback về anonymous Admin nếu public.

Pitch line:

> Đây là item security có điều kiện: hiện P1 vì config nguy hiểm, P0 nếu chứng minh public reachable.

### P1 - `CDO08-SEC-11`: frontend-proxy admin/observability route exposure

**Owner:** Nhân  
**Risk:** Public ALB route `/` vào `frontend-proxy`; proxy có route target admin/observability/flagd-ui.  
**Why it matters:** Khi backend admin/observability được bật lại, public proxy có thể expose surface không dành cho khách.  
**Evidence:** `deploy/ingress.yaml`, `frontend-proxy/envoy.tmpl.yaml` routes `/loadgen/`, `/jaeger/`, `/grafana/`, `/flagservice/`, `/feature`.  
**Rubric:** Score 21, P1 vì Security Impact 5; Needs Info vì cần runtime route validation.  
**Next:** validate route public reachability, lock down admin/observability paths.  
**Rollback/safety:** giữ storefront path, chỉ private/auth cho admin UI.

Pitch line:

> Đây không phải finding “observability đang tắt”; đây là route exposure risk khi các backend được bật lại.

## 6. Next Priority Group - 4 Minutes

Các item P1 tiếp theo:

| ID | Owner | Why next |
|---|---|---|
| `CDO08-REL-01` | Nam | Critical services single replica; liên hệ INC-2/node reschedule; cần CDO04 cost review |
| `CDO08-REL-03` | Phương | PostgreSQL/Valkey/Kafka single replica/no PVC; ảnh hưởng cart/order/event data |
| `CDO08-REL-07` | Quân | Checkout có thể trả lỗi sau payment/shipping nếu Kafka publish fail; consistency risk |
| `CDO08-REL-09` | Quân | Checkout dependency timeout/deadline gaps; liên hệ INC-1 checkout slow under load |
| `CDO08-REL-10` | Nguyên / Quân | Payment init OpenFeature provider per request; hot path latency risk |
| `CDO08-REL-11` | Phương | Backup/restore proof missing; cần trước khi thay đổi persistence/HA |
| `CDO08-SEC-03` | Nhân / Quyết | OpenSearch security plugin disabled; P1/Needs Info vì phụ thuộc exposure |
| `CDO08-SEC-10` | Nhân | SecurityContext hardening gap diện rộng; cần staged rollout |
| `CDO08-SEC-12` | Nhân / Quyết | Grafana ClusterRole đọc Secrets toàn cluster; privilege blast-radius risk |

Positioning:

- Nhóm này đủ quan trọng để đưa vào kế hoạch Week 2-3.
- Một số cần CDO04 vì cost/resource/storage.
- Một số cần CDO07 vì evidence/ADR/audit trail nếu đổi quyền hoặc security posture.
- Một số cần thêm runtime validation trước khi triển khai.

## 7. Deferred / Track Items - 2 Minutes

CDO08 cố ý chưa làm trước các item này:

| ID | Owner | Why defer |
|---|---|---|
| `CDO08-REL-05` | Quyết | Observability retention gap là P2: ảnh hưởng điều tra incident, chưa trực tiếp làm checkout outage |
| `CDO08-REL-12` | Nam | PDB chỉ có ý nghĩa sau khi service có >=2 replicas và readiness đúng |
| `CDO08-SEC-13` | Nhân | Shared ServiceAccount là preventive hardening; hiện chưa thấy app RBAC rộng |
| `CDO08-SEC-14` | Nhân | OTLP CORS rộng phụ thuộc endpoint exposure; track cùng network exposure validation |

Pitch line:

> CDO08 không bỏ qua các item này. Chúng tôi để sau vì impact thấp hơn hoặc phụ thuộc điều kiện trước đó. Đây là quyết định ưu tiên, không phải thiếu awareness.

## 8. Cross-Team Dependencies

| Team | Need |
|---|---|
| CDO04 | Review cost/resource cho tăng replica, storage/PVC, HA/managed service, retention |
| CDO07 | Review evidence, ADR, audit trail nếu đổi RBAC, security posture, secret handling |
| AIO01 | Confirm impact nếu scale/harden LLM/product-reviews/AI-related services |
| Deploy Operator | Helm changes, flagd sync deployment, rollback execution |

## 9. Suggested Slide Flow

1. **CDO08 mission:** protect Security + Reliability for customer/revenue-critical system.
2. **System reality:** app running, but resilience/security baseline still thin.
3. **Incident history:** checkout overload, cart loss on reschedule, payment deploy failure.
4. **Rubric:** how CDO08 ranks risk.
5. **Top 5 priorities:** `REL-08`, `REL-02`, `SEC-01`, `SEC-02`, `SEC-11`.
6. **Next P1 group:** runtime/data/checkout/security hardening.
7. **Deferred items:** what we intentionally do later and why.
8. **Ask / dependencies:** CDO04 cost review, CDO07 evidence/ADR, Deploy Operator for safe rollout.

## 10. Q&A Notes

### PM Questions

**Q: Khách được gì nếu làm mấy việc hạ tầng này?**  
A: Khách được checkout/cart/payment ổn định hơn khi deploy, pod restart, dependency chậm hoặc node reschedule. Các item P1 như probes, replica, timeout và data durability đều bảo vệ luồng khách thấy trực tiếp.

**Q: Vì sao không làm feature trước?**  
A: Phase 3 Week 1 là chọn đúng backlog ưu tiên. Incident history cho thấy hệ thống từng mất checkout success, mất cart và lỗi payment khi deploy. Nếu baseline này không chắc, feature mới vẫn có thể fail khi có tải hoặc deploy.

**Q: Vì sao `flagd` là P0 dù khách không thấy?**  
A: `flagd` là protected control path cho fault injection/evidence. Nếu control path sai, mọi test incident phía sau có thể không đáng tin và có thể vi phạm rule. Đây là foundation để pitch các reliability findings khác.

### CFO Questions

**Q: Tăng replica/PVC/retention có vượt budget không?**  
A: Chưa rollout ngay. Backlog đánh dấu item cần CDO04 review. Thứ tự đề xuất là low-cost/high-impact trước: fix flagd config/probes/security config validation, sau đó mới replica/storage có cost tradeoff.

**Q: ROI của replica/probe là gì?**  
A: Incident history đã có payment lỗi trong deploy và mất cart khi node reschedule. Replica/probe giảm downtime và giảm khả năng mất doanh thu checkout. Probe ít cost, replica cần cost review.

**Q: Vì sao không bật hết HA ngay?**  
A: Vì HA/storage/managed service có cost và migration risk. CDO08 đề xuất làm backup/restore proof và CDO04 review trước, tránh tăng cost mà chưa chứng minh risk/benefit.

### SRE Questions

**Q: Readiness probe sẽ check gì? Sai thì sao?**  
A: Nam cần đề xuất probe theo service. Rollback plan là revert probe config nếu threshold sai làm pod không ready. Không nối probe vào endpoint tĩnh vô nghĩa nếu dependency critical cần readiness.

**Q: Checkout timeout set bao nhiêu? Có làm fail request nhanh quá không?**  
A: Quân/Nguyên cần timeout budget theo dependency. Mục tiêu là bounded failure thay vì treo vô hạn. Cần fault test trước rollout.

**Q: Nếu fix `flagd` sync làm `flagd` crash thì sao?**  
A: Không dùng command cũ có `/bin/sh -c`. Nếu fix mới crash, rollback local-only để phục hồi runtime, nhưng ghi rõ protected path/rule risk và không coi là done.

**Q: Security hardening có làm app crash không?**  
A: Nhân đề xuất staged rollout. Không bật `readOnlyRootFilesystem` global. Test từng batch, ưu tiên stateless services trước.

### CDO07 / Audit Questions

**Q: Evidence đã đủ chưa?**  
A: Top P0/P1 đều có source/config/runtime evidence trong backlog. Một số item có `Needs Info` như Grafana/OpenSearch exposure, cần thêm runtime validation trước triển khai.

**Q: Có cần ADR không?**  
A: Các thay đổi policy/RBAC/security posture hoặc architecture như outbox/HA nên có ADR hoặc decision note, phối hợp CDO07.

## 11. Dry-Run Notes

Status: **Pending human dry-run**.

Dry-run cần thực hiện với:

- Nguyên: review technical risk và trả lời SRE-style questions.
- Ít nhất 2 owner trong nhóm: gợi ý Nam cho runtime/probe và Nhân hoặc Thuỷ cho security/flagd.

Checklist sau dry-run:

- [ ] Top 5 priority có thể nói trong dưới 8 phút.
- [ ] Mỗi top risk có evidence, impact, priority reason.
- [ ] CFO cost questions có câu trả lời không né tránh.
- [ ] SRE rollback/test questions có câu trả lời cụ thể.
- [ ] Deferred items được giải thích rõ là deliberate choice.

## 12. Final Pitch Position

CDO08 sẽ pitch rằng:

> Chúng tôi không cố sửa tất cả ngay. Chúng tôi đã scan baseline, map risk về incident history và SLO/business impact, rồi chọn một backlog thứ tự rõ. Week 2-3 nên bắt đầu từ protected control path `flagd`, deploy safety probes, secret/security exposure validation, sau đó đến replica/data/checkout hardening có cost và design review.
