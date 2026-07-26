# CDO08-REL-22 GitOps Terraform Secret Recoverability Evidence

**Owner:** Hoàng Nam
**Team:** CDO08
**Task:** CDO08-REL-22
**Subtask:** Verify GitOps Terraform and secret reference recoverability
**Ngày ghi nhận:** 2026-07-27

Tài liệu này ghi lại evidence cho khả năng dựng lại Terraform state, GitOps state và secret references. Evidence không chứa secret, credential hoặc plaintext secret value.

---

## 1. Output Của Subtask

Subtask này cần tạo ra các output sau:

- Evidence cho S3 Terraform state versioning và encryption.
- Evidence cho GitOps repo history/branches và root bootstrap path.
- Evidence ExternalSecret manifest chỉ chứa reference, secret source nằm ở AWS Secrets Manager.
- Checklist rebuild tối thiểu để re-bootstrap ArgoCD và resync ExternalSecrets.

Kết luận hiện tại:

| Hạng mục                       | Trạng thái | Evidence chính                                                       |
| ------------------------------ | ---------- | -------------------------------------------------------------------- |
| Terraform remote state backend | PASS       | `s3://tf4-phase3-state-bucket-511825856493/eks/terraform.tfstate`    |
| State bucket versioning        | PASS       | `Status=Enabled`                                                     |
| State bucket encryption        | PASS       | `SSEAlgorithm=AES256`                                                |
| State lock table               | PASS       | `tf4-phase3-state-locks`, `ACTIVE`, SSE `ENABLED`                    |
| GitOps bootstrap path          | PASS       | `argocd/bootstrap/root.yaml` -> `argocd/root-resources`              |
| GitOps repo history/branches   | PASS       | `main` và các branch promotion/REL-22 còn truy vết được              |
| ExternalSecret references      | PASS       | `remoteRef` trỏ tới AWS Secrets Manager, không chứa plaintext secret |
| ExternalSecrets runtime        | PASS       | In-scope ExternalSecret `SecretSynced=True`                          |
| Rebuild checklist              | PASS       | Có checklist re-bootstrap ArgoCD và resync ExternalSecrets           |

---

## 2. Terraform Remote State Backend

Lệnh kiểm tra source:

```powershell
Get-ChildItem -Path infra -Recurse -Filter *.tf |
  Select-String -Pattern 'backend "s3"|tf4-phase3-state-bucket|dynamodb_table|terraform.tfstate' -Context 2,4
```

Output chính:

```hcl
backend "s3" {
  bucket         = "tf4-phase3-state-bucket-511825856493"
  key            = "eks/terraform.tfstate"
  region         = "us-east-1"
  dynamodb_table = "tf4-phase3-state-locks"
  encrypt        = true
}
```

Kết luận:

- Terraform production state dùng S3 remote backend.
- State key nằm ở `eks/terraform.tfstate`.
- State locking dùng DynamoDB table `tf4-phase3-state-locks`.
- Backend bật `encrypt=true`.

---

## 3. State Bucket Versioning

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-versioning `
  --bucket tf4-phase3-state-bucket-511825856493 `
  --profile tf4 `
  --region us-east-1
```

Output:

```json
{
    "Status": "Enabled"
}
```

Kết luận: Terraform state bucket đã bật versioning, hỗ trợ recover lại state object/version khi cần.

---

## 4. State Bucket Encryption

Lệnh kiểm tra:

```powershell
aws s3api get-bucket-encryption `
  --bucket tf4-phase3-state-bucket-511825856493 `
  --profile tf4 `
  --region us-east-1
```

Output chính:

```json
{
    "ServerSideEncryptionConfiguration": {
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                },
                "BucketKeyEnabled": false,
                "BlockedEncryptionTypes": {
                    "EncryptionType": ["SSE-C"]
                }
            }
        ]
    }
}
```

Kết luận: Terraform state bucket được mã hóa server-side bằng `AES256`.

---

## 5. State Lock Table

Lệnh kiểm tra:

```powershell
aws dynamodb describe-table `
  --table-name tf4-phase3-state-locks `
  --profile tf4 `
  --region us-east-1 `
  --query 'Table.{TableName:TableName,TableStatus:TableStatus,BillingMode:BillingModeSummary.BillingMode,SSE:SSEDescription.Status,KeySchema:KeySchema}' `
  --output json
```

Output:

```json
{
    "TableName": "tf4-phase3-state-locks",
    "TableStatus": "ACTIVE",
    "BillingMode": "PAY_PER_REQUEST",
    "SSE": "ENABLED",
    "KeySchema": [
        {
            "AttributeName": "LockID",
            "KeyType": "HASH"
        }
    ]
}
```

