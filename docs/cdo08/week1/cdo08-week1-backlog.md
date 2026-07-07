# CDO08 Week 1 - Backlog Tổng Hợp Findings

Owner: Hải  
Reviewer: Nguyên  
Status: Draft Template - Waiting For Owner Findings

## Mục Đích

File này là bảng backlog chung của CDO08 trong Tuần 1.

Mục tiêu không phải là tự đoán toàn bộ vấn đề thay cho các owner. Mục tiêu là gom findings từ từng workstream, chuẩn hóa thành cùng một format, chấm priority bằng rubric, rồi chọn top items đủ bằng chứng để đưa vào pitch cuối Tuần 1 và tạo task triển khai cho Tuần 2-3.

Backlog này dùng để:

- tổng hợp findings từ tất cả owner CDO08
- biết finding nào đã đủ thông tin, finding nào còn thiếu
- xếp priority P0/P1/P2/P3 theo rubric
- xác định dependency với CDO04, CDO07 hoặc AIO01
- chọn top-N items cho pitch
- tạo follow-up implementation tasks cho Tuần 2-3

## Nguồn Input

| Owner | Area / Ownership | Expected Artifact | Intake Status | Notes |
|---|---|---|---|---|
| Nguyên | Tech Lead / Architecture / Review Gate | `docs/cdo08/week1/system-dependency-map.md` | Waiting | Cần dependency map để gắn finding vào đúng flow |
| Nguyên | Tech Lead / Architecture / Review Gate | `docs/cdo08/week1/technical-review-checklist.md` | Waiting | Cần checklist để review P0/P1 candidates |
| Nguyên | Tech Lead / Architecture / Review Gate | `docs/cdo08/week1/technical-risk-review.md` | Waiting | Sẽ có sau khi backlog draft có top findings |
| Thuỷ | Secrets / Config / flagd Safety | `docs/cdo08/week1/secrets-config-inventory.md` | Waiting | Cần findings về secret/config |
| Thuỷ | Secrets / Config / flagd Safety | `docs/cdo08/week1/flagd-sync-safety-checklist.md` | Waiting | P0 vì liên quan rule Phase 3 |
| Thuỷ | Secrets / Config / flagd Safety | `docs/cdo08/week1/secret-migration-candidates.md` | Optional / P2 | Có thể defer nếu chưa đủ findings |
| Quân | Checkout Reliability | `docs/cdo08/week1/checkout-dependency-map.md` | Waiting | Cần map checkout revenue-critical path |
| Quân | Checkout Reliability | `docs/cdo08/week1/checkout-timeout-retry-gaps.md` | Waiting | Cần gaps để chọn reliability follow-up |
| Quân | Checkout Reliability | `docs/cdo08/week1/checkout-smoke-test-checklist.md` | Waiting | P1, dùng cho deploy/rollback verification |
| Phương | Data Reliability | `docs/cdo08/week1/postgresql-reliability-baseline.md` | Waiting | P0, data dependency quan trọng |
| Phương | Data Reliability | `docs/cdo08/week1/valkey-cart-reliability-baseline.md` | Waiting | P1, liên quan cart và checkout |
| Phương | Data Reliability | `docs/cdo08/week1/kafka-reliability-baseline.md` | Waiting | P1, liên quan async order processing |
| Phương | Data Reliability | `docs/cdo08/week1/backup-restore-gap-checklist.md` | Waiting | P1, dùng cho data-loss backlog |
| Nam | Kubernetes Runtime Reliability | `docs/cdo08/week1/replica-coverage-matrix.md` | Waiting | P0, tìm SPOF/single replica |
| Nam | Kubernetes Runtime Reliability | `docs/cdo08/week1/probe-coverage-matrix.md` | Waiting | P0, bám incident deploy/readiness |
| Nam | Kubernetes Runtime Reliability | `docs/cdo08/week1/helm-upgrade-rollback-runbook.md` | Waiting | P1, dùng cho deploy safety |
| Nam | Kubernetes Runtime Reliability | `docs/cdo08/week1/pdb-candidates.md` | Optional / P2 | Có thể defer nếu chưa đủ replica analysis |
| Nhân | Platform Security | `docs/cdo08/week1/securitycontext-coverage-matrix.md` | Waiting | P1, container hardening baseline |
| Nhân | Platform Security | `docs/cdo08/week1/serviceaccount-rbac-baseline.md` | Waiting | P1, RBAC/least privilege baseline |
| Nhân | Platform Security | `docs/cdo08/week1/network-exposure-inventory.md` | Waiting | P1, attack surface inventory |
| Nhân | Platform Security | `docs/cdo08/week1/platform-hardening-checklist.md` | Optional / P2 | Có thể defer nếu baseline chưa đủ |
| Quyết | SLO / Observability / Evidence | `docs/cdo08/week1/observability-inventory.md` | Waiting | P1, biết hiện tại đo được gì |
| Quyết | SLO / Observability / Evidence | `docs/cdo08/week1/checkout-slo-metric-queries.md` | Waiting | P0, cần cho pitch checkout SLO |
| Quyết | SLO / Observability / Evidence | `docs/cdo08/week1/health-evidence-checks.md` | Waiting | P1, chuẩn hóa evidence runtime/data |
| Quyết | SLO / Observability / Evidence | `docs/cdo08/week1/evidence-pack-template.md` | Waiting | P1, chuẩn hóa evidence cho pitch/CDO07 |

