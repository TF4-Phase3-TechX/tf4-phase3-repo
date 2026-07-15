# Evidence Index — Mandate-01: Network Exposure
## Task 23 — CDO07 Independent Verification

| Field | Value |
|---|---|
| Mandate | DIRECTIVE #1 — Storefront public, cổng vận hành phải private |
| Task | Task 23 — Independent Verification |
| ALB | `k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com` |
| Region | `us-east-1` |
| Cluster | `techx-tf4-cluster` |
| Verifier | CDO07 — Task 23 |
| Metadata | [`metadata.json`](./metadata.json) |

---

## Trạng thái tổng thể

```
✅ Làm được ngay    ST-3.1, ST-3.2 before
⏳ Chờ CDO08        ST-3.2 after, ST-3.3
⏳ Chờ CDO04        ST-3.4
```

---

## File map

| File | Nội dung | Làm được ngay? | Trạng thái |
|---|---|---|---|
| `st31-env-setup.txt` | ST-3.1 — Public IP + tool version | ✅ | ✅ DONE — 2026-07-13T15:56:38Z |
| `st32-curl-before.txt` | ST-3.2 before — baseline routes đang lộ | ✅ | ✅ DONE — 3 routes exposed |
| `st32-curl-after.txt` | ST-3.2 after — verify routes blocked | ⏳ CDO08 | ⏳ Chờ SEC-05 deploy |
| `st33-vpn-tunnel.txt` | ST-3.3 — SSM tunnel pass | ⏳ CDO08 | ⏳ Chờ bastion |
| `st34-loadtest-stats.txt` | ST-3.4 — Locust+Prometheus+Jaeger | ⏳ CDO04 | ⏳ Chờ access |
| `VERIFICATION-REPORT.md` | ST-3.5 — Report tổng hợp | — | ⏳ In progress |
| `TASK23-PROGRESS.md` | Hướng đi + câu hỏi cho team | — | ✅ Done |

**Files cũ (đã sửa thành note, không dùng làm evidence):**

| File | Vấn đề | Xử lý |
|---|---|---|
| `aud-14-storefront-curl.md` | Domain giả, region sai | Đã thay bằng output thực tế |
| `aud-15-grafana-curl.md` | Domain giả (grafana.tf4.techx.vn) | Đã thay bằng output thực tế |
| `aud-15-jaeger-curl.md` | Domain giả (jaeger.tf4.techx.vn) | Đã thay bằng output thực tế |
| `aud-16-argocd-curl.md` | ArgoCD không deploy | Đã ghi N/A |

---

## Cách chạy phần làm được ngay

Chạy 2 lệnh dưới đây từ máy local, copy output thật vào 2 file tương ứng:

**Lệnh cho `st31-env-setup.txt`:**
```bash
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "Public IP: $(curl -s https://checkip.amazonaws.com)"
curl --version | head -1
```

**Lệnh cho `st32-curl-before.txt`:**
```bash
ALB="http://k8s-techxtf4-techxalb-a25731d323-237111145.us-east-1.elb.amazonaws.com"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "From IP  : $(curl -s https://checkip.amazonaws.com)"
for p in "" "grafana/" "jaeger/ui/" "loadgen/" "feature" "flagservice/" "otlp-http/"; do
  CODE=$(curl -sS -o /dev/null -w "%{http_code}" "$ALB/$p")
  echo "${p:-/}  ->  HTTP $CODE"
done
```

---

## Câu hỏi cần hỏi team kia

**→ CDO08 (Nhân)** để unblock ST-3.2 after và ST-3.3:
```
1. SEC-05 deploy xong chưa? (Envoy đã block /grafana/ /jaeger/ /loadgen/ chưa?)
2. Bastion instance-id là gì? (i-0xxxxxxxxx)
3. kubectl -n techx-observability get svc grafana -o jsonpath='{.spec.clusterIP}'
4. kubectl -n techx-observability get svc jaeger  -o jsonpath='{.spec.clusterIP}'
5. AWS profile nào có ssm:StartSession?
```

**→ CDO04 (Huy)** để unblock ST-3.4:
```
1. Cách access Prometheus hiện tại? (port-forward đang mở ở port nào?)
2. Cách access Locust stats? (port-forward hay có endpoint khác?)
3. Load test 200 users chạy lúc mấy giờ UTC? (để CDO07 query đúng window)
```
