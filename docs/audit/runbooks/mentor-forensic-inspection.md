# Runbook: Hướng Dẫn Mentor Kiểm Tra Forensic Audit Trail

**Phiên bản:** 1.0  
**Ngày:** 14/07/2026  
**Owner:** CDO07 - Team Audit  
**Mục đích:** Hướng dẫn mentor/kiểm toán viên xem audit log và chấm bài forensic tại chỗ

---

## Tổng Quan

TF4 đã bật đầy đủ audit trail ở 2 tầng:
1. **Tầng Cluster (K8s):** EKS Control Plane Audit Log → CloudWatch Logs
2. **Tầng Cloud (AWS):** CloudTrail → S3 + CloudWatch Logs

Mentor sẽ chọn **1 sự kiện thật** đã xảy ra, TF4 sẽ dựng lại timeline **ai-làm-gì-khi-nào** trong **≤10 phút**.

---

## Điều Kiện Tiên Quyết

### AWS Profile
Mentor cần profile có quyền read-only:
- `cloudtrail:LookupEvents`
- `logs:FilterLogEvents`
- `logs:StartQuery`
- `logs:GetQueryResults`

**Profile đề xuất:** `TF4-AuditReadOnlyAndAnalyze`

### Công Cụ
- AWS CLI v2
- `jq` (parse JSON)
- CloudWatch Logs Insights UI (alternative)

---

## Cách Chọn Sự Kiện Kiểm Tra

Mentor có thể chọn 1 trong các loại sự kiện:

| Loại Sự Kiện | Ví Dụ Câu Hỏi | Data Source |
|--------------|---------------|-------------|
| **Config Change** | "Ai đã thay đổi flagd config lúc 15:30 hôm qua?" | K8s audit log |
| **Infrastructure Change** | "Ai đã tăng số node EKS từ 2 lên 4?" | CloudTrail |
| **Unauthorized Access** | "Ai đã cố đọc S3 evidence bucket mà bị chặn?" | CloudTrail (AccessDenied) |
| **On-Call Action** | "Ai đã restart checkout pod lúc 2h sáng?" | K8s audit log + CloudTrail (SSM) |
| **Secrets Access** | "Ai đã decrypt secrets bằng KMS?" | CloudTrail (KMS Decrypt) |

---

## Phương Pháp 1: CloudWatch Logs Insights (UI) - Đơn Giản Nhất

### Bước 1: Truy Cập CloudWatch Logs
1. Đăng nhập AWS Console với profile `TF4-AuditReadOnlyAndAnalyze`
2. Vào **CloudWatch** → **Logs** → **Logs Insights**

### Bước 2: Chọn Log Group
- **K8s audit log:** `/aws/eks/techx-tf4-cluster/cluster`
- **CloudTrail log:** `/aws/cloudtrail/tf4-general-cloudtrail` (nếu có CloudWatch integration)

### Bước 3: Chạy Query

#### Ví Dụ 1: Tìm ConfigMap Update
```sql
fields @timestamp, @message
| filter @message like /ConfigMap/
| filter @message like /update/
| sort @timestamp desc
| limit 20
```

**Time range:** Chọn khoảng thời gian mentor quan tâm (VD: Last 24 hours)

#### Ví Dụ 2: Tìm Pod Delete
```sql
fields @timestamp, @message
| filter @message like /delete/
| filter @message like /pods/
| filter @message like /checkout/
| sort @timestamp desc
| limit 20
```

### Bước 4: Phân Tích Kết Quả
Click vào 1 dòng log → Expand JSON → Tìm:
- `user.username`: Ai làm?
- `objectRef.name`: Resource nào?
- `verb`: Hành động gì? (create, update, delete)
- `timestamp`: Khi nào?

---

## Phương Pháp 2: AWS CLI - Nhanh Hơn Cho Power User

### Bước 1: Query CloudTrail Events

#### Tìm Infrastructure Change
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=UpdateNodegroupConfig \
  --start-time 2026-07-13T00:00:00Z \
  --end-time 2026-07-14T23:59:59Z \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Events[] | {time: .EventTime, user: .Username, event: .EventName, params: (.CloudTrailEvent | fromjson | .requestParameters)}'
```

**Output mẫu:**
```json
{
  "time": "2026-07-13T18:00:05Z",
  "user": "arn:aws:sts::511825856493:assumed-role/TF4-GitHubActions/infra-bot",
  "event": "UpdateNodegroupConfig",
  "params": {
    "name": "techx-tf4-nodegroup",
    "scalingConfig": {
      "desiredSize": 4,
      "minSize": 2,
      "maxSize": 6
    }
  }
}
```

#### Tìm Unauthorized Access
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=GetObject \
  --start-time 2026-07-14T00:00:00Z \
  --end-time 2026-07-14T23:59:59Z \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Events[] | select(.CloudTrailEvent | fromjson | .errorCode == "AccessDenied") | {time: .EventTime, user: .Username, bucket: (.CloudTrailEvent | fromjson | .requestParameters.bucketName)}'
```

#### Tìm KMS Decrypt
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=Decrypt \
  --start-time 2026-07-14T00:00:00Z \
  --end-time 2026-07-14T23:59:59Z \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Events[] | {time: .EventTime, user: .Username, key: .Resources[0].ResourceName}'
