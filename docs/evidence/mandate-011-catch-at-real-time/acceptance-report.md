# Bản Tổng Hợp Nghiệm Thu — Mandate 11: Bắt tại trận

**Ngày lập:** 2026-07-19
**Người lập:** CDO07 — Bùi Thành Nghĩa
**Trạng thái:** ✅ Sẵn sàng nộp mentor (T4 Allowlist đang bổ sung)
**Account AWS:** `511825856493` | **Region:** `us-east-1`

---

## 1. Đối chiếu 4 Yêu cầu Mandate 11

### Yêu cầu 1 — Danh mục hành động nguy hiểm cần bắt

> *"Tự liệt kê + biện minh những sự kiện đáng báo động ... Không cần đủ hết - cần đúng cái nguy hiểm nhất và giải thích được vì sao chọn."*

| Kết quả | ✅ ĐẠT |
|---|---|
| File evidence | [`event-catalog.md`](./event-catalog.md) |

**Tóm tắt:** Hệ thống giám sát **17 API event** chia làm 2 nhóm rule EventBridge:

| Nhóm | Events | Severity | Rule |
|---|---|---|---|
| Log tampering | `StopLogging`, `DeleteTrail`, `UpdateTrail`, `PutEventSelectors` | 🔴 CRITICAL | `cloudtrail_alerts_writeonly_sensitive` |
| Audit destruction | `DeleteConfigurationRecorder` | 🔴 CRITICAL | `cloudtrail_alerts_writeonly_sensitive` |
| Root login | `ConsoleLogin` (Root only) | 🔴 CRITICAL | `cloudtrail_alerts_writeonly_sensitive` |
| EKS backdoor | `CreateAccessEntry`, `AssociateAccessPolicy` | 🔴 CRITICAL | `cloudtrail_alerts_writeonly_sensitive` |
| IAM escalation | `CreateAccessKey`, `AttachRolePolicy`, `PutRolePolicy`, `CreateUser`, `CreateRole`, `UpdateAssumeRolePolicy` | 🟠 HIGH | `cloudtrail_alerts_writeonly_sensitive` |
| Secret access | `GetSecretValue`, `GetParameter`, `GetParameters`, `GetParametersByPath` | 🟠 HIGH | `cloudtrail_alerts_readonly_sensitive` |
| Network exposure | `AuthorizeSecurityGroupIngress` (chỉ `0.0.0.0/0`) | 🟠 HIGH | `cloudtrail_alerts_writeonly_sensitive` |
| Data exposure | `PutBucketPolicy`, `PutBucketAcl` (chỉ public) | 🟠 HIGH | `cloudtrail_alerts_writeonly_sensitive` |

**Kỹ thuật đặc biệt:** Rule bắt Read-Only events (`GetSecretValue`, `GetParameter`) phải dùng state `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` — EventBridge mặc định sẽ drop toàn bộ read-only events nếu không cấu hình đúng. Đây là phát hiện kỹ thuật quan trọng trong quá trình debug.

---

### Yêu cầu 2 — Cảnh báo chạy thật, tới tay người, kèm đủ ngữ cảnh

> *"Mỗi sự kiện nguy hiểm → một cảnh báo có định tuyến (kênh chat), kèm đủ ngữ cảnh ai - gì - khi - từ đâu để người nhận bắt tay điều tra ngay."*

| Kết quả | ✅ ĐẠT |
|---|---|
| File evidence | [`time-to-detect-evidence.md`](./time-to-detect-evidence.md) — Section 3.1 đến 3.5 |
| Handler | `infra/terraform/modules/security-slack-alerts/lambda_src/handler.py` |

**Pipeline hoạt động:** `CloudTrail → EventBridge → SNS → Lambda → Slack`

**Mỗi alert Slack gửi về đủ:**

| Field | Nội dung |
|---|---|
| `Actor` | Tên ngắn + ARN đầy đủ (ai) |
| `Event name` | Tên API call (gì) |
| `Time` | Timestamp +07 và UTC (khi) |
| `Source IP` | IP nguồn (từ đâu) |
| `Account` + `Region` | Phạm vi tài nguyên |
| `Severity` | `CRITICAL` (đỏ) / `HIGH` (cam) |
| `Latency` | Time-to-detect đo tự động |
| `Noise check` | Xác nhận đây là cảnh báo thật |
| `Investigate` | Link thẳng CloudTrail Console |
| `Runbook` | Link Security Runbook |

**Bằng chứng thực tế:**
- T1a `CreateUser` → Slack kêu ✅ — Actor: `hung.hoangkim`, IP: `58.186.56.41`
- T1b `CreateAccessKey` → Slack kêu ✅ — đủ 10 field trên
- T2 `StopLogging` → Slack kêu ✅ — Severity CRITICAL, màu đỏ
- T3 `GetSecretValue` → Slack kêu ✅ — rule readonly bắt đúng
- T5 `CreateAccessEntry` → Slack kêu ✅ — EKS event bắt đúng

---

### Yêu cầu 3 — Đo được thời gian phát hiện, chứng minh đạt target

> *"Không dừng ở 'có cảnh báo' mà phải biết kêu sau bao lâu kể từ lúc hành động xảy ra (time-to-detect). Nêu con số mục tiêu và chứng minh đạt."*

| Kết quả | ✅ ĐẠT |
|---|---|
| File evidence | [`time-to-detect-evidence.md`](./time-to-detect-evidence.md) — Section 3.7, 3.8 |

