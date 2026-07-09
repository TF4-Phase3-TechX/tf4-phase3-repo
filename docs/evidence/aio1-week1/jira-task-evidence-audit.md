# AIO1 Jira Task Evidence Audit

Date: 2026-07-09  
Jira project: `TF4AIO` (`TF4 Phase 3 - AIO01`)  
Scope scanned: `TF4AIO-1` through `TF4AIO-21`

This audit consolidates the evidence currently referenced by AIO1 Jira tasks and flags inconsistencies that should be fixed before the Week 1 pitch/review.

## 1. Canonical evidence folder

Use this folder as the canonical Week 1 AIO evidence package:

- `docs/evidence/aio1-week1/evidence.md`
- `docs/evidence/aio1-week1/ai-eval-rubric-baseline.md`
- `docs/evidence/aio1-week1/aiops-data-sources-taxonomy.md`
- `docs/evidence/aio1-week1/ai-incident-postmortem-readiness.md`
- `docs/evidence/aio1-week1/mandate-capacity-review.md`
- `docs/evidence/aio1-week1/screenshots/ai-smoke-test-product-page.png`
- `docs/evidence/aio1-week1/screenshots/grafana-access.png`
- `docs/evidence/aio1-week1/screenshots/jaeger-access.png`

Related cross-epic evidence:

- `docs/evidence/epic-01/013-ai-01-obs-02-telemetry-redaction.md`
- `docs/evidence/epic-01/014-ai-02-ai-fallback-eval-cost-baseline.md`

Related planning evidence:

- `docs/planning/AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md`

## 2. Jira task evidence map

| Jira | Current status at scan time | Evidence status | Canonical evidence / note |
| --- | --- | --- | --- |
| `TF4AIO-1` | To Do | OK as epic container | Epic for baseline discovery. Child task evidence is in `TF4AIO-9`, `TF4AIO-10`, `TF4AIO-11`, `TF4AIO-21`. |
| `TF4AIO-2` | To Do | OK as epic container | Epic for eval/faithfulness. Current baseline doc is `ai-eval-rubric-baseline.md`; implementation/report still W2. |
| `TF4AIO-3` | To Do | OK as epic container | Epic for reliability/fallback/safety. Evidence is in `014-ai-02-ai-fallback-eval-cost-baseline.md` and source findings in `evidence.md`. |
| `TF4AIO-4` | To Do | OK as future epic | Shopping Copilot is W2/W3 scope; no Week 1 build evidence expected. |
| `TF4AIO-5` | To Do | OK as epic container | AIOps foundation evidence is in `aiops-data-sources-taxonomy.md`. |
| `TF4AIO-6` | To Do | OK as future epic | Anomaly detector MVP is W2/W3 scope; no Week 1 live detector evidence expected. |
| `TF4AIO-7` | To Do | OK as future epic | Incident summary/runbook suggestion is W2/W3 scope; readiness template is in `ai-incident-postmortem-readiness.md`. |
| `TF4AIO-8` | To Do | OK as epic container | Ops evidence is in `evidence.md`, `mandate-capacity-review.md`, and `ai-incident-postmortem-readiness.md`. |
| `TF4AIO-9` | In Review | Good | Repo-backed comment exists. Evidence: source flow and mock LLM confirmation in `evidence.md`. |
| `TF4AIO-10` | In Progress | Inconsistent | Jira comments conflict: earlier comments say smoke test completed; a later comment says blocked due to EKS/kubeconfig. Evidence folder confirms UI/Grafana/Jaeger screenshots exist, but exact Jaeger trace ID and real LLM latency are not captured. |
| `TF4AIO-11` | In Review | Good | Findings are supported by `evidence.md`, `013-ai-01-obs-02-telemetry-redaction.md`, and `014-ai-02-ai-fallback-eval-cost-baseline.md`. |
| `TF4AIO-12` | In Progress | Partial | Jira comment still points to a local path. Canonical replacement should be `aiops-data-sources-taxonomy.md`. |
| `TF4AIO-13` | In Review | Good | Repo-backed comment exists. Evidence: Grafana and Jaeger screenshots in this folder. Programmatic Prometheus/OpenSearch access is still W2. |
| `TF4AIO-14` | In Review | Partial / overclaim risk | MVP incident selection exists in Jira, but claims about Prometheus histograms and emitted signals are not fully backed by repo evidence. Canonical conservative version is `aiops-data-sources-taxonomy.md`. |
| `TF4AIO-15` | In Review | Partial | Jira has repo link for AI-02, but the task-specific eval rubric/cases were only in comments/blob images. Canonical text version is now `ai-eval-rubric-baseline.md`. |
| `TF4AIO-16` | In Progress | Good / not complete | Telemetry gaps are evidence-backed. Important source evidence: `product_reviews_server.py` records `app.product.question`; metrics only include `app_ai_assistant_counter`; no token/cost/latency/fallback metrics yet. |
| `TF4AIO-17` | In Review | Good | Repo-backed evidence package comment exists and points to this folder. |
| `TF4AIO-18` | In Review | Good | Decision is consistent: Week 1 uses mock LLM; real LLM readiness is W2/W3 after eval/fallback/telemetry/cost gates. |
| `TF4AIO-19` | In Review | Good | Jira comment exists. Canonical repo copy is `ai-incident-postmortem-readiness.md`. |
| `TF4AIO-20` | In Review | Good | Jira comment exists. Canonical repo copy is `mandate-capacity-review.md`. |
| `TF4AIO-21` | In Review | Needs correction | Pitch-note comment overclaims code/eval evidence not found in the current repo. Do not use the claim as-is. See inconsistency item I-01 below. |

