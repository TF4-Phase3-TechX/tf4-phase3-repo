# 📋 Danh sách Jira Tasks - Team Audit (CD007)

*Tài liệu này được chuẩn hóa theo "Jira Working Rules — Xbrain Accelerator" nhằm đảm bảo tracking tiến độ và bằng chứng (evidence) rõ ràng cho Weekly Export.*

---

## 🏗️ 1. Cấu trúc Epic / Story (Task Tổng)

- **Issue Type:** Epic / Story
- **Summary:** `[Audit] Kiểm toán Hạ tầng và Tuân thủ An toàn (Phase 3)`
- **Assignee:** Audit Lead (PM)
- **Label:** `Docs`, `Need-Review`

**Mục tiêu (Objective):** Thực hiện rà soát, kiểm toán và giám sát toàn bộ các thay đổi về cấu hình, phân quyền, và log hệ thống trên hạ tầng AWS. Đảm bảo có đầy đủ bằng chứng (evidence) báo cáo hàng tuần.

---

## 🛠️ 2. Danh sách Các Task (Công việc cụ thể 1-2 ngày)

*Tất cả các Task dưới đây bắt buộc phải có Assignee và không được để vô chủ. Khi có blocker phải gắn label `Blocker`. Yêu cầu có checklist Sub-tasks để xác định khi nào task thực sự "Done" (Definition of Done).*

### 📌 Nhóm 1: Kiểm toán Truy cập & Tuân thủ
**Task 1: Kiểm tra quyền IAM & Access Analyzer**
- **Issue Type:** Task
- **Summary:** `[Compliance] Rà soát quyền IAM và đánh giá Access Analyzer`
- **Assignee:** Member 1
- **Label:** `Research`, `Docs`
- **Priority:** P1
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Phát hiện user/role dư thừa quyền (over-privileged) dựa trên báo cáo Access Analyzer.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Xuất danh sách policy hiện hành từ AWS IAM.
  - [ ] Phân tích báo cáo rủi ro từ IAM Access Analyzer.
  - [ ] Lập danh sách tài khoản vi phạm (over-privileged) vào file `IAM_AUDIT_DOC.md`.
  - [ ] **Evidence:** Screenshot kết quả scan hoặc link tới file báo cáo đính kèm trên comment Jira.

**Task 2: Soát xét thay đổi cấu hình hạ tầng qua AWS Config**
- **Issue Type:** Task
- **Summary:** `[Compliance] Đánh giá thay đổi cấu hình hạ tầng lõi trên AWS Config`
- **Assignee:** Member 2
- **Label:** `Research`, `Docs`
- **Priority:** P1
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Đối chiếu resource timeline của AWS Config với checklist yêu cầu an toàn.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Truy cập AWS Config kiểm tra lịch sử biến động (Resource timeline) của hạ tầng lõi.
  - [ ] So sánh hiện trạng với `AUDIT_CHECKLIST.md`.
  - [ ] Đánh giá Pass/Fail và ghi chú nguyên nhân.
  - [ ] **Evidence:** Link tới file `AUDIT_CHECKLIST.md` đã được update.

**Task 3: Cập nhật & Quản lý Architecture Decision Records (ADR)**
- **Issue Type:** Task
- **Summary:** `[Docs] Thu thập và lưu vết tài liệu quyết định kiến trúc (ADR)`
- **Assignee:** Member 3
- **Label:** `Docs`
- **Priority:** P2
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Viết tóm tắt các quyết định thay đổi thiết kế và đẩy vào thư mục `/adr`.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Thu thập lý do và quyết định kiến trúc từ các buổi họp/Slack.
  - [ ] Soạn văn bản ADR chuẩn format.
  - [ ] Tạo PR merge tài liệu vào `/adr`.
  - [ ] **Evidence:** Link tới PR hoặc link tới file Markdown trên nhánh main.

