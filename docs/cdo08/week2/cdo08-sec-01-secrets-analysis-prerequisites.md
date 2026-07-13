# CDO08-SEC-01 — Phân tích Secret & Điều kiện tiên quyết

> **Task:** `[CDO08-SEC-01][P1][Secrets] Move sensitive config candidates out of Helm values`
> **Owner chính:** Thuỷ (Security)
> **Branch:** `feature/CDO08-SEC-01-move-secrets`
> **Trạng thái:** `ANALYSIS & PREREQUISITES COMPLETE — WAITING FOR DEPLOY APPROVAL`
> **Thời gian phân tích:** 2026-07-13T22:00:00+07:00

---

## 1. Tổng quan

Báo cáo này tổng hợp kết quả phân tích và phân loại toàn bộ cấu hình nhạy cảm (secrets) được phát hiện trong Helm values và source code, đồng thời ghi nhận trạng thái migration hiện tại trên branch `feature/CDO08-SEC-01-move-secrets`.

**Input đầu vào:**
- [Báo cáo quét Secrets/Config Week 1](../week1/secrets-config-flagd-findings.md) (15 findings, 8 real secrets)
- [Backlog CDO08 Week 1 — item CDO08-SEC-01](../week1/backlog/cdo08-week1-backlog.md)
- Evidence lines trong [values.yaml](../../../techx-corp-chart/values.yaml): L182-183, L581-582, L618-619, L600-601, L870-871

---

## 2. Bảng phân loại Secret (Acceptance Criteria #1)

### 2.1 Scope chính — Findings trong task description

