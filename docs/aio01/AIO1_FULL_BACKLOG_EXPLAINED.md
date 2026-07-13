# AIO1 Full Backlog Explained

Purpose: tài liệu để AIO1 hiểu và defend backlog khi mentor hỏi random. Mỗi task cần được giải thích theo 5 ý: **mục tiêu → quyết định → lý do → evidence → dependency**.

Canonical Jira backlog reference: [AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md](./AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md).

## 1. Backlog tổng thể

Jira hiện có 8 epic:

| Jira epic | Track | Mục đích |
| --- | --- | --- |
| `TF4AIO-1` | AIE | Hiểu AI baseline, mock behavior và evidence Week 1. |
| `TF4AIO-2` | AIE | Đo AI summary/Q&A và Copilot bằng eval tái tạo được. |
| `TF4AIO-3` | AIE | Làm real LLM reliable, safe, observable và cost-aware. |
| `TF4AIO-4` | AIE | Xây Shopping Copilot MVP có guardrail. |
| `TF4AIO-5` | AIOps | Xác nhận telemetry/data access và chọn scope incident. |
| `TF4AIO-6` | AIOps | Rule-based detector, continuous workload và output channel. |
| `TF4AIO-7` | AIOps | Incident summary, runbook suggestion, validation report. |
| `TF4AIO-8` | OPS | PR/evidence, cost guard, Ops Review và final handoff. |

```text
Week 1: baseline + evidence + scope
    -> Week 2: safety/reliability + telemetry + detector foundation
    -> Week 2-3: Copilot + AIOps MVP
    -> Week 3: failure drill/eval/validation/final package
```

### Quyết định lớn của backlog

1. Week 1 không build full Copilot hay full AIOps. Team ưu tiên discovery, evidence, baseline và dependency vì chưa đủ dữ liệu để defend implementation lớn.
2. AIE foundation đi trước Copilot: eval, real-LLM readiness, fallback, timeout, safety, telemetry và cost phải có trước khi mở rộng tính năng.
3. AIOps MVP đi theo hướng rule-based, evidence-grounded và read-only trước; không claim full ML/RCA hay auto-remediation.
4. Automation là roadmap có safety gate, approval và rollback/escalation, không phải detect xong tự restart pod.
5. Mọi closing evidence phải ở repo/PR/Jira comment; không dùng local-only path.

## 2. EPIC-AIE-01 — AI Baseline Discovery & Assessment (`TF4AIO-1`, Done)

### Mục tiêu

Hiểu AI path hiện tại trước khi thay đổi: `frontend -> product-reviews -> DB/product catalog -> LLM`.

### Week 1 tasks đã hoàn thành

- `TF4AIO-9`: review source và document AI flow.
- `TF4AIO-10`: smoke test AI trên TF4 baseline.
- `TF4AIO-11`: record baseline findings/gaps.
- `TF4AIO-21`: prepare Week 1 pitch notes.

### Decision và reasoning

**Quyết định:** coi kết quả deployed hiện tại là **mock/baseline evidence**, không gọi đó là real-LLM quality evidence.

**Lý do:** response có tính deterministic/mock fixture. Nó chứng minh integration path gọi được LLM-compatible endpoint và trả response, nhưng không chứng minh model quality, hallucination rate, latency thật hoặc cost thật.

### Evidence cần nói được

- Source flow/documentation.
- Smoke-test screenshot hoặc request/result trên TF4.
- Finding có code reference và risk/impact.

### Câu trả lời mentor

> Week 1 tụi em chưa claim AI tốt hay đã production-ready. Tụi em xác nhận vertical slice hiện tại chạy bằng mock baseline, đọc code để tìm gap, rồi dùng evidence đó xếp priority cho Week 2/3.

## 3. EPIC-AIE-02 — AI Evaluation & Faithfulness (`TF4AIO-2`)

### Mục tiêu

Đo summary/Q&A có faithful, relevant và grounded hay không bằng eval tái tạo được.

### Tasks

