# Gap-to-Pillar Mapping — TechX Baseline System Gaps

Tài liệu phân loại 21 lỗ hổng (findings) từ `PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` vào các pillars (trụ) mà mỗi nhóm CDO/AIO trong TF4 chịu trách nhiệm fix.

**Ngày:** 2026-07-08
**Refs:** `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md`, `docs/epic-01-addressing-system-gap/EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md`, `tf4-phase3-repo/docs/requirements/RULES.md`

---

## 1. Pillar System Overview

Theo RULES.md Section 4, TF4 vận hành theo **5 trụ CDO + 1 trụ AI (AIO)**:


| #   | Pillar (Trụ)                | Chủ sở hữu trong TF4   | Trách nhiệm chính                                                                     |
| --- | --------------------------- | ---------------------- | ------------------------------------------------------------------------------------- |
| 1   | **Security**                | **CDO-08**             | Hardening, least-privilege, credentials, access control, container security           |
| 2   | **Reliability**             | **CDO-08**             | Fault tolerance, self-healing, SLO enforcement, data durability, graceful degradation |
| 3   | **Performance Efficiency**  | **CDO-04**             | Right-sizing, scaling, latency optimization, bottleneck removal                       |
| 4   | **Cost Optimization**       | **CDO-04**             | Right-size, spot instances, waste elimination, budget guardrails                      |
| 5   | **Auditability**            | **CDO-07**             | K8s audit, CloudTrail, change management, log integrity, evidence collection          |
| 6   | **AI Safety &amp; Quality** | **AIO-01**             | AI guardrails, eval, fallback, cost tracking, prompt/content safety                   |


**Xuyên suốt cả 5 trụ CDO:** Operational Excellence — on-call, ADR, Ops Review, evidence, quy mọi quyết định về khách hàng và doanh thu.

### TF4 Group ↔ Pillar Assignment

| Nhóm | Pillar(s) | Viết tắt | Workload (owned) |
|---|---|---|---|
| **AIO-01** | AI Safety & Quality | AI | 2 gaps (🟠×2) |
| **CDO-04** | Performance Efficiency + Cost Optimization | Perf + Cost | 5 gaps (🟡×5) |
| **CDO-07** | Auditability | Audit | 3 owned + verify 18 gaps from others |
| **CDO-08** | Security + Reliability | Sec + Rel | 13 gaps (🔴×3 🟠×8 🟡×2) |

> **Note:** CDO-08 has the largest workload (13/21 gaps) because Reliability owns the revenue-critical path and Security owns observability auth + credentials. CDO-04 and AIO-01 should provide input early to unblock CDO-08 where needed (e.g., Cost review for K8S-02 resource increase, Perf baseline for REL-04 timeout values). CDO-07 is the evidence backstop for the entire team.

---

## 2. Gap-to-Pillar Mapping Matrix

### Legend


| Ký hiệu                         | Ý nghĩa                                             |
| ------------------------------- | --------------------------------------------------- |
| **P** (Primary)                 | Pillar chịu trách nhiệm chính — lead implementation |
| **S** (Secondary)               | Pillar hỗ trợ — cần input/review từ pillar này      |
| **C** (Cross-cutting)           | Liên quan đến nhiều pillar, cần phối hợp            |
| **OE** (Operational Excellence) | Thuộc về vận hành xuyên suốt, cả team cùng làm      |


### Full Matrix


