# AIO1 Project Planning & Task Assignment

Date: 2026-07-09

Purpose: document how AIO1 splits work for the full Phase 3 project, including Week 1 discovery/evidence and Week 2-3 implementation/validation. This file is intended for mentor review and team alignment.

## 1. Team structure

| Role | Member |
| --- | --- |
| Tech Lead | Đinh Danh Nam |
| PM | Trần Đình Thông |
| AIO | Nam, Hậu, Hòa, Tâm |
| AIE | Vũ, Thông, Văn |

## 2. Working principle

Week 1 của AIO1 tập trung vào discovery, assessment, baseline evidence và planning.

Team không claim real LLM readiness trong Week 1. Evidence hiện tại chỉ chứng minh AI baseline path hoạt động với mock OpenAI-compatible LLM. Real LLM quality, fallback, eval, cost và telemetry là follow-up cho Week 2/3.

Week 2-3 chuyển sang implementation/validation có kiểm soát:

- AIE build AI reliability, safety, eval, fallback và Copilot guardrails trước khi mở rộng feature.
- AIOps build detector MVP dựa trên telemetry thật, không overclaim root cause khi thiếu evidence.
- PM/Tech Lead giữ evidence, risk, PR, pitch, Jira hygiene và dependency với CDO.

Capacity buffer:

- W2/W3 giữ 20% capacity, tương đương khoảng 1 ngày/người/tuần, không assign cố định để xử lý BTC directive và incident response.
- Backlog không allocate 100% capacity vào planned work.

Task ownership rule:

- Mỗi task có đúng 1 Primary owner.
- Nếu cần reviewer, ghi format `Primary -> Reviewer`.
- Không dùng format `A / B` vì dễ mờ accountability.

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
| P0 | Merge PR #34 so Jira evidence links point to repo instead of local files | Nam -> reviewer |
| P1 | Add/confirm PR evidence links on any Jira comments that still mention local paths | Nam -> Thông |
| P1 | Finish `TF4AIO-14`: choose AIOps MVP incidents | Hòa |
| P1 | Finish `TF4AIO-19`: incident/postmortem readiness note | Thông |
| P1 | Finish `TF4AIO-20`: mandate monitoring note | Thông |
| P2 | Move eligible tasks to `In Review` after owner comments evidence | Thông -> Nam |

## 7. Full project task plan

### 7.1 AIE track — AI Engineering

Owner group: Vũ, Thông, Văn.

Goal: make AI feature measurable, safer, more reliable, and ready for real LLM / Copilot work.