| Jira key | Task | Owner | Decision và reasoning |
| --- | --- | --- | --- |
| `TF4AIO-22` | Run eval on mock/current LLM | Vũ | Chạy mock trước để validate eval pipeline, không claim model quality. |
| `TF4AIO-55` | Copilot task-success eval | Vũ | Copilot phải được đo task success/failure, không chỉ demo một happy path. |

### Eval phải đo gì?

- Faithfulness: không bịa claim ngoài product/review data.
- Relevance: trả lời đúng câu hỏi người dùng.
- Groundedness: có căn cứ dữ liệu; nếu thiếu dữ liệu thì nói không đủ thông tin.
- Safety: không lộ PII/system prompt, không hành động sai.
- Task success: user tìm được sản phẩm, hiểu thông tin và chỉ mutate cart sau confirmation.

### Decision và reasoning

**Quyết định:** eval đi trước Copilot expansion.

**Lý do:** không có rubric/cases/runner/pass-fail report thì team không thể chứng minh AI hay Copilot tốt hơn baseline. Eval trên mock chỉ kiểm tra plumbing: dataset, expected behavior, runner và report. Cùng pipeline đó được tái sử dụng khi bật real LLM.

### Câu trả lời mentor

> Eval trên mock không để chấm mock model. Nó chứng minh eval pipeline chạy end-to-end. Khi chuyển real LLM, tụi em dùng lại cùng cases và rubric để so sánh quality một cách tái tạo được.

## 4. EPIC-AIE-03 — AI Reliability, Fallback & Safety (`TF4AIO-3`)

### Mục tiêu

Đảm bảo LLM chậm/lỗi không làm treo product page, output không unsafe, và real LLM có telemetry/cost guard.

### Tasks

| Jira key | Task | Owner | Decision và reasoning |
| --- | --- | --- | --- |
| `TF4AIO-25` | Add real LLM readiness checklist | Thông | Chỉ cut over khi eval, secret/model config, rollback, cost, fallback, timeout và telemetry gates rõ. |
| `TF4AIO-23` | Enable real LLM in controlled mode | Văn | Controlled/canary scope; không bật đại trà ngay. |
| `TF4AIO-24` | Implement/test safe fallback | Văn | LLM fail phải trả UX an toàn, không treo page hoặc bịa summary. |
| `TF4AIO-51` | Test LLM incident flags | Văn | Không bypass `llmRateLimitError`/`llmInaccurateResponse`; chứng minh graceful degradation. |
| `TF4AIO-26` | Prompt-injection guardrail | Văn | Review content là untrusted input. |
| `TF4AIO-27` | PII/system-prompt output filter | Văn | Không cho output/log leak nội dung nội bộ hoặc sensitive data. |
| `TF4AIO-28` | Fix DB connection pooling | Văn | AI request path vẫn phụ thuộc DB; connection pressure có thể làm endpoint degrade. |
| `TF4AIO-29` | Add LLM timeout and circuit breaker | Văn | Chặn slow/failing LLM chiếm hết worker và kéo sập service. |
| `TF4AIO-30` | Monitor/alert LLM API cost | Thông | Real LLM tạo spend risk; cost phải thấy được trước khi mở rộng traffic. |
| `TF4AIO-52` | Add AI-specific metrics/log fields | Thông | AIOps cần tách AI latency/error/fallback khỏi product-page latency chung. |

### Key technical decisions

#### Controlled real-LLM cutover

**Decision:** không bật real LLM rộng ngay; dùng controlled mode và readiness checklist.

**Reasoning:** real LLM thay đổi latency, failure mode, quality và cost. Mock baseline không chứng minh các rủi ro này đã được kiểm soát.

#### Fallback, timeout và circuit breaker trước Copilot

**Decision:** reliability foundation ưu tiên cao hơn Copilot polish.

**Reasoning:** normal LLM call hiện có risk chậm/lỗi; gRPC worker pool giới hạn. Timeout giới hạn thời gian chờ; fallback giữ UX an toàn; circuit breaker ngừng gọi upstream đang fail liên tục.

#### Không tắt injected flags

**Decision:** test flags thay vì vô hiệu hoá chúng.

**Reasoning:** `llmRateLimitError` và `llmInaccurateResponse` là incident scenario của BTC. Thành công là system degrade gracefully khi flag bật.