| Finding ID  | Severity    | Security | Reliability | Perf Efficiency | Cost Optimization | Auditability | AI (AIO) | Notes                                                                                       |
| ----------- | ----------- | -------- | ----------- | --------------- | ----------------- | ------------ | -------- | ------------------------------------------------------------------------------------------- |
| **SEC-01**  | 🟠 High     | **P**    |             |                 |                   | S            |          | Observability auth = Security lead; Audit verify evidence                                   |
| **SEC-02**  | 🟠 High     | **P**    |             |                 |                   | S            |          | Static creds → Secrets = Security lead; Audit verify no plaintext                           |
| **SEC-03**  | 🟡 Medium   | **P**    |             |                 |                   |              |          | Container hardening = pure Security                                                         |
| **SEC-04**  | 🟡 Medium   | **P**    | S           |                 |                   |              |          | Cart API trust boundary = Security lead; Reliability review cart SLO impact                 |
| **K8S-01**  | 🟠 High     |          | **P**       |                 |                   | S            |          | Probes = Reliability lead; Audit verify manifests                                           |
| **K8S-02**  | 🟠 High     |          | **P**       |                 | S                 |              |          | Replicas/PDB = Reliability lead; Cost review resource impact                                |
| **K8S-03**  | 🟡 Medium   |          |             | S               | **P**             |              |          | Resource/quota = Cost lead; Perf provide baseline data                                      |
| **K8S-04**  | 🔴 Critical |          | **P**       |                 |                   | S            |          | Data persistence = Reliability lead; Audit verify durability evidence                       |
| **REL-01**  | 🔴 Critical |          | **P**       |                 |                   | S            |          | Kafka producer ack = Reliability lead; Audit verify event integrity                         |
| **REL-02**  | 🔴 Critical |          | **P**       |                 |                   | S            |          | Accounting commit = Reliability lead; Audit verify no data loss                             |
| **REL-03**  | 🟠 High     |          | **P**       |                 |                   | S            |          | Idempotency design = Reliability lead; Audit track ADR                                      |
| **REL-04**  | 🟠 High     |          | **P**       | S               |                   |              |          | Timeout budget = Reliability lead; Perf help measure p95                                    |
| **REL-05**  | 🟠 High     |          | **P**       |                 |                   |              |          | Graceful shutdown = pure Reliability                                                        |
| **REL-06**  | 🟠 High     |          | **P**       |                 |                   | S            |          | Cart durability = Reliability lead; Audit verify TTL/retention decision                     |
| **PERF-01** | 🟡 Medium   |          |             | **P**           |                   |              |          | Currency fan-out = pure Performance                                                         |
| **PERF-02** | 🟡 Medium   |          |             | **P**           |                   |              |          | Search query = pure Performance                                                             |
| **COST-01** | 🟡 Medium   |          |             |                 | **P**             |              |          | Load-gen autostart = pure Cost                                                              |
| **COST-02** | 🟡 Medium   |          |             |                 | **P**             | S            |          | Obs footprint = Cost lead; Audit verify retention decision                                  |
| **OBS-01**  | 🟠 High     |          | S           |                 |                   | **P**        |          | SLO alerts = Auditability lead (measurement/evidence); Reliability input on thresholds      |
| **OBS-02**  | 🟡 Medium   | S        |             |                 |                   | **P**        | S        | Telemetry redaction = Auditability lead; Security review; AI review prompt content          |
| **OBS-03**  | 🟢 Low      |          |             |                 |                   | **P**        |          | CODEOWNERS/ADR templates = pure Auditability                                                |
| **AI-01**   | 🟠 High     | S        |             |                 |                   | S            | **P**    | Prompt capture = AIO lead; Security review boundaries; Audit verify redaction               |
| **AI-02**   | 🟠 High     |          | S           |                 | S                 |              | **P**    | AI fallback/eval/cost = AIO lead; Reliability review fallback path; Cost review token spend |


---

## 3. Per-Pillar Breakdown

### 3.1 Security Pillar → **CDO-08**

**Owns 4 findings (all single-pillar lead). Participates in 3 cross-pillar.**

```
Workload: 4 owned + 3 supporting = 7 items touched
Critical: 0  |  High: 2  |  Medium: 2
```

#### Owned (Primary)


| ID         | Severity  | Gap                                                                   | Week 1? | Effort | Dependencies                                 |
| ---------- | --------- | --------------------------------------------------------------------- | ------- | ------ | -------------------------------------------- |
| **SEC-01** | 🟠 High   | Grafana anonymous Admin + OpenSearch security disabled                | ✅ Yes   | M      | Needs Audit verify no anonymous access       |
| **SEC-02** | 🟠 High   | Static DB credentials plaintext in values.yaml                        | ✅ Yes   | M      | Needs Audit verify no plaintext in manifests |
| **SEC-03** | 🟡 Medium | Container hardening missing (runAsNonRoot, readOnlyRootFS, drop caps) | Week 2  | M      | Test per image; some need writable paths     |
| **SEC-04** | 🟡 Medium | Cart API client-controlled userId                                     | ✅ Yes   | S      | Reliability review cart SLO impact           |


#### Supporting (Secondary)


| ID         | Role   | What Security Needs to Do                                                           |
| ---------- | ------ | ----------------------------------------------------------------------------------- |
| **OBS-02** | Review | Verify telemetry redaction includes PII/payment/prompt; review redaction boundaries |
| **AI-01**  | Review | Review prompt content capture boundaries; confirm redaction approach covers AI path |


