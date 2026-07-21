# ADR-018: Kiến trúc cảnh báo bảo mật thời gian thực (Mandate-11)

- **Trạng thái:** Accepted
- **Ngày:** 2026-07-19
- **Owner:** CDO-07 — Hoàng Kim Hùng
- **Mandate liên quan:** DIRECTIVE #11 — Bắt tại trận
- **Task liên quan:** Task 37 (Event Catalog), Task 38 (Alert Pipeline), Task 40 (Test & Nghiệm thu)
- **Evidence:** `docs/evidence/mandate-011-catch-at-real-time/`

---

## 1. Bối cảnh

Directive #11 đặt ra câu hỏi cốt lõi: *"Khi một hành động nguy hiểm đang diễn ra, hệ thống của các bạn có KÊU không, và kêu sau bao lâu?"*

Trước Mandate-11, hệ thống TF4 đã có CloudTrail ghi lại toàn bộ API call (đã hardened trong Mandate-04), nhưng log nằm im — chỉ phục vụ forensic sau sự cố. Không có cơ chế nào tự động phát hiện và cảnh báo khi kẻ tấn công đang thao tác, ví dụ: tắt trail, tạo access key backdoor, hoặc thêm quyền vào EKS cluster.

**Yêu cầu cần đáp ứng:**
1. Phát hiện và cảnh báo các hành động nguy hiểm trong thời gian thực.
2. Cảnh báo phải kèm đủ ngữ cảnh `ai / gì / khi / từ đâu` để on-call điều tra ngay.
3. Time-to-detect (TTD) phải đo được và đạt target đã cam kết.
4. Phân biệt được hành động CI/CD hợp lệ với hành động bất thường — không gây alert fatigue.
5. Chi phí nằm trong ngân sách $300/tuần/TF, không ảnh hưởng storefront hay flagd.

---

## 2. Quyết định

Triển khai pipeline cảnh báo serverless theo kiến trúc:

```
CloudTrail → EventBridge Rules → SNS Topic → Lambda → Slack Webhook
```

Các thành phần cụ thể:

| Thành phần | Tài nguyên AWS | Vai trò |
|---|---|---|
| **Nguồn sự kiện** | `tf4-general-cloudtrail` (có sẵn từ Mandate-04) | Ghi toàn bộ Management Events (kể cả Read-Only) |
| **Bộ lọc & Router** | 2 EventBridge Rules trên Default Event Bus | Lọc các event nguy hiểm, chuyển sang SNS |
| **Message Bus** | SNS Topic `audit-security-alerts` (KMS encrypted) | Fan-out trung gian, dễ mở rộng thêm kênh sau |
| **Xử lý & Định dạng** | Lambda `audit-security-slack-alerts` (Python 3.12) | Allowlist, severity, TTD, Slack Block Kit |
| **Lưu trữ secret** | SSM Parameter Store `/security-alerts/slack-webhook-url` (SecureString, KMS) | Webhook URL không lộ trong Terraform state |
| **Kênh nhận** | Slack Incoming Webhook | On-call nhận alert trực tiếp |

**Hai EventBridge Rule tách biệt** (quyết định thiết kế quan trọng):

- `cloudtrail_alerts_writeonly_sensitive` — state `ENABLED` — bắt các Write events (IAM, EKS, CloudTrail, S3, EC2, Config)
- `cloudtrail_alerts_readonly_sensitive` — state **`ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS`** — bắt các Read-Only events (SecretsManager, SSM)

---

## 3. Các phương án đã cân nhắc

### Phương án A: CloudWatch Metric Filter + CloudWatch Alarm (Từ chối)

| Tiêu chí | Đánh giá |
|---|---|
| Độ phức tạp | Thấp — tích hợp native AWS |
| Phạm vi | Bị giới hạn: chỉ bắt được events đã stream vào CloudWatch Logs. CloudTrail có delay ~5-15 phút khi ghi vào CWL |
| Định dạng alert | Rất cơ bản — chỉ có metric value, không có actor/IP/context |
| Routing | Qua SNS email/SMS — không đủ linh hoạt định dạng |
| **Lý do từ chối** | Không đủ ngữ cảnh `ai/gì/khi/đâu`, không có allowlist logic, delay cao hơn |

### Phương án B: AWS GuardDuty + Security Hub (Từ chối)

| Tiêu chí | Đánh giá |
|---|---|
| Tính năng | Rất mạnh — ML-based, cross-account |
| Chi phí | ~$50-150/tháng cho GuardDuty (EKS Protection, S3 Protection) — vượt ngân sách |
| Độ trễ phát hiện | 5-15 phút (threat intelligence enrichment) |
| Customization | Khó tùy chỉnh event catalog riêng cho TF4 |
| **Lý do từ chối** | Chi phí vượt ngân sách $300/tuần; không cần ML-based detection cho threat model hiện tại |

### Phương án C: EventBridge + Lambda (Chọn)

| Tiêu chí | Đánh giá |
|---|---|
| Độ trễ | **Near-realtime**: EventBridge nhận event trong vòng giây từ CloudTrail |
| Chi phí | **~$0/tháng** (serverless pay-per-use, nằm trong Free Tier) |
| Customization | Hoàn toàn linh hoạt — event catalog, allowlist, severity, format Slack |
| Context | Đầy đủ actor/event/timestamp/IP/account/region từ raw CloudTrail payload |
| Allowlist | Lambda filter chính xác theo ARN pattern |
| TTD đo được | Lambda tự tính delta từ `CloudTrail eventTime` → ghi CloudWatch metric |
| **Lý do chọn** | Đáp ứng đủ 4 yêu cầu, chi phí ~$0, không cần agent/polling, dễ audit code |

### Phương án D: Polling CloudTrail API định kỳ (Từ chối)

