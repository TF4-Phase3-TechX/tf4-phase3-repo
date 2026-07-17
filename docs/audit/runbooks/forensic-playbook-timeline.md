# Playbook: Dựng Timeline Forensic từ Audit Log / Trace
## CDO07 — Mandate 4 · Forensic Drill

> **Mục tiêu:** Khi mentor chọn 1 sự kiện (config change hoặc flag toggle), CDO07 dựng lại
> **ai-làm-gì-khi-nào** chỉ từ audit log trong ≤10 phút, ngay trước mặt.
>


| Thông tin | Giá trị |
|---|---|
| Cluster | `techx-tf4-cluster` |
| Region | `us-east-1` |
| Profile AWS | `TF4-AuditReadOnlyAndAnalyze-511825856493` |
| CloudTrail | `tf4-general-cloudtrail` |
| K8s Log Group | `/aws/eks/techx-tf4-cluster/cluster` |
| Namespace ứng dụng | `techx-tf4` |

---

## Phần 1: Chuẩn bị trước khi bị hỏi (≤2 phút)

### 1.1 Xác nhận credentials còn hạn

```bash
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

Kết quả phải trả về ARN `TF4-AuditReadOnlyAndAnalyze` và account `511825856493`.
Nếu expired → chạy `aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493` ngay.

### 1.2 Xác nhận kubeconfig

```bash
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1
kubectl -n techx-tf4 get pods --request-timeout=10s 2>&1 | head -5
```

Phải thấy danh sách pods. Nếu lỗi → check VPN / bastion tunnel.

### 1.3 Chuẩn bị epoch calculator (dùng khi mentor đưa timestamp)

```powershell
# Windows PowerShell — đổi timestamp sang epoch milliseconds cho CloudWatch
$t = [DateTimeOffset]::Parse("2026-07-14T07:15:00Z")
$epochMs = $t.ToUnixTimeMilliseconds()
Write-Output "Epoch ms: $epochMs"
```

```bash
# Linux/macOS
date -u -d '2026-07-14 07:15:00' +%s000
```

---

## Phần 2: Quy trình 4 bước — ≤10 phút

```
Bước 1: Phân loại sự kiện (1 phút)
    ↓
Bước 2: Chọn nguồn log & build query (2 phút)
    ↓
Bước 3: Chạy query, đọc kết quả (4 phút)
    ↓
Bước 4: Trình bày ai-làm-gì-khi-nào (3 phút)
```

### Bước 1: Phân loại sự kiện (1 phút)

| Loại sự kiện | Nguồn chính | Nguồn phụ |
|---|---|---|
| ConfigMap update (K8s config) | K8s Audit Log (CloudWatch) | CloudTrail nếu qua API |
| Flag toggle (flagd) | K8s Audit Log — ConfigMap `flagd-config` | — |
| Node scale / EKS change | CloudTrail | K8s events |
| SSM bastion access | CloudTrail | — |
| IAM / AWS API call | CloudTrail | — |
| kubectl exec / port-forward | K8s Audit Log | — |
| Pod restart / deployment | K8s events + K8s Audit Log | — |

> **Rule nhanh:** Hành động trong cluster → K8s Audit Log. Hành động AWS API → CloudTrail.

### Bước 2: Build query (2 phút)

**Trường hợp A — Sự kiện trong Kubernetes (config change, flag toggle, kubectl action):**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"ConfigMap" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.resource == "configmaps")
        | {
            time:      .requestReceivedTimestamp,
            user:      .user.username,
            verb:      .verb,
            object:    .objectRef.name,
            namespace: .objectRef.namespace,
            sourceIP:  .sourceIPs[0],
            userAgent: .userAgent,
            status:    .responseStatus.code
          }'
```

**Trường hợp B — Flag toggle cụ thể (flagd-config ConfigMap):**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"flagd" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.name | test("flagd"))
        | {time: .requestReceivedTimestamp, user: .user.username, verb: .verb, object: .objectRef.name, status: .responseStatus.code}'