#### Cross-Pillar Dependencies

```
SEC-01 ──→ Auditability (OBS scope): verify no unauthenticated access remains
SEC-02 ──→ Auditability: verify no plaintext credentials in rendered manifests
SEC-04 ──→ Reliability: cart SLO must not regress after auth change
AI-01  ──→ Security (review boundaries) ←→ AIO (implements redaction)
```

### 3.2 Reliability Pillar → **CDO-08**

**Owns 9 findings (largest workload). Participates in 2 cross-pillar.**

```
Workload: 9 owned + 2 supporting = 11 items touched
Critical: 3  |  High: 6  |  Medium: 0
```

#### Owned (Primary)


| ID         | Severity    | Gap                                                      | Week 1?             | Effort | Dependencies                                                   |
| ---------- | ----------- | -------------------------------------------------------- | ------------------- | ------ | -------------------------------------------------------------- |
| **REL-01** | 🔴 Critical | Checkout Kafka producer ack (`NoResponse`)               | ✅ Yes (P0)          | M      | Audit verify event integrity                                   |
| **REL-02** | 🔴 Critical | Accounting consumer auto-commit before DB write          | ✅ Yes (P0)          | M      | Audit verify no data loss                                      |
| **K8S-04** | 🔴 Critical | Data stores non-persistent Deployments (PG/Valkey/Kafka) | Validate W1, fix W2 | L      | Audit verify durability evidence; Cost input on managed vs PVC |
| **K8S-01** | 🟠 High     | Probes supported but none configured in values           | ✅ Yes (P0)          | M      | Audit verify manifests                                         |
| **K8S-02** | 🟠 High     | Single replicas, no HPA/PDB                              | ✅ Yes (P0)          | M      | Cost review resource increase                                  |
| **REL-03** | 🟠 High     | Partial-success no idempotency                           | Doc W1, fix W2-3    | L      | Audit track ADR                                                |
| **REL-04** | 🟠 High     | No dependency timeout budget                             | ✅ Yes (P1)          | M      | Perf help measure p95 baselines                                |
| **REL-05** | 🟠 High     | Checkout graceful shutdown unreachable                   | ✅ Yes (P0)          | S      | None (pure code fix)                                           |
| **REL-06** | 🟠 High     | Cart ephemeral + 60min TTL                               | Validate W1, fix W2 | M      | Audit verify TTL/retention decision                            |


#### Supporting (Secondary)


| ID         | Role   | What Reliability Needs to Do                                                          |
| ---------- | ------ | ------------------------------------------------------------------------------------- |
| **SEC-04** | Review | Cart SLO must not regress when auth identity model changes                            |
| **AI-02**  | Review | AI fallback path must not cause cascading failure; review timeout/retry               |
| **OBS-01** | Input  | Provide SLO threshold recommendations (checkout ≥99%, cart ≥99.5%, browse &lt;1s p95) |


#### Cross-Pillar Dependencies

```
REL-01 ──→ Auditability: event integrity evidence
REL-02 ──→ Auditability: no-data-loss evidence
K8S-04 ──→ Auditability: durability evidence + Cost: managed vs PVC trade-off
K8S-01 ──→ Auditability: probe manifest verification
K8S-02 ──→ Cost: resource increase approval
REL-03 ──→ Auditability: ADR for idempotency design
REL-04 ──→ Performance Efficiency: p95/p99 latency baselines
OBS-01 ──→ Auditability: SLO alert thresholds
```

### 3.3 Performance Efficiency Pillar → **CDO-04**

**Owns 2 findings. Participates in 1 cross-pillar.**

```
Workload: 2 owned + 1 supporting = 3 items touched
Critical: 0  |  High: 0  |  Medium: 2
```

#### Owned (Primary)


| ID          | Severity  | Gap                                    | Week 1?  | Effort | Dependencies                                |
| ----------- | --------- | -------------------------------------- | -------- | ------ | ------------------------------------------- |
| **PERF-01** | 🟡 Medium | N currency conversions per browse page | Week 2-3 | M      | Need runtime baseline (trace fan-out count) |
| **PERF-02** | 🟡 Medium | Unbounded index-hostile search query   | Week 2-3 | M      | Need runtime baseline (EXPLAIN ANALYZE)     |


#### Supporting (Secondary)


| ID         | Role  | What Performance Needs to Do                                           |
| ---------- | ----- | ---------------------------------------------------------------------- |
| **REL-04** | Input | Provide p95/p99 latency baseline data for checkout dependency timeouts |


