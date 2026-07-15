# Playbook: Dựng Timeline Forensic từ Audit Log / Trace
## CDO07 �?" Mandate 4 · Forensic Drill

> **Mục tiêu:** Khi mentor chọn 1 sự ki�?n (config change hoặc flag toggle), CDO07 dựng lại
> **ai-làm-gì-khi-nào** ch�? từ audit log trong �?�10 phút, ngay trư�>c mặt.
>
> Playbook này là tài li�?u tác chiến �?" in ra, �'�f bàn, dùng khi b�< hỏi live.

| Thông tin | Giá tr�< |
|---|---|
| Cluster | `techx-tf4-cluster` |
| Region | `us-east-1` |
| Profile AWS | `TF4-AuditReadOnlyAndAnalyze` |
| CloudTrail | `tf4-general-cloudtrail` |
| K8s Log Group | `/aws/eks/techx-tf4-cluster/cluster` |
| Namespace ứng dụng | `techx-tf4` |

---

## Phần 1: Chuẩn b�< trư�>c khi b�< hỏi (�?�2 phút)

### 1.1 Xác nhận credentials còn hạn

```bash
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

Kết quả phải trả về ARN `TF4-AuditReadOnlyAndAnalyze` và account `511825856493`.
Nếu expired �?' chạy `aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493` ngay.

### 1.2 Xác nhận kubeconfig

```bash
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1
kubectl -n techx-tf4 get pods --request-timeout=10s 2>&1 | head -5
```

Phải thấy danh sách pods. Nếu l�-i �?' check VPN / bastion tunnel.

### 1.3 Chuẩn b�< epoch calculator (dùng khi mentor �'ưa timestamp)

```powershell
# Windows PowerShell �?" �'�.i timestamp sang epoch milliseconds cho CloudWatch
$t = [DateTimeOffset]::Parse("2026-07-14T07:15:00Z")
$epochMs = $t.ToUnixTimeMilliseconds()
Write-Output "Epoch ms: $epochMs"
```

```bash
# Linux/macOS
date -u -d '2026-07-14 07:15:00' +%s000
```

---

## Phần 2: Quy trình 4 bư�>c �?" �?�10 phút

Khi mentor �'ưa sự ki�?n, thực hi�?n theo �'úng thứ tự này:

```
Bư�>c 1: Phân loại sự ki�?n (1 phút)
    �?"
Bư�>c 2: Chọn ngu�"n log & build query (2 phút)
    �?"
Bư�>c 3: Chạy query, �'ọc kết quả (4 phút)
    �?"
Bư�>c 4: Trình bày ai-làm-gì-khi-nào (3 phút)
```

### Bư�>c 1: Phân loại sự ki�?n (1 phút)

Mentor nói gì �?' chọn ngu�"n log nào:

| Loại sự ki�?n | Ngu�"n chính | Ngu�"n phụ |
|---|---|---|
| ConfigMap update (K8s config) | K8s Audit Log (CloudWatch) | CloudTrail nếu qua API |
| Flag toggle (flagd) | K8s Audit Log �?" ConfigMap `flagd-config` | �?" |
| Node scale / EKS change | CloudTrail | K8s events |
| SSM bastion access | CloudTrail | �?" |
| IAM / AWS API call | CloudTrail | �?" |
| kubectl exec / port-forward | K8s Audit Log | �?" |
| Pod restart / deployment | K8s events + K8s Audit Log | �?" |

> **Rule nhanh:** Hành �'�Tng trong cluster �?' K8s Audit Log. Hành �'�Tng AWS API �?' CloudTrail.

### Bư�>c 2: Build query (2 phút)

**Trường hợp A �?" Sự ki�?n trong Kubernetes (config change, flag toggle, kubectl action):**

```bash
# Query K8s audit log �?" CloudWatch Logs Insights
# Điền: START_EPOCH_MS và END_EPOCH_MS từ Phần 1.3

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"ConfigMap" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.resource == "configmaps")
        | {
            time:       .requestReceivedTimestamp,
            user:       .user.username,
            verb:       .verb,
            object:     .objectRef.name,
            namespace:  .objectRef.namespace,
            sourceIP:   .sourceIPs[0],
            userAgent:  .userAgent,
            status:     .responseStatus.code
          }'
```

**Trường hợp B �?" Flag toggle cụ th�f (flagd-config ConfigMap):**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"flagd" "update"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.name | test("flagd"))
        | {
            time:    .requestReceivedTimestamp,
            user:    .user.username,
            verb:    .verb,
            object:  .objectRef.name,
            status:  .responseStatus.code
          }'
```

**Trường hợp C �?" Bất kỳ hành �'�Tng nào của 1 user cụ th�f trong K8s:**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"T�SN_USER"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.user.username | test("T�SN_USER"; "i"))
        | {time: .requestReceivedTimestamp, verb: .verb, resource: .objectRef.resource, name: .objectRef.name}'
