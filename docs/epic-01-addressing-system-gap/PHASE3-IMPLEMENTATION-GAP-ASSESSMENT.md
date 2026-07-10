# Phase 3 Implementation-Gap Assessment

## 1. Executive Summary

Phase 3 baseline is deployable demo platform, not production-safe takeover baseline. Biggest gaps are not abstract Kubernetes hygiene: checkout can succeed while downstream order event is lost, accounting can consume then drop orders, cart and core data stores are single ephemeral pods, rollout readiness is mostly unwired, observability admin/log stores are unauthenticated inside access boundary, and AI path leaks prompt content while lacking quality fallback.

Confirmed weaknesses versus runtime hypotheses:

- Confirmed from repository: unsafe Kafka producer acknowledgement, accounting auto-commit-before-durable-write risk, missing probes in active Helm values, single replicas, no PVC/StatefulSet for in-cluster data stores, Grafana anonymous Admin, OpenSearch security disabled, AI prompt capture/logging, checkout graceful shutdown bug, no explicit checkout dependency deadlines.
- Runtime validation required: actual public exposure, node/AZ distribution, admission behavior with `deploy/quota.yaml`, real SLO/error-rate queries, alert delivery, and whether cluster-level policies compensate for chart gaps.

Top 5 risks with direct business/SLO impact:

1. Checkout returns success even when Kafka order event is not durably acknowledged, breaking accounting/fraud/audit.
2. Accounting consumer can advance offsets while DB writes fail, losing order accounting trail.
3. Cart state is single-pod Valkey with no chart persistence and 60-minute TTL, repeating known cart-loss incident mode.
4. Revenue path has single replicas, no active readiness/liveness probes, no HPA/PDB, and broken checkout graceful shutdown.
5. AI review path captures/logs customer prompt content and can display inaccurate responses without guardrail/fallback.

Top 5 implementation gaps to fix or validate first:

1. Kafka/order-event integrity: producer acks, request outcome, consumer commit semantics, replay path.
2. Rollout safety for checkout/cart/payment/frontend/product-catalog: probes, graceful termination, PDB, minimum replicas.
3. Data durability baseline: Valkey/PostgreSQL/Kafka persistence/backup trade-off within $300/week.
4. SLO observability: checkout/cart/browse/AI SLI dashboards and routed alerts.
5. AI safety baseline: disable prompt-content capture in prod-like mode, fallback on LLM failure, eval set before real model.

## 2. Assessment Scope and Method

Files reviewed:

- Onboarding/hypothesis docs: `README.md`, `docs/requirements/RULES.md`, `docs/requirements/GETTING_STARTED.md`, `docs/requirements/onboarding/ARCHITECTURE.md`, `docs/requirements/onboarding/SLO.md`, `docs/requirements/onboarding/BUDGET.md`, `docs/requirements/onboarding/INCIDENT_HISTORY.md`, `docs/requirements/onboarding/PITCH_GUIDE.md`, `docs/requirements/mandates/README.md`, `docs/notes/phase3-pre-system-exploration.md`.
- Helm/deploy: `techx-corp-chart/values.yaml`, `techx-corp-chart/templates/*.yaml`, `techx-corp-chart/grafana/provisioning/**`, `deploy/*.yaml`, `deploy/build-push-images.sh`.
- Critical app paths: `src/checkout/**`, `src/cart/**`, `src/product-catalog/**`, `src/product-reviews/**`, `src/llm/**`, `src/payment/**`, `src/email/**`, `src/shipping/**`, `src/accounting/**`, `src/fraud-detection/**`, `src/frontend/**`, `src/frontend-proxy/**`.

Existing exploration document was treated as hypotheses only. Each retained claim below was checked against Helm values/templates or source code. Claims needing cluster evidence were moved to Runtime Validation Required.

Static-analysis limitations:

- No cluster access, rendered manifests, live Prometheus labels, Cost Explorer, CloudTrail, or actual AWS/EKS configuration were available.
- Helm rendering was not used in final evidence; line-level source/static chart evidence only.
- Some Kubernetes outcomes may be overridden by cluster policies outside this repository; those are explicitly marked runtime validation required.

Required Opus subagent review was run after initial scan. Its top findings were merged, duplicates removed, and high/critical items manually re-checked against source evidence. Disagreements are noted in section 10.

## 3. Architecture Reality Check

### Actual component inventory

| Component | Intended responsibility | Actual baseline configuration | Critical dependencies | Production-safe now? | Restart/scale/load failure mode |
|---|---|---|---|---|---|
| `frontend-proxy` | Envoy entrypoint and observability routes | ClusterIP service, routes `/`, `/grafana/`, `/jaeger/`, `/loadgen/`, `/otlp-http/`; Envoy admin binds `0.0.0.0:10000` | frontend, Grafana, Jaeger, load-generator, collector | No, exposure/auth depends on port-forward/Ingress boundary | Single replica default; if exposed, admin/observability surfaces reachable |
| `frontend` | Next.js storefront/API | single default replica, no probes in values | cart, checkout, catalog, reviews, recommendation, ad, shipping | No | Browse/checkout UI unavailable during pod restart |
| `product-catalog` | list/get/search products | Go gRPC, PostgreSQL conn string literal, memory limit 20Mi | PostgreSQL, flagd | No | DB outage breaks browse/search/checkout item prep |
| `product-reviews` | reviews + AI assistant | Python gRPC, dummy API key baseline, GenAI content capture enabled | PostgreSQL, LLM, catalog, flagd | No | LLM/DB failures leak or fail AI path; prompt content in telemetry |
| `llm` | mock OpenAI-compatible backend | Flask debug server, no resource/security/probe config in values | flagd | No | Mock behavior not real model quality/cost; debug mode unsuitable |
| `cart` | cart state | .NET gRPC, Valkey backend, memory limit only | Valkey, flagd | No | Valkey restart/TTL loses carts; cart errors can dirty checkout state |
| `checkout` | order orchestration | Go gRPC, memory limit 20Mi, sequential dependencies, Kafka async producer | cart, catalog, currency, shipping, payment, email, Kafka | No | Any dependency can fail checkout; partial success after payment possible |
| `payment` | mock card charge | Node gRPC, per-request OpenFeature provider init | flagd | Partially | flagd latency amplifies payment latency; pod restart cuts in-flight charge |
| `shipping` / `quote` | shipping quote/order | HTTP, no idempotency state | quote | No | shipping after payment can fail checkout after charge |
| `currency` | price conversion | C++ gRPC | none | Partially | serial fan-out bottleneck for browse/checkout |
| `email` | order email | Sinatra test mailer, can leak memory by flag | flagd | No | email failure logged but checkout succeeds; no resend queue |
| `accounting` | consume order events and persist | Kafka auto-commit enabled, PostgreSQL writes | Kafka, PostgreSQL | No | DB failure can lose consumed orders |
| `fraud-detection` | consume order events | consumes/logs only; sleeps under `kafkaQueueProblems` | Kafka, flagd | No | no fraud decision; consumer lag/rebalance under delay |
| `kafka` | order event bus | single Deployment, KRaft quorum 1, no PVC in chart | checkout/accounting/fraud | No | restart can lose event data and offsets |
| `postgresql` | catalog/reviews/accounting DB | single Deployment, static passwords, no PVC/StatefulSet in chart | catalog/reviews/accounting | No | restart/reschedule can lose mutable DB data |
| `valkey-cart` | cart KV store | single Deployment, no persistence config | cart | No | restart/reschedule loses carts |
| `otel-collector` | telemetry fan-in/out | DaemonSet, exports metrics/logs/traces, permissive CORS for OTLP HTTP | apps, Prometheus, Jaeger, OpenSearch | Partially | loss degrades visibility; `/otlp-http/` exposed through proxy |
| `prometheus` | metrics | persistence disabled, alertmanager disabled | collector, Grafana | No | restart loses metrics; no routed alertmanager |
| `jaeger` | traces | memory storage | collector, Grafana | No | restart loses traces |
| `opensearch` | logs | single-node, security plugin disabled, persistence disabled | collector, Grafana | No | unauthenticated logs internally; restart loses logs |
| `grafana` | dashboards/alerts | anonymous Admin, literal `admin` password | Prometheus, Jaeger, OpenSearch | No | any reachable user can alter dashboards/datasources |
| `load-generator` | Locust load | enabled by default, autostart true, 1500Mi memory limit | frontend-proxy, flagd | Runtime-dependent | can create baseline cost/load noise |
| `flagd` | protected fault-injection flags | local file by default; central read-only overlay removes UI | central flag endpoint when overlay used | Protected mechanism, not removable | if overlay omitted, central incidents not wired |

