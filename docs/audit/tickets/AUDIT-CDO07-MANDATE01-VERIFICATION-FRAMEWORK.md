# [CDO07] Audit Verification Framework — MANDATE-01 Network Exposure

> **Mục đích:** Khung chuẩn cho Task 21 và Task 22 (Trực + Hùng) thực hiện, Nghĩa sẽ là người review lại và chỉnh sửa  
> sau khi CDO08 hoàn tất deploy SEC-05 (Envoy block + SSM Bastion).  
> **Không được điền evidence vào đây trước khi CDO08 deploy xong.**

| Thông tin | Giá trị |
|---|---|
| Mandate | DIRECTIVE #1 — Network Exposure |
| Deadline | Thứ Ba 14/07/2026 |
| Owner CDO07 | Trực (Task 21), Hùng (Task 22) |
| Prerequisite | CDO08-SEC-05 deploy xong + Bastion instance-id được cung cấp |
| Pass tối thiểu | Evidence có thể tái kiểm chứng; Xác minh chi phí và log truy cập thành công; Kết quả CDO08/CDO04 được ký duyệt rõ ràng |

---

## 1. Evidence Index

Nơi lưu trữ tập trung raw evidence — chốt metadata trước khi thu thập.

```json
{
  "mandate": "DIRECTIVE-01-NETWORK-EXPOSURE",
  "utc_window": "YYYY-MM-DDTHH:MM:SSZ — YYYY-MM-DDTHH:MM:SSZ",
  "alb_dns": "k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com",
  "bastion_instance_id": "<ĐIỀN SAU KHI CDO08 DEPLOY>",
  "git_sha": "<git rev-parse HEAD>",
  "helm_release_revision": "<helm -n techx-tf4 history techx-corp | tail -1>",
  "verifier": "CDO07 — Trực + Hùng + Nghĩa",
  "note": "Evidence thu thập SAU khi CDO08-SEC-05 deploy xong"
}
```

**File evidence cần tạo:**

| File | Nội dung | Người làm |
|---|---|---|
| `aud-14-storefront-curl.md` | curl -I ALB/  → phải ra HTTP 200 | Nghĩa |
| `aud-15-grafana-curl.md` | curl -I ALB/grafana/ → phải ra HTTP 404 | Nghĩa |
| `aud-15-jaeger-curl.md` | curl -I ALB/jaeger/ui/ → phải ra HTTP 404 | Nghĩa |
| `aud-15-loadgen-curl.txt` | curl -I ALB/loadgen/ → phải ra HTTP 404 | Nghĩa |
| `aud-15-feature-curl.txt` | curl -I ALB/feature → phải ra HTTP 404 | Nghĩa |
| `aud-15-flagservice-curl.txt` | curl -I ALB/flagservice/ → phải ra HTTP 404 | Nghĩa |
| `aud-15-otlp-curl.txt` | curl -I ALB/otlp-http/ → phải ra HTTP 404 | Nghĩa |
| `aud-16-argocd-curl.md` | curl ArgoCD nếu tồn tại → phải ra HTTP 404 | Nghĩa |
| `aud-17-cloudtrail-startsession.txt` | CloudTrail query StartSession event | Hùng |
| `aud-18-private-access-screenshot.png` | Screenshot SSM tunnel vào Grafana thành công | Hùng |
| `aud-19-cost-verification.md` | Xác minh chi phí Bastion vs budget | Hùng |

**Lệnh lấy evidence (chạy sau khi CDO08 deploy):**

```bash
export ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
TIMESTAMP=$(date -Iseconds)
echo "Timestamp: $TIMESTAMP"

# Test storefront (phải 200)
curl -sS -o /dev/null -w "/ -> %{http_code}\n" "$ALB/"

# Test 6 internal routes (phải 404)
for path in grafana/ jaeger/ui/ loadgen/ feature flagservice/ otlp-http/; do
  curl -sS -o /dev/null -w "$path -> %{http_code}\n" "$ALB/$path"
done
```

**Kết quả mong đợi:**
```
/ -> 200
grafana/ -> 404
jaeger/ui/ -> 404
loadgen/ -> 404
feature -> 404
flagservice/ -> 404
otlp-http/ -> 404
```

> ⚠️ Nếu bất kỳ internal route nào KHÔNG ra 404 → dừng lại, báo CDO08 fix, không điền PASS.

---

## 2. Xác minh Giả định Chi phí (Verify Cost Assumptions)

Task này phụ thuộc CDO04 và CDO08 gửi số liệu lên GitHub trước.

### 2.1. Chi phí Bastion EC2 t3.nano

CDO08 ước tính ~$3.5/tuần. CDO07 cần đối chiếu với:

- [ ] **Giá EC2 t3.nano On-Demand us-east-1**: $0.0052/giờ × 168h/tuần = **$0.874/tuần** (chỉ EC2)
- [ ] **EBS gp3 8GiB** (root volume): $0.08 × 8 / 4.345 ≈ **$0.15/tuần**
- [ ] **SSM Session Manager**: $0 (built-in AWS, không tính phí)
- [ ] **Tổng ước tính thực tế**: ~**$1.02/tuần** (thấp hơn ước tính CDO08 $3.5/tuần)

