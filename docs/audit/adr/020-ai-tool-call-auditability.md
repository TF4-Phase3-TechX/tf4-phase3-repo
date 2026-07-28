# ADR-020: Auditability cho AI và Tool Call

- **Ngày:** 2026-07-28
- **Trạng thái:** Proposed
- **Tác giả:** Bá Huân - CDO07 Auditability
- **Đồng phê duyệt AIE:** Chờ thành viên AIE ký tên
- **Pillar liên quan:** Auditability, AI, Security, Reliability
- **Mandate:** MANDATE-14

## 1. Bối cảnh

MANDATE-14 yêu cầu hệ thống chứng minh tính đáng tin của AI bằng số liệu và
đồng thời ghi lại lời gọi AI/tool để phục vụ kiểm toán. Bản ghi phải hỗ trợ trả
lời một sự kiện AI nào đã xảy ra, quyết định an toàn là gì và có yêu cầu xác
nhận hay không, nhưng không được làm lộ prompt, response, PII, credential hoặc
tool input.

CDO07 đã xác minh runtime hiện tại có thể liên kết một `trace_id` từ
`product-reviews` qua CloudWatch, Firehose, S3 WORM và Athena. Cần ghi nhận
kiến trúc này thành quyết định chung để AIE sở hữu việc phát sinh event đúng
schema, còn CDO07 xác minh độc lập tính đầy đủ và bất biến của evidence.

ADR này không thay thế ADR-014 của AIE về tiêu chuẩn eval. Hai quyết định có
phạm vi và ownership riêng.

## 2. Quyết định

### 2.1. Canonical audit event

Mỗi lời gọi AI/tool thuộc phạm vi kiểm toán phải phát sinh một event
`ai_tool_audit`. Payload canonical của event bắt buộc có tám trường:

```text
log_type
trace_id
surface
model_id
tool_name
tool_input_redacted
safety_decision
confirmation_status
```

Quy ước:

- `tool_input_redacted` chỉ ghi marker redaction, không ghi raw input.
- `safety_decision` dùng tập giá trị giới hạn như `allow`, `block`, `refuse`
  hoặc `provider_unavailable`.
- `confirmation_status` tách độc lập khỏi output của model và dùng các trạng
  thái `not_required`, `confirmed` hoặc `rejected`.
- `trace_id` là khóa tương quan chính giữa application telemetry và evidence.
- Không ghi prompt, response, PII, credential, confirmation token hoặc raw tool
  arguments.
- OTel envelope có thể bổ sung metadata kỹ thuật như timestamp, service, pod,
  image hoặc span; metadata bổ sung vẫn phải tuân thủ nguyên tắc không ghi nội
  dung và dữ liệu nhạy cảm.

### 2.2. Đường lưu trữ

```text
AI service
  -> OTel exact filter: log_type = ai_tool_audit
  -> CloudWatch Logs
  -> CloudWatch subscription
  -> Firehose
  -> S3 Versioning + Object Lock COMPLIANCE
  -> Glue/Athena
```

- CloudWatch là bản vận hành để tìm kiếm gần thời gian thực.
- S3 Object Lock `COMPLIANCE` là evidence authority, retention tối thiểu 90
  ngày.
- Athena là lớp truy vấn forensic theo partition thời gian và `trace_id`.
- Event `allow` và `provider_unavailable` đều được giữ để chứng minh cả luồng
  thành công và fallback đều có thể kiểm toán.

### 2.3. Quyền và ownership

- AIE chịu trách nhiệm emit event đúng schema tại boundary của AI/tool.
- CDO07 dùng role audit read/query để kiểm tra CloudWatch, Firehose, S3 và
  Athena.
- CDO07 không có quyền sửa hoặc xóa audit object, thay đổi retention hay bypass
  Object Lock.
- Thay đổi hạ tầng phải đi qua team Platform/IaC theo separation of duties.

## 3. Lý do

| Mục tiêu | Cách quyết định đáp ứng |
|---|---|
| Truy vết | `trace_id` liên kết application event với CloudWatch, S3 và Athena |
| Data minimization | Chỉ lưu metadata canonical và redaction marker |
| Tamper evidence | S3 Versioning và Object Lock `COMPLIANCE` 90 ngày |
| Forensic query | Athena truy vấn evidence theo partition và `trace_id` |
| Separation of duties | AIE phát sinh event, CDO07 xác minh, Platform quản lý hạ tầng |
| Reliability | Cả provider success và provider fallback đều được ghi nhận |

## 4. Phương án đã cân nhắc

| Phương án | Kết luận |
|---|---|
| Chỉ giữ log trong CloudWatch | Không chọn vì chưa đủ làm evidence authority bất biến |
| Ghi raw prompt/response để điều tra | Không chọn vì tăng rủi ro PII, credential và prompt leakage |
| Application ghi trực tiếp vào S3 | Không chọn vì tăng coupling và cấp quyền ghi storage cho workload |
| Chỉ dùng OpenSearch | Không chọn làm evidence authority vì retention và immutability không tương đương S3 WORM |

## 5. Hệ quả

### Tích cực

- Mentor có thể tái dựng một AI/tool event bằng cùng `trace_id`.
- Evidence vẫn tồn tại khi provider lỗi và application fallback.
- Nội dung người dùng không bị sao chép vào audit storage.
- CDO07 có thể xác minh độc lập mà không có quyền thay đổi evidence.

### Trade-off và rủi ro

- Firehose tạo độ trễ ngắn trước khi event xuất hiện trong S3/Athena.
- Schema canonical phải được quản lý tương thích khi thêm surface hoặc tool.
- Athena phải dùng partition thời gian để giảm dữ liệu quét và chi phí.
- ADR chỉ chứng minh kiến trúc Auditability; kết quả eval và hidden cases vẫn
  thuộc evidence của AIE.

## 6. Điều kiện phê duyệt

ADR chuyển từ `Proposed` sang `Accepted` khi:

1. Một reviewer AIE có tên cụ thể xác nhận schema và điểm emit event.
2. CDO07 xác nhận lại event thành công và fallback không chứa dữ liệu bị cấm.
3. Script repro trả `PASS` cho CloudWatch, Firehose, S3 WORM và Athena.
4. PR chứa ADR nhận approval theo quy trình repository.

## 7. Evidence và tham chiếu

- [CDO07 MANDATE-14 AI/tool audit evidence](../evidence/CDO07-MANDATE-14-AI-TOOL-AUDIT-EVIDENCE.md)
- [Runtime artifacts](../evidence/mandate-14/runtime/)
- [Script xác minh E2E](../../../scripts/audit/verify-ai-tool-audit-e2e.ps1)
- [MANDATE-14](../../../mandates/MANDATE-14-ai-eval-standard.md)
- [ADR-001: Separation of Duties](001-audit-platform-separation.md)
- [ADR-017: Tamper-Evident Logging](017-eks-cloudtrail-tamper-evident-logging.md)
- [AIE ADR-014: Standard AI Evaluation](../../aio1/mandate-14/ADR-014-standard-ai-evaluation.md)

## 8. Approval

| Vai trò | Người phê duyệt | Trạng thái | Ngày |
|---|---|---|---|
| Tác giả / CDO07 | Bá Huân | Đã soạn thảo | 2026-07-28 |
| Reviewer AIE | Chờ điền tên | Pending | - |
| Repository approver | Chờ PR approval | Pending | - |