### Critical request and event paths

1. Browse/search: user → `frontend-proxy` → `frontend` → `product-catalog` → PostgreSQL; product list then calls currency conversion per product in frontend.
2. Product review/AI: `frontend` → `product-reviews` → PostgreSQL + `llm` → optional catalog tool call.
3. Cart: `frontend` → `cart` → `valkey-cart`.
4. Checkout/payment: `frontend` → `checkout` → cart → product-catalog → currency → shipping/quote → payment → shipping → cart empty → email → Kafka.
5. Kafka order path: `checkout` produces `orders` → `accounting` persists PostgreSQL, `fraud-detection` consumes/logs.
6. Telemetry: services/proxy → collector → Prometheus/Jaeger/OpenSearch → Grafana.
7. Deployment/rollout: Helm chart emits Deployments/Services/Ingress when values enabled; no active HPA/PDB/probes in baseline values.

### Documentation-to-code mismatches

| Expected behavior | Evidence source | Actual implementation | Gap | Impact |
|---|---|---|---|---|
| Checkout ≥ 99% success must be protected first | `docs/requirements/onboarding/SLO.md:11-14` | checkout is single replica, no active probe, no explicit dependency deadlines, broken graceful shutdown | revenue path not hardened | checkout SLO can burn during dependency slowness/rollout |
| Product review AI must not show misleading summaries | `docs/requirements/onboarding/SLO.md:12` | `llmInaccurateResponse` can cause inaccurate answer path; no guardrail/eval before response | protected flag reveals missing validation/fallback | customer sees wrong AI output |
| Historical cart-loss lesson not fully resolved | `docs/requirements/onboarding/INCIDENT_HISTORY.md:16-22` | `valkey-cart` single replica, no persistence config, 60-minute TTL | recurrence path remains | active carts lost on restart/drain |
| Historical deploy readiness issue should be applied system-wide | `docs/requirements/onboarding/INCIDENT_HISTORY.md:24-30` | chart supports probes, values set none | readiness gating not wired | traffic can hit non-ready pod |
| Observability available for SLO | `docs/requirements/onboarding/SLO.md:25-29` | only one cart alert found; Prometheus persistence and Alertmanager disabled | SLO measurement/routing incomplete | on-call cannot defend error budget |
| README says `.github/CODEOWNERS` exists | `README.md:8-10`, `README.md:57-58` | `.github/**` not present in repository scan | ownership/audit doc contradiction | PR approval claim not enforceable from repo |
| Getting started says build pushes ECR after `.env.override` | `docs/requirements/GETTING_STARTED.md:26-33` | script comments still say Docker Hub/public and final URL says Docker Hub | deployment doc/script mismatch | operator can push/check wrong registry |

## 4. Confirmed Implementation Gaps

### 4.1 Security

### SEC-01 — Grafana and OpenSearch are administrative/log surfaces without authentication in chart baseline

- Severity: High
- Confidence: Confirmed
- Domain: Security
- Affected components: Grafana, OpenSearch, frontend-proxy, observability stack
- Evidence:
  - `techx-corp-chart/values.yaml:1186-1192`
  - `techx-corp-chart/values.yaml:1195`
  - `techx-corp-chart/values.yaml:1221-1228`
  - `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml:49-52`
- Current implementation: Grafana disables login and grants anonymous `Admin`; password literal is `admin`. OpenSearch has `DISABLE_SECURITY_PLUGIN=true` and persistence disabled. Envoy routes `/grafana/` through the main proxy.
- Why this is a real gap: Observability UI and log store are not just dashboards; they expose traces/logs/data sources and can change alerting/dashboards. Repository actively configures anonymous admin/security-disabled state.
- Failure or abuse scenario: Anyone with network path to `frontend-proxy` or service network can alter Grafana dashboards/datasources or read/write OpenSearch logs.
- Business and SLO impact: Incident evidence can be tampered with or lost; SLO dashboards can be changed during outage.
- Why this matters in Phase 3: Auditability and Ops Review require trustworthy metrics/logs/traces.
- Recommended remediation direction: Keep access through `frontend-proxy` if needed, but require auth, reduce Grafana anonymous role to viewer or disable it, enable OpenSearch security or isolate it with NetworkPolicy, and document emergency access.
- Runtime validation: Check `kubectl get ingress,svc`; attempt unauthenticated `/grafana/` admin action and OpenSearch access from a random pod.
- Rollback or safety constraint: Do not block on-call access without break-glass account; rollback via Helm values.
- Complexity: M
- Week 1 suitability: Yes

### SEC-02 — Static credentials and plaintext internal DB connection strings are committed into baseline values

- Severity: High
- Confidence: Confirmed
- Domain: Security
- Affected components: PostgreSQL, product-catalog, product-reviews, accounting
- Evidence:
  - `techx-corp-chart/values.yaml:181-184`
  - `techx-corp-chart/values.yaml:581-582`
  - `techx-corp-chart/values.yaml:618-619`
  - `techx-corp-chart/values.yaml:866-870`
- Current implementation: App and PostgreSQL credentials are literal Helm values: `root` / `otel`, app password `otelp`, and `sslmode=disable`.
- Why this is a real gap: Anyone with repo, rendered manifests, pod env access, or Grafana/trace/log leakage gets DB credentials. Rotation requires config changes across services.
- Failure or abuse scenario: Compromised low-value pod uses committed DB credentials to read or modify catalog/reviews/accounting data.
- Business and SLO impact: Customer-visible catalog/reviews can be corrupted; accounting audit data can be modified.
- Why this matters in Phase 3: System is operated by multiple teams; static shared secrets break least privilege and auditability.
- Recommended remediation direction: Move DB credentials to Kubernetes Secrets, split users by service privilege, plan rotation, and keep TLS decision explicit.
- Runtime validation: From a non-DB pod, test DB reachability and credential scope; check rendered manifests/env exposure.
- Rollback or safety constraint: Rotate with staged secret rollout; do not break init SQL/user creation order.
- Complexity: M
- Week 1 suitability: Yes

### SEC-03 — Most workloads lack container hardening despite chart support for securityContext

- Severity: Medium
- Confidence: Confirmed
- Domain: Security
- Affected components: accounting, ad, cart, checkout, currency, email, fraud-detection, image-provider, load-generator, product-catalog, product-reviews, recommendation, shipping, flagd, llm, postgresql
- Evidence:
  - `techx-corp-chart/values.yaml:35-37`
  - `techx-corp-chart/values.yaml:406-410`
  - `techx-corp-chart/values.yaml:468-472`
  - `techx-corp-chart/values.yaml:559-563`
  - `techx-corp-chart/values.yaml:654-658`
  - `techx-corp-chart/values.yaml:810-814`
  - `techx-corp-chart/values.yaml:901-905`
