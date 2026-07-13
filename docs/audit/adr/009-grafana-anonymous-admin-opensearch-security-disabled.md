# ADR-009: Grafana Anonymous Admin và OpenSearch Security Disabled

**Ngày:** 2026-07-09
**Trạng thái:** Accepted tạm thời — cần fix Week 1 (P0 nếu public expose)
**Người quyết định:** CDO-04 (Infrastructure), CDO-08 (Security)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Security, Auditability
**Source:** `techx-corp-chart/values.yaml`, `techx-corp-platform/src/grafana/grafana.ini`

---

## 1. Bối cảnh (Context)

CDO-08 scan xác nhận Grafana đang cấu hình anonymous access với quyền Admin, và OpenSearch đang tắt hoàn toàn security plugin. Đây là cấu hình mặc định từ chart baseline.

**Tại sao với CDO-07 đây là vấn đề nghiêm trọng:** Grafana chứa SLO dashboards, alert rules, và datasource kết nối đến Prometheus/Jaeger/OpenSearch. Nếu bất kỳ ai có thể sửa dashboard → audit evidence bị compromise. OpenSearch chứa toàn bộ application logs — nếu không có security → log có thể bị đọc/sửa/xóa.

---

## 2. Trạng thái hiện tại (Confirmed từ 2 file)

**Grafana — `values.yaml`:**
```yaml
grafana:
  grafana.ini:
    auth:
      disable_login_form: true    # Không có login form
    auth.anonymous:
      enabled: true
      org_name: Main Org.
      org_role: Admin             # Anonymous = FULL ADMIN
  adminPassword: admin            # Cả login và anonymous đều là admin
```

**Grafana — `src/grafana/grafana.ini` (source config xác nhận):**
```ini
[auth]
disable_login_form = true

[auth.anonymous]
enabled = true
org_role = Admin
```

**OpenSearch — `values.yaml`:**
```yaml
opensearch:
  persistence:
    enabled: false
  extraEnvs:
    - name: "DISABLE_SECURITY_PLUGIN"
      value: "true"               # Security hoàn toàn tắt
```

**Access path:**
```
User → frontend-proxy:8080/grafana/ → grafana.techx-observability:80
→ Bất kỳ ai có ALB DNS đều có quyền Admin Grafana
```

---

## 3. Lý do chưa fix (Rationale)

| Lý do | Giải thích |
|---|---|
| Speed to baseline | Grafana auth cần config provisioning phức tạp hơn |
| On-call access | Không muốn block on-call access khi cần xem dashboard nhanh |
| Demo environment | Hệ thống ban đầu được thiết kế cho demo, không phải production |
| Namespace separation mới hoàn thành | Observability tách namespace là bước đầu, auth là bước tiếp theo |

---

## 4. Rủi ro đã ghi nhận (Known Risks)

| Risk | Impact | Likelihood | CDO-07 impact |
|---|---|---|---|
| Bất kỳ user nào sửa Grafana dashboards/alerts | SLO evidence không đáng tin | Medium | Audit trail compromise |
| OpenSearch logs bị đọc/sửa | PII, order data, payment traces bị expose | Medium | Evidence integrity |
| Alert rules bị tắt trong incident | On-call không nhận được alert | High | Incident response gap |
| Dashboard bị thay đổi để che giấu SLO violation | Cheating in graded context | Low | Audit integrity |

---

## 5. Fix Plan (CDO-08 owns, CDO-07 verify)

**Grafana — giảm anonymous về Viewer:**
```yaml
grafana:
  grafana.ini:
    auth.anonymous:
      enabled: true
      org_role: Viewer    # Từ Admin → Viewer
  adminPassword: <strong-password>
```

**OpenSearch — enable security hoặc isolate:**
Option A: Enable OpenSearch security plugin (phức tạp hơn)
Option B: NetworkPolicy để chỉ allow collector → OpenSearch (đơn giản hơn)

**CDO-07 verify sau fix:**
```bash
# Test anonymous access
curl -s http://<alb>:8080/grafana/api/dashboards/home | jq '.meta.canEdit'
# Expected: false (Viewer không thể edit)

# Test OpenSearch
curl -s http://opensearch:9200/_cat/indices
# Expected: 401 Unauthorized nếu security enabled
```

---

## 6. Tham chiếu (References)

- `techx-corp-chart/values.yaml` — grafana.ini config, opensearch extraEnvs
- `techx-corp-platform/src/grafana/grafana.ini` — source auth config
- `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` — SEC-01
- ADR-006 — Observability namespace separation (context)