#### Cross-Pillar Dependencies

```
PERF-01 ──→ (none, standalone optimization)
PERF-02 ──→ (none, standalone optimization)
REL-04 ──→ Performance Efficiency: latency data → Reliability: timeout values
```

### 3.4 Cost Optimization Pillar → **CDO-04**

**Owns 3 findings. Participates in 2 cross-pillar.**

```
Workload: 3 owned + 2 supporting = 5 items touched
Critical: 0  |  High: 0  |  Medium: 3
```

#### Owned (Primary)


| ID          | Severity  | Gap                                                  | Week 1? | Effort | Dependencies                                             |
| ----------- | --------- | ---------------------------------------------------- | ------- | ------ | -------------------------------------------------------- |
| **COST-01** | 🟡 Medium | Load-generator autostarts in default values          | ✅ Yes   | S      | None (values change)                                     |
| **COST-02** | 🟡 Medium | Observability stack heavy (2.4GB) but non-durable    | Week 2  | M      | Need runtime usage data; Audit verify retention decision |
| **K8S-03**  | 🟡 Medium | Resource model incomplete; conflicts with quota.yaml | Week 2  | M      | Need Prometheus/Grafana resource data; Perf provide load baselines |


#### Supporting (Secondary)


| ID         | Role   | What Cost Needs to Do                                          |
| ---------- | ------ | -------------------------------------------------------------- |
| **K8S-02** | Review | Approve resource increase for additional replicas              |
| **K8S-04** | Input  | Provide managed vs PVC cost trade-off analysis for data stores |


#### Cross-Pillar Dependencies

```
COST-01 ──→ (none, standalone values change)
COST-02 ──→ Auditability: retention decision sign-off
K8S-03 ──→ Performance Efficiency: load baseline data
K8S-02 ──→ Cost (review resource increase) ← Reliability (implements replicas)
K8S-04 ──→ Cost (managed/PVC analysis) ← Reliability (implements persistence)
```

### 3.5 Auditability Pillar → **CDO-07**

**Owns 3 findings directly. Touches nearly ALL other findings as evidence/secondary.**

```
Workload: 3 owned + 13 supporting = 16 items touched (largest cross-cutting)
Critical: 0  |  High: 1  |  Medium: 1  |  Low: 1
```

#### Owned (Primary)


| ID         | Severity  | Gap                                                     | Week 1?    | Effort | Dependencies                          |
| ---------- | --------- | ------------------------------------------------------- | ---------- | ------ | ------------------------------------- |
| **OBS-01** | 🟠 High   | Missing checkout/payment/Kafka/DB SLO alerts            | ✅ Yes (P0) | M      | Reliability input on thresholds       |
| **OBS-02** | 🟡 Medium | Sensitive data in logs/traces (order/payment/email/AI)  | ✅ Yes (P1) | S      | Security + AIO review redaction scope |
| **OBS-03** | 🟢 Low    | CODEOWNERS path wrong, missing ADR/postmortem templates | ✅ Yes      | S      | None                                  |


#### Supporting (Secondary) — Evidence &amp; Verification for ALL other pillars

Auditability is cross-cutting by design (RULES.md Section 4: "Auditability là trụ xuyên suốt mọi thay đổi"). Every fix requires:


| Finding     | What Auditability Verifies                                         |
| ----------- | ------------------------------------------------------------------ |
| **SEC-01**  | No unauthenticated access to Grafana/OpenSearch after fix          |
| **SEC-02**  | No plaintext credentials in rendered manifests after migration     |
| **K8S-01**  | Probes present in rendered manifests                               |
| **K8S-04**  | Data survives pod restart (durability evidence)                    |
| **REL-01**  | Order event integrity proof (Kafka topic + accounting table match) |
| **REL-02**  | No accounting data loss proof (DB write before offset commit)      |
| **REL-03**  | ADR for idempotency design decisions                               |
| **REL-06**  | Cart TTL/retention decision documented                             |
| **COST-02** | Observability retention decision documented                        |
| **OBS-01**  | SLO dashboards and alerts functional                               |
| **AI-01**   | No prompt/PII content in OpenSearch/Jaeger after redaction         |
| **AI-02**   | AI eval/fallback/cost documentation in place                       |


#### Audit Evidence Collection Workflow