#### Safety + privacy là functionality, không phải polish

**Decision:** guardrail và output filtering nằm trong backlog core.

**Reasoning:** review content là untrusted; prompt injection có thể làm model làm sai. Prompt/review content có thể xuất hiện trong logs/traces nếu không redaction.

### Câu trả lời mentor

> Nếu LLM 429 hoặc timeout, tụi em không restart pod mù. App có bounded retry/backoff cho lỗi tạm thời, fallback an toàn và circuit breaker. Nếu upstream vẫn lỗi thì degrade gracefully và ghi telemetry để AIOps nhận diện.

## 5. EPIC-AIE-04 — Shopping Copilot MVP (`TF4AIO-4`)

### Mục tiêu

Xây Copilot có business value nhưng bị giới hạn scope và action boundary.

### Tasks

| Jira key | Task | Owner | Decision và reasoning |
| --- | --- | --- | --- |
| `TF4AIO-31` | Design Copilot architecture/tool wiring | Nam | Chốt data/tool boundary trước code. |
| `TF4AIO-32` | Natural-language product search | Vũ | Intent read-only, value rõ, rủi ro thấp. |
| `TF4AIO-33` | Grounded Q&A over reviews | Vũ | Answer phải dựa product/review data, không free-form claim. |
| `TF4AIO-53` | Multi-turn conversation memory | Vũ | Chỉ thêm sau khi scope/session/privacy rõ. |
| `TF4AIO-34` | Tool allow-list/excessive-agency guardrail | Văn | Agent không gọi API/tool arbitrary. |
| `TF4AIO-54` | Agent loop limit/tool audit log | Văn | Ngăn tool-loop/cost runaway và tạo audit evidence. |
| `TF4AIO-35` | Cart action with confirmation gate | Văn | Cart mutation chỉ sau explicit user confirmation. |

### Scope decision

```text
Copilot MVP = natural-language search + grounded Q&A + bounded memory + confirmed cart action
Copilot is NOT = autonomous agent được gọi tool/API tuỳ ý
```

### Reasoning

- Search/Q&A mang value rõ và phần lớn read-only.
- Groundedness giảm hallucination bằng cách buộc answer bám product/review data.
- Tool allow-list + loop limit giảm excessive agency, infinite loop và cost risk.
- Cart là side effect nên confirmation/audit log là mandatory.

### De-scope rule

Nếu Week 2 bị overload, defer theo thứ tự: final packaging → cart action → multi-turn memory → Copilot polish → alert/webhook upgrade. Không defer eval, fallback/timeout, telemetry/cost, hoặc AIOps data access.

## 6. EPIC-AIOPS-01 — AIOps Data Foundation (`TF4AIO-5`, Week 1 Done)

### Mục tiêu

Xác định detector dùng telemetry nào và chọn incident scope vừa đủ để validate.

### Week 1 tasks đã hoàn thành

- `TF4AIO-12`: data sources + incident taxonomy.
- `TF4AIO-13`: observability access.
- `TF4AIO-14`: select AIOps MVP incident types.

### Taxonomy hiện có

- Service latency spike.
- Error-rate spike.
- Pod crash/restart.
- DB saturation/connection pressure.
- Kafka lag.
- LLM timeout/error.
- AI unsafe/misleading response.
- AI telemetry/privacy leak.

### MVP decision

```text
MVP incident 1: Service latency spike
MVP incident 2: LLM timeout/error
```

**Reasoning:** LLM timeout/error thuộc AIO ownership và liên quan trực tiếp real-LLM readiness. Service latency spike có SLO impact rõ và dễ demonstrate. Chọn 2 case để làm detector/validation thật thay vì ôm taxonomy lớn.

### Data-source decision

```text
Prometheus = metrics
OpenSearch = logs
Jaeger = traces
Grafana = UI/query proxy, không phải detector architecture cuối cùng
```

Public Grafana/Jaeger hiện chứng minh được prototype programmatic query. Tuy nhiên detector production-like vẫn cần endpoint nội bộ, authentication, network policy và service-account path được CDO xác nhận.