```

### Bước 2: Query K8s Audit Log

#### Tìm ConfigMap Update
```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '2026-07-14 15:00:00' +%s)000 \
  --end-time $(date -u -d '2026-07-14 16:00:00' +%s)000 \
  --filter-pattern '"ConfigMap" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.events[] | .message | fromjson | {time: .timestamp, user: .user.username, verb: .verb, object: .objectRef.name}'
```

**Output mẫu:**
```json
{
  "time": "2026-07-14T15:30:12Z",
  "user": "john.doe@techx-corp.com",
  "verb": "update",
  "object": "flagd-config"
}
```

#### Tìm Pod Delete
```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '2026-07-14 02:00:00' +%s)000 \
  --end-time $(date -u -d '2026-07-14 03:00:00' +%s)000 \
  --filter-pattern '"delete" "pods" "checkout"' \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.events[] | .message | fromjson | {time: .timestamp, user: .user.username, verb: .verb, object: .objectRef.name, namespace: .objectRef.namespace}'
```

---

## Phương Pháp 3: Correlate Events (Advanced)

Một số sự kiện cần correlate giữa CloudTrail và K8s audit log:

### Ví Dụ: On-Call Action (Pod Restart)

**Step 1:** Tìm SSM StartSession (người vào bastion)
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time 2026-07-14T02:00:00Z \
  --end-time 2026-07-14T03:00:00Z \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.Events[] | {time: .EventTime, user: .Username}'
```

**Output:**
```json
{
  "time": "2026-07-14T02:29:30Z",
  "user": "arn:aws:sts::511825856493:assumed-role/TF4-OnCall/jane.smith@techx-corp.com"
}
```

**Step 2:** Tìm kubectl delete pod (hành động từ bastion)
```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time $(date -u -d '2026-07-14 02:29:00' +%s)000 \
  --end-time $(date -u -d '2026-07-14 02:35:00' +%s)000 \
  --filter-pattern '"delete" "pods" "checkout"' \
  --profile TF4-AuditReadOnlyAndAnalyze \
  | jq '.events[] | .message | fromjson | {time: .timestamp, user: .user.username}'
```

**Output:**
```json
{
  "time": "2026-07-14T02:30:15Z",
  "user": "jane.smith@techx-corp.com"
}
```

**Timeline kết hợp:**
1. `02:29:30` - jane.smith vào bastion qua SSM
2. `02:30:15` - jane.smith xóa pod `checkout-7d9f8b-xyz`
3. `02:30:18` - K8s tự tạo pod mới `checkout-7d9f8b-abc`

---

## Checklist Chấm Điểm

Mentor có thể dùng checklist này:

### 1. Timeline Accuracy (40 điểm)
- [ ] **Who:** Xác định đúng danh tính (ARN/email/bot name) - 15 điểm
- [ ] **What:** Mô tả đúng hành động (event name, verb, resource) - 10 điểm
- [ ] **When:** Timestamp chính xác (UTC, ±1 phút) - 10 điểm
- [ ] **How:** Method (kubectl/API/console/automation) - 5 điểm

### 2. Speed (30 điểm)
- [ ] ≤5 phút: 30 điểm
- [ ] 5-7 phút: 20 điểm
- [ ] 7-10 phút: 10 điểm
- [ ] >10 phút: 0 điểm

### 3. Evidence Quality (20 điểm)
- [ ] Raw log output chính xác - 10 điểm
- [ ] Correlation logic rõ ràng (nếu multi-source) - 10 điểm

### 4. Tamper-Evident (10 điểm)
- [ ] Chứng minh operator không xóa được log - 10 điểm

**Total: 100 điểm**  
**Pass threshold: ≥70 điểm**

---

## FAQ

### Q1: CloudTrail lag bao lâu?
**A:** Thường ~5-15 phút. Nên chọn sự kiện ≥30 phút trước để đảm bảo log đã có.

### Q2: K8s audit log có bao nhiêu noise?
**A:** Rất nhiều (health check, list pods, etc.). Dùng filter chặt:
- `verb in [create, update, delete]`
- `objectRef.namespace = "techx-tf4"`
- Exclude `verb = get` (read-only)

### Q3: Làm sao biết session name mapping?
**A:** Xem `docs/evidence/aud-17.4-identity-mapping.md` - có bảng mapping ARN → person.

### Q4: Nếu TF4 fail forensic?
**A:** Check:
- Log group có data không? (`aws logs describe-log-streams`)
- Permission có đủ không? (test query 1 lệnh đơn giản)
- Query syntax có đúng không? (test trên CloudWatch Insights UI trước)

---

## Liên Hệ

Nếu mentor gặp vấn đề:
- **Slack:** `#tf4-cdo07-audit`
- **On-Call:** Member 4 (Evidence Collector)

---

## Phụ Lục: Epoch Conversion

Để convert timestamp sang epoch (cho `--start-time`):

### Linux/macOS
```bash
date -u -d '2026-07-14 15:30:00' +%s
# Output: 1783964400
```

### Windows (PowerShell)
```powershell
[DateTimeOffset]::Parse("2026-07-14T15:30:00Z").ToUnixTimeSeconds()
# Output: 1783964400
```

CloudWatch Logs API cần epoch **milliseconds** → nhân 1000:
```bash
$(date -u -d '2026-07-14 15:30:00' +%s)000
# Output: 1783964400000
```

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-14 | CDO07 | Initial version |
