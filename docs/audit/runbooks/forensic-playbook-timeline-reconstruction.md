# Playbook: Dá»±ng Timeline Forensic tá»« Audit Log / Trace
## CDO07 â€” Mandate 4 Â· Forensic Drill

> **Má»¥c tiÃªu:** Khi mentor chá»n 1 sá»± kiá»‡n (config change hoáº·c flag toggle), CDO07 dá»±ng láº¡i
> **ai-lÃ m-gÃ¬-khi-nÃ o** chá»‰ tá»« audit log trong â‰¤10 phÃºt, ngay trÆ°á»›c máº·t.
>
> Playbook nÃ y lÃ  tÃ i liá»‡u tÃ¡c chiáº¿n â€” in ra, Ä‘á»ƒ bÃ n, dÃ¹ng khi bá»‹ há»i live.

| ThÃ´ng tin | GiÃ¡ trá»‹ |
|---|---|
| Cluster | `techx-tf4-cluster` |
| Region | `us-east-1` |
| Profile AWS | `TF4-AuditReadOnlyAndAnalyze` |
| CloudTrail | `tf4-general-cloudtrail` |
| K8s Log Group | `/aws/eks/techx-tf4-cluster/cluster` |
| Namespace á»©ng dá»¥ng | `techx-tf4` |

---

## Pháº§n 1: Chuáº©n bá»‹ trÆ°á»›c khi bá»‹ há»i (â‰¤2 phÃºt)

### 1.1 XÃ¡c nháº­n credentials cÃ²n háº¡n

```bash
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

Káº¿t quáº£ pháº£i tráº£ vá» ARN `TF4-AuditReadOnlyAndAnalyze` vÃ  account `511825856493`.
Náº¿u expired â†’ cháº¡y `aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493` ngay.

### 1.2 XÃ¡c nháº­n kubeconfig

```bash
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1
kubectl -n techx-tf4 get pods --request-timeout=10s 2>&1 | head -5
```

Pháº£i tháº¥y danh sÃ¡ch pods. Náº¿u lá»—i â†’ check VPN / bastion tunnel.

### 1.3 Chuáº©n bá»‹ epoch calculator (dÃ¹ng khi mentor Ä‘Æ°a timestamp)

```powershell
# Windows PowerShell â€” Ä‘á»•i timestamp sang epoch milliseconds cho CloudWatch
$t = [DateTimeOffset]::Parse("2026-07-14T07:15:00Z")
$epochMs = $t.ToUnixTimeMilliseconds()
Write-Output "Epoch ms: $epochMs"
```

```bash
# Linux/macOS
date -u -d '2026-07-14 07:15:00' +%s000
```

---

## Pháº§n 2: Quy trÃ¬nh 4 bÆ°á»›c â€” â‰¤10 phÃºt

Khi mentor Ä‘Æ°a sá»± kiá»‡n, thá»±c hiá»‡n theo Ä‘Ãºng thá»© tá»± nÃ y:

```
BÆ°á»›c 1: PhÃ¢n loáº¡i sá»± kiá»‡n (1 phÃºt)
    â†“
BÆ°á»›c 2: Chá»n nguá»“n log & build query (2 phÃºt)
    â†“
BÆ°á»›c 3: Cháº¡y query, Ä‘á»c káº¿t quáº£ (4 phÃºt)
    â†“
BÆ°á»›c 4: TrÃ¬nh bÃ y ai-lÃ m-gÃ¬-khi-nÃ o (3 phÃºt)
```

### BÆ°á»›c 1: PhÃ¢n loáº¡i sá»± kiá»‡n (1 phÃºt)

Mentor nÃ³i gÃ¬ â†’ chá»n nguá»“n log nÃ o:

| Loáº¡i sá»± kiá»‡n | Nguá»“n chÃ­nh | Nguá»“n phá»¥ |
|---|---|---|
| ConfigMap update (K8s config) | K8s Audit Log (CloudWatch) | CloudTrail náº¿u qua API |
| Flag toggle (flagd) | K8s Audit Log â€” ConfigMap `flagd-config` | â€” |
| Node scale / EKS change | CloudTrail | K8s events |
| SSM bastion access | CloudTrail | â€” |
| IAM / AWS API call | CloudTrail | â€” |
| kubectl exec / port-forward | K8s Audit Log | â€” |
| Pod restart / deployment | K8s events + K8s Audit Log | â€” |

> **Rule nhanh:** HÃ nh Ä‘á»™ng trong cluster â†’ K8s Audit Log. HÃ nh Ä‘á»™ng AWS API â†’ CloudTrail.

### BÆ°á»›c 2: Build query (2 phÃºt)

**TrÆ°á»ng há»£p A â€” Sá»± kiá»‡n trong Kubernetes (config change, flag toggle, kubectl action):**

```bash
# Query K8s audit log â€” CloudWatch Logs Insights
# Äiá»n: START_EPOCH_MS vÃ  END_EPOCH_MS tá»« Pháº§n 1.3

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

