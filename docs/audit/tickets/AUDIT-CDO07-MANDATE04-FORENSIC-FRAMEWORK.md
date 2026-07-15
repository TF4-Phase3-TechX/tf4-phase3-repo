# [CDO07] Audit Verification Framework — MANDATE-04 Forensic Audit Trail

> **Mục đích:** Khung chuẩn cho Hoàng và Ty thực hiện forensic audit trail, chứng minh khả năng truy vết  
> **ai-làm-gì-khi-nào** từ audit log trong **≤10 phút**.  
> **Không được điền evidence vào đây trước khi AUDIT-010 và AUDIT-011 hoàn tất.**

| Thông tin | Giá trị |
|---|---|
| Mandate | DIRECTIVE #4 — Forensic Audit Trail |
| Deadline | Thứ Năm 16/07/2026 |
| Owner CDO07 | Hoàng + Ty |
| Prerequisite | AUDIT-010 (audit permissions) + AUDIT-011 (CloudTrail terraform fix) deployed |
| Pass tối thiểu | Drill ≥3 scenario pass (≤10 phút/scenario); Operator không xóa được log; ≥5 hành động traced về danh tính |

---

## 1. Evidence Index

Nơi lưu trữ tập trung raw evidence — chốt metadata trước khi thu thập.

```json
{
  "mandate": "DIRECTIVE-04-FORENSIC-TRAIL",
  "utc_window": "YYYY-MM-DDTHH:MM:SSZ — YYYY-MM-DDTHH:MM:SSZ",
  "cloudtrail_name": "tf4-general-cloudtrail",
  "k8s_cluster": "techx-tf4-cluster",
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
| `aud-17.1-cloudtrail-config.json` | CloudTrail config + log validation enabled | Hoàng |
| `aud-17.1-cloudtrail-status.json` | CloudTrail status (IsLogging, IsMultiRegionTrail) | Hoàng |
| `aud-17.1-aws-config-status.json` | AWS Config recorder và delivery channel status | Hoàng |
| `aud-17.1-eks-audit-config.json` | EKS Control Plane logging enabled | Hoàng |
| `aud-17.1-query-test-result.md` | Test query thành công | Hoàng |
| `aud-17.2-drill-scenarios.md` | ≥5 forensic scenarios designed | Ty |
| `aud-17.2-drill-log.md` | ≥3 drill results với stopwatch | Ty |
| `aud-17.3-separation-test.md` | Operator thử xóa log → AccessDenied | Hoàng |
| `aud-17.3-s3-object-lock-test.md` | Test S3 Object Lock COMPLIANCE config (CloudTrail + EKS logs) | Hoàng |
| `aud-17.3-validate-logs-test.md` | CloudTrail log validation digest test | Hoàng |
| `aud-17.3-firehose-config.json` | Firehose delivery stream configuration | Hoàng |

**Lệnh lấy evidence (chạy sau khi AUDIT-010 và AUDIT-011 completed):**

```bash
# [Hoàng] Check CloudTrail configuration và status
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-cloudtrail-config.json

aws cloudtrail get-trail-status --name tf4-general-cloudtrail \
  --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-cloudtrail-status.json

# [Hoàng] Check AWS Config status
aws configservice describe-configuration-recorder-status \
  --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-aws-config-status.json

# [Hoàng] Check EKS audit logging  
aws eks describe-cluster --name techx-tf4-cluster \
  --query 'cluster.logging' --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.1-eks-audit-config.json

# [Hoàng] Check Firehose configuration
aws firehose describe-delivery-stream --delivery-stream-name tf4-eks-audit-logs-firehose \
  --profile TF4-AuditReadOnlyAndAnalyze \
  > docs/evidence/aud-17.3-firehose-config.json

# [Ty] IAM users scan (no shared accounts)
aws iam list-users --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Users[] | {username: .UserName, arn: .Arn}' \
  > docs/evidence/aud-17.4-iam-users-scan.json
```

**Kết quả mong đợi:**
```json
// CloudTrail config (describe-trails)
{
  "trailList": [
    {
      "Name": "tf4-general-cloudtrail",
      "LogFileValidationEnabled": true
    }
  ]
}

// CloudTrail status (get-trail-status)  
{
  "IsLogging": true,
  "IsMultiRegionTrail": true
}

// EKS audit log phải enabled
{
  "clusterLogging": [{"types": ["audit"], "enabled": true}]
}
```

> ⚠️ Nếu `LogFileValidationEnabled = false` hoặc `IsLogging = false` → STOP, AUDIT-011 chưa xong.

---

## 2. Phần Truy Vết (Audit Trail Coverage)

### 2.1. CloudTrail - AWS API calls (Hoàng)

**Verify CloudTrail logging:**

```bash
# Test 1: CloudTrail configuration
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.trailList[] | select(.Name=="tf4-general-cloudtrail") | .LogFileValidationEnabled'
# Kết quả phải là true

