# AIO1 — Mentor check-in cheat sheet

> Cập nhật: 23/07/2026 · Trọng tâm: Mandate 7b/15 và Mandate 22\
> Jira: `https://aio1-xbrain.atlassian.net/browse/<KEY>`

## 1. Câu mở đầu 30 giây

“Phần AIOps của nhóm hiện có hai lớp. Lớp detection đã được merge, đóng gói bằng image đã scan/ký/attest và đang chạy liên tục trên cluster. Nó đọc Prometheus, OpenSearch và Jaeger, đã phát hiện hai degradation thật của `frontend` và `checkout`, nhưng remediation vẫn ở `dry-run`, không có mutation. Lớp closed-loop Mandate 22 đã có controller, safety policy, verification, rollback, audit và external replay trong code; tuy nhiên nhóm chưa claim hoàn thành vì còn thiếu CDO/on-call ký ADR-022 và hai live drill: một action thành công, một forced-wrong tự rollback/escalate.”

## 2. Trạng thái thật — nói đúng mức này

### Đã hoàn tất

- [TF4AIO-70 — Mandate 6](https://aio1-xbrain.atlassian.net/browse/TF4AIO-70): **Done**.
- [TF4AIO-71 — Mandate 7a](https://aio1-xbrain.atlassian.net/browse/TF4AIO-71): **Done**.
- [TF4AIO-78 — detector tests](https://aio1-xbrain.atlassian.net/browse/TF4AIO-78): **Done**; full AIOps suite trên release image đạt **69 passed**.
- Application và GitOps đã merge; AIOps pod production hiện **1/1 Ready, 0 restart**.

### Đã làm phần lớn nhưng chưa được claim Done

- [TF4AIO-72 — Mandate 7b](https://aio1-xbrain.atlassian.net/browse/TF4AIO-72): detector đã live; còn controlled labelled run, live precision/recall/MTTD và Slack evidence.
- [TF4AIO-76 — deploy/integrate alerts](https://aio1-xbrain.atlassian.net/browse/TF4AIO-76): secure image, GitOps deploy, pod và telemetry path đã xong; còn ảnh/timestamp alert tại `#tf4-alerts`.
- [TF4AIO-77 — live E2E measurement](https://aio1-xbrain.atlassian.net/browse/TF4AIO-77): offline replay có số; live labelled precision/recall/lead-time chưa đủ.
- [TF4AIO-80 — Mandate 15](https://aio1-xbrain.atlassian.net/browse/TF4AIO-80): continuous detector và ambient-production detection đã có; còn bộ live evidence định lượng.
- [TF4AIO-58 — Mandate 22 epic](https://aio1-xbrain.atlassian.net/browse/TF4AIO-58) và [TF4AIO-83 — canonical Mandate 22](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83): code/replay merged, nhưng live mutation chưa được cấp quyền.
- [TF4AIO-63 — controlled remediation drill](https://aio1-xbrain.atlassian.net/browse/TF4AIO-63): **chưa chạy**; phải có named CDO/on-call approval trước.

### Không được nói quá

- Không nói “Mandate 22 đã xong”; hiện mới xong implementation/offline proof và safe dry-run deployment.
- Không gọi hai ambient incidents là measured MTTD vì không biết chính xác thời điểm degradation bắt đầu.
- `precision=1.0`, `recall=1.0`, MTTD `45s` là **offline replay trên labelled fixture**, không phải general production performance.
- Không nói Jaeger hoàn toàn ổn: query checkout trả 200, nhưng frontend enrichment đôi lúc timeout vì Jaeger v2 đang thiếu memory.
- Không nói Slack đã nhận alert nếu chưa có screenshot hoặc timestamp thật trong `#tf4-alerts`.

## 3. Mentor hỏi theo Jira task

### TF4AIO-70 — AI Mandate 6

**Đã làm:** grounded product-review Q&A trên Bedrock; deterministic citation validation; refusal khi thiếu evidence; lớp local deterministic filter cho fast-path, Bedrock Guardrail là semantic enforcement; sanitized telemetry, Pod Identity, canary và rollback evidence. Bộ hardening bổ sung multilingual/obfuscated/adversarial cases.

**Vì sao không chỉ regex:** regex chỉ là tối ưu latency/cost và chặn mẫu rõ ràng; không phải security boundary. Input đã qua local precheck vẫn phải chịu managed guardrail trong Bedrock inference path. Không gọi thêm `ApplyGuardrail` trước mọi `Converse` vì sẽ nhân latency/cost mà vẫn trùng lớp enforcement; thay vào đó harden dataset và Guardrail policy.

**Evidence:** [Jira](https://aio1-xbrain.atlassian.net/browse/TF4AIO-70), [closure PR #280](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/280), [hardening PR #414](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/414), `ADR-006-bedrock-model-and-safety.md`.

### TF4AIO-71 — AI Mandate 7a

**Đã làm:** detector/baseline thật; phân tích latency p95, request error và LLM error theo từng emitting service; acute detection, slow-drift detection, service-scoped ownership, RCA evidence, incident lifecycle và safe-response design. Thresholds đều chuyển thành runtime config và có sensitivity/calibration report.

**Thuật toán ngắn gọn:** Median/MAD tạo robust baseline; ratio/z-score/EWMA bắt thay đổi cấp tính; short-window trend + consistency + SLO proximity bắt drift tăng dần; Isolation Forest chỉ bổ sung tối đa `0.05` confidence, không tự fire incident.

**Evidence:** [Jira](https://aio1-xbrain.atlassian.net/browse/TF4AIO-71), [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281), [ADR-007](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/aiops/ADR-007-hybrid-anomaly-detection-and-safe-response.md).

### TF4AIO-72 — AI Mandate 7b

**Đã làm:** đưa phase-1 detector từ replay lên continuous production pod; kết nối Prometheus/OpenSearch/Jaeger; triển khai Alertmanager route bằng GitOps; giữ mutation tắt; đã quan sát hai ambient incidents thật.

**Còn thiếu để Done:** một bộ controlled/live có nhãn, evidence alert tới on-call, precision/recall/MTTD thật và kết luận recalibration. Đây là ticket gom runtime acceptance của các task 76–78, không phải viết lại detector 7a.

### TF4AIO-73/74/75 — design, implementation và telemetry/evidence subtasks

**Đã làm chung:** các output không còn nằm rời rạc; đã hợp nhất vào PR #281 và tài liệu detector: signal contract, baseline/gate, service-aware LLM ownership, PromQL namespace scope, evidence bundle từ metric/log/trace, RCA candidate và bounded incident lifecycle.

**Cách trả lời cá nhân:** owner nói đúng phần mình review/implement; không nhận toàn bộ PR. Nếu mentor hỏi trạng thái, nói các task review này đã có implementation/evidence trong main; live acceptance thuộc 72/76/77/80.

### TF4AIO-76 — Integrate detection and deploy alerts

**Đã làm:**

- Release PR [#553](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/553) merged.
- Main release [run 29980198546](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/actions/runs/29980198546) pass build/push, Trivy, Cosign, SBOM, provenance.
- Image `66ed32b-aiops`, digest `sha256:7eff9e53c0ba609a2b421a33778b5bcf8ef98a429dd846e354c53ccf4fa6fb0d`.
- GitOps promotion [#137](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/137), detector activation [#118](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/118), narrow observability network fix [#140](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/140) đều merged.
- Pod `1/1 Ready`, 0 restart; `/healthz`, `/readyz`, `/metrics` trả 200; Prometheus/OpenSearch/checkout Jaeger query trả 200.

**Còn thiếu:** bằng chứng notification thật tại Slack `#tf4-alerts`.

### TF4AIO-77 — Run live E2E and measure precision/recall

**Đã làm:** external JSONL replay và labelled scenarios; phase-1 offline result `TP=3, FP=0, FN=0, TN=3`, precision/recall `1.0/1.0`, simulated lead-time `45s`. Detector live đã bắt hai ambient incidents.

**Còn thiếu:** controlled live set gồm real incident, masking/noise và healthy-busy; timestamp onset/detect/notify; tính lại live precision, recall và MTTD. Ambient incident không đủ để tính MTTD.

**Evidence:** [PR #509](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/509).

### TF4AIO-78 — Unit/integration tests

**Đã làm:** acute spike, transient rejection, masking resistance, stable busy, slow drift, ownership, replay schema, incident summary, remediation safety/rollback paths. Final secure image chạy full suite: **69 passed**.

### TF4AIO-80 — AI Mandate 15

**Đã làm:** detector không còn chỉ là docs/replay; đã chạy liên tục trên production cluster và đọc telemetry thật. Nó tạo hai incident:

- `frontend service_latency_spike`, confidence khoảng `0.839`, p95 `1913.58ms`;
- `checkout service_latency_spike`, confidence khoảng `0.843`, p95 `1010.57ms`.

Cả hai ở `awaiting_approval`, `execution_attempts=0`; không mutation/rollback. Điều này chứng minh detection path và safety boundary, chưa chứng minh live precision/recall/MTTD hoặc Slack delivery.

### TF4AIO-58 — Automated Remediation & Recovery epic

**Vai trò:** epic điều phối 59–63, không phải một implementation riêng. Thiết kế, policy, controller và rollback workflow đã được hợp nhất trong PR #473. Epic vẫn mở vì task 63 và canonical Mandate 22 chưa có live closure evidence.

### TF4AIO-59 — Remediation action catalog và CDO contract

**Đã làm:** action allowlist, target workload/namespace, prerequisites, blast radius, stop conditions, verification SLI, rollback và escalation contract. Chỉ chọn một bounded action cho closure: `deployment-latency-rollback`.

**Còn thiếu:** CDO ghi rõ target Deployment, retained known-good ReplicaSet và drill window rồi ký ADR.

### TF4AIO-60 — Execution policy

**Đã làm:** deterministic policy version, confidence/severity/evidence gates, one mutation per incident, action lock, Kubernetes Lease chống duplicate giữa replicas/restarts, retry/cooldown, audit contract và fail-closed behavior.

**Điểm chính:** không dùng LLM output, free-form shell, HPA restart hay flagd mutation làm authorization.

### TF4AIO-61 — Runbook execution controller

**Đã làm:** controller nhận structured incident, kiểm tra exact policy/action/target, preflight current và previous ReplicaSet, hỗ trợ dry-run, Helm/RBAC gate riêng cho live patch, rồi theo dõi rollout.

**Hiện trạng:** controller đã merge nhưng production config vẫn `REMEDIATION_MODE=dry-run`, autonomous false, live RBAC false.

### TF4AIO-62 — Verification, rollback và escalation

**Đã làm:** capture before state; verify readiness và SLO qua nhiều poll; nếu action không cải thiện thì restore original template; verify rollback lần nữa; nếu rollback không chứng minh healthy thì block mutation tiếp theo và escalate. Audit có trigger → policy checks → action → verification samples → rollback/escalation.

### TF4AIO-63 / TF4AIO-83 — Live Mandate 22 closure

**Đã làm:** [PR #473](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/473) merged commit `0b63c20`; offline external replay có ba nhánh: mitigation success, forced-wrong rồi verified rollback, unhealthy rollback rồi mutation-block + escalation.

**Chưa làm:** live autonomous action và live forced-wrong drill. Đây không phải thiếu code mà là activation gate:

1. CDO và on-call/SRE ký đầy đủ tên trong ADR-022.
2. Chọn exact Deployment/namespace/known-good revision/drill window.
3. Bật policy-level preauthorization + live RBAC qua reviewed GitOps.
4. Chạy success drill và forced-wrong rollback drill.
5. Đính kèm telemetry thật, audit log, Slack/escalation và MTTR.

## 4. ADR — câu mentor có thể hỏi

### ADR là gì và tại sao cần?

“ADR ghi lại quyết định kiến trúc, lý do chọn, phương án bị loại, trade-off, consequences và ai chịu trách nhiệm phê duyệt. PR review chứng minh code được review; ADR signature chứng minh con người chấp nhận decision và phạm vi activation. Hai việc không thay thế nhau.”

### ADR-007 quyết định gì?

Chọn hybrid explainable detector thay vì chỉ static threshold hoặc chỉ ML:

- Median/MAD: baseline ít bị một outlier làm lệch.
- ratio/z-score/EWMA: phát hiện acute deviation.
- trend + consistency + SLO proximity: phát hiện slow drift.
- Isolation Forest: evidence phụ cho confidence, không phải firing gate.
- logs/traces/deployment evidence: enrich RCA, không tự biến correlation thành cause.
- remediation mặc định dry-run và bị tách khỏi detection confidence.

**Status:** Accepted cho Mandate 7a. Có chữ ký Đinh Danh Nam, Cái Xuân Hòa và Trần Đình Thông. CDO/on-call signatures chỉ dành cho runtime activation sau đó.

### Vì sao Median/MAD rồi vẫn tính mean/pstdev?

“Median/MAD dùng để loại masking outlier trước, còn mean/pstdev dùng trên phần baseline đã làm sạch để có ratio/z-score dễ giải thích. Ưu điểm là robust với noise và không cần giả định raw series Gaussian. Nhược điểm là có thể bỏ sớm signal của incident dài; vì vậy slow-drift path dùng recent unfiltered sequence, short-vs-long trend và sustained gate.”

### Tại sao chọn EWMA alpha `0.35` và các hệ số?

“Đây là seed, không claim tối ưu. Alpha 0.35 cho recent samples đủ trọng số nhưng không để một điểm thống trị. Nhóm đã sensitivity-check `0.2/0.35/0.5` và replay 81 parameter combinations trên 12 production-informed windows. Boundary 70% SLO cho 6 TP/0 FP/6 TN/0 FN trên tập nhỏ đó; 60% còn 1 FP, 80% miss 1 signal. Vì tập nhỏ nên 7b vẫn phải re-calibrate bằng controlled live labelled data.”

### Isolation Forest có vai trò gì?

“IF được fit để tìm nonlinear outlier nhưng hiện chỉ cộng tối đa 0.05 confidence và ghi audit. Nó không có quyền fire incident vì chưa đủ labelled production data để justify contamination/decision boundary. Gate chính vẫn deterministic và explainable.”

### Làm sao biết LLM error thuộc service nào?

“Không hard-code `product-reviews`. Mỗi caller emit `service.name` và `llm.operation`; Prometheus giữ `service_name`, query group/join theo label đó và detector giữ state per service. Series thiếu label bị đánh `unattributed/coverage degraded`, không gán bừa owner.”

### ADR-022 quyết định gì?

“Không dùng nút approve cho từng incident vì như vậy chưa phải closed-loop; cũng không cho autonomy mở. Nhóm chọn policy-level preauthorization: CDO ký trước một policy version cực hẹp cho đúng action, target, namespace, blast radius và time window. Khi incident xảy ra, hệ tự act chỉ khi mọi deterministic gate đúng; verify fail thì tự restore và verify rollback, sau đó block/escalate.”

**Status:** Proposed. Implementation đã merge nhưng CDO deployment owner và on-call/SRE owner chưa ký tên, nên mutation đang khóa đúng thiết kế.

### Vì sao hiện incident vẫn `awaiting_approval` nếu Mandate 22 yêu cầu không cần người bấm?

“Deployment hiện tại là safety staging cho detector, chưa phải Mandate 22 activation. Final design không yêu cầu per-incident button; nó dùng deployment-time signed policy envelope. Chưa có named sign-off và drill scope nên hệ fail closed ở `awaiting_approval`. Sau khi policy được ký và bật bằng GitOps, incident đủ điều kiện mới tự chạy trong envelope.”

## 5. Flow đầy đủ để vẽ/giải thích

```text
Prometheus metrics
  + OpenSearch logs
  + Jaeger traces
        |
        v
per-service baseline + coverage
        |
        +--> acute gate: floor + ratio/z/EWMA + sustain
        |
        +--> slow-drift gate: short trend + consistency + long baseline + SLO proximity
        |
        v
incident + confidence + evidence + RCA candidates
        |
        +--> Alertmanager --> Slack/on-call
        |
        v
pre-authorized deterministic policy?
        |
     no +--> dry-run / awaiting approval / escalate with runbook
        |
     yes
        v
target lock + preflight + blast-radius check
        |
        v
allowlisted deployment rollback
        |
        v
multi-poll readiness + real SLO verification
        |
        +--> recovered --> audit + close
        |
        +--> failed --> restore original template --> verify rollback
                                      |
                                      +--> healthy: audit + escalate
                                      +--> unhealthy: mutation block + urgent escalation
```

## 6. Evidence links phải mở sẵn khi check-in

- Mandate 7a implementation: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281
- Mandate 15 phase-1: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/509
- Mandate 22 controller: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/473
- Secure runtime: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/553
- Release workflow: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/actions/runs/29980198546
- Image promotion: https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/137
- Detector deployment: https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/118
- Observability NetworkPolicy: https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/140
- ADR-007: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/aiops/ADR-007-hybrid-anomaly-detection-and-safe-response.md
- ADR-022: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/aio1/mandate-22/ADR-022-safe-closed-loop-mitigation.md
- Jira Mandate 15: https://aio1-xbrain.atlassian.net/browse/TF4AIO-80
- Jira Mandate 22: https://aio1-xbrain.atlassian.net/browse/TF4AIO-83

## 7. Việc làm ngay sau check-in

1. Chụp/timestamp alert thật trong `#tf4-alerts`.
2. Chạy controlled labelled detector set; tính live precision/recall/MTTD.
3. Update Jira 72/76/77/80 bằng evidence, không dùng số offline như live.
4. Xin full-name CDO/on-call signatures cho ADR-022 và exact drill scope.
5. Sau approval: chạy một mitigation success và một forced-wrong rollback; lưu before/after SLI, audit và MTTR.
6. Chỉ khi đủ mục 4–5 mới chuyển 58/63/83 sang Done.

## 8. Phần trả lời theo từng thành viên

> Quy tắc khi trả lời: phân biệt rõ **Jira owner**, **người viết code** và **người review**. Không nói “em tự viết toàn bộ” nếu implementation đã được hợp nhất từ work của nhiều người vào PR canonical.

### Nam — integration, execution policy và deployment

**Jira chính dễ trình bày**

- [TF4AIO-60](https://aio1-xbrain.atlassian.net/browse/TF4AIO-60): thiết kế remediation execution policy.
- [TF4AIO-76](https://aio1-xbrain.atlassian.net/browse/TF4AIO-76): tích hợp và deploy detector/alert path.
- [TF4AIO-58](https://aio1-xbrain.atlassian.net/browse/TF4AIO-58): điều phối epic Automated Remediation & Recovery.

**Đã làm**

- Hợp nhất detector, RCA, telemetry và safe-response design trong [PR #281](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/281).
- Hợp nhất closed-loop controller, policy, locking, verify, rollback và audit trong [PR #473](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/473).
- Sửa production image/security gate trong [PR #553](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/553).
- Đưa image và detector lên cluster bằng GitOps [#137](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/137), [#118](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/118)và sửa NetworkPolicy bằng [#140](https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests/pull/140).

**Policy TF4AIO-60 thực sự hoạt động thế nào**

1. CDO/on-call không approve tùy ý từng câu lệnh. Họ ký trước một policy envelope gồm exact policy version, action `deployment-latency-rollback`, Deployment/namespace, known-good revision, blast radius, drill window và stop conditions.
2. Incident chỉ eligible khi severity/confidence đạt ngưỡng, có primary telemetry evidence, action/runbook/target nằm trong allowlist, không trong cooldown và chưa có mutation attempt.
3. Controller lấy Kubernetes Lease để chỉ một replica được act trên target; đồng thời giữ one-action-per-target và one-mutation-per-incident.
4. Preflight phải tìm được current và previous ReplicaSet template. Thiếu known-good state, telemetry hoặc lock thì fail closed.
5. Live patch cần ba gate riêng: policy preauthorization, autonomous mode và Helm/RBAC live gate. LLM output, free-form shell, HPA restart và flagd không có quyền authorize action.
6. Sau action, readiness và SLO phải healthy qua nhiều poll trong stabilization window. Một sample tốt không đủ để kết luận recovered.
7. Verify fail thì restore captured original template và verify rollback qua window thứ hai. Rollback không chứng minh healthy thì block mutation tiếp và escalate.
8. Audit ghi policy version/checks, incident evidence, preflight, action, verification samples, rollback, rollback verification và escalation reason.

**Câu trả lời ngắn**

> Em thiết kế policy theo hướng CDO pre-authorize một envelope rất hẹp, không approve từng incident và cũng không cho autonomy mở. Hệ chỉ được rollback đúng target đã allowlist khi đủ telemetry, severity, confidence, lock và cooldown. Sau action phải verify bằng readiness/SLO thật; fail thì tự restore, verify rollback, khóa mutation tiếp và escalate. Production hiện vẫn dry-run vì ADR-022 chưa đủ activation signatures.

### Hòa — observability evidence và action catalog

**Jira chính dễ trình bày**

- [TF4AIO-59](https://aio1-xbrain.atlassian.net/browse/TF4AIO-59): remediation action catalog và CDO operating contract.
- `TF4AIO-67`: thu thập Prometheus/OpenSearch/Jaeger runtime evidence.
- `TF4AIO-75`: telemetry/rule/runbook integration thuộc detector.
- `TF4AIO-36`: xác minh programmatic observability access.

**Đã làm**

- Xác minh Prometheus query được, OpenSearch trả HTTP 200 và Jaeger thấy services/traces; thiết kế detection rules và mapping incident → runbook.
- Với TF4AIO-59, xác định action nào được phép, target/namespace, prerequisites, blast radius, verification SLI, rollback và escalation contract.
- Review/approve các PR canonical #281, #509, #473, #553 và GitOps #137/#140.

**Nếu mentor hỏi TF4AIO-36**

> Task 36 là chứng minh team có quyền đọc observability stack thật, không phải viết detector. Evidence gồm Prometheus, OpenSearch và Jaeger. Sau deployment, AIOps đã query Prometheus/OpenSearch và checkout Jaeger thành công; frontend Jaeger đôi lúc timeout do shared Jaeger pod thiếu memory.

**Lưu ý ownership**

TF4AIO-36 hợp logic với Hòa vì đây là observability-access/evidence task. Không gán task này cho Hậu nếu Jira chưa có chuyển assignee/evidence rõ ràng.

### Vũ — detector tests và Copilot memory

**Jira chính dễ trình bày**

- [TF4AIO-78](https://aio1-xbrain.atlassian.net/browse/TF4AIO-78): unit/integration tests cho detector.
- [TF4AIO-53](https://aio1-xbrain.atlassian.net/browse/TF4AIO-53): Copilot multi-turn memory.

**Đã làm / evidence**

- Scope TF4AIO-78 bao gồm acute incident, transient/noise rejection, masking resistance, stable-busy, slow drift, service ownership và integration path.
- Full AIOps suite chạy trong exact secure release image đạt **69 passed**.
- Review và approve GitOps #118 trước khi detector được bật ở safe dry-run.
- Phần Copilot memory đã merge qua PR #504, nhưng không dùng nó để claim AIOps Mandate 15/22.

**Câu trả lời ngắn**

> Em phụ trách đảm bảo detector không chỉ bắt spike mà còn không báo nhầm khi busy/noise, bắt được masking và slow drift, đồng thời giữ state riêng theo service. Final suite trên đúng production image có 69 test pass.

### Thông — Mandate 15 evaluation và canonical closure

**Jira chính dễ trình bày**

- [TF4AIO-80](https://aio1-xbrain.atlassian.net/browse/TF4AIO-80): AI Mandate 15.
- [TF4AIO-77](https://aio1-xbrain.atlassian.net/browse/TF4AIO-77): live E2E precision/recall/MTTD.
- [TF4AIO-83](https://aio1-xbrain.atlassian.net/browse/TF4AIO-83): canonical Mandate 22 submission.

**Đã làm**

- Author/điều phối [PR #509](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/509): external JSONL replay, labelled scenarios, ADR-015 và reproducible report.
- Offline result: `TP=3, FP=0, FN=0, TN=3`, precision/recall `1.0/1.0`, simulated detection time `45s`.
- Review/approve final #281, #473, #553 và các GitOps promotion/deployment PR.
- Theo dõi Jira/evidence boundary cho Mandate 15/22.

**Điều phải nói rõ**

> 45 giây và precision/recall 1.0 là offline labelled replay, không phải số production tổng quát. Live detector đã bắt hai ambient incidents nhưng chưa biết true onset, nên chưa dùng chúng để tính MTTD. Còn thiếu controlled labelled run và Slack timestamp.

### Tâm — post-action verification, rollback và escalation

**Jira chính dễ trình bày**

- [TF4AIO-62](https://aio1-xbrain.atlassian.net/browse/TF4AIO-62): post-action verification, rollback và escalation.

**TF4AIO-62 đã làm gì**

- Định nghĩa before/after state, rollout/readiness và user SLI verification.
- Recovery phải giữ qua stabilization window.
- Verify fail thì restore original template; verify rollback fail thì mutation block và escalate, không tạo restart loop.
- Canonical implementation của scope này đã được hợp nhất vào PR #473; task owner không đồng nghĩa là sole author của toàn PR.

**Câu trả lời ngắn**

> Em phụ trách kiểm tra kết quả sau remediation. Hệ không kết luận thành công chỉ vì Kubernetes patch trả 200; nó phải đo readiness và SLO qua nhiều poll. Nếu không cải thiện thì restore state cũ, verify rollback lần nữa; nếu vẫn không healthy thì khóa mutation tiếp và escalate để tránh restart loop.

### Hậu — controlled auto-remediation drill

**Jira chính dễ trình bày**

- [TF4AIO-63](https://aio1-xbrain.atlassian.net/browse/TF4AIO-63): validate one CDO-approved controlled remediation drill end-to-end.

**Đã làm / scope cần nắm**

- Đã soạn `E:\xBrain-capstone3\drill-proposal-TF4AIO-63.md`: đề xuất hai scenario controlled drill gồm successful mitigation và forced-wrong action dẫn tới verified rollback/escalation; kèm safety boundary, policy gates, evidence checklist và acceptance criteria.
- Task 63 chưa chạy live: cần exact target, known-good revision, CDO/on-call signatures và drill window. Phải nói đây là **proposal đang chờ duyệt**, chưa phải runtime evidence đã chạy.

**Câu trả lời ngắn**

> Em phụ trách proposal và evidence plan cho live controlled drill. Proposal có hai nhánh: một action thành công được verify bằng telemetry thật và một forced-wrong action phải tự restore, verify rollback rồi escalate. Hiện mới là proposal; chưa chạy vì còn chờ CDO/on-call duyệt target, known-good revision, safety boundary và drill window.

**Các điểm phải sửa/chốt trước khi dùng proposal để chạy**

1. Proposal hiện có bước `request_approval()`/`approve()` theo từng incident, nhưng Mandate 22 và ADR-022 yêu cầu policy được pre-authorize trước để khi incident đủ điều kiện hệ tự chạy, không chờ người bấm. Khi trình bày phải nói approval trong proposal là **deployment-time policy activation**, không phải manual approval giữa incident; flow/script phải được sửa tương ứng trước drill.
2. Proposal ghi namespace `techx-corp`, trong khi detector hiện chạy tại `techx-tf4`. CDO phải xác nhận chính xác staging target/namespace; không được tự thay bằng production namespace.
3. Proposal nhắc in-memory `_locks`; canonical PR #473 dùng Kubernetes Lease để chống duplicate giữa pod replicas/restarts. Drill phải kiểm chứng canonical Lease path, không dùng mô tả lock cũ.
4. Không chỉ chứng minh Deployment rollout Ready. Kết quả success phải có readiness **và** SLO/telemetry healthy qua stabilization window.
5. Nhánh forced-wrong phải chứng minh restore đúng captured original template, rollback verification, mutation block/escalation và chuỗi audit đầy đủ.
6. Evidence tối thiểu: before/during/after Prometheus, exact timestamps, incident JSON, audit-event chain, Kubernetes revision/template evidence, alert/escalation và MTTD/MTTR/rollback time.

**Lưu ý ownership:** không đưa TF4AIO-36 cho Hậu. Task 36 là observability access/evidence và hợp với Hòa; task Hậu học và trình bày là TF4AIO-63.

### Văn — Bedrock safety/reliability và evaluation harness

**Jira chính dễ trình bày**

- `TF4AIO-23/24/26/27/28/29`: Bedrock routing, safe fallback, injection/PII, timeout/circuit breaker và DB reliability.
- `TF4AIO-81`: external-input evaluation harness cho AI/Copilot.

**Đã làm / evidence**

- Có contribution cho Bedrock adapter và safety path: pinned model/Guardrail, timeout, retry/circuit behavior, canonical safe response và injection/PII checks.
- Mở rộng bake-off runner/dataset trong PR #269. PR này hiện không phải canonical closure và chứa scope trộn; chỉ nhận contribution dataset/runner, không nói toàn bộ PR đã merge.
- Canonical Guardrail hardening/closure nằm ở PR #414/#280.
- TF4AIO-81 là external-input harness; hiện thấp ưu tiên hơn Mandate 15/22.

**Câu trả lời ngắn**

> Em phụ trách reliability/safety quanh Bedrock call và phần external-input eval: timeout/circuit breaker, safe failure, injection/PII cases và dataset runner. Phần bake-off của em là input cho bộ hardening; canonical evidence cuối nằm ở PR #414/#280.

## 9. Tin nhắn ngắn gửi mentor về task split

```text
Anh ơi, các task chính tuần rồi của nhóm em:

- Nam: TF4AIO-60 — remediation execution policy; TF4AIO-76 — deploy AIOps detector.
- Hòa: TF4AIO-59 — action catalog/CDO contract; TF4AIO-36 — observability access evidence.
- Vũ: TF4AIO-78 — unit/integration tests cho detector.
- Thông: TF4AIO-80 — Mandate 15 detection; TF4AIO-83 — Mandate 22 closure/evidence.
- Tâm: TF4AIO-62 — post-action verification, rollback và escalation.
- Hậu: TF4AIO-63 — soạn controlled auto-remediation drill proposal, đang chờ CDO/on-call duyệt.
- Văn: TF4AIO-81 — external-input eval harness; đồng thời hỗ trợ Bedrock safety/eval.

Mandate 6 và 7a đã đóng. Hiện nhóm tập trung live evidence cho 7b/15 và controlled
closed-loop drill cho Mandate 22.
```