**TrÆ°á»ng há»£p B â€” Flag toggle cá»¥ thá»ƒ (flagd-config ConfigMap):**

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

**TrÆ°á»ng há»£p C â€” Báº¥t ká»³ hÃ nh Ä‘á»™ng nÃ o cá»§a 1 user cá»¥ thá»ƒ trong K8s:**

```bash
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_EPOCH_MS \
  --end-time END_EPOCH_MS \
  --filter-pattern '"TÃŠN_USER"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.events[] | .message | fromjson
        | select(.user.username | test("TÃŠN_USER"; "i"))
        | {time: .requestReceivedTimestamp, verb: .verb, resource: .objectRef.resource, name: .objectRef.name}'
```

**TrÆ°á»ng há»£p D â€” AWS API call / CloudTrail (infra change, SSM, IAM):**

```bash
aws cloudtrail lookup-events \
  --region us-east-1 \
  --lookup-attributes AttributeKey=EventName,AttributeValue=TÃŠN_EVENT \
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

### BÆ°á»›c 3: Äá»c káº¿t quáº£ (4 phÃºt)

CÃ¡c trÆ°á»ng cáº§n Ä‘á»c ngay:

| TrÆ°á»ng | Ã nghÄ©a | NÆ¡i tÃ¬m |
|---|---|---|
| `time` / `requestReceivedTimestamp` | Khi nÃ o xáº£y ra | K8s audit log |
| `user.username` | Ai lÃ m â€” email SSO hoáº·c role | K8s audit log |
| `verb` | LÃ m gÃ¬ â€” get/create/update/delete | K8s audit log |
| `objectRef.name` | TÃ¡c Ä‘á»™ng lÃªn resource nÃ o | K8s audit log |
| `responseStatus.code` | ThÃ nh cÃ´ng (200/201) hay bá»‹ cháº·n (403) | K8s audit log |
| `EventTime` | Khi nÃ o xáº£y ra | CloudTrail |
| `Username` | Ai lÃ m â€” session name = email SSO | CloudTrail |
| `userIdentity.arn` | Traceable vá» ngÆ°á»i/role | CloudTrail |
| `sourceIPAddress` | Tá»« Ä‘Ã¢u | CloudTrail |

> **Äá»c nhanh:** NhÃ¬n `user.username` vÃ  `time` trÆ°á»›c. Náº¿u khÃ´ng tháº¥y gÃ¬ â†’ má»Ÿ rá»™ng time window thÃªm Â±30 phÃºt.

### BÆ°á»›c 4: TrÃ¬nh bÃ y (3 phÃºt)

Tráº£ lá»i Ä‘Ãºng 4 cÃ¢u â€” khÃ´ng thÃªm khÃ´ng bá»›t:

```
WHO:   [email/username/ARN tá»« log]
WHAT:  [verb] [resource] "[object name]"  â† vÃ­ dá»¥: update ConfigMap "flagd-config"
WHEN:  [timestamp UTC]  =  [timestamp +07]  â† Ä‘á»•i mÃºi giá» trá»±c tiáº¿p
HOW:   kubectl / AWS Console / CI/CD (Ä‘á»c tá»« userAgent hoáº·c source IP)
```

VÃ­ dá»¥ tráº£ lá»i chuáº©n:
> "LÃºc 07:30:12 UTC (14:30:12 +07), `phuong@techx-corp.com` Ä‘Ã£ cháº¡y `kubectl port-forward`
> vÃ o pod grafana trong namespace `techx-tf4`, xÃ¡c nháº­n qua K8s audit log vá»›i verb `create`
> trÃªn resource `pods/portforward`. Source IP `10.x.x.x` tá»« trong VPC."

---

## Pháº§n 3: Ká»‹ch báº£n cá»¥ thá»ƒ â€” Ä‘Ã£ Ä‘Æ°á»£c chuáº©n bá»‹ sáºµn

### Scenario A: Config change â€” K8s action (incident 20260714)

**Sá»± kiá»‡n tháº­t:** Team Ä‘iá»u tra sá»± cá»‘ checkout 14/07, `phuong` + `nam` + bastion
port-forward vÃ o Grafana/Jaeger lÃºc 14:25â€“14:27 +07.

**CÃ¢u há»i mentor cÃ³ thá»ƒ há»i:** "Ai Ä‘Ã£ truy cáº­p Grafana lÃºc ~14:25 ngÃ y 14/07?"

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

**Káº¿t quáº£ mong Ä‘á»£i:**

```json
{
  "time":     "2026-07-14T07:25:39Z",
  "user":     "phuong",
  "verb":     "create",
  "resource": "pods/portforward",
  "name":     "grafana-b9fc94c47-..."
}
```

**Tráº£ lá»i:** WHO=phuong (TF4-SecReliabilityReadOnlyAudit), WHAT=kubectl port-forward vÃ o Grafana pod,
WHEN=07:25:39 UTC (14:25:39 +07), HOW=kubectl tá»« bastion.

---

### Scenario B: Flag toggle â€” flagd ConfigMap update

**Sá»± kiá»‡n tháº­t (hoáº·c test event):** Ai Ä‘Ã³ update ConfigMap `flagd-config`
Ä‘á»ƒ thay Ä‘á»•i flag value (báº­t/táº¯t feature flag).

**CÃ¢u há»i mentor cÃ³ thá»ƒ há»i:** "Ai Ä‘Ã£ thay Ä‘á»•i flagd config?"

**Query â€” bÆ°á»›c 1: tÃ¬m má»i update ConfigMap trong 7 ngÃ y:**

```bash
# 7 ngÃ y trÆ°á»›c: tÃ­nh epoch cá»§a 2026-07-09T00:00:00Z
# PowerShell: [DateTimeOffset]::Parse("2026-07-09T00:00:00Z").ToUnixTimeMilliseconds()
# â†’ 1752019200000

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