```

**Trường hợp C — Bất kỳ hành động nào của 1 user cụ thể trong K8s:**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"TÊN_USER"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.user.username | test("TÊN_USER"; "i"))
        | {time: .requestReceivedTimestamp, verb: .verb, resource: .objectRef.resource, name: .objectRef.name}'
```

**Trường hợp D — AWS API call / CloudTrail (infra change, SSM, IAM):**

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=TÊN_EVENT \
  --start-time "2026-07-14T07:00:00Z" \
  --end-time "2026-07-14T08:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:   .EventTime,
      event:  .EventName,
      user:   .Username,
      source: .EventSource,
      raw:    (.CloudTrailEvent | fromjson | {userArn: .userIdentity.arn, sourceIP: .sourceIPAddress})
    }'
```

### Bước 3: Đọc kết quả (4 phút)

| Trường | Ý nghĩa | Nơi tìm |
|---|---|---|
| `time` / `requestReceivedTimestamp` | Khi nào xảy ra | K8s audit log |
| `user.username` | Ai làm — email SSO hoặc role | K8s audit log |
| `verb` | Làm gì — get/create/update/delete | K8s audit log |
| `objectRef.name` | Tác động lên resource nào | K8s audit log |
| `responseStatus.code` | Thành công (200/201) hay bị chặn (403) | K8s audit log |
| `EventTime` | Khi nào xảy ra | CloudTrail |
| `Username` | Ai làm — session name = email SSO | CloudTrail |
| `userIdentity.arn` | Traceable về người/role | CloudTrail |
| `sourceIPAddress` | Từ đâu | CloudTrail |

> **Đọc nhanh:** Nhìn `user.username` và `time` trước. Nếu không thấy gì → mở rộng time window thêm ±30 phút.

### Bước 4: Trình bày (3 phút)

```
WHO:   [email/username/ARN từ log]
WHAT:  [verb] [resource] "[object name]"  ← ví dụ: update ConfigMap "flagd-config"
WHEN:  [timestamp UTC]  =  [timestamp +07]  ← đổi múi giờ trực tiếp
HOW:   kubectl / AWS Console / CI/CD (đọc từ userAgent hoặc source IP)
```

Ví dụ trả lời chuẩn:
> "Lúc 07:30:12 UTC (14:30:12 +07), `phuong@techx-corp.com` đã chạy `kubectl port-forward`
> vào pod grafana trong namespace `techx-tf4`, xác nhận qua K8s audit log với verb `create`
> trên resource `pods/portforward`. Source IP `10.x.x.x` từ trong VPC."

---

## Phần 3: Kịch bản cụ thể — đã được chuẩn bị sẵn

### Scenario A: Config change — K8s action (incident 20260714)

**Câu hỏi mentor có thể hỏi:** "Ai đã truy cập Grafana lúc ~14:25 ngày 14/07?"

```bash
# Epoch: 14:20 +07 = 07:20 UTC = 1752384000000 ms
# Epoch: 14:35 +07 = 07:35 UTC = 1752384900000 ms

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time 1752384000000 \
  --end-time 1752384900000 \
  --filter-pattern '"portforward" "grafana"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | {time: .requestReceivedTimestamp, user: .user.username, verb: .verb, resource: .objectRef.resource, name: .objectRef.name}'
```

**Trả lời:** WHO=phuong (TF4-SecReliabilityReadOnlyAudit), WHAT=kubectl port-forward vào Grafana pod,
WHEN=07:25:39 UTC (14:25:39 +07), HOW=kubectl từ bastion.

---

### Scenario B: Flag toggle — flagd ConfigMap update

**Câu hỏi mentor có thể hỏi:** "Ai đã thay đổi flagd config?"

```bash
# Epoch: 2026-07-09T00:00:00Z = 1752019200000

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time 1752019200000 \
  --filter-pattern '"configmaps"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.resource == "configmaps")
        | select(.verb | IN("update", "patch", "create", "delete"))
        | select(.user.username | test("system:") | not)
        | {time: .requestReceivedTimestamp, user: .user.username, verb: .verb, object: .objectRef.name, ns: .objectRef.namespace}'