**Task 4: Tổng hợp Báo cáo Evidence Hàng tuần**
- **Issue Type:** Task
- **Summary:** `[Docs] Đóng gói Báo cáo Evidence Audit tuần cho Friday Presentation`
- **Assignee:** Member 4
- **Label:** `Docs`, `Need-Review`
- **Priority:** P2
- **Estimate:** 6h (1.5 SP)
- **Mục tiêu:** Gom bằng chứng từ các thành viên khác vào ngày chốt báo cáo để xuất file.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Yêu cầu các thành viên Audit nộp link file evidence cá nhân.
  - [ ] Đóng gói nội dung, ảnh chụp, log vào báo cáo tổng hợp.
  - [ ] Xuất file report (PDF/Markdown) và đưa lên kho lưu trữ (SharePoint/Drive).
  - [ ] **Evidence:** Link thư mục Drive/SharePoint chứa báo cáo.

### 📌 Nhóm 2: Lên Yêu cầu & Nghiệm thu Task P0
**Task 5: Yêu cầu & Nghiệm thu CloudTrail + S3 Versioning**
- **Issue Type:** Task
- **Summary:** `[Log-Tracking] Nghiệm thu lưu vết CloudTrail an toàn vào S3`
- **Assignee:** Member 5
- **Label:** `Lab`, `Need-Review`
- **Priority:** P1
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Giao requirement cho DevOps và truy cập S3 kiểm chứng log CloudTrail được ghi nhận.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Gửi yêu cầu cấu hình CloudTrail sang board DevOps.
  - [ ] Kiểm tra Versioning trên S3 bucket chứa log đã được Enable.
  - [ ] Truy cập S3 bucket và xác nhận có log file mới sinh ra.
  - [ ] **Evidence:** Screenshot đường dẫn S3 có chứa log file, hoặc URL file evidence Markdown.

**Task 6: Yêu cầu & Nghiệm thu CloudWatch Logs cho EKS**
- **Issue Type:** Task
- **Summary:** `[Log-Tracking] Nghiệm thu log Control Plane EKS trên CloudWatch`
- **Assignee:** Member 6
- **Label:** `Lab`, `Need-Review`
- **Priority:** P1
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Giao requirement cho DevOps, kiểm tra Log Groups query được log EKS.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Gửi yêu cầu bật Control Plane logging cho DevOps.
  - [ ] Kiểm tra trên CloudWatch có Log Group `/aws/eks/...` chưa.
  - [ ] Chạy query Log Insight thành công đối với API Server/Authenticator log.
  - [ ] **Evidence:** Screenshot giao diện query Log Insight thành công đính kèm Jira.

**Task 7: Review Policy OpenSearch ISM**
- **Issue Type:** Task
- **Summary:** `[Compliance] Xác nhận chính sách Retention vòng đời log OpenSearch`
- **Assignee:** Member 7
- **Label:** `Research`, `Need-Review`
- **Priority:** P2
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Review mã JSON chính sách ISM (Index State Management) do DevOps cung cấp.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Nhận file JSON hoặc PR policy ISM từ DevOps.
  - [ ] Phân tích mã nguồn JSON để kiểm chứng chính sách xóa log có đúng hạn (vd 30 ngày) không.
  - [ ] Approve trên PR hoặc reply xác nhận trên Jira.
  - [ ] **Evidence:** Link tới PR hoặc hình ảnh comment Approve của team Audit.

**Task 8: Nghiệm thu Grafana Audit Dashboard**
- **Issue Type:** Task
- **Summary:** `[Log-Tracking] Phối hợp nghiệm thu biểu đồ log lỗi (401, 403) trên Grafana`
- **Assignee:** Member 8
- **Label:** `Lab`, `Need-Review`
- **Priority:** P1
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Đảm bảo Dashboard hiển thị đúng dữ liệu log truy cập trái phép.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Cung cấp logic lọc HTTP 401/403 cho DevOps.
  - [ ] Đăng nhập Grafana kiểm tra panel hiển thị.
  - [ ] Xác nhận dữ liệu biểu đồ nảy số khi có request lỗi.
  - [ ] **Evidence:** Screenshot dashboard Grafana hiển thị dữ liệu live.