- Current implementation: Global `securityContext` is `{}`. Only six components set `runAsNonRoot`; no values set `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, dropped capabilities, or seccomp.
- Why this is a real gap: Many exposed application runtimes run with image defaults and broad container capabilities.
- Failure or abuse scenario: RCE in product-reviews/llm/load-generator gives writable root filesystem and default Linux capabilities inside pod.
- Business and SLO impact: Compromise can pivot to DB/Kafka/OpenSearch because NetworkPolicy is absent.
- Why this matters in Phase 3: Security hardening must protect customer, prompt, and order data.
- Recommended remediation direction: Add global baseline hardening where compatible; override only components that need writes/caps.
- Runtime validation: `kubectl get pod -o json` check effective UID/caps/seccomp and write paths per container.
- Rollback or safety constraint: Test per image; read-only root may require writable temp dirs.
- Complexity: M
- Week 1 suitability: Needs baseline first

### SEC-04 — Cart API lets client choose `userId` for cart mutation/empty operations

- Severity: Medium
- Confidence: Confirmed
- Domain: Security
- Affected components: frontend cart API, cart service, Valkey
- Evidence:
  - `techx-corp-platform/src/frontend/pages/api/cart.ts:33-45`
  - `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs:131-174`
  - `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs:185-199`
- Current implementation: POST and DELETE accept `userId` from request body and mutate that cart. GET uses query `sessionId`.
- Why this is a real gap: Client-controlled identifier is trust boundary. No session-to-cart ownership check exists in API handler.
- Failure or abuse scenario: Malicious client empties another active cart if user/cart ID is known or leaked via logs/traces.
- Business and SLO impact: Cart success SLO can look healthy while users lose carts; revenue conversion drops.
- Why this matters in Phase 3: Cart has explicit 99.5% success target and known loss incident.
- Recommended remediation direction: Derive user/cart ID server-side from session for all cart operations; validate quantities and item IDs at API boundary.
- Runtime validation: Try DELETE with another observed userId/sessionId pair and confirm cart loss.
- Rollback or safety constraint: Preserve anonymous-cart UX; migrate existing sessions carefully.
- Complexity: S
- Week 1 suitability: Yes

### 4.2 Kubernetes and Helm

### K8S-01 — Helm supports probes but baseline values configure none

- Severity: High
- Confidence: Confirmed
- Domain: Kubernetes
- Affected components: all app services, especially frontend, checkout, cart, payment, product-catalog
- Evidence:
  - `techx-corp-chart/templates/_objects.tpl:72-79`
  - `techx-corp-chart/values.yaml:151-154`
  - `docs/requirements/onboarding/INCIDENT_HISTORY.md:24-30`
- Current implementation: Template emits `livenessProbe`/`readinessProbe` only if values set them. Values only contain commented examples; no component configures probes.
- Why this is a real gap: Historical payment deploy outage came from missing readiness gating. Current baseline does not wire readiness across revenue path.
- Failure or abuse scenario: Rolling deploy sends traffic to process with open port but not initialized dependency/flag/client state.
- Business and SLO impact: Checkout/payment requests fail during deploy and burn checkout error budget.
- Why this matters in Phase 3: Week 1 pitch must prove safe deployment before improvements.
- Recommended remediation direction: Add minimal service-appropriate readiness/liveness probes, using gRPC health where available and HTTP health where not; tune thresholds per startup behavior.
- Runtime validation: Render/apply chart, `kubectl get deploy -o yaml`, rollout restart under load, confirm endpoints only include ready pods.
- Rollback or safety constraint: Bad probes can cause crash loops; rollout service-by-service.
- Complexity: M
- Week 1 suitability: Yes

### K8S-02 — Single replicas plus no HPA/PDB create outage on pod/node disruption

- Severity: High
- Confidence: Confirmed
- Domain: Kubernetes
- Affected components: all components, especially checkout/cart/frontend/payment/data stores
- Evidence:
  - `techx-corp-chart/values.yaml:26-28`
  - `techx-corp-chart/values.yaml:714-715`
  - `techx-corp-chart/values.yaml:786-787`
  - `techx-corp-chart/values.yaml:836-837`
  - `techx-corp-chart/values.yaml:887-888`
  - no `HorizontalPodAutoscaler` / `PodDisruptionBudget` found in chart templates
- Current implementation: Default replicas = 1. Flagd/Kafka/PostgreSQL/Valkey explicitly set 1. No HPA/PDB manifests exist.
- Why this is a real gap: Any single pod restart, eviction, or node drain removes capacity for that component. Checkout path depends on many singletons.
- Failure or abuse scenario: Node drain during maintenance evicts cart/payment/catalog; checkout becomes unavailable until reschedule completes.
- Business and SLO impact: Direct revenue outage and cart failures.
- Why this matters in Phase 3: Incident history says deploy/node events were prior failure modes.
- Recommended remediation direction: Start with two replicas for stateless revenue services after probes/resources; add PDBs; add HPA only after requests and metrics are valid. Treat data stores separately with persistence/managed options.
- Runtime validation: `kubectl get deploy,hpa,pdb`; drain test or delete pods under synthetic checkout load.
- Rollback or safety constraint: Do not scale stateful single-broker DB/Kafka blindly without data/leader design.
- Complexity: M
- Week 1 suitability: Yes for stateless services; data layer needs baseline first

### K8S-03 — Resource model is incomplete and conflicts with sample ResourceQuota

- Severity: Medium
- Confidence: Confirmed
- Domain: Kubernetes / Cost
- Affected components: all app workloads, namespace quota
- Evidence:
  - `techx-corp-chart/values.yaml:186-188`
  - `techx-corp-chart/values.yaml:279-281`
  - `techx-corp-chart/values.yaml:587-589`
  - `deploy/quota.yaml:4-9`
- Current implementation: Services mostly specify memory limits only. No CPU requests/limits are configured. `deploy/quota.yaml` sets hard `requests.cpu`, `requests.memory`, `limits.cpu`, `limits.memory`.
- Why this is a real gap: Without CPU requests, scheduler and HPA inputs are weak; with quota requiring CPU requests/limits and no LimitRange defaults, admission may reject pods.
- Failure or abuse scenario: Team applies sample quota, Helm deploy fails for missing CPU requests/limits; or CPU-heavy flag path starves revenue services.
- Business and SLO impact: Bad deploy baseline or noisy-neighbor CPU contention affects checkout/browse.
- Why this matters in Phase 3: Budget and scaling decisions need real resource baselines.
- Recommended remediation direction: Measure CPU/memory through Prometheus/Grafana under baseline load, then set conservative requests/limits for revenue services first; add LimitRange or adjust quota plan.
- Runtime validation: Apply quota in test namespace and run Helm dry-run/apply; inspect effective pod QoS and throttling.
- Rollback or safety constraint: Too-low limits cause OOM/throttling; change one tier at a time.
- Complexity: M
- Week 1 suitability: Needs runtime baseline first

### K8S-04 — In-cluster PostgreSQL, Valkey, and Kafka are Deployments with no repository-defined persistence

- Severity: Critical
- Confidence: Confirmed
- Domain: Kubernetes / Reliability
- Affected components: PostgreSQL, Valkey, Kafka, Prometheus, Jaeger, OpenSearch
- Evidence:
  - `techx-corp-chart/templates/_objects.tpl:3-7`
  - `techx-corp-chart/values.yaml:829-879`
  - `techx-corp-chart/values.yaml:782-814`
  - `techx-corp-chart/values.yaml:880-905`
  - `techx-corp-chart/values.yaml:1039-1043`
  - `techx-corp-chart/values.yaml:1172-1174`
  - `techx-corp-chart/values.yaml:1220-1228`
- Current implementation: Custom components render as `Deployment`. No `StatefulSet`, `PersistentVolumeClaim`, or `volumeClaimTemplates` exist in chart. Prometheus PV disabled, Jaeger memory storage, OpenSearch persistence disabled.
- Why this is a real gap: Runtime-created order/accounting/cart/event/log/metric/trace state can disappear on restart/reschedule.
- Failure or abuse scenario: Node drain or pod restart wipes Valkey carts, Kafka events, PostgreSQL mutable rows, and incident telemetry.
- Business and SLO impact: Data loss, cart loss, incomplete accounting/fraud, and no post-incident evidence.
- Why this matters in Phase 3: Known incidents include cart loss and DB saturation; auditability requires retention.
- Recommended remediation direction: Decide per store: managed service vs StatefulSet+PVC+backup. Prioritize Valkey cart durability and Kafka/order/audit path before long retention observability.
- Runtime validation: Create cart/order, restart pods, compare data/offsets/history before/after.
- Rollback or safety constraint: Stateful migration needs backup/restore and rollback plan; do not change storage class blindly.
- Complexity: L
- Week 1 suitability: Needs baseline first

### 4.3 Reliability and Data Durability

### REL-01 — Checkout can succeed while Kafka order event is lost

- Severity: Critical
- Confidence: Confirmed
- Domain: Reliability / Auditability
- Affected components: checkout, Kafka, accounting, fraud-detection
- Evidence:
  - `techx-corp-platform/src/checkout/kafka/producer.go:38-41`
  - `techx-corp-platform/src/checkout/main.go:384-392`
  - `techx-corp-platform/src/checkout/main.go:638-645`
- Current implementation: Producer uses `sarama.NoResponse`; source comment says it may swallow failed messages. `PlaceOrder` calls `sendToPostProcessor` after order work and returns success regardless Kafka result.
- Why this is a real gap: Order success is not coupled to durable event publication or recovery queue.
- Failure or abuse scenario: Kafka broker restart/outage during checkout; customer sees successful order, accounting/fraud never receive it.
- Business and SLO impact: Revenue event missing from accounting and fraud; audit trail broken.
- Why this matters in Phase 3: Kafka order-event path is mandatory and checkout is revenue-critical.
- Recommended remediation direction: Require broker acks, bounded publish timeout, explicit failure metric, and outbox/retry path. Keep protected Kafka fault flag; add resilience around it.
- Runtime validation: Stop/isolate Kafka, place order, compare checkout response, topic offsets, accounting rows, fraud logs.
- Rollback or safety constraint: Stronger acks can increase latency; measure checkout p95 before/after.
- Complexity: M
- Week 1 suitability: Yes

### REL-02 — Accounting consumer can auto-commit offsets for orders that failed DB persistence

- Severity: Critical
- Confidence: Confirmed
- Domain: Reliability / Auditability
- Affected components: accounting, Kafka, PostgreSQL
- Evidence:
  - `techx-corp-platform/src/accounting/Consumer.cs:65-67`
  - `techx-corp-platform/src/accounting/Consumer.cs:92-96`
  - `techx-corp-platform/src/accounting/Consumer.cs:131-136`
  - `techx-corp-platform/src/accounting/Consumer.cs:141-148`
- Current implementation: Consumer has `EnableAutoCommit = true`. Processing catches all exceptions and only logs. If `_dbContext` is null, it returns without persisting.
- Why this is a real gap: Kafka offset can advance independently of durable accounting write.
- Failure or abuse scenario: PostgreSQL outage or bad DB env; messages are consumed/committed but not written.
- Business and SLO impact: Order accounting gap, reconciliation failure, incident audit loss.
- Why this matters in Phase 3: Accounting is explicit Kafka consumer path and auditability pillar.
- Recommended remediation direction: Disable auto-commit; commit only after successful DB transaction; add retry/backoff and dead-letter/quarantine path.
- Runtime validation: Break DB connection, publish order, observe consumer group offset and accounting table.
- Rollback or safety constraint: Manual commit bugs can cause duplicates; make DB writes idempotent by order ID.
- Complexity: M
- Week 1 suitability: Yes

### REL-03 — Checkout has partial-success failure modes after payment with no idempotency or compensation

- Severity: High
- Confidence: Confirmed
- Domain: Reliability
- Affected components: checkout, payment, shipping, cart, email, Kafka
- Evidence:
  - `techx-corp-platform/src/checkout/main.go:328-344`
  - `techx-corp-platform/src/checkout/main.go:348-388`
  - `techx-corp-platform/src/checkout/main.go:378-382`
- Current implementation: Card charge happens before shipping order. Shipping failure after charge returns checkout error. Cart-empty error is ignored. Email failure logs warning. Kafka failure does not fail checkout. Order ID is generated server-side each attempt; no idempotency key.
- Why this is a real gap: Retrying checkout after partial failure can double-charge or double-ship while cart/event state diverges.
- Failure or abuse scenario: Payment succeeds, shipping endpoint times out; user retries; second payment succeeds because no idempotency boundary exists.
- Business and SLO impact: Customer trust, refunds, support load, revenue reconciliation.
- Why this matters in Phase 3: Checkout is most important SLO and business path.
- Recommended remediation direction: Add idempotency key from client/session, persist order state/outbox, define compensation or retry semantics for shipping/email/Kafka.
- Runtime validation: Inject shipping failure after payment and retry same checkout; inspect transactions/order events.
- Rollback or safety constraint: Idempotency store must be durable; keep migration reversible.
- Complexity: L
- Week 1 suitability: Needs baseline first

### REL-04 — Checkout dependency calls have no explicit deadlines or retry budget

- Severity: High
- Confidence: Confirmed
- Domain: Reliability / Performance
- Affected components: checkout, cart, catalog, currency, shipping, payment, email
- Evidence:
  - `techx-corp-platform/src/checkout/main.go:441-445`
  - `techx-corp-platform/src/checkout/main.go:462-465`
  - `techx-corp-platform/src/checkout/main.go:524-548`
  - `techx-corp-platform/src/checkout/main.go:560-563`
  - `techx-corp-platform/src/checkout/main.go:582-585`
- Current implementation: gRPC clients use default connection behavior. HTTP calls use inherited request context only. No `context.WithTimeout` or explicit retry policy in checkout source.
- Why this is a real gap: Slow dependency can hold checkout request until upstream timeout, with no per-hop budget or fallback.
- Failure or abuse scenario: Shipping or payment stalls; checkout goroutines pile up and p95/p99 exceed SLO.
- Business and SLO impact: Checkout ≥99% success and latency degrade under realistic dependency slowness.
- Why this matters in Phase 3: Protected fault injection should reveal missing timeouts/retries, not be removed.
- Recommended remediation direction: Define checkout deadline budget, per-dependency timeout, limited retries only for safe/idempotent calls, and failure metrics by dependency.
- Runtime validation: Delay shipping/payment; measure checkout latency, goroutines, and error distribution.
- Rollback or safety constraint: Retrying payment/shipping can duplicate side effects; do not retry non-idempotent operations until idempotency exists.
- Complexity: M
- Week 1 suitability: Yes for timeouts/metrics; retries need baseline

### REL-05 — Checkout graceful shutdown code is unreachable and server is invoked twice

- Severity: High
- Confidence: Confirmed
- Domain: Reliability / Kubernetes
- Affected components: checkout
- Evidence:
  - `techx-corp-platform/src/checkout/main.go:246-255`
  - `techx-corp-platform/src/checkout/main.go:257-269`
- Current implementation: `srv.Serve(lis)` is called before signal setup and blocks. A second `srv.Serve(lis)` appears in goroutine after signal setup, unreachable during normal run.
- Why this is a real gap: Kubernetes SIGTERM cannot trigger the intended `GracefulStop`; rollout termination can cut in-flight checkout requests.
- Failure or abuse scenario: Deployment restart while checkout request is charging/payment; process is terminated without drain.
- Business and SLO impact: Checkout errors during deploy; repeats prior deploy incident class.
- Why this matters in Phase 3: Safe rollout is part of Week 1 operational baseline.
- Recommended remediation direction: Start server in goroutine once, set signal context before serving, use termination grace period and readiness fail-before-drain.
- Runtime validation: Send SIGTERM/delete pod under load; expect graceful-stop log and no dropped in-flight requests.
- Rollback or safety constraint: Test locally and in one namespace before rollout.
- Complexity: S
- Week 1 suitability: Yes

### REL-06 — Cart data is ephemeral and expires active user carts after 60 minutes

- Severity: High
- Confidence: Confirmed
- Domain: Reliability
- Affected components: cart, Valkey
- Evidence:
  - `techx-corp-chart/values.yaml:880-900`
  - `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs:172-174`
  - `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs:196-199`
  - `docs/requirements/onboarding/INCIDENT_HISTORY.md:16-22`
- Current implementation: Valkey is single replica, no persistence config. Add/empty operations set key expiry to 60 minutes.
- Why this is a real gap: Active carts can disappear on Valkey restart or after a fixed TTL regardless customer intent.
- Failure or abuse scenario: Maintenance reschedules Valkey; customers lose carts. Long shopping session exceeds 60 minutes; cart gone.
- Business and SLO impact: Cart SLO and conversion rate drop.
- Why this matters in Phase 3: Known historical cart loss was explicitly not fully resolved.
- Recommended remediation direction: Define cart retention requirement; add durable/replicated Valkey or managed ElastiCache trade-off; review TTL.
- Runtime validation: Add cart, restart Valkey pod, check cart; test 61-minute session.
- Rollback or safety constraint: Longer TTL raises memory/cost; set retention by business need.
- Complexity: M
- Week 1 suitability: Yes for validation; remediation may need baseline/cost decision

### 4.4 Performance and Scaling

### PERF-01 — Browse product listing does N currency conversions per page load

- Severity: Medium
- Confidence: Confirmed
- Domain: Performance
- Affected components: frontend, currency
- Evidence:
  - `techx-corp-platform/src/frontend/services/ProductCatalog.service.ts:15-28`
- Current implementation: `listProducts` fetches products then `Promise.all` converts price per product unless currency is USD.
- Why this is a real gap: One browse request amplifies to one product-catalog call plus N currency calls.
- Failure or abuse scenario: Non-USD storefront traffic or load generator causes currency service saturation and frontend latency.
- Business and SLO impact: Browse p95 must stay <1s; fan-out increases p95/p99 risk.
- Why this matters in Phase 3: Browse/search has explicit SLO and high traffic weight.
- Recommended remediation direction: Avoid conversion when USD; for non-USD use batch conversion/cached rates at frontend or product list response.
- Runtime validation: Run browse load with non-USD currency; trace count of currency spans per request.
- Rollback or safety constraint: Currency correctness must remain exact enough for checkout display; do not change payment amount semantics without tests.
- Complexity: M
- Week 1 suitability: Needs runtime baseline first

### PERF-02 — Product search query is unbounded and index-hostile

- Severity: Medium
- Confidence: Confirmed
- Domain: Performance
- Affected components: product-catalog, PostgreSQL, browse/search path
- Evidence:
  - `techx-corp-platform/src/product-catalog/main.go:292-305`
  - `techx-corp-platform/src/product-catalog/main.go:346-372`
- Current implementation: Search builds `%query%`, applies `LOWER(name) LIKE` or `LOWER(description) LIKE`, orders by ID, returns all rows; no LIMIT/pagination in code.
- Why this is a real gap: Leading wildcard and lower-case expression are expensive without specialized indexes; returning all rows scales poorly.
- Failure or abuse scenario: Broad search term causes full table scan and large response; DB saturation affects checkout/catalog calls.
- Business and SLO impact: Browse/search p95 and checkout item lookup can degrade through shared PostgreSQL.
- Why this matters in Phase 3: INC-1 history involved DB saturation under peak load.
- Recommended remediation direction: Add pagination/limit and appropriate text/trigram/full-text index; rate-limit broad queries if exposed.
- Runtime validation: EXPLAIN ANALYZE search queries with realistic catalog size; load test search p95 and DB CPU.
- Rollback or safety constraint: Index creation on live DB needs migration plan and rollback.
- Complexity: M
- Week 1 suitability: Needs runtime/data baseline first

### 4.5 Cost

### COST-01 — Load generator is enabled and autostarted in default chart values

- Severity: Medium
- Confidence: Confirmed
- Domain: Cost / Performance
- Affected components: load-generator, frontend-proxy, frontend, downstream services
- Evidence:
  - `techx-corp-chart/values.yaml:498-535`
- Current implementation: `load-generator` is enabled by default, `LOCUST_AUTOSTART=true`, `LOCUST_USERS=10`, `LOCUST_BROWSER_TRAFFIC_ENABLED=true`, memory limit 1500Mi.
- Why this is a real gap: Baseline app deploy includes synthetic traffic and a large memory limit, which can distort cost/performance baselines if not intentionally used.
- Failure or abuse scenario: Team measures SLO/cost with load generator unintentionally running; CPU/memory spend and downstream load look like real traffic.
- Business and SLO impact: Cost per successful checkout and p95 latency baselines become misleading; $300/week budget decisions get skewed.
- Why this matters in Phase 3: Week 1 pitch must separate customer traffic from synthetic load and justify spend.
- Recommended remediation direction: Keep load generator available but make load profile explicit per environment; disable autostart in production-like baseline or tag synthetic traffic clearly.
- Runtime validation: Check Locust UI/logs and telemetry baggage/labels; compare resource use with load-generator disabled.
- Rollback or safety constraint: Do not remove load-generator; it is useful for validation. Control when it runs.
- Complexity: S
- Week 1 suitability: Yes

### COST-02 — Observability stack is always-on heavy footprint but non-durable

- Severity: Medium
- Confidence: Confirmed
- Domain: Cost / Observability
- Affected components: OpenSearch, Jaeger, Prometheus, Grafana, collector
- Evidence:
  - `techx-corp-chart/values.yaml:1039-1056`
  - `techx-corp-chart/values.yaml:1116-1178`
  - `techx-corp-chart/values.yaml:1213-1232`
  - `docs/requirements/onboarding/BUDGET.md:6-15`
- Current implementation: Jaeger memory 600Mi, Prometheus 400Mi, OpenSearch 1100Mi, Grafana 300Mi, collector DaemonSet 200Mi; persistence disabled for core stores.
- Why this is a real gap: The platform pays always-on resource cost but loses evidence on restart.
- Failure or abuse scenario: Observability consumes meaningful node capacity, then loses traces/logs during incident restart.
- Business and SLO impact: Budget spent without audit/recovery value; capacity pressure can affect app pods.
- Why this matters in Phase 3: CFO trade-off asks for ROI under $300/week.
- Recommended remediation direction: Define retention/SLO evidence requirement; right-size based on actual load; persist only required stores/retention.
- Runtime validation: Measure pod memory/CPU and storage after baseline load; calculate weekly cost contribution.
- Rollback or safety constraint: Do not blind-disable observability; reduce after SLO dashboards exist.
- Complexity: M
- Week 1 suitability: Needs runtime baseline first

### 4.6 Observability and Auditability

### OBS-01 — Checkout/payment/Kafka SLO alerts are missing from repo; only cart latency alert found

- Severity: High
- Confidence: Confirmed
- Domain: Observability
- Affected components: Grafana, Prometheus, checkout, payment, Kafka, PostgreSQL
- Evidence:
  - `docs/requirements/onboarding/SLO.md:4-14`
  - `techx-corp-chart/grafana/provisioning/alerting/cart-service-alerting.yml:11-23`
  - `techx-corp-chart/grafana/provisioning/alerting/cart-service-alerting.yml:91-93`
  - `techx-corp-chart/values.yaml:1118-1119`
- Current implementation: Repository provisions a cart add-item latency alert. No repo alert was found for checkout success, checkout latency, payment errors, Kafka producer failures, consumer lag, or DB saturation. Prometheus Alertmanager is disabled.
- Why this is a real gap: Stated SLOs cannot be operationally enforced without alerts and routing.
- Failure or abuse scenario: Kafka producer drops events or checkout p95 spikes; no checkout-specific alert pages on-call.
- Business and SLO impact: Error budget can burn unnoticed until customer complaints.
- Why this matters in Phase 3: Ops Review and on-call are graded deliverables.
- Recommended remediation direction: Add SLI queries and Grafana/Prometheus alerts for checkout success/latency, payment errors, Kafka lag/producer failures, PostgreSQL saturation, Valkey availability; configure receiver.
- Runtime validation: Confirm metric names/labels in live Prometheus and alert receiver delivery.
- Rollback or safety constraint: Avoid noisy alerts; start warning-only and tune thresholds from baseline.
- Complexity: M
- Week 1 suitability: Yes

### OBS-02 — Order, payment, email, AI prompts, and customer identifiers are logged/traced broadly

- Severity: Medium
- Confidence: Confirmed
- Domain: Observability / Auditability / Security
- Affected components: checkout, payment, email, product-reviews, llm, OpenSearch, Jaeger
- Evidence:
  - `techx-corp-platform/src/checkout/main.go:294-299`
  - `techx-corp-platform/src/payment/index.js:18-20`
  - `techx-corp-platform/src/email/email_server.rb:86-94`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:102-104`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:160-162`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:289-300`
