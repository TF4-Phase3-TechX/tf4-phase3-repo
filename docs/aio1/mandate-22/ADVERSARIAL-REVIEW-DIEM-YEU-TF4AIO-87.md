# Báo cáo adversarial review — Điểm yếu AIOps Closed-Loop

- **Ticket:** [TF4AIO-87](https://aio1-xbrain.atlassian.net/browse/TF4AIO-87)
- **Phạm vi:** Detection → Alerting / Lifecycle → RCA → Policy & Auto-remediation → Verification → Rollback / Escalation → Replay / Evidence
- **Nguồn:** PR #662, FINAL-EVIDENCE-2026-07-25, `live-drill-inc-c35170a68bef.json`, ADR-022, code path AIOps canonical
- **Ràng buộc:** CDO-04 freeze — chỉ review offline/source; không drill EKS/GitOps/load/chaos
- **PR harden follow-up:** [#669](https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/669) (một phần Critical/High đã được vá offline)

---

## 1. Mục đích tài liệu

Tài liệu này **không** phải review code style. Mục tiêu là liệt kê assumption sai, điểm yếu thiết kế và edge case có thể dẫn tới:

- bỏ sót incident;
- false positive / alert flood;
- mutation sai hoặc nguy hiểm;
- không fail-closed;
- claim thành công mạnh hơn bằng chứng runtime.

Mỗi mục phân biệt mức độ:

| Nhãn | Ý nghĩa |
|---|---|
| **Critical** | Có thể mutate sai, mất kiểm soát mutation, hoặc claim sai nghiêm trọng |
| **High** | Bỏ sót lớn, verifier sai, mất audit/safety quan trọng |
| **Medium** | Edge case, impact giới hạn hoặc có workaround |
| **Accepted** | Đã hiểu rủi ro, claim boundary phù hợp scope hiện tại |
| **Follow-up** | Không block submission offline; cần Jira/owner riêng |

Trạng thái evidence:

| Mức | Ý nghĩa |
|---|---|
| Designed | Có trong ADR/docs |
| Implemented | Có trong code |
| Offline/CI | Có test/replay |
| Runtime observed | Đã thấy trên production drill |
| Accepted / signed-off | Có chữ ký CDO + on-call/SRE |

---

## 2. Tóm tắt verdict

| Câu hỏi | Kết luận |
|---|---|
| Merge kỹ thuật PR #662 (verifier scope + evidence honesty)? | **Có** — hướng đúng; đã merge |
| Claim full Mandate 22 closed-loop pass? | **Không** |
| Bật lại live autonomous an toàn? | **Không** cho đến khi xử lý Critical/High + chữ ký ADR |
| Runtime đã chứng minh gì? | Safety branch: detect → policy → action → verify → rollback → escalate → restore GitOps |
| Runtime **chưa** chứng minh gì? | Happy-path verifier chấp nhận healthy; MTTR cải thiện vs manual; ADR formal acceptance |

**Một câu:** Hệ thống có **khung fail-closed thật**, evidence packet **tương đối trung thực**, nhưng **chưa** phải closed-loop autonomous production-grade.

---

## 3. Điểm yếu Critical

### 3.1. `mutation_blocked` / ESCALATED có thể bị auto-resolve rồi mutate lại

- **Scenario:** Incident đã remediate → verify fail → escalate + `mutation_blocked=true`. Detector thấy vài poll “healthy” → store auto-resolve → hết cooldown → incident mới → policy pass → mutate lại cùng Deployment.
- **Hậu quả:** Khóa an toàn chỉ gắn object incident in-memory; sau resolve, autonomous path có thể thrash ReplicaSet, làm nặng sự cố.
- **Code:** `store.observe_recovery` từng cho phép `ESCALATED` recover **không** kiểm `mutation_blocked`.
- **Vì sao chưa chặn:** Policy/quarantine không durable qua lifecycle resolve.
- **Trạng thái sau #669:** Đã suppress auto-resolve khi blocked + process-local target quarantine + API unlock. **Vẫn mất khi pod restart.**

### 3.2. Crash/restart sau `action_executed`, trước verify/rollback

- **Scenario:** Patch template thành công → AIOps OOM/kill/rollout trong settle ~2 phút hoặc lúc verify. Snapshot template gốc + state incident chỉ nằm memory. Lease hết TTL sau đó.
- **Hậu quả:** Cluster đã mutate; không ai verify/rollback tự động; sau TTL có thể incident khác mutate tiếp; audit runtime có thể mất.
- **Code:** `remediation.execute` giữ `original` local; `IncidentStore` process-local; không saga/CRD.
- **Vì sao chưa chặn:** Lease chỉ chống concurrent holder, không phải durable workflow.
- **Trạng thái:** **Chưa fix trong #669** — follow-up bắt buộc trước live autonomous thường xuyên.

### 3.3. “Previous ReplicaSet” không đồng nghĩa known-good

- **Scenario:** Lịch sử revision: good → bad_A → bad_B (current). Code lấy `owned[1]` = bad_A. Hoặc drill trước để lại RS fault; hoặc image giống nhưng env/resources khác “good” CDO.
- **Hậu quả:** Autonomous rollback **đẩy fault khác** (hoặc partial fault). Live drill may mắn vì previous đúng 75m/300m — đó **không** phải invariant.
- **Code:** `KubernetesRollbackAdapter.previous_template` sort revision, lấy previous; chỉ check recency của latest.
- **Vì sao chưa chặn:** ADR yêu cầu CDO confirm known-good; code trước đó không pin.
- **Trạng thái sau #669:** Có optional `AIOPS_KNOWN_GOOD_REVISIONS`. **Bắt buộc CDO set pin khi bật live**; không set thì vẫn giả định previous.

---

## 4. Điểm yếu High

### 4.1. Verification window trộn pre-action + `all(polls)` → false escalate (đã runtime)

- **Scenario (live):** Rollback samples `7097ms` → `105ms` → `105ms`. Poll đầu stale; rule `all(polls)` → `rollback_unverified_escalation`. Đồng thời settle 120s ≈ window 2m → poll đầu vẫn chứa data quanh thời điểm action.
- **Hậu quả:** Rollback “đúng” vẫn escalate; happy path có thể fail oan; sau false verify fail, controller **khôi phục fault template** dù latency target đã 1.9ms.
- **Trạng thái sau #669:** Trailing consecutive healthy polls; settle ≥ window; default settle 150s. **Chưa runtime re-prove.**

### 4.2. Worker `await` remediation block cả detection loop

- **Scenario:** Một remediation ~5 phút (settle + polls + rollback). Trong lúc đó không poll service khác.
- **Hậu quả:** Bỏ sót multi-incident; streak/recovery sai; “closed-loop” làm mù detector.
- **Trạng thái sau #669:** Remediation chạy `asyncio.create_task` — detection không bị block.

### 4.3. Verifier thiếu request-count floor

- **Scenario:** Sau action traffic gần 0 hoặc rất ít request; p95/error “đẹp” giả → kết luận healthy.
- **Hậu quả:** False recovery; resolve remediation khi khách đã rời.
- **Trạng thái sau #669:** Fail-closed khi volume dưới floor (config).

### 4.4. Safety state & audit không durable

- **Scenario:** Pod restart; prune store; log ship fail.
- **Hậu quả:** Mất `mutation_blocked`, mất evidence, dedup hỏng. Packet FINAL-EVIDENCE là **export thủ công**, không chứng minh durability runtime.
- **Trạng thái:** #669 chỉ quarantine process-local. Durable OpenSearch/DB + saga = follow-up.

### 4.5. Argo/GitOps self-heal đua với action/verify/rollback

- **Scenario:** AIOps patch → Argo desired=Git khác → self-heal giữa settle/verify.
- **Hậu quả:** Double writer; verify/rollback trên state lai; snapshot original lệch cluster.
- **Trạng thái:** Ngoài code controller; cần CDO pause self-heal / annotation ignore trong cửa sổ drill. **Chưa code.**

### 4.6. Docs/runbook claim checkout guard sau khi #662 đã bỏ

- **Scenario:** Operator tin verifier vẫn chặn checkout/storefront error; code chỉ guard target.
- **Hậu quả:** Ảo giác blast-radius; dependency regress không veto.
- **Trạng thái sau #669:** Đã sync runbook + `docs/aiops/README`.

### 4.7. Policy `evidence_present` quá lỏng

- **Scenario:** Evidence list có item `value=unavailable` vẫn truthy; Jaeger down vẫn remediate nếu có metric spike.
- **Hậu quả:** Mutate trên evidence chất lượng kém.
- **Trạng thái sau #669:** Bắt buộc ít nhất một quan sát Prometheus usable.

### 4.8. OpenSearch correlation không có time window

- **Scenario:** Search log không filter thời gian → log cũ làm “RCA”.
- **Hậu quả:** Correlation sai thời điểm; confidence/RCA lệch.
- **Trạng thái sau #669:** Filter lookback theo detector.

### 4.9. Replay/scenarios quá “đẹp”

- **Scenario:** JSONL 3 case boolean; adapter luôn ready; không Lease loss, wrong RS, restart mid-flow, zero traffic, Argo overwrite.
- **Hậu quả:** CI xanh không cover failure mode production.
- **Trạng thái:** #669 thêm một số unit test negative; catalog đầy đủ vẫn follow-up.

---

## 5. Điểm yếu Medium

### 5.1. Baseline MAD/relative band nuốt slow drift dài

- Memory leak / queue growth tăng chậm trong lookback → baseline trượt theo; slow_drift có ngưỡng heuristic.
- **Rủi ro:** MTTD chậm hoặc miss drift dưới floor.
- **Follow-up:** Calibration Mandate 7b / long-window baseline.

### 5.2. `sustained_polls=1` + acute window nhạy noise/load-test

- 2/3 sample trong một poll đủ mở incident → false positive / alert noise (cooldown 600s giảm flood nhưng không hết).
- **Trade-off:** Nhanh cho drill; có thể tách profile production.

### 5.3. Frontend error SLI vs burn-rate SLI lệch selector

- `error_rate_query` frontend không filter operation; burn-rate filter operation → impact/severity lệch.
- **Follow-up:** Một SLI definition shared.

### 5.4. Alert payload thiếu trạng thái remediation

- Rule `AIOpsIncidentDetected` có service/type/severity/impact; thiếu “đã mutate / escalated / blocked”; owner label hardcode.
- **Follow-up:** Label remediation status + service-owner map.

### 5.5. Retry patch sau client timeout

- API apply OK nhưng client timeout → retry có thể patch lần hai (nguy hiểm nếu Argo concurrent).
- **Trạng thái sau #669:** Live patch không retry.

### 5.6. Một replica xấu trong N replica

- Availability bắt partial; latency service-level có thể miss hot-pod low traffic.
- **Follow-up** nếu cần per-pod metrics.

### 5.7. Confidence threshold 0.74 fit theo drill

- Gate authorization dựa score calibrate 0.742–0.75 ceiling → data-fit.
- **Rủi ro:** Score noise đủ điều kiện autonomous nếu severity high.
- **Đề xuất:** Tách confidence (ưu tiên operator) khỏi authorization deterministic.

---

## 6. Accepted trade-off (chấp nhận có điều kiện)

| Trade-off | Điều kiện chấp nhận |
|---|---|
| Chưa có successful live E2E verify-accept | Evidence/ADR **không** claim full pass |
| #662/#669 offline-only dưới freeze | Không pretend đã promote/runtime prove |
| Isolation Forest chỉ confidence, không fire gate | Đúng anti-noise |
| Store in-memory MVP | **Chỉ** khi autonomous live **tắt**; bật live thì thành High/Critical |
| Không có causal graph thật | API/docs phải nói *suspected/correlation*, không *root cause chắc chắn* |
| Replay dùng production controller + fake adapter | Evidence level 3, không thay live drill |

---

## 7. Follow-up bắt buộc (Jira / activation)

1. **Durable remediation saga** — persist phase + original template; reconcile orphan mutation khi restart (Critical 3.2).
2. **CDO pin known-good** + promote image có #662/#669 trước live.
3. **ADR-022 chữ ký** CDO deployment owner + on-call/SRE.
4. **Live window sau freeze** — một lần happy-path verify-accept + một forced-wrong rollback.
5. **Manual MTTR baseline** — hiện `null`, không claim %.
6. **Negative replay catalog** đầy đủ (Lease loss, wrong RS, zero traffic, Argo, simultaneous incidents).
7. **Optional E2E dependency guard** — chỉ khi mapping được approve + test; **không** nhét silent lại.
8. **BTC hidden scenarios** / grading-day.

---

## 8. Ma trận claim vs bằng chứng

| Claim / cảm giác | Thực tế |
|---|---|
| “Runtime evidence level 5 safety path” | **Observed** một drill detect→act→verify→rollback→escalate→restore |
| “Successful closed-loop mitigation” | **Not proven** — và evidence packet **không** claim |
| “Target recovered” | Latency 15s→1.9ms **observed**; composite healthy **false** (legacy guard) |
| “Rollback verified” | Rollback **applied**; verify **failed** (stale first poll) → escalate |
| “Mutation block an toàn” | Trước #669: per-incident, auto-resolve được. Sau #669: process-local quarantine — **mất khi restart** |
| “Previous = known-good” | Chỉ đúng nếu CDO pin / may mắn history |
| “Safe GitOps restore” | Observed Ready + CPU profile + dry-run — không full digest attestation trong JSON |
| “#662 fail-closed missing telemetry” | Implemented + unit test; **không** runtime observed trước freeze |

---

## 9. Detection — failure mode còn cần nhớ

- Single outlier: có pre-filter MAD + acute window (2/3) — tốt hơn spike-only, vẫn nhạy khi `sustained_polls=1`.
- Slow drift: có trend path nhưng phụ thuộc heuristic; baseline dài có thể nhiễm.
- Empty/NaN/partial Prometheus: coverage `unavailable`/`warming` — **không** coi healthy để resolve (đúng hướng).
- Busy vs degraded vs down vs rollout vs mất telemetry: có `classify_service_state` + availability adapter; rollout ngắn dựa `availability_sustained_polls`.
- Multi-service đồng thời: streak per key; remediation trước đây block loop (đã soft-fix #669).
- Detector restart: mất streak in-memory.
- Error-budget burn: có floor request; frontend SLI lệch (Medium 5.3).
- Confidence: explainable score, **không** calibrated probability.

---

## 10. Alerting / lifecycle — failure mode

- Severity map: high → notification `critical`, còn lại `warning`.
- Auto-resolve chỉ khi coverage available + non-breach đủ poll — missing telemetry **không** resolve (tốt).
- Dedup key = `incident_type:service` — hai root cause khác cùng type/service gộp một incident.
- **Trước #669:** escalated/mutation-blocked có thể auto-resolve sai (Critical).
- Alert qua Prometheus rule + Alertmanager; delivery Slack chỉ proven bằng receipt, không bằng code path AIOps.
- Payload thiếu action/remediation state chi tiết.

---

## 11. RCA — failure mode

- Không cùng time-window cứng giữa Prometheus / OpenSearch / Jaeger.
- Candidate ranking chủ yếu service đang alert — không causal inference.
- Jaeger/OpenSearch thiếu: vẫn có thể kết luận mềm; field `root_cause` dễ overclaim (nên *suspected*).
- Evidence reference sau restart: phụ thuộc stdout/OS retention — không durable incident store.
- Live drill: `jaeger_evidence: unavailable` vẫn remediate trên Prometheus.

---

## 12. Remediation safety — failure mode

| Giả định | Rủi ro |
|---|---|
| Previous RS = known-good | Sai nếu không pin |
| Một AIOps replica / Lease đủ | Lease expire mid-flight; restart amnesia |
| Dry-run pass ⇒ live patch OK | Admission/RBAC đổi giữa chừng |
| One-attempt / cooldown | Mất sau restart; auto-resolve mở lại cửa (đã harden một phần) |
| Allowlist = blast radius | Config/RBAC; không graph dependency |
| LLM không mutate | Đúng — LLM không authorize action |
| Telemetry degraded giữa decide và act | Policy không re-check coverage ngay trước patch |

---

## 13. Verification / rollback — failure mode

- Settle + window overlap pre-action (đã live).
- Fast-error + low latency: cần error-rate target (đã có sau #662) + volume floor (sau #669).
- Target healthy nhưng dependency xấu: **không** veto mặc định (cố ý sau #662; dependency phải policy riêng).
- Zero traffic: phải inconclusive/fail-closed (volume floor).
- `all(polls)` quá cứng → trailing consecutive (sau #669).
- Rollback restore **original** = có thể restore **fault** nếu action đã “chữa” xong mà verify fail oan (đã live).
- Mutation-blocked qua restart: vẫn yếu nếu không durable.
- GitOps restore cuối: quan sát Ready, không full digest proof trong evidence JSON.

---

## 14. Sáu câu trả lời bắt buộc (tóm tắt)

1. **Blocker merge #662?** Không (offline fix + honesty). **Blocker full pass / live autonomous?** Có.
2. **Test bổ sung ngay:** mutation_blocked không auto-resolve; stale first poll; low volume; evidence unavailable; settle < window — phần lớn đã có trong #669.
3. **Trade-off ghi ADR/docs:** settle/window/trailing; previous≠known-good; quarantine process-local; target-only verify; confidence≠authz; detection/remediation concurrency.
4. **Chấp nhận scope hiện tại:** adaptive detection coverage; policy envelope; safety-branch runtime; claim boundary FINAL-EVIDENCE; hướng #662/#669.
5. **Follow-up Jira:** saga durable; pin known-good ops; ADR sign; live window; MTTR baseline; negative replay; alert content.
6. **Approve #662?** Technical merge **Yes**. Mandate complete / live autonomous **No**. **#669** recommend merge harden offline.

---

## 15. Bottom line (cho tech lead / CDO)

> AIOps hiện là **closed-loop an toàn có điều kiện (narrow, human-gated activation)**, không phải autonomous remediation luôn-bật production-grade.
>
> Runtime 2026-07-25 chứng minh **nhánh fail-closed**, đồng thời vạch ra verifier legacy, stale poll, và giả định known-good/mutation-block yếu.
>
> PR #669 harden offline các lỗ hổng có thể sửa không cần EKS. **Chưa đủ** để tuyên bố xong Mandate 22 hay bật live lại mà không có: pin known-good, durable saga (khuyến nghị), ADR signatures, và drill happy-path sau freeze.

---

## 16. Liên kết

| Tài liệu | URL / path |
|---|---|
| Jira review | https://aio1-xbrain.atlassian.net/browse/TF4AIO-87 |
| Jira Mandate 22 | https://aio1-xbrain.atlassian.net/browse/TF4AIO-83 |
| PR #662 | https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/662 |
| PR #669 harden | https://github.com/TF4-Phase3-TechX/tf4-phase3-repo/pull/669 |
| Final evidence | `docs/aio1/mandate-22/FINAL-EVIDENCE-2026-07-25.md` |
| Runtime JSON | `docs/aio1/mandate-22/evidence/live-drill-inc-c35170a68bef.json` |
| ADR-022 | `docs/aio1/mandate-22/ADR-022-safe-closed-loop-mitigation.md` |
