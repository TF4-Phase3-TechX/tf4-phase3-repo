📊 EPIC-01 SYSTEM GAP ASSESSMENT — MASTER SUMMARY

Đã hoàn thành phân tích toàn bộ 21 lỗ hổng trong baseline TechX Phase 3.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 SOURCE DOCUMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Gap Assessment (789 dòng, 10 sections):


  tf4-phase3-repo/docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md at main · TF4-Phase3-TechX/tf4-phase3-repo 

Fix Checklist (21 items, evidence template):


  tf4-phase3-repo/docs/epic-01-addressing-system-gap/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md at main · TF4-Phase3-TechX/tf4-phase3-repo 

Gap → Pillar → Nhóm Mapping:




━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 TỔNG HỢP PHÂN LOẠI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Severity

Count

IDs

🔴 Critical

3

REL-01, REL-02, K8S-04

🟠 High

10

SEC-01,02 / K8S-01,02 / REL-03,04,05,06 / OBS-01 / AI-01,02

🟡 Medium

7

SEC-03,04 / K8S-03 / PERF-01,02 / COST-01,02 / OBS-02

🟢 Low

1

OBS-03

By Domain:

Security:         4 gaps (SEC-01→04)

K8s/Helm:         4 gaps (K8S-01→04)

Reliability/Data: 6 gaps (REL-01→06)

Performance:      2 gaps (PERF-01,02)

Cost:             2 gaps (COST-01,02)

Observability:    3 gaps (OBS-01→03)

AI Safety:        2 gaps (AI-01,02)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ TOP 5 RỦI RO CAO NHẤT (Business/SLO Impact)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REL-01 🔴 Checkout success ngay cả khi Kafka order event bị mất
→ Accounting/Fraud không nhận order → đứt audit trail, thất thoát revenue

REL-02 🔴 Accounting auto-commit offset trước DB write
→ Mất order accounting record → không thể reconciliation

K8S-04 🔴 PG/Valkey/Kafka là Deployment, không PVC/StatefulSet
→ Mất toàn bộ data khi pod restart

K8S-01+K8S-02+REL-05 🟠 Single replica, no probes, broken graceful shutdown
→ Rollout mất capacity revenue path

AI-01+AI-02 🟠 Prompt capture trong telemetry + không AI fallback/eval
→ Privacy risk + khách thấy AI answer sai

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 PHÂN CÔNG THEO NHÓM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Nhóm

Pillar(s)

Gaps (Primary)

Severity

CDO-08

Security + Reliability

13 gaps

🔴×3 🟠×8 🟡×2

CDO-04

Perf + Cost

5 gaps

🟡×5

CDO-07

Auditability

3 owned + verify all evidence

🟠×1 🟡×1 🟢×1

AIO-01

AI Safety & Quality

2 gaps

🟠×2

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 WEEK 1 PRIORITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
P0 — Revenue/Audit Integrity + Rollout Safety:
  ✅ REL-01, REL-02: Fix Kafka producer/consumer integrity
  ✅ K8S-01, K8S-02, REL-05: Probes + replicas + graceful shutdown
  ✅ OBS-01: SLO dashboards/alerts

P1 — Data Durability + Security/Privacy + AI:
  ⏳ K8S-04, REL-06: Validate data durability
  ⏳ REL-03, REL-04: Timeout budget + idempotency ADR
  ⏳ SEC-01, SEC-02: Observability auth + Secrets migration
  ⏳ AI-01, AI-02: Telemetry redaction + AI fallback/eval

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 EVIDENCE RULE (cứng)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mỗi fix PHẢI CÓ evidence file trong:


  tf4-phase3-repo/docs/evidence/epic-01 at main · TF4-Phase3-TechX/tf4-phase3-repo 

Format: {NNN}-{slug}.md (đánh số tăng dần 001, 002, ...)

Template: xem checklist section "Evidence File Template"

KHÔNG đánh dấu Done nếu thiếu evidence

CDO-07 (Auditability) là backstop verify toàn bộ evidence

Chi tiết từng nhóm → xem các comment khác ở Task này






Truong An

5 hours ago
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@CDO-08 — SCOPE: SECURITY + RELIABILITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Các bạn sở hữu 13/21 gaps — nhiều nhất team, vì Reliability nắm revenue-critical path và Security nắm auth/credentials.

📁 Docs gốc cần đọc:

