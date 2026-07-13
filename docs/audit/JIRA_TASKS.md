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
  - [ ] Đọc và verify các evidence files về Kafka/DB (REL-01, REL-02, REL-03, REL-06).
  - [ ] Đọc và verify evidence probes và HA (K8S-01, K8S-04).
  - [ ] **Evidence:** Comment Approve xác nhận trên các file evidence này.

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