```
Any Pillar Fix → Auditability: create numbered evidence file in 
  tf4-phase3-repo/docs/evidence/epic-01/{NNN}-{slug}.md
  using the template from EPIC-01-SYSTEM-GAP-FIX-CHECKLIST.md Section "Evidence File Template"

Evidence must include: what was done, current result, proof location, remaining risk.
Only then can the checklist item be marked Done.
```

---

### 3.6 AI Safety &amp; Quality Pillar (AIO) → **AIO-01**

**Owns 2 findings. Participates in 2 cross-pillar.**

```
Workload: 2 owned + 2 supporting = 4 items touched
Critical: 0  |  High: 2  |  Medium: 0
```

#### Owned (Primary)


| ID        | Severity | Gap                                                                | Week 1?    | Effort | Dependencies                                                      |
| --------- | -------- | ------------------------------------------------------------------ | ---------- | ------ | ----------------------------------------------------------------- |
| **AI-01** | 🟠 High  | AI prompt/content captured in telemetry by default                 | ✅ Yes (P1) | S      | Security review boundaries; Audit verify redaction                |
| **AI-02** | 🟠 High  | No AI fallback/eval/cost gate; `llmInaccurateResponse` unprotected | ✅ Yes (P1) | M      | Reliability review fallback resilience; Cost review token metrics |


#### Supporting (Secondary)


| ID         | Role  | What AIO Needs to Do                                      |
| ---------- | ----- | --------------------------------------------------------- |
| **OBS-02** | Input | Define which AI telemetry fields must be redacted vs kept |
| **OBS-01** | Input | Define AI-specific SLO metrics to monitor                 |


#### Cross-Pillar Dependencies

```
AI-01 ──→ Security (review redaction boundaries) + Auditability (verify no prompt in logs)
AI-02 ──→ Reliability (review fallback doesn't cascade) + Cost (token cost tracking)
```

---

## 4. Operational Excellence — Cross-Cutting Across All Pillars

Operational Excellence không sở hữu finding riêng nhưng áp dụng cho **mọi finding**:


| OE Aspect            | Applies To                                                                     | Action                                                                                |
| -------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| **ADR ký tên**       | Mọi quyết định lớn (REL-03 idempotency, K8S-04 persistence, COST-02 retention) | Viết ADR, lưu trong `docs/audit/`, Auditability verify                                |
| **Evidence file**    | Mọi fix hoàn thành                                                             | Tạo file numbered evidence trong `docs/evidence/epic-01/`, dùng template từ checklist |
| **Ops Review**       | Weekly                                                                         | Mỗi pillar báo cáo progress, SLO status, risk                                         |
| **On-call rotation** | All                                                                            | Trực xoay vòng; xử lý bất kỳ pillar nào khi sự cố                                     |
| **SLO defense**      | Checkout, Cart, Browse, AI                                                     | Auditability dựng dashboards; cả team giữ error budget                                |


---

## 5. Week 1 Action Items Per Group

### CDO-08 — Security + Reliability (13 gaps)

**Security (4 gaps):**
- [ ] **SEC-01**: Disable Grafana anonymous Admin → Viewer; document emergency access (Evidence: `010-sec-01-observability-access-baseline.md`)
- [ ] **SEC-02**: Move DB creds to Kubernetes Secrets; document rotation plan (Evidence: `011-sec-02-static-db-credentials-secret-baseline.md`)
- [ ] **SEC-04**: Fix cart API userId server-side (Evidence: `015-sec-04-cart-api-ownership-validation.md`)

**Reliability (9 gaps):**
- [ ] **REL-01**: Fix Kafka producer ack → `WaitForAll` + bounded timeout (Evidence: `001-rel-01-checkout-kafka-order-event-integrity.md`)
- [ ] **REL-02**: Fix accounting consumer → manual commit after DB write (Evidence: `002-rel-02-accounting-manual-commit-after-db-write.md`)
- [ ] **REL-05**: Fix checkout graceful shutdown (Evidence: `003-rel-05-checkout-graceful-shutdown.md`)
- [ ] **K8S-01**: Add probes to checkout/cart/payment/frontend/product-catalog (Evidence: `004-k8s-01-revenue-path-probes.md`)
- [ ] **K8S-02**: Add stateless replicas + PDB baseline (Evidence: `005-k8s-02-stateless-replica-pdb-baseline.md`)
- [ ] **REL-04**: Add checkout dependency timeout budget (Evidence: `008-rel-04-checkout-dependency-timeout-budget.md`)
- [ ] **REL-03**: Document idempotency ADR (Evidence: `009-rel-03-checkout-idempotency-follow-up.md`)
- [ ] **K8S-04** + **REL-06**: Validate data durability + document Week 2 path (Evidence: `007-k8s-04-rel-06-data-durability-validation.md`)

