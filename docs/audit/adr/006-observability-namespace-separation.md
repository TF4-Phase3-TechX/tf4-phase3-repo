# ADR-006: Tách Observability Stack sang Namespace Riêng (techx-observability)

**Ngày:** 2026-07-09
**Trạng thái:** Accepted — Implemented
**Người quyết định:** CDO-04 (Infrastructure)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Auditability, Cost Optimization
**Source:** `deploy/values-app-stamp.yaml`, `deploy/values-observability.yaml`, `.github/workflows/deploy.yaml`

---

## 1. Bối cảnh (Context)

Ban đầu, observability stack (Prometheus, Grafana, Jaeger, OpenSearch, OTel Collector) được triển khai trong cùng namespace `techx-tf4` với application. CDO-08 scan phát hiện các pod observability bị `Killed` trong namespace `techx-tf4`.

Điều tra từ `deploy.yaml` CI/CD workflow cho thấy CDO-04 đã chủ động tách thành 2 Helm release riêng biệt.

---

## 2. Quyết định (Decision)

**Tách observability stack ra namespace riêng `techx-observability`.**

Cấu trúc deploy hiện tại (từ `.github/workflows/deploy.yaml`):

```yaml
# Biến môi trường
APP_NAMESPACE: techx-tf4          # Application namespace
OBS_NAMESPACE: techx-observability # Observability namespace

# Deploy observability release
helm upgrade --install techx-observability ./techx-corp-chart \
  --namespace "$OBS_NAMESPACE" \
  -f deploy/values-observability.yaml

# Deploy app release  
helm upgrade --install techx-corp ./techx-corp-chart \
  --namespace "$APP_NAMESPACE" \
  -f deploy/values-app-stamp.yaml
```

`deploy/values-app-stamp.yaml` — app release tắt toàn bộ observability subcharts:
```yaml
opentelemetry-collector: { enabled: false }
jaeger: { enabled: false }
prometheus: { enabled: false }
grafana: { enabled: false }
opensearch: { enabled: false }
```

`deploy/values-observability.yaml` — observability release chỉ bật subcharts, tắt app:
```yaml
opentelemetry-collector: { enabled: true }
jaeger: { enabled: true }
prometheus: { enabled: true }
grafana: { enabled: true }
opensearch: { enabled: true }
# tất cả app components: enabled: false
```

App services gửi telemetry đến collector qua:
```yaml
default:
  envOverrides:
    - name: OTEL_COLLECTOR_NAME
      value: otel-collector.techx-observability.svc.cluster.local
```

---

## 3. Lý do (Rationale)

| Lý do | Giải thích |
|---|---|
| Lifecycle độc lập | Observability có thể upgrade/restart mà không ảnh hưởng app traffic |
| RBAC separation | Dễ cấp quyền read-only cho CDO-07 chỉ trên namespace observability |
| Resource isolation | Observability stack nặng (~2.4GB RAM) không cạnh tranh resource với app services |
| Upgrade path | Cho phép deploy observability changes mà không redeploy toàn bộ app |

---

## 4. Impact với CDO-07 (Audit)

> ⚠️ **CDO-07 cần cập nhật cách truy cập Grafana/logs:**

Grafana hiện ở namespace `techx-observability`, nhưng vẫn accessible qua `frontend-proxy` (trong `techx-tf4`) theo đường:

```
User → frontend-proxy:8080/grafana/ → grafana.techx-observability.svc.cluster.local:80
```

`frontend-proxy` config:
```yaml
- name: GRAFANA_HOST
  value: grafana                           # resolves trong observability namespace
- name: GRAFANA_PORT
  value: "80"
```

Khi verify CDO-07 cần dùng kubectl với đúng namespace:
```bash
# Xem observability resources
kubectl -n techx-observability get pods
kubectl -n techx-observability get svc

# Xem app resources  
kubectl -n techx-tf4 get pods
```

---

## 5. Rủi ro (Known Risks)

| Risk | Impact | Mitigation |
|---|---|---|
| Cross-namespace networking | App cần connect đến observability qua FQDN | Đã config `otel-collector.techx-observability.svc.cluster.local` |
| RBAC complexity tăng | CDO-07 cần quyền trên 2 namespace | Cấp `view` role trên cả hai namespace |
| Grafana không thể truy cập nếu OBS namespace down | SLO monitoring mất | Alert khi observability pods down |

---

## 6. Tham chiếu (References)

- `.github/workflows/deploy.yaml` — 2-release deploy strategy
- `deploy/values-app-stamp.yaml` — App release config
- `deploy/values-observability.yaml` — Observability release config
- ADR-001 — CDO-07 chỉ có Read quyền trên cả 2 namespace
