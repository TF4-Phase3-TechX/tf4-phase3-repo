# ADR-007: Single Replica và Không có Readiness/Liveness Probe cho Week 1

**Ngày:** 2026-07-09
**Trạng thái:** Accepted — cần fix Week 1/2 (P0)
**Người quyết định:** CDO-04 (Infrastructure), CDO-08 (Reliability)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Reliability
**Source:** `techx-corp-chart/values.yaml:27`, `techx-corp-chart/templates/_objects.tpl:72-79`

---

## 1. Bối cảnh (Context)

CDO-08 scan runtime xác nhận toàn bộ deployments trong `techx-tf4` chỉ có `1/1` replica và không có readiness/liveness probe.

Hệ thống có tiền sử sự cố:
- **INC-3:** Lỗi payment trong lúc deploy vì traffic vào pod mới trước khi sẵn sàng — nguyên nhân: thiếu readiness gating.
- **INC-2:** Mất giỏ hàng khi node reschedule — liên quan single replica.

---

## 2. Trạng thái hiện tại (Confirmed từ repo)

**Single replica — toàn bộ services:**
```yaml
# values.yaml:27
default:
  replicas: 1    # global default cho tất cả components

# Stateful stores explicit:
flagd:    replicas: 1
kafka:    replicas: 1
postgresql: replicas: 1
valkey-cart: replicas: 1
```

**Không có probe nào được configure:**
```yaml
# _objects.tpl:72-79 — probe chỉ render nếu values set:
{{- if .livenessProbe }}
livenessProbe: ...
{{- end }}
{{- if .readinessProbe }}
readinessProbe: ...
{{- end }}

# values.yaml — toàn bộ components: không có livenessProbe/readinessProbe
# (chỉ có comment: # livenessProbe: {})
```

**Không có HPA/PDB:**
Không tìm thấy `HorizontalPodAutoscaler` hay `PodDisruptionBudget` trong toàn bộ chart templates.

---

## 3. Lý do Week 1 chưa fix (Rationale)

| Lý do | Giải thích |
|---|---|
| Speed to baseline | Tuần 1 ưu tiên deploy được hệ thống trước, tune sau |
| Probe config cần testing | Probe sai có thể gây crash loop — cần test từng service |
| Stateful stores không thể scale blindly | PostgreSQL/Kafka/Valkey không thể tăng replica đơn giản (no leader election, no data sync) |
| Budget concern | Tăng replica stateless services cần CDO-04 review cost trước |

---

## 4. Rủi ro đã ghi nhận (Known Risks)

| Risk ID | Risk | Impact | Services affected |
|---|---|---|---|
| REL-01 | Pod restart → 100% downtime cho service đó | Critical | checkout, cart, payment, frontend |
| REL-02 | Deploy → traffic vào pod chưa ready (lặp lại INC-3) | High | checkout, payment, cart |
| K8S-02 | Node drain → toàn bộ checkout path down | High | tất cả |
| K8S-04 | Data store restart → mất data | Critical | PostgreSQL, Valkey, Kafka |

**CDO-07 audit note:** Không có probe = không có rollout safety = audit evidence có thể bị mất khi deploy. Mọi lần deploy có thể tạo race condition không thể trace được.

---

## 5. Plan fix (CDO-08 owns)

| Priority | Service | Probe type | Timeline |
|---|---|---|---|
| P0 | checkout | gRPC health (`/grpc.health.v1.Health/Check`) | Week 1 |
| P0 | cart | gRPC health | Week 1 |
| P0 | payment | HTTP `/healthz` | Week 1 |
| P0 | frontend | HTTP `/` | Week 1 |
| P0 | product-catalog | gRPC health | Week 1 |
| P1 | Stateless services | gRPC/HTTP health | Week 2 |
| Defer | postgresql/valkey/kafka | Liveness only (không scale data stores) | Week 2+ |

**CDO-07 verify sau khi CDO-08 fix:**
```bash
kubectl -n techx-tf4 get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].readinessProbe}{"\n"}{end}'
```

---

## 6. Tham chiếu (References)

- `techx-corp-chart/values.yaml:27` — `replicas: 1`
- `techx-corp-chart/templates/_objects.tpl:72-79` — conditional probe template
- `docs/requirements/onboarding/INCIDENT_HISTORY.md` — INC-2, INC-3
- `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` — K8S-01, K8S-02