| Phase | Task | Owner | Output / Done Criteria | Jira status |
| --- | --- | --- | --- | --- |
| W1 | Review current AI source and document flow | Văn -> Nam | Current AI flow + mock LLM behavior documented | `TF4AIO-9` In Review |
| W1 | Run AI smoke test on TF4 baseline | Văn | UI response, mock LLM status, Grafana/Jaeger evidence | `TF4AIO-10` In Progress |
| W1 | Record AI findings/gaps | Nam -> Thông | AI-01, AI-02, real LLM gap, eval/fallback/cost gap | `TF4AIO-11` In Review |
| W1-W2 | Define eval rubric and initial cases | Vũ | Faithfulness/relevance/safety rubric + 5-10 cases | `TF4AIO-15` In Progress |
| W1-W2 | Audit AI telemetry gaps | Thông | Missing latency/token/cost/error/fallback metrics identified | `TF4AIO-16` In Progress |
| W2 | Run eval on mock/current LLM | Vũ | Pass/fail report, limitation clearly stated | New Jira task needed |
| W2 | Add/test safe fallback for LLM failure | Văn | Timeout/rate-limit/unavailable returns safe fallback | New Jira task needed |
| W2 | Test incident flags `llmRateLimitError` and `llmInaccurateResponse` | Văn | Flags still work and are not bypassed | New Jira task needed |
| W2 | Add real LLM readiness checklist | Thông -> Nam | Secret/config/eval/fallback/cost gate checklist | New Jira task needed |
| W2 | Implement prompt injection guardrail for review content | Văn -> Vũ | Injection from review content cannot override summarization intent | New Jira task needed |
| W2 | Implement PII and system prompt output filter | Văn -> Vũ | Output does not expose PII or system prompt content | New Jira task needed |
| W2 | Fix DB connection pooling in `product-reviews` | Văn -> Nam | No new DB connection per request under load | New Jira task needed |
| W2 | Add LLM call timeout and circuit breaker | Văn -> Nam | Slow LLM call does not exhaust gRPC/thread workers | New Jira task needed |
| W2 | Monitor and alert LLM API cost | Thông -> Nam | LLM spend visible; alert threshold defined | New Jira task needed |
| W2-W3 | Add AI-specific metrics/log fields if needed | Thông -> Văn | latency/error/fallback/token/cost markers | New Jira task needed |
| W2 | Design Copilot architecture and tool wiring plan | Nam -> Vũ | Architecture diagram, tool registry, service boundary | New Jira task needed |
| W2-W3 | Natural-language product search MVP | Vũ -> Văn | User query returns relevant products | New Jira task needed |
| W2-W3 | Grounded Q&A over product reviews | Vũ -> Văn | Answer grounded in product/review facts; refuses unknown | New Jira task needed |
| W2-W3 | Implement multi-turn conversation memory | Vũ -> Văn | Agent resolves context like "it", "the first one" | New Jira task needed |
| W2-W3 | Implement tool allow-list and excessive-agency guardrail | Văn -> Vũ | Agent is blocked when calling tools outside allow-list | New Jira task needed |
| W2-W3 | Implement agent loop limit and tool audit log | Văn -> Vũ | Max loop limit enforced; tool arguments logged | New Jira task needed |
| W3 | Cart action with confirmation gate | Văn -> Vũ | No cart mutation without explicit confirmation | New Jira task needed |
| W3 | Copilot task-success eval | Vũ | Task success/failure report for core intents | New Jira task needed |

### 7.2 AIOps track — AI for Operations

Owner group: Nam, Hậu, Hòa, Tâm.

Goal: build a small AIOps MVP that can use observability data to detect incidents, summarize symptoms, and suggest runbook hints.

| Phase | Task | Owner | Output / Done Criteria | Jira status |
| --- | --- | --- | --- | --- |
| W1 | Define AIOps data sources and incident taxonomy | Hòa -> Nam | Data source mapping + incident taxonomy | `TF4AIO-12` In Review |
| W1 | Confirm observability access | Nam -> Hòa | Grafana/Jaeger access evidence | `TF4AIO-13` In Review |
| W1-W2 | Select MVP incident types | Hòa | Choose 2-3 MVP incidents, likely latency spike, error spike, LLM timeout/error | `TF4AIO-14` In Progress |
| W2 | Verify Prometheus/OpenSearch query access from AIOps agent | Hòa -> Hậu | PromQL/OpenSearch query returns real data; code snippet or screenshot captured | New Jira task needed |
| W2 | Define detection rules/thresholds | Hòa -> Hậu | Rule spec for selected incidents | New Jira task needed |
| W2-W3 | Build rule-based detector prototype | Hậu -> Tâm | Detector runs on sample/live metrics | New Jira task needed |
| W2-W3 | Deploy detector as continuous K8s workload | Hậu -> Tâm | Detector runs automatically every 1-2 minutes as CronJob/Pod or equivalent | New Jira task needed |
| W2-W3 | Detect AI-specific LLM timeout/error | Hậu -> Tâm | Detector identifies AI path issue when signal exists | New Jira task needed |
| W2-W3 | Define incident summary format | Nam -> Hòa | Summary template with symptoms/evidence/impact | New Jira task needed |
| W2-W3 | Build incident summary MVP | Tâm -> Hậu | Summary generated from detector signals | New Jira task needed |
| W2-W3 | Map incident type to runbook actions | Hòa -> Nam | Runbook hints for each MVP incident | New Jira task needed |
| W3 | Validate latency/error detector with load test | Hậu -> Tâm | Detector catches controlled degradation; CDO dependency noted | New Jira task needed |
| W3 | Validate LLM timeout/error signal | Hậu -> Tâm | AIOps recognizes AI path issue; AIE dependency noted | New Jira task needed |
| W3 | Write AIOps validation report | Hòa -> Nam | What worked, what failed, false positives/limitations | New Jira task needed |

