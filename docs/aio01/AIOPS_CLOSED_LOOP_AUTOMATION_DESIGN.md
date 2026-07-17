# AIOps Closed-Loop Automation — Target Architecture and Delivery Plan

- **Status:** Target-state design; runtime implementation is phased and must not be inferred from this document
- **Scope owner:** AIO01, with CDO approval for cluster/platform actions and AIE ownership for AI-path actions
- **Mandate boundary:** Mandate 07a records the design, initial detector implementation, metric analysis, and signed ADR. Runtime alerting, drills, and automation evidence are later gates.
- **Related work:** TF4AIO-38, TF4AIO-42, TF4AIO-43, TF4AIO-44, TF4AIO-71, TF4AIO-72, TF4AIO-76
- **Runbook allow-list:** [aiops_runbook_specs.md](./aiops_runbook_specs.md)
- **Detection rules:** [aiops_detection_rules_specs.md](./aiops_detection_rules_specs.md)

## 1. Objective and delivery boundary

The final AIO01 scope is a closed-loop AIOps system that can detect a service
incident, correlate evidence, recommend or execute a bounded response, verify
the result, and escalate to an on-call engineer when confidence or safety gates
are insufficient.

The target architecture is intentionally broader than the Mandate 07a runtime
deliverable. The team must preserve this distinction in Jira, pull requests,
and mentor-facing evidence:

| Phase | Required capability | Evidence type |
| --- | --- | --- |
| Mandate 07a | Detection design, at least three metric analyses, initial detector/baseline implementation, target closed-loop design, signed ADR | Document, PR/commit, ADR approval |
| Mandate 07b | Deployed rules, visible alert, controlled incident injection, precision/recall/lead-time, impact-aware routing | Runtime screenshots/logs, labeled drill data, GitOps revisions |
| Closed-loop delivery | Policy engine, approval workflow, allow-listed executor, post-action verification, rollback, escalation, audit trail | Shadow-mode results followed by separately approved automation drills |

No statement in this document claims that the policy engine or mutation
executor is currently deployed.

## 2. Target end-to-end architecture

```text
Prometheus       OpenSearch        Jaeger        Deployment/GitOps metadata
    |                |                |                       |
    +----------------+----------------+-----------------------+
                             |
                    Detection adapters
                             |
             Normalize + validate incident event
                             |
             Fingerprint + deduplicate + group
                             |
              Correlation / RCA hypothesis engine
                             |
                    Incident state manager
                             |
                    Decision / policy engine
                  /          |             \
             observe      recommend     approval/auto
                |             |             |
                |        runbook hint   allow-listed executor
                |             |             |
                +-------------+-------------+
                             |
                  Post-action verification
                     /                  \
                recovered             failed/unknown
                    |                       |
             resolve + audit        rollback + escalate
                             |
                Alertmanager / Slack / on-call / Jira
```

### Component responsibilities

| Component | Responsibility | Must not do |
| --- | --- | --- |
| Detection adapters | Evaluate versioned PromQL/log/trace rules and preserve raw evidence references | Treat missing telemetry as healthy zero |
| Event normalizer | Produce one schema, severity vocabulary, scope, timestamps, and stable fingerprint inputs | Accept unbounded labels or raw prompt/response content |
| Incident state manager | Deduplicate, group, apply sustained windows, and track lifecycle | Create a new incident for every polling interval |
| RCA hypothesis engine | Rank suspected causes and state confidence/source availability | Claim a certain root cause from correlation alone |
| Policy engine | Select observe/recommend/approval/auto mode from explicit gates | Execute free-form commands or LLM-generated actions |
| Action executor | Execute only versioned allow-listed actions with least privilege and idempotency | Restart shared stores, mutate flagd, or bypass GitOps policy |
| Verifier | Compare pre/post metrics and declare recovered, failed, or inconclusive | Mark success without a bounded verification window |
| Notification router | Route, group, inhibit, and escalate using incident state | Page repeatedly for the same fingerprint without state change |
| Audit writer | Persist decision inputs, approvals, revisions, actions, and results | Store credentials, prompts, reviews, model responses, or PII |

## 3. Incident lifecycle

```text
detected
  -> correlating
  -> open
  -> acknowledged
  -> action_pending
  -> executing
  -> verifying
      -> resolved
      -> rollback_pending -> rolled_back -> escalated
      -> inconclusive --------------------> escalated
```

Rules:

1. A stable `incident_id` is derived from a versioned fingerprint such as
   `environment + service + incident_type + rule_id`.
