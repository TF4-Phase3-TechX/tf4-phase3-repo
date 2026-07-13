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
| ST-3.1 | Môi trường external | ✅ PASS | `st31-env-setup.txt` |
| ST-3.2 before | Baseline — routes đang lộ | ✅ DONE | `st32-curl-before.txt` |
| ST-3.2 after | Verify routes đã blocked | ✅ PASS | `st32-curl-after.txt` |
| ST-3.3 | SSM tunnel private access | ✅ PASS (CDO08 verified) / ⏳ CDO07 tự verify | `st33-vpn-tunnel.txt` |
| ST-3.4 | Hệ thống đang chạy + trace data | ✅ Một phần (CDO08 evidence) / ⏳ CDO07 tự verify | `st34-loadtest-stats.txt` |
| ST-3.3 | SSM tunnel private access | ⏳ BLOCKED — chờ CDO08 | `st33-vpn-tunnel.txt` |
| ST-3.4 | Load test Locust+Prometheus+Jaeger | ⏳ Đang xử lý | `st34-loadtest-stats.txt` |

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

### AFTER (verification — routes đã blocked)
**Raw output** (từ `st32-curl-after.txt`):
```
Thời điểm : 2026-07-13T16:55:09Z
IP nguồn   : 42.118.54.254

GET /             -> HTTP 200   OK - storefront vẫn công khai
GET /grafana/     -> HTTP 404   DA BLOCK
GET /grafana      -> HTTP 404   DA BLOCK
GET /jaeger/ui/   -> HTTP 404   DA BLOCK
GET /jaeger/      -> HTTP 404   DA BLOCK
GET /loadgen/     -> HTTP 404   DA BLOCK
GET /feature      -> HTTP 404   DA BLOCK
GET /flagservice/ -> HTTP 404   DA BLOCK
GET /otlp-http/   -> HTTP 404   DA BLOCK
```

**Kết quả:** ✅ PASS — Tất cả 6 internal routes đã blocked. Storefront vẫn 200.

---

## ST-3.3 — VPN/SSM Private Access

**Bằng chứng CDO08** (từ `st33-vpn-tunnel.txt`):
```
Bastion ID  : i-072084d1cf0b2f1c9
SSM Session : nguyen-cqzlbzsh4onaob6vh2536k3vj4
Owner       : arn:aws:sts::511825856493:assumed-role/.../nguyen
StartDate   : 2026-07-13T23:28:39+07:00
Status      : Terminated (completed successfully)

Grafana qua SSM tunnel  -> HTTP 301 (redirect /grafana/ = PASS)
ClusterIP Grafana       : 172.20.108.200
ClusterIP Jaeger        : 172.20.88.27
ClusterIP Locust        : 172.20.219.77
```

**CDO07 tự verify** (cần chạy với profile `iam-tf4`):
```
[Điền sau khi CDO07 tự chạy SSM tunnel]
Thời điểm CDO07 test : _______________
localhost:3000 (Grafana) -> HTTP ___
localhost:16686 (Jaeger) -> HTTP ___
CloudTrail StartSession  : ___
```

**Kết quả:** ✅ PASS (CDO08) / ⏳ CDO07 đang verify độc lập

---

## ST-3.4 — Load Test Timeline Correlation

**Bằng chứng CDO08** (từ `st34-loadtest-stats.txt`):
```
Thời điểm : 2026-07-13T23:18:47+07:00

Runtime health:
  frontend, checkout, cart, payment, shipping: 2/2 available
  flagd, grafana, jaeger: 1/1 available

OpenSearch trace data:
  jaeger-span-2026-07-13    -> 43,516 spans (4.7MB)
  jaeger-service-2026-07-13 -> 76 services
  Ngày: 13/07/2026 (hôm nay) -> dữ liệu THẬT, không phải cũ
```

**CDO07 tự verify** (cần profile `iam-tf4`):
```
[Điền sau khi CDO07 chạy SSM tunnel vào Locust + Jaeger]
Thời điểm CDO07    : _______________
Locust user_count  : ___
Jaeger span count  : ___  (phải >= 43,516)
Timeline delta     : ___  (phải < 5 phút)
```

**Kết quả:** ✅ Một phần PASS (CDO08 evidence) / ⏳ CDO07 đang verify độc lập

---

## Blocker log

| # | Blocker | Cần từ | Unblocks | Trạng thái |
|---|---|---|---|---|
| B1 | CDO07 cần profile `iam-tf4` để tự chạy SSM tunnel | CDO08 | ST-3.3, ST-3.4 CDO07 verify | ⏳ Đang xin |
| B2 | CloudTrail LookupEvents cần role có quyền | CDO07 dùng TF4-AuditReadOnlyAndAnalyze | ST-3.3 audit trail | ⏳ Tự thực hiện |

---

## Kết luận

```
Mandate-01 Independent Verification — Task 23:

ST-3.1  PASS  — External network confirmed, IP: 42.118.54.254
ST-3.2  DONE  — Baseline: 3 routes exposed (before), tất cả 404 (after)
ST-3.3  PASS  — CDO08 verified SSM tunnel, Grafana accessible via bastion
               Bastion: i-072084d1cf0b2f1c9 | Session: nguyen-cqzlbzsh4onaob6vh2536k3vj4
               CDO07 độc lập verify: ⏳ cần profile iam-tf4
ST-3.4  PASS* — CDO08 evidence: 43,516 spans từ 76 services ngày 13/07/2026
               Runtime: tất cả services 2/2 healthy
               CDO07 độc lập verify: ⏳ cần chạy SSM tunnel vào Locust/Jaeger

Overall: IN PROGRESS — Core requirements MET, CDO07 independent verify đang hoàn tất

Verifier: CDO07 — Kim Hùng
Ngày:     2026-07-13
Git SHA:  2ced9bbef1d6d7d356bb1253477c566a61364562

CDO08 CloudTrail audit còn thiếu:
  -> CDO07 chạy: aws cloudtrail lookup-events --region us-east-1
     --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession
     --profile TF4-AuditReadOnlyAndAnalyze
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
