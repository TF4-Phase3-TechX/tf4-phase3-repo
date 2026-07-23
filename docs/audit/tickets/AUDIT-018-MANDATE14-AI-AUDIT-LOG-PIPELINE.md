# [TASK-68][AUDIT-018][P0] Cấu hình pipeline gom AI Audit Log tập trung cho Mandate 14

| Thuộc tính | Giá trị |
|---|---|
| Trạng thái | `TO DO` |
| Source task | Task 68 — docs plan cấu hình pipeline gom log AI Audit |
| Jira ID | Gán key khi tạo ticket trên Jira `AI MANDATE #14` |
| Reporter / Verifier | CDO-07 (Auditability) |
| Assignee | CDO-08 / Platform |
| Data producer | AIO — `product-reviews` |
| Cost reviewer | CDO-04 |
| Priority | P0 — blocker cho phần Auditability của Mandate 14 |
| Due date | Trước phiên nghiệm thu Mandate 14 |
| Design | [Mandate 14 AI Audit Log Pipeline Plan](../planning/MANDATE-14-AI-AUDIT-LOG-PIPELINE-PLAN.md) |
| Evidence location | `docs/audit/evidence/mandate-14-ai-audit/` |

## 1. Summary để tạo Jira

**Summary**

```text
[MANDATE-14][CDO-07][P0] Route ai_tool_audit logs từ EKS qua OTel đến OpenSearch, CloudWatch và S3 WORM
```

**Description ngắn**

```text
AIO đã chuẩn hóa event ai_tool_audit với 8 trường canonical ở product-reviews.
Yêu cầu CDO-08/Platform triển khai bằng IaC pipeline riêng:

Pod -> OTel Collector -> OpenSearch hot copy
                     -> CloudWatch Logs -> Firehose -> S3 Object Lock

Routing bắt buộc dùng log.attributes["log_type"] == "ai_tool_audit".
CDO-07 chỉ nhận quyền read/query và thực hiện nghiệm thu độc lập. Không lưu raw
prompt/response/review/user/session/token/tool payload. Chi tiết thiết kế,
retention, IAM, rollout và acceptance criteria nằm trong docs plan liên kết.
```

## 2. Bối cảnh

Mandate 14 yêu cầu chứng minh Auditability cho AI/tool-call. AIO đã merge code
phát event `ai_tool_audit` với đúng tám trường:

```text
log_type, trace_id, surface, model_id, tool_name,
tool_input_redacted, safety_decision, confirmation_status
```

Hiện tại log ứng dụng đi qua OTel Collector vào index OpenSearch chung
`otel-logs-*`. Chưa có:

- filter/routing dành riêng cho `ai_tool_audit`;
- CloudWatch Log Group riêng;
- S3 archive có Object Lock;
- retention policy dành cho AI audit;
- resource-scoped IAM cho service roles và Audit team;
- runtime evidence canonical sau deploy.

Runtime snapshot hiện có chỉ chứng minh OTLP wiring và log-to-trace correlation,
không đủ để đóng Mandate 14.

## 3. User story

Là thành viên **CDO-07 Audit**, tôi cần:

- truy vấn độc lập các AI/tool-call decisions theo trace và thời gian;
- chứng minh log được route đúng, giữ đủ lâu và không chứa customer/AI content;
- có một bản WORM không thể bị sửa/xóa trong thời hạn retention;
- đọc evidence mà không có quyền tạo, sửa hoặc xóa evidence;

để nghiệm thu phần Auditability của Mandate 14 theo Separation of Duties và
Least Privilege.

## 4. Phạm vi implement

### 4.1. OTel Collector / Helm

- Pin `opentelemetry-collector-contrib` bằng version và image digest.
- Xác nhận distribution có `filterprocessor`, `awscloudwatchlogsexporter`,
  `opensearchexporter` và `file_storage`.
- Ghi nhận `awscloudwatchlogsexporter` đang ở stability level alpha; chỉ rollout
  sau staging/recovery test và đặt CloudWatch/S3 branch sau feature flag.
- Thêm dedicated logs pipeline.
- Route bằng:

  ```text
  log.attributes["log_type"] == "ai_tool_audit"
  ```

- Giữ OTLP attributes khi export CloudWatch (`raw_log: false`).
- Thêm persistent sending queue, retry và capacity limit.
- Thêm safe schema/privacy validation; error record không chứa raw content.
- Thêm NetworkPolicy và service account role riêng cho collector.
- Shadow dual-write trước khi loại AI audit khỏi general index.

File dự kiến:

- `techx-corp-chart/values.yaml`
- `deploy/values-observability.yaml`
- chart templates/values schema liên quan nếu cần