## 7. EPIC-AIOPS-02 — Anomaly Detection MVP (`TF4AIO-6`)

### Mục tiêu

Biến telemetry thành detection tự động, explainable và chạy liên tục.

### Tasks

| Jira key | Task | Owner | Decision và reasoning |
| --- | --- | --- | --- |
| `TF4AIO-36` | Verify Prometheus/OpenSearch programmatic query | Hòa | Xác nhận workload chạy trong cluster query được, không chỉ browser/UI. |
| `TF4AIO-37` | Define detection rules/thresholds | Hòa | Chốt signal/window/severity/dedupe trước code detector. |
| `TF4AIO-38` | Build rule-based detector prototype | Hậu | Baseline explainable, dễ validate. |
| `TF4AIO-39` | Deploy continuous detector workload | Hậu | Production-like worker low-resource, không chỉ chạy script thủ công. |
| `TF4AIO-40` | Define notification/output channel | Hòa | Detection phải đến được người trực. |
| `TF4AIO-41` | Detect AI-specific LLM timeout/error | Hậu | Tách AI-path issue khi AIE đã bổ sung signal. |

### Rule spec phải define gì?

Mỗi rule cần có:

- Metric/log/trace query và labels/index fields.
- Normal baseline hoặc SLO.
- Threshold, time window và số cửa sổ liên tiếp.
- Severity, confidence, minimum traffic.
- Fingerprint/deduplication và cooldown.
- Evidence links/query và expected output.
- False-positive/false-negative policy.

### Rule-based trước, không full BARO/TORAI/ML ngay

**Decision:** MVP là deterministic rule-based detector.

**Reasoning:** retention ngắn, persistence/historical labelled incident chưa đủ và full research reproduction không tự giải quyết integration. Rule-based dễ explain, test và defend. AI engine có thể dùng ở lớp correlation/RCA hypothesis/summary sau deterministic detection, không tự execute action.

### Continuous Deployment thay vì CronJob là đích

Detector production-like nên là low-resource `Deployment`/worker poll 30-60 giây hoặc nhận alert event. CronJob chỉ chấp nhận được cho prototype fallback, không phải architecture cuối.

### Output decision

W2 minimum: structured detector output vào logs/OpenSearch. W3 nếu có thời gian và CDO cung cấp channel: Slack/webhook/Grafana alert.

## 8. EPIC-AIOPS-03 — Incident Summary & Runbook Suggestion (`TF4AIO-7`)

### Mục tiêu

Đổi signal thô thành incident mà người trực đọc và xử lý được.

### Tasks

| Jira key | Task | Owner | Decision và reasoning |
| --- | --- | --- | --- |
| `TF4AIO-42` | Define incident summary format | Nam | Chốt output contract trước generator. |
| `TF4AIO-43` | Build incident summary MVP | Hậu | Synthesize metrics/logs/traces thành output rõ. |
| `TF4AIO-44` | Map incident to runbook action | Hòa | Incident nào cũng có suggestion + owner/escalation. |
| `TF4AIO-56` | Validate detector with load/failure drill | Hậu | Không chỉ demo happy path. |
| `TF4AIO-45` | Validate LLM timeout/error signal | Hậu | Chứng minh AIOps nhận diện AI-path problem khi signal tồn tại. |
| `TF4AIO-46` | Write validation report | Hòa | Report true/false positive, false negative và limitation. |

### Incident summary contract

```text
incident_id / type / severity / confidence
affected service + first/last seen
metrics, logs và trace evidence
impact + suspected cause (không claim RCA chắc chắn)
runbook hint + owner/escalation path
known limitation
```

### Human-in-the-loop decision

**Decision:** AIOps chỉ suggest runbook, không auto-remediate trong MVP.

**Reasoning:** LLM có thể summarize evidence nhưng không được tự quyết restart/rollback/scale/config change. Các action đó cần CDO-approved RBAC, action allow-list, blast-radius control, verification và rollback path.

### Validation criteria

- True positive: có incident và detector bắt được.
- False positive: detector báo nhưng không có incident.
- False negative: có incident nhưng detector bỏ sót.
- Time-to-detect.
- Evidence completeness và telemetry gap.

