# [CDO07] Audit Verification Framework — MANDATE-04 Forensic Trail

> **Mục đích:** Khung chuẩn cho Hoàng và Ty thực hiện forensic drill, chứng minh khả năng dựng lại sự thật từ dấu vết.  
> **Kiểm toán sẽ chọn 1 sự kiện thật** đã xảy ra, TF4 phải dựng lại timeline **ai-làm-gì-khi-nào** trong **≤10 phút**.

| Thông tin | Giá trị |
|---|---|
| Mandate | DIRECTIVE #4 — Forensic Audit Trail |
| Deadline | Thứ Ba 16/07/2026 |
| Owner CDO07 | Hoàng + Ty |
| Prerequisite | K8s audit log + CloudTrail enabled, audit permissions granted (AUDIT-010, AUDIT-011) |
| Pass tối thiểu | Drill ≥3 sự kiện pass (≤10 phút/sự kiện); Operator không xóa được log; ≥5 hành động traced về danh tính |

---

## 1. Evidence Index

Nơi lưu trữ tập trung raw evidence — chốt metadata trước khi thu thập.

```json
{
  "mandate": "DIRECTIVE-04-FORENSIC-TRAIL",
  "utc_window": "2026-07-14T00:00:00Z — 2026-07-16T23:59:59Z",
  "k8s_cluster": "techx-tf4-cluster",
  "cloudtrail_name": "tf4-general-cloudtrail",
  "log_group_k8s": "/aws/eks/techx-tf4-cluster/cluster",
  "log_group_cloudtrail": "/aws/cloudtrail/tf4-general-cloudtrail",
  "git_sha": "<git rev-parse HEAD>",
  "verifier": "CDO07 — Hoàng + Ty",
  "note": "Evidence thu thập SAU khi AUDIT-010 và AUDIT-011 completed"
}
```

**File evidence cần tạo:**

| File | Nội dung | Người làm |
|---|---|---|
| `aud-17.1-cloudtrail-status.json` | CloudTrail status + log validation | Hoàng |
| `aud-17.1-eks-audit-config.json` | EKS Control Plane logging config | Hoàng |
| `aud-17.1-cloudwatch-log-group.json` | CloudWatch Log Group retention | Hoàng |
| `aud-17.1-recent-log-streams.json` | Recent log streams (24h) | Hoàng |
| `aud-17.1-query-test-result.md` | Test query: tìm ≥1 audit event | Hoàng |
| `aud-17.2-scenario-*.md` | ≥5 kịch bản forensic (config change, unauthorized access, infra change, on-call, secrets) | Ty |
| `aud-17.2-drill-log.md` | Drill log: ≥3 scenarios với stopwatch (time, pass/fail, lessons learned) | Ty |
| `aud-17.2-query-patterns.md` | Query patterns tái sử dụng (CloudTrail + K8s) | Hoàng + Ty |
| `aud-17.3-iam-policies-review.json` | IAM policies cho operator roles | Hoàng |
| `aud-17.3-s3-bucket-policy.json` | S3 bucket policy (CloudTrail logs) | Hoàng |
| `aud-17.3-separation-test-log.md` | Live test: operator thử xóa log → AccessDenied | Hoàng |
| `aud-17.4-identity-mapping.md` | Identity mapping table (≥5 hành động) | Ty |
| `aud-17.4-infra-changes-7days.json` | CloudTrail infra changes (7 ngày) | Ty |
| `aud-17.4-bastion-access-7days.json` | SSM StartSession events (7 ngày) | Ty |
| `aud-17.4-iam-users-inventory.json` | IAM users scan (check shared accounts) | Ty |

**Lệnh lấy evidence (chạy sau khi AUDIT-010 và AUDIT-011 completed):**

```bash
# [Hoàng] CloudTrail status
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-cloudtrail-status.json

aws cloudtrail get-trail-status --name tf4-general-cloudtrail \
  --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-cloudtrail-trail-status.json

# [Hoàng] EKS audit log config
aws eks describe-cluster --name techx-tf4-cluster \
  --query 'cluster.logging' --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-eks-audit-config.json

# [Hoàng] CloudWatch Log Group
aws logs describe-log-groups \
  --log-group-name-prefix /aws/eks/techx-tf4-cluster/cluster \
  --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-cloudwatch-log-group.json

# [Ty] IAM users inventory
aws iam list-users --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Users[] | {username: .UserName, arn: .Arn, created: .CreateDate}' \
  > docs/evidence/aud-17.4-iam-users-inventory.json
```