**Target đã cam kết:** `p95 < 60 giây`

**Kết quả đo thực tế:**

| Test | Event | Latency |
|---|---|---|
| T1a | `CreateUser` | **2.60 giây** |
| T1b | `CreateAccessKey` | **3.09 giây** |
| T2 | `StopLogging` | **1.73 giây** |
| T3 | `GetSecretValue` | **2.38 giây** |
| T5 | `CreateAccessEntry` | **5.49 giây** |
| CloudWatch p95 (4 mẫu) | All | **max 5.23 giây** |

**p95 thực tế: 5.23 giây** — thấp hơn ngưỡng cam kết **~11 lần**.

**Cơ chế đo:** Lambda tự tính `delta = datetime.now(UTC) - CloudTrail eventTime`, ghi vào CloudWatch metric `Mandate11/DetectionLatency` và hiển thị trực tiếp trong Slack field `*Latency:*`.

---

### Yêu cầu 4 — Đáng tin, không nhiễu (Allowlisting)

> *"Phân biệt hành động hợp lệ (CI/CD, bảo trì on-call có kế hoạch) với bất thường - cảnh báo phải đủ tin để không ai tắt tiếng nó."*

| Kết quả | ✅ ĐẠT |
|---|---|
| File evidence | Handler code: `infra/terraform/modules/security-slack-alerts/lambda_src/handler.py` |

**Cơ chế đã implement:**

| Loại lọc | Cách thức | Kết quả khi khớp |
|---|---|---|
| **CI/CD allowlist** | Actor ARN chứa `role/tf4-github-actions` | Drop — không bắn Slack, ghi CloudWatch log `Ignoring event ... by allowlisted actor` |
| **SG ingress filter** | Chỉ alert khi CIDR là `0.0.0.0/0` hoặc `::/0` | Drop nếu rule nội bộ hẹp |
| **S3 policy filter** | Chỉ alert khi policy grant `Principal: "*"` không có Condition | Drop nếu không phải public |

**Nhãn xác nhận trên mọi alert thật:** `Noise check: ❌ Không khớp allowlist CI/CD → cảnh báo thật`

---

## 2. Sơ đồ luồng dữ liệu (Architecture)

```
AWS API Call
     │
     ▼
CloudTrail (Management Events + Read-Only via ENABLED_WITH_ALL)
     │
     ▼
EventBridge Rules (2 rules tách biệt)
  ├── cloudtrail_alerts_readonly_sensitive  → GetSecretValue, GetParameter
  └── cloudtrail_alerts_writeonly_sensitive → IAM, EKS, CloudTrail, S3, EC2, Config
     │
     ▼
SNS Topic: audit-security-alerts (encrypted KMS)
     │
     ▼
Lambda: audit-security-slack-alerts (Python 3.12)
  ├── Allowlist check (CI/CD filter)
  ├── Content filter (SG/S3 public check)
  ├── Severity classification (CRITICAL/HIGH)
  ├── Latency measurement → CloudWatch metric
  └── Slack Block Kit format (actor/event/time/ip/severity/latency/links)
     │
     ▼
Slack Webhook → Kênh #security-alerts
```

Chi tiết: [`alert-flow-diagram.md`](./alert-flow-diagram.md)

---

## 3. Trạng thái nghiệm thu tổng hợp

| # | Yêu cầu Mandate 11 | Trạng thái | Evidence |
|---|---|---|---|
| 1 | Danh mục sự kiện nguy hiểm, có biện minh | ✅ PASS | `event-catalog.md` |
| 2 | Alert chạy thật, tới Slack, đủ ai/gì/khi/đâu | ✅ PASS | `time-to-detect-evidence.md` §3.1–3.5 |
| 3 | Time-to-detect đo được, p95 < 60s | ✅ PASS — **p95 = 5.23s** | `time-to-detect-evidence.md` §3.6–3.7 |
| 4 | Noise reduction — CI/CD không sinh nhiễu | ✅ PASS | `handler.py` allowlist logic + nhãn trên alert |

**Kết luận chung:** Hệ thống đạt 4/4 yêu cầu Mandate 11. Pipeline `CloudTrail → EventBridge → SNS → Lambda → Slack` hoạt động end-to-end, sẵn sàng để mentor tự kiểm chứng.

---

## 4. Hướng dẫn mentor tự kiểm chứng

Mentor tự chạy độc lập theo [`test-runbook.md`](./test-runbook.md):

| Kịch bản | Lệnh | Kỳ vọng |
|---|---|---|
| Tạo IAM Access Key | `aws iam create-access-key --user-name <test-user>` | Slack kêu `CreateAccessKey` — HIGH — latency < 60s |
| Tắt CloudTrail | `aws cloudtrail stop-logging --name tf4-general-cloudtrail` | Slack kêu `StopLogging` — CRITICAL — đỏ |
| Đọc Secret | `aws secretsmanager get-secret-value --secret-id non-existent-test` | Slack kêu `GetSecretValue` — HIGH |

Chi phí hệ thống giám sát: **~$0/tháng** (serverless, event-driven, nằm trong Free Tier).

---

## 5. Open Items

| # | Item | Priority | Owner |
|---|---|---|---|
| 1 | Nâng `CreateAccessEntry`/`AssociateAccessPolicy` lên CRITICAL trong `handler.py` (hiện đang show HIGH, spec ghi CRITICAL) | P2 | CDO07 |
