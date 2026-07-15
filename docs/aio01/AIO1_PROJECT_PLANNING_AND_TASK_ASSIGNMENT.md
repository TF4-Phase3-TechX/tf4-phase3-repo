# AIO1 Project Planning & Task Assignment

Date: 2026-07-09

Purpose: tài liệu tổng hợp để mentor review cách team AIO1 chia việc cho toàn project Phase 3, gồm Week 1 baseline/planning và Week 2-3 build/validation.

## 1. Team structure

| Role | Member |
| --- | --- |
| Tech Lead | Đinh Danh Nam |
| PM | Trần Đình Thông |
| AIO | Nam, Hậu, Hòa, Tâm |
| AIE | Vũ, Thông, Văn |

## 2. Working principle

Week 1 của AIO1 tập trung vào discovery, assessment, baseline evidence và planning.

Team không claim real LLM readiness trong Week 1. Evidence hiện tại chứng minh AI baseline path hoạt động với mock OpenAI-compatible LLM, còn real LLM quality, fallback, eval, cost và telemetry là follow-up cho Week 2/3.

Week 2-3 chuyển sang implementation/validation có kiểm soát:

- AIE build AI reliability/safety/eval trước khi mở rộng feature.
- AIOps build detector MVP dựa trên telemetry thật, không overclaim root cause khi thiếu evidence.
- PM/Tech Lead giữ evidence, risk, PR, pitch và dependency với CDO.

## 3. Jira task assignment rule

- Task `Done`: không assign lại.
- Task `In Review`: không assign lại.
- Task `To Do` / `In Progress`: assign theo team structure để thấy rõ owner tiếp tục xử lý.

## 4. Current Jira task assignment

### Done

| Jira | Task | Owner | Note |
| --- | --- | --- | --- |
| `TF4AIO-21` | Prepare AIO Week 1 pitch notes | Done, no reassignment | Pitch notes đã có trên Jira |

### In Review

Các task này đã có evidence hoặc review note, nên không assign lại.

| Jira | Task | Evidence / note |
| --- | --- | --- |
| `TF4AIO-9` | Review current AI source and document AI flow | Source/AI flow review |
| `TF4AIO-11` | Record AI baseline findings and gaps | Linked to PR #34 evidence |
| `TF4AIO-12` | Define AIOps data sources and incident taxonomy | AIOps foundation review |
| `TF4AIO-13` | Confirm observability access for AIOps | Grafana/Jaeger access evidence |
| `TF4AIO-17` | Prepare AIO Week 1 evidence package and Ops Review notes | Evidence package |
| `TF4AIO-18` | Record AIO Week 1 decisions | Decision log |

### In Progress

| Jira | Task | Suggested owner | Track | Reason |
| --- | --- | --- | --- | --- |
| `TF4AIO-10` | Run AI smoke test on TF4 EKS baseline | Văn | AIE | Smoke test and runtime evidence |
| `TF4AIO-14` | Select AIOps MVP incident types | Hòa | AIO | AIOps incident taxonomy and MVP scope |
| `TF4AIO-15` | Define initial AI eval rubric and cases | Vũ | AIE | Eval rubric/cases |
| `TF4AIO-16` | Audit AI telemetry gaps | Thông | AIE / PM | Telemetry gap and follow-up planning |

### To Do

| Jira | Task | Suggested owner | Track | Reason |
| --- | --- | --- | --- | --- |
| `TF4AIO-19` | Prepare AIO incident/postmortem readiness note | Thông | PM / AIE | Operational readiness and postmortem format |
| `TF4AIO-20` | Monitor mandates and reserve capacity | Thông | PM | PM-owned tracking/capacity buffer |

## 5. Evidence currently on PR

Evidence PR:

- https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/34

Evidence files in PR:

| File | Purpose |
| --- | --- |
| `docs/evidence/aio1-week1/README.md` | Evidence index |
| `docs/evidence/aio1-week1/evidence.md` | AIO1 Week 1 AI baseline evidence |
| `docs/evidence/aio1-week1/screenshots/ai-smoke-test-product-page.png` | AI smoke test screenshot |
| `docs/evidence/aio1-week1/screenshots/grafana-access.png` | Grafana access screenshot |
| `docs/evidence/aio1-week1/screenshots/jaeger-access.png` | Jaeger access screenshot |
| `docs/evidence/epic-01/013-ai-01-obs-02-telemetry-redaction.md` | AI-01 telemetry/privacy evidence baseline |
| `docs/evidence/epic-01/014-ai-02-ai-fallback-eval-cost-baseline.md` | AI-02 fallback/eval/cost evidence baseline |

## 6. Remaining actions