- Current implementation: Logs/traces include user ID, currency, full charge request, email recipient, product question, full LLM messages, and AI response.
- Why this is a real gap: Logs/traces are routed to OpenSearch/Jaeger, which are non-durable and weakly authenticated in baseline.
- Failure or abuse scenario: Prompt or customer details become visible to anyone with observability access.
- Business and SLO impact: Privacy/audit risk and potential inability to share incident traces safely.
- Why this matters in Phase 3: AI and auditability require traceability without leaking sensitive content.
- Recommended remediation direction: Redact payment/customer/prompt fields, keep correlation IDs/order IDs, disable GenAI message content capture in prod-like mode.
- Runtime validation: Submit unique sensitive marker through checkout/AI; search OpenSearch/Jaeger.
- Rollback or safety constraint: Preserve enough identifiers for incident correlation.
- Complexity: S
- Week 1 suitability: Yes

### OBS-03 — Ownership and change-control docs contradict repository contents

- Severity: Low
- Confidence: Confirmed
- Domain: Auditability
- Affected components: repo governance, PR process
- Evidence:
  - `README.md:8-10`
  - `README.md:57-58`
  - `.github/**` scan returned no files
  - `docs/requirements/RULES.md:100-104`
- Current implementation: README references `.github/CODEOWNERS`, but no `.github` directory was present. Rules require ADR/decision log/postmortem, but repo contains no starting templates.
- Why this is a real gap: Claimed PR approval/ownership cannot be verified from repository.
- Failure or abuse scenario: Operational changes lack reviewer/owner trace; pitch claims cannot be backed by repo evidence.
- Business and SLO impact: Lower direct runtime impact, but weak auditability for Phase 3 grading.
- Why this matters in Phase 3: Deliverables explicitly include signed ADR and postmortem/COE.
- Recommended remediation direction: Add or correct CODEOWNERS path and create minimal ADR/runbook/postmortem templates after this report if allowed.
- Runtime validation: Check remote repo branch protections and GitHub CODEOWNERS.
- Rollback or safety constraint: None; documentation/process only.
- Complexity: S
- Week 1 suitability: Yes

