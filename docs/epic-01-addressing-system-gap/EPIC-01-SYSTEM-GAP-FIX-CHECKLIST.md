# EPIC-01: System Gap Fix Checklist

Epic: System Gap Assessment &amp; Remediation Plan

Goal: fix or mitigate highest-risk TechX baseline gaps from `docs/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` before Week 1 Pitch, with evidence per completed task.

Evidence folder for completed fixes:

`./docs/evidence/epic-01`

File numbering rule:

- First completed task: `001-<finding-or-task-slug>.md`
- Next completed task: `002-<finding-or-task-slug>.md`
- Increase by 1 for each fixed checklist item.
- Evidence filenames below are suggested if fixing in checklist order. If fixing in different order, use next available number.
- Keep typo path `evidence` because requested path uses it.

Done rule:

- Do not mark task Done without evidence file.
- If fix exists but evidence missing, task stays In Review.
- Evidence must show work done, current result, proof location, and remaining follow-up/risk/assumption.
- Because system is not live yet, mark implemented items as not live-verified in checklist/evidence until go-live recheck is possible.

## Fix Checklist

### P0 — Revenue/audit integrity

- [x] `REL-01` Fix checkout Kafka producer acknowledgement and publish result handling.
  - Target: checkout must not silently succeed when order event is not acknowledged or recoverable.
  - Evidence file: `001-rel-01-checkout-kafka-order-event-integrity.md`
  - Validation: Kafka outage/failure test, checkout response/result, topic offsets/logs.
  - Status: implemented, not live-verified yet because system is not Go live.

- [x] `REL-02` Fix accounting consumer commit semantics.
  - Target: accounting commits Kafka offsets only after durable DB write or explicit quarantine path.
  - Evidence file: `002-rel-02-accounting-manual-commit-after-db-write.md`
  - Validation: broken DB connection test, consumer offset behavior, accounting table/logs.
  - Status: implemented, not live-verified yet because system is not Go live.

### P0 — Rollout safety

- [ ] `REL-05` Fix checkout graceful shutdown flow.
  - Target: server starts once, signal handling works, in-flight checkout drains on SIGTERM.
  - Evidence file: `003-rel-05-checkout-graceful-shutdown.md`
  - Validation: local/unit run or pod SIGTERM/delete under request load.

- [ ] `K8S-01` Add readiness/liveness probes for revenue path services.
  - Target: checkout, cart, payment, frontend, product-catalog have safe baseline probes.
  - Evidence file: `004-k8s-01-revenue-path-probes.md`
  - Validation: rendered manifests and rollout restart behavior.

- [ ] `K8S-02` Add safe stateless replica/PDB baseline where probes/resources allow.
  - Target: reduce single-pod disruption risk for stateless revenue services. Do not scale stateful stores blindly.
  - Evidence file: `005-k8s-02-stateless-replica-pdb-baseline.md`
  - Validation: rendered manifests, `kubectl get deploy,pdb`, disruption test if cluster available.

### P0 — Observability baseline

- [ ] `OBS-01` Add checkout/payment/Kafka/DB SLO alerts or dashboard queries.
  - Target: checkout success/latency, payment error, Kafka producer/consumer, DB saturation signals exist.
  - Evidence file: `006-obs-01-slo-alert-dashboard-baseline.md`
  - Validation: rendered Grafana/Prometheus config, live query screenshots/logs if runtime available.

### P1 — Data durability and checkout containment

- [ ] `K8S-04` / `REL-06` Validate data-store restart behavior and document Week 2 durability path.
  - Target: evidence table for Valkey/PostgreSQL/Kafka persistence behavior and recommended managed/PVC path.
  - Evidence file: `007-k8s-04-rel-06-data-durability-validation.md`
  - Validation: create cart/order, restart pod, compare data/offsets/history.

- [ ] `REL-04` Add checkout dependency timeout budget.
  - Target: bounded dependency calls and dependency-specific failure metrics; no unsafe retries before idempotency.
  - Evidence file: `008-rel-04-checkout-dependency-timeout-budget.md`
  - Validation: slow shipping/payment injection, checkout latency/error behavior.

- [ ] `REL-03` Document partial-success/idempotency design before broad compensation work.
  - Target: clear backlog/ADR for idempotency key, order state, outbox, compensation semantics.
  - Evidence file: `009-rel-03-checkout-idempotency-follow-up.md`
  - Validation: decision log/ADR link and current risk statement.
  - Deferred from REL-01 QA:
    - H1: Kafka publish fail after charge/shipping → partial-success not rollback-able. Needs idempotency key + outbox.
    - M1: `WaitForAll` + retries without idempotent producer → at-least-once duplicates possible. Needs `Producer.Idempotent = true`.
  - Validation: decision log/ADR link and current risk statement.

### P1 — Security/privacy/AI safety

- [ ] `SEC-01` Secure observability access baseline or document runtime exposure limits.
  - Target: no anonymous admin in shared/prod-like path; OpenSearch exposure/isolation decision recorded.
  - Evidence file: `010-sec-01-observability-access-baseline.md`
  - Validation: unauthenticated Grafana/OpenSearch test or rendered values.