| Priority | Action | Owner |
| --- | --- | --- |
| P0 | Merge PR #34 so Jira evidence links point to repo instead of local files | Nam / reviewer |
| P1 | Add/confirm PR evidence links on any Jira comments that still mention local paths | Nam / PM |
| P1 | Finish `TF4AIO-14`: choose AIOps MVP incidents | Hòa |
| P1 | Finish `TF4AIO-19`: incident/postmortem readiness note | Thông |
| P1 | Finish `TF4AIO-20`: mandate monitoring note | Thông |
| P2 | Move eligible tasks to `In Review` after owner comments evidence | PM |

## 7. Full project task plan

### 7.1 AIE track — AI Engineering

Owner group: Vũ, Thông, Văn.

Goal: make AI feature measurable, safer, more reliable, and ready for real LLM / Copilot work.

| Phase | Task | Owner | Output / Done Criteria | Jira status |
| --- | --- | --- | --- | --- |
| W1 | Review current AI source and document flow | Văn / Nam | Current AI flow + mock LLM behavior documented | `TF4AIO-9` In Review |
| W1 | Run AI smoke test on TF4 baseline | Văn | UI response, mock LLM status, Grafana/Jaeger evidence | `TF4AIO-10` In Progress |
| W1 | Record AI findings/gaps | Nam / PM | AI-01, AI-02, real LLM gap, eval/fallback/cost gap | `TF4AIO-11` In Review |
| W1-W2 | Define eval rubric and initial cases | Vũ | Faithfulness/relevance/safety rubric + 5-10 cases | `TF4AIO-15` In Progress |
| W1-W2 | Audit AI telemetry gaps | Thông | Missing latency/token/cost/error/fallback metrics identified | `TF4AIO-16` In Progress |
| W2 | Run eval on mock/current LLM | Vũ | Pass/fail report, limitation clearly stated | `TF4AIO-22` To Do |
| W2 | Add/test safe fallback for LLM failure | Văn | Timeout/rate-limit/unavailable returns safe fallback | `TF4AIO-24` To Do |
| W2 | Test incident flags `llmRateLimitError` and `llmInaccurateResponse` | Văn | Flags still work and are not bypassed | `TF4AIO-51` To Do |
| W2 | Add real LLM readiness checklist | Thông / Nam | Secret/config/eval/fallback/cost gate checklist | `TF4AIO-25` To Do |
| W2-W3 | Add AI-specific metrics/log fields if needed | Thông / Văn | latency/error/fallback/token/cost markers | `TF4AIO-52` To Do |
| W2-W3 | Natural-language product search MVP | Vũ / Văn | User query returns relevant products | `TF4AIO-32` To Do |
| W2-W3 | Grounded Q&A over product reviews | Vũ / Văn | Answer grounded in product/review facts; refuses unknown | `TF4AIO-33` To Do |
| W3 | Cart action with confirmation gate | Văn | No cart mutation without explicit confirmation | `TF4AIO-35` To Do |
| W3 | Copilot task-success eval | Vũ | Task success/failure report for core intents | `TF4AIO-55` To Do |

### 7.2 AIOps track — AI for Operations

Owner group: Nam, Hậu, Hòa, Tâm.

Goal: build a small AIOps MVP that can use observability data to detect incidents, summarize symptoms, and suggest runbook hints.

| Phase | Task | Owner | Output / Done Criteria | Jira status |
| --- | --- | --- | --- | --- |
| W1 | Define AIOps data sources and incident taxonomy | Hòa / Nam | Data source mapping + incident taxonomy | `TF4AIO-12` In Review |
| W1 | Confirm observability access | Nam / Hòa | Grafana/Jaeger access evidence | `TF4AIO-13` In Review |
| W1-W2 | Select MVP incident types | Hòa | Choose 2-3 MVP incidents, likely latency spike, error spike, LLM timeout/error | `TF4AIO-14` In Progress |
| W2 | Define detection rules/thresholds | Hòa / Hậu | Rule spec for selected incidents | `TF4AIO-37` To Do |
| W2-W3 | Build rule-based detector prototype | Hậu / Tâm | Detector runs on sample/live metrics and emits structured JSONL output to logs | `TF4AIO-38` To Do |
| W2-W3 | Detect AI-specific LLM timeout/error | Hậu / Tâm | Detector identifies AI path issue when signal exists | `TF4AIO-41` To Do |
| W2-W3 | Define incident summary format | Nam / Hòa | Summary template with symptoms/evidence/impact | `TF4AIO-42` To Do |
| W2-W3 | Build incident summary MVP | Tâm / Hậu | Summary generated from detector signals | `TF4AIO-43` To Do |
| W2-W3 | Map incident type to runbook actions | Hòa / Nam | Runbook hints for each MVP incident | `TF4AIO-44` To Do |
| W3 | Validate latency/error detector with load test | Hậu / Tâm + CDO dependency | Detector catches controlled degradation or limitation is documented; false positives/negatives are recorded | `TF4AIO-56` To Do |
| W3 | Validate LLM timeout/error signal | Hậu / Tâm + AIE dependency | AIOps recognizes AI path issue | `TF4AIO-45` To Do |
| W3 | Write AIOps validation report | Hòa / Nam | What worked, what failed, false positives/limitations | `TF4AIO-46` To Do |