2. Repeated detector results update the same incident and its evidence window.
3. A severity increase creates a state transition and notification update, not
   an unrelated incident.
4. An incident is resolved only after the recovery condition holds for the
   configured verification window.
5. Manual acknowledgement, approval, rejection, rollback, and closure record
   the human identity and timestamp.

## 4. Unified incident and action contract

All detector, summary, runbook, policy, and notification components must use a
single versioned contract. The JSON Schema implementation is a planned artifact;
until it exists, this YAML is the normative design example.

```yaml
schema_version: "1.0"
incident_id: inc-prod-product-reviews-llm-timeout-20260717
fingerprint: production/product-reviews/llm_timeout_error/v1
state: open
detected_at: "2026-07-17T03:00:00Z"
updated_at: "2026-07-17T03:03:00Z"
service: product-reviews
environment: production
namespace: techx-tf4
incident_type: llm_timeout_error
severity: critical                  # info | warning | critical | unknown
confidence: high                    # high | partial | unknown
rule:
  id: ai_llm_provider_failure
  version: "1"
  observed_value: "0.62 errors/s"
  threshold: "> 0.5 errors/s for 3m"
sources:
  prometheus: available
  opensearch: available
  jaeger: unavailable
evidence:
  - kind: prometheus
    query: sum(rate(app_llm_errors_total[3m]))
  - kind: opensearch
    index: otel-logs-*
    query: 'resource.service.name:"product-reviews" AND resource.k8s.namespace.name:"techx-tf4"'
rca_hypotheses:
  - cause_id: bedrock_provider_or_quota_failure
    score: 0.78
    evidence_refs: [prometheus, opensearch]
  - cause_id: in_cluster_network_failure
    score: 0.22
    evidence_refs: [opensearch]
runbook_hint:
  incident_type: llm_timeout_error
  evidence_checks:
    - verify_ai_calls_errors_and_latency
    - classify_inject_vs_organic_failure_readonly
  suggested_actions:
    - confirm_app_safe_fallback_ux
    - freeze_ai_rollout
    - escalate_aie_then_cdo_if_platform
  do_not:
    - patch_or_rewrite_flagd
    - restart_llm_or_product_reviews_for_429
  escalation:
    primary: aie_owner_aio01
    secondary: cdo_platform
automation:
  mode: recommend                 # observe | recommend | approval_required | auto
  eligible: false
  candidate_action_id: freeze_ai_rollout
  blocked_by:
    - jaeger_unavailable
    - human_approval_required
  policy_version: "1"
```

Contract rules:

- `severity` is limited to `info`, `warning`, `critical`, or `unknown`.
- `confidence` is mandatory and independent from severity.
- `unknown` telemetry never becomes zero and blocks mutation unless a separate
  critical base rule and policy explicitly allow the action.
- `suggested_actions`, `do_not`, and `candidate_action_id` contain curated IDs,
  never free-form shell commands.
- Evidence contains queries, bounded results, and links; it must not contain
  prompt/model content, secrets, credentials, or PII.

## 5. Automation modes and promotion model

| Mode | Behaviour | Initial use |
| --- | --- | --- |
| `observe` | Detect, correlate, and record; no human recommendation or mutation | Detector bring-up and baseline calibration |
| `recommend` | Emit evidence and curated runbook hints; human performs all actions | Mandate 07a/07b default |
| `approval_required` | Prepare one bounded action and wait for a named approver | First controlled automation drills |
| `auto` | Execute an allow-listed action only when every policy gate passes | Final state after shadow-mode and approval evidence |

Promotion from one mode to the next is per `service + incident_type + action_id`.
Approval for one action does not enable every action or service.

## 6. Automation eligibility policy

An action is automation-eligible only when all required gates pass:

1. The event matches a versioned rule and incident schema.
2. Severity and sustained duration meet the action policy.
3. Confidence is `high`, or a separately approved critical base rule permits
   action without correlation.
4. The minimum required independent sources are available and agree.
5. The minimum traffic/sample-size guard passes.
6. The incident is not an unclassified controlled injection or drill.
7. No deployment, rollback, or automation action is already active for the
   service.
8. The action is in the service-specific allow-list.
9. The estimated blast radius is within the configured bound.
10. A pre-state snapshot, success query, timeout, and rollback action exist.
11. Cooldown, attempt, concurrency, and change-window limits pass.
12. The configured approval requirement is satisfied.

Any missing gate produces `eligible: false` plus explicit `blocked_by` reasons
and routes the incident to a human.

## 7. Action tiers and ownership

