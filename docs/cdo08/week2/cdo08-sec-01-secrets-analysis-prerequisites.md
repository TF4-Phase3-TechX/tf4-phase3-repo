# CDO08-SEC-01 — Phân tích Secret & Điều kiện tiên quyết

> **Task:** `[CDO08-SEC-01][P1][Secrets] Move sensitive config candidates out of Helm values`
> **Owner chính:** Thuỷ (Security)
> **Branch:** `feature/CDO08-SEC-01-move-secrets`
> **Trạng thái:** `DESIGN + HELM REFERENCES COMPLETE — BLOCKED ON ESO/IRSA/AWS SECRETS PRE-DEPLOY GATES`
> **Thời gian phân tích:** 2026-07-13T22:00:00+07:00
> **Cập nhật lần cuối:** 2026-07-14T14:00:00+07:00

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
| 1 | [values.yaml:L182-186](../../../techx-corp-chart/values.yaml#L182) | `DB_CONNECTION_STRING` | `accounting` | `***REDACTED***` | **Real Secret** — Active DB credential | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: accounting-db-secret` |
| 2 | [values.yaml:L669-673](../../../techx-corp-chart/values.yaml#L669) | `DB_CONNECTION_STRING` | `product-catalog` | `***REDACTED***` | **Real Secret** — Active DB credential | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: product-catalog-db-secret` |
| 3 | [values.yaml:L727-731](../../../techx-corp-chart/values.yaml#L727) | `DB_CONNECTION_STRING` | `product-reviews` | `***REDACTED***` | **Real Secret** — Active DB credential | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: product-reviews-db-secret` |
| 4 | [values.yaml:L706-710](../../../techx-corp-chart/values.yaml#L706) | `OPENAI_API_KEY` | `product-reviews` | `***REDACTED***` | **Placeholder/Demo** — Mocked LLM, không phải key thật | P1 Thấp | ✅ **Đã migrate** → `secretKeyRef: product-reviews-openai-secret` |
| 5 | [values.yaml:L998-1002](../../../techx-corp-chart/values.yaml#L998) | `POSTGRES_PASSWORD` | `postgresql` | `***REDACTED***` | **Real Secret** — PostgreSQL admin password | P1 Cao | ✅ **Đã migrate** → `secretKeyRef: postgresql-secret` |

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

### 3.1 Phương án: External Secrets Operator + AWS Secrets Manager + IRSA

| Tiêu chí | Đánh giá |
|:---|:---|
| **Phương án chọn** | External Secrets Operator (ESO) + AWS Secrets Manager + IRSA |
| **Lý do chọn** | Production-ready; secret thật không nằm trong Git/Helm/CI; source of truth tập trung tại AWS Secrets Manager; có versioning, rotation, audit; quyền truy cập qua IRSA theo nguyên tắc least privilege |
| **Phương án đã loại bỏ** | (1) Helm tự tạo Kubernetes Secret từ `.Values.secrets` — Rủi ro lộ secret qua CI log, Git history, Helm values; (2) CD tạo Secret trực tiếp từ GitHub Actions Secrets — Không centralized, khó audit/rotate |
| **Cách hoạt động** | ESO đồng bộ secret từ AWS Secrets Manager → Kubernetes Secret trong namespace `techx-tf4`. Workload đọc secret qua `secretKeyRef` như trước |

> [!IMPORTANT]
> Branch này **không tự cài External Secrets Operator, IAM role hoặc IRSA**. Trước khi merge/deploy phải có gate xác nhận ESO CRDs/controller, IAM role, IRSA ServiceAccount và AWS Secrets Manager entries đã tồn tại. Nếu các gate này chưa pass, không chạy Helm deploy vì chart sẽ render `ExternalSecret`/`SecretStore` cho app release và workload sẽ phụ thuộc vào các Kubernetes Secret do ESO sync.

### 3.2 Mapping Secret → Service → AWS Secrets Manager

```
Kubernetes Secret                  → Service            → Key              → AWS Secrets Manager Path
──────────────────────────────────────────────────────────────────────────────────────────────────────────
accounting-db-secret               → accounting          (connection-string) → tf4/techx-tf4/accounting/db-connection-string
product-catalog-db-secret          → product-catalog     (connection-string) → tf4/techx-tf4/product-catalog/db-connection-string
product-reviews-db-secret          → product-reviews     (connection-string) → tf4/techx-tf4/product-reviews/db-connection-string
product-reviews-openai-secret      → product-reviews     (api-key)           → tf4/techx-tf4/product-reviews/openai-api-key
postgresql-secret                  → postgresql          (postgres-password)  → tf4/techx-tf4/postgresql/postgres-password
```

### 3.3 Naming Convention — AWS Secrets Manager

```
tf4/techx-tf4/<service-name>/<secret-purpose>
```

Ví dụ:
- `tf4/techx-tf4/accounting/db-connection-string`
- `tf4/techx-tf4/product-reviews/openai-api-key`
- `tf4/techx-tf4/postgresql/postgres-password`

---

## 4. Đánh giá Service bị ảnh hưởng & Rủi ro Rollout

### 4.1 Service bị ảnh hưởng

| Service | Thay đổi | Rủi ro khi rollout | Mitigation |
|:---|:---|:---|:---|
| `accounting` | `DB_CONNECTION_STRING` đọc từ `secretKeyRef` | Pod không start nếu Secret chưa được ESO sync (`CreateContainerConfigError`) | Verify ExternalSecret status `Ready` trước khi `helm upgrade` |
| `product-catalog` | `DB_CONNECTION_STRING` đọc từ `secretKeyRef` | Tương tự trên | Verify ExternalSecret status |
| `product-reviews` | `DB_CONNECTION_STRING` + `OPENAI_API_KEY` đọc từ `secretKeyRef` | 2 secret references — cả hai phải tồn tại | Verify cả 2 ExternalSecret |
| `postgresql` | `POSTGRES_PASSWORD` đọc từ `secretKeyRef` | Rolling restart DB pod — **Rủi ro cao nhất**: phải đảm bảo password match với `init.sql` | Verify password khớp; deploy khi không có active transactions |

### 4.2 Rủi ro rollout tổng thể

> [!WARNING]
> **Rủi ro chính:** Nếu ESO chưa sync thành công 5 secrets từ AWS Secrets Manager trước khi chạy `helm upgrade`, tất cả 4 service sẽ fail với `CreateContainerConfigError`.
>
> **Rủi ro phụ:** PostgreSQL pod restart sẽ gây gián đoạn ngắn (~10-30s) cho tất cả service đọc DB. Cần coordinate với team để deploy khi không có live traffic hoặc chấp nhận downtime ngắn.

### 4.3 Constraint quan trọng

> [!IMPORTANT]
> **Coordination với DB Initializer:** Giá trị password trong AWS Secrets Manager **PHẢI** khớp chính xác với password trong [postgresql/init.sql:L4](../../../techx-corp-chart/postgresql/init.sql#L4) (`otelp` cho user `otelu`, `otel` cho admin). Nếu không khớp, service sẽ bị `connection refused` từ PostgreSQL.

---

## 5. External Secrets Operator — Kiến trúc & Điều kiện tiên quyết

### 5.1 Kiến trúc

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ AWS Secrets Manager                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐      │
│  │ tf4/techx-tf4/accounting/db-connection-string                     │      │
│  │ tf4/techx-tf4/product-catalog/db-connection-string                │      │
│  │ tf4/techx-tf4/product-reviews/db-connection-string                │      │
│  │ tf4/techx-tf4/product-reviews/openai-api-key                      │      │
│  │ tf4/techx-tf4/postgresql/postgres-password                        │      │
│  └───────────────────────────────────────────────────────────────────┘      │
└────────────────────────────────┬─────────────────────────────────────────────┘
                                 │ IRSA (STS AssumeRoleWithWebIdentity)
                                 ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│ EKS Cluster — namespace: techx-tf4                                          │
│                                                                              │
│  ┌─────────────────────────┐    ┌──────────────────────────┐                │
│  │ External Secrets        │    │ SecretStore              │                │
│  │ Operator (ESO)          │◄───│ aws-secretsmanager       │                │
│  │ (external-secrets ns)   │    │ (provider: AWS SM)       │                │
│  └──────────┬──────────────┘    └──────────────────────────┘                │
│             │ sync                                                           │
│             ▼                                                                │
│  ┌──────────────────────────┐   ┌──────────────────────────┐                │
│  │ ExternalSecret (x5)     │──►│ Kubernetes Secret (x5)    │                │
│  │ (refreshInterval: 1h)   │   │ (type: Opaque)            │                │
│  └──────────────────────────┘   └────────────┬─────────────┘                │
│                                               │ secretKeyRef                 │
│                                               ▼                              │
│  ┌──────────────────────────────────────────────────────────┐                │
│  │ Workloads: accounting, product-catalog,                  │                │
│  │            product-reviews, postgresql                    │                │
│  └──────────────────────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Điều kiện tiên quyết

| # | Điều kiện | Trạng thái | Ghi chú |
|:---|:---|:---|:---|
| 1 | External Secrets Operator đã cài trên cluster | ⏳ Cần xác nhận | `kubectl -n external-secrets get pods` |
| 2 | IRSA đã enable trên EKS cluster (OIDC provider) | ⏳ Cần xác nhận | `aws eks describe-cluster --name <cluster> --query "cluster.identity.oidc"` |
| 3 | IAM role cho ESO đã tạo với least-privilege policy | ⏳ Cần tạo / review | Cần team infra/platform hoặc AWS admin tạo policy chỉ đọc đúng secret path |
| 4 | IAM role có trust relationship cho IRSA | ⏳ Cần tạo / review | Trust policy phải bind đúng OIDC provider và service account `techx-tf4/external-secrets-sa` |
| 5 | Service account `external-secrets-sa` có annotation IRSA | ⏳ Cần tạo | `eks.amazonaws.com/role-arn: arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>` |
| 6 | 5 secrets đã tạo trong AWS Secrets Manager | ⏳ Cần tạo | Tạo qua AWS Console hoặc CLI — **không commit giá trị vào repo** |
| 7 | Team có quyền `secretsmanager:CreateSecret` | ⏳ Cần xác nhận | Cần trước khi tạo secrets |

### 5.3 Tạo Secret trong AWS Secrets Manager

> [!IMPORTANT]
> Các lệnh sau chỉ được thực hiện từ máy có quyền truy cập AWS Secrets Manager. Không chạy trong CI/CD pipeline. Không log giá trị secret.

```bash
# Tạo 5 secrets trong AWS Secrets Manager
# Giá trị <VALUE> phải được lấy từ secure source (1Password, vault, etc.)
# KHÔNG commit giá trị thật vào repo hoặc log.

aws secretsmanager create-secret \
  --name tf4/techx-tf4/accounting/db-connection-string \
  --secret-string "<VALUE>" \
  --description "Accounting service DB connection string" \
  --tags Key=project,Value=tf4 Key=namespace,Value=techx-tf4 Key=service,Value=accounting

aws secretsmanager create-secret \
  --name tf4/techx-tf4/product-catalog/db-connection-string \
  --secret-string "<VALUE>" \
  --description "Product Catalog service DB connection string" \
  --tags Key=project,Value=tf4 Key=namespace,Value=techx-tf4 Key=service,Value=product-catalog

aws secretsmanager create-secret \
  --name tf4/techx-tf4/product-reviews/db-connection-string \
  --secret-string "<VALUE>" \
  --description "Product Reviews service DB connection string" \
  --tags Key=project,Value=tf4 Key=namespace,Value=techx-tf4 Key=service,Value=product-reviews

aws secretsmanager create-secret \
  --name tf4/techx-tf4/product-reviews/openai-api-key \
  --secret-string "<VALUE>" \
  --description "Product Reviews OpenAI API key (placeholder/demo)" \
  --tags Key=project,Value=tf4 Key=namespace,Value=techx-tf4 Key=service,Value=product-reviews

aws secretsmanager create-secret \
  --name tf4/techx-tf4/postgresql/postgres-password \
  --secret-string "<VALUE>" \
  --description "PostgreSQL admin password" \
  --tags Key=project,Value=tf4 Key=namespace,Value=techx-tf4 Key=service,Value=postgresql
```

**Xác nhận secrets đã tạo:**

```bash
aws secretsmanager list-secrets \
  --filters Key=name,Values=tf4/techx-tf4 \
  --query "SecretList[].{Name:Name,ARN:ARN}" \
  --output table
```

### 5.4 IRSA Setup

**IAM Policy cần tạo/review:**
- Chỉ cho phép `secretsmanager:GetSecretValue` và `secretsmanager:DescribeSecret`
- Resource giới hạn đúng 5 secret ARN paths
- Không cấp wildcard `secretsmanager:*`

**Trust Policy cần tạo/review:**
- Chỉ cho phép service account `external-secrets-sa` trong namespace `techx-tf4`
- Sử dụng EKS OIDC provider

> [!NOTE]
> Cần thay `<ACCOUNT_ID>` và `<OIDC_PROVIDER>` bằng giá trị thật trong policy files trước khi apply. Lấy OIDC provider:
> ```bash
> aws eks describe-cluster --name <CLUSTER_NAME> \
>   --query "cluster.identity.oidc.issuer" --output text | sed 's|https://||'
> ```

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
> Trên branch `feature/CDO08-SEC-01-move-secrets`, cả 5 candidates đã được migrate trong `values.yaml` sang `secretKeyRef`. ESO sẽ tạo Kubernetes Secrets tự động khi sync từ AWS Secrets Manager.

---

## 7. Thay đổi đã thực hiện trên Branch

### File được sửa đổi / tạo mới / xóa

| File | Mô tả thay đổi |
|:---|:---|
| [techx-corp-chart/values.yaml](../../../techx-corp-chart/values.yaml) | 5 biến env giữ `valueFrom.secretKeyRef`; **xóa** block `.Values.secrets` (CHANGE_ME); **thêm** block `.Values.externalSecrets` (chỉ chứa config reference, không chứa secret value) |
| [techx-corp-chart/values.schema.json](../../../techx-corp-chart/values.schema.json) | **Xóa** schema `secrets`; **thêm** schema `externalSecrets` |
| [deploy/values-app-stamp.yaml](../../../deploy/values-app-stamp.yaml) | **Bật** `externalSecrets.enabled=true` chỉ cho app release `techx-corp` trong namespace `techx-tf4` |
| ~~techx-corp-chart/templates/secrets.yaml~~ | **Đã xóa** — Helm template tạo K8s Secrets không còn cần thiết |
| [techx-corp-chart/templates/secretstore.yaml](../../../techx-corp-chart/templates/secretstore.yaml) | **Mới** — SecretStore namespace-scoped cho AWS Secrets Manager + IRSA |
| [techx-corp-chart/templates/external-secrets.yaml](../../../techx-corp-chart/templates/external-secrets.yaml) | **Mới** — 5 ExternalSecret resources đồng bộ secret từ AWS SM → K8s Secret |
| Infra/IAM policy files | **Chưa nằm trong PR này** — Thuỷ cần tạo review gate/request cho infra/platform hoặc AWS admin nếu các IAM/IRSA resources chưa tồn tại |

### Chi tiết thay đổi trong values.yaml

#### externalSecrets config (thay thế secrets block)
```diff
-# -- Kubernetes Secrets managed by Helm (CDO08-SEC-01)
-# WARNING: Do NOT commit real credentials here. Use placeholder values only.
-# Override with real values via: helm upgrade --set secrets.accounting-db-secret.data.connection-string="..."
-# Or use a separate encrypted values file in CI/CD pipeline.
-secrets:
-  accounting-db-secret:
-    enabled: true
-    data:
-      connection-string: "CHANGE_ME"
-  ...
+# -- External Secrets Operator configuration (CDO08-SEC-01)
+# Secrets are sourced from AWS Secrets Manager and synced by ESO.
+# No secret values are stored in this file or in Git.
+externalSecrets:
+  enabled: false  # base values; app overlay enables this for techx-tf4 only
+  region: us-east-1
+  serviceAccountName: external-secrets-sa
+  refreshInterval: 1h
+  secrets:
+    accounting-db-secret:
+      remoteRef: tf4/techx-tf4/accounting/db-connection-string
+      secretKey: connection-string
+    ...
```

#### deploy/values-app-stamp.yaml
```yaml
externalSecrets:
  enabled: true
```

`externalSecrets.enabled` được bật ở app overlay để chỉ app release `techx-corp` render `SecretStore`/`ExternalSecret` trong namespace `techx-tf4`. Observability release không render các app secrets.

#### secretKeyRef references (giữ nguyên, không thay đổi)
```yaml
# accounting, product-catalog, product-reviews, postgresql
# Tất cả vẫn đọc secret qua secretKeyRef — không ảnh hưởng
- name: DB_CONNECTION_STRING
  valueFrom:
    secretKeyRef:
      name: accounting-db-secret
      key: connection-string
```

---

## 8. Verification Plan

### 8.1 Static Verification — Scan secrets còn sót

```bash
# Quét lại toàn bộ repo xem còn hardcoded credential hoặc CHANGE_ME
rg -n "CHANGE_ME|PASSWORD|SECRET|API_KEY|TOKEN|CONNECTION_STRING" \
  techx-corp-chart/values.yaml deploy/ techx-corp-platform/src/
```

**Kết quả mong đợi:** Các biến trong scope (5 items) chỉ xuất hiện dưới dạng `secretKeyRef` reference, không còn plaintext value hoặc `CHANGE_ME`.

### 8.2 Pre-deploy Gate — ESO, CRDs, IRSA và AWS Secrets

Các gate này phải pass **trước** khi merge/deploy app release:

```bash
# 1. ESO CRDs đã tồn tại
kubectl get crd | rg "externalsecrets|secretstores|clustersecretstores"

# 2. ESO controller đang chạy
kubectl -n external-secrets get pods

# 3. IRSA service account đã tồn tại trong namespace app
kubectl -n techx-tf4 get sa external-secrets-sa -o yaml | rg "eks.amazonaws.com/role-arn"

# 4. EKS OIDC provider đã bật
aws eks describe-cluster \
  --name techx-tf4-cluster \
  --region us-east-1 \
  --query "cluster.identity.oidc.issuer" \
  --output text

# 5. AWS Secrets Manager đã có đủ 5 secret metadata
aws secretsmanager list-secrets \
  --region us-east-1 \
  --filters Key=name,Values=tf4/techx-tf4 \
  --query "SecretList[].Name" \
  --output table
```

Nếu một trong các gate trên chưa pass, dừng deploy và tạo review/request cho team liên quan.

### 8.3 ESO Verification — Sau khi deploy

```bash
# 1. Verify External Secrets Operator đang chạy
kubectl -n external-secrets get pods

# 2. Verify SecretStore ready
kubectl -n techx-tf4 get secretstore aws-secretsmanager
kubectl -n techx-tf4 describe secretstore aws-secretsmanager

# 3. Verify ExternalSecret sync status
kubectl -n techx-tf4 get externalsecret
# Kết quả mong đợi: tất cả 5 ExternalSecret có STATUS = SecretSynced, READY = True

# 4. Verify chi tiết từng ExternalSecret
kubectl -n techx-tf4 describe externalsecret accounting-db-secret
kubectl -n techx-tf4 describe externalsecret product-catalog-db-secret
kubectl -n techx-tf4 describe externalsecret product-reviews-db-secret
kubectl -n techx-tf4 describe externalsecret product-reviews-openai-secret
kubectl -n techx-tf4 describe externalsecret postgresql-secret
```

### 8.4 Kubernetes Secret Verification

```bash
# 5. Verify Kubernetes Secrets đã được ESO tạo
kubectl -n techx-tf4 get secret accounting-db-secret
kubectl -n techx-tf4 get secret product-catalog-db-secret
kubectl -n techx-tf4 get secret product-reviews-db-secret
kubectl -n techx-tf4 get secret product-reviews-openai-secret
kubectl -n techx-tf4 get secret postgresql-secret
# Kết quả mong đợi: 5 secrets hiển thị với TYPE Opaque
```

> [!WARNING]
> **Không được in secret value ra terminal, log hoặc tài liệu evidence.** Chỉ verify sự tồn tại và metadata của secrets.

### 8.5 Runtime Verification — Workload health

```bash
# 6. Verify rollout status
kubectl -n techx-tf4 rollout status deploy/accounting
kubectl -n techx-tf4 rollout status deploy/product-catalog
kubectl -n techx-tf4 rollout status deploy/product-reviews
kubectl -n techx-tf4 rollout status deploy/postgresql

# 7. Verify logs — không có lỗi kết nối DB, lỗi đọc API key, hoặc lỗi thiếu secret
kubectl -n techx-tf4 logs deploy/accounting -c accounting --tail=50
kubectl -n techx-tf4 logs deploy/product-catalog -c product-catalog --tail=50
kubectl -n techx-tf4 logs deploy/product-reviews -c product-reviews --tail=50

# 8. Verify env vars đọc từ secret (không còn plaintext)
kubectl -n techx-tf4 get deploy accounting -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .
```

---

## 9. Rollback & Break-Glass Plan

### 9.1 Rollback Helm changes

```bash
# Revert values.yaml về main
git checkout main -- techx-corp-chart/values.yaml

# Re-deploy Helm chart với values cũ
helm upgrade --install techx-corp ./techx-corp-chart -n techx-tf4 --create-namespace \
  --set default.image.repository=<ECR_REGISTRY_URL> \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml
```

> [!CAUTION]
> **Không rollback bằng cách commit plaintext secret vào repository.** Nếu cần rollback, sử dụng break-glass procedure bên dưới.

### 9.2 Break-Glass — Tạo Kubernetes Secret tạm thời

Nếu ESO hoặc IRSA gặp lỗi và cần khôi phục service ngay:

```bash
# 1. Suspend ExternalSecret để tránh conflict
kubectl -n techx-tf4 annotate externalsecret accounting-db-secret \
  reconcile.external-secrets.io/disabled=true
kubectl -n techx-tf4 annotate externalsecret product-catalog-db-secret \
  reconcile.external-secrets.io/disabled=true
kubectl -n techx-tf4 annotate externalsecret product-reviews-db-secret \
  reconcile.external-secrets.io/disabled=true
kubectl -n techx-tf4 annotate externalsecret product-reviews-openai-secret \
  reconcile.external-secrets.io/disabled=true
kubectl -n techx-tf4 annotate externalsecret postgresql-secret \
  reconcile.external-secrets.io/disabled=true

# 2. Lấy giá trị secret từ AWS Secrets Manager qua kênh kiểm soát
# (Chạy trên máy có quyền truy cập AWS — KHÔNG log giá trị)
SECRET_VALUE=$(aws secretsmanager get-secret-value \
  --secret-id tf4/techx-tf4/accounting/db-connection-string \
  --query SecretString --output text)

# 3. Tạo Kubernetes Secret thủ công
kubectl -n techx-tf4 create secret generic accounting-db-secret \
  --from-literal=connection-string="$SECRET_VALUE" \
  --dry-run=client -o yaml | kubectl apply -f -

# Lặp lại cho 4 secrets còn lại...

# 4. Restart workloads
kubectl -n techx-tf4 rollout restart deploy/accounting
kubectl -n techx-tf4 rollout restart deploy/product-catalog
kubectl -n techx-tf4 rollout restart deploy/product-reviews
kubectl -n techx-tf4 rollout restart deploy/postgresql
```

### 9.3 Khôi phục ESO sau khi lỗi được xử lý

```bash
# 1. Xác nhận ESO pods healthy
kubectl -n external-secrets get pods

# 2. Xác nhận IRSA hoạt động
kubectl -n techx-tf4 describe sa external-secrets-sa

# 3. Remove suspend annotation
kubectl -n techx-tf4 annotate externalsecret accounting-db-secret \
  reconcile.external-secrets.io/disabled-
# Lặp lại cho 4 ExternalSecrets còn lại...

# 4. Verify sync lại thành công
kubectl -n techx-tf4 get externalsecret
# Kết quả: tất cả STATUS = SecretSynced

# 5. Xóa manual secrets nếu cần (ESO sẽ take over ownership)
```

---

## 10. Acceptance Criteria Checklist

| # | Criteria | Trạng thái | Evidence |
|---|:---|:---|:---|
| 1 | Có bảng phân loại secret | ✅ Hoàn thành | [Section 2](#2-bảng-phân-loại-secret-acceptance-criteria-1) — 5 in-scope + 4 out-of-scope |
| 2 | Không còn hardcoded sensitive configuration trong Helm values | ✅ Hoàn thành (trên branch) | `.Values.secrets` với `CHANGE_ME` đã bị xóa; chỉ còn `secretKeyRef` references |
| 3 | Secret thật nằm trong AWS Secrets Manager, không nằm trong Git | ⏳ Chờ tạo secrets trong AWS SM | Cần tạo 5 secrets theo [Section 5.3](#53-tạo-secret-trong-aws-secrets-manager) |
| 4 | Không sử dụng SSM Parameter Store | ✅ Hoàn thành | Toàn bộ thiết kế dùng AWS Secrets Manager |
| 5 | ESO đồng bộ thành công secret từ AWS SM → K8s Secret | ⏳ Chờ deploy & runtime verification | Cần: (a) ESO installed, (b) IRSA configured, (c) `helm upgrade`, (d) verify theo [Section 8.3](#83-eso-verification--sau-khi-deploy) |
| 6 | Workload đọc được secret thông qua secretKeyRef | ⏳ Chờ deploy & runtime verification | Verify theo [Section 8.5](#85-runtime-verification--workload-health) |
| 7 | Có evidence cho IAM/IRSA theo nguyên tắc least privilege | ⏳ Chờ infra/security review | Cần attach IAM policy, trust policy, service account annotation và reviewer approval |
| 8 | Có rollback và break-glass plan rõ ràng | ✅ Hoàn thành | [Section 9](#9-rollback--break-glass-plan) |

> [!IMPORTANT]
> **Hành động tiếp theo:**
> 1. ✅ ~~Phân tích & phân loại secrets~~ — Hoàn thành
> 2. ✅ ~~Code changes: xóa Helm secrets, thêm ESO manifests~~ — Hoàn thành trên branch
> 3. ⏳ **Xác nhận ESO đã cài trên cluster** — Nếu chưa, cần tạo installation request
> 4. ⏳ **Tạo/review IAM policy & trust policy** — Không nằm trong PR hiện tại; cần infra/security review nếu chưa tồn tại
> 5. ⏳ **Tạo IAM role + IRSA** — Apply policy files, tạo service account
> 6. ⏳ **Tạo secrets trong AWS Secrets Manager** — Thuỷ chủ động coordinate
> 7. ⏳ **Chờ approval từ PM/Reviewer** để tiến hành deploy
> 8. ⏳ Deploy & verify runtime — chạy verification plan Section 8

---

## 11. Coordination

| Vai trò | Người | Hành động cần thiết |
|:---|:---|:---|
| Owner | Thuỷ | Đã hoàn thành phân tích, code changes và ESO manifests; cần coordinate pre-deploy gates |
| PM | Hải | Review và approve để tiến hành deploy |
| Security Reviewer | Nhân | Review IAM policy, IRSA trust, ESO configuration khi Thuỷ tạo review request/gate |
| Deploy Operator | — | Hỗ trợ deploy khi có approval |
| Infra/Platform | — | Xác nhận ESO installed, IRSA enabled; tạo IAM role nếu cần review gate |

> [!NOTE]
> Nếu cần review về IAM, chi phí, audit hoặc operator ownership, Thuỷ cần chủ động tạo review request hoặc review gate cho team liên quan trước khi implement và deploy.
