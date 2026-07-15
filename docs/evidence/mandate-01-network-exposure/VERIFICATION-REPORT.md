# VERIFICATION REPORT — Mandate-01: Network Exposure
## Task 23 — CDO07 Independent Verification

| Field | Value |
|---|---|
| Task | Task 23 — Independent Verification — Mandate-01 |
| Verifier | CDO07 — hung.hoangkim |
| Role | AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze |
| ALB | `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com` |
| Cluster | `techx-tf4-cluster` — `us-east-1` — account `511825856493` |
| Bastion | `i-072084d1cf0b2f1c9` (tf4-portal-bastion) |
| Verified | 2026-07-14T01:42:33+07:00 |
| Verdict | **PASS ✅** |

---

## Kết quả tổng hợp

| ST | Mô tả | Trạng thái | File evidence |
|---|---|---|---|
| ST-3.1 | Môi trường external xác nhận | ✅ PASS | `st31-env-setup.txt` |
| ST-3.2 before | Baseline — routes đang lộ trước deploy | ✅ DONE | `st32-curl-before.txt` |
| ST-3.2 after | Verify routes đã blocked sau SEC-05 | ✅ PASS | `st32-curl-after.txt` |
| ST-3.3 | SSM tunnel — private access verified | ✅ PASS | `st33-vpn-tunnel.txt` |
| ST-3.4 | Runtime health + trace data verified | ✅ PASS | `st34-loadtest-stats.txt` |

**Overall: PASS ✅ — CDO07 đã xác minh độc lập toàn bộ Mandate-01**

---

## ST-3.1 — Môi trường test

```
Timestamp : 2026-07-13T15:56:38Z
Public IP : 42.118.54.254
Tool      : PowerShell Invoke-WebRequest (Windows)
Network   : External — không VPN, không kubectl port-forward
```

**Kết quả:** ✅ PASS — External network confirmed, IP `42.118.54.254`

---

## ST-3.2 — External curl test

### BEFORE — Baseline trước khi CDO08 deploy SEC-05

```
Timestamp : 2026-07-13T15:58:17Z
From IP   : 42.118.54.254

GET /             -> HTTP 200   OK  — storefront public
GET /grafana/     -> HTTP 200   ❌ EXPOSED
GET /grafana      -> HTTP 301   ❌ EXPOSED (redirect)
GET /jaeger/ui/   -> HTTP 200   ❌ EXPOSED
GET /loadgen/     -> HTTP 200   ❌ EXPOSED
GET /feature      -> HTTP 503   Route tồn tại, backend down
GET /flagservice/ -> HTTP 404   Already blocked
GET /otlp-http/   -> HTTP 404   Already blocked
```

**Nhận xét:** 3 routes lộ HTTP 200 từ internet — Grafana, Jaeger, Locust.
CDO07 đã ghi lại baseline này TRƯỚC khi CDO08 deploy để làm evidence đối chiếu.

### AFTER — Sau khi CDO08 deploy SEC-05

```
Timestamp : 2026-07-13T16:55:09Z
From IP   : 42.118.54.254

GET /             -> HTTP 200   ✅ Storefront vẫn công khai
GET /grafana/     -> HTTP 404   ✅ BLOCKED
GET /grafana      -> HTTP 404   ✅ BLOCKED
GET /jaeger/ui/   -> HTTP 404   ✅ BLOCKED
GET /jaeger/      -> HTTP 404   ✅ BLOCKED
GET /loadgen/     -> HTTP 404   ✅ BLOCKED
GET /feature      -> HTTP 404   ✅ BLOCKED
GET /flagservice/ -> HTTP 404   ✅ BLOCKED
GET /otlp-http/   -> HTTP 404   ✅ BLOCKED
```

**Kết quả:** ✅ PASS — Tất cả 6 internal routes blocked. Storefront 200 không đổi.

| Route | Before | After | Result |
|---|---|---|---|
| `/` | HTTP 200 | HTTP 200 | ✅ Unchanged |
| `/grafana/` | HTTP 200 ❌ | HTTP 404 | ✅ BLOCKED |
| `/jaeger/ui/` | HTTP 200 ❌ | HTTP 404 | ✅ BLOCKED |
| `/loadgen/` | HTTP 200 ❌ | HTTP 404 | ✅ BLOCKED |
| `/feature` | HTTP 503 | HTTP 404 | ✅ BLOCKED |
| `/flagservice/` | HTTP 404 | HTTP 404 | ✅ Maintained |
| `/otlp-http/` | HTTP 404 | HTTP 404 | ✅ Maintained |