> Note: CDO08 dùng t3.nano không phải t3.micro, cần confirm instance type thật sau deploy.

**Đối chiếu với budget:**

| Hạng mục | Baseline/tuần | Bastion thêm | Tổng | Trần |
|---|---|---|---|---|
| Fixed infra (EC2+EKS+NAT+ALB) | ~$56.83 | ~$1.02 | ~$57.85 | $300 |
| Kết luận | — | — | ✅ Nằm trong ngân sách | — |

- [ ] **Bước 1:** Đợi CDO04 push actual Cost Explorer data lên GitHub
- [ ] **Bước 2:** Đối chiếu estimated vs actual để xác nhận chi phí thực
- [ ] **Bước 3:** Ghi kết quả vào bảng trên (điền số actual thay số estimate)
- [ ] **Bước 4:** Xác nhận cost/request không phình so với baseline (liên quan Mandate-02)

**Evidence cần có:** Screenshot Cost Explorer hoặc AWS CLI cost output trong window sau khi Bastion được bật.

```bash
# Lấy cost Bastion instance trong 24h gần nhất (chạy sau khi có billing data)
aws ce get-cost-and-usage \
  --time-period Start=2026-07-13,End=2026-07-14 \
  --granularity DAILY \
  --filter '{"Dimensions":{"Key":"INSTANCE_TYPE","Values":["t3.nano"]}}' \
  --metrics BlendedCost
```

### 2.2. Chi phí Node Group scale-out (liên quan Mandate-02)

Khi chạy load test 200 users, node group có thể scale từ 2 → 3/4 nodes:

- [ ] Xác nhận CDO04 có report node count trước/sau load test
- [ ] Nếu scale lên 3 nodes: thêm ~$14.40/tuần (1 t3.large)
- [ ] Nếu scale lên 4 nodes: thêm ~$28.80/tuần (2 t3.large)
- [ ] Tổng phải vẫn ≤ $300/tuần

**Evidence cần có:** Node count screenshot từ `aws eks describe-nodegroup` hoặc Prometheus trước/sau test.

---

## 3. Independent Verification

CDO07 tự kiểm tra độc lập — không dựa vào evidence của CDO08.

### 3.1. Verify routes bị chặn từ internet

```bash
export ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"

# Chạy từ máy local (không dùng kubectl/port-forward)
# Storefront phải 200
curl -v "$ALB/" 2>&1 | grep "< HTTP"

# 6 internal routes phải 404 (không phải 200, không phải redirect về storefront)
curl -v "$ALB/grafana/" 2>&1 | grep "< HTTP"
curl -v "$ALB/jaeger/ui/" 2>&1 | grep "< HTTP"
curl -v "$ALB/loadgen/" 2>&1 | grep "< HTTP"
curl -v "$ALB/feature" 2>&1 | grep "< HTTP"
curl -v "$ALB/flagservice/" 2>&1 | grep "< HTTP"
curl -v "$ALB/otlp-http/" 2>&1 | grep "< HTTP"
```

**Điều kiện PASS:**
- [ ] Storefront `/` = HTTP 200, có HTML content
- [ ] `/grafana/` = HTTP 404, không có Grafana UI
- [ ] `/jaeger/ui/` = HTTP 404, không có Jaeger UI
- [ ] `/loadgen/` = HTTP 404, không có Locust UI
- [ ] `/feature` = HTTP 404
- [ ] `/flagservice/` = HTTP 404
- [ ] `/otlp-http/` = HTTP 404

> Lưu ý: 404 là acceptable (Envoy direct_response). Nếu thấy 302/301 redirect về `/` là chưa đúng — có thể là SPA catch-all vẫn đang active.

### 3.2. Verify timeline thật (loại trừ trace/metric cũ)

Đối chiếu timestamp trong evidence với Prometheus/Grafana/Jaeger để loại trừ cache hoặc dữ liệu cũ:

```bash
# Lấy timestamp hiện tại trước khi chạy curl tests
date -u +"%Y-%m-%dT%H:%M:%SZ"

# Sau khi chạy curl, check Prometheus có spike request nào không
# PromQL: rate(traces_span_metrics_calls_total{span_name=~".*grafana.*"}[5m])
```

- [ ] Timestamp evidence phải trong vòng 30 phút trước deadline
- [ ] Không copy-paste evidence từ lần test trước

### 3.3. Verify private access hoạt động

Dùng SSM tunnel command CDO08 cung cấp, tự test:

```bash
# Tunnel vào Grafana qua Bastion
aws ssm start-session \
  --target <BASTION_INSTANCE_ID> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters '{"host":["<GRAFANA_CLUSTERIP>"],"portNumber":["80"],"localPortNumber":["3000"]}'

# Mở browser tới http://localhost:3000 → phải thấy Grafana UI
```

- [ ] SSM tunnel mở được (không lỗi)
- [ ] Grafana UI accessible qua localhost:3000
- [ ] Jaeger UI accessible qua localhost:16686
- [ ] Chụp screenshot với URL bar hiện "localhost:3000" làm evidence