### 4.7 AI Safety, Quality, and Cost

### AI-01 — Product-review AI captures and logs customer prompt/content by default

- Severity: High
- Confidence: Confirmed
- Domain: AI / Security / Observability
- Affected components: product-reviews, llm, collector, OpenSearch, Jaeger
- Evidence:
  - `techx-corp-chart/values.yaml:624-625`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:102-104`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:160-162`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:227-241`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:289-300`
  - `techx-corp-platform/src/llm/app.py:93-98`
- Current implementation: `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true`. Service logs question, full response message, tool args, full messages sent to LLM, and final response. Mock LLM logs request messages.
- Why this is a real gap: Customer prompt/review content enters telemetry/logs by default.
- Failure or abuse scenario: User asks AI with sensitive info; content is stored in OpenSearch/Jaeger and visible through anonymous Grafana/OpenSearch boundary.
- Business and SLO impact: Privacy and trust risk; incident data cannot be broadly shared.
- Why this matters in Phase 3: AIE must handle prompt/content safely before real LLM.
- Recommended remediation direction: Disable content capture in prod-like values, redact logs, keep structured non-sensitive metrics: request count, model, latency, error type, token count.
- Runtime validation: Ask AI with unique marker; search logs/traces.
- Rollback or safety constraint: Keep debug overlay for controlled local dev only.
- Complexity: S
- Week 1 suitability: Yes

