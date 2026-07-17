# AIOps MVP Incident Runbook Specifications

- **Epic:** [TF4AIO-7](https://aio1-xbrain.atlassian.net/browse/TF4AIO-7) — EPIC-AIOPS-03: Incident Summary & Runbook Suggestion
- **Jira Task:** [TF4AIO-44](https://aio1-xbrain.atlassian.net/browse/TF4AIO-44) — [W2/W3][AIOPS] Map incident types to runbook actions
- **Status:** Draft — 07a runbook contract plus phased closed-loop target design
- **Planning:** [AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md](./AIO1_PROJECT_PLANNING_AND_TASK_ASSIGNMENT.md)
- **Detection rules (1:1 source of truth for alerts/queries):** [aiops_detection_rules_specs.md](./aiops_detection_rules_specs.md)
- **Target architecture:** [AIOPS_CLOSED_LOOP_AUTOMATION_DESIGN.md](./AIOPS_CLOSED_LOOP_AUTOMATION_DESIGN.md)
- **Current remediation mode:** `recommend` / human-in-the-loop; mutation is not implemented in Mandate 07a

---

## 0. MVP scope and non-goals

### MVP incident types (aligned with detection rules TF4AIO-37)

| ID | Incident type | Primary signals |
| --- | --- | --- |
| MVP-1 | Service latency spike | p95 span duration on critical path |
| MVP-2 | Error-rate spike | gRPC/HTTP error ratio + min traffic |
| MVP-3 | LLM timeout / error | AI span errors, AI throughput drop, LLM logs |

> Scope note: program taxonomy may list more incident classes; **AIOps MVP mapping covers these three** so detector → summary → runbook hint stay consistent.

### Current delivery boundary and final scope

Mandate 07a documents the target closed-loop system, but its runtime boundary is
detection plus curated human response. In 07a the system **does not**:

- claim that an automation policy engine or executor is deployed;
- auto-restart pods, StatefulSets, or nodes;
- auto-scale, roll back, or mutate traffic;
- Patch, rewrite, disable, or re-point **flagd** / incident-injection flags
- Claim root-cause certainty (hints may state *suspected* cause only)
- Replace CDO-owned platform runbooks

The final team scope does include gated closed-loop automation. Its modes,
eligibility gates, action tiers, executor safety, verification, rollback, and
on-call escalation are defined in the
[target architecture](./AIOPS_CLOSED_LOOP_AUTOMATION_DESIGN.md). Automation is
promoted per action only after shadow-mode, human approval, and runtime safety
evidence; it is not implied by this runbook.

### Output contract (for TF4AIO-42/43 summary field)

Each mapping below is intended to populate a structured **runbook hint**, not a free-form remediation essay.

**Contract rule:** the incident summary generator / detector **must emit exactly these fields and formats**. Free-form prose may appear only in human-facing renderers; the structured payload is the machine contract. Mismatched field names, casing, or invented action IDs break downstream consumers.

```yaml
runbook_hint:
  incident_type: latency_spike | error_rate_spike | llm_timeout_error
  confidence: high | partial | unknown
  symptoms_summary: short human string
  evidence_checks: []
  suggested_actions: []
  do_not: []
  escalation:
    primary: aio01_oncall
    secondary: cdo_platform
  known_limitations: []
  automation:
    mode: observe | recommend | approval_required | auto
    eligible: false
    candidate_action_id: null
    blocked_by: []
```

#### `runbook_hint` field contract (YAML / JSON)

Nested under the incident summary as `runbook_hint`:

| Field | Type | Format / rules |
| --- | --- | --- |
| `incident_type` | string | One of: `latency_spike`, `error_rate_spike`, `llm_timeout_error` |
| `confidence` | string | Required: `high`, `partial`, or `unknown`; independent from severity |
| `evidence_checks` | string[] | Required curated read-only checks or evidence references |
| `suggested_actions` | string[] | **snake_case action IDs only** (e.g. `verify_p95_and_trace_outliers`). Do **not** emit free-text sentences, Title Case, or kebab-case. Order = safety priority (safest first). IDs must come from the allow-list in each MVP §F example (or the matching §C table mapping). |
| `do_not` | string[] | **snake_case anti-pattern IDs only** (e.g. `patch_or_rewrite_flagd`). Same casing rules as `suggested_actions`. |
| `escalation.primary` | string | snake_case owner id from §E |
| `escalation.secondary` | string | snake_case owner id from §E |
| `automation.mode` | string | Required current policy mode; 07a defaults to `recommend` |
| `automation.eligible` | boolean | Required; false when any confidence, evidence, approval, or safety gate is missing |
| `automation.blocked_by` | string[] | Explicit policy-gate failures; never silently fall through to execution |

**Generator / detector conformance:**

1. Copy action / do-not IDs **verbatim** from the curated allow-list for the classified `incident_type` — do not paraphrase into natural language inside the structured fields.
2. Emit only the evidence-gated subset that is safe for the current incident state; never invent IDs such as `ScaleOutNow` or `verify-p95`.
3. Human-readable labels (for UI) may be derived by a separate presentation layer; they are **not** substitutes for the snake_case IDs in the payload.
4. If evidence is incomplete, keep the same schema, set confidence/limitations,
   set `automation.eligible=false`, and stop at investigate/escalate.

Canonical examples: §2.F, §3.F, §4.F.

---

## 1. Operating principles

1. **Phased control:** 07a/07b run in `observe` or `recommend`; later phases may use `approval_required` or `auto` only for separately approved allow-listed actions.
2. **No free-form remediation:** The engine never runs arbitrary `kubectl`, Helm, Terraform, ConfigMap patches, or LLM-generated commands.
3. **Evidence before action:** Every suggested action names the evidence that must be true first. If evidence is missing, the hint stops at investigate/escalate.
4. **Blast-radius order:** Prefer read-only diagnosis → application containment/fallback → freeze rollout → CDO-owned infra change (last resort).
5. **flagd is protected:** Incident flags (`llmRateLimitError`, `llmInaccurateResponse`, …) are BTC/org inject mechanisms. Operators **read** flag state for diagnosis; they **must not** patch `flagd` ConfigMaps to “clear” an incident. Remediation for inject scenarios is **graceful degradation in the app**, not disabling the inject path.
6. **Curated, not free-form:** Recommendations stay in the allow-list below. Detector/LLM summarizer must not invent new mutate commands.

---

## 2. Runbook MVP-1: Latency Spike

### A. Symptoms

Alert `AIOpsServiceLatencySpikeCritical` (p95 > 2000ms) or `AIOpsServiceLatencySpikeWarning` (p95 > 1000ms) on critical-path services: `product-reviews`, `checkout`, or `cart` (see detection rules for `for:` windows).

### B. Evidence to check (read-only)

1. **Confirm p95 on Prometheus** (same family as detection rule):

   ```promql
   histogram_quantile(
     0.95,
     sum by (le, service_name) (
       rate(traces_span_metrics_duration_milliseconds_bucket{
         service_name=~"product-reviews|checkout|cart"
       }[3m])
     )
   )
   ```

2. **Logs — saturation / timeout keywords (OpenSearch `otel-logs-*`):**  
   Filter `resource.service.name` = affected service; search body for `timeout`, `deadline exceeded`, `connection pool`, `slow query`.

3. **Jaeger / trace outliers (required):**  
   Traces for the affected service with duration > 2000ms (Jaeger UI may show µs; detection notes use > 2_000_000 µs). Inspect sub-spans: gRPC downstream, DB query, or AI path (`get_ai_assistant_response` / LLM).

4. **Load / resource gate (required before any scale suggestion):**

   ```bash
   # Examples only — human runs after choosing correct context/namespace
   kubectl top pods -n <namespace> -l app.kubernetes.io/name=<service-name>
   kubectl get deploy <service-name> -n <namespace> -o wide
   kubectl describe deploy <service-name> -n <namespace> | tail -n 40
   ```

   Optional metrics if present: container CPU/memory vs limits; HPA status.

5. **Recent change gate (required before rollback suggestion):**  
   Deploy/ReplicaSet age, rollout history, ArgoCD/GitOps sync time, or release notes in the incident window.

6. **Dependency / DB branch (if traces point off-app):**  
   Downstream service latency/errors; DB connection errors in logs; do **not** treat app scale-out as default if the bottleneck is shared DB or an external dependency.

### C. Suggested human-approved actions (ordered by safety)

> AIOps emits these as **options**. None are executed by the detector.

| Priority | When evidence shows… | Suggested action | Who executes |
| --- | --- | --- | --- |
| 1 | Spike confirmed; root span unclear | Continue triage (traces + logs); open incident note with evidence links | AIO on-call |
| 2 | Bottleneck = dependency/DB/LLM, not local CPU | **Do not** scale the app blindly; escalate to owner of that dependency (CDO for data plane / AIE for AI path) | AIO → CDO or AIE |
| 3 | Sustained CPU/memory near limit (> ~80% of limit) **and** HPA not covering **and** dependency not saturated | Propose a small bounded replica change through the approved GitOps workflow; re-check p95 before promotion | CDO platform |
| 4 | Clear correlation with a bad deploy in the incident window | Propose a GitOps revert to the exact previous known-good application revision | CDO platform (+ AIO verify p95) |

**Change-control path:** capture the pre-state revision and metrics, open a
bounded GitOps change/revert, obtain the named CDO approval and deployment
window, wait for Argo `Synced/Healthy`, then run the verification contract.
Direct `kubectl scale` or `kubectl rollout undo` is not a normal AIOps action;
any break-glass use remains a separate CDO-owned incident procedure.

### D. Do not

- Restart app pods or DB as first response to latency (reconnect / thundering herd risk when DB is saturated).
- Scale out when traces show DB pool exhaustion or downstream timeout as the dominant span.
- Claim RCA beyond “suspected” without trace+metric agreement.

### E. Escalation owner

| Suspected class | Primary | Secondary |
| --- | --- | --- |
| App logic / recent AIO service change | AIO01 application owner / Tech Lead | AIO on-call |
| Cluster capacity, node pressure, data-store platform | CDO platform / DevOps on-call | AIO on-call (evidence package) |
| AI path latency (`product-reviews` → LLM / Bedrock) | AIE owner (AIO01) | CDO if infra/network to provider |

### F. Canonical `runbook_hint` payload (allow-list)

> Generator must emit these **snake_case IDs** (or an evidence-gated subset in the same order). Do not rewrite as free text.

```yaml
runbook_hint:
  incident_type: latency_spike
  confidence: high
  evidence_checks:
    - verify_p95_and_trace_outliers
    - check_cpu_memory_and_recent_deploy
  do_not:
    - restart_pods_or_db_as_first_response
    - scale_out_if_dependency_or_db_is_bottleneck
  suggested_actions:
    - continue_readonly_triage
    - if_local_resource_saturation_then_propose_cdo_gitops_scale
    - if_bad_deploy_then_propose_cdo_gitops_revert
  escalation:
    primary: aio01_oncall
    secondary: cdo_platform
  known_limitations: []
  automation:
    mode: recommend
    eligible: false
    candidate_action_id: null
    blocked_by:
      - human_approval_required
```

---

## 3. Runbook MVP-2: Error Rate Spike

### A. Symptoms

Alert `AIOpsServiceErrorRateSpikeCritical` (error rate > 5%) or `AIOpsServiceErrorRateSpikeWarning` (error rate > 1%, or frontend ingress 5xx path per detection rule) on `product-reviews`, `checkout`, or `cart`.

### B. Evidence to check (read-only)

1. **Confirm error ratio + traffic floor (mirror detection guard):**

   ```promql
   (
     sum by (service_name) (
       rate(traces_span_metrics_calls_total{
         service_name=~"product-reviews|checkout|cart",
         status_code="STATUS_CODE_ERROR"
       }[2m])
     )
     /
     (sum by (service_name) (
       rate(traces_span_metrics_calls_total{
         service_name=~"product-reviews|checkout|cart"
       }[2m])
     ) > 0)
   ) * 100
   and on(service_name)
   sum by (service_name) (
     increase(traces_span_metrics_calls_total{
       service_name=~"product-reviews|checkout|cart"
     }[2m])
   ) > 10
   ```

2. **OpenSearch — error classification** (reuse optimized DSL from detection rules):

   ```json
   {
     "query": {
       "bool": {
         "must": [
           {
             "terms": {
               "resource.service.name": [
                 "product-reviews",
                 "checkout",
                 "cart"
               ]
             }
           },
           {
             "terms": {
               "severity.text": ["ERROR", "FATAL"]
             }
           }
         ],
         "should": [
           { "match_phrase": { "body": "connection refused" } },
           { "match_phrase": { "body": "database error" } },
           { "match_phrase": { "body": "internal server error" } }
         ],
         "minimum_should_match": 1
       }
     }
   }
   ```

   Goal: separate **infra/connectivity** (`connection refused`, DB errors) from **app/code** symptoms (parse/null/business logic), without claiming a definitive RCA.

3. **Workload / dependency health (before any restart idea):**

   ```bash
   kubectl get pods -n <namespace> -l app.kubernetes.io/name=<service-name>
   kubectl get endpoints -n <namespace>
   kubectl get events -n <namespace> --sort-by='.lastTimestamp' | tail -n 30
   ```

4. **Recent deploy / config change** in the same window as the spike (same as latency gate).

### C. Suggested human-approved actions (ordered by safety)

| Priority | When evidence shows… | Suggested action | Who executes |
| --- | --- | --- | --- |
| 1 | Error rate real (traffic floor met); class unclear | Package metrics + log samples + trace IDs; continue triage | AIO on-call |
| 2 | Downstream/DB connectivity errors; dependency pods not Ready | Report dependency health to **CDO**; do not restart shared data stores as first step | AIO → CDO |
| 3 | Clear bad deploy / config of the **application** service | Propose a CDO-approved GitOps revert of **that** application revision | CDO (+ AIO verify error rate) |
| 4 | Shared platform store unhealthy after CDO diagnosis | CDO follows **platform** datastore runbook (restore/failover/restart only under CDO change control) | **CDO only** |

Use the same pre-state, GitOps approval, Argo health, verification, and rollback
contract as the latency runbook. Do not replace it with an untracked direct
cluster mutation.

> **Postgres / shared DB:** AIOps runbook does **not** suggest `kubectl rollout restart statefulset/postgresql` (or equivalent) as a default or early step. Restarting a shared datastore has high blast radius (connection storms, multi-service impact) and is **CDO platform last-resort** only, outside this curated MVP allow-list.

### D. Do not

- Restart PostgreSQL (or any shared StatefulSet) from an AIO runbook hint.
- Rollback without deploy/time correlation.
- Treat client/user errors as infra incidents if OTel marks non-system statuses as ERROR (see detection limitations).

### E. Escalation owner

| Suspected class | Primary | Secondary |
| --- | --- | --- |
| Application / recent service deploy | AIO01 application owner / Tech Lead | AIO on-call |
| Data plane, networking, node, shared PostgreSQL platform | CDO platform on-call | AIO on-call (evidence only) |
| Cross-service mesh of failures | CDO platform (coordination) | Service owners per failing dependency |

### F. Canonical `runbook_hint` payload (allow-list)

> Generator must emit these **snake_case IDs** (or an evidence-gated subset in the same order). Do not rewrite as free text.

```yaml
runbook_hint:
  incident_type: error_rate_spike
  confidence: high
  evidence_checks:
    - confirm_error_ratio_with_min_traffic
    - classify_logs_infra_vs_app
    - check_pods_endpoints_events
  do_not:
    - restart_shared_postgresql_from_aio_hint
    - rollback_without_deploy_correlation
  suggested_actions:
    - continue_readonly_triage
    - if_bad_app_deploy_then_propose_cdo_gitops_revert
    - if_shared_datastore_unhealthy_then_cdo_platform_runbook
  escalation:
    primary: aio01_oncall
    secondary: cdo_platform
  known_limitations: []
  automation:
    mode: recommend
    eligible: false
    candidate_action_id: null
    blocked_by:
      - human_approval_required
```

---

## 4. Runbook MVP-3: LLM Timeout / Error

### A. Symptoms

Alert `AIOpsLLMIntegrationFailureCritical` (AI span error rate > 0.5/s **or** AI assistant throughput ~0 while AI path still receives traffic) or `AIOpsLLMIntegrationFailureWarning` (AI span error rate > 0.1/s), scoped to the product-reviews AI path (see detection rules).

### B. Evidence to check (read-only)

1. **Prometheus — AI path isolation** (current `product-reviews` contract):

   The provider contract is `app_llm_calls_total`, `app_llm_errors_total`, and
   `app_llm_latency_seconds`. `app_ai_assistant_counter_total` may be used only
   as the upstream assistant-demand signal; it is not a substitute for the
   provider call/error counters. Verify exported names under real traffic before
   treating an empty series as a healthy zero.

   ```promql
   # Provider failure rate and call throughput
   sum(rate(app_llm_errors_total[3m]))
   sum(rate(app_llm_calls_total[3m]))

   # Provider latency
   histogram_quantile(0.95, sum by (le) (rate(app_llm_latency_seconds_bucket[3m])))

   # Optional demand cross-check: assistant requests reaching product-reviews
   sum(rate(app_ai_assistant_counter_total[3m]))

   # Errors on AI span only (avoids mixing with generic product-reviews errors)
   rate(
     traces_span_metrics_calls_total{
       service_name="product-reviews",
       span_name="get_ai_assistant_response",
       status_code="STATUS_CODE_ERROR"
     }[3m]
   )
   ```

2. **OpenSearch — Bedrock/product-reviews errors** (production resource scope):

   ```json
   {
     "query": {
       "bool": {
          "must": [
            { "term": { "resource.service.name": "product-reviews" } },
            { "term": { "resource.k8s.namespace.name": "techx-tf4" } },
            { "term": { "severity.text": "ERROR" } }
         ],
         "should": [
           { "match_phrase": { "body": "rate limit exceeded" } },
           { "match_phrase": { "body": "status code 429" } },
           { "match_phrase": { "body": "timeout" } }
         ],
         "minimum_should_match": 1
       }
     }
   }
   ```

3. **Traces:** ERROR spans on AI operations (`get_ai_assistant_response` / product AI assistant path); note provider vs in-cluster hop.

4. **Incident-flag state (read-only diagnosis):**  
   Check whether org inject flags such as `llmRateLimitError` / `llmInaccurateResponse` are **on** (flagd UI, last known Git/Helm values, or CDO-visible config).  
   - Purpose: distinguish **controlled inject / drill** from **organic provider or app failure**.  
   - **Do not** patch flagd ConfigMaps to turn flags off or invent new flags.

5. **Architecture-aware provider path (current AIE direction):**  
   Prefer checks for **Bedrock / Pod Identity / IAM** readiness, model invocation errors, Guardrail blocks, and **application safe-fallback / unavailable** UX — not a default “rotate OpenAI API key” story unless that legacy path is still explicitly in use for the environment under incident.

6. **Fallback / customer impact:**  
   Confirm storefront still degrades safely (static/safe message, no hang, no silent mock if product policy forbids it). Capture whether fallback counters/logs exist.

### C. Suggested human-approved actions (ordered by safety)

| Priority | When evidence shows… | Suggested action | Who executes |
| --- | --- | --- | --- |
| 1 | AI errors/throughput drop confirmed | Freeze further AI-related rollout; attach Prom/log/trace evidence | AIO on-call + AIE owner |
| 2 | 429 / rate limit / timeout (inject **or** provider) | Rely on **application-level** safe fallback / unavailable path already in product; verify UX; do **not** restart `llm` or `product-reviews` to “fix” 429 | AIE / AIO verify |
| 3 | Inject flag `llmRateLimitError` (or similar) is on | Treat as expected inject path: prove graceful degradation; document; **do not** disable flagd inject mechanism | AIE + PM evidence |
| 4 | Organic provider/IAM/Pod Identity failure | Escalate to AIE for model/integration fix; CDO only if cluster identity/network/platform change is required | AIE primary; CDO secondary |
| 5 | Bad AI-related deploy of app/chart | Optional **CDO-approved** GitOps/Helm revert of the AI-related change set | CDO (+ AIE/AIO verify) |

### D. Do not

- `kubectl patch` / rewrite `flagd` ConfigMap (`demo.flagd.json` or equivalent) — high risk of wiping BTC inject flags; forbidden as MVP remediation and conflicts with program rules on incident mechanisms.
- Invent flags such as `llmFallbackMode` that are **not** in `techx-corp-chart/flagd/demo.flagd.json`.
- Restart `llm` or `product-reviews` as the primary response to provider 429/timeout.
- Claim auto-remediation or traffic mutation by AIOps.

### E. Escalation owner

| Suspected class | Primary | Secondary |
| --- | --- | --- |
| Model quality, prompt/Guardrail, AI fallback behavior | AIE owner (AIO01) | AIO on-call (AIOps evidence) |
| Bedrock quota / provider outage / integration contract | AIE owner (AIO01) | CDO if account/IAM/network platform |
| Cluster identity (Pod Identity), DNS, egress, deploy pipeline | CDO platform | AIE owner |

### F. Canonical `runbook_hint` payload (allow-list)

> Generator must emit these **snake_case IDs** (or an evidence-gated subset in the same order). Do not rewrite as free text.

```yaml
runbook_hint:
  incident_type: llm_timeout_error
  confidence: high
  evidence_checks:
    - verify_ai_calls_errors_and_latency
    - classify_inject_flag_vs_organic_provider_failure_readonly
  do_not:
    - patch_or_rewrite_flagd
    - invent_llm_fallback_mode_flag
    - restart_llm_or_product_reviews_for_429
  suggested_actions:
    - confirm_app_safe_fallback_ux
    - freeze_ai_rollout
    - escalate_aie_then_cdo_if_platform
  escalation:
    primary: aie_owner_aio01
    secondary: cdo_platform
  known_limitations: []
  automation:
    mode: recommend
    eligible: false
    candidate_action_id: freeze_ai_rollout
    blocked_by:
      - human_approval_required
```

---

## 5. Cross-cutting: how the detector / summary generator must use this map

| Detector / summary field | Source in this doc | Format constraint |
| --- | --- | --- |
| `runbook_hint.incident_type` | MVP-1 → `latency_spike`; MVP-2 → `error_rate_spike`; MVP-3 → `llm_timeout_error` | snake_case enum only |
| `runbook_hint.evidence_checks[]` | Section B queries/check IDs | structured read-only checks; not free-form remediation |
| `runbook_hint.suggested_actions` | Section C (safety order) + §F allow-list IDs | **snake_case action IDs only** (e.g. `verify_p95_and_trace_outliers`); no free-text sentences |
| `runbook_hint.do_not` | Section D + §F allow-list IDs | **snake_case IDs only** |
| `runbook_hint.escalation` | Section E | `primary` / `secondary` as snake_case owner ids |
| `runbook_hint.confidence` / `runbook_hint.known_limitations` | Detection rules + §6 known gaps | Required; missing sources must block mutation and remain visible to operators |
| `runbook_hint.automation` | Target policy design | Required mode, eligibility, candidate action, and blocked reasons; 07a defaults to non-executing `recommend` |

**Contract enforcement (TF4AIO-42/43):**

- The incident summary generator and detector are planned **producers** of
  `runbook_hint`; until conformance tests exist, this is the target allow-list
  contract rather than a runtime implementation claim.
- Emit the same schema as §0 and the §F YAML samples. Do not rename fields (`suggestedActions`, `suggested-actions`, `actions`) or change ID casing.
- UI copy may map IDs → display strings; the stored/API payload keeps snake_case IDs so consumers do not diverge from the contract.
- Reject or drop unknown action IDs rather than accepting LLM-invented mutate steps.

AIOps must not render arbitrary mutate commands. It emits curated action IDs and
routes approved GitOps/platform work to the owning human or executor handler.

---

## 6. Known limitations

1. **Idle cluster / missing series:** PromQL may return no data without traffic; hints should say “signal not confirmable” rather than invent actions.
2. **Inject-flag noise:** `llmRateLimitError` drills will fire MVP-3 by design; runbook treats this as degradation proof, not a license to mutate flagd.
3. **Metric contract drift:** The runbook uses the current provider family
   `app_llm_calls_total`, `app_llm_errors_total`, and
   `app_llm_latency_seconds`; `app_ai_assistant_counter_total` is only an
   upstream demand cross-check. Re-verify exported names against
   `product-reviews/metrics.py` and live Prometheus after instrumentation changes.
4. **Namespace/context:** Commands use `<namespace>` placeholders — confirm live context (`techx-tf4` or current TF namespace) before any human execution.
5. **No claim of automated remediation readiness:** The target architecture is
   documented, but policy/executor runtime evidence remains phased work. The
   current mode is `observe` or `recommend`.
6. **Runbook hint contract drift:** If the summary generator emits free-text actions or non-snake_case IDs, consumers of `runbook_hint.suggested_actions` will mismatch this spec. Keep generator templates / schemas synchronized with §0 and §F allow-lists.

---

## 7. Acceptance checklist (TF4AIO-44)

| Requirement | Status in this revision |
| --- | --- |
| Each MVP incident has symptoms | Yes (§A) |
| Evidence to check | Yes (§B), aligned with detection rules where applicable |
| Suggested human-approved action | Yes (§C), ordered, owner-tagged, evidence-gated |
| Escalation owner | Yes (§E), AIO01 / AIE / CDO mapped |
| 07a runtime boundary and final closed-loop scope are separated | Yes (§0 plus target architecture) |
| No flagd mutation / no default DB restart in allow-list | Yes |
| Nested `runbook_hint` target contract is consistent | Yes (§0 contract + §5 + §F examples) |
| Current Bedrock telemetry/resource contract is used | Yes (§4.B + §6.3) |
| Automation policy, verification, rollback, and escalation are planned | Yes (target architecture) |

---

## 8. Revision history

| Date | Change |
| --- | --- |
| 2026-07-17 | Add final closed-loop scope; link target architecture; unify nested runbook contract; align Bedrock metrics/resource scope; replace direct mutation examples with approved GitOps change control |
| 2026-07-16 | Review follow-up: formalize `runbook_hint` output contract (snake_case action / do-not IDs; generator must not invent field names or free-text actions); expand metric-name drift risk for pinned PromQL (e.g. `app_ai_assistant_counter_total` vs evolving `app_llm_*` family) with periodic re-verify guidance |
| 2026-07-16 | Rewrite for TF4AIO-44 review: remove flagd patch / invented `llmFallbackMode`; remove default PostgreSQL restart; reframe kubectl as CDO-optional; align evidence with detection rules; Bedrock/Pod Identity-aware LLM path; structured `runbook_hint` examples |
| (prior) | Initial draft with executable-style scale/rollback/restart/flagd actions |