| Tier | Examples | Default policy | Owner |
| --- | --- | --- | --- |
| T0 — evidence/coordination | Create or update an incident, attach queries, group duplicate alerts, send notification | Automatic | AIO01 |
| T1 — application containment | Verify safe fallback, freeze a rollout through the approved delivery system, reduce non-critical AI traffic if a pre-existing control exists | Recommend first; approval-required after drills | AIO/AIE, with CDO where delivery state changes |
| T2 — reversible workload change | Small bounded replica change, GitOps revert of a correlated bad application deployment | Human approval required; candidate for later automation only after service-specific drills | CDO platform |
| T3 — shared platform/security | Database failover/restart, node/network/IAM changes, shared storage changes | Manual CDO incident process only | CDO/platform/security |
| Forbidden | Rewrite flagd injection state, execute LLM-generated commands, delete evidence, expose secrets/content, restart a shared database as first response | Never | N/A |

The first closed-loop milestone may automate only T0. T1/T2 require separate
policy approval and runtime evidence; T3 and forbidden actions do not enter the
AIOps executor allow-list.

## 8. Executor safety model

The executor design must provide:

- one versioned handler per action ID;
- least-privilege identity and namespace/resource scoping;
- idempotency key `incident_id + action_id + policy_version`;
- one active mutation per service;
- maximum attempts and cooldown;
- dry-run and approval-token validation;
- pre-state revision and resource snapshot;
- bounded timeout and cancellation;
- no arbitrary shell, `eval`, templated kubectl, or LLM-generated commands;
- immutable audit event for request, approval, execution, verification, and
  rollback;
- a global kill switch that disables mutation while leaving detection active.

Production delivery changes follow the approved GitOps process. Direct cluster
mutation is not a normal action path; any documented break-glass procedure is
owned by CDO and remains outside the AIOps executor.

## 9. Verification and rollback contract

Every action definition contains:

```yaml
action_id: gitops_revert_bad_product_reviews_revision
owner: cdo_platform
preconditions:
  - bad_deploy_time_correlation_confirmed
  - previous_revision_known_good
  - approval_present
pre_state:
  - deployment_revision
  - image_digest
  - error_rate
  - p95_latency
verify:
  window: 5m
  success:
    - error_rate_below_warning_threshold
    - p95_below_warning_threshold
    - workload_ready
  failure:
    - verification_timeout
    - error_rate_worse
rollback:
  strategy: restore_pre_action_gitops_revision
  owner: cdo_platform
on_inconclusive: escalate
```

Verification must use the same scope and rule family as detection. A source
failure during verification produces `inconclusive`, not `recovered`.

## 10. Alert routing and escalation

Target routing policy:

| Condition | Initial route | Escalation |
| --- | --- | --- |
| Warning, high confidence | Team Slack/Alertmanager receiver; update incident | Primary on-call if sustained or severity increases |
| Critical, high confidence | Page primary on-call immediately; attach evidence and candidate action | Secondary/Tech Lead after acknowledgement timeout |
| Unknown/partial because telemetry is unavailable | Observability/platform route plus affected-service owner | Incident commander if multiple sources fail |
| Approval-required action pending | Named approver and primary on-call | Secondary approver after timeout; never auto-approve |
| Action or rollback failed | Primary + CDO/platform page | Incident commander; mutation kill switch if systemic |

The notification design must include grouping, inhibition, stable fingerprint,
acknowledgement state, escalation timeout, silence ownership, and resolved
notifications. Receiver URLs and credentials are external secrets, not repo
content.

## 11. Incident-specific target decisions

| Incident | Detection floor | RCA evidence | Initial response | Future bounded automation candidate |
| --- | --- | --- | --- | --- |
| Latency spike | Per-service p95 plus sustained window and traffic guard | Resource saturation, trace outliers, dependency latency, recent deploy | Investigate and route to owning dependency/service | T0 incident update; later approval-gated GitOps revert or bounded scale when evidence gates pass |
| Error-rate spike | Per-service error ratio plus minimum request count | Error class, dependency health, recent deploy, trace/log agreement | Preserve evidence, classify app vs platform, escalate | T0 incident update; later approval-gated application GitOps revert |
| LLM timeout/provider failure | `app_llm_errors_total`, `app_llm_calls_total`, latency and sanitized logs | Provider/Guardrail/quota/IAM/network classification and safe-fallback state | Verify safe fallback, freeze rollout, route AIE then CDO if platform | T0 incident update; T1 existing safe-fallback control only if separately designed and approved |

## 12. Audit, privacy, and evidence

Record for every decision:

- incident/fingerprint/schema/rule/policy/action versions;
- UTC timestamps and evaluation window;
- service, environment, and namespace;
- source availability, bounded observed values, queries, and evidence URLs;
- RCA hypotheses and confidence;
- selected mode, eligibility gates, and blocked reasons;
- approver identity and approval artifact;
- pre/post revision, action result, verification result, and rollback result;
- notification route and acknowledgement timestamps.

Never record credentials, webhook values, raw prompts, stored reviews, model
responses, system canaries, or PII.

## 13. Success measures

| Measure | Definition |
| --- | --- |
| Detection precision/recall | Correct alerts / all alerts; caught labeled incidents / all injected incidents |
| Lead time | First qualifying alert timestamp minus labeled incident start |
| MTTA | First on-call acknowledgement minus incident open time |
| Recommendation acceptance | Approved recommendations / recommendations presented |
| Automation success rate | Actions that pass post-verification / actions executed |
| Rollback rate | Actions rolled back / actions executed |
| Unsafe-action count | Must remain zero |
| Duplicate notification rate | Notifications beyond configured state transitions for one fingerprint |

Automation promotion requires acceptable detection precision first. A detector
that is not trusted must remain in observe/recommend mode.

## 14. Phased implementation backlog

| Phase | Work package | Acceptance | Dependency |
| --- | --- | --- | --- |
| Design / 07a | Target architecture, unified contract, policy gates, action tiers, alert/escalation design, signed ADR | Human-reviewed docs and traceability links; no runtime claim | Detection metric analysis |
| Detection / 07b | Deploy rule versions, incident normalization, sustained windows, visible routing, labeled drills | Runtime alert evidence and precision/recall/lead-time | Telemetry access and GitOps window |
| Shadow policy | Implement incident state/dedup and policy evaluation with `observe/recommend`; persist decisions | Replayed and live events produce deterministic eligible/blocked results without mutation | Unified JSON Schema |
| Approval workflow | Named approval/rejection with expiry and audit; T0/T1 action catalog | No execution without valid approval where required | On-call identity and routing |
| Executor | Implement T0 first, then separately approved T1/T2 handlers | Idempotency, least privilege, cooldown, kill switch, tests | CDO-owned RBAC/GitOps interfaces |
| Verification/rollback | Versioned pre/post queries, timeout, rollback state machine | Controlled drills prove recovery, failure, inconclusive, and rollback paths | Executor and telemetry reliability |
| Automation promotion | Per-action shadow report and safety review | Explicit approval for each service/incident/action tuple | Precision, rollback, and unsafe-action gates |

Each work package requires a Jira issue with one accountable owner, dependency,
acceptance criteria, PR/commit, reproducible validation, and evidence link.

## 15. Open design decisions

The ADR/review process must resolve before mutation is enabled:

1. Incident state store and retention.
2. Exact severity/confidence thresholds and independent-source quorum per rule.
3. Alertmanager/Slack/paging provider and acknowledgement timeout.
4. Approval identity, expiry, and break-glass authority.
5. GitOps API/contract exposed to the executor.
6. Initial T0/T1 action catalog and service owners.
7. Automation kill-switch ownership and test cadence.
8. Evidence retention and access boundaries.

Until these decisions are accepted, the system remains in `observe` or
`recommend` mode.

## 16. Mandate 07a traceability

| Mandate 07a requirement/design concern | Canonical artifact | Status boundary |
| --- | --- | --- |
| At least three metric analyses and initial thresholds | [aiops_detection_rules_specs.md](./aiops_detection_rules_specs.md) | Design/initial implementation; live calibration remains 07b |
| Incident response and curated action allow-list | [aiops_runbook_specs.md](./aiops_runbook_specs.md) | Target `runbook_hint` contract; generator conformance remains implementation work |
| Final closed-loop automation scope and plan | This document | Target-state design; no deployed policy/executor claim |
| Detection/output implementation evidence | [PR #137](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/137) and [PR #208](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/208) | Initial code; merge/deployment status must be checked at submission time |
| Signed architectural decision | [PR #241 / ADR-M07](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/241) | Must receive required human approval before 07a closure |
| Jira submission/evidence index | [TF4AIO-71](https://aio1-xbrain.atlassian.net/browse/TF4AIO-71) | Must link final-head commits/docs and avoid 07b runtime claims |
| Runtime alerting, drill, precision/recall/lead-time | [TF4AIO-72](https://aio1-xbrain.atlassian.net/browse/TF4AIO-72) | Explicitly deferred to Mandate 07b |