### 4.2. OpenSearch

- Tạo index pattern `ai-tool-audit-*`.
- Tạo index template/mapping cho canonical fields.
- Tạo read alias `ai-tool-audit-read`.
- Tạo ISM delete sau 14 ngày.
- Bật authentication/FGAC hoặc đóng security gap tương đương.
- OTel chỉ có quyền write vào dedicated index.
- Audit chỉ có `read/search/view_index_metadata`.
- Không coi OpenSearch là evidence authority.

Nếu `DISABLE_SECURITY_PLUGIN=true` vẫn còn tại nghiệm thu, phần OpenSearch
least-privilege là blocker hoặc phải được ghi rõ là deferred risk có owner/date;
CloudWatch/S3 vẫn phải đạt.

### 4.3. AWS storage / Terraform

Tạo resource bằng Terraform, không tạo tay:

- CloudWatch Log Group `/tf4/mandate-14/ai-tool-audit`, retention 30 ngày.
- CloudWatch validation/error Log Group, retention 30 ngày.
- Firehose delivery stream `tf4-ai-audit-logs`.
- Firehose delivery error Log Group, retention 14 ngày.
- S3 bucket `tf4-ai-audit-logs-<account-id>`:
  - Versioning enabled;
  - Object Lock `COMPLIANCE` 90 ngày;
  - total retention 365 ngày;
  - Public Access Block;
  - TLS-only bucket policy;
  - encryption bằng dedicated KMS CMK;
  - lifecycle theo design sau khi Cost review;
  - `force_destroy=false`.
- CloudWatch subscription filter từ dedicated Log Group sang Firehose.
- Firehose bật CloudWatch Logs decompression + message extraction, GZIP output
  và error prefix riêng; không double-compress subscription payload và không
  dùng stream này cho Vended Logs/direct PUT.
- Outputs cho resource names/ARNs cần dùng trong verification.

File dự kiến:

- `infra/terraform/ai-audit-logs.tf`
- `infra/terraform/outputs.tf`
- variable/policy files liên quan nếu cần

Không tái sử dụng prefix/schema EKS control-plane audit cho AI audit vì hai loại
record có schema, owner và query contract khác nhau.

### 4.4. IAM / SSO

Tạo các role/policy tách biệt:

1. OTel Collector -> CloudWatch Logs.
2. CloudWatch Logs -> đúng Firehose stream.
3. Firehose -> đúng S3 bucket/prefix + KMS encrypt.
4. CDO-07 SSO -> read/query đúng CloudWatch, S3 prefix, KMS key và OpenSearch
   index.

Yêu cầu:

- Không cấp `s3:*`, `logs:*`, `es:*` hoặc `kms:*`.
- Không cấp data-plane read cho collector/Firehose.
- Không cấp write/delete cho CDO-07.
- Không cấp `s3:BypassGovernanceRetention`,
  `s3:PutObjectRetention`, `s3:PutObjectLegalHold`.
- Trust policy service role có `aws:SourceArn`/`aws:SourceAccount` phù hợp.
- `s3:ListBucket` có prefix condition.
- Action console list/describe buộc dùng `Resource: "*"` phải tách statement và
  có justification.
- Validate policy bằng IAM Access Analyzer.

Update documentation:

- `docs/iam/group/cdo07/TF4-AuditReadOnlyAndAnalyze.md`
- evidence IAM/negative tests tại
  `docs/audit/evidence/mandate-14-ai-audit/`.

### 4.5. Monitoring

Tạo dashboard/alarms tối thiểu:

- OTel audit exporter send failure > 0.
- Persistent queue >= 80%.
- Có AI/tool activity nhưng 15 phút không có audit event.
- Schema/privacy validation failure.
- Firehose delivery failure/throttling.
- CloudWatch -> S3 lag > 10 phút.
- OpenSearch rejected document.

Alert phải chứa resource, time window và trace ID mẫu nếu có; không chứa prompt,
response hoặc tool payload.

## 5. Retention và data classification

| Store | Retention | Vai trò |
|---|---|---|
| OpenSearch `ai-tool-audit-*` | 14 ngày | Hot searchable copy |
| CloudWatch `/tf4/mandate-14/ai-tool-audit` | 30 ngày | Operational query/alert + Firehose source |
| S3 AI audit bucket | 365 ngày tổng; WORM COMPLIANCE tối thiểu 90 ngày | Evidence authority |
| Firehose errors | 14 ngày | Delivery troubleshooting |
| Safe validation errors | 30 ngày | Schema/privacy monitoring |

Classification: audit metadata nội bộ. Dù payload không chứa raw content, quyền
vẫn bị giới hạn vì `trace_id`, model/tool và safety decision có thể tiết lộ hành
vi hệ thống.