### AI-02 — AI answer path lacks normal LLM fallback, eval gate, and cost tracking for real model overlay

- Severity: High
- Confidence: Confirmed
- Domain: AI
- Affected components: product-reviews, llm, real LLM overlay
- Evidence:
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:186-200`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:216-223`
  - `techx-corp-platform/src/product-reviews/product_reviews_server.py:268-294`
  - `deploy/values-aio-llm.yaml:4-10`
  - `techx-corp-platform/src/llm/app.py:153-187`
- Current implementation: Rate-limit injection branch has a fallback message, but normal `client.chat.completions.create` calls are not wrapped with timeout/429/unavailable fallback. `llmInaccurateResponse` can request inaccurate output. Real model overlay swaps endpoint/model/key but adds no eval criteria, token-cost export, or quality gate.
- Why this is a real gap: SLO says AI is best-effort but must not show misleading summary. Current path can fail hard or display unverified answer.
- Failure or abuse scenario: Real LLM times out/429s; gRPC handler errors. Inaccurate-response flag returns wrong customer-facing content without disclaimer/fallback.
- Business and SLO impact: Customer trust and AI-quality expectation violated; cost can grow without per-request tracking.
- Why this matters in Phase 3: AIO work must prove quality, safety, and cost of AI feature.
- Recommended remediation direction: Add eval set, confidence/fallback policy, bounded timeout, 429/unavailable UX, token/cost metrics, and response validation against tool facts. Do not remove protected flags; make service resilient to them.
- Runtime validation: Enable `llmRateLimitError`/`llmInaccurateResponse`; point overlay to real or failing endpoint; inspect UX, metrics, logs, cost.
- Rollback or safety constraint: Keep mock baseline; real model overlay should be opt-in with Secret.
- Complexity: M
- Week 1 suitability: Yes

## 5. Runtime Validation Required

| Concern | Why static evidence is insufficient | Validation |
|---|---|---|
| Public exposure of `frontend-proxy`, Grafana, Jaeger, OpenSearch | Chart has no enabled Ingress/LoadBalancer, but cluster may add exposure outside repo | `kubectl get ingress,svc -A`; cloud LB inventory; attempt unauthenticated access |
| Effective pod QoS/admission with `deploy/quota.yaml` | Kubernetes defaulting/LimitRange may alter requests | Apply in test namespace or `kubectl apply --dry-run=server`; inspect pod resources |
| Stateful data survival | Static chart shows no persistence, but cluster/operator may inject volumes | Create order/cart, restart pods, verify data and offsets |
| SLO metric labels and dashboard correctness | Metrics names/labels depend runtime instrumentation | Query Prometheus for checkout/cart/browse/AI SLI labels |
| Alert routing | Grafana receiver name exists but actual channel delivery unknown | Fire test alert and confirm on-call channel/email |
| DB connection-pool saturation | Code uses default Go/psycopg2/EF settings; live limits depend DB and load | Load test, inspect DB stats, pool metrics, timeouts |
| Real AI provider behavior/cost | Overlay is optional and provider/model-specific | Enable overlay with test key, measure latency, 429s, token usage, cost |
| AWS cost guardrails | Repository has no AWS Budgets/IaC evidence | Check AWS Budgets, Cost Explorer tags, anomaly detection |
| IAM/IRSA boundary | Chart SA annotations empty, but cluster/node IAM unknown | Inspect service accounts, node role, IRSA, CloudTrail |

## 6. Consolidated Risk Register