```

**Trường hợp D �?" AWS API call / CloudTrail (infra change, SSM, IAM):**

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=T�SN_EVENT \
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

### Bư�>c 3: Đọc kết quả (4 phút)

Các trường cần �'ọc ngay:

| Trường | Ý nghĩa | Nơi tìm |
|---|---|---|
| `time` / `requestReceivedTimestamp` | Khi nào xảy ra | K8s audit log |
| `user.username` | Ai làm �?" email SSO hoặc role | K8s audit log |
| `verb` | Làm gì �?" get/create/update/delete | K8s audit log |
| `objectRef.name` | Tác �'�Tng lên resource nào | K8s audit log |
| `responseStatus.code` | Thành công (200/201) hay b�< chặn (403) | K8s audit log |
| `EventTime` | Khi nào xảy ra | CloudTrail |
| `Username` | Ai làm �?" session name = email SSO | CloudTrail |
| `userIdentity.arn` | Traceable về người/role | CloudTrail |
| `sourceIPAddress` | Từ �'âu | CloudTrail |

> **Đọc nhanh:** Nhìn `user.username` và `time` trư�>c. Nếu không thấy gì �?' m�Y r�Tng time window thêm ±30 phút.

### Bư�>c 4: Trình bày (3 phút)

Trả lời �'úng 4 câu �?" không thêm không b�>t:

```
WHO:   [email/username/ARN từ log]
WHAT:  [verb] [resource] "[object name]"  �?� ví dụ: update ConfigMap "flagd-config"
WHEN:  [timestamp UTC]  =  [timestamp +07]  �?� �'�.i múi giờ trực tiếp
HOW:   kubectl / AWS Console / CI/CD (�'ọc từ userAgent hoặc source IP)
```

Ví dụ trả lời chuẩn:
> "Lúc 07:30:12 UTC (14:30:12 +07), `phuong@techx-corp.com` �'ã chạy `kubectl port-forward`
> vào pod grafana trong namespace `techx-tf4`, xác nhận qua K8s audit log v�>i verb `create`
> trên resource `pods/portforward`. Source IP `10.x.x.x` từ trong VPC."

---

## Phần 3: K�<ch bản cụ th�f �?" �'ã �'ược chuẩn b�< sẵn

### Scenario A: Config change �?" K8s action (incident 20260714)

**Sự ki�?n thật:** Team �'iều tra sự c�' checkout 14/07, `phuong` + `nam` + bastion
port-forward vào Grafana/Jaeger lúc 14:25�?"14:27 +07.

**Câu hỏi mentor có th�f hỏi:** "Ai �'ã truy cập Grafana lúc ~14:25 ngày 14/07?"

**Query:**

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

**Kết quả mong �'ợi:**

```json
{
  "time":     "2026-07-14T07:25:39Z",
  "user":     "phuong",
  "verb":     "create",
  "resource": "pods/portforward",
  "name":     "grafana-b9fc94c47-..."
}
```

**Trả lời:** WHO=phuong (TF4-SecReliabilityReadOnlyAudit), WHAT=kubectl port-forward vào Grafana pod,
WHEN=07:25:39 UTC (14:25:39 +07), HOW=kubectl từ bastion.

---

### Scenario B: Flag toggle �?" flagd ConfigMap update

**Sự ki�?n thật (hoặc test event):** Ai �'ó update ConfigMap `flagd-config`
�'�f thay �'�.i flag value (bật/tắt feature flag).

**Câu hỏi mentor có th�f hỏi:** "Ai �'ã thay �'�.i flagd config?"

**Query �?" bư�>c 1: tìm mọi update ConfigMap trong 7 ngày:**

```bash
# 7 ngày trư�>c: tính epoch của 2026-07-09T00:00:00Z
# PowerShell: [DateTimeOffset]::Parse("2026-07-09T00:00:00Z").ToUnixTimeMilliseconds()
# �?' 1752019200000

aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time 1752019200000 \
  --filter-pattern '"flagd" "configmaps"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.objectRef.resource == "configmaps")
        | select(.objectRef.name | test("flagd"; "i"))
        | select(.verb | IN("update", "patch", "create", "delete"))
        | {
            time:      .requestReceivedTimestamp,
            user:      .user.username,
            verb:      .verb,
            object:    .objectRef.name,
            namespace: .objectRef.namespace,
            userAgent: .userAgent,
            status:    .responseStatus.code
          }'
```

**Query �?" bư�>c 2 (nếu bư�>c 1 không thấy): m�Y r�Tng filter:**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time 1752019200000 \
  --filter-pattern '"update" "configmaps"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.verb == "update" or .verb == "patch")
        | select(.objectRef.resource == "configmaps")
        | {time: .requestReceivedTimestamp, user: .user.username, object: .objectRef.name, ns: .objectRef.namespace}'
```

**Nếu flagd sync từ central (khi fix xong):** Flag toggle qua HTTP sync �?"
không thấy trong K8s audit log. Dùng CloudTrail lookup cho event `PutParameter` (SSM)
hoặc hỏi BTC cho audit log của central flag service.

---

### Scenario C: SSM bastion access (CloudTrail)

**Sự ki�?n thật:** `quang.tranminh` m�Y SSM tunnel vào bastion lúc 00:07�?"00:08 UTC ngày 14/07.
Đã có evidence tại `SSM-startsession-cloudtrail.md`.

**Query:**

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time "2026-07-14T00:00:00Z" \
  --end-time "2026-07-14T01:00:00Z" \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Events[] | {
      time:    .EventTime,
      user:    .Username,
      target:  (.CloudTrailEvent | fromjson | .requestParameters.target),
      session: (.CloudTrailEvent | fromjson | .responseElements.sessionId),
      srcIP:   (.CloudTrailEvent | fromjson | .sourceIPAddress)
    }'
```

**Trả lời:** WHO=quang.tranminh (AuditReadOnlyAndAnalyze role),
WHAT=StartSession SSM vào bastion `i-072084d1cf0b2f1c9`,
WHEN=00:07:14 UTC (07:07:14 +07), HOW=AWS SSM Console/CLI từ IP `118.68.56.162`.

---

## Phần 4: Xử lý khi gặp sự c�' lúc drill

### Không thấy event nào trong time window

```
1. M�Y r�Tng window: ±30 phút, ±1 giờ, ±1 ngày
2. Bỏ filter phụ, ch�? giữ filter chính
3. Check lại epoch: �'ã nhân 1000 �'�f ra milliseconds chưa?
4. Ki�fm tra log stream có active không:
   aws logs describe-log-streams \
     --log-group-name /aws/eks/techx-tf4-cluster/cluster \
     --order-by LastEventTime --descending --max-items 3 \
     --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### jq parse l�-i

```bash
# Bỏ jq, xem raw text trư�>c
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_MS \
  --filter-pattern '"ConfigMap"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | grep -o '"username":"[^"]*"' | sort | uniq
```

### CloudTrail lookup-events chậm

```bash
# Dùng CloudWatch Logs Insights thay thế (nhanh hơn v�>i large dataset)
# Log group: /aws/cloudtrail/tf4-general-cloudtrail (nếu �'ã setup CWL integration)
# Hoặc dùng CloudTrail console filter trực tiếp
```

### Credentials hết hạn giữa chừng

```bash
aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493
# Sau �'ó chạy lại query
```

---

## Phần 5: Chứng minh log không sửa �'ược (Tamper-Evident)

Khi mentor hỏi "làm sao tôi tin log này không b�< sửa?":

**Lập luận 1 �?" Separation of Duties (ADR-001):**
> "CDO07 ch�? có Read-only profile. Không có quyền write vào CloudWatch Logs, S3 CloudTrail bucket,
> hoặc bất kỳ resource nào. Operator (CDO04/CDO08) thực thi infrastructure,
> CDO07 verify �'�Tc lập �?" không có conflict of interest."

**Lập luận 2 �?" S3 Versioning:**
> "S3 bucket `tf4-cloudtrail-logs-bucket-511825856493` có versioning Enabled.
> Ngay cả nếu file b�< overwrite, version cũ vẫn còn. Có th�f verify bằng:"

```bash
aws s3api list-object-versions \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --prefix AWSLogs/511825856493/CloudTrail/ \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Versions | length'
```

**Lập luận 3 �?" IAM không có DeleteObject:**
> "Operator roles không có `s3:DeleteObject`, `cloudtrail:StopLogging`,
> hay `logs:DeleteLogStream` trong policy. Người vận hành không tự xóa vết của mình."

**Đi�fm yếu cần thành thật nêu:**
> "CloudTrail `LogFileValidationEnabled` hi�?n là `false` �?" chúng tôi �'ã tạo
> ticket AUDIT-011 yêu cầu CDO04 fix Terraform. Đây là gap �'ang trong quá trình fix.
> Trong thời gian chờ, S3 versioning + Separation of Duties là compensating control."

---

## Phần 6: Checklist trư�>c khi vào phòng v�>i mentor

- [ ] AWS SSO login còn hạn (test `aws sts get-caller-identity`)
- [ ] kubeconfig updated
- [ ] Terminal m�Y sẵn, profile �'ã set
- [ ] File này in ra hoặc m�Y sẵn trên màn hình thứ 2
- [ ] Biết epoch của 2026-07-14 07:15Z = `1752383700000`
- [ ] Biết epoch của 2026-07-14 07:30Z = `1752384600000`
- [ ] Incident report `incident-20260714-checkout-payment.md` m�Y sẵn (Scenario A data)

---

**Playbook version:** 1.0
**Tác giả:** CDO07 �?" Hoàng Kim Hùng
**Ngày:** 2026-07-15
**Kế tiếp:** Xem drill log tại `aud-17.2-drill-log.md`