## 3. Source-verified evidence

Verified from the current repo:

- Mock LLM fixture source:
  - `techx-corp-platform/src/llm/app.py:21`
  - `techx-corp-platform/src/llm/product-review-summaries/product-review-summaries.json`
- Product reviews AI call path:
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:155`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:204-223`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:292-295`
- Rate-limit and inaccurate-response incident flags:
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:164-200`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:269-278`
  - `techx-corp-platform/src/llm/app.py:63-64`
- AI telemetry/privacy risk:
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:162` records the full user question in span attributes.
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:228` logs the model response message.
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:290-301` logs the message list and result.
  - `techx-corp-chart/values.yaml:624` enables GenAI message-content capture.
- Current AI metric scope:
  - `techx-corp-platform/src/product-reviews/metrics.py:13-16` defines only `app_ai_assistant_counter` for AI.
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:307-308` increments the AI request counter.
- DB connection pattern:
  - `techx-corp-platform/src/product-reviews/database.py:33`
  - `techx-corp-platform/src/product-reviews/database.py:60`
- gRPC worker pool:
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:361`

## 4. Inconsistencies found

### I-01 — Pitch notes overclaim code/eval/guardrail readiness

`TF4AIO-21` comment claims items such as:

- `ai_safety.py`
- `make aio-eval`
- `evals/aio_ai_eval.py`
- `evals/aio_copilot_eval.py`
- `src/aiops/`
- "8/8 safety checks PASS"
- "30/30 copilot intent checks PASS"
- "17 unit tests PASS"
- "8 OTel AI metrics"
- "guardrail 5 layers"

These were not found in the current repo scan. Current repo evidence supports only:

- AI path exists and works with the mock OpenAI-compatible LLM.
- There is an AI request counter.
- There are incident flags for rate-limit and inaccurate response paths.
- There are clear gaps for eval, guardrails, fallback, token/cost, latency, and AIOps detector work.

Action: rewrite or supersede the pitch note before using it with mentors/council.

### I-02 — `TF4AIO-10` has conflicting Jira comments

Evidence comments say both:

- smoke test completed with product page/Grafana/Jaeger evidence; and
- task is blocked because EKS/kubeconfig is not accessible.

The repo evidence confirms UI screenshots exist, so the conservative status is:

> Smoke-test UI evidence exists for the deployed public route, but exact Ask AI Jaeger trace ID, real LLM latency, and programmatic cluster/kubeconfig validation are not captured.

Action: owner should add one final clarification comment and keep the task status aligned with that comment.

### I-03 — Local-path evidence remains in older Jira comments

Older comments still contain Windows local-path evidence references under the project workspace and local screenshot folder.

Later comments on many tasks supersede them with PR links. The Jira tool available here cannot edit/delete old comments, so the safest fix is to add a latest superseding comment or remove old comments manually in Jira UI.

### I-04 — Evidence is split between `docs/evidence/...` and `w01/...`

The PR also contains `w01/[AIE-05] Run AI smoke test on TF4 EKS baseline/...` artifacts. They may be useful supporting artifacts, but they are outside the agreed `docs/` evidence convention.

Action: keep canonical links pointing to `docs/evidence/aio1-week1/`. Use `w01/` only as supplemental raw evidence if needed.

### I-05 — AIOps MVP selection makes signal-readiness claims without enough runtime evidence

`TF4AIO-14` says the LLM timeout/error signals and Prometheus histograms are already emitted/queryable. Current repo evidence does not include PromQL/API outputs for these claims.

Action: state MVP selection as a design decision, not runtime proof. Programmatic Prometheus/OpenSearch verification should be W2.

### I-06 — Eval task is in review, but implementation evidence is not present

`TF4AIO-15` is in review, but current repo scan does not show eval scripts or generated eval reports.

Action: treat W1 as rubric/case planning only. Actual reproducible eval command/report is W2 work.

## 5. Recommended final Week 1 wording

Use this wording for pitch/review:

> AIO1 verified the baseline AI request path on the deployed TF4 environment using the current mock OpenAI-compatible LLM. The response matches fixture data, so this is valid Week 1 baseline evidence, not real LLM quality/cost/latency evidence. Week 1 deliverables are source review, evidence package, gap analysis, eval rubric planning, AIOps taxonomy/MVP selection, incident readiness, and backlog defense. Real LLM, reproducible eval reports, safety guardrails, AI cost/latency metrics, and continuous AIOps detector work remain Week 2/3 tasks.