**Kết quả mong đợi:**
```json
// CloudTrail
{
  "IsLogging": true,
  "IsMultiRegionTrail": true,
  "LogFileValidationEnabled": true  // CRITICAL - phải true
}

// EKS audit log
{
  "clusterLogging": [
    {
      "types": ["audit"],
      "enabled": true
    }
  ]
}

// IAM users inventory
// KHÔNG có username pattern: "shared-*", "team-*", "ops-admin"
```

> ⚠️ Nếu `LogFileValidationEnabled = false` → STOP, phải fix Terraform trước khi tiếp tục.

---

## 2. Phân Công Chi Tiết (Hoàng + Ty)

### 2.1. Hoàng - Audit Trail Configuration & Separation (8h)

**Task 1: Verify Audit Log Coverage (AUD-17.1)**
- [ ] Check CloudTrail status: `IsLogging`, `IsMultiRegionTrail`, `LogFileValidationEnabled`
- [ ] Check EKS Control Plane Logging: `audit` log enabled
- [ ] Verify CloudWatch Log Group `/aws/eks/techx-tf4-cluster/cluster` có stream mới trong 24h
- [ ] Test query: tìm được ≥1 audit event trong 1h gần nhất
- [ ] Document audit policy level và chi phí estimate
- **Deadline:** 14/07 EOD

**Task 2: Verify Separation of Duties (AUD-17.3)**
- [ ] Review IAM policies cho operator roles (TF4-Developer, TF4-DevOps, TF4-OnCall)
- [ ] Confirm operator KHÔNG có quyền xóa log: `logs:Delete*`, `cloudtrail:StopLogging`, `s3:DeleteObject`
- [ ] Review S3 bucket policy: có explicit Deny cho non-admin delete
- [ ] Live test ≥3 scenarios với operator role → tất cả AccessDenied ✅
- [ ] Document separation of duties evidence
- **Deadline:** 15/07 AM

### 2.2. Ty - Forensic Drill & Identity Mapping (9h)

**Task 3: Forensic Scenarios & Drill (AUD-17.2)**
- [ ] Design ≥5 kịch bản forensic:
  - Scenario 1: Config change (flagd ConfigMap update)
  - Scenario 2: Unauthorized access (403 S3 GetObject)
  - Scenario 3: Infrastructure change (EKS node scale)
  - Scenario 4: On-call action (pod restart)
  - Scenario 5: Secrets access (KMS Decrypt)
- [ ] Drill ≥3 kịch bản với stopwatch, mỗi kịch bản ≤10 phút
- [ ] Log drill results: scenario ID, time taken, pass/fail, lessons learned
- [ ] Optimize query nếu >10 phút
- [ ] Document query patterns tái sử dụng
- **Deadline:** 15/07 PM

**Task 4: Identity Mapping (AUD-17.4)**
- [ ] Query CloudTrail: infra changes, SSM StartSession trong 7 ngày
- [ ] Query K8s audit log: ConfigMap updates, pod actions trong 7 ngày
- [ ] Build identity mapping table: ≥5 hành động → Event, Timestamp, ARN, Real Person
- [ ] Scan IAM users: confirm không có shared account
- **Deadline:** 15/07 PM

### 2.3. Cùng Làm (Hoàng + Ty)

**Task 5: Final Review & Runbook**
- [ ] Review toàn bộ evidence quality
- [ ] Hoàn thiện runbook cho mentor: `mentor-forensic-inspection.md`
- [ ] Final drill rehearsal (≥1 lần nữa)
- [ ] Chuẩn bị cho mentor inspection
- **Deadline:** 16/07 AM

---

## 3. Independent Verification

CDO07 tự kiểm tra độc lập — không dựa vào giả định mà phải verify thật.

### 3.1. Verify Audit Log Coverage (Hoàng)

**CloudTrail:**

```bash
# Test 1: CloudTrail có ghi event không?
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Events | length'
# Kết quả phải >0 (có events)

# Test 2: Log file validation enabled?
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.trailList[] | select(.Name=="tf4-general-cloudtrail") | .LogFileValidationEnabled'
# Kết quả phải là true
```

**K8s Audit Log (Hoàng):**

```bash
# Test 1: CloudWatch Log Group có stream mới không?
aws logs describe-log-streams \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --order-by LastEventTime --descending --max-items 1 \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.logStreams[0].lastEventTime'
# Kết quả phải trong 24h gần nhất (epoch > now - 86400000)

# Test 2: Query audit log thành công?
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"audit"' --max-items 5 \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.events | length'
# Kết quả phải >0
```