### 7.3 Operational / PM track

Owner group: Nam, Thông.

Goal: keep project defensible with evidence, PRs, decision logs, readiness notes, budget awareness, and review material.

| Phase | Task | Owner | Output / Done Criteria | Jira status |
| --- | --- | --- | --- | --- |
| W1 | Prepare evidence package | Nam -> Thông | Repo-backed PR evidence, no local-only paths | `TF4AIO-17` In Review |
| W1 | Record Week 1 decisions | Thông -> Nam | Decision log: mock LLM W1, defer real LLM, defer full Copilot/AIOps | `TF4AIO-18` In Review |
| W1 | Prepare pitch notes | Thông -> Nam | Week 1 pitch notes | `TF4AIO-21` Done |
| W1-W2 | Prepare incident/postmortem readiness note | Thông | AI incident categories + evidence required + postmortem format | `TF4AIO-19` To Do |
| W1-W3 | Monitor mandates and reserve capacity | Thông | Mandate check note; update backlog if new requirements appear | `TF4AIO-20` To Do |
| W2 | Create implementation PR plan | Nam -> Thông | PR list by AIE/AIOps/OPS | New Jira task needed |
| W2-W3 | Weekly Ops Review AIO section | Thông | AI status/risk/evidence/incident/next action | New Jira task needed |
| W2-W3 | Track LLM/API budget guard | Thông -> Nam | Weekly cost note and alert threshold | New Jira task needed |
| W3 | Package final endpoint/eval/repro docs | Nam -> Thông | Submission package: endpoint, eval command, evidence, limitations | New Jira task needed |
| W3 | Prepare AIO Service Health Readout | Thông -> Nam | Final summary: AI health, eval result, AIOps result, known risks | New Jira task needed |

## 8. Jira creation backlog

The current Jira board has Week 1 tasks plus high-level epics. The following task groups should be created next for full project tracking.

### Create for AIE Week 2 — Reliability, eval, safety

- `[W2][AIE] Run eval on mock/current LLM`
- `[W2][AIE] Implement/test safe fallback for LLM failure`
- `[W2][AIE] Test LLM incident flags`
- `[W2][AIE] Add real LLM readiness checklist`
- `[W2][AIE] Implement prompt injection guardrail for review content`
- `[W2][AIE] Implement PII and system prompt output filter`
- `[W2][AIE] Fix DB connection pooling in product-reviews`
- `[W2][AIE] Add LLM call timeout and circuit breaker`
- `[W2][AIE] Monitor and alert LLM API cost`
- `[W2-W3][AIE] Add AI-specific telemetry metrics/log fields`

### Create for AIE Week 2-3 — Copilot cross-cutting and feature work

- `[W2][AIE] Design Copilot architecture and tool wiring plan`
- `[W2-W3][AIE] Natural-language product search MVP`
- `[W2-W3][AIE] Grounded Q&A over product reviews`
- `[W2-W3][AIE] Implement multi-turn conversation memory`
- `[W2-W3][AIE] Implement tool allow-list and excessive-agency guardrail`
- `[W2-W3][AIE] Implement agent loop limit and tool audit log`
- `[W3][AIE] Cart action with confirmation gate`
- `[W3][AIE] Copilot task-success eval`

### Create for AIOps Week 2-3

