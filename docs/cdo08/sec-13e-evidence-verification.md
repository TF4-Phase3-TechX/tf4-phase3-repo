# SEC-13E: Evidence — Verify no plaintext managed credentials in repo and ESO sync pass

**Task:** CDO08-121 — [SEC-13E][Evidence] Verify no plaintext managed credentials in repo and ESO sync pass  
**Mục tiêu:** Evidence externalsecret, secretstore, no plaintext scan, rotation note

---

## ✅ VERIFIED — 2026-07-21

### 2a. ClusterSecretStore — READY=True

```
NAME                 AGE     STATUS   CAPABILITIES   READY
aws-secretsmanager   5d19h   Valid    ReadWrite      True
```

### 2b. ExternalSecret — READY=True cho cả 3

```
NAME                        STORE              REFRESH INTERVAL   STATUS         READY
rds-postgres-secret         aws-secretsmanager 1h                 SecretSynced   True
elasticache-valkey-secret   aws-secretsmanager 1h                 SecretSynced   True
msk-kafka-secret            aws-secretsmanager 1h                 SecretSynced   True
```

### 2c. Kubernetes Secrets — tồn tại, TYPE=Opaque

```
NAME                        TYPE     DATA   AGE
rds-postgres-secret         Opaque   3      6h48m
elasticache-valkey-secret   Opaque   1      37s
msk-kafka-secret            Opaque   5      8h
```

### 2d. AWS Secrets Manager — 3 entries SEC-13 tồn tại

```
techx/tf4/rds-postgres       arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/rds-postgres-T586rF
techx/tf4/elasticache-valkey arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/elasticache-valkey-jFYmFu
techx/tf4/msk-kafka          arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/msk-kafka-W5RENp
```

### 2e. IRSA verification — PASS

- ServiceAccount `external-secrets` có annotation `eks.amazonaws.com/role-arn: arn:aws:iam::511825856493:role/external-secrets-techx-tf4-cluster`
- IAM policy `external-secrets-read-production`: Allow `GetSecretValue`, `DescribeSecret`, `ListSecretVersionIds` trên `arn:aws:secretsmanager:us-east-1:511825856493:secret:techx/tf4/*`
- Không có write actions, không có wildcard account-wide

### 2f. No-plaintext scan — PASS

Kết quả `git grep` trên `*.yaml` và `*.json`:
- Matches tìm thấy chỉ trong `docs/evidence/` (snapshot evidence cũ từ directive-03/05, trạng thái cluster trước SEC-13) và `ci.yaml` (pattern trong lệnh grep chính nó)
- Không có plaintext managed credential nào trong source files, chart templates, hay values files production
- `techx-corp-chart/values.yaml` giữ in-cluster default (`postgresql`, `kafka:9092`, `valkey-cart:6379`) cho backward compat local/dev — không vi phạm Mandate 8

### 2g. Helm render validation — PASS

`helm template` với `managedData.*.enabled=true`: không có output từ grep pattern `otelp|Password=otel|postgres://.*@postgresql|kafka:9092|valkey-cart:6379` (sau khi exclude false positives `postgresql-init` và `KAFKA_ADVERTISED_LISTENERS`). App service env vars dùng `secretKeyRef` đúng cho tất cả 7 services.

---

---

## 1. No plaintext managed credentials — Git repo

```bash
# App repo
git -C tf4-phase3-repo grep -rn \
  "otelp\|Password=.*otel\|postgres://.*@postgresql\|kafka:9092\|valkey-cart:6379" \
  -- '*.yaml' '*.json'

# GitOps repo
git -C tf4-phase3-gitops-manifests grep -rn . -- 'platform/secrets/*.yaml' \
  | grep -v "secretKey:\|remoteRef:\|key:\|property:\|secretStoreRef:\|#\|name:\|namespace:\|kind:\|apiVersion:\|spec:\|data:\|target:\|refreshInterval:\|creationPolicy:\|labels:\|app.kubernetes"
```

Kỳ vọng: không có plaintext **managed credentials** trong cả hai repo.

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