### CDO-04 — Performance Efficiency + Cost Optimization (5 gaps)

**Performance (2 gaps):**
- [ ] Provide p95/p99 latency baseline data for checkout dependencies (input to REL-04)
- [ ] Plan PERF-01/PERF-02 runtime measurement approach

**Cost (3 gaps):**
- [ ] **COST-01**: Disable load-gen autostart in prod-like values (Evidence: `016-cost-01-load-generator-explicit-profile.md`)
- [ ] Review K8S-02 resource increase impact on $300/week budget
- [ ] Start gathering actual resource usage data

### CDO-07 — Auditability (3 owned + verify all evidence)

- [ ] **OBS-01**: Build SLO dashboards + alerts for checkout/payment/Kafka/DB (Evidence: `006-obs-01-slo-alert-dashboard-baseline.md`)
- [ ] **OBS-02**: Redact sensitive telemetry (Evidence: `013-ai-01-obs-02-telemetry-redaction.md`)
- [ ] **OBS-03**: Fix CODEOWNERS + add ADR/postmortem templates (Evidence: `019-obs-03-repo-auditability-artifacts.md`)
- [ ] Verify evidence files from CDO-08 and CDO-04 as they complete

### AIO-01 — AI Safety & Quality (2 gaps)

- [ ] **AI-01**: Disable prompt content capture in prod-like values (Evidence: `013-ai-01-obs-02-telemetry-redaction.md` — shared with OBS-02)
- [ ] **AI-02**: Add AI fallback/eval/cost baseline (Evidence: `014-ai-02-ai-fallback-eval-cost-baseline.md`)

---

## 6. Cross-Pillar Handoff Map

```
                    ┌─────────────┐
                    │  Security   │
                    │  (4 owned)  │
                    └──┬───┬──────┘
                       │   │
          SEC-01,02,04 │   │ AI-01 review
          → Audit      │   │ → AIO
                       │   │
        ┌──────────────┘   └──────────────┐
        ▼                                  ▼
┌──────────────┐                  ┌──────────────┐
│  Reliability │                  │  AIO (AI)    │
│  (9 owned)   │                  │  (2 owned)   │
└──┬───┬───┬───┘                  └──────┬───────┘
   │   │   │                             │
   │   │   │ REL-03,04     AI-02         │ AI-01,02
   │   │   │ → Audit       → Reliability │ → Audit
   │   │   │               → Cost        │
   │   │   │                             │
   │   │   └──────────────────┐          │
   │   │                      ▼          │
   │   │              ┌──────────────┐   │
   │   └──────────────┤  Auditability│◄──┘
   │                  │  (3 owned +  │
   │   K8S-02,04      │   13 verify) │
   │   → Cost          └──────────────┘
   │                       ▲
   │                       │ COST-02, OBS-*
   │                       │ → Audit
   │               ┌───────┴──────┐
   │               │ Cost Opt.    │
   └───────────────┤ (3 owned)    │
                   └──────────────┘
                        ▲
                        │ K8S-03
                        │ → Perf data
                   ┌────┴─────────┐
                   │ Perf Effic.  │
                   │ (2 owned)    │
                   └──────────────┘
```

---

## 7. Quick Reference: Which Pillar Fixes What


| If the finding ID starts with... | Primary owner is...                                     |
| -------------------------------- | ------------------------------------------------------- |
| `SEC-`                           | **Security**                                            |
| `REL-`                           | **Reliability**                                         |
| `K8S-01`, `K8S-02`               | **Reliability** (probes, replicas, PDB)                 |
| `K8S-03`                         | **Cost Optimization** (resources/quota)                 |
| `K8S-04`                         | **Reliability** (data persistence) + Cost input         |
| `PERF-`                          | **Performance Efficiency**                              |
| `COST-`                          | **Cost Optimization**                                   |
| `OBS-01`                         | **Auditability** (SLO dashboards/alerts)                |
| `OBS-02`                         | **Auditability** (telemetry redaction) + Security + AIO |
| `OBS-03`                         | **Auditability** (repo governance artifacts)            |
| `AI-`                            | **AIO** (AI Safety &amp; Quality)                       |


