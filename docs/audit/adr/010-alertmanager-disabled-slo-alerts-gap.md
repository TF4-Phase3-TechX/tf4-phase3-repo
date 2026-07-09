# ADR-010: Alertmanager Disabled — SLO Alert Gap

**Ngày:** 2026-07-09
**Trạng thái:** Accepted tạm thời — cần fix Week 1 (P1, CDO-07 owns OBS-01)
**Người quyết định:** CDO-04 (Infrastructure), CDO-07 (Audit/Observability)
**Người review:** CDO-08 (Reliability — cung cấp SLO thresholds)
**Pillar liên quan:** Auditability, Reliability
**Source:** `techx-corp-chart/values.yaml:1118`, `grafana/provisioning/alerting/cart-service-alerting.yml`

---

## 1. Bối cảnh (Context)

CDO-08 scan phát hiện `alertmanager.enabled: false`. CDO-07 owns finding OBS-01: "Missing checkout/payment/Kafka/DB SLO alerts".

Đây là gap trực tiếp của CDO-07 — không chỉ là quyết định của CDO-04/08.

---

## 2. Trạng thái hiện tại (Confirmed từ repo)

**Alertmanager disabled:**
```yaml
# values.yaml
prometheus:
  alertmanager:
    enabled: false     # ← Không có alert routing
```

**Alert rules hiện có — chỉ 1 rule duy nhất:**
```yaml
# cart-service-alerting.yml
- title: CartAddItemHighLatency   # ← Chỉ có cart latency alert
  notification_settings:
    receiver: grafana-default-email   # ← Receiver không hoạt động
```

**Không có alert cho:**
- Checkout success rate < 99% ← SLO vi phạm
- Checkout p95 latency > 1s
- Payment failure rate
- Kafka producer failures / consumer lag
- PostgreSQL saturation
- Valkey unavailability

---

## 3. Lý do hiện tại (Rationale)

| Lý do | Giải thích |
|---|---|
| Alertmanager cần config Slack/email | Cần cấp credentials alert channel, chưa setup |
| Prometheus metrics chưa verify đủ labels | Cần live cluster để xác nhận metric names |
| Cost thêm | Alertmanager pod thêm ~50-100Mi RAM |
| Observability mới tách namespace | Ưu tiên stabilize observability trước khi config alerts |

---

## 4. Impact (CDO-07 directly affected)

| Impact | Giải thích |
|---|---|
| SLO không được giám sát tự động | Error budget burn không được phát hiện |
| On-call không nhận alert | Incident detection delay |
| Không có alert evidence cho Ops Review | Khó chứng minh SLO compliance |
| CDO-07 phải manual check Grafana hàng ngày | Thay vì alerting tự động |

---

## 5. Fix Plan (CDO-07 owns OBS-01)

**Bước 1 — Bật Alertmanager:**
```yaml
prometheus:
  alertmanager:
    enabled: true
    config:
      receivers:
        - name: slack-on-call
          slack_configs:
            - api_url: <slack-webhook>
              channel: '#tf4-alerts'
      route:
        receiver: slack-on-call
```

**Bước 2 — Thêm SLO alert rules (CDO-07 viết PromQL):**
```yaml
# Checkout success rate
- alert: CheckoutSuccessRateLow
  expr: |
    sum(rate(rpc_server_requests_per_rpc_count{grpc_service="oteldemo.CheckoutService",grpc_status="OK"}[5m]))
    / sum(rate(rpc_server_requests_per_rpc_count{grpc_service="oteldemo.CheckoutService"}[5m]))
    < 0.99
  for: 2m
  annotations:
    summary: "Checkout success rate below 99% SLO"

# Cart success rate
- alert: CartSuccessRateLow
  expr: |
    sum(rate(rpc_server_requests_per_rpc_count{grpc_service="oteldemo.CartService",grpc_status="OK"}[5m]))
    / sum(rate(rpc_server_requests_per_rpc_count{grpc_service="oteldemo.CartService"}[5m]))
    < 0.995
  for: 2m
  annotations:
    summary: "Cart success rate below 99.5% SLO"
```

**Bước 3 — CDO-07 verify:**
```bash
# Check alertmanager up
kubectl -n techx-observability get pod | grep alertmanager

# Fire test alert
kubectl -n techx-observability port-forward svc/prometheus 9090:9090
# Truy cập http://localhost:9090/alerts → confirm alerts loaded
```

---

## 6. Evidence file

Sau khi implement: tạo `docs/evidence/epic-01/006-obs-01-slo-alert-dashboard-baseline.md`

---

## 7. Tham chiếu (References)

- `techx-corp-chart/values.yaml:1118` — `alertmanager.enabled: false`
- `techx-corp-chart/grafana/provisioning/alerting/cart-service-alerting.yml` — only alert rule
- `docs/requirements/onboarding/SLO.md` — SLO thresholds: checkout ≥99%, cart ≥99.5%, p95 <1s
- `docs/epic-01-addressing-system-gap/GAP-TO-PILLAR-MAPPING.md` — OBS-01 owned by CDO-07