**Điều kiện PASS:**
- [ ] CloudTrail: `IsLogging = true`, `LogFileValidationEnabled = true`
- [ ] CloudTrail: Có ≥1 event trong 1h gần nhất
- [ ] K8s audit log: CloudWatch Log Group có stream mới trong 24h
- [ ] K8s audit log: Query thành công, có ≥1 event trong 1h gần nhất

### 3.2. Verify Forensic Drill Pass (Ty)

**Drill Session Template:**

Mentor cung cấp: **Event type** + **Time window**  
VD: "Config change lúc 15:30 ngày 14/07"

**4 Bước (≤10 phút):**

1. **Xác định data source** (2 phút): Config change → K8s audit log
2. **Build query** (3 phút): Time window epoch, filter by ConfigMap + update
3. **Execute query** (3 phút): CLI hoặc CloudWatch Logs Insights UI
4. **Present timeline** (2 phút): Who (ARN/email), What (update flagd-config), When (15:30:12 UTC), How (kubectl apply)

**Drill Log Format:**

| Date | Scenario | Time Taken | Result | Notes |
|------|----------|------------|--------|-------|
| 2026-07-15 10:00 | Scenario 1 (Config change) | 08:30 | ✅ Pass | Query tối ưu bằng jq |
| 2026-07-15 11:00 | Scenario 2 (Unauthorized access) | 09:15 | ✅ Pass | CloudTrail lookup nhanh |
| 2026-07-15 14:00 | Scenario 4 (On-call action) | 12:45 | ❌ Fail | Query K8s audit chậm |
| 2026-07-15 15:00 | Scenario 4 (retry) | 07:20 | ✅ Pass | Đổi sang CloudWatch Insights UI |

**Điều kiện PASS:**
- [ ] ≥3 scenarios drill với stopwatch
- [ ] ≥3 scenarios result = ✅ Pass (≤10 phút)
- [ ] Drill log có timestamp thật, không placeholder
- [ ] Lessons learned documented

### 3.3. Verify Separation of Duties (Hoàng)

**Live Test với Operator Role:**

```bash
# Test 1: Thử xóa log stream
aws logs delete-log-stream \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --log-stream-name <any-stream> \
  --profile TF4-Developer 2>&1 | grep "AccessDenied"
# Expected: AccessDenied

# Test 2: Thử stop CloudTrail
aws cloudtrail stop-logging --name tf4-general-cloudtrail \
  --profile TF4-Developer 2>&1 | grep "AccessDenied"
# Expected: AccessDenied

# Test 3: Thử xóa S3 object (CloudTrail log)
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/<any-log-file> \
  --profile TF4-Developer 2>&1 | grep "AccessDenied"
# Expected: AccessDenied
```

**Điều kiện PASS:**
- [ ] Tất cả 3 tests trả về AccessDenied ✅
- [ ] IAM policy review: operator roles KHÔNG có dangerous permissions
- [ ] S3 bucket policy có explicit Deny cho non-admin
- [ ] RBAC review (K8s): operator không edit được audit infrastructure

### 3.4. Verify Identity Traceability (Ty)

**Identity Mapping Table Mẫu:**