Kết luận: Terraform lock table đang hoạt động và được mã hóa.

---

## 6. GitOps Bootstrap Path

Lệnh kiểm tra:

```powershell
Get-ChildItem argocd -Recurse -File | Select-Object -ExpandProperty FullName
```

Output chính:

```text
argocd/bootstrap/root.yaml
argocd/root-resources/applications.yaml
argocd/root-resources/techx-production.yaml
```

Root bootstrap manifest:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
    name: root-bootstrap
    namespace: argocd
spec:
    source:
        repoURL: "https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests.git"
        targetRevision: main
        path: argocd/root-resources
    destination:
        server: "https://kubernetes.default.svc"
        namespace: argocd
    syncPolicy:
        automated:
            prune: false
            selfHeal: true
```

Kết luận:

- Root bootstrap path là `argocd/bootstrap/root.yaml`.
- Root app trỏ về `argocd/root-resources`.
- Các application con được quản lý qua `argocd/root-resources/applications.yaml`.
- `prune=false`, `selfHeal=true`, phù hợp hướng phục hồi thận trọng.

---

## 7. GitOps Runtime State

Lệnh kiểm tra:

```powershell
kubectl -n argocd get application root-bootstrap platform-secrets techx-raw techx-corp `
  -o custom-columns=NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status,REVISION:.status.sync.revision `
  --no-headers