### 📌 Các Task Chung (Shared Tasks)
**Task 9: Soạn thảo Ticket Uỷ quyền cho DevOps**
- **Issue Type:** Task
- **Summary:** `[Delegation] Soạn thảo chi tiết các ticket bàn giao cấu hình cho DevOps (CDO08)`
- **Assignee:** Shared (Các thành viên Nhóm 2)
- **Label:** `Docs`
- **Priority:** P1
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Viết file requirement Markdown chuyển sang board của team DevOps.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Lọc các công việc thuộc trách nhiệm DevOps từ `DELEGATED_TASKS_P0.md`.
  - [ ] Soạn file yêu cầu chi tiết (Markdown) đặt vào `audits/tickets/`.
  - [ ] Bàn giao ticket qua board của DevOps.
  - [ ] **Evidence:** Link tới các file ticket trong repo (nhánh main).

---

## 🔥 MANDATE #4: Forensic Audit Trail (DIRECTIVE #4)

**Epic: AUDIT-CDO07-MANDATE04-FORENSIC-FRAMEWORK**
- **Issue Type:** Epic
- **Summary:** `[MANDATE-04] Forensic Audit Trail - Dựng lại sự thật từ dấu vết`
- **Assignee:** Hoàng + Ty (CDO07)
- **Label:** `Mandate`, `P0`, `Need-Review`
- **Priority:** P0 (Critical)
- **Deadline:** 16/07/2026 (còn 2 ngày)
- **Estimate:** 17h total (Hoàng: 8h, Ty: 9h)
- **Mục tiêu:** Chứng minh khả năng dựng lại timeline ai-làm-gì-khi-nào từ audit log trong ≤10 phút, audit log không sửa/xóa được, và truy về danh tính cụ thể.

**Related Files:**
- Framework: [AUDIT-CDO07-MANDATE04-FORENSIC-FRAMEWORK.md](tickets/AUDIT-CDO07-MANDATE04-FORENSIC-FRAMEWORK.md)
- Delegated Ticket (IAM): [AUDIT-010-request-forensic-audit-permissions.md](tickets/AUDIT-010-request-forensic-audit-permissions.md)
- Delegated Ticket (IaC): [AUDIT-011-fix-cloudtrail-terraform.md](tickets/AUDIT-011-fix-cloudtrail-terraform.md)
- Runbook: [mentor-forensic-inspection.md](runbooks/mentor-forensic-inspection.md)

---

### 📌 MANDATE #4 - Subtasks (Hoàng + Ty)

**Task 19: [Hoàng] Verify Audit Log Coverage (AUD-17.1)**
- **Issue Type:** Task
- **Summary:** `[MANDATE-04] Verify CloudTrail + K8s Audit Log Coverage`
- **Assignee:** Hoàng (Nguyễn Duy Hoàng)
- **Label:** `Lab`, `Need-Review`, `P0`
- **Priority:** P0
- **Deadline:** 14/07/2026 EOD
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Xác nhận CloudTrail và K8s audit log đủ chi tiết để forensic, có log validation và không thể sửa/xóa.
**✅ Sub-tasks (Definition of Done):**
  - [ ] CloudTrail: `IsLogging = true`, `LogFileValidationEnabled = true`, `IsMultiRegionTrail = true`.
  - [ ] CloudTrail: Có ≥1 event trong 1h gần nhất.
  - [ ] K8s audit log: EKS Control Plane logging enabled, CloudWatch Log Group có stream mới trong 24h.
  - [ ] K8s audit log: Query thành công, có ≥1 event trong 1h gần nhất.
  - [ ] Document audit policy level và chi phí estimate.
  - [ ] **Evidence:** `docs/evidence/aud-17.1-cloudtrail-*.json`, `aud-17.1-eks-*.json`, `aud-17.1-query-test-result.md`.