**Query â€” bÆ°á»›c 2 (náº¿u bÆ°á»›c 1 khÃ´ng tháº¥y): má»Ÿ rá»™ng filter:**

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

**Náº¿u flagd sync tá»« central (khi fix xong):** Flag toggle qua HTTP sync â€”
khÃ´ng tháº¥y trong K8s audit log. DÃ¹ng CloudTrail lookup cho event `PutParameter` (SSM)
hoáº·c há»i BTC cho audit log cá»§a central flag service.

---

### Scenario C: SSM bastion access (CloudTrail)

**Sá»± kiá»‡n tháº­t:** `quang.tranminh` má»Ÿ SSM tunnel vÃ o bastion lÃºc 00:07â€“00:08 UTC ngÃ y 14/07.
ÄÃ£ cÃ³ evidence táº¡i `SSM-startsession-cloudtrail.md`.

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

**Tráº£ lá»i:** WHO=quang.tranminh (AuditReadOnlyAndAnalyze role),
WHAT=StartSession SSM vÃ o bastion `i-072084d1cf0b2f1c9`,
WHEN=00:07:14 UTC (07:07:14 +07), HOW=AWS SSM Console/CLI tá»« IP `118.68.56.162`.

---

## Pháº§n 4: Xá»­ lÃ½ khi gáº·p sá»± cá»‘ lÃºc drill

### KhÃ´ng tháº¥y event nÃ o trong time window

```
1. Má»Ÿ rá»™ng window: Â±30 phÃºt, Â±1 giá», Â±1 ngÃ y
2. Bá» filter phá»¥, chá»‰ giá»¯ filter chÃ­nh
3. Check láº¡i epoch: Ä‘Ã£ nhÃ¢n 1000 Ä‘á»ƒ ra milliseconds chÆ°a?
4. Kiá»ƒm tra log stream cÃ³ active khÃ´ng:
   aws logs describe-log-streams \
     --log-group-name /aws/eks/techx-tf4-cluster/cluster \
     --order-by LastEventTime --descending --max-items 3 \
     --profile TF4-AuditReadOnlyAndAnalyze-511825856493
```

### jq parse lá»—i