Gap Assessment: tf4-phase3-repo/docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md at main · TF4-Phase3-TechX/tf4-phase3-repo 

Gap → Pillar Map: https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/GAP-TO-PILLAR-MAPPING.md#32-reliability-pillar--cdo-08Connect your Github account 

Checklist: tf4-phase3-repo/docs/epic-01-addressing-system-gap/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md at main · TF4-Phase3-TechX/tf4-phase3-repo

━━━━━━━━━━━━━━━━━━━
🔴 CRITICAL — FIX NGAY (P0)
━━━━━━━━━━━━━━━━━━━

□ REL-01 — Checkout Kafka producer dùng sarama.NoResponse
  → Fix: WaitForAll + bounded timeout + failure metric
  → Evidence: 001-rel-01-checkout-kafka-order-event-integrity.md
  → Impact: Checkout success với missing accounting/fraud → đứt audit trail

□ REL-02 — Accounting consumer EnableAutoCommit=true, catch-all exception chỉ log
  → Fix: Disable auto-commit, chỉ commit sau DB write thành công, dead-letter path
  → Evidence: 002-rel-02-accounting-manual-commit-after-db-write.md
  → Impact: Mất order accounting record nếu DB down

□ REL-05 — Checkout gọi srv.Serve() 2 lần, graceful shutdown code unreachable
  → Fix: Start server 1 lần trong goroutine, signal context trước Serve
  → Evidence: 003-rel-05-checkout-graceful-shutdown.md
  → Impact: Deploy cắt in-flight checkout → mất order đang thanh toán

□ K8S-01 — Helm hỗ trợ probes nhưng values set none
  → Fix: Thêm readiness/liveness probes cho checkout/cart/payment/frontend/product-catalog
  → Evidence: 004-k8s-01-revenue-path-probes.md
  → Impact: Rollout gửi traffic đến pod chưa ready → checkout error

□ K8S-02 — Single replica toàn bộ service, không HPA/PDB
  → Fix: 2 replicas cho stateless revenue services + PDB baseline
  → Evidence: 005-k8s-02-stateless-replica-pdb-baseline.md
  → ⚠️ Cần CDO-04 review resource increase impact

━━━━━━━━━━━━━━━━━━━
🟠 HIGH — FIX SỚM (P1)
━━━━━━━━━━━━━━━━━━━

□ REL-04 — Checkout không có dependency timeout budget
  → Fix: context.WithTimeout per dependency, failure metrics by dependency
  → Evidence: 008-rel-04-checkout-dependency-timeout-budget.md
  → ⚠️ Cần CDO-04 cung cấp p95 baseline data

□ SEC-01 — Grafana anonymous Admin + OpenSearch DISABLE_SECURITY_PLUGIN=true
  → Fix: Disable anonymous, reduce role → Viewer, enable OpenSearch security
  → Evidence: 010-sec-01-observability-access-baseline.md
  → ⚠️ Cần CDO-07 verify no unauthenticated access còn sót

□ SEC-02 — DB credentials plaintext trong values.yaml (root/otel/otelp)
  → Fix: Kubernetes Secrets, split user per service privilege, rotation plan
  → Evidence: 011-sec-02-static-db-credentials-secret-baseline.md
  → ⚠️ Cần CDO-07 verify no plaintext trong rendered manifests

□ SEC-04 — Cart API cho client tự chọn userId
  → Fix: Derive userId server-side từ session, validate quantities/item IDs
  → Evidence: 015-sec-04-cart-api-ownership-validation.md

━━━━━━━━━━━━━━━━━━━
📋 DEFERRED — Validate W1, Fix W2+
━━━━━━━━━━━━━━━━━━━

□ K8S-04 + REL-06 — Data stores non-persistent, cart TTL 60 phút
  → W1: Validate restart behavior, document evidence table
  → W2: Managed service vs StatefulSet+PVC decision
  → Evidence: 007-k8s-04-rel-06-data-durability-validation.md
  → ⚠️ Cần CDO-04 input managed vs PVC cost trade-off

□ REL-03 — Checkout partial-success, không idempotency (double charge risk)
  → W1: Document ADR/idempotency design plan
  → W2-3: Implement idempotency key + outbox
  → Evidence: 009-rel-03-checkout-idempotency-follow-up.md

□ SEC-03 — Container hardening (runAsNonRoot, readOnlyRootFS)
  → W2: Global hardening baseline, test per image
  → Evidence: 012-sec-03-container-hardening-baseline.md