**Task 20: [Hoàng] Verify Separation of Duties (AUD-17.3)**
- **Issue Type:** Task
- **Summary:** `[MANDATE-04] Verify IAM/RBAC Separation - Tamper-Evident`
- **Assignee:** Hoàng (Nguyễn Duy Hoàng)
- **Label:** `Research`, `Need-Review`, `P0`
- **Priority:** P0
- **Deadline:** 15/07/2026 AM
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Chứng minh operator không xóa được audit log của chính mình (quyền ghi/xóa tách khỏi người vận hành).
**✅ Sub-tasks (Definition of Done):**
  - [ ] IAM policy review: operator roles KHÔNG có `logs:Delete*`, `cloudtrail:StopLogging`, `s3:DeleteObject`.
  - [ ] S3 bucket policy có explicit Deny cho non-admin delete.
  - [ ] Live test ≥3 scenarios: operator role thử xóa log stream, stop CloudTrail, delete S3 object → tất cả AccessDenied ✅.
  - [ ] RBAC review (K8s): operator không edit được audit infrastructure.
  - [ ] **Evidence:** `docs/evidence/aud-17.3-iam-policies-review.json`, `aud-17.3-s3-bucket-policy.json`, `aud-17.3-separation-test-log.md`.

**Task 21: [Ty] Design Forensic Scenarios (AUD-17.2)**
- **Issue Type:** Task
- **Summary:** `[MANDATE-04] Thiết kế ≥5 kịch bản forensic + drill execution`
- **Assignee:** Ty
- **Label:** `Lab`, `Need-Review`, `P0`
- **Priority:** P0
- **Deadline:** 15/07/2026 PM
- **Estimate:** 5h (1.25 SP)
- **Mục tiêu:** Thiết kế ≥5 kịch bản forensic và drill ≥3 kịch bản với stopwatch (≤10 phút/sự kiện).
**✅ Sub-tasks (Definition of Done):**
  - [ ] ≥5 kịch bản documented: config change, unauthorized access, infra change, on-call action, secrets access.
  - [ ] Mỗi kịch bản có ground truth + query pattern.
  - [ ] Drill ≥3 kịch bản pass (≤10 phút mỗi kịch bản).
  - [ ] Drill log có timestamp thật, stopwatch, pass/fail, lessons learned.
  - [ ] Query patterns documented cho tái sử dụng.
  - [ ] **Evidence:** `docs/evidence/aud-17.2-scenario-*.md` (5 files), `aud-17.2-drill-log.md`, `aud-17.2-query-patterns.md`.

**Task 22: [Ty] Identity Mapping (AUD-17.4)**
- **Issue Type:** Task
- **Summary:** `[MANDATE-04] Identity Mapping - Truy về danh tính cụ thể`
- **Assignee:** Ty
- **Label:** `Research`, `Need-Review`, `P0`
- **Priority:** P0
- **Deadline:** 15/07/2026 PM
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Chứng minh mọi thay đổi lớn + on-call truy được về 1 danh tính cụ thể (không dùng chung account).
**✅ Sub-tasks (Definition of Done):**
  - [ ] ≥5 hành động gần nhất (trong 7 ngày) mapped thành công: Event → Timestamp → ARN → Real Person.
  - [ ] Identity mapping table với ≥5 hành động documented.
  - [ ] Scan IAM users, confirm không có shared account (shared-*, team-*, ops-admin).
  - [ ] ≥3 hành động on-call traced về person/bot (SSM StartSession).
  - [ ] **Evidence:** `docs/evidence/aud-17.4-identity-mapping.md`, `aud-17.4-infra-changes-7days.json`, `aud-17.4-bastion-access-7days.json`, `aud-17.4-iam-users-inventory.json`.

**Task 23: [Hoàng + Ty] Final Review & Runbook**
- **Issue Type:** Task
- **Summary:** `[MANDATE-04] Final Review + Runbook cho mentor`
- **Assignee:** Hoàng + Ty
- **Label:** `Docs`, `Need-Review`, `P0`
- **Priority:** P0
- **Deadline:** 16/07/2026 AM
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Review toàn bộ evidence quality, hoàn thiện runbook cho mentor, và final drill rehearsal.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Review toàn bộ evidence quality: timestamp thật, không placeholder.
  - [ ] Runbook cho mentor ready: `mentor-forensic-inspection.md`.
  - [ ] Final drill rehearsal (≥1 lần nữa).
  - [ ] Chi phí estimate documented: ~$3/week baseline, ~$19/week peak.
  - [ ] Chuẩn bị cho mentor inspection.
  - [ ] **Evidence:** All evidence files committed, runbook complete.