---

## ST-3.3 — SSM Tunnel Private Access

### CDO08 Evidence (reference)

```
CDO08 Session ID : nguyen-cqzlbzsh4onaob6vh2536k3vj4
Owner            : AWSReservedSSO_TF4-SecurityIAMSSOManager/.../nguyen
StartDate        : 2026-07-13T23:28:39+07:00
Status           : Terminated
Grafana via tunnel -> HTTP 301 PASS
```

### CDO07 Independent Verify

```
Timestamp        : 2026-07-14T01:17:33+07:00
Caller           : hung.hoangkim / TF4-AuditReadOnlyAndAnalyze
SSM Plugin       : v1.2.835.0

Bastion          : i-072084d1cf0b2f1c9 — PingStatus: Online
CDO07 Session ID : hung.hoangkim-7jyzlso8gnvkyl7t4vgr28nu3a
StartDate        : 2026-07-14T01:15:20+07:00

[PRIVATE] localhost:3000 (Grafana via tunnel)  -> HTTP 301 → 200  ✅
          Content-Type: text/html; charset=UTF-8
          Body: <!DOCTYPE html><html lang="en-US">...  (Grafana UI thật)

[PUBLIC ] ALB /grafana/ (internet)             -> HTTP 404         ✅
[PUBLIC ] ALB / (storefront)                   -> HTTP 200         ✅
```

### CloudTrail Audit (CDO07 query độc lập)

CDO08 thiếu quyền `cloudtrail:LookupEvents` — CDO07 đã query thay:

```
+--------------+---------------------+-----------------------------+----------------+
|   EventName  |       Source        |            Time             |     User       |
+--------------+---------------------+-----------------------------+----------------+
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T01:15:20+07:00  |  hung.hoangkim | ← CDO07
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T01:13:16+07:00  |  hung.hoangkim |
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T00:16:40+07:00  |  huyhoang      |
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T00:16:21+07:00  |  anngo         |
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T00:13:46+07:00  |  cdo04-an      |
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T00:12:53+07:00  |  anngo         |
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T00:03:49+07:00  |  cdo04-an      |
|  StartSession|  ssm.amazonaws.com  |  2026-07-14T00:02:58+07:00  |  cdo04-an      |
|  StartSession|  ssm.amazonaws.com  |  2026-07-13T23:28:39+07:00  |  nguyen        | ← CDO08
|  StartSession|  ssm.amazonaws.com  |  2026-07-13T23:27:46+07:00  |  nguyen        |
+--------------+---------------------+-----------------------------+----------------+
```

Session CDO07 `01:15:20` và session CDO08 `23:28:39` đều có trong CloudTrail.
Audit trail đầy đủ: Who / When / Target đều được ghi.

**Kết quả ST-3.3:** ✅ PASS

---

## ST-3.4 — Runtime Health + Telemetry

### Deployment Health (CDO07 kubectl read-only)

```
Timestamp : 2026-07-14T01:31:04+07:00
Cluster   : techx-tf4-cluster

techx-tf4 — 22/22 deployments Ready:
  frontend 2/2 | frontend-proxy 2/2 | checkout 2/2 | cart 2/2
  payment 2/2  | shipping 2/2       | product-catalog 2/2
  load-generator 1/1 | flagd 1/1    | (+ 13 others all Ready)

techx-observability:
  grafana 1/1 (4d16h uptime)
  jaeger  1/1 (4d16h uptime)
  prometheus 1/1 (4d16h uptime)

Load generator pod:
  load-generator-6845cc7466-wjn78
  Status: Running | Age: 63min | Restarts: 0
  LOCUST_AUTOSTART=false → manual trigger mode (đúng thiết kế)
```

### Locust Stats (CDO07 via SSM tunnel hung.hoangkim-pgcpt9cdjazcjytesyavbhcttq)

```
Tunnel   : portNumber=18089 → localPortNumber=8089
Timestamp: 2026-07-14T01:42:33+07:00

GET /stats/requests:
  state       : ready
  user_count  : 0
  total_rps   : 0.0
  errors      : []
```

state=`ready` là ĐÚNG — `LOCUST_AUTOSTART=false`, load test chỉ trigger thủ công.
Pod running healthy, web UI accessible qua tunnel.

### Jaeger Traces (CDO07 via SSM tunnel hung.hoangkim-vqhplqcrezhltkkcatt6hfijjy)