**Yêu cầu raw output, không chỉ ảnh chụp:**
CDO07 cần output text từ lệnh, không phải chỉ screenshot. Screenshot dễ giả mạo, output text có timestamp và headers thật.

---

## 4. Auditability Checks

### 4.1. Audit Trail — SSM Session Manager + Port Mapping

**Hạn chế đã biết:** CloudTrail log `StartSession` chỉ ghi được **port number**, không ghi tên service (Grafana/Jaeger). Để audit trail có ý nghĩa, cần kết hợp với **Port Mapping Document** do CDO08 cung cấp.

**Port Mapping (CDO08 phải bổ sung vào runbook):**

| SSM localPortNumber | Target Host | Service | Namespace |
|---|---|---|---|
| 3000 | grafana.techx-observability.svc.cluster.local | Grafana Dashboard | techx-observability |
| 16686 | jaeger.techx-observability.svc.cluster.local | Jaeger Tracing UI | techx-observability |
| 8089 | load-generator.techx-tf4.svc.cluster.local | Locust Load Gen UI | techx-tf4 |

> **Khi CDO08 implement xong**, CDO07 verify: `portNumber` trong CloudTrail + bảng mapping trên → biết ai vào service nào, khi nào.

**Query CloudTrail để verify:**

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --start-time 2026-07-13T00:00:00Z \
  --end-time 2026-07-14T23:59:59Z \
  --profile TF4-AuditReadOnlyAndAnalyze \
  --output json | jq '.Events[] | {
    time: .EventTime,
    user: .Username,
    source_ip: (.CloudTrailEvent | fromjson | .sourceIPAddress),
    target: (.CloudTrailEvent | fromjson | .requestParameters.target),
    port: (.CloudTrailEvent | fromjson | .requestParameters.portNumber)
  }'
```

**Điều kiện PASS:**

- [ ] Có ít nhất 1 event `StartSession` được ghi trong window test
- [ ] Event có đủ: user ARN, timestamp, source IP, target instance-id, port number
- [ ] Port number khớp với Port Mapping → xác định được người truy cập service nào

### 4.2. Kiểm tra PII/payment/prompt không lộ trong logs/traces

Sau khi Mandate-01 deploy, test nhanh:

```bash
# Check OpenSearch không có payment info (dùng Kibana DevTools hoặc API)
curl -X GET "http://localhost:9200/otel-*/_search" -H 'Content-Type: application/json' -d'
{
  "query": {
    "multi_match": {
      "query": "4111111111111111",
      "fields": ["*"]
    }
  }
}'
# Kết quả phải là 0 hits
```

- [ ] Credit card numbers không xuất hiện trong OpenSearch
- [ ] Email addresses không xuất hiện trong trace attributes
- [ ] AI prompt content không xuất hiện trong logs (nếu AI-01 đã fix)
- [ ] Correlation IDs (order_id, trace_id) vẫn còn trong logs (không bị over-redact)

### 4.3. Kết luận tổng nghiệm thu

| Hạng mục | Pass / Fail / Blocked | Ghi chú |
|---|---|---|
| Storefront public (HTTP 200) | ☐ | |
| 6 internal routes blocked (HTTP 404) | ☐ | |
| Private access qua SSM hoạt động | ☐ | |
| CloudTrail ghi StartSession event | ☐ | |
| Port mapping document tồn tại | ☐ | CDO08 phải bổ sung |
| Chi phí Bastion trong ngân sách | ☐ | Đợi CDO04 actual cost |
| PII không lộ trong logs/traces | ☐ | |
| flagd/OpenFeature không bị ảnh hưởng | ☐ | Test checkout sau deploy |
| Checkout SLO không tụt | ☐ | Check Grafana SLO dashboard |

**Kết luận cuối:** ☐ PASS / ☐ FAIL / ☐ BLOCKED (lý do: ___)

**Người duyệt CDO07:** ___ | **Ngày:** ___

---

## 5. Checklist trước khi submit PR

- [ ] Tất cả file evidence có timestamp thật (không placeholder)
- [ ] ALB DNS trong evidence là `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com` (không phải fake domain)
- [ ] metadata.json đã cập nhật `bastion_instance_id` thật
- [ ] CDO08 đã sign-off (ký tên vào Approval gate)
- [ ] CDO04 đã confirm cost
- [ ] Không có credential, token, cookie trong evidence files

---

## 6. Ghi chú về blocker hiện tại

> **Trạng thái:** CDO08-SEC-05 đang ở `RESEARCH COMPLETE — WAITING FOR APPROVAL`  
> CDO07 chưa thể điền evidence thật vào đây cho đến khi CDO08 deploy xong.  
> 
> **Action items CDO08 còn nợ:**  
> - [ ] Nhân approve 6 routes  
> - [ ] Quyết confirm /otlp-http xử lý thế nào  
> - [ ] CDO04 approve cost EC2 t3.nano  
> - [ ] Đinh Văn Ty duyệt PR  
> - [ ] **Bổ sung Port Mapping Document** (xem mục 4.1) — CDO07 yêu cầu bổ sung
