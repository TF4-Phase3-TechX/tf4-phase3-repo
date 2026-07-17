# SEC-13E: Evidence — Verify no plaintext managed credentials in repo and ESO sync pass

**Task:** CDO08-121 — [SEC-13E][Evidence] Verify no plaintext managed credentials in repo and ESO sync pass  
**Parent:** CDO08-1061 — [CDO08-SEC-13][P0][Secrets] Wire managed data credentials through Secrets Manager and ESO

## Status

- [x] Git repo does not contain plaintext managed data credentials (verified below)
- [x] Helm chart supports `managedData` flags (all disabled by default)
- [x] ExternalSecret manifests deployed to GitOps repo (CDO08-119)
- [ ] ESO sync evidence — pending runtime verification after AWS Secrets Manager entries created (CDO08-118)
- [ ] Render clean after managed mode flip — pending cutover tasks (REL-15/16/17)

---

## 1. Git repo plaintext credential scan

### Command

```bash
git grep -r "otelp\|Password=.*otel\|postgres://.*@postgresql\|kafka:9092\|valkey-cart:6379" \
  -- '*.yaml' '*.json' '*.env' '*.tf'
```

### Result (app repo `tf4-phase3-repo`)

Plaintext in-cluster credentials exist **only** in `techx-corp-chart/values.yaml` as default values for in-cluster services (postgresql, kafka, valkey-cart). These are **not** managed data credentials being replaced by SEC-13 — they are the local fallback values used before cutover.

No plaintext managed data credentials (RDS endpoint, ElastiCache endpoint, MSK bootstrap servers) are present in the repo.

### Command (GitOps repo `tf4-phase3-gitops-manifests`)

```bash
git grep -r "password\|secret\|key" -- '*.yaml' | grep -v "secretKey\|secretName\|secretKeyRef\|SecretStore\|ExternalSecret\|kind: Secret"
```

GitOps repo contains only ExternalSecret references — no plaintext values.

---

## 2. Helm render validation (managed mode OFF — default state)

### Command

```bash
helm template techx-corp ./techx-corp-chart \
  -n techx-tf4 \
  -f deploy/values-app-stamp.yaml \
  -f deploy/values-flagd-sync.yaml \
  -f deploy/values-aio-llm.yaml
```

### Result

- Render passes without error.
- In-cluster plaintext values (`kafka:9092`, `valkey-cart:6379`, `Host=postgresql;...otelp...`) still present — **expected** because managed mode is disabled (`managedData.*.enabled: false`).
- No `secretKeyRef` injected by managed data logic — correct.

---

## 3. Helm render validation (managed mode ON — for pre-cutover verification)

Run this command after all three ExternalSecrets are Ready=True to confirm render is clean:

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

Expected: **no output** (grep finds nothing) — means no plaintext credential present in rendered manifests.

Expected `secretKeyRef` entries in rendered output:

```yaml
# accounting — DB_CONNECTION_STRING
- name: DB_CONNECTION_STRING
  valueFrom:
    secretKeyRef:
      name: rds-postgres-secret
      key: dotnet-conn-string

# product-catalog — DB_CONNECTION_STRING
- name: DB_CONNECTION_STRING
  valueFrom:
    secretKeyRef:
      name: rds-postgres-secret
      key: go-conn-string

# product-reviews — DB_CONNECTION_STRING
- name: DB_CONNECTION_STRING
  valueFrom:
    secretKeyRef:
      name: rds-postgres-secret
      key: python-conn-string

# cart — VALKEY_ADDR
- name: VALKEY_ADDR
  valueFrom:
    secretKeyRef:
      name: elasticache-valkey-secret
      key: valkey-address

# accounting, checkout, fraud-detection — KAFKA_ADDR
- name: KAFKA_ADDR
  valueFrom:
    secretKeyRef:
      name: msk-kafka-secret
      key: kafka-address
```

---

## 4. ESO sync verification (runtime — after cutover)

Run after GitOps PR merged and ArgoCD syncs:

```bash
# Check ExternalSecret status
kubectl -n techx-tf4 get externalsecret rds-postgres-secret elasticache-valkey-secret msk-kafka-secret

# Expected: READY=True for all three

# Describe for error details if not Ready
kubectl -n techx-tf4 describe externalsecret rds-postgres-secret
kubectl -n techx-tf4 describe externalsecret elasticache-valkey-secret
kubectl -n techx-tf4 describe externalsecret msk-kafka-secret

# Verify K8s Secrets created (metadata only, no values)
kubectl -n techx-tf4 get secret rds-postgres-secret elasticache-valkey-secret msk-kafka-secret
```

### Expected ESO conditions

```
STATUS   REASON    MESSAGE
True     SecretSynced   Secret was synced
```

No `AccessDenied` errors — means IRSA role has correct IAM permissions for `techx/tf4/*`.  
No missing property errors — means AWS Secrets Manager payload matches ExternalSecret key references.

---

## 5. Runtime env verification (after app cutover)

```bash
kubectl -n techx-tf4 get deploy accounting -o yaml | grep -A5 DB_CONNECTION_STRING
kubectl -n techx-tf4 get deploy product-catalog -o yaml | grep -A5 DB_CONNECTION_STRING
kubectl -n techx-tf4 get deploy product-reviews -o yaml | grep -A5 DB_CONNECTION_STRING
kubectl -n techx-tf4 get deploy cart -o yaml | grep -A5 VALKEY_ADDR
kubectl -n techx-tf4 get deploy checkout -o yaml | grep -A5 KAFKA_ADDR
kubectl -n techx-tf4 get deploy fraud-detection -o yaml | grep -A5 KAFKA_ADDR
```

Expected: `valueFrom.secretKeyRef` present, no plaintext `value:` for managed env vars.

---

## 6. Definition of Done checklist

- [x] `managed-data-secrets.yaml` added to GitOps repo `platform/secrets/`
- [x] `managedData` block added to `techx-corp-chart/values.yaml` (all flags disabled)
- [x] Chart template supports `secretKeyRef` injection when flags enabled
- [x] InitContainer `wait-for-kafka`/`wait-for-valkey-cart` gated behind managed mode flags
- [x] No plaintext managed data credential committed to Git
- [x] `values.schema.json` updated with `managedData` schema
- [ ] AWS Secrets Manager entries created (CDO08-118 — requires real endpoints from Nam)
- [ ] ExternalSecret Ready=True runtime evidence (post-deploy)
- [ ] Helm render clean with managed flags enabled (pre-cutover verification)
- [ ] Cutover tasks (REL-15/16/17) approved before flipping managed flags in production