# Test 2: CloudTrail status  
aws cloudtrail get-trail-status --name tf4-general-cloudtrail \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.IsLogging'
# Kết quả phải là true

# Test 3: CloudTrail có ghi event không?
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --profile TF4-AuditReadOnlyAndAnalyze | jq '.Events | length'
# Kết quả phải >0
```

**Điều kiện PASS:**
- [ ] CloudTrail `IsLogging = true`
- [ ] CloudTrail `LogFileValidationEnabled = true` (tamper-evident)
- [ ] Có ≥1 event trong 1h gần nhất

### 2.2. AWS Config - Infrastructure changes (Hoàng)

**Check AWS Config enabled:**

```bash
# Verify AWS Config recorder status
aws configservice describe-configuration-recorder-status \
  --profile TF4-AuditReadOnlyAndAnalyze | jq '.ConfigurationRecordersStatus[0].recording'
# Kết quả phải là true

# Verify delivery channel status
aws configservice describe-delivery-channel-status \
  --profile TF4-AuditReadOnlyAndAnalyze | jq '.DeliveryChannelsStatus[0].configDeliveryInfo.lastStatus'
# Expected: "Success"
```

**Điều kiện PASS:**
- [ ] AWS Config recorder status `recording = true`
- [ ] Delivery channel status `lastStatus = "Success"`
- [ ] Config có ghi configuration changes

### 2.3. EKS Control Plane Logging - K8s audit (Ty)

**Check K8s audit log:**

```bash
# Test K8s audit log có event không?
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '1 hour ago' +%s)000 \
  --filter-pattern '"audit"' --max-items 5 \
  --profile TF4-AuditReadOnlyAndAnalyze | jq '.events | length'
# Kết quả phải >0
```

**Điều kiện PASS:**
- [ ] EKS Control Plane `audit` log enabled
- [ ] CloudWatch Log Group có stream mới trong 24h
- [ ] Query thành công, có ≥1 audit event

---

## 3. Bảo Vệ Chống Xóa Sửa Log (Tamper-Evident Protection)

### 3.1. S3 Object Lock COMPLIANCE mode (Hoàng)

**CloudTrail logs được bảo vệ bởi S3 Object Lock COMPLIANCE:**

```bash
# Check S3 Object Lock configuration
aws s3api get-object-lock-configuration \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze
# Expected: "Mode": "COMPLIANCE"
```

**Test operator không xóa được log:**

```bash
# Test 1: Check S3 Object Lock configuration
aws s3api get-object-lock-configuration \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze
# Expected: "Mode": "COMPLIANCE", "Days": 90

# Test 2: Operator thử xóa log → AccessDenied
aws s3 rm s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail/ \
  --recursive --profile TF4-Developer 2>&1 | grep "AccessDenied"
# Expected: AccessDenied
```

**Điều kiện PASS:**
- [ ] S3 Object Lock mode = "COMPLIANCE" (không phải GOVERNANCE)
- [ ] Object Lock retention ≥90 ngày
- [ ] Operator role AccessDenied khi xóa log

### 3.2. CloudTrail Log File Validation (Hoàng)

**Verify log integrity:**

```bash
# Test 1: CloudTrail tạo digest file mỗi giờ với hash
aws cloudtrail validate-logs \
  --trail-arn arn:aws:cloudtrail:us-east-1:511825856493:trail/tf4-general-cloudtrail \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
  --profile TF4-AuditReadOnlyAndAnalyze
# Expected: All log files validated successfully

# Test 2: Check digest files exist in S3
aws s3 ls s3://tf4-cloudtrail-logs-bucket-511825856493/AWSLogs/511825856493/CloudTrail-Digest/ \
  --profile TF4-AuditReadOnlyAndAnalyze | head -5
# Expected: List of digest files with .json.gz extension
```

**Điều kiện PASS:**
- [ ] `LogFileValidationEnabled = true` trong CloudTrail
- [ ] Validate-logs command thành công
- [ ] Digest files tồn tại trong S3 bucket

### 3.3. EKS Logs Firehose & S3 Object Lock (Hoàng)

Để ngăn chặn lỗ hổng Root account hoặc Administrator có thể xóa EKS Control Plane logs trực tiếp trong CloudWatch Logs, logs được stream qua **Amazon Data Firehose** lưu vào S3 bucket độc lập `tf4-eks-audit-logs-511825856493` bảo vệ bởi **S3 Object Lock COMPLIANCE mode 90 ngày**.

**Check EKS logs S3 Object Lock configuration:**

```bash
# Check S3 Object Lock configuration
aws s3api get-object-lock-configuration \
  --bucket tf4-eks-audit-logs-511825856493 \
  --profile TF4-AuditReadOnlyAndAnalyze