**Task 24: [CDO04] Fix CloudTrail Terraform (AUDIT-011) - DELEGATED**
- **Issue Type:** Task
- **Summary:** `[DELEGATED to CDO04] Fix CloudTrail Terraform - Tamper-Evident`
- **Assignee:** CDO04 (DevOps/IaC Owner)
- **Reporter:** Hoàng (Nguyễn Duy Hoàng) - CDO07
- **Label:** `Delegation`, `P0`, `Blocker`
- **Priority:** P0
- **Deadline:** 15/07/2026
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Fix 3 critical issues: `LogFileValidationEnabled = true`, `force_destroy = false`, S3 bucket policy với explicit Deny.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Terraform code đã sửa: `enable_log_file_validation = true`.
  - [ ] Terraform code đã sửa: `force_destroy = false`.
  - [ ] S3 bucket policy đã thêm: `DenyNonAdminDeleteObject` statement.
  - [ ] `terraform apply` thành công.
  - [ ] CDO07 verify bằng AWS CLI: `LogFileValidationEnabled = true`, `force_destroy = false`, bucket policy có Deny.
  - [ ] **Evidence:** CDO07 lưu evidence sau khi verify.
  - **Related:** [AUDIT-011-fix-cloudtrail-terraform.md](tickets/AUDIT-011-fix-cloudtrail-terraform.md)

**Task 25: [CDO08] Grant Forensic Audit Permissions (AUDIT-010) - DELEGATED**
- **Issue Type:** Task
- **Summary:** `[DELEGATED to CDO08] Grant Forensic Audit Read-Only Permissions`
- **Assignee:** CDO08 (Security/IAM Owner)
- **Reporter:** Trần Minh Quang - CDO07
- **Label:** `Delegation`, `P0`, `Blocker`
- **Priority:** P0
- **Deadline:** 15/07/2026
- **Estimate:** 1h (0.25 SP)
- **Mục tiêu:** Cấp quyền read-only cho SSO Permission Set `TF4-AuditReadOnlyAndAnalyze` phục vụ forensic audit.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Permission Set `TF4-AuditReadOnlyAndAnalyze` đã cập nhật với 11 quyền forensic.
  - [ ] CDO07 chạy lại được AWS CLI checks không còn `AccessDenied`.
  - [ ] CDO07 validate CloudTrail log integrity.
  - [ ] CDO07 map Identity Store user ID về người dùng cụ thể.
  - [ ] **Evidence:** CDO07 lưu evidence sau khi verify.
  - **Related:** [AUDIT-010-request-forensic-audit-permissions.md](tickets/AUDIT-010-request-forensic-audit-permissions.md)

### 📌 Nhóm 3: EPIC-01 Gap Fixes (Primary Owned)
*Các task mà CDO07 trực tiếp sở hữu (Owned) theo đánh giá rủi ro EPIC-01.*

**Task 10: Thiết lập SLO Alerts (OBS-01)**
- **Issue Type:** Task
- **Summary:** `[Observability] Thiết lập SLI queries, Grafana alerts và Alertmanager receiver (OBS-01)`
- **Assignee:** Shared
- **Label:** `Lab`, `Need-Review`
- **Priority:** P1
- **Estimate:** 8h (2 SP)
- **Mục tiêu:** Khắc phục tình trạng missing SLO alerts cho checkout/payment/Kafka/DB.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Lấy thông tin SLO thresholds từ team CDO08.
  - [ ] Viết SLI queries cho các dịch vụ trọng tâm trên.
  - [ ] Set up Alertmanager và kích hoạt thử (fire alert) gửi về Slack.
  - [ ] **Evidence:** Link file `{NNN}-obs-01-slo-alert-dashboard-baseline.md` chứa screenshot alert nổ trên Slack.

