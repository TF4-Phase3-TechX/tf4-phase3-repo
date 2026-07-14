# Mandate 06 evidence index: AI trust and safety guardrails

- Status: Draft / not runtime-verified
- Team: AIO1 with CDO deployment and CDO-07 audit review
- Deadline: 2026-07-18
- ADR: `docs/audit/adr/014-ai-trust-safety-guardrails.md`

## What this document is

This is the evidence index and execution checklist for Mandate 06. It does not claim that the mandate is complete. In particular, deterministic behavior from the mock LLM is pipeline-readiness evidence, not real-model quality evidence.

## Current verified baseline

- The repository contains a deterministic OpenAI-compatible mock LLM.
- `TF4AIO-22` records completion of the mock/current eval-pipeline exercise.
- The current storefront baseline can display deterministic mock review answers.

These facts do not satisfy the mandate's real-model, groundedness, attack-resistance or runtime-fallback requirements.

## Evidence matrix

| Requirement | Required artifact | Jira | Current state |
|---|---|---|---|
| Real model and safe cutover | Provider/model decision, explicit mode switch, secret reference, 1-2 product smoke result | `TF4AIO-23` | In progress; runtime evidence pending |
| Provider failure fallback | Tests for timeout, 429, 5xx and invalid response; safe response; rollback rehearsal | `TF4AIO-24`, `TF4AIO-29` | In progress/planned |
| Grounded answers | Versioned review/Q&A dataset, numeric faithfulness and unsupported-refusal report | `TF4AIO-64` | Real-model report missing |
| Injection resistance | Malicious text stored in review/tool evidence and end-to-end refusal/grounding result | `TF4AIO-26` | In progress; mock-only test is insufficient |
| PII/system prompt safety | Pre-provider redaction and post-output scan tests with leakage-rate report | `TF4AIO-27` | To do |
| Tool/action boundary | Unknown/disallowed tool rejection and approved-call audit | `TF4AIO-34` | To do |
| Cost and telemetry | Token, cost, latency, errors and fallback metrics visible in the deployed stack | `TF4AIO-30`, `TF4AIO-52` | Jira says Done; merged/runtime artifact must be verified |
| Mentor demonstration | Re-runnable end-to-end script plus screenshots/logs and signed ADR | `TF4AIO-65` | Missing |

## Reproducible evaluation contract

The committed eval package must contain:

```text
eval/
  cases.jsonl                 # versioned inputs, review evidence and expected policy
  run_eval.py                 # deterministic runner/config capture
  README.md                   # exact command and prerequisites
  reports/<timestamp>.json    # raw case results
  reports/<timestamp>.md      # aggregate metrics and failures
```

Minimum case families:

1. Supported facts explicitly present in reviews.
2. Unsupported facts, including battery/CPU claims absent from reviews.
3. Prompt injection embedded in review content.
4. Direct system-prompt exfiltration attempts.
5. Email and phone PII in reviews and generated output.
6. Cross-product/tool argument manipulation.
7. Timeout, rate-limit, provider unavailable and malformed response.

The report must identify provider/model version, prompt/config version, dataset revision, run timestamp, token usage and known limitations.

## Mentor validation path

Mentor validation must exercise the actual application boundary:

```text
storefront/product-review API
  -> product-reviews
  -> review data/tool call
  -> guardrails
  -> real provider
  -> output gate
  -> displayed response or safe fallback
```

Required live cases:

- a review containing instruction override text;
- a question not answerable from review evidence;
- a review containing test PII;
- provider failure/slow response showing graceful fallback;
- an unauthorized tool/action request if Copilot actions are enabled.

## Evidence capture checklist

- [ ] PR/commit containing implementation and tests.
- [ ] Provider/model decision without secrets.
- [ ] Numeric eval report from the real model.
- [ ] Injection and PII raw case IDs with sanitized outputs.
- [ ] Timeout/rate-limit/invalid-response fallback test output.
- [ ] Grafana/trace/log evidence for latency, errors, fallback, tokens and cost.
- [ ] Storefront SLO observation during controlled smoke.
- [ ] Explicit rollback-to-mock rehearsal and verification.
- [ ] Mentor-run validation result.
- [ ] Named ADR approvals.

## Verification commands

Exact commands will be filled only after the implementation and eval runner are committed. Commands must reference repository paths and must not require a local-only file or a secret embedded in the command line.

## Known blockers and CDO dependencies

- Secure provider API-key provisioning through a Kubernetes Secret or approved secret store.
- Controlled deployment path that does not expose a new model directly to all public traffic before gates pass.
- Private access to observability for authorized AIO members and the mentor.
- Deployment owner for the final `techx-tf4` rollout and rollback.
- Confirmation of the allowed test window, product IDs and SLO dashboard.