```bash
# Bá» jq, xem raw text trÆ°á»›c
aws logs filter-log-events \
  --log-group-name /aws/eks/techx-tf4-cluster/cluster \
  --start-time START_MS \
  --filter-pattern '"ConfigMap"' \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | grep -o '"username":"[^"]*"' | sort | uniq
```

### CloudTrail lookup-events cháº­m

```bash
# DÃ¹ng CloudWatch Logs Insights thay tháº¿ (nhanh hÆ¡n vá»›i large dataset)
# Log group: /aws/cloudtrail/tf4-general-cloudtrail (náº¿u Ä‘Ã£ setup CWL integration)
# Hoáº·c dÃ¹ng CloudTrail console filter trá»±c tiáº¿p
```

### Credentials háº¿t háº¡n giá»¯a chá»«ng

```bash
aws sso login --profile TF4-AuditReadOnlyAndAnalyze-511825856493
# Sau Ä‘Ã³ cháº¡y láº¡i query
```

---

## Pháº§n 5: Chá»©ng minh log khÃ´ng sá»­a Ä‘Æ°á»£c (Tamper-Evident)

Khi mentor há»i "lÃ m sao tÃ´i tin log nÃ y khÃ´ng bá»‹ sá»­a?":

**Láº­p luáº­n 1 â€” Separation of Duties (ADR-001):**
> "CDO07 chá»‰ cÃ³ Read-only profile. KhÃ´ng cÃ³ quyá»n write vÃ o CloudWatch Logs, S3 CloudTrail bucket,
> hoáº·c báº¥t ká»³ resource nÃ o. Operator (CDO04/CDO08) thá»±c thi infrastructure,
> CDO07 verify Ä‘á»™c láº­p â€” khÃ´ng cÃ³ conflict of interest."

**Láº­p luáº­n 2 â€” S3 Versioning:**
> "S3 bucket `tf4-cloudtrail-logs-bucket-511825856493` cÃ³ versioning Enabled.
> Ngay cáº£ náº¿u file bá»‹ overwrite, version cÅ© váº«n cÃ²n. CÃ³ thá»ƒ verify báº±ng:"

```bash
aws s3api list-object-versions \
  --bucket tf4-cloudtrail-logs-bucket-511825856493 \
  --prefix AWSLogs/511825856493/CloudTrail/ \
  --profile TF4-AuditReadOnlyAndAnalyze-511825856493 \
  | jq '.Versions | length'
```

**Láº­p luáº­n 3 â€” IAM khÃ´ng cÃ³ DeleteObject:**
> "Operator roles khÃ´ng cÃ³ `s3:DeleteObject`, `cloudtrail:StopLogging`,
> hay `logs:DeleteLogStream` trong policy. NgÆ°á»i váº­n hÃ nh khÃ´ng tá»± xÃ³a váº¿t cá»§a mÃ¬nh."

**Äiá»ƒm yáº¿u cáº§n thÃ nh tháº­t nÃªu:**
> "CloudTrail `LogFileValidationEnabled` hiá»‡n lÃ  `false` â€” chÃºng tÃ´i Ä‘Ã£ táº¡o
> ticket AUDIT-011 yÃªu cáº§u CDO04 fix Terraform. ÄÃ¢y lÃ  gap Ä‘ang trong quÃ¡ trÃ¬nh fix.
> Trong thá»i gian chá», S3 versioning + Separation of Duties lÃ  compensating control."

---

## Pháº§n 6: Checklist trÆ°á»›c khi vÃ o phÃ²ng vá»›i mentor

- [ ] AWS SSO login cÃ²n háº¡n (test `aws sts get-caller-identity`)
- [ ] kubeconfig updated
- [ ] Terminal má»Ÿ sáºµn, profile Ä‘Ã£ set
- [ ] File nÃ y in ra hoáº·c má»Ÿ sáºµn trÃªn mÃ n hÃ¬nh thá»© 2
- [ ] Biáº¿t epoch cá»§a 2026-07-14 07:15Z = `1752383700000`
- [ ] Biáº¿t epoch cá»§a 2026-07-14 07:30Z = `1752384600000`
- [ ] Incident report `incident-20260714-checkout-payment.md` má»Ÿ sáºµn (Scenario A data)

---

**Playbook version:** 1.0
**TÃ¡c giáº£:** CDO07 â€” HoÃ ng Kim HÃ¹ng
**NgÃ y:** 2026-07-15
**Káº¿ tiáº¿p:** Xem drill log táº¡i `aud-17.2-drill-log.md`