━━━━━━━━━━━━━━━━━━━
🤝 CROSS-PILLAR INPUT CẦN TỪ TEAM
━━━━━━━━━━━━━━━━━━━

CDO-04: Resource increase approval (K8S-02), p95 latency data (REL-04), managed vs PVC cost (K8S-04)

CDO-07: Verify evidence ALL fixes (SEC-01,02; REL-01,02,03,06; K8S-01,04)

AIO-01: Review AI fallback resilience (AI-02 → Reliability)

━━━━━━━━━━━━━━━━━━━
📊 SECURITY — SUPPORTING ROLE
━━━━━━━━━━━━━━━━━━━

OBS-02: Review telemetry redaction includes PII/payment/prompt

AI-01: Review prompt content capture boundaries






Truong An

5 hours ago
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@CDO-04 — SCOPE: PERFORMANCE + COST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Các bạn sở hữu 5 gaps — toàn bộ mức Medium, chủ yếu W2+ sau khi có runtime baseline.

📁 Docs gốc cần đọc:

Gap Assessment: tf4-phase3-repo/docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md at main · TF4-Phase3-TechX/tf4-phase3-repo 

Gap → Pillar Map (Perf): https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/GAP-TO-PILLAR-MAPPING.md#33-performance-efficiency-pillar--cdo-04Connect your Github account 

Gap → Pillar Map (Cost): https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/GAP-TO-PILLAR-MAPPING.md#34-cost-optimization-pillar--cdo-04Connect your Github account 

Checklist: tf4-phase3-repo/docs/epic-01-addressing-system-gap/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md at main · TF4-Phase3-TechX/tf4-phase3-repo

━━━━━━━━━━━━━━━━━━━
🎯 OWNED — PRIMARY
━━━━━━━━━━━━━━━━━━━

□ COST-01 🟡 Load-generator autostart mặc định (LOCUST_AUTOSTART=true, USERS=10)
  → Fix W1: Disable autostart trong prod-like values; tag synthetic traffic rõ ràng
  → Evidence: 016-cost-01-load-generator-explicit-profile.md
  → Effort: S (chỉ cần đổi values)

□ COST-02 🟡 Observability stack nặng (2.4GB memory) nhưng non-durable
  → Fix W2: Đo actual usage, right-size, persistence decision
  → Evidence: 017-cost-02-observability-footprint-retention.md
  → ⚠️ Cần CDO-07 verify retention decision

□ K8S-03 🟡 Resource requests/limits thiếu CPU, conflict với deploy/quota.yaml
  → Fix W2: kubectl top baseline → conservative requests/limits → LimitRange
  → Evidence: 018-k8s-03-resource-quota-baseline.md

□ PERF-01 🟡 Browse N currency conversions per page (frontend Promise.all per product)
  → Fix W2-3: Batch conversion hoặc cached rates
  → Evidence: 020-perf-01-perf-02-browse-search-performance.md
  → Cần runtime baseline (trace fan-out count)

□ PERF-02 🟡 Search query unbounded (%LOWER LIKE%, no LIMIT)
  → Fix W2-3: Pagination + text/trigram index + LIMIT
  → Evidence: 020-perf-01-perf-02-browse-search-performance.md
  → Cần runtime baseline (EXPLAIN ANALYZE)

━━━━━━━━━━━━━━━━━━━
🤝 INPUT CẦN CUNG CẤP CHO TEAM (W1)
━━━━━━━━━━━━━━━━━━━
QUAN TRỌNG — CDO-08 đang bị block bởi các bạn:

□ REL-04 → Cần p95/p99 latency baseline data để CDO-08 set checkout timeout budget
  → Action W1: Đo latency checkout dependencies dưới Locust load

□ K8S-02 → Cần review & approve resource increase khi CDO-08 thêm replicas
  → Action W1: Tính impact trên $300/week budget

□ K8S-04 → Cần managed vs PVC cost trade-off analysis
  → Action W1-W2: So sánh RDS/ElastiCache/MSK vs in-cluster StatefulSet+PVC

□ REL-04 → K8S-03 → Cần load baseline data từ kubectl top
  → Action W1: Thu thập CPU/memory usage thực tế

━━━━━━━━━━━━━━━━━━━
📊 COST — SUPPORTING ROLE
━━━━━━━━━━━━━━━━━━━