- `[W2][AIOPS] Verify Prometheus/OpenSearch programmatic query access`
- `[W2][AIOPS] Define detection rules and thresholds`
- `[W2-W3][AIOPS] Build rule-based detector prototype`
- `[W2-W3][AIOPS] Deploy detector as continuous K8s workload`
- `[W2-W3][AIOPS] Detect AI-specific LLM timeout/error`
- `[W2-W3][AIOPS] Define incident summary format`
- `[W2-W3][AIOPS] Build incident summary MVP`
- `[W2-W3][AIOPS] Map incident types to runbook actions`
- `[W3][AIOPS] Validate detector with load test/failure drill`
- `[W3][AIOPS] Validate LLM timeout/error signal`
- `[W3][AIOPS] Write AIOps validation report`

### Create for OPS Week 2-3

- `[W2][OPS] Create implementation PR plan`
- `[W2-W3][OPS] Prepare AIO weekly Ops Review section`
- `[W2-W3][OPS] Track LLM/API budget guard`
- `[W3][OPS] Package endpoint/eval/repro documentation`
- `[W3][OPS] Prepare AIO Service Health Readout`

## 9. Mentor-review summary

Team AIO1 chia việc theo 3 nhóm chính cho toàn project:

1. AI baseline discovery/evidence: đọc source, smoke test mock LLM, ghi findings.
2. AI engineering: eval, fallback, telemetry/privacy, safety guardrails, cost guard, Copilot architecture và feature MVP.
3. AIOps: data sources, incident taxonomy, detector MVP, continuous deployment, incident summary, runbook hints và validation report.

Week 1 scope là planning + evidence. Team chưa claim real LLM readiness; real LLM quality, cost, fallback, telemetry và Copilot/AIOps implementation sẽ được xử lý trong Week 2/3 với Jira task riêng.

Before entering W2, the remaining planning actions are:

- Create the missing W2/W3 Jira tickets listed in Section 8.
- Keep 20% capacity unassigned for BTC directive and incident response.
- Use `Primary -> Reviewer` ownership for all new tasks.

## 10. AI gap reasoning to defend backlog

This section maps each AI-related backlog group to concrete evidence from requirements/source code. Use this when mentor asks "why is this task necessary?" or "is this over-scoped?".

### 10.1 Core requirement: AIO owns both AIE and AIOps

| Evidence | What it means | Backlog defended |
| --- | --- | --- |
| `docs/requirements/RULES.md:48-50` says AIO owns two directions: AIOps and AIE. | AIO work is not optional support work for CDO. It is a separate AI pillar. | Keep both AIE and AIOps epics/tasks in Jira. |
| `docs/requirements/RULES.md:28-30` says each TF runs as a mini product org and AIO/CDO work cross-functionally. | AIO should not wait passively for CDO. AIO must prepare AI backlog, evidence, and dependencies. | Planning, evidence package, PR plan, Ops Review section. |
| `phase3/onboarding/AI_FEATURE.md:18-21`, `:23-47`, `:59-74` define AIE baseline work, Shopping Copilot, eval/repro, safety, and continuous AIOps. | The W2/W3 backlog is a direct breakdown of the AI onboarding requirement, not extra scope invented by AIO1. | Safety, eval, Copilot, AIOps detector, task-success eval, reproducible evidence. |

### 10.2 Backlog defense matrix