## 9. Automation / retry / rollback roadmap

Automation hiện là roadmap, chưa phải auto-remediation task implementation trong Jira. Đây là quyết định scope và safety, không phải quên backlog.

```text
Detect
  -> collect evidence
  -> classify severity/confidence
  -> suggest action
  -> safety check + dry-run
  -> human/CDO approval
  -> one bounded execution
  -> verify telemetry
  -> rollback if a safe path exists, otherwise escalate
```

### Retry

Chỉ retry transient và idempotent operations (ví dụ telemetry query/API timeout): tối đa 2-3 attempts, timeout mỗi attempt, exponential backoff + jitter, action lock, cooldown. Không retry action nguy hiểm hoặc restart loop.

### Rollback

| Action | Rollback/escape path |
| --- | --- |
| Deploy version mới | Rollback về revision known-good trước đó. |
| Config/feature flag | Revert previous known-good value. |
| Scale workload | Revert replica count. |
| Restart pod | Không phải rollback; là remediation attempt. Không recover thì escalate. |

### Câu trả lời mentor: service treo thì làm gì?

> Detector xác nhận symptom qua latency, throughput, readiness, error logs và trace; sau đó tạo evidence-grounded summary + runbook hint. Kubernetes có thể restart container khi liveness probe fail. AIOps MVP không tự restart/rollback. Nếu có automation sau này thì phải qua approval, bounded action, telemetry verification và rollback/escalation path.

## 10. EPIC-OPS-01 — Operational Readiness & Evidence (`TF4AIO-8`)

### Mục tiêu

Đảm bảo implementation review/reproduce/chấm được, không chỉ có demo.

### Tasks

| Jira key | Task | Owner | Decision và reasoning |
| --- | --- | --- | --- |
| `TF4AIO-47` | Create implementation PR plan | Nam | Work phải review được qua PR. |
| `TF4AIO-48` | Weekly AIO Ops Review section | Thông | Theo dõi status/risk/evidence hằng tuần, không đợi cuối kỳ. |
| `TF4AIO-57` | Track LLM/API budget guard | Thông | Cost là production risk khi real LLM mở rộng. |
| `TF4AIO-49` | Package endpoint/eval/repro docs | Nam | Reviewer tái chạy và kiểm tra được. |
| `TF4AIO-50` | Prepare AIO Service Health Readout | Thông | Chốt AI health, eval, AIOps result và known risks. |

### Evidence rule

- Repo doc hoặc PR link.
- Jira comment có command/result.
- Query output cho telemetry task.
- Eval report cho quality/safety task.
- Screenshot chỉ dùng khi UI evidence là cần thiết.
- Không đóng task bằng local-only file path.

## 11. Dependency chain phải thuộc

### AIE

```text
Eval runner
  -> readiness checklist
  -> controlled real LLM
  -> fallback / timeout / circuit breaker / telemetry / cost
  -> Copilot MVP
  -> task-success eval
```

### AIOps

```text
Telemetry access
  -> selected taxonomy
  -> detection rules
  -> detector
  -> continuous deployment + output channel
  -> incident summary + runbook hint
  -> failure drill + validation report
```

## 12. Techlead opening answer

> Team AIO1 chia backlog thành AIE, AIOps và Ops. AIE làm AI feature đo được, reliable, safe rồi mới mở Copilot. AIOps dùng telemetry thật để detect hai incident MVP, tạo evidence-grounded summary và runbook hint; chưa overclaim auto-remediation. Ops giữ PR, evidence, cost guard và final readout. Thứ tự dựa trên dependency và risk: không có eval/fallback/telemetry thì real LLM và Copilot không defend được; không có query access/rule spec thì detector chỉ là dashboard thủ công.

## 13. Random-question answer format

Mỗi người trả lời theo mẫu:

```text
Em thuộc [AIE/AIOps/OPS] path.
Task chính của em là [task].
Task này cần vì [risk/dependency].
Done evidence là [PR/query/eval report/document].
Dependency hoặc blocker là [CDO access/real LLM config/signal/PR review].
```