| # | File & Dòng | Config Key | Service | Giá trị hiện tại | Phân loại | Mức độ | Trạng thái migration |
|---|:---|:---|:---|:---|:---|:---|:---|
| 1 | [values.yaml:L182-186](../../../techx-corp-chart/values.yaml#L182) | `DB_CONNECTION_STRING` | `accounting` | `Host=postgresql;Username=otelu;Password=otelp;Database=otel` | **Real Secret** — Active DB credential | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: accounting-db-secret` |
| 2 | [values.yaml:L669-673](../../../techx-corp-chart/values.yaml#L669) | `DB_CONNECTION_STRING` | `product-catalog` | `postgres://otelu:otelp@postgresql/otel?sslmode=disable` | **Real Secret** — Active DB credential | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: product-catalog-db-secret` |
| 3 | [values.yaml:L727-731](../../../techx-corp-chart/values.yaml#L727) | `DB_CONNECTION_STRING` | `product-reviews` | `host=postgresql user=otelu password=otelp dbname=otel` | **Real Secret** — Active DB credential | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: product-reviews-db-secret` |
| 4 | [values.yaml:L706-710](../../../techx-corp-chart/values.yaml#L706) | `OPENAI_API_KEY` | `product-reviews` | `dummy` | **Placeholder/Demo** — Mocked LLM, không phải key thật | P1 Thấp | ✅ **Đã migrate** → `secretKeyRef: product-reviews-openai-secret` |
| 5 | [values.yaml:L998-1002](../../../techx-corp-chart/values.yaml#L998) | `POSTGRES_PASSWORD` | `postgresql` | `otel` | **Real Secret** — PostgreSQL admin password | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: postgresql-secret` |

### 2.2 Findings liên quan — Ngoài scope task nhưng cần ghi nhận

Các items sau được phát hiện trong [báo cáo week1](../week1/secrets-config-flagd-findings.md) nhưng **nằm ngoài scope** của task CDO08-SEC-01 hiện tại. Ghi nhận để tracking trong backlog riêng:

| # | Finding ID | File & Dòng | Config Key | Service | Phân loại | Trạng thái |
|---|:---|:---|:---|:---|:---|:---|
| 6 | SEC-008 | [values.yaml:L975](../../../techx-corp-chart/values.yaml#L975) | `password` (Collector Scraper) | `postgresql` annotations | **Real Secret** — Nằm trong pod annotation, không thể dùng `secretKeyRef` | ⏳ Out of scope — Cần giải pháp khác (OTel Collector secret store) |
| 7 | SEC-006 | [values.yaml:L1369](../../../techx-corp-chart/values.yaml#L1369) | `adminPassword` | `grafana` | **Real Secret** — Grafana subchart config | ⏳ Out of scope — Thuộc task CDO08-SEC-02 |
| 8 | SEC-004 | [values.yaml:L888](../../../techx-corp-chart/values.yaml#L888) | `SECRET_KEY_BASE` | `flagd-ui` | **Real Secret** — Đang bị comment | ⏳ Out of scope — flagd-ui chưa enabled |
| 9 | SEC-007 | [postgresql/init.sql:L4](../../../techx-corp-chart/postgresql/init.sql#L4) | `PASSWORD` (CREATE USER) | `postgresql` | **Real Secret** — Hardcoded trong SQL init script | ⏳ Out of scope — Cần refactor init mechanism |

> [!NOTE]
> Quyết định giữ scope chặt theo 5 evidence lines trong task description (L182-183, L581-582, L618-619, L600-601, L870-871) để tránh mở rộng phạm vi gây rủi ro rollout. Các finding ngoài scope được tracking riêng.

---

## 3. Phương án lưu Secret đã chọn

### 3.1 Phương án: Native Kubernetes Secrets + `secretKeyRef`

| Tiêu chí | Đánh giá |
|:---|:---|
| **Phương án chọn** | Native Kubernetes Secrets với `env.valueFrom.secretKeyRef` |
| **Lý do chọn** | Không cần thêm operator/dependency mới; đủ đáp ứng acceptance criteria; phù hợp với scope P1 |
| **Phương án thay thế đã cân nhắc** | AWS Secrets Manager + External Secrets Operator — Phù hợp hơn cho production thật, nhưng vượt scope task hiện tại và cần install thêm operator trên cluster |
| **Cách tạo Secret** | `kubectl create secret generic` — Xem chi tiết tại [Section 5](#5-lệnh-tạo-kubernetes-secrets-điều-kiện-tiên-quyết) |

### 3.2 Mapping Secret → Service

```
accounting-db-secret          → accounting        (key: connection-string)
product-catalog-db-secret     → product-catalog    (key: connection-string)
product-reviews-db-secret     → product-reviews    (key: connection-string)
product-reviews-openai-secret → product-reviews    (key: api-key)
postgresql-secret             → postgresql         (key: postgres-password)
```

---

## 4. Đánh giá Service bị ảnh hưởng & Rủi ro Rollout

### 4.1 Service bị ảnh hưởng

| Service | Thay đổi | Rủi ro khi rollout | Mitigation |
|:---|:---|:---|:---|
| `accounting` | `DB_CONNECTION_STRING` chuyển từ `value` → `secretKeyRef` | Pod không start nếu Secret chưa tồn tại (`CreateContainerConfigError`) | Pre-create Secret trước khi `helm upgrade` |
| `product-catalog` | `DB_CONNECTION_STRING` chuyển từ `value` → `secretKeyRef` | Tương tự trên | Pre-create Secret |
| `product-reviews` | `DB_CONNECTION_STRING` + `OPENAI_API_KEY` chuyển sang `secretKeyRef` | 2 secret references — cả hai phải tồn tại | Pre-create cả 2 Secret |
| `postgresql` | `POSTGRES_PASSWORD` chuyển sang `secretKeyRef` | Rolling restart DB pod — **Rủi ro cao nhất**: phải đảm bảo password match với `init.sql` | Pre-create Secret; verify password khớp; deploy khi không có active transactions |

### 4.2 Rủi ro rollout tổng thể

> [!WARNING]
> **Rủi ro chính:** Nếu 5 Kubernetes Secrets chưa được tạo trước khi chạy `helm upgrade`, tất cả 4 service sẽ fail với `CreateContainerConfigError`.
>
> **Rủi ro phụ:** PostgreSQL pod restart sẽ gây gián đoạn ngắn (~10-30s) cho tất cả service đọc DB. Cần coordinate với team để deploy khi không có live traffic hoặc chấp nhận downtime ngắn.

### 4.3 Constraint quan trọng

> [!IMPORTANT]
> **Coordination với DB Initializer:** Giá trị password trong Secret **PHẢI** khớp chính xác với password trong [postgresql/init.sql:L4](../../../techx-corp-chart/postgresql/init.sql#L4) (`otelp` cho user `otelu`, `otel` cho admin). Nếu không khớp, service sẽ bị `connection refused` từ PostgreSQL.

---

## 5. Lệnh tạo Kubernetes Secrets (Điều kiện tiên quyết)

> [!IMPORTANT]
> Các lệnh sau **PHẢI** được chạy thành công trước khi thực hiện `helm upgrade` với branch `feature/CDO08-SEC-01-move-secrets`.

```bash
NS=techx-tf4

# 1. accounting — DB connection string (.NET format)
kubectl -n $NS create secret generic accounting-db-secret \
  --from-literal=connection-string="Host=postgresql;Username=otelu;Password=otelp;Database=otel"

# 2. product-catalog — DB connection string (PostgreSQL URI format)
kubectl -n $NS create secret generic product-catalog-db-secret \
  --from-literal=connection-string="postgres://otelu:otelp@postgresql/otel?sslmode=disable"

# 3. product-reviews — DB connection string (libpq format)
kubectl -n $NS create secret generic product-reviews-db-secret \
  --from-literal=connection-string="host=postgresql user=otelu password=otelp dbname=otel"

# 4. product-reviews — OpenAI API key (placeholder)
kubectl -n $NS create secret generic product-reviews-openai-secret \
  --from-literal=api-key="dummy"

# 5. postgresql — Admin password
kubectl -n $NS create secret generic postgresql-secret \
  --from-literal=postgres-password="otel"
```

**Xác nhận điều kiện tiên quyết:**

```bash
# Verify tất cả 5 secrets đã tồn tại
kubectl -n techx-tf4 get secret \
  accounting-db-secret \
  product-catalog-db-secret \
  product-reviews-db-secret \
  product-reviews-openai-secret \
  postgresql-secret
```

**Kết quả mong đợi:** 5 secrets hiển thị với TYPE `Opaque` và trạng thái bình thường.

---

## 6. Migration Candidates theo Priority

| Thứ tự | Secret | Service | Lý do ưu tiên |
|:---|:---|:---|:---|
| **1** | `accounting-db-secret` | `accounting` | DB credential thật, active trên production cluster |
| **2** | `product-catalog-db-secret` | `product-catalog` | DB credential thật, active |
| **3** | `product-reviews-db-secret` | `product-reviews` | DB credential thật, active |
| **4** | `postgresql-secret` | `postgresql` | Admin password thật — deploy sau cùng vì restart DB |
| **5** | `product-reviews-openai-secret` | `product-reviews` | Placeholder `dummy` — rủi ro thấp nhất nhưng nên migrate cùng batch |

> [!NOTE]
> Trên branch `feature/CDO08-SEC-01-move-secrets`, cả 5 candidates đã được migrate trong `values.yaml`. Việc deploy thực tế sẽ áp dụng tất cả cùng lúc qua một lệnh `helm upgrade` duy nhất.

---

## 7. Thay đổi đã thực hiện trên Branch

### File được sửa đổi

| File | Mô tả thay đổi |
|:---|:---|
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml) | 5 biến env chuyển từ `value: <plaintext>` sang `valueFrom.secretKeyRef` |

### Chi tiết diff cho từng service

#### accounting (L182-186)
```diff
       - name: DB_CONNECTION_STRING
-        value: Host=postgresql;Username=otelu;Password=otelp;Database=otel
+        valueFrom:
+          secretKeyRef:
+            name: accounting-db-secret
+            key: connection-string
```

#### product-catalog (L669-673)
```diff
       - name: DB_CONNECTION_STRING
-        value: postgres://otelu:otelp@postgresql/otel?sslmode=disable
+        valueFrom:
+          secretKeyRef:
+            name: product-catalog-db-secret
+            key: connection-string
```

#### product-reviews — OPENAI_API_KEY (L706-710)
```diff
       - name: OPENAI_API_KEY
-        value: dummy
+        valueFrom:
+          secretKeyRef:
+            name: product-reviews-openai-secret
+            key: api-key
```

#### product-reviews — DB_CONNECTION_STRING (L727-731)
```diff
       - name: DB_CONNECTION_STRING
-        value: host=postgresql user=otelu password=otelp dbname=otel
+        valueFrom:
+          secretKeyRef:
+            name: product-reviews-db-secret
+            key: connection-string
```

#### postgresql (L998-1002)
```diff
       - name: POSTGRES_PASSWORD
-        value: otel
+        valueFrom:
+          secretKeyRef:
+            name: postgresql-secret
+            key: postgres-password
```

---

## 8. Verification Plan

### 8.1 Static Verification — Scan secrets còn sót

```bash
# Quét lại toàn bộ repo xem còn hardcoded credential nào trong scope
rg -n "PASSWORD|SECRET|API_KEY|TOKEN|CONNECTION_STRING" \
  techx-corp-chart/values.yaml deploy/ techx-corp-platform/src/
```

**Kết quả mong đợi:** Các biến trong scope (5 items) chỉ xuất hiện dưới dạng `secretKeyRef` reference, không còn plaintext value.

### 8.2 Runtime Verification — Sau khi deploy

```bash
# 1. Verify secrets đã tồn tại trên cluster
kubectl -n techx-tf4 get secret

# 2. Verify rollout status của các service bị ảnh hưởng
kubectl -n techx-tf4 rollout status deploy/accounting
kubectl -n techx-tf4 rollout status deploy/product-catalog
kubectl -n techx-tf4 rollout status deploy/product-reviews
kubectl -n techx-tf4 rollout status deploy/postgresql

# 3. Verify service đọc được DB (check logs cho connection errors)
kubectl -n techx-tf4 logs deploy/accounting -c accounting --tail=50
kubectl -n techx-tf4 logs deploy/product-catalog -c product-catalog --tail=50
kubectl -n techx-tf4 logs deploy/product-reviews -c product-reviews --tail=50

# 4. Verify env vars đọc từ secret (không còn plaintext)
kubectl -n techx-tf4 get deploy accounting -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .
```

---

## 9. Rollback Path

Nếu service không đọc được config mới sau deploy:

```bash
# 1. Revert values.yaml về main
git checkout main -- techx-corp-chart/values.yaml

# 2. Re-deploy Helm chart với values cũ
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 --create-namespace \
  --set default.image.repository=<ECR_REGISTRY_URL> \
  -f deploy/values-observability.yaml \
  -f deploy/values-flagd-sync.yaml

# 3. (Optional) Cleanup secrets nếu cần
kubectl -n techx-tf4 delete secret \
  accounting-db-secret \
  product-catalog-db-secret \
  product-reviews-db-secret \
  product-reviews-openai-secret \
  postgresql-secret
```

---

## 10. Acceptance Criteria Checklist

| # | Criteria | Trạng thái | Evidence |
|---|:---|:---|:---|
| 1 | Có bảng phân loại secret | ✅ Hoàn thành | [Section 2](#2-bảng-phân-loại-secret-acceptance-criteria-1) — 5 in-scope + 4 out-of-scope |
| 2 | Sensitive config không còn hardcoded hoặc có exception rõ | ✅ Hoàn thành (trên branch) | [Section 7](#7-thay-đổi-đã-thực-hiện-trên-branch) — 5/5 items đã migrate; 4 items out-of-scope có exception rõ |
| 3 | Service đọc được secret mới sau deploy | ⏳ Chờ deploy | Cần chạy `helm upgrade` và verify theo [Section 8.2](#82-runtime-verification--sau-khi-deploy) |
| 4 | Có rollback path | ✅ Hoàn thành | [Section 9](#9-rollback-path) |

> [!IMPORTANT]
> **Hành động tiếp theo:**
> 1. ✅ ~~Phân tích & phân loại secrets~~ — Hoàn thành
> 2. ✅ ~~Research phương án & code changes~~ — Hoàn thành trên branch
> 3. ⏳ **Chờ approval từ PM/Reviewer** để tiến hành deploy
> 4. ⏳ Tạo Kubernetes Secrets trên cluster (cần active AWS session)
> 5. ⏳ Deploy & verify runtime

---

## 11. Coordination

| Vai trò | Người | Hành động cần thiết |
|:---|:---|:---|
| Owner | Thuỷ | Đã hoàn thành phân tích, code changes, và báo cáo |
| PM | Hải | Review và approve để tiến hành deploy |
| Security Reviewer | Nhân | Review changes trên branch |
| Deploy Operator | — | Hỗ trợ deploy khi có approval |