Giảm retention chỉ được thực hiện bằng change ticket/ADR mới có CDO-04 cost
review, CDO-08 approval và CDO-07 sign-off.

## 6. Kế hoạch thực hiện

### Subtask 1 — Preflight và cost

- Đo event rate, average/p95 event size trên synthetic/runtime window.
- Ước tính CloudWatch ingest/storage, Firehose, S3/KMS và OpenSearch storage.
- Pin collector version/digest.
- Chạy config validation và xác nhận component support.

**Owner:** CDO-04 + CDO-08

### Subtask 2 — AWS storage và service roles

- Implement Terraform resources.
- Chạy `terraform fmt`, `terraform validate`, plan.
- Security/IAM review trước apply.
- Apply theo workflow hiện hữu.

**Owner:** CDO-08

### Subtask 3 — OpenSearch security và lifecycle

- Index template, role, read alias, ISM 14 ngày.
- FGAC/authentication và NetworkPolicy.
- Negative write/delete tests cho Audit role.

**Owner:** CDO-08

### Subtask 4 — OTel shadow route

- Deploy dedicated pipeline nhưng giữ AI audit trong general index.
- Phát synthetic test matrix.
- Đối soát parity giữa general/dedicated/CloudWatch/S3.

**Owner:** CDO-08; AIO cung cấp request/test cases

### Subtask 5 — Cutover

- Chỉ khi parity = 100%, drop AI audit khỏi general pipeline.
- Monitor tối thiểu 24 giờ.
- Không xóa storage/resource khi rollback.

**Owner:** CDO-08

### Subtask 6 — Audit verification

- CDO-07 tự query bằng SSO read-only.
- Chạy functional, privacy, retention, Object Lock và negative IAM tests.
- Gắn evidence và ký kết quả.

**Owner:** CDO-07

## 7. Test matrix bắt buộc

Chỉ dùng synthetic IDs/content.

| Case | Event mong đợi |
|---|---|
| Product Q&A thành công | `tool_name=bedrock.converse`, `safety_decision=allow`, `confirmation_status=not_required` |
| Injection/safety block | `safety_decision=block` |
| Unsupported/out-of-scope | `safety_decision=refuse` |
| Provider timeout/failure | `safety_decision=provider_unavailable` |
| Cart proposal chưa confirm/reject | `tool_name=modify_cart`, `confirmation_status=rejected` khi boundary từ chối |
| Cart action đã confirm | `tool_name=modify_cart`, `confirmation_status=confirmed` |
| Application log bình thường | Không xuất hiện trong dedicated AI audit stores |
| Malformed audit candidate | Safe validation alert, không raw content |
| Collector exporter tạm lỗi | Event được queue, alarm fire, giao lại sau recovery |

## 8. Acceptance Criteria

### AC-01 — Canonical routing

- [ ] Collector route dựa trên
      `log.attributes["log_type"] == "ai_tool_audit"`.
- [ ] Event hợp lệ giữ đủ tám canonical fields.
- [ ] Non-audit application logs không đi vào dedicated storage sau cutover.
- [ ] Malformed event không bị âm thầm route general-only.

### AC-02 — End-to-end delivery

- [ ] 100% event của controlled test có trong CloudWatch.
- [ ] 100% event của controlled test có trong S3 sau tối đa 10 phút.
- [ ] 100% event hợp lệ có trong OpenSearch dedicated index khi branch này bật.
- [ ] `trace_id` correlation được với đúng Jaeger trace.
- [ ] p95 CloudWatch/OpenSearch delivery <= 2 phút trong controlled test.

### AC-03 — Privacy

- [ ] Không sink nào có raw prompt, response, review, system prompt, user ID,
      session ID, confirmation token hoặc tool input.
- [ ] `tool_input_redacted` luôn là
      `{"redacted": true, "content_logged": false}`.
- [ ] Validation/error logs không echo giá trị field vi phạm.

### AC-04 — Retention và integrity

- [ ] OpenSearch ISM = 14 ngày.
- [ ] CloudWatch retention = 30 ngày, không `Never Expire`.
- [ ] S3 Versioning = `Enabled`.
- [ ] S3 Object Lock = `COMPLIANCE`, default 90 ngày.
- [ ] S3 total lifecycle retention = 365 ngày.
- [ ] Encryption và Public Access Block được bật.
- [ ] Synthetic object `head-object` có retain-until date đúng.
- [ ] Delete object version bằng non-authorized role trả `AccessDenied`.

### AC-05 — Least privilege

