# Mandate and Capacity Review

Jira: `TF4AIO-20`

## 1. Sources reviewed

- `docs/requirements/RULES.md`
- `docs/requirements/onboarding/SLO.md`
- `docs/requirements/onboarding/BUDGET.md`
- `docs/requirements/onboarding/INCIDENT_HISTORY.md`
- TF4 Jira tổng AI gaps copied into AIO tracking: AI-01 telemetry/privacy and AI-02 fallback/eval/cost.
- AIO planning/backlog defense doc: `docs/planning/AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md`

## 2. Week 1 mandate conclusion

Current conclusion:

- No extra Week 1 coding mandate is required beyond discovery, evidence, backlog, and pitch readiness.
- Week 1 should not claim real LLM readiness.
- Real LLM is W2/W3 work behind eval, fallback, timeout, telemetry, and cost gates.
- AIOps is mandatory project scope, but Week 1 completion is data-source discovery, taxonomy, MVP selection, and planning.
- Continuous detector implementation and validation are W2/W3 work.

## 3. Required backlog coverage

Backlog/planning should continue to cover:

- prompt injection guardrail;
- PII/system prompt output filter;
- DB connection pooling;
- LLM timeout/circuit breaker;
- safe LLM fallback;
- LLM API cost monitoring;
- AI latency/error/fallback metrics;
- Copilot architecture/tool wiring;
- multi-turn memory;
- tool allow-list / excessive-agency guardrail;
- agent loop limit / tool audit log;
- Prometheus/OpenSearch programmatic query verification;
- continuous AIOps detector workload;
- incident summary and runbook suggestion.

## 4. Capacity reserve rule

Reserve 20% of W2/W3 capacity, approximately 1 day/person/week, for:

- BTC directives;
- incident response;
- mentor/council feedback;
- evidence cleanup;
- CDO dependency handling.

Do not allocate 100% of team time to planned backlog tasks.

## 5. Triage rule for new mandates

1. Check whether the mandate affects SLO, budget, security/safety, or disqualification risk.
2. If yes, create/update Jira task and use the 20% buffer before pulling lower-priority scope.
3. Record decision and evidence link in Jira.
4. Communicate dependency to CDO if infrastructure/deploy access is required.