| Gap / risk | Source evidence | Why this matters | Backlog task(s) defended | Short defense answer |
| --- | --- | --- | --- | --- |
| AI summary must not be misleading, but current system has an explicit inaccurate-response incident flag. | `docs/requirements/onboarding/SLO.md:13`; `phase3/onboarding/AI_FEATURE.md:18-21`; `techx-corp-platform/src/flagd/demo.flagd.json:4-15`; `product_reviews_server.py:269-295`. | Even though AI is best-effort, wrong customer-facing summaries are explicitly not acceptable. | Eval rubric, eval cases, inaccurate-response test, response validation/fallback. | "This is not nice-to-have. SLO and AI_FEATURE say summaries must be faithful, and the repo has a protected flag that can force wrong AI output." |
| Normal LLM calls have no timeout/circuit breaker and are outside the rate-limit fallback branch. | `product_reviews_server.py:218-223`, `product_reviews_server.py:292-295`; gRPC thread pool is only `max_workers=10` at `product_reviews_server.py:361`. | Slow/failed real LLM can occupy handlers and degrade the service. | Add LLM timeout + circuit breaker; safe fallback for LLM failure. | "Once real LLM is enabled, one slow dependency can hold the AI path. Timeout/circuit breaker protects the service, not just the AI feature." |
| Rate-limit incident is expected by BTC and cannot be removed. | `docs/requirements/RULES.md:111-112`; `GETTING_STARTED.md:109-112`; `product_reviews_server.py:164-201`; `llm/app.py:120-130`. | We must make the service resilient to injected failure, not disable flagd. | Test `llmRateLimitError`; fallback UX; incident handling evidence. | "BTC can turn this on. We defend by proving fallback behavior, not by removing the flag." |
| Prompt/question content is captured in telemetry/logs by default. | `product_reviews_server.py:162`, `product_reviews_server.py:228`, `product_reviews_server.py:290-301`; `llm/app.py:94-98`, `llm/app.py:168-187`; Helm has `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` at `values.yaml:624-625`. | Customer prompt/review content can appear in Jaeger/OpenSearch/Grafana evidence surfaces. This is an AI safety/privacy issue before real LLM. | PII/system prompt output filter; telemetry redaction; audit AI telemetry gaps. | "We need privacy controls because the current baseline records prompt/message content by design." |
| Prompt injection risk exists because user question and review content are passed into the LLM/tool loop with no sanitization or output validation. | `phase3/onboarding/AI_FEATURE.md:20`; user question is embedded directly at `product_reviews_server.py:211-214`; tool outputs are appended at `product_reviews_server.py:244-266`; final LLM answer is returned directly at `product_reviews_server.py:297-305`. | Malicious review/user text could steer the model or leak unsafe content when real LLM is enabled. | Prompt injection guardrail; output filter; grounded Q&A eval. | "The model receives raw customer/review text. AI_FEATURE explicitly calls out prompt injection in review content, so guardrails and evals are required." |
| Tool-calling path has only two allowed tools but no explicit tool registry/audit policy for future Copilot. | `phase3/onboarding/AI_FEATURE.md:23-47`; tool schema exists at `product_reviews_server.py:52-88`; unexpected tool raises exception at `product_reviews_server.py:256-257`; tool calls and args are logged at `product_reviews_server.py:238-248`. | Current feature is small, but Copilot will add more tools/actions. Without allow-list, loop limit, and audit log, agent behavior is hard to defend. | Copilot architecture/tool wiring; tool allow-list; agent loop limit; tool audit log. | "Copilot is an agentic feature. AI_FEATURE requires tool allow-list, loop limit, confirmation gates, and audit logs." |
| Current frontend AI interaction is single-turn and product-scoped. It has no conversation memory. | `phase3/onboarding/AI_FEATURE.md:44`; `ProductAIAssistant.provider.tsx:41-43`; `ProductReviews.tsx:56-64`, `ProductReviews.tsx:103-127`. | Copilot requirement needs follow-up context such as "nó" or "cái đầu tiên"; current UI sends independent questions only. | Multi-turn conversation memory; Copilot architecture. | "Current AI assistant is not Copilot yet. Memory is a separate story because the current provider only sends one question per mutation." |
| Cart/action safety is not represented in the current AI UI. | `phase3/onboarding/AI_FEATURE.md:30-34`, `:45`; current AI UI only asks questions and renders answer: `ProductReviews.tsx:74-140`. | If Copilot can add to cart later, it needs explicit confirmation and excessive-agency guardrails. | Cart action with confirmation gate; excessive-agency guardrail. | "Search/Q&A and cart mutation have different risk. AI_FEATURE requires confirmation before write actions and forbids automatic checkout/delete-cart." |
| Current AI metric only counts requests; it does not expose latency, token usage, cost, fallback count, or LLM error reason. | `phase3/onboarding/AI_FEATURE.md:61-62`; `metrics.py:13-16`; increment only at `product_reviews_server.py:307-308`; mock LLM response includes token-ish usage at `llm/app.py:153-187` but product-reviews does not export it. | We cannot defend real LLM readiness or budget without per-request telemetry. | Add AI-specific metrics/log fields; audit telemetry gaps; LLM cost monitoring. | "A counter alone cannot tell us if AI is slow, expensive, failing, or falling back. AI_FEATURE says improvements must be measured and reproducible." |
| Real LLM overlay only swaps endpoint/model/key; it does not add eval, timeout, fallback, or budget controls. | `phase3/onboarding/AI_FEATURE.md:13`, `:78-82`; `deploy/values-aio-llm.yaml:1-11`; baseline uses dummy key/mock URL at `values.yaml:600-609`. | Turning on real LLM changes latency, quality, error rate, and cost profile. | Real LLM readiness checklist; eval before real LLM; cost guard; fallback. | "The overlay makes real LLM possible, but AI_FEATURE says eval and guardrail come before expanding. Readiness requires quality, reliability, and spend gates." |
| DB connection is opened per product-review request and per average-score request. | `database.py:33-51`; `database.py:60-89`; incident history mentions DB connection exhaustion and pool/timeout fix at `INCIDENT_HISTORY.md:13-14`. | AI tool calls fetch reviews from DB. Under load, AI can contribute to DB connection churn. | Fix DB connection pooling in product-reviews; load/eval validation. | "This is directly tied to known incident history. AI calls use the same review DB path." |
| Observability is available but not enough for AIOps until programmatic queries are verified. | Prometheus exposes OTLP labels in `values.yaml:1131-1175`; Grafana/OpenSearch/Jaeger are deployed in `values.yaml:1182-1233`; SLO doc says source of measurement is Prometheus/Grafana at `SLO.md:29`. | AIOps detector must use real telemetry, not screenshots/manual UI only. | Verify Prometheus/OpenSearch query access; define detection rules; build detector. | "AIOps must consume telemetry as data. UI access proves visibility, not detector readiness." |
| Detector must run continuously to count as operational AIOps, not just a local script. | RULES frames AIOps as using observability for detection/incident support at `RULES.md:49`; `phase3/onboarding/AI_FEATURE.md:72-73`; Ops Review expects service status weekly at `RULES.md:90`. | A local one-shot analysis does not help during on-call or incident injection. | Deploy detector as continuous K8s workload; incident summary MVP; Ops Review section. | "For operations, detection must run while the system runs. AI_FEATURE explicitly says AIOps must run continuously, not demo once." |
| Budget risk increases when real LLM is enabled and load generator includes AI traffic. | Budget constraints and AWS Budgets are required by `BUDGET.md:15`, `BUDGET.md:20-21`; load-generator has AI task at `locustfile.py:150-159`; real LLM overlay at `values-aio-llm.yaml:6-11`. | AI calls add external API spend on top of AWS infrastructure budget. | Monitor and alert LLM API cost; track LLM/API budget guard. | "Real LLM cost is not visible from AWS-only dashboards unless we explicitly track usage/spend." |

### 10.3 How to answer mentor pushback

| Mentor pushback | Answer |
| --- | --- |
| "Week 1 chỉ planning, sao backlog nhiều vậy?" | Week 1 deliverable is not to implement all of this. The purpose is to show we found AI gaps and turned them into W2/W3 backlog with priority and owners. |
| "Có cần real LLM ngay không?" | No. Week 1 evidence only proves mock baseline. Real LLM should wait until eval, fallback, timeout, telemetry, and cost gates exist. |
| "AIOps có overkill không?" | No, because RULES explicitly defines AIOps as AIO responsibility. MVP scope is small: verify telemetry query, detect 2-3 incident types, summarize evidence, and run continuously. |
| "Sao phải làm safety/guardrail?" | Because SLO says AI summary cannot be misleading, source has inaccurate-response and rate-limit flags, and current path passes raw prompt/review content through LLM/logs. |
| "Sao phải làm cost monitoring riêng cho LLM?" | AWS budget covers infrastructure, but real LLM introduces external per-token/call spend. The repo overlay enables real LLM but does not add cost controls. |