Kỳ vọng cuối cùng: `READY=True` cho cả 3.

Nếu AWS Secrets Manager entries `techx/tf4/rds-postgres`,
`techx/tf4/elasticache-valkey` hoặc `techx/tf4/msk-kafka` chưa được tạo/nạp
value thật thì ExternalSecret có thể chưa Ready. Trường hợp đó là blocker của
bước credential handoff/cutover, không phải lý do commit plaintext vào Git.

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
  --set managedData.enabled=true \
  --set managedData.postgresql.enabled=true \
  --set managedData.valkey.enabled=true \
  --set managedData.kafka.enabled=true \
  | grep -E 'otelp|Password=|postgres://.*@postgresql|kafka:9092|valkey-cart:6379'
```

Kỳ vọng: **không có output** — không còn plaintext credential trong rendered manifest.

Không bật các flag này ở production cho tới khi:
- RDS có app credential riêng.
- `cart` hỗ trợ TLS nếu dùng ElastiCache transit encryption.
- Kafka clients hỗ trợ SCRAM/IAM nếu dùng MSK `SASL_SSL`.

---

## 7. Rotation strategy

Sau khi cutover, rotate credential khi có yêu cầu hoặc security incident.

### 7.1 Rotation order

**Không rotate tất cả ba managed data credential cùng lúc.**

Thứ tự đề xuất: **PostgreSQL → Valkey → Kafka**

Chờ pod healthy và smoke test pass cho từng service trước khi tiếp tục rotate service tiếp theo.

### 7.2 Rotation step sequence

Thực hiện lần lượt theo 4 bước sau cho từng service cần rotate:

**Step 1 — Update AWS Secrets Manager:**

```bash
aws secretsmanager put-secret-value \
  --secret-id "techx/tf4/rds-postgres" \
  --secret-string '{...new-payload...}' \
  --region us-east-1
```

Lặp lại với `techx/tf4/elasticache-valkey` hoặc `techx/tf4/msk-kafka` tuỳ theo service đang rotate.

**Step 2 — Confirm ESO sync READY=True với timestamp mới:**

ESO tự sync theo `refreshInterval: 1h`. Force sync ngay nếu cần:

```bash
kubectl -n techx-tf4 annotate externalsecret <name> \
  force-sync=$(date +%s) --overwrite
```

Verify sync thành công và timestamp đã cập nhật:

```bash
kubectl -n techx-tf4 get externalsecret <name>
# Expect: READY=True và SYNCED_AT timestamp mới hơn thời điểm put-secret-value
```

**Step 3 — Rolling restart deployment:**

```bash
kubectl -n techx-tf4 rollout restart deployment/<service-name>
```

**Step 4 — Verify pod healthy và không có authentication error trong logs:**

```bash
kubectl -n techx-tf4 rollout status deployment/<service-name>
kubectl -n techx-tf4 logs -l app=<service-name> --since=2m | grep -i 'auth\|error\|denied'
# Expect: pod healthy, không có authentication error
```

### 7.3 Ghi chú về pod restart

Không cần redeploy nếu chỉ cần credential mới propagate — ESO sync vào Kubernetes Secret mà không cần tác động gì thêm. Tuy nhiên, rolling restart deployment là bắt buộc nếu credential mới cần được inject ngay lập tức (vì env var được inject tại thời điểm pod start, không hot-reload).

### 7.4 Rollback path

Nếu deployment rollout fails sau khi rotate credential, rollback Helm release về revision trước:

```bash
# Xem lịch sử revision
helm history techx-corp -n techx-tf4

# Rollback về revision cụ thể
helm rollback techx-corp <REVISION> -n techx-tf4
```

**Quan trọng: Không xóa Kubernetes Secret do ESO tạo khi rollback.** ESO là owner của các secret `rds-postgres-secret`, `elasticache-valkey-secret`, `msk-kafka-secret` — xóa thủ công sẽ gây disruption cho các pod đang đọc từ secretKeyRef. Helm rollback chỉ revert chart configuration, không ảnh hưởng đến K8s Secrets do ESO quản lý.
