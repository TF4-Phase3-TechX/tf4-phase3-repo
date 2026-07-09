# ADR-008: Hardcoded DB Credentials và API Key Plaintext trong Helm Values

**Ngày:** 2026-07-09
**Trạng thái:** Accepted — cần fix Week 1 (P1)
**Người quyết định:** CDO-04 (Infrastructure), CDO-08 (Security)
**Người review:** CDO-07 (Audit)
**Pillar liên quan:** Security, Auditability
**Source:** `techx-corp-chart/values.yaml` nhiều dòng

---

## 1. Bối cảnh (Context)

CDO-08 scan phát hiện nhiều credentials và sensitive config được hard-code trực tiếp vào `values.yaml` — file này có trong version control và accessible cho tất cả thành viên TF4.

---

## 2. Danh sách credentials đã xác nhận (Confirmed từ values.yaml)

| Credential | File location | Giá trị | Risk |
|---|---|---|---|
| PostgreSQL root password | `values.yaml:870` | `otel` | DB admin access |
| App DB password | `values.yaml:182,581,618` | `otelp` | Read/write mọi schema |
| DB connection string | `values.yaml:581` | `postgres://otelu:otelp@postgresql/otel?sslmode=disable` | Credentials + SSL disabled |
| Grafana admin password | `values.yaml` | `admin` | Grafana admin (cùng với anonymous) |
| OpenAI API key | `values.yaml:600` | `dummy` | Hiện là placeholder |

**SSL disabled:** Tất cả DB connections dùng `sslmode=disable` — data in transit không được mã hóa.

**Đánh giá:**
- Passwords (`otel`, `otelp`) là **thật và đang active** trong production cluster.
- OpenAI key là `dummy` — placeholder, không active.
- Grafana password `admin` kết hợp với anonymous Admin = double exposure.

---

## 3. Lý do Week 1 chưa migrate sang K8s Secrets (Rationale)

| Lý do | Giải thích |
|---|---|
| Speed to baseline | Secret management cần staged rollout để tránh break DB connections |
| Init SQL dependency | PostgreSQL init SQL dùng user `otelu`/password `otelp` — phải migrate đồng bộ |
| Services cần restart | Rotate secret → tất cả services phụ thuộc DB phải restart cùng lúc |
| sslmode migration | Thêm SSL cần PostgreSQL cert provisioning — scope lớn hơn |

---

## 4. Rủi ro đã ghi nhận (Known Risks)

| Risk | Impact | Likelihood |
|---|---|---|
| Bất kỳ thành viên đọc repo đều biết DB password | Compromise accounting data | Confirmed |
| Grafana trace/log có thể expose connection string | Secret leak qua observability | Medium |
| Không có rotation plan | Credential compromise không thể remediate nhanh | High |
| SSL disabled | Man-in-the-middle trong cluster nếu network bị compromise | Low/Medium |

**CDO-07 audit note:** Đây là SEC-02 gap — mọi accounting/order data có thể bị access bởi bất kỳ pod nào trong cluster biết `otelp` password. Audit trail có thể bị modified.

---

## 5. Migration Plan (CDO-08 owns, CDO-07 verify)

**Bước 1 — Tạo Kubernetes Secret:**
```bash
kubectl -n techx-tf4 create secret generic db-credentials \
  --from-literal=POSTGRES_PASSWORD=<new-password> \
  --from-literal=DB_APP_PASSWORD=<new-password>
```

**Bước 2 — Update values.yaml để reference Secret:**
```yaml
postgresql:
  env:
    - name: POSTGRES_PASSWORD
      valueFrom:
        secretKeyRef:
          name: db-credentials
          key: POSTGRES_PASSWORD
```

**Bước 3 — CDO-07 verify:**
```bash
# Confirm không còn plaintext trong rendered manifests
helm -n techx-tf4 get manifest techx-corp | grep -i "otel\|otelp\|password"
# Expected: không có kết quả
```

---

## 6. Tham chiếu (References)

- `techx-corp-chart/values.yaml:181-184, 581-582, 618-619, 866-870` — credential locations
- `techx-corp-chart/postgresql/init.sql` — `CREATE USER otelu WITH PASSWORD 'otelp'`
- `docs/epic-01-addressing-system-gap/PHASE3-IMPLEMENTATION-GAP-ASSESSMENT.md` — SEC-02
- ADR-001 — Separation of Duties: CDO-07 verify sau khi CDO-08 fix