- [ ] CDO-07 read/query được đúng resources.
- [ ] CDO-07 không Put/Delete/change retention.
- [ ] Collector không read/query log hoặc S3.
- [ ] Collector không ghi CloudWatch Log Group khác.
- [ ] Firehose không read object hoặc ghi prefix khác.
- [ ] Platform runtime role không đọc AI audit data.
- [ ] IAM Access Analyzer không có finding High/Critical chưa xử lý.

### AC-06 — Reliability và monitoring

- [ ] Persistent queue sống qua collector restart trong staging test.
- [ ] Exporter/queue/Firehose/schema/privacy alarms đã test.
- [ ] Recovery giao đủ event; duplicate nếu có được ghi nhận.
- [ ] Theo dõi production/cutover đủ 24 giờ, không có P0/P1 mở.

### AC-07 — Evidence và sign-off

- [ ] PR/commit link cho Terraform/Helm/IAM.
- [ ] `terraform plan` và Helm render/config validation.
- [ ] Query result/screenshot có đủ canonical fields từ ba sink.
- [ ] Retention/Object Lock/encryption/Public Access Block output.
- [ ] Positive và negative access-test output.
- [ ] Cost estimate + actual first-24h observation.
- [ ] Audit evidence pack được tạo tại
      `docs/audit/evidence/mandate-14-ai-audit/` sau canonical deploy.
- [ ] CDO-08 deployment sign-off và CDO-07 independent audit sign-off.

## 9. Evidence cần attach vào Jira

1. Link plan này và PR/commit implement.
2. Collector image digest và component/version inventory.
3. Sanitized collector config hoặc Helm rendered excerpt.
4. Terraform plan/apply result, không chứa secret.
5. OpenSearch index template, ISM và role mapping.
6. CloudWatch Log Group retention output.
7. Firehose delivery status/error metric.
8. S3 versioning, Object Lock, encryption, public access và lifecycle output.
9. Một synthetic event được correlation bằng cùng `trace_id` ở:
   - OpenSearch;
   - CloudWatch;
   - S3;
   - Jaeger.
10. Privacy negative search.
11. IAM positive/negative test results.
12. Queue restart/recovery test.
13. Cost observation sau 24 giờ.

Không attach workstation path, credential, raw customer content, raw model
prompt/response hoặc confirmation token.

## 10. Rollout gate

| Gate | Điều kiện để qua |
|---|---|
| G0 — Design | CDO-07, CDO-08, CDO-04 review retention/IAM/cost |
| G1 — Plan | Terraform validate/plan và Helm config/render pass |
| G2 — Staging | Test matrix, privacy, queue recovery và negative IAM pass |
| G3 — Shadow production | 24h parity 100%, không P0/P1 |
| G4 — Cutover | Audit event được bỏ khỏi general index, dedicated route ổn định |
| G5 — Close | Evidence đầy đủ và CDO-07 sign-off |

Không bỏ qua gate bằng screenshot đơn lẻ. Runtime evidence phải có timestamp,
cluster/namespace, identity đã dùng và command/query có thể tái tạo.

## 11. Rollback

- Revert collector config về commit trước và giữ/re-enable AI audit trong general
  pipeline.
- Dừng đường ghi mới nếu cần, nhưng không xóa Log Group, Firehose, S3 bucket hoặc
  object.
- Không chạy `terraform destroy` đối với bucket Object Lock.
- Nếu mapping OpenSearch sai, tạo generation/index mới và đổi alias.
- Mở incident nếu có lost event, queue overflow, PII/content leak hoặc retention
  bị thay đổi ngoài change process.

## 12. Dependencies và blockers

| Dependency | Trạng thái đầu vào | Owner |
|---|---|---|
| Canonical logger đã merge/package | Done ở code; cần deploy/recapture | AIO |
| OTel component compatibility / CloudWatch exporter alpha | Chưa xác nhận version/digest và recovery behavior | CDO-08 |
| OpenSearch FGAC/security | Baseline đang disabled | CDO-08 |
| IAM/SSO attachment | Chưa có policy AI audit scoped | CDO-08 |
| Cost estimate theo AI event volume | Chưa có | CDO-04 |
| Live canonical sample | Pending deployment | AIO + CDO-08 |

Nếu bất kỳ blocker nào làm chậm quá 24 giờ, Reporter escalate PM/Lead theo
[ADR-001 Separation of Duties](../adr/001-audit-platform-separation.md); CDO-07
không tự apply hạ tầng để vượt blocker.

## 13. Definition of Done

Ticket chỉ được chuyển `Done` khi toàn bộ AC-01 đến AC-07 đạt, evidence có thể
tái tạo và không còn P0/P1. Việc merge docs plan hoặc merge canonical logger
không đồng nghĩa pipeline production đã hoàn tất.