| Event | Timestamp | ARN | Real Person | Traceability |
|-------|-----------|-----|-------------|--------------|
| UpdateNodegroupConfig (2→4) | 2026-07-13T18:00:05Z | `arn:aws:sts::511825856493:assumed-role/TF4-GitHubActions/infra-bot` | Bot (GH Actions run #1234) | Session name + source IP |
| ConfigMap update | 2026-07-14T15:30:12Z | K8s user: `john.doe@techx-corp.com` | john.doe@techx-corp.com | Session name = email |
| SSM StartSession | 2026-07-14T02:29:30Z | `arn:aws:sts::511825856493:assumed-role/TF4-OnCall/jane.smith@techx-corp.com` | jane.smith@techx-corp.com | Session name = email |
| KMS Decrypt | 2026-07-14T14:00:10Z | `arn:aws:sts::511825856493:assumed-role/TF4-Developer/alice.dev@techx-corp.com` | alice.dev@techx-corp.com | Session name = email |
| Pod delete | 2026-07-14T02:30:15Z | K8s user: `jane.smith@techx-corp.com` | jane.smith@techx-corp.com | K8s RBAC mapping |

**Điều kiện PASS:**
- [ ] ≥5 hành động mapped thành công
- [ ] Không có shared account (IAM users scan clean)
- [ ] Mọi ARN/session name traceable về người thật hoặc bot có run ID

---

## 4. Auditability Checks

### 4.1. Cost Verification (Hoàng)

**Chi phí Audit Logging:**

| Component | Volume (Baseline) | Volume (Peak) | Cost/GB | Est. Cost/Week |
|-----------|-------------------|---------------|---------|----------------|
| CloudTrail → CWL | ~50 MB/day | ~200 MB/day | $0.50/GB | $1.75 - $7/week |
| K8s audit → CWL | ~30 MB/day | ~300 MB/day | $0.50/GB | $1.05 - $10.5/week |
| CWL storage (14d) | ~1.1 GB | ~7 GB | $0.03/GB/mo | $0.25 - $1.5/week |
| **Total** | | | | **~$3 - $19/week** ✅ |

**Đối chiếu với budget:**
- [ ] Chi phí thực tế ≤ $300/tuần/TF ✅
- [ ] Monitor CloudWatch Logs ingestion daily
- [ ] Alert nếu ingestion spike >500 MB/day

### 4.2. Timeline Thật (Loại Trừ Cache)

- [ ] Timestamp evidence phải trong vòng 30 phút trước deadline
- [ ] Không copy-paste evidence từ lần test trước
- [ ] Drill log có stopwatch timestamp thật (không fake)

### 4.3. Không Ảnh Hưởng Flagd

- [ ] Test checkout flow sau khi enable audit log: HTTP 200, order created
- [ ] flagd ConfigMap không bị thay đổi do audit setup
- [ ] Feature flag evaluation vẫn hoạt động (check OpenFeature SDK logs)

### 4.4. Kết Luận Tổng Nghiệm Thu

| Hạng mục | Pass / Fail / Blocked | Ghi chú |
|---|---|---|
| **Audit Trail Coverage** | | |
| CloudTrail logging enabled | ☐ | IsLogging, LogFileValidationEnabled |
| CloudTrail có event trong 1h | ☐ | |
| K8s audit log enabled | ☐ | |
| K8s audit log có event trong 1h | ☐ | |
| CloudWatch Logs integration | ☐ | |
| **Forensic Drill** | | |
| ≥5 kịch bản designed | ☐ | Scenario 1-5 documented |
| ≥3 kịch bản drill pass (≤10 phút) | ☐ | Drill log với stopwatch |
| Query patterns documented | ☐ | |
| Runbook cho mentor | ☐ | mentor-forensic-inspection.md |
| **Separation of Duties** | | |
| Operator không có dangerous permissions | ☐ | IAM policy review |
| S3 bucket policy explicit Deny | ☐ | |
| Live test ≥3 scenarios AccessDenied | ☐ | Test log committed |
| RBAC review (K8s) | ☐ | |
| **Identity Traceability** | | |
| ≥5 hành động mapped | ☐ | Identity mapping table |
| Không có shared account | ☐ | IAM users scan |
| On-call actions traced | ☐ | ≥3 SSM StartSession |
| **Cost & Non-Functional** | | |
| Chi phí ≤ $300/tuần | ☐ | Actual cost monitored |
| Không ảnh hưởng flagd | ☐ | Checkout test pass |
| Timeline thật (không cache) | ☐ | Evidence timestamp fresh |

**Kết luận cuối:** ☐ PASS / ☐ FAIL / ☐ BLOCKED (lý do: ___)

**Người duyệt CDO07:** Hoàng + Ty | **Ngày:** ___

---

## 5. Checklist trước khi submit PR

- [ ] Tất cả file evidence có timestamp thật (không placeholder)
- [ ] Drill log có ≥3 scenarios pass với stopwatch
- [ ] IAM separation test log có ≥3 AccessDenied results
- [ ] Identity mapping table có ≥5 hành động với real person
- [ ] Query patterns documented (tái sử dụng được)
- [ ] Runbook cho mentor ready: `mentor-forensic-inspection.md`
- [ ] Chi phí estimate documented: ~$3/week baseline, ~$19/week peak
- [ ] Không có credential, token, private key trong evidence files
- [ ] metadata.json updated với git SHA thật
- [ ] Tất cả 4 subtask AUD-17.1 → AUD-17.4 Done
- [ ] Hoàng + Ty sign-off

---

## 6. Ghi chú về blocker hiện tại

> **Trạng thái:** 🟡 IN PROGRESS — Đang thu thập evidence  
> 
> **Prerequisite dependencies:**
> - ✅ `CDO07-AUD-05` (EKS Control Plane Logging) — confirmed partial (api, audit, authenticator enabled)
> - ✅ `CDO07-AUD-01` (CloudTrail hardening) — logging enabled, nhưng LogFileValidationEnabled = false cần fix
> - ⚠️ `CDO07-AUD-11` (Audit permissions) — một số quyền bị deny, đã request

**Action items CDO07 còn cần làm:**
- [ ] Hoàng: Verify AUDIT-011 (CloudTrail Terraform fix) đã apply
- [ ] Hoàng: Verify AUDIT-010 (permissions) đã grant
- [ ] Hoàng: Confirm K8s audit policy level (default EKS audit đủ chưa)
- [ ] Ty: Design ≥5 forensic scenarios
- [ ] Ty: Generate test events nếu không có sự kiện thật trong 7 ngày
- [ ] Both: Daily standup 21:00 update progress

**Known limitations:**
- CloudTrail lag ~5-15 phút → Chọn sự kiện ≥30 phút trước để drill
- K8s audit log nhiều noise (health check, list pods) → Filter chặt: `verb in [create, update, delete]`
- Drill cần practice ≥5 lần để đạt ≤10 phút → Ty schedule drill sessions

**Risk mitigation:**
- Nếu mentor chọn sự kiện >7 ngày: Extend query time window to 14 days
- Nếu drill >10 phút: Optimize query, dùng CloudWatch Insights UI thay CLI
- Nếu không có non-admin profile để test: Dùng IAM Policy Simulator

---

## 7. Related Documents

**Framework này:**
- File này là framework verification duy nhất cho MANDATE #4
- Tất cả subtasks (AUD-17.1a/b, AUD-17.2a/b, AUD-17.3, AUD-17.4) đã tích hợp trong đây

**Runbooks:**
- [../runbooks/mentor-forensic-inspection.md](../runbooks/mentor-forensic-inspection.md) - Hướng dẫn mentor xem audit log và chấm forensic

**Backlog & Tracking:**
- [../cdo07_audit_backlog_plan_v2.md](../cdo07_audit_backlog_plan_v2.md) - Section 5: MANDATE #4
- [../JIRA_TASKS.md](../JIRA_TASKS.md) - Task 19-24

---

## 8. Scoring Rubric (Mentor Chấm Điểm)

### Timeline Accuracy (40 điểm)
- **Who:** Xác định đúng danh tính (ARN/email/bot name) - 15 điểm
- **What:** Mô tả đúng hành động (event name, verb, resource) - 10 điểm
- **When:** Timestamp chính xác (UTC, ±1 phút) - 10 điểm
- **How:** Method (kubectl/API/console/automation) - 5 điểm

### Speed (30 điểm)
- ≤5 phút: 30 điểm
- 5-7 phút: 20 điểm
- 7-10 phút: 10 điểm
- >10 phút: 0 điểm (FAIL)

### Evidence Quality (20 điểm)
- Raw log output chính xác - 10 điểm
- Correlation logic rõ ràng (nếu multi-source) - 10 điểm

### Tamper-Evident (10 điểm)
- Chứng minh operator không xóa được log - 10 điểm

**Total: 100 điểm**  
**Pass threshold: ≥70 điểm**

---

## 9. Query Pattern Reference (Quick Cheat Sheet)

### CloudTrail Events

```bash
# Infrastructure change
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateNodegroupConfig \
  --start-time <ISO-8601> --end-time <ISO-8601> \
  --profile TF4-AuditReadOnlyAndAnalyze

# Unauthorized access (AccessDenied)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time <ISO-8601> \
  | jq '.Events[] | select(.CloudTrailEvent | fromjson | .errorCode == "AccessDenied")'

# SSM StartSession (bastion access)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time <ISO-8601>

# KMS Decrypt (secrets access)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=Decrypt \
  --start-time <ISO-8601> \
  | jq '.Events[] | select(.Resources[]?.ResourceName | contains("tf4"))'
```

### K8s Audit Log

```bash
# ConfigMap update
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time <epoch-ms> --end-time <epoch-ms> \
  --filter-pattern '"ConfigMap" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.events[] | .message | fromjson | {time, user: .user.username, verb, object: .objectRef.name}'

# Pod delete
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time <epoch-ms> \
  --filter-pattern '"delete" "pods" "checkout"'
```

### Epoch Conversion

```bash
# Linux/macOS
date -u -d '2026-07-14 15:30:00' +%s
# Output: 1783964400

# CloudWatch needs milliseconds
date -u -d '2026-07-14 15:30:00' +%s | awk '{print $1 * 1000}'
# Output: 1783964400000
```

---

**Last updated:** 2026-07-14  
**Next review:** 2026-07-16 (after mentor inspection)