```
Tunnel      : portNumber=16686 → localPortNumber=16686
Timestamp   : 2026-07-14T01:42:33+07:00
Jaeger ver  : jaegertracing/jaeger:2.17.0
Storage     : OpenSearch (http://opensearch:9200)
base_path   : /jaeger/ui (configmap user-config)

Jaeger UI   : GET /jaeger/ui/ -> HTTP 200 (4651 bytes, HTML)  ✅

GET /jaeger/ui/api/services -> HTTP 200
  Total services: 19
  frontend | checkout | cart | payment | shipping | product-catalog
  flagd | jaeger | ad | frontend-proxy | recommendation | accounting
  email | fraud-detection | quote | shipping | currency | image-provider
  load-generator

Recent traces (frontend, last 15min):
  TraceID: d51d0c5c65d5b3350f3746c1217f9813
  Latest : 2026-07-13T18:42:33+00:00 = 2026-07-14T01:42:33+07:00  ← FRESH ✅
```

**Đối chiếu:**

| Metric | CDO08 claim | CDO07 verify | Khớp? |
|---|---|---|---|
| Deployments healthy | 10 services | 22/22 services ✅ | ✅ YES |
| Jaeger running | 1/1 | 1/1 (4d16h) | ✅ YES |
| Jaeger UI accessible | PASS | HTTP 200 HTML | ✅ YES |
| Traces fresh | implied | Latest 01:42 07/14 | ✅ FRESH |
| Services reporting | 76 operations | 19 processes | ✅ Consistent |
| Locust accessible | PASS | HTTP 200 via tunnel | ✅ YES |

**NOTE:** CDO08 đếm 76 từ OpenSearch (operation names), CDO07 đếm 19 từ Jaeger API (service processes). Đây là 2 metric khác nhau — không mâu thuẫn.

**Kết quả ST-3.4:** ✅ PASS

---

## Kết luận Mandate-01

```
Mandate-01 yêu cầu:
  [1] Storefront / phải HTTP 200 từ internet
  [2] Cổng vận hành (Grafana, Jaeger, Locust...) phải 404 từ internet
  [3] Người có quyền vẫn vào được qua VPN/tunnel/bastion

CDO07 Independent Verification:

  [1] Storefront HTTP 200  → CONFIRMED ✅
      (ST-3.2 after: GET / -> 200, cả before lẫn after)

  [2] Routes blocked       → CONFIRMED ✅
      (ST-3.2 after: 8 routes -> 404, cross-checked with CDO08 curl output)

  [3] Private access OK    → CONFIRMED ✅
      (ST-3.3: CDO07 mở tunnel hung.hoangkim-7jyzlso8gnvkyl7t4vgr28nu3a
               Grafana HTTP 301->200, Jaeger 19 services, Locust UI accessible)

  [4] Runtime healthy      → CONFIRMED ✅
      (ST-3.4: 22/22 deploys Ready, traces FRESH tại 01:42:33 07/14)

  [5] Audit trail complete → CONFIRMED ✅
      (CloudTrail: CDO07 query độc lập, session CDO08 và CDO07 đều có trong log)

VERDICT: Mandate-01 — PASS ✅
Verifier: CDO07 — hung.hoangkim (TF4-AuditReadOnlyAndAnalyze)
Date    : 2026-07-14T01:42:33+07:00
```

---

## Hướng dẫn Mentor tái kiểm chứng

```powershell
# 1. External curl test (Windows PowerShell)
$ALB = "http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
foreach ($p in @("/", "/grafana/", "/jaeger/ui/", "/loadgen/", "/feature", "/flagservice/", "/otlp-http/")) {
    $code = try { (Invoke-WebRequest "$ALB$p" -UseBasicParsing -MaximumRedirection 0 -TimeoutSec 5 -EA SilentlyContinue).StatusCode }
            catch { [int]$_.Exception.Response.StatusCode }
    Write-Output "$p -> HTTP $code"
}

# 2. SSM tunnel Grafana (Windows PowerShell — cần Session Manager Plugin)
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
aws ssm start-session --target i-072084d1cf0b2f1c9 --document-name AWS-StartPortForwardingSession --parameters '{\"portNumber\":[\"13000\"],\"localPortNumber\":[\"3000\"]}' --region us-east-1
# → localhost:3000 phải HTTP 301 → 200 (Grafana UI)

# 3. Kiểm tra deployment health
aws eks update-kubeconfig --name techx-tf4-cluster --region us-east-1
kubectl -n techx-tf4 get deploy
kubectl -n techx-observability get deploy

# 4. CloudTrail audit trail
aws cloudtrail lookup-events --region us-east-1 --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession --max-results 10 --output table
```
