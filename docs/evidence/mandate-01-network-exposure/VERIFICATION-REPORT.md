# VERIFICATION REPORT — Mandate-01: Network Exposure
## Task 23 — CDO07 Independent Verification

| Field | Value |
|---|---|
| Task | Task 23 — Independent Verification — Mandate-01 for CDO04 |
| Verifier | CDO07 — Kim Hùng |
| ALB | `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com` |
| Cluster | `techx-tf4-cluster` — `us-east-1` |
| Source path | `docs/evidence/mandate-01-network-exposure/` |

---

## Kết quả tổng hợp

| ST | Mô tả | Trạng thái | File |
|---|---|---|---|
| ST-3.1 | Môi trường external | ✅ DONE | `st31-env-setup.txt` |
| ST-3.2 before | Baseline — routes đang lộ | ✅ DONE | `st32-curl-before.txt` |
| ST-3.2 after | Verify routes đã blocked | ⏳ BLOCKED — chờ CDO08 | `st32-curl-after.txt` |
| ST-3.3 | SSM tunnel private access | ⏳ BLOCKED — chờ CDO08 | `st33-vpn-tunnel.txt` |
| ST-3.4 | Load test Locust+Prometheus+Jaeger | ⏳ BLOCKED — chờ CDO04 | `st34-loadtest-stats.txt` |

---

## ST-3.1 — Môi trường test

**Raw output** (từ `st31-env-setup.txt`):
```
Timestamp : 2026-07-13T15:56:38Z
Public IP : 42.118.54.254
Tool      : PowerShell Invoke-WebRequest (Windows)
Shell     : PowerShell 5.1 on Windows
Network   : External - not VPN, not kubectl port-forward
```

**Kết quả:** ✅ PASS — External network confirmed, IP: 42.118.54.254

---

## ST-3.2 — External curl test

### BEFORE (baseline — routes đang lộ)
**Raw output** (từ `st32-curl-before.txt`):
```
Timestamp : 2026-07-13T15:58:17Z
From IP   : 42.118.54.254

GET /             -> HTTP 200   OK - storefront public
GET /grafana/     -> HTTP 200   EXPOSED - needs CDO08 block
GET /grafana      -> HTTP 301   EXPOSED (redirect to /grafana/)
GET /jaeger/ui/   -> HTTP 200   EXPOSED - needs CDO08 block
GET /jaeger/      -> HTTP 404   Already 404
GET /loadgen/     -> HTTP 200   EXPOSED - needs CDO08 block
GET /feature      -> HTTP 503   Route exists, backend down
GET /flagservice/ -> HTTP 404   Already 404
GET /otlp-http/   -> HTTP 404   Already 404
```

**Nhận xét:** 3 routes đang bị lộ HTTP 200 từ internet (/grafana/, /jaeger/ui/, /loadgen/).
CDO08 cần deploy SEC-05 để block tất cả internal routes bằng Envoy direct_response 404.

### AFTER (verification — routes phải 404)
**Raw output** (từ `st32-curl-after.txt`):
```
[ĐIỀN SAU KHI CDO08 DEPLOY]

Timestamp : _______________
From IP   : _______________

GET /             -> HTTP ___   # Phải 200
GET /grafana/     -> HTTP ___   # Phải 404
GET /jaeger/ui/   -> HTTP ___   # Phải 404
GET /loadgen/     -> HTTP ___   # Phải 404
GET /feature      -> HTTP ___   # Phải 404
GET /flagservice/ -> HTTP ___   # Phải 404
GET /otlp-http/   -> HTTP ___   # Phải 404
```

**Kết quả:** ☐ PASS / ☐ BLOCKED (chờ CDO08 deploy)

---

## ST-3.3 — VPN/SSM Private Access

**Raw output** (từ `st33-vpn-tunnel.txt`):
```
[ĐIỀN SAU KHI CDO08 CUNG CẤP BASTION]

Timestamp  : _______________
Bastion ID : i-0_______________
SessionId  : _______________

localhost:3000 (Grafana/SSM)  -> HTTP ___   # Phải 200
ALB /grafana/ (public)        -> HTTP ___   # Phải 404
```

**Kết quả:** ☐ PASS / ☐ BLOCKED (chờ CDO08 — cần bastion-id + ClusterIP)

---

## ST-3.4 — Load Test Timeline Correlation

**Locust raw stats** (từ `st34-loadtest-stats.txt`):
```
[ĐIỀN SAU KHI CÓ ACCESS PROMETHEUS/LOCUST]

user_count         : ___
checkout fail_ratio: ___
```

**Prometheus SLO** (từ `st34-loadtest-stats.txt`):
```
Checkout success   : ___   # target >= 0.99
Storefront p95 ms  : ___   # target < 1000
```

**Jaeger trace correlation** (từ `st34-loadtest-stats.txt`):
```
Traces in window   : ___
Delta Locust↔Jaeger: ___   # Confirm traces là mới
```

**Kết quả:** ☐ PASS / ☐ BLOCKED (chờ CDO04 — cần port-forward access)

---

## Blocker log

| # | Blocker | Cần từ | Unblocks |
|---|---|---|---|
| B1 | Envoy chưa block routes (SEC-05 chưa deploy) | CDO08 — Nhân | ST-3.2 after |
| B2 | Bastion instance-id + ClusterIP chưa có | CDO08 — Nhân | ST-3.3 |
| B3 | Port-forward Prometheus/Locust chưa có | CDO04 — Huy | ST-3.4 |

---

## Kết luận

```
Mandate-01 Independent Verification — Task 23:

Completed:
  ST-3.1  PASS  — External network confirmed, IP 42.118.54.254
  ST-3.2  DONE  — Baseline captured: 3 routes exposed (/grafana/ /jaeger/ui/ /loadgen/)

Blocked:
  ST-3.2 after  BLOCKED B1 — chờ CDO08 deploy SEC-05
  ST-3.3        BLOCKED B2 — chờ CDO08 cung cấp bastion-id + ClusterIP
  ST-3.4        BLOCKED B3 — chờ CDO04 cung cấp Prometheus/Locust access

Overall: IN PROGRESS

Verifier: CDO07 — Kim Hùng
Ngày:     2026-07-13
Git SHA:  2ced9bbef1d6d7d356bb1253477c566a61364562
```

---

## Hướng dẫn mentor tái kiểm chứng

```bash
export ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"

# 1. Storefront phải 200
curl -sS -o /dev/null -w "/ -> %{http_code}\n" "$ALB/"

# 2. Internal routes phải 404
for p in grafana/ jaeger/ui/ loadgen/ feature flagservice/ otlp-http/; do
  curl -sS -o /dev/null -w "$p -> %{http_code}\n" "$ALB/$p"
done

# 3. Private access qua SSM (CDO08 cung cấp instance-id)
# aws ssm start-session --target <instance-id> \
#   --document-name AWS-StartPortForwardingSessionToRemoteHost \
#   --parameters '{"host":["<grafana-clusterip>"],"portNumber":["80"],"localPortNumber":["3000"]}'
# → curl http://localhost:3000 phải ra 200
```