| ID | Severity | Confidence | Gap | Evidence | Customer/Business Impact | SLO Impact | Recommended Direction |
|---|---|---|---|---|---|---|---|
| SEC-01 | High | Confirmed | Anonymous Grafana Admin and OpenSearch security disabled | `values.yaml:1186-1192`, `1221-1228` | observability tamper/data exposure | incident/SLO evidence unreliable | auth + isolation + persistence |
| SEC-02 | High | Confirmed | Static DB credentials | `values.yaml:181-184`, `581-582`, `618-619`, `866-870` | data compromise/corruption | DB outage/incident scope grows | Secrets + least privilege + rotation |
| SEC-03 | Medium | Confirmed | weak container hardening | `values.yaml:35-37`, component security contexts | compromise blast radius | indirect | global hardening baseline |
| SEC-04 | Medium | Confirmed | client-controlled cart userId | `cart.ts:33-45` | cart loss/abuse | cart success impacted | server-derived session/cart ID |
| K8S-01 | High | Confirmed | probes supported but unset | `_objects.tpl:72-79`, `values.yaml:151-154` | rollout sends traffic to bad pods | checkout/cart/payment errors | add tuned probes |
| K8S-02 | High | Confirmed | single replicas, no HPA/PDB | `values.yaml:26-28`, no HPA/PDB | pod/node drain outage | all SLOs | stateless replicas + PDB + HPA after requests |
| K8S-03 | Medium | Runtime validation required | incomplete resources/quota mismatch | `deploy/quota.yaml:4-9`, memory-only limits | deploy/admission or CPU contention | latency/errors | set measured requests/limits |
| K8S-04 | Critical | Confirmed | data stores non-persistent Deployments | `_objects.tpl:3-7`, data store values | data loss | cart/checkout/audit | managed or StatefulSet+PVC+backup |
| REL-01 | Critical | Confirmed | checkout success despite Kafka loss | `producer.go:38-41`, `main.go:384-392` | accounting/fraud missing orders | checkout success misleading | acks + outbox/retry |
| REL-02 | Critical | Confirmed | accounting auto-commit data loss | `Consumer.cs:65-67`, `131-148` | lost accounting records | audit gap | commit after DB transaction |
| REL-03 | High | Confirmed | partial checkout no idempotency | `main.go:328-388` | duplicate charge/ship/cart dirty | checkout errors/support | idempotency + state/outbox |
| REL-04 | High | Confirmed | no dependency deadlines | `main.go:441-585` | dependency slowness cascades | checkout latency/success | timeout budget + safe retries |
| REL-05 | High | Confirmed | checkout graceful shutdown unreachable | `main.go:246-269` | deploy drops requests | checkout errors | fix serve/signal flow |
| REL-06 | High | Confirmed | cart ephemeral + 60m TTL | `ValkeyCartStore.cs:172-174`, `196-199` | lost carts | cart SLO | durability/retention decision |
| PERF-01 | Medium | Confirmed | N currency fan-out | `ProductCatalog.service.ts:15-28` | slow browse | browse p95 | batch/cache conversion |
| PERF-02 | Medium | Confirmed | unbounded index-hostile search | `product-catalog/main.go:292-305` | DB saturation | browse/search p95 | limit + index + pagination |
| COST-01 | Medium | Confirmed | load-generator autostarts | `values.yaml:498-535` | distorted cost/load | noisy baseline | explicit load env/profile |
| COST-02 | Medium | Confirmed | heavy non-durable observability | `values.yaml:1039-1232` | spend without retention | indirect | right-size + required retention |
| OBS-01 | High | Confirmed | missing checkout/payment/Kafka alerts | `SLO.md:4-14`, `cart-service-alerting.yml:11-23`, `values.yaml:1118-1119` | late incident detection | error budget burn | SLO dashboards + routed alerts |
| OBS-02 | Medium | Confirmed | sensitive logs/traces | checkout/payment/email/AI refs | privacy/audit risk | indirect | redact, keep correlation IDs |
| OBS-03 | Low | Confirmed | CODEOWNERS/templates missing | `README.md:8-10`, no `.github/**` | weak governance | none direct | add process artifacts |
| AI-01 | High | Confirmed | prompt/content telemetry capture | `values.yaml:624-625`, AI logs | privacy leak | AI trust | disable/redact content capture |
| AI-02 | High | Confirmed | no AI eval/fallback/cost gate | `product_reviews_server.py:216-294`, `values-aio-llm.yaml:4-10` | wrong/failed AI answers | AI quality expectation | eval + fallback + token metrics |

## 7. Week 1 Prioritized Backlog

| Priority | Work Item | Finding IDs | Why This Is Correct Priority | Expected Outcome | Complexity | Requires Runtime Baseline? | Validation | Rollback |
|---|---|---|---|---|---|---|---|---|
| P0 | Prove and protect order-event integrity | REL-01, REL-02 | Checkout success with missing accounting/fraud is highest revenue/audit risk | known behavior under Kafka/DB failure; producer/consumer fix plan | M | No for static; yes for proof | stop Kafka/DB, place order, compare UI/topic/DB | revert producer/consumer config; replay topic if needed |
| P0 | Add checkout/cart/payment/frontend/product-catalog readiness + rollout validation | K8S-01, K8S-02, REL-05 | Prior incident class and cheap risk reduction | safe rollout evidence for pitch | M | Yes | rollout restart under Locust checkout load | Helm rollback values/code |
| P0 | Build SLO dashboard/alerts for checkout/cart/browse/payment/Kafka/DB | OBS-01, REL-01, REL-02 | Cannot manage 99% checkout without measurement | live SLI queries and routed alerts | M | Yes | fire test alerts; compare traces/logs | revert dashboards/alerts |
| P1 | Validate data durability for Valkey/PostgreSQL/Kafka and pick Week 2 path | K8S-04, REL-06 | Data loss is critical but remediation cost/architecture trade-off matters | evidence table: restart/drain results + managed/PVC cost trade-off | M | Yes | restart pods after writes; inspect persistence | no config change unless approved |
| P1 | Add checkout dependency timeout budget and partial-failure metrics | REL-03, REL-04 | Stops slow dependencies from consuming checkout SLO; metrics expose partial states | bounded failure, dependency error breakdown | M | Yes for timeout values | inject slow shipping/payment | revert timeout values/code |
| P1 | Secure observability access and persistence decision | SEC-01, COST-02 | Observability is incident evidence and admin plane | no anonymous admin in shared/prod path; retention decision | M | Yes | unauthenticated access test; restart retention test | break-glass admin + Helm rollback |
| P1 | Redact AI/prompt/payment/customer telemetry | AI-01, OBS-02, SEC-01 | Fast privacy risk reduction before real LLM | no prompt/payment/email content in logs/traces | S | Yes | submit marker and search logs/traces | debug-only overlay restores capture |
| P1 | Add AI fallback/eval/cost baseline before real model | AI-02 | SLO says no misleading AI; AIO overlay currently only swaps model/key | eval checklist, fallback UX, token/cost metrics | M | Yes | 429/timeout/inaccurate flag tests | revert to mock LLM |
| P2 | Fix cart API ownership/quantity validation | SEC-04, REL-03 | Prevents cart abuse and bad order quantities | server-side session validation and quantity bounds | S | No | negative quantity/cross-cart tests | revert API handler |
| P2 | Right-size resources and load-generator behavior | K8S-03, COST-01 | Cost/perf needs data; load-generator can skew baseline | measured requests/limits and explicit load profile | M | Yes | Prometheus/Grafana resource metrics, quota admission test | revert values |
| P2 | Search/browse performance improvements | PERF-01, PERF-02 | Meaningful but after revenue/integrity controls | fewer fan-out calls, bounded search | M | Yes | trace fan-out, EXPLAIN ANALYZE | revert code/index migration |
| P2 | Restore repo auditability artifacts | OBS-03 | Required for deliverables, low runtime risk | CODEOWNERS/templates/decision log | S | No | GitHub branch protection/CODEOWNERS check | revert docs/config |

## 8. Items Explicitly Not Prioritized Yet

- Full managed-service migration to RDS/ElastiCache/MSK: likely correct long-term, but needs cost, directive, backup/restore, and downtime trade-off evidence first.
- Broad service mesh/mTLS: security value exists, but current top risks are unauthenticated admin surfaces, static DB creds, and NetworkPolicy/data-store access. Mesh comes after baseline hardening.
- HPA everywhere: unsafe before CPU/memory requests, probes, and SLO metrics exist.
- Multi-AZ for all stateful services: may exceed $300/week; first prove data-loss behavior and revenue/audit impact.
- Rewriting checkout saga/orchestration: needed for robust idempotency, but Week 1 can first add evidence, timeouts, metrics, and order-event safeguards.
- Removing or bypassing flagd/OpenFeature/fault injection: explicitly not allowed. All recommendations preserve protected mechanism and add resilience around exposed failure modes.