## Backlog Findings

Điền mỗi finding thành một dòng. Mỗi finding P0/P1 bắt buộc phải có risk, affected service/file, evidence, proposed follow-up, test plan, rollback plan và reviewer status.

| ID | Owner | Area | Finding | Current Risk | Business Impact | Affected Service/File | Evidence | Proposed Follow-up | Dependency | Cost / Perf Impact | Test Plan | Rollback Plan | Priority Draft | Reviewer Status | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CDO08-W1-001 | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD | Needs Info | Waiting for owner findings |

## Priority Rules

Priority phải dựa trên `docs/cdo08/week1/pm-priority-rubric.md`.

Tóm tắt rule:

- P0: trực tiếp ảnh hưởng checkout, data loss, real secret exposure, flagd rule violation hoặc pitch readiness.
- P1: rủi ro có evidence khá chắc trên service critical và nên đưa vào kế hoạch Tuần 2-3.
- P2: improvement hữu ích, nhưng không bắt buộc cho pitch Tuần 1.
- P3: thấp, cleanup hoặc revisit later.

Nếu evidence yếu nhưng impact có vẻ cao, dùng `Needs Info` thay vì đẩy priority quá mạnh.

## Missing Info Tracker

Dùng bảng này để follow up các finding còn thiếu thông tin.

| Finding ID | Owner | Missing Info | Needed By | Blocking What | Status |
|---|---|---|---|---|---|
| TBD | TBD | TBD | Trước pitch dry-run | Priority scoring / technical review | Open |

## Top Candidates For Pitch

Chỉ đưa item vào đây sau khi có evidence và Nguyên review.

| Rank | Finding ID | Summary | Why It Matters | Evidence | Priority | Owner | Reviewer Status |
|---:|---|---|---|---|---|---|---|
| 1 | TBD | TBD | TBD | TBD | TBD | TBD | Needs Info |

## Cross-Team Dependencies

| Finding ID | Team | Dependency Type | Ask | Needed By | Decision Required | Status |
|---|---|---|---|---|---|---|
| TBD | CDO04 | Cost / Performance | TBD | Trước final pitch | TBD | Open |
| TBD | CDO07 | Evidence / ADR / Auditability | TBD | Trước final pitch | TBD | Open |
| TBD | AIO01 | AI / product-reviews / LLM | TBD | Nếu finding liên quan AI flow | TBD | Open |

## Follow-Up Task Candidates For Week 2-3

Mỗi P0/P1 finding cần có proposed follow-up đủ rõ để tạo task sau pitch.

| Finding ID | Proposed Task Summary | Owner Candidate | Scope | Test Plan | Rollback Plan | Dependency | Priority |
|---|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

## Review Log

| Date | Reviewer | Scope Reviewed | Status | Notes |
|---|---|---|---|---|
| TBD | Nguyên | Top P0/P1 candidates | Not Started | Waiting for owner findings |

## Current Status

This is a template. It should be updated as owner artifacts arrive.

Current blockers:

- Waiting for owner findings from technical workstreams.
- Waiting for runtime evidence if EKS environment is not ready.
- Waiting for Tech Lead review before final pitch ranking.