Polling mỗi 1 phút qua Lambda scheduled → delay tối thiểu 60 giây + cost ingestion. Không đáp ứng TTD < 60 giây theo cam kết.

---

## 4. Lý do kỹ thuật cho quyết định tách 2 EventBridge Rule

Trong quá trình implement, team phát hiện vấn đề: **AWS EventBridge với state `ENABLED` mặc định sẽ drop toàn bộ Read-Only Management Events** từ CloudTrail (như `GetSecretValue`, `GetParameter`) để tiết kiệm chi phí xử lý.

Nếu gộp chung tất cả events vào 1 rule với state `ENABLED`, các sự kiện đọc secret sẽ bị bỏ lỡ hoàn toàn mà không có error — đây là **silent failure** rất nguy hiểm.

**Giải pháp:** Tách thành 2 rule:
- Rule Write: `ENABLED` (mặc định, đủ cho write events)
- Rule Read: `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` (bắt buộc cho read-only events)

Đây là lý do thiết kế không thể bỏ qua khi maintain hoặc mở rộng hệ thống.

---

## 5. Cơ chế Giảm nhiễu (Noise Reduction)

Allowlist được implement tại Lambda layer (không phải EventBridge filter) để có logging đầy đủ:

| Rule | Pattern | Hành động |
|---|---|---|
| Exact read allowlist | Khớp account + exact assumed role/AWS service + API + resource | Drop — structured log CloudWatch, không bắn Slack |
| MSK service read | `AWSService`/`kafka.amazonaws.com` đọc đúng secret ARN `AmazonMSK_*` | Drop |
| DMS migration read | Exact DMS role/session đọc đúng một trong hai PostgreSQL migration secret | Drop |
| SG ingress filter | `AuthorizeSecurityGroupIngress` không phải `0.0.0.0/0`/`::/0` | Drop |
| S3 policy filter | `PutBucketPolicy`/`PutBucketAcl` không grant public | Drop |

Mọi alert lọt đến Slack có resource bị tác động và nhãn noise check. Privileged write từ Terraform apply vẫn cảnh báo với nhãn CI/CD riêng; chỉ các read khớp chính xác identity + API + resource mới được bỏ Slack.

---

## 6. Kết quả đạt được

| Yêu cầu | Target | Thực tế | Kết quả |
|---|---|---|---|
| Time-to-detect p95 | < 60 giây | **5.23 giây** | ✅ PASS (~11x tốt hơn target) |
| Alert có đủ ngữ cảnh | actor/event/resource/time/ip | Đủ field điều tra + links | ✅ PASS |
| Exact read allowlist | Giảm nhiễu, không tạo điểm mù | Unit test pass; chờ runtime evidence sau deploy | ⚠️ PENDING RUNTIME |
| Chi phí | < $300/tuần | **~$0/tháng** | ✅ PASS |
| Không ảnh hưởng storefront/flagd | Không đụng | Toàn serverless, no-op với app | ✅ PASS |

---

## 7. Hệ quả & Rủi ro còn lại

**Tích cực:**
- Log thụ động đã biến thành cảnh báo chủ động — audit trail từ Mandate-04 nay có "đôi mắt" giám sát.
- Chi phí cực thấp, không cần thêm agent hay cơ sở hạ tầng.
- Dễ mở rộng: chỉ cần thêm SNS subscription để routing sang email/PagerDuty.

**Rủi ro còn lại:**

| Rủi ro | Mức độ | Compensating Control |
|---|---|---|
| Slack webhook bị revoke → alert mất | Thấp | CloudWatch Logs vẫn ghi metric DetectionLatency; SNS có thể thêm email backup |
| EventBridge Rule bị disable tay → blind spot | Thấp | CloudTrail ghi event `DisableRule` → trigger alert qua rule khác |
| Lambda cold start delay ~200ms | Không đáng kể | Không ảnh hưởng SLO p95 < 60s |
| Severity `CreateAccessEntry` hiển thị HIGH thay vì CRITICAL | P2 | Sẽ fix trong handler.py sprint tiếp theo |

---

## 8. Rollback Plan

**Tắt khẩn cấp (không cần Terraform):**
```bash
# Disable 2 EventBridge rules — alert ngừng ngay lập tức
aws events disable-rule --name security-alerts-cloudtrail-readonly-sensitive --region us-east-1
aws events disable-rule --name security-alerts-cloudtrail-writeonly-sensitive --region us-east-1
```

**Gỡ bỏ hoàn toàn:** Comment out module call trong `infra/terraform/security-slack-alerts.tf` → `terraform apply`.

---

## 9. Kiểm chứng / Evidence

| Artifact | Đường dẫn |
|---|---|
| IaC module | `infra/terraform/modules/security-slack-alerts/` |
| Lambda handler | `infra/terraform/modules/security-slack-alerts/lambda_src/handler.py` |
| Event catalog | `docs/evidence/mandate-011-catch-at-real-time/event-catalog.md` |
| Alert flow diagram | `docs/evidence/mandate-011-catch-at-real-time/alert-flow-diagram.md` |
| TTD evidence (số liệu thực tế) | `docs/evidence/mandate-011-catch-at-real-time/time-to-detect-evidence.md` |
| Acceptance report | `docs/evidence/mandate-011-catch-at-real-time/acceptance-report.md` |
| Test runbook (mentor) | `docs/evidence/mandate-011-catch-at-real-time/test-runbook.md` |
| Incident response runbook | `docs/audit/runbooks/mandate-11-incident-response.md` |

---

## 10. Xác nhận

- **Owner:** CDO-07 — Hoàng Kim Hùng
- **Reviewer:** Ban quản trị dự án TF4
- **Ngày accept:** 2026-07-19