**Task 11: Redact dữ liệu nhạy cảm (OBS-02)**
- **Issue Type:** Task
- **Summary:** `[Observability] Redact dữ liệu nhạy cảm (PII/payment/prompt) trong logs/traces (OBS-02)`
- **Assignee:** Shared
- **Label:** `Lab`, `Need-Review`
- **Priority:** P1
- **Estimate:** 8h (2 SP)
- **Mục tiêu:** Ẩn các thông tin nhạy cảm (order/payment/email/AI prompt) trong telemetry.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Review cấu hình telemetry collection để đảm bảo rule redact được enable.
  - [ ] Search thử logs/traces trên OpenSearch/Jaeger, xác minh thông tin đã biến thành `***`.
  - [ ] Đảm bảo correlation IDs không bị xóa nhầm.
  - [ ] **Evidence:** Link file `{NNN}-ai-01-obs-02-telemetry-redaction.md` có chứa screenshot log đã bị che.

**Task 12: Cập nhật CODEOWNERS và Templates (OBS-03)**
- **Issue Type:** Task
- **Summary:** `[Auditability] Sửa CODEOWNERS và tạo template ADR/runbook/postmortem (OBS-03)`
- **Assignee:** Shared
- **Label:** `Docs`, `Need-Review`
- **Priority:** P2
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Đảm bảo CODEOWNERS trỏ đúng đường dẫn và team có đủ template mẫu.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Cập nhật path trong file `CODEOWNERS`.
  - [ ] Viết template chuẩn cho ADR, runbook, postmortem.
  - [ ] Tạo PR merge vào main.
  - [ ] **Evidence:** Link file `{NNN}-obs-03-repo-auditability-artifacts.md` chứa link PR.

### 📌 Nhóm 4: EPIC-01 Evidence Verify (Backstop)
*CDO07 đóng vai trò Audit Backstop: KHÔNG gap nào từ các nhóm khác được chuyển sang Done nếu CDO07 chưa verify evidence.*

**Task 13: Verify Evidence cho Security Gaps (CDO-08)**
- **Issue Type:** Task
- **Summary:** `[Verify] Kiểm chứng bằng chứng Security Gaps (SEC-01, SEC-02) từ CDO-08`
- **Assignee:** Shared
- **Label:** `Docs`, `Need-Review`
- **Priority:** P1
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Xác nhận 100% không còn unauthenticated access và không lộ credentials.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Review evidence file của CDO08 cho SEC-01 (Grafana/OpenSearch).
  - [ ] Review evidence file của CDO08 cho SEC-02 (Secret credentials).
  - [ ] Đóng dấu Approve nếu evidence đầy đủ.
  - [ ] **Evidence:** Comment xác nhận trên issue/PR của CDO08.

**Task 14: Verify Evidence cho Reliability/K8S Gaps (CDO-08)**
- **Issue Type:** Task
- **Summary:** `[Verify] Kiểm chứng bằng chứng Reliability/K8S Gaps (REL-01/02/03/06, K8S-01/04) từ CDO-08`
- **Assignee:** Shared
- **Label:** `Docs`, `Need-Review`
- **Priority:** P1
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Verify tính toàn vẹn của Kafka event, DB data loss, ADR và độ bền dữ liệu.
**✅ Sub-tasks (Definition of Done):**
  - [x] Đọc và verify các evidence files về Kafka/DB (REL-01, REL-02, REL-03, REL-06).
  - [x] Đọc và verify evidence probes và HA (K8S-01, K8S-04).
  - [x] **Evidence:** Comment Approve xác nhận trên các file evidence này.

**Task 15: Verify Evidence cho Cost/Performance Gaps (CDO-04)**
- **Issue Type:** Task
- **Summary:** `[Verify] Kiểm chứng bằng chứng Cost Gaps (COST-02, K8S-03) từ CDO-04`
- **Assignee:** Shared
- **Label:** `Docs`, `Need-Review`
- **Priority:** P1
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Xác nhận quyết định retention cho observability và resource quota compatibility.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Đọc evidence `017-cost-02` (retention decision).
  - [ ] Đọc evidence `018-k8s-03` (resource quota compatibility).
  - [ ] **Evidence:** Comment Approve xác nhận trên các file evidence.