## 9. Cross-Check Against Existing Exploration Document

| Existing Claim | Status | Evidence | Notes |
|---|---|---|---|
| Checkout calls many dependencies sequentially; one dependency failure can fail checkout | Confirmed | `checkout/main.go:313-344`, `453-607` | Refined with partial-success/payment-after-failure risk |
| Default `replicas: 1`; no HPA/PDB | Confirmed | `values.yaml:26-28`; no HPA/PDB templates found | High for stateless revenue path; data stores need special handling |
| PostgreSQL, Valkey, Kafka single in-cluster | Confirmed | `values.yaml:782-888` | Refined to persistence/Deployment evidence |
| Prometheus, OpenSearch, Jaeger lack persistence | Confirmed | `values.yaml:1039-1043`, `1172-1174`, `1220-1228` | Confirmed non-durable observability |
| AI default uses mock LLM and has inaccurate/rate-limit flags | Confirmed | `values.yaml:600-609`, `product_reviews_server.py:163-200`, `268-278` | Added missing fallback/eval/cost evidence |
| Grafana anonymous Admin, OpenSearch security disabled | Confirmed | `values.yaml:1186-1195`, `1227-1228` | Severity depends on runtime exposure; internal risk confirmed |
| LLM key uses Kubernetes Secret | Refined | `deploy/values-aio-llm.yaml:9-10`; baseline `values.yaml:600-601` | Only true when AIO overlay is used; baseline has dummy literal |
| Kafka producer acknowledgement needs verification | Refined | `checkout/kafka/producer.go:38-41` | Source proves unsafe `NoResponse`; runtime verifies impact |
| No Terraform/CDK for EKS/VPC/IAM/etc. | Runtime-only / not prioritized | repo scan | Absence of IaC in repo is not a runtime weakness by itself without account evidence |
| Need AWS Budgets + Cost Anomaly Detection | Runtime-only | `BUDGET.md:17-21` | Required to check in AWS account, not proven by app repo |
| ResourceQuota exists | Confirmed but limited | `deploy/quota.yaml:4-9` | It is sample/manual and may conflict with missing CPU requests/limits |
| Search query may be slow | Confirmed | `product-catalog/main.go:292-305` | Actual query is unbounded `%LOWER LIKE%` |
| Alert only for cart latency | Confirmed/refined | `cart-service-alerting.yml:11-23`; grep found no checkout/payment/Kafka alerts | Alert threshold and receiver need runtime validation |
| Build/deploy docs align with ECR | Refined | `GETTING_STARTED.md:26-33`; `deploy/build-push-images.sh:1-3`, `21` | Script comments/output still mention Docker Hub/public |

## 10. Appendix

### Full file list reviewed

Primary files read or searched:

- `README.md`
- `docs/requirements/RULES.md`
- `docs/requirements/GETTING_STARTED.md`
- `docs/requirements/mandates/README.md`
- `docs/requirements/onboarding/ARCHITECTURE.md`
- `docs/requirements/onboarding/SLO.md`
- `docs/requirements/onboarding/BUDGET.md`
- `docs/requirements/onboarding/INCIDENT_HISTORY.md`
- `docs/requirements/onboarding/PITCH_GUIDE.md`
- `docs/notes/phase3-pre-system-exploration.md`
- `deploy/build-push-images.sh`
- `deploy/quota.yaml`
- `deploy/values-aio-llm.yaml`
- `deploy/values-app-stamp.yaml`
- `deploy/values-flagd-sync.yaml`
- `deploy/values-observability.yaml`
- `techx-corp-chart/values.yaml`
- `techx-corp-chart/templates/component.yaml`
- `techx-corp-chart/templates/_objects.tpl`
- `techx-corp-chart/templates/_pod.tpl`
- `techx-corp-chart/templates/serviceaccount.yaml`
- `techx-corp-chart/grafana/provisioning/alerting/cart-service-alerting.yml`
- `techx-corp-chart/grafana/provisioning/dashboards/*.json`
- `techx-corp-platform/README.md`
- `techx-corp-platform/src/checkout/main.go`
- `techx-corp-platform/src/checkout/kafka/producer.go`
- `techx-corp-platform/src/cart/src/cartstore/ValkeyCartStore.cs`
- `techx-corp-platform/src/cart/src/services/CartService.cs`
- `techx-corp-platform/src/accounting/Consumer.cs`
- `techx-corp-platform/src/fraud-detection/src/main/kotlin/frauddetection/main.kt`
- `techx-corp-platform/src/product-catalog/main.go`
- `techx-corp-platform/src/product-reviews/product_reviews_server.py`
- `techx-corp-platform/src/product-reviews/database.py`
- `techx-corp-platform/src/llm/app.py`
- `techx-corp-platform/src/payment/index.js`
- `techx-corp-platform/src/payment/charge.js`
- `techx-corp-platform/src/email/email_server.rb`
- `techx-corp-platform/src/shipping/src/shipping_service.rs`
- `techx-corp-platform/src/frontend/pages/api/cart.ts`
- `techx-corp-platform/src/frontend/services/ProductCatalog.service.ts`
- `techx-corp-platform/src/frontend-proxy/envoy.tmpl.yaml`

Searches also covered TODO/FIXME/default/insecure/anonymous/disabled, probes/resources/replicas/persistence, HPA/PDB/NetworkPolicy/RBAC, timeout/retry/idempotency/Kafka, eval/token/cost/guardrail, CODEOWNERS/ADR/audit/Budgets, and search/proto implementation references.

### Open questions for AWS/EKS runtime validation

1. What namespace, region, EKS version, node groups, instance types, AZ spread, and autoscaler/Karpenter settings are used?
2. Is `frontend-proxy` exposed by LoadBalancer/Ingress, or only port-forward?
3. Are there cluster-level NetworkPolicies, Pod Security Admission, LimitRanges, or mutating policies not in repo?
4. Does any external storage class/PVC injection exist for PostgreSQL, Kafka, Valkey, Prometheus, Jaeger, or OpenSearch?
5. What IAM permissions do nodes/service accounts have? Any IRSA annotations outside chart?
6. Are AWS Budgets, Cost Anomaly Detection, and tagging enabled for TF4?
7. What Prometheus labels represent checkout success, cart success, storefront p95, AI errors, Kafka lag, DB saturation?
8. Does Grafana `grafana-default-email` receiver deliver to real on-call?
9. Do logs/traces contain payment/card request bodies, email, prompt content, or review text in live OpenSearch/Jaeger?
10. What real LLM provider/model/rate limits/token prices are planned for `values-aio-llm.yaml`?

### Opus subagent findings incorporated

Incorporated and manually re-checked:

- Kafka `RequiredAcks = sarama.NoResponse` plus checkout success despite event publish failure.
- Accounting auto-commit with swallowed DB/process exceptions.
- Checkout graceful shutdown unreachable due blocking `Serve` before signal setup.
- Missing explicit checkout dependency deadlines.
- Valkey/PostgreSQL/Kafka single-replica non-persistent data-store risks.
- Single replica/no probe/no HPA/PDB rollout safety gap.
- Grafana anonymous Admin/OpenSearch disabled security/non-durable observability.
- AI prompt capture/inaccurate response path.

Rejected or downgraded from subagent/exploration:

- “Missing Terraform/CDK” as a finding: kept runtime-only because repository scope may intentionally exclude AWS account IaC.
- “All pods BestEffort because requests missing”: not used. Memory limits may default memory requests depending admission, but CPU requests/limits are still missing and quota behavior needs runtime validation.
- “No search implementation exists”: rejected. `product-catalog` implements `SearchProducts`; retained performance issue for unbounded `%LOWER LIKE%` search instead.
- “LLM key uses Secret” as baseline: refined. Secret use only exists in optional AIO overlay; baseline uses dummy literal.