- [ ] `SEC-02` Move static DB credentials toward Kubernetes Secrets and rotation plan.
  - Target: committed plaintext DB credentials/connection strings are removed from prod-like values or isolated behind Secret references with staged rotation notes.
  - Evidence file: `011-sec-02-static-db-credentials-secret-baseline.md`
  - Validation: rendered manifests reference Secrets, app config still resolves expected DB env/connection values.

- [ ] `SEC-03` Add compatible container hardening baseline.
  - Target: workloads use least-privilege container security settings where compatible; unsafe settings documented as exceptions.
  - Evidence file: `012-sec-03-container-hardening-baseline.md`
  - Validation: rendered pod securityContext/container securityContext values, smoke test for services that need writable paths.

- [ ] `AI-01` / `OBS-02` Redact AI prompt/payment/customer telemetry.
  - Target: prompt/message/payment/customer content absent from prod-like logs/traces; correlation IDs remain.
  - Evidence file: `013-ai-01-obs-02-telemetry-redaction.md`
  - Validation: unique marker test and OpenSearch/Jaeger/log search if runtime available.

- [ ] `AI-02` Add AI fallback/eval/cost baseline before real model overlay.
  - Target: timeout/429/unavailable fallback, eval checklist, token/cost metric plan.
  - Evidence file: `014-ai-02-ai-fallback-eval-cost-baseline.md`
  - Validation: rate-limit/inaccurate/failing endpoint tests, eval file/log output.

### P2 — Smaller safe fixes

- [ ] `SEC-04` Fix cart API trust boundary and validation.
  - Target: cart mutation identity derived server-side where possible; quantities/item IDs validated.
  - Evidence file: `015-sec-04-cart-api-ownership-validation.md`
  - Validation: cross-cart mutation attempt, invalid quantity tests.

- [ ] `COST-01` Make load-generator behavior explicit per environment.
  - Target: production-like baseline does not autostart synthetic load unintentionally.
  - Evidence file: `016-cost-01-load-generator-explicit-profile.md`
  - Validation: rendered env values and telemetry/load-generator state.

- [ ] `COST-02` Baseline observability cost and retention trade-off.
  - Target: always-on observability footprint is measured or documented, and persistence/retention/right-sizing decision is explicit.
  - Evidence file: `017-cost-02-observability-footprint-retention.md`
  - Validation: rendered resource values, runtime CPU/memory/storage if available, retention/persistence decision link.

- [ ] `K8S-03` Add measured resource baseline or quota compatibility note.
  - Target: requests/limits plan based on runtime data; quota admission status clear.
  - Evidence file: `018-k8s-03-resource-quota-baseline.md`
  - Validation: Prometheus/Grafana resource metrics, server dry-run/apply result, rendered resources.

- [ ] `OBS-03` Restore repo auditability artifacts.
  - Target: CODEOWNERS path mismatch fixed or documented; ADR/runbook/postmortem templates added if allowed.
  - Evidence file: `003-obs-03-repo-auditability-artifacts.md`
  - Validation: file links and GitHub branch protection/CODEOWNERS check if available.
  - Status: PR opened with templates and destination folders, pending GitHub CODEOWNERS check and merge.

- [ ] `PERF-01` / `PERF-02` Fix or baseline browse/search performance.
  - Target: avoid N currency fan-out where safe and bound search with pagination/index plan.
  - Evidence file: `020-perf-01-perf-02-browse-search-performance.md`
  - Validation: trace fan-out count, `EXPLAIN ANALYZE`, browse/search p95.

## Evidence File Template

Copy this into each numbered evidence file under:

`./docs/evidence/epic-01`

```markdown
# EPIC-01 Evidence — <TASK ID>: <Task title>

EVIDENCE UPDATE

## Đã làm gì?

- <Mô tả ngắn gọn phần việc đã hoàn thành.>
- <Nêu rõ đã cập nhật diagram, tài liệu, config hoặc phần architecture nào.>

## Kết quả hiện tại

- <Kết quả sau khi làm là gì?>
- <Task đã đáp ứng acceptance criteria nào?>
- <Assumption hoặc giới hạn cần ghi nhận nếu có.>

## Bằng chứng nằm ở đâu?

- Link/file diagram: <path/link hoặc N/A>
- Screenshot: <path/link hoặc N/A>
- Command output/log nếu có: <path/link hoặc inline summary>
- PR/commit/link nếu có: <link hoặc N/A>
- Folder lưu evidence: `./docs/evidence/epic-01`

## Ghi chú / Follow-up

- <Điểm cần team review thêm nếu có.>
- <Bug, risk hoặc backlog phát sinh nếu có.>
- <Quyết định cần ghi vào ADR/ACR/Decision Log nếu có.>
```

## Implementation Rule

After every fixed item:

1. Run smallest relevant validation.
2. Create next numbered evidence markdown file in epic evidence folder.
3. Include exact file paths, command output/log summary, and remaining risk.
4. Only then mark checklist item Done.