```

**Lưu ý ADR-012:** flagd hiện dùng local file. Nếu BTC toggle flag, action đó ở hệ thống BTC — không thấy trong K8s audit log TF4. Kết quả "không có event" là negative forensic finding hợp lệ.

---

### Scenario C: SSM bastion access (CloudTrail)

**Câu hỏi mentor có thể hỏi:** "Tối 13/07 ai vào bastion?"

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time "2026-07-13T16:00:00Z" \
  --end-time "2026-07-14T02:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:    .EventTime,
      user:    .Username,
      target:  (.CloudTrailEvent | fromjson | .requestParameters.target),
      session: (.CloudTrailEvent | fromjson | .responseElements.sessionId),
      srcIP:   (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

**Trả lời:** nguyen, cdo04-an, anngo, huyhoang, hung.hoangkim — 10 sessions, 23:27 ngày 13/07 → 01:15 ngày 14/07 +07. Ngay sau CDO08 deploy SEC-05, team verify ingress hardening.

---

## Phần 4: Xử lý khi gặp sự cố lúc drill

### Không thấy event nào trong time window

```
1. Mở rộng window: ±30 phút, ±1 giờ, ±1 ngày
2. Bỏ filter phụ, chỉ giữ filter chính
3. Check lại epoch: đã nhân 1000 để ra milliseconds chưa?
4. Kiểm tra log stream có active không:
   aws logs describe-log-streams \
     --log-group-name /aws/eks/techx-tf4-cluster/cluster \
     --order-by LastEventTime --descending --max-items 3 \
     --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### jq parse lỗi

```bash
# Bỏ jq, xem raw text trước để debug
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_MS \
  --filter-pattern '"ConfigMap"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | grep -o '"username":"[^"]*"' | sort | uniq
```

### CloudTrail lookup-events chậm

Dùng CloudTrail console filter trực tiếp, hoặc CloudWatch Logs Insights nếu đã setup CWL integration.

### Credentials hết hạn giữa chừng

```bash
aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

---

## Phần 5: Chứng minh log không sửa được (Tamper-Evident)

Khi mentor hỏi "làm sao tôi tin log này không bị sửa?":

**Lập luận 1 — Separation of Duties (ADR-001):**
> "CDO07 chỉ có Read-only profile. Không có quyền write vào CloudWatch Logs, S3 CloudTrail bucket.
> Operator (CDO04/CDO08) thực thi infrastructure, CDO07 verify độc lập."

**Lập luận 2 — S3 Versioning:**
> "S3 bucket `tf4-cloudtrail-logs-bucket-511825856493` có versioning Enabled.
> Ngay cả nếu file bị overwrite, version cũ vẫn còn."

```bash
aws s3api list-object-versions \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --prefix AWSLogs/511825856493/CloudTrail/ \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Versions | length'
```

**Lập luận 3 — IAM không có DeleteObject:**
> "Operator roles không có `s3:DeleteObject`, `cloudtrail:StopLogging`, hay `logs:DeleteLogStream`.
> Người vận hành không tự xóa vết của mình."

**Gap cần thành thật nêu:**
> "CloudTrail `LogFileValidationEnabled` hiện là `false` — ticket AUDIT-011 đã tạo cho CDO04 fix.
> Trong thời gian chờ, S3 versioning + Separation of Duties là compensating control."

---

## Phần 6: Checklist trước khi vào phòng với mentor

- [ ] AWS SSO login còn hạn: `aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493`
- [ ] kubeconfig updated: `aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1`
- [ ] Terminal mở sẵn, profile đã set
- [ ] File này in ra hoặc mở sẵn trên màn hình thứ 2
- [ ] Biết epoch của 2026-07-14 07:15Z = `1752383700000`
- [ ] Biết epoch của 2026-07-14 07:30Z = `1752384600000`
- [ ] Biết epoch của 2026-07-09 00:00Z = `1752019200000`
- [ ] Incident report `incident-20260714-checkout-payment.md` mở sẵn (Scenario A data)

---

**Playbook version:** 1.1
**Tác giả:** CDO07 — Hoàng Kim Hùng
**Ngày:** 2026-07-15
**Drill log:** `docs/evidence/mandate-04-forensic/aud-17.2-drill-log.md`