# Expected: "Mode": "COMPLIANCE", "Days": 90
```

**Test operator/admin không xóa được log khỏi S3:**

```bash
# Operator thử xóa EKS log khỏi S3 → AccessDenied
aws s3 rm s3://tf4-eks-audit-logs-511825856493/ \
  --recursive --profile TF4-Developer 2>&1 | grep "AccessDenied"
# Expected: AccessDenied
```

**Điều kiện PASS:**
- [ ] Kinesis Firehose delivery stream `tf4-eks-audit-logs-firehose` ở trạng thái ACTIVE
- [ ] EKS logs S3 Object Lock mode = "COMPLIANCE" (retention ≥90 ngày)
- [ ] Operator role AccessDenied khi xóa EKS log trong S3 bucket

---

## 4. Chạy Thử Các Bài Test (Forensic Drill Scenarios)

### 4.1. Design ≥5 Test Scenarios (Ty)

**Scenario 1: Infrastructure change**
- Event: EKS nodegroup scale hoặc S3 bucket create
- Data source: CloudTrail 
- Query: `UpdateNodegroupConfig` hoặc `CreateBucket`

**Scenario 2: K8s cluster access**  
- Event: ConfigMap update hoặc Pod delete
- Data source: EKS audit log (CloudWatch)
- Query: `"ConfigMap" "update"` hoặc `"delete" "pods"`

**Scenario 3: Unauthorized access attempt**
- Event: S3 GetObject AccessDenied hoặc AssumeRole failure
- Data source: CloudTrail
- Query: `errorCode == "AccessDenied"`

**Scenario 4: Secrets access**
- Event: KMS Decrypt hoặc SSM GetParameter  
- Data source: CloudTrail
- Query: `Decrypt` hoặc `GetParameter`

**Scenario 5: On-call action**
- Event: SSM StartSession (bastion access)
- Data source: CloudTrail
- Query: `StartSession`

### 4.2. Drill Session Template (≤10 phút/scenario)

Mentor cung cấp: **Event type** + **Time window**  
VD: "Someone updated S3 bucket policy lúc 15:30 ngày 14/07"

**4 Bước forensic (≤10 phút):**

1. **Xác định data source** (2 phút): S3 policy change → CloudTrail
2. **Build query** (3 phút): Time window + EventName=PutBucketPolicy  
3. **Execute query** (3 phút): CLI hoặc CloudWatch Logs Insights
4. **Present timeline** (2 phút): Who (ARN/email), What (policy change), When (15:30:12 UTC), How (console/CLI)

**Drill Log Mẫu:**

| Date | Scenario | Time | Result | Notes |
|------|----------|------|--------|-------|
| 15/07 10:00 | S3 bucket change | 08:30 | ✅ Pass | CloudTrail lookup nhanh |
| 15/07 11:00 | ConfigMap update | 09:15 | ✅ Pass | K8s audit log query |
| 15/07 14:00 | Unauthorized access | 07:45 | ✅ Pass | Filter by errorCode |

**Điều kiện PASS:**
- [ ] ≥3 scenarios drill với stopwatch thật
- [ ] ≥3 scenarios ≤10 phút mỗi cái
- [ ] Timeline chính xác: Who-What-When-How

### 4.3. Query Patterns (Tái sử dụng)

**CloudTrail common queries:**

```bash
# Infrastructure changes (7 ngày)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateNodegroupConfig \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ) \
  --profile TF4-AuditReadOnlyAndAnalyze

# Unauthorized access
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
  | jq '.Events[] | select(.CloudTrailEvent | fromjson | .errorCode == "AccessDenied")'

# SSM StartSession (bastion access)  
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%SZ)
```

**K8s audit log queries:**

```bash
# ConfigMap updates
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '24 hours ago' +%s)000 \
  --filter-pattern '"ConfigMap" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze

# Pod deletions  
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '24 hours ago' +%s)000 \
  --filter-pattern '"delete" "pods"'
