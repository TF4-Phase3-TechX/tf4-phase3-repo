# AIO1 execution plan for Mandate 06: AI trust and safety

- Effective date: 2026-07-14
- Deadline: 2026-07-18
- Scope owner: AIO1 AIE track
- Tech Lead: Đinh Danh Nam
- PM/evidence coordinator: Trần Đình Thông
- AIE implementers: Nguyễn Trần Huy Vũ, Trần Đình Thông, Tất Văn

## Outcome

Demonstrate through the real product-review user path that a real LLM is grounded in review evidence, resists prompt injection, does not leak PII/system instructions, degrades safely on provider failure, stays within latency/cost constraints, and can be re-evaluated from committed scripts and data.

## Priority order and dependency chain

```text
P0 provider/model + explicit controlled mode
  -> P0 non-bypassable guardrail path
  -> P0 bounded provider calls and safe fallback
  -> P0 offline real-model eval
  -> P0 controlled deployment and end-to-end mentor test
  -> P1 telemetry/cost/SLO evidence and final signed ADR
  -> P2 Copilot tool/action boundary if actions are included in the demo
```

Copilot feature expansion and non-mandate work yield to this chain until the deadline is met.

## Work allocation

| Owner | Work | Jira | Done when |
|---|---|---|---|
| Tất Văn | Fix controlled real-LLM mode and provider/model configuration | `TF4AIO-23` | Explicit mock/real switch, secret-backed config, local/integration proof and rollback steps |
| Tất Văn | Implement bounded fallback, timeout and circuit breaker | `TF4AIO-24`, `TF4AIO-29` | Timeout/429/5xx/invalid response tests return safe output and cannot exhaust workers |
| Tất Văn | Guard against malicious review instructions | `TF4AIO-26` | Attack stored in review/tool evidence cannot override system behavior on the real path |
| Tất Văn with review from Vũ | PII and system-prompt protection | `TF4AIO-27` | PII is removed before provider transmission and before display; leakage tests pass |
| Nguyễn Trần Huy Vũ | Extend mock eval harness into real-model trust/safety eval | `TF4AIO-64` | Versioned cases and numeric report cover groundedness, refusal, injection and PII |
| Trần Đình Thông | Verify telemetry and cost artifacts are merged and observable | `TF4AIO-30`, `TF4AIO-52` | Repo artifact plus deployed sample metric/log evidence exist; Jira/local-only claims are not used |
| Trần Đình Thông | Coordinate mentor validation and evidence index | `TF4AIO-65` | End-to-end script/result, rollback evidence and named ADR approvals are linked |
| Đinh Danh Nam | Architecture review, release decision and CDO coordination | all P0 tasks | No bypass path; release gates and residual risk explicitly accepted or rollout stopped |

## Daily execution plan

### 14 July: unblock and freeze design

- Confirm provider/model and budget ceiling.
- Agree whether the real provider is called directly by `product-reviews` or through a mandatory gateway.
- Replace API-key-presence routing with explicit mode control.
- Request CDO secret provisioning, private observability access and controlled deployment route.
- Mark this ADR `Proposed`; do not claim completion from mock-only tests.

### 15 July: implement safety and failure controls

- Apply guardrails on the non-bypassable real request path.
- Add pre-provider PII redaction and post-output filtering.
- Add timeout, bounded retry/circuit breaker and safe fallback.
- Add unit/contract tests that do not require the storefront or Docker UI.

### 16 July: run offline real-model evaluation

- Run versioned supported, unsupported, injection, PII and tool-scope cases.
- Produce raw results, aggregate metrics and failure examples.
- Fix P0 failures; record conservative thresholds and limitations.
- Verify runtime-hardening requirements for the deployment manifest.

### 17 July: controlled deploy and integration validation

- CDO deploys an isolated/canary or otherwise controlled configuration.
- Smoke 1-2 agreed products without enabling unvalidated behavior for all public traffic.
- Capture end-to-end latency, error/fallback, token/cost and storefront SLO evidence.
- Rehearse rollback to mock and verify recovery.

### 18 July: mentor validation and submission

- Mentor injects malicious review content and asks an unsupported question.
- Demonstrate PII protection and provider-failure fallback.
- Demonstrate tool/action refusal if the Copilot action surface is enabled.
- Finalize the evidence index, record limitations and obtain named ADR sign-off.

## Release gates

The team must not declare the mandate complete unless all are true:

- [ ] Real model is used in the controlled test.
- [ ] Guardrails cannot be bypassed by selecting the real provider path.
- [ ] Real-model numeric eval is reproducible from committed data and scripts.
- [ ] Malicious review injection is blocked.
- [ ] Unsupported questions do not produce invented facts.
- [ ] PII does not leave for the provider unredacted or reach the user.
- [ ] Timeout/rate-limit/5xx/invalid response paths return a safe fallback.
- [ ] Runtime telemetry and cost evidence are visible after deployment.
- [ ] Storefront SLO is not broken by guardrails/fallback.
- [ ] Rollback is rehearsed.
- [ ] Mentor validation and named ADR approval are recorded.

## CDO input required

1. Approve provider/model and supply the API key through a Secret; never through chat/Jira/repo.
2. Confirm outbound egress/DNS from the selected workload to the provider.
3. Provide a controlled deployment option: isolated namespace, canary, allow-listed test route or equivalent.
4. Provide authorized private observability access, preferably namespace-scoped port-forward or the TF private tunnel.
5. Confirm deployment and rollback owner, test window, product IDs and SLO dashboard.
6. Confirm the hardening policy required for the new/updated workload.

## AIO output to CDO

1. Reviewed PR with pinned image/model configuration and no secrets.
2. Resource requests/limits, non-root security context, probes and rollback values.
3. Exact smoke-test and rollback commands.
4. Eval gate result and known limitations.
5. Expected metrics/logs/traces and safe log-redaction policy.
6. Requested deployment window and success/abort criteria.

## Risks and stop conditions

- No approved provider/key or controlled route: do not expose real LLM globally.
- Guardrail exists only in mock `llm/app.py`: stop; real mode can bypass it.
- Eval has only pass/fail mock unit tests and no numeric real-model report: not complete.
- PII reaches the external provider before redaction: stop release.
- Raw prompts, reviews, system instructions or keys appear in logs: stop release and sanitize evidence.
- SLO or cost ceiling is exceeded: revert to mock and escalate with evidence.
