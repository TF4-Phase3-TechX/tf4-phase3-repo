# SEC-13E: Evidence — Verify no plaintext managed credentials in repo and ESO sync pass

**Task:** CDO08-121 — [SEC-13E][Evidence] Verify no plaintext managed credentials in repo and ESO sync pass  
**Mục tiêu:** Evidence externalsecret, secretstore, no plaintext scan, rotation note

---

## 1. No plaintext scan — Git repo

```bash
# App repo
git -C tf4-phase3-repo grep -rn \
  "otelp\|Password=.*otel\|postgres://.*@postgresql\|kafka:9092\|valkey-cart:6379" \
  -- '*.yaml' '*.json'

# GitOps repo
git -C tf4-phase3-gitops-manifests grep -rn . -- 'platform/secrets/*.yaml' \
  | grep -v "secretKey:\|remoteRef:\|key:\|property:\|secretStoreRef:\|#\|name:\|namespace:\|kind:\|apiVersion:\|spec:\|data:\|target:\|refreshInterval:\|creationPolicy:\|labels:\|app.kubernetes"
```

Kỳ vọng: không có plaintext credential trong cả hai repo.

Plaintext còn lại trong `techx-corp-chart/values.yaml` là giá trị mặc định cho in-cluster services (postgresql, kafka, valkey-cart) **chưa cutover** — không vi phạm Mandate 8.

---

## 2. SecretStore evidence

```bash
kubectl get clustersecretstore aws-secretsmanager
kubectl describe clustersecretstore aws-secretsmanager
```

Kỳ vọng: `Ready=True`

---

## 3. ExternalSecret evidence

```bash
kubectl -n techx-tf4 get externalsecret \
  rds-postgres-secret elasticache-valkey-secret msk-kafka-secret
```

Kỳ vọng: `READY=True` cho cả 3.

Nếu chưa Ready, describe để xem lỗi:

```bash
kubectl -n techx-tf4 describe externalsecret rds-postgres-secret
kubectl -n techx-tf4 describe externalsecret elasticache-valkey-secret
kubectl -n techx-tf4 describe externalsecret msk-kafka-secret
```

Lỗi thường gặp:
- `AccessDenied` → IRSA role thiếu quyền `GetSecretValue` trên `techx/tf4/*`
- `NoSecretForThisKey` / missing property → AWS Secrets Manager payload chưa có key đó (kiểm tra CDO08-118)

---

## 4. Kubernetes Secret evidence (metadata only — không in value)

```bash
kubectl -n techx-tf4 get secret \
  rds-postgres-secret elasticache-valkey-secret msk-kafka-secret
```

Kỳ vọng: cả 3 secret tồn tại, TYPE = `Opaque`.

---

## 5. AWS Secrets Manager list

```bash
aws secretsmanager list-secrets \
  --region us-east-1 \
  --query 'SecretList[?starts_with(Name, `techx/tf4/`)].{Name:Name,ARN:ARN}' \
  --output table
```

Kỳ vọng thấy đủ:
- `techx/tf4/rds-postgres`
- `techx/tf4/elasticache-valkey`
- `techx/tf4/msk-kafka`

---

## 6. Helm render validation — no plaintext khi managed mode bật

Chạy trước khi cutover để xác nhận chart đã sạch:

```bash
helm template techx-corp ./techx-corp-chart \
  -n techx-tf4 \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  -f deploy/values-aio-llm.yaml \
  --set managedData.postgresql.enabled=true \
  --set managedData.valkey.enabled=true \
  --set managedData.kafka.enabled=true \
  | grep -E 'otelp|Password=|postgres://.*@postgresql|kafka:9092|valkey-cart:6379'
```

Kỳ vọng: **không có output** — không còn plaintext credential trong rendered manifest.

---

## 7. Rotation strategy

Sau khi cutover, rotate credential khi có yêu cầu hoặc security incident:

```bash
# Update secret value trong AWS Secrets Manager
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/rds-postgres" \
  --secret-string '{...new-payload...}' \
  --region us-east-1

# Lặp lại cho elasticache-valkey và msk-kafka nếu cần
```

ESO tự sync theo `refreshInterval: 1h`. Force sync ngay:

```bash
kubectl -n techx-tf4 annotate externalsecret rds-postgres-secret \
  force-sync=$(date +%s) --overwrite
kubectl -n techx-tf4 annotate externalsecret elasticache-valkey-secret \
  force-sync=$(date +%s) --overwrite
kubectl -n techx-tf4 annotate externalsecret msk-kafka-secret \
  force-sync=$(date +%s) --overwrite
```

Sau khi K8s Secret được update, pod sẽ nhận giá trị mới khi restart hoặc redeploy. Không cần xoá Secret thủ công.