```

---

## 5. Identity Mapping (≥5 hành động → danh tính cụ thể)

**Identity Mapping Table:**

| Event | Timestamp | ARN | Real Person | Traceability |
|-------|-----------|-----|-------------|--------------|
| S3 policy update | 2026-07-14T15:30:12Z | `arn:aws:sts::511825856493:assumed-role/TF4-DevOps/john.doe@techx-corp.com` | john.doe@techx-corp.com | Session name = email |
| ConfigMap update | 2026-07-14T16:00:05Z | K8s user: `alice.dev@techx-corp.com` | alice.dev@techx-corp.com | K8s RBAC mapping |
| SSM StartSession | 2026-07-14T02:29:30Z | `arn:aws:sts::511825856493:assumed-role/TF4-OnCall/jane.smith@techx-corp.com` | jane.smith@techx-corp.com | Session name = email |
| KMS Decrypt | 2026-07-14T14:00:10Z | `arn:aws:sts::511825856493:assumed-role/TF4-Developer/bob.eng@techx-corp.com` | bob.eng@techx-corp.com | Session name = email |
| EKS nodegroup scale | 2026-07-13T18:00:05Z | `arn:aws:sts::511825856493:assumed-role/TF4-GitHubActions/infra-bot` | Bot (GH Actions run #1234) | Session name + source IP |

**Verify no shared accounts:**

```bash
# Scan IAM users
aws iam list-users --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Users[].UserName' | grep -E "(shared|team|ops-admin)"
# Expected: No matches (empty result)
```

**Điều kiện PASS:**
- [ ] ≥5 hành động mapped thành công  
- [ ] Không có shared account pattern
- [ ] Mọi ARN traceable về người thật hoặc bot có run ID

---

## 6. Verification Checklist

| Hạng mục | Pass / Fail | Ghi chú |
|---|---|---|
| **1. Phần Truy Vết** | | |
| CloudTrail logging + validation enabled | ☐ | IsLogging=true, LogFileValidationEnabled=true |
| AWS Config recording enabled | ☐ | Configuration changes tracked |
| EKS Control Plane audit log enabled | ☐ | CloudWatch Log Group active |
| **2. Bảo Vệ Chống Xóa Sửa** | | |
| CloudTrail S3 Object Lock COMPLIANCE | ☐ | Mode="COMPLIANCE", ≥90 days |
| CloudTrail S3 Object Lock verified | ☐ | get-object-lock-configuration pass |
| CloudTrail Operator AccessDenied test | ☐ | Cannot delete CloudTrail logs |
| EKS S3 Object Lock COMPLIANCE | ☐ | Mode="COMPLIANCE", ≥90 days (Anti-Root deletion) |
| EKS S3 Object Lock verified | ☐ | get-object-lock-configuration pass |
| EKS S3 Operator AccessDenied test | ☐ | Cannot delete EKS logs from S3 |
| Kinesis Firehose Stream active | ☐ | Stream status ACTIVE |
| CloudTrail log file validation pass | ☐ | validate-logs command success |
| CloudTrail digest files exist | ☐ | S3 digest folder has .json.gz files |
| **3. Forensic Drill Tests** | | |
| ≥5 scenarios designed | ☐ | Infrastructure, K8s, unauthorized, secrets, on-call |
| ≥3 scenarios drill pass (≤10 phút) | ☐ | Stopwatch timed |
| Identity mapping ≥5 actions | ☐ | ARN → real person |
| Query patterns documented | ☐ | CloudTrail + K8s patterns |
| **4. Chi phí & Non-Functional** | | |
| Chi phí audit logging ≤ $300/tuần | ☐ | Baseline ~$3/week, peak ~$19/week |
| flagd/OpenFeature không bị ảnh hưởng | ☐ | Test checkout sau enable audit log |
| Timeline evidence thật (không cache) | ☐ | Timestamp fresh, stopwatch thật |

**Kết luận cuối:** ☐ PASS / ☐ FAIL / ☐ BLOCKED (lý do: ___)

**Người duyệt CDO07:** Hoàng + Ty | **Ngày:** ___

---

## 7. Checklist trước khi submit PR

- [ ] Tất cả file evidence có timestamp thật (không placeholder)
- [ ] Drill log có ≥3 scenarios pass với stopwatch
- [ ] IAM separation test log có ≥3 AccessDenied results
- [ ] S3 Object Lock COMPLIANCE verified (CloudTrail + EKS logs) + CloudTrail validate-logs pass
- [ ] Identity mapping table có ≥5 hành động với real person
- [ ] Query patterns documented (tái sử dụng được)
- [ ] Runbook cho mentor ready: `mentor-forensic-inspection.md`
- [ ] Không có credential, token, private key trong evidence files
- [ ] metadata.json updated với git SHA thật
- [ ] Tất cả 4 subtask AUD-17.1 → AUD-17.4 Done
- [ ] Hoàng + Ty sign-off

---