Ghi chú triển khai cho TF4AIO-6: workload detector đã được thêm vào chart Helm như một Deployment liên tục, có giới hạn tài nguyên và không thay đổi flagd/openfeature. Channel đầu ra đầu tiên được chọn là structured JSONL logs (`stdout-jsonl`), với payload schema và owner response path được ghi trong [docs/aio01/TF4AIO-6-detector-evidence.md](./TF4AIO-6-detector-evidence.md). Artifact render để review nhanh tại [docs/aio01/evidence/tf4aio6-detector-render-snippet.yaml](./evidence/tf4aio6-detector-render-snippet.yaml). Trạng thái runtime inventory trên cluster `techx-tf4` đang chờ mở khóa credential/kube-context để bổ sung bằng chứng triển khai trực tiếp.

### 7.3 Operational / PM track

Owner group: Nam, Thông.

Goal: keep project defensible with evidence, PRs, decision logs, readiness notes, and review material.

| Phase | Task | Owner | Output / Done Criteria | Jira status |
| --- | --- | --- | --- | --- |
| W1 | Prepare evidence package | Nam / Thông | Repo-backed PR evidence, no local-only paths | `TF4AIO-17` In Review |
| W1 | Record Week 1 decisions | Thông / Nam | Decision log: mock LLM W1, defer real LLM, defer full Copilot/AIOps | `TF4AIO-18` In Review |
| W1 | Prepare pitch notes | Thông / Nam | Week 1 pitch notes | `TF4AIO-21` Done |
| W1-W2 | Prepare incident/postmortem readiness note | Thông | AI incident categories + evidence required + postmortem format | `TF4AIO-19` To Do |
| W1-W3 | Monitor mandates and reserve capacity | Thông | Mandate check note; update backlog if new requirements appear | `TF4AIO-20` To Do |
| W2 | Create Week 2 implementation PR plan | Nam / Thông | PR list by AIE/AIOps/OPS | `TF4AIO-47` To Do |
| W2-W3 | Weekly Ops Review AIO section | Thông | AI status/risk/evidence/incident/next action | `TF4AIO-48` To Do |
| W3 | Package final endpoint/eval/repro docs | Nam / Thông | Submission package: endpoint, eval command, evidence, limitations | `TF4AIO-49` To Do |
| W3 | Prepare AIO Service Health Readout | Thông / Nam | Final summary: AI health, eval result, AIOps result, known risks | `TF4AIO-50` To Do |

## 8. Jira creation backlog

The current Jira board has Week 1 tasks plus high-level epics. The following task groups should be created next for full project tracking.

### Create for AIE Week 2

- `[W2][AIE] Run eval on mock/current LLM`
- `[W2][AIE] Implement/test safe fallback for LLM failure`
- `[W2][AIE] Test LLM incident flags`
- `[W2][AIE] Add real LLM readiness checklist`
- `[W2][AIE] Add AI-specific telemetry metrics/log fields`

### Create for AIE Week 2-3 / Copilot

- `[W2-W3][AIE] Natural-language product search MVP`
- `[W2-W3][AIE] Grounded Q&A over product reviews`
- `[W3][AIE] Cart action with confirmation gate`
- `[W3][AIE] Copilot task-success eval`

### Create for AIOps Week 2-3

- `[W2][AIOPS] Define detection rules and thresholds`
- `[W2-W3][AIOPS] Build rule-based detector prototype`
- `[W2-W3][AIOPS] Detect AI-specific LLM timeout/error`
- `[W2-W3][AIOPS] Define incident summary format`
- `[W2-W3][AIOPS] Build incident summary MVP`
- `[W2-W3][AIOPS] Map incident types to runbook actions`
- `[W3][AIOPS] Validate detector with load test/failure drill`
- `[W3][AIOPS] Write AIOps validation report`

### Create for OPS Week 2-3

- `[W2][OPS] Create Week 2 implementation PR plan`
- `[W2-W3][OPS] Prepare AIO weekly Ops Review section`
- `[W3][OPS] Package endpoint/eval/repro documentation`
- `[W3][OPS] Prepare AIO Service Health Readout`

## 9. Mentor-review summary

Team AIO1 đã chia việc theo 3 nhóm chính cho toàn project:

1. AI baseline discovery/evidence: đọc source, smoke test mock LLM, ghi findings.
2. AI reliability/safety planning: eval, fallback, telemetry/privacy, cost gate.
3. AIOps planning: data sources, incident taxonomy, observability access, readiness/postmortem.

Week 1 scope là planning + evidence. Team chưa claim real LLM readiness; real LLM quality, cost, fallback và telemetry sẽ được xử lý sau khi có eval/fallback/cost plan rõ ràng.