**Task 16: Verify Evidence cho AI Gaps (AIO-01)**
- **Issue Type:** Task
- **Summary:** `[Verify] Kiểm chứng bằng chứng AI Gaps (AI-01, AI-02) từ AIO-01`
- **Assignee:** Shared
- **Label:** `Docs`, `Need-Review`
- **Priority:** P1
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Xác nhận không lộ prompt/PII và AI eval/fallback document.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Verify không lộ thông tin nhạy cảm qua evidence của AI-01.
  - [ ] Đọc và phê duyệt AI eval/fallback doc (AI-02).
  - [ ] **Evidence:** Comment Approve trên evidence file của AIO-01.

**Task 17: Review Format toàn bộ Evidence (ALL)**
- **Issue Type:** Task
- **Summary:** `[Verify] Review toàn bộ evidence file đảm bảo đúng template và naming convention`
- **Assignee:** Audit Lead / PM
- **Label:** `Docs`
- **Priority:** P1
- **Estimate:** 4h (1 SP)
- **Mục tiêu:** Đảm bảo tất cả evidence file của EPIC-01 đều có 4 section bắt buộc.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Check file names phải tuân thủ `{NNN}-{slug}.md`.
  - [ ] Đảm bảo nội dung có đủ 4 mục theo format yêu cầu.
  - [ ] Báo cáo PM/Lead các file lỗi để yêu cầu fix.
  - [ ] **Evidence:** Tick 100% check-list này và để lại link report vào comment Jira.

**Task 18: Kiểm toán KMS CMK (Key Policy & Rotation)**
- **Issue Type:** Task
- **Summary:** `[Compliance] Kiểm tra Key Policy và Auto Rotation của KMS CMK cho CloudTrail`
- **Assignee:** Member 4
- **Label:** `Research`, `Need-Review`
- **Priority:** P1
- **Estimate:** 2h (0.5 SP)
- **Mục tiêu:** Đảm bảo dữ liệu CloudTrail (và các evidence khác) được mã hóa bằng CMK an toàn, không bị over-privileged quyền Decrypt.
**✅ Sub-tasks (Definition of Done):**
  - [ ] Thu thập ARN của KMS CMK từ team DevOps.
  - [ ] Kiểm tra Key Policy, đảm bảo giới hạn chặt chẽ quyền `kms:Decrypt`.
  - [ ] Xác nhận tính năng Key Rotation đã được bật (`aws kms get-key-rotation-status`).
  - [ ] **Evidence:** Screenshot cấu hình Key Policy hoặc output lệnh AWS CLI.

---

## ⏰ 3. Quy tắc Cập nhật & Nghiệm thu (Bắt buộc tuân thủ)

### ⭐ Daily Update (Cập nhật Hàng ngày)
Mỗi thành viên mỗi ngày phải để lại dấu vết trên Jira issue đang làm trước **21:00** theo format:
```text
📅 [Ngày]
✅ Hôm nay làm: (VD: Đã đọc xong tài liệu Access Analyzer và nháp kết quả)
🔜 Mai làm: (VD: Tổng hợp báo cáo vào file MD)
⛔ Vướng (nếu có): (VD: Chưa có quyền read IAM -> đánh label Blocker)
```
*(Nếu không cập nhật hoặc không chuyển status, coi như hôm đó không đóng góp - no trace = no work).*

### ✅ Definition of Done (Tiêu chuẩn Hoàn thành Issue)
Một Task (issue) chỉ được kéo sang cột **Done** khi thỏa mãn:
1. Hoàn thành toàn bộ Sub-task bên trong.
2. **Có Bằng Chứng (Evidence):** Phải có ít nhất 1 link/text/screenshot nằm gọn trong comment hoặc description (ví dụ link tới Git, ảnh chụp query log). Không để dạng đính kèm file (attachment không export được).
3. Được PM/Lead xác nhận (nếu không đạt sẽ bị trả về *In Review*).
4. Phù hợp để PM xuất Weekly Export gửi Trainer.