```

Output:

```text
root-bootstrap     Synced      Healthy   42ae20cfb27b1cd589b601871c4465d85982483a
platform-secrets   Synced      Healthy   42ae20cfb27b1cd589b601871c4465d85982483a
techx-raw          OutOfSync   Healthy   42ae20cfb27b1cd589b601871c4465d85982483a
techx-corp         Synced      Healthy   <none>
```

Kết luận:

- `root-bootstrap`, `platform-secrets`, `techx-corp` đang healthy.
- `techx-raw` healthy nhưng OutOfSync do `NetworkPolicy techx-tf4/sec21-allow-flagd-btc-egress` đang diff với desired state; resource này thuộc SEC-21/network egress guardrail, ngoài scope GitOps/Terraform/secret recoverability của subtask này và không chặn evidence về bootstrap/recoverability.

---

## 8. GitOps Repo History Và Branches

Lệnh kiểm tra:

```powershell
git -C tf4-phase3-gitops-manifests log --oneline -5
git -C tf4-phase3-gitops-manifests branch -a --no-color
```

Output history chính:

```text
42ae20c feat(deploy): migrate four stateless workloads to ARM64 Spot (#224)
7c3697e fix(gitops): [CDO08-REL-22] preserve orders protobuf bytes in archive (#223)
362567a fix(deploy): stabilize ARM64 Spot canary batch one (#222)
c0cea3c perf(deploy): add ARM64 Spot canary batch one (#221)
57f501c chore(gitops): promote e4b49ba (#220)
```

Output branch chính:

```text
* main
  remotes/origin/main
  remotes/origin/cdo08/week3/rel22/allow-kafka-connect-msk-egress
  remotes/origin/cdo08/week3/rel22/create-orders-s3-connector
  remotes/origin/cdo08/week3/rel22/fix-orders-s3-connector-path-format
  remotes/origin/cdo08/week3/rel22/fix-orders-s3-connector-string-value
  remotes/origin/cdo08/week3/rel22/preserve-orders-protobuf-bytes
```

Kết luận:

- GitOps repo có history để truy vết trạng thái release.
- Các branch liên quan REL-22 vẫn còn truy vết được trên remote.

---

## 9. ExternalSecret References

Lệnh kiểm tra source:

```powershell
rg -n "kind: ExternalSecret|remoteRef|secretStoreRef|ClusterSecretStore|secretKey|target:" platform/secrets -S
```

Manifest chính:

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
    name: rds-postgres-secret
    namespace: techx-tf4
spec:
    refreshInterval: 1h
    secretStoreRef:
        name: aws-secretsmanager
        kind: ClusterSecretStore
    target:
        name: rds-postgres-secret
        creationPolicy: Owner
    data:
        - secretKey: dotnet-conn-string
          remoteRef:
              key: techx/tf4/rds-postgres
              property: connection_string_dotnet
```

Các managed data secret references:

| Kubernetes Secret           | AWS Secrets Manager key        | Ghi chú                                                |
| --------------------------- | ------------------------------ | ------------------------------------------------------ |
| `rds-postgres-secret`       | `techx/tf4/rds-postgres`       | RDS accounting/app connection strings                  |
| `elasticache-valkey-secret` | `techx/tf4/elasticache-valkey` | Valkey address/password/TLS flag                       |
| `msk-kafka-secret`          | `techx/tf4/msk-kafka`          | MSK bootstrap/security protocol/SASL username/password |

Kết luận:

- ExternalSecret manifest chỉ chứa reference tới AWS Secrets Manager.
- Không copy secret thật vào GitOps repo hoặc evidence.
- Target Kubernetes Secret được tái tạo bởi External Secrets Operator.

---

## 10. ExternalSecret Runtime

Lệnh kiểm tra:

```powershell
kubectl get externalsecret -A
```

Output chính:

```text
NAMESPACE             NAME                        STORE                REFRESH INTERVAL   STATUS         READY
techx-tf4             elasticache-valkey-secret   aws-secretsmanager   1h                 SecretSynced   True
techx-tf4             msk-kafka-secret            aws-secretsmanager   1h                 SecretSynced   True
techx-tf4             postgres-db-secret          aws-secretsmanager   1h                 SecretSynced   True
techx-tf4             rds-postgres-secret         aws-secretsmanager   1h                 SecretSynced   True
```

Lệnh kiểm tra ClusterSecretStore:

```powershell
kubectl get clustersecretstore aws-secretsmanager -o yaml
```

Output chính:

```yaml
spec:
    provider:
        aws:
            auth:
                jwt:
                    serviceAccountRef:
                        name: external-secrets
                        namespace: external-secrets
            region: us-east-1
            service: SecretsManager
status:
    conditions:
        - message: store validated
          reason: Valid
          status: "True"
          type: Ready
```

Kết luận:

- ESO dùng AWS Secrets Manager làm source.
- Store validated và Ready.
- In-scope ExternalSecrets đang sync thành công.

---

## 11. Minimal Rebuild Checklist

Checklist khôi phục tối thiểu nếu cần dựng lại cluster/hạ tầng:

1. Clone source repo và GitOps repo:

```powershell
git clone https://github.com/TF4-Phase3-TechX/tf4-phase3-repo.git
git clone https://github.com/TF4-Phase3-TechX/tf4-phase3-gitops-manifests.git
```

2. Init Terraform backend từ source repo:

```powershell
terraform -chdir=infra/terraform init -reconfigure
terraform -chdir=infra/terraform plan
```

3. Verify state backend trước khi apply:

```powershell
aws s3api get-bucket-versioning --bucket tf4-phase3-state-bucket-511825856493 --profile tf4 --region us-east-1
aws s3api get-bucket-encryption --bucket tf4-phase3-state-bucket-511825856493 --profile tf4 --region us-east-1
aws dynamodb describe-table --table-name tf4-phase3-state-locks --profile tf4 --region us-east-1
```

4. Re-bootstrap ArgoCD root app từ GitOps repo:

```powershell
kubectl apply -n argocd -f argocd/bootstrap/root.yaml
kubectl -n argocd get application root-bootstrap
```

5. Confirm root app tạo lại các application con:

```powershell
kubectl -n argocd get applications
```

6. Confirm External Secrets Operator và platform secrets:

```powershell
kubectl -n argocd get application external-secrets platform-secrets
kubectl get clustersecretstore aws-secretsmanager
kubectl get externalsecret -A
```

7. Resync ExternalSecrets từ AWS Secrets Manager nếu cần:

```powershell
kubectl annotate externalsecret -n techx-tf4 rds-postgres-secret force-sync="$(Get-Date -Format o)" --overwrite
kubectl annotate externalsecret -n techx-tf4 elasticache-valkey-secret force-sync="$(Get-Date -Format o)" --overwrite
kubectl annotate externalsecret -n techx-tf4 msk-kafka-secret force-sync="$(Get-Date -Format o)" --overwrite
kubectl -n techx-tf4 get externalsecret
```

8. Confirm application workloads dùng secret reference đã phục hồi:

```powershell
kubectl -n techx-tf4 get secret rds-postgres-secret elasticache-valkey-secret msk-kafka-secret
kubectl -n techx-tf4 rollout status deploy/checkout --timeout=180s
kubectl -n techx-tf4 rollout status deploy/accounting --timeout=180s
```

Lưu ý: không dùng `kubectl get secret -o yaml` hoặc decode secret value trong evidence.

---

## 12. Kết Luận

Subtask đạt acceptance criteria:

- Terraform state bucket có versioning và encryption.
- Terraform state lock table active và encrypted.
- GitOps repo có root bootstrap path rõ ràng và history/branches truy vết được.
- ExternalSecret manifests chỉ chứa reference, source ở AWS Secrets Manager.
- ExternalSecrets runtime đang sync thành công.
- Có checklist re-bootstrap ArgoCD và resync ExternalSecrets từ ASM.
- Không copy secret thật vào evidence.