AI-02: Review token cost tracking metrics (AIO-01 implement)






Truong An

5 hours ago
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@CDO-07 — SCOPE: AUDITABILITY (EVIDENCE BACKSTOP)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Các bạn sở hữu 3 gaps trực tiếp VÀ là evidence backstop cho TOÀN BỘ 18 gaps còn lại.
KHÔNG gap nào được đánh dấu Done nếu chưa có evidence được CDO-07 verify.

📁 Docs gốc cần đọc:
• Gap Assessment: tf4-phase3-repo/docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md at main · TF4-Phase3-TechX/tf4-phase3-repo 
• Gap → Pillar Map (Audit): https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/blob/main/docs/GAP-TO-PILLAR-MAPPING.md#35-auditability-pillar--cdo-07Connect your Github account 
• Checklist + Evidence Template: tf4-phase3-repo/docs/epic-01-addressing-system-gap/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md at main · TF4-Phase3-TechX/tf4-phase3-repo

━━━━━━━━━━━━━━━━━━━
🎯 OWNED — PRIMARY (3 gaps)
━━━━━━━━━━━━━━━━━━━

□ OBS-01 🟠 HIGH — Missing checkout/payment/Kafka/DB SLO alerts (chỉ có 1 alert cart latency)
  → Fix W1 (P0): SLI queries + Grafana alerts + Alertmanager receiver
  → Evidence: 006-obs-01-slo-alert-dashboard-baseline.md
  → ⚠️ Cần CDO-08 input SLO thresholds (checkout ≥99%, cart ≥99.5%, browse <1s)

□ OBS-02 🟡 MEDIUM — Sensitive data trong logs/traces (order/payment/email/AI prompt)
  → Fix W1 (P1): Redact PII/payment/prompt, giữ correlation IDs
  → Evidence: 013-ai-01-obs-02-telemetry-redaction.md
  → ⚠️ Cần Security review redaction scope + AIO-01 input AI fields

□ OBS-03 🟢 LOW — CODEOWNERS path sai, thiếu ADR/postmortem templates
  → Fix W1: Sửa CODEOWNERS + tạo template ADR/runbook/postmortem
  → Evidence: 019-obs-03-repo-auditability-artifacts.md

━━━━━━━━━━━━━━━━━━━
🔍 VERIFY — EVIDENCE BACKSTOP (13+ items)
━━━━━━━━━━━━━━━━━━━

Mỗi fix từ team → CDO-07 verify evidence trước khi đánh dấu Done:

CDO-08 (Security):
  □ SEC-01: Verify no unauthenticated access to Grafana/OpenSearch
  □ SEC-02: Verify no plaintext credentials in rendered manifests

CDO-08 (Reliability):
  □ REL-01: Verify order event integrity (Kafka topic offset ↔ accounting table rows)
  □ REL-02: Verify no accounting data loss (DB write completed before offset commit)
  □ REL-03: Verify ADR for idempotency design documented
  □ REL-06: Verify cart TTL/retention decision documented
  □ K8S-01: Verify probes present in rendered manifests
  □ K8S-04: Verify data survives pod restart (durability evidence)

CDO-04 (Cost):
  □ COST-02: Verify observability retention decision documented
  □ K8S-03: Verify resource baseline and quota compatibility

AIO-01 (AI):
  □ AI-01: Verify no prompt/PII content in OpenSearch/Jaeger after redaction
  □ AI-02: Verify AI eval/fallback/cost documentation in place

Cross-cutting:
  □ OBS-01: Verify SLO dashboards and alerts functional
  □ ALL: Verify evidence file format đúng template, đánh số đúng

━━━━━━━━━━━━━━━━━━━
📐 EVIDENCE FILE RULES
━━━━━━━━━━━━━━━━━━━
• Folder: tf4-phase3-repo/docs/evidence/epic-01 at main · TF4-Phase3-TechX/tf4-phase3-repo 
• Naming: {NNN}-{slug}.md (001-rel-01-..., 002-rel-02-..., tăng dần)
• Template: 4 sections bắt buộc:

Đã làm gì?

Kết quả hiện tại

Bằng chứng nằm ở đâu? (link/file/screenshot/PR)

Ghi chú / Follow-up (risk, assumption, deferred items)

Evidence Folder: tf4-phase3-repo/docs/evidence/epic-01 at main · TF4-Phase3-TechX/tf4-phase3-repo






