> **TRẠNG THÁI: DRAFT — CHƯA CHẠY.** Đây là kịch bản lệnh thật để thực thi khi PM đã duyệt
> [kế hoạch](CDO08-REL-23-accounting-rds-isolation-plan.md) và [chi phí](../review-requests/CDO08-REL-23-cost-estimate.md).
> Không chạy các lệnh **MỘT LẦN / MUTATING** ở dưới cho tới khi có approval — các lệnh **QUAN SÁT** (read-only)
> có thể chạy bất cứ lúc nào để kiểm tra tình trạng hệ thống.

# CDO08-REL-23 — Kịch bản demo: tách `accounting` sang RDS instance riêng

**Mandate:** [MANDATE-20-dr-backup-restore.md](../../../../../mandates/MANDATE-20-dr-backup-restore.md) - Directive #20
**Kế hoạch:** [CDO08-REL-23-accounting-rds-isolation-plan.md](CDO08-REL-23-accounting-rds-isolation-plan.md) (§3 đã chốt PA-A cho cả 2 quyết định)
**Chi phí:** [CDO08-REL-23-cost-estimate.md](../review-requests/CDO08-REL-23-cost-estimate.md)
**Region/Account:** `us-east-1` / `511825856493`
**Namespace K8s:** `techx-tf4`

## Quy ước ký hiệu dùng xuyên suốt tài liệu

| Ký hiệu | Ý nghĩa |
|---|---|
| 🔍 **QUAN SÁT LIÊN TỤC** | Lệnh phải để chạy/theo dõi liên tục trong suốt bước đó (dùng `-w`/`--watch` hoặc vòng lặp poll) — không chạy 1 lần rồi bỏ qua, vì trạng thái thay đổi theo thời gian và bạn cần thấy nó ổn định trước khi qua bước sau. |
| ▶️ **CHẠY MỘT LẦN** | Lệnh có tác dụng thay đổi trạng thái (mutating) — chỉ chạy đúng 1 lần, không lặp lại, không chạy lại "cho chắc" (chạy lại có thể gây lỗi hoặc side-effect kép, VD tạo trùng resource, mất offset). |
| ✅ **KIỂM TRA (một lần)** | Lệnh read-only, chạy 1 lần để xác nhận kết quả bước trước, không cần theo dõi liên tục. |
| **Lý do** | Giải thích vì sao bước này cần thiết — đọc trước khi chạy, đừng chạy mù. |

Mọi lệnh dưới đây đã được **kiểm chứng cú pháp thật** trong lúc soạn tài liệu này (không suy đoán):
Terraform block đã chạy `terraform validate` thành công trong bản sao cách ly; các lệnh `kubectl`/`aws` đọc
(get/describe/list) đã chạy thật và xác nhận đúng tên tài nguyên; các lệnh mutating (scale/dump/restore/tạo
secret) được viết theo đúng khuôn mẫu đã dùng thật ở REL-15 (`docs/cdo08/week2/mandate8/scripts/postgres/`),
chỉ đổi tên tài nguyên cho REL-23.

---

## §0. Pre-check bắt buộc — `accounting` hiện đang DOWN (chặn cả Subtask 2 và 4)

**Lý do phải làm trước:** Subtask 2 dựa trên cơ chế "scale `accounting` về 0 = write-freeze tự nhiên vì nó
đang là writer duy nhất". Nếu `accounting` đã chết sẵn từ trước, bước "scale về 0" không có ý nghĩa gì, và
Subtask 4 (validate order processing) không thể chạy vì không có gì để validate.

✅ **KIỂM TRA (một lần)** — xác nhận tình trạng hiện tại:
```bash
kubectl get deployment accounting -n techx-tf4
kubectl describe replicaset -n techx-tf4 -l app.kubernetes.io/component=accounting | tail -15
```
Tại thời điểm soạn tài liệu này, kết quả thật là:
```
NAME         READY   UP-TO-DATE   AVAILABLE   AGE
accounting   0/1     0            0           15d

Events:
  Warning  FailedCreate  ...  replicaset-controller  Error creating: admission webhook
  "ivpol.validate.kyverno.svc-fail-finegrained-require-signed-techx-images" denied the request:
  ... MANIFEST_UNKNOWN: Requested image not found
```
Nghĩa là: pod không tạo được vì Kyverno chặn — image digest hiện tại của `accounting` không còn tồn tại
trên ECR (nhiều khả năng bị lifecycle policy prune). **Đây là sự cố ngoài phạm vi thiết kế REL-23**, không
phải lỗi do kế hoạch này. Không tự sửa trong kịch bản này — cần xử lý riêng (rebuild/push lại image đúng
digest, hoặc trigger lại promotion bot như đã làm cho các sự cố tương tự trước đây trong repo này) **trước
khi tiếp tục §2 trở đi**. Nếu chạy lại lệnh kiểm tra trên và thấy `READY 1/1`, coi như pre-check đã qua.

---

## §1. Chuẩn bị môi trường (một lần, đầu buổi demo)

**Lý do:** cố định các biến dùng xuyên suốt để không gõ sai tên tài nguyên giữa các bước.

✅ **KIỂM TRA (một lần)** — công cụ cần có:
```bash
command -v terraform && command -v kubectl && command -v aws && command -v jq && command -v psql
```
Nếu thiếu `jq`: cài trước (`choco install jq` hoặc `winget install jqlang.jq` trên Windows) — dùng để đọc
JSON credential từ Secrets Manager an toàn, tránh parse tay dễ sai.

▶️ Đặt biến môi trường dùng chung cho cả phiên (không phải lệnh mutating, chỉ set shell variable):
```bash
export NAMESPACE=techx-tf4
export OLD_RDS_ID=techx-tf4-postgresql
export NEW_RDS_ID=techx-tf4-accounting-postgresql
export DB_NAME=otel
export REGION=us-east-1
```

---

## §2. Subtask 1 — Provision dedicated accounting RDS instance

### 2.1 Thêm block Terraform (một lần — commit vào PR, không apply tay ngoài luồng CI)

**Lý do:** mirror đúng cấu hình instance hiện tại (đã xác nhận thật qua `aws rds describe-db-instances`:
`postgres 17.9, db.t4g.micro, MultiAZ=true, storage=20GiB, backup retention=7`), chỉ đổi identifier/SG/subnet
group sang tên mới, giữ private/encrypted/deletion-protection giống hệt.

Thêm file `infra/terraform/rds-accounting.tf` (nội dung dưới đây đã chạy `terraform validate` thành công
trong bản sao cách ly, không có lỗi cú pháp):

```hcl
resource "aws_security_group" "rds_accounting_postgresql" {
  name        = "techx-tf4-rds-accounting-postgresql"
  description = "Private RDS PostgreSQL access for the isolated accounting recovery boundary (REL-23)"
  vpc_id      = module.vpc.vpc_id
  tags = merge(var.tags, { Name = "techx-tf4-rds-accounting-postgresql", Component = "postgresql-accounting", Service = "rds", ManagedBy = "terraform", Mandate = "20", Task = "CDO08-REL-23" })
}

resource "aws_vpc_security_group_ingress_rule" "rds_accounting_postgresql_from_eks_nodes" {
  security_group_id            = aws_security_group.rds_accounting_postgresql.id
  referenced_security_group_id = module.eks.node_security_group_id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "Allow EKS worker nodes to reach the dedicated accounting RDS instance"
}

resource "aws_vpc_security_group_egress_rule" "rds_accounting_postgresql_all_egress" {
  security_group_id = aws_security_group.rds_accounting_postgresql.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
  description       = "Allow outbound responses and AWS-managed maintenance traffic"
}

resource "aws_db_subnet_group" "accounting_postgresql" {
  name       = "techx-tf4-accounting-postgresql-private"
  subnet_ids = module.vpc.private_subnets
  tags       = var.tags
}

resource "aws_db_instance" "accounting_postgresql" {
  identifier = "techx-tf4-accounting-postgresql"

  engine         = "postgres"
  engine_version = "17.9"
  instance_class = "db.t4g.micro"

  db_name  = "otel"
  username = "postgres"

  manage_master_user_password = true

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true

  multi_az               = true
  db_subnet_group_name   = aws_db_subnet_group.accounting_postgresql.name
  vpc_security_group_ids = [aws_security_group.rds_accounting_postgresql.id]
  publicly_accessible    = false

  backup_retention_period = 7
  backup_window           = "18:00-19:00"
  maintenance_window      = "sun:19:00-sun:20:00"

  auto_minor_version_upgrade = false
  copy_tags_to_snapshot      = true
  deletion_protection        = true
  delete_automated_backups   = false
  skip_final_snapshot        = false
  final_snapshot_identifier  = "techx-tf4-accounting-postgresql-final"

  performance_insights_enabled = false
  monitoring_interval          = 0

  tags = merge(var.tags, { Name = "techx-tf4-accounting-postgresql", Component = "postgresql-accounting", Service = "rds", ManagedBy = "terraform", Mandate = "20", Task = "CDO08-REL-23" })
}
```

▶️ **CHẠY MỘT LẦN** — kiểm tra cú pháp và tạo PR (không `terraform apply` tay — CI `terraform-apply.yaml` tự
chạy khi PR merge vào `main`, đúng convention repo này đang dùng):
```bash
cd infra/terraform
terraform fmt rds-accounting.tf
terraform validate
git add rds-accounting.tf
git commit -m "feat(cdo08): [CDO08-REL-23] provision dedicated accounting RDS instance"
git push -u origin <tên-nhánh>
gh pr create --title "feat(cdo08): [CDO08-REL-23] provision dedicated accounting RDS instance" --body "..."
```

🔍 **QUAN SÁT LIÊN TỤC** — sau khi PR merge, theo dõi tới khi instance `available` (RDS mất khoảng 10-15
phút để tạo xong, không có cách rút ngắn — phải đợi, không suy đoán đã xong):
```bash
until [ "$(aws rds describe-db-instances --db-instance-identifier $NEW_RDS_ID --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null)" = "available" ]; do
  echo "$(date -u +%H:%M:%S) - vẫn đang tạo, chờ 30s..."
  sleep 30
done
echo "RDS instance $NEW_RDS_ID đã available."
```

✅ **KIỂM TRA (một lần)** — xác nhận đúng Acceptance Criteria của Subtask 1 (private, PITR, không public):
```bash
aws rds describe-db-instances --db-instance-identifier $NEW_RDS_ID \
  --query 'DBInstances[0].{Status:DBInstanceStatus,MultiAZ:MultiAZ,Public:PubliclyAccessible,Backup:BackupRetentionPeriod,Encrypted:StorageEncrypted,DeletionProtection:DeletionProtection}' \
  --output table
```
Đạt khi: `Public=False`, `Backup=7`, `Encrypted=True`, `DeletionProtection=True`, `MultiAZ=True`.

---

## §3. Subtask 2 — Migrate accounting schema and data safely (PA-A đã chốt)

### 3.1 Ghi baseline TRƯỚC khi freeze (một lần — đây chính là checkpoint P-1/P-2/P-3 trong kế hoạch §7)

**Lý do:** phải có số baseline TRƯỚC khi động vào bất kỳ thứ gì, để so sánh parity sau này. Không có bước
này thì không biết migrate có đúng hay không.

Trước tiên lấy host/port của instance cũ (đã xác nhận thật):
```bash
OLD_HOST=$(aws rds describe-db-instances --db-instance-identifier $OLD_RDS_ID --query 'DBInstances[0].Endpoint.Address' --output text)
echo $OLD_HOST   # kỳ vọng: techx-tf4-postgresql.covse6gsuue2.us-east-1.rds.amazonaws.com
```

Lấy credential master của CẢ 2 instance ngay bây giờ (instance mới ở §2 đã `available`) — biến chỉ tồn tại
trong shell của phiên làm việc, không ghi ra file:
```bash
OLD_SECRET_ARN=$(aws rds describe-db-instances --db-instance-identifier $OLD_RDS_ID --query 'DBInstances[0].MasterUserSecret.SecretArn' --output text)
OLD_USER=$(aws secretsmanager get-secret-value --secret-id "$OLD_SECRET_ARN" --query SecretString --output text | jq -r .username)
OLD_PASS=$(aws secretsmanager get-secret-value --secret-id "$OLD_SECRET_ARN" --query SecretString --output text | jq -r .password)

NEW_HOST=$(aws rds describe-db-instances --db-instance-identifier $NEW_RDS_ID --query 'DBInstances[0].Endpoint.Address' --output text)
NEW_SECRET_ARN=$(aws rds describe-db-instances --db-instance-identifier $NEW_RDS_ID --query 'DBInstances[0].MasterUserSecret.SecretArn' --output text)
NEW_USER=$(aws secretsmanager get-secret-value --secret-id "$NEW_SECRET_ARN" --query SecretString --output text | jq -r .username)
NEW_PASS=$(aws secretsmanager get-secret-value --secret-id "$NEW_SECRET_ARN" --query SecretString --output text | jq -r .password)
```

Tạo 1 K8s Secret tạm chứa credential của cả 2 instance (chỉ tồn tại trong lúc migrate, xoá ở cuối §3.4 —
**không commit vào Git bao giờ**). Dùng tiền tố `old_`/`new_` cho tên key để không trùng nhau khi nạp vào
env của pod ở bước sau:
```bash
kubectl -n $NAMESPACE create secret generic rel23-migrate-creds \
  --from-literal=old_host="$OLD_HOST" --from-literal=old_user="$OLD_USER" --from-literal=old_password="$OLD_PASS" \
  --from-literal=new_host="$NEW_HOST" --from-literal=new_user="$NEW_USER" --from-literal=new_password="$NEW_PASS"
```

Tạo pod tạm để chạy `psql`/`pg_dump` (spec này đã tuân thủ đúng các ValidatingAdmissionPolicy cluster-wide
đang bật — `runAsNonRoot`, drop hết capabilities, có resource limits — copy nguyên khuôn mẫu đã dùng thật ở
REL-15):
```bash
cat <<'YAML' | kubectl -n techx-tf4 apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: rel23-migrate-pod
spec:
  restartPolicy: Never
  containers:
    - name: psql
      image: postgres:17.6
      command: ["sleep", "3600"]
      envFrom:
        - secretRef: { name: rel23-migrate-creds }
      resources:
        requests: { cpu: 50m, memory: 128Mi }
        limits: { cpu: 250m, memory: 256Mi }
      securityContext:
        allowPrivilegeEscalation: false
        capabilities: { drop: ["ALL"] }
        runAsNonRoot: true
        runAsUser: 999
        runAsGroup: 999
        seccompProfile: { type: RuntimeDefault }
YAML
kubectl -n techx-tf4 wait --for=condition=Ready pod/rel23-migrate-pod --timeout=60s
```

✅ **KIỂM TRA (một lần)** — ghi lại baseline (P-1/P-2/P-3 trong kế hoạch), lưu output này làm evidence:
```bash
kubectl -n techx-tf4 exec pod/rel23-migrate-pod -- bash -c '
  PGPASSWORD="$old_password" psql -h "$old_host" -U "$old_user" -d otel -At -c "SELECT COUNT(*) FROM accounting.\"order\";"
  PGPASSWORD="$old_password" psql -h "$old_host" -U "$old_user" -d otel -At -c "SELECT COUNT(*) FROM accounting.orderitem;"
  PGPASSWORD="$old_password" psql -h "$old_host" -U "$old_user" -d otel -At -c "SELECT COUNT(*) FROM accounting.shipping;"
'
```

### 3.2 Scale `accounting` về 0 (▶️ CHẠY MỘT LẦN — đây là điểm write-freeze, ghi lại giờ chính xác)

**Lý do:** `accounting` là writer duy nhất — scale về 0 = không còn ai ghi vào schema `accounting` nữa,
tương đương write-freeze mà không cần lock DB thủ công. Order mới vẫn nằm an toàn trong Kafka topic `orders`.

```bash
date -u   # ghi lại giờ freeze cho evidence
kubectl -n techx-tf4 scale deployment/accounting --replicas=0
```

🔍 **QUAN SÁT LIÊN TỤC** — xác nhận pod cũ đã dừng hẳn trước khi dump (không dump khi pod còn đang terminate,
có thể dump dở dữ liệu):
```bash
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=accounting -w
```
Để tới khi không còn pod nào hiển thị, rồi Ctrl+C thoát watch.

### 3.3 Dump + restore trực tiếp qua network (▶️ CHẠY MỘT LẦN)

**Lý do dùng pipe trực tiếp thay vì dump ra file rồi copy:** cả 2 instance đều nằm trong cùng VPC private
subnet, pod tạm (đã có credential của cả 2 phía từ §3.1) có thể kết nối tới cả hai cùng lúc — pipe thẳng
`pg_dump | psql` tránh phải quản lý file dump trung gian.

Dump schema+data của schema `accounting` (không phải `--schema-only` — lần này cần cả data) và restore
thẳng vào instance mới trong 1 lệnh:
```bash
kubectl -n techx-tf4 exec pod/rel23-migrate-pod -- bash -c '
  set -euo pipefail
  PGPASSWORD="$old_password" pg_dump -h "$old_host" -U "$old_user" -d otel -n accounting --no-owner --no-privileges \
  | PGPASSWORD="$new_password" psql -h "$new_host" -U "$new_user" -d otel -v ON_ERROR_STOP=1
'
```

### 3.4 Parity check (✅ KIỂM TRA — một lần, đối chiếu với baseline §3.1)

```bash
for t in 'accounting."order"' 'accounting.orderitem' 'accounting.shipping'; do
  echo "=== $t ==="
  kubectl -n techx-tf4 exec pod/rel23-migrate-pod -- bash -c "PGPASSWORD=\"\$new_password\" psql -h \"\$new_host\" -U \"\$new_user\" -d otel -At -c \"SELECT COUNT(*) FROM $t;\""
done
```
So từng số với baseline đã ghi ở §3.1 — **phải khớp tuyệt đối (0 lệch)**, đúng tiêu chuẩn A-1/A-2 trong kế hoạch §7.

**Rollback checkpoint (theo Acceptance Criteria Subtask 2):** ghi lại đúng lúc này — instance cũ vẫn còn
nguyên schema `accounting` chưa bị xoá, đây chính là điểm có thể quay lại (Bước R.1 trong kế hoạch §6) nếu
phát hiện lỗi ở các bước sau.

**Chưa xoá pod/secret tạm ở đây** — §4.1 (tạo app role) vẫn cần dùng lại `rel23-migrate-pod`. Chỉ dọn sau
khi §4.1 xong (xem lệnh dọn ở cuối §4.1).

---

## §4. Subtask 3 — Update accounting secret and application connection (PA-A đã chốt)

### 4.1 Tạo app role trên instance mới (▶️ CHẠY MỘT LẦN)

**Lý do:** không dùng master `postgres` làm credential ứng dụng lâu dài — instance cũ dùng role riêng
(`techx_app`, theo evidence REL-15) chỉ có quyền `SELECT, INSERT, UPDATE` trên schema `accounting` (khớp
`postgresql/init.sql`), không phải quyền admin toàn instance. Instance mới cũng phải theo đúng nguyên tắc
least-privilege này.

```bash
NEW_APP_PASSWORD=$(openssl rand -base64 24)   # sinh ngẫu nhiên, KHÔNG ghi ra file/log
kubectl -n techx-tf4 exec pod/rel23-migrate-pod -- bash -c "
  PGPASSWORD=\"\$new_password\" psql -h \"\$new_host\" -U \"\$new_user\" -d otel -v ON_ERROR_STOP=1 -c \"
    CREATE USER techx_app WITH PASSWORD '$NEW_APP_PASSWORD';
    GRANT USAGE ON SCHEMA accounting TO techx_app;
    GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA accounting TO techx_app;
  \"
" 2>&1
```

Dọn pod/secret tạm dùng cho migrate (▶️ CHẠY MỘT LẦN — chỉ sau khi bước trên đã chạy xong, vì đây là lần
cuối cùng còn cần tới `rel23-migrate-pod`):
```bash
kubectl -n techx-tf4 delete pod rel23-migrate-pod
kubectl -n techx-tf4 delete secret rel23-migrate-creds
```

### 4.2 Tạo secret AWS Secrets Manager mới (▶️ CHẠY MỘT LẦN)

```bash
CONN_STRING="Host=${NEW_HOST};Port=5432;Username=techx_app;Password=${NEW_APP_PASSWORD};Database=otel;SSL Mode=Require;Trust Server Certificate=true"
aws secretsmanager create-secret --name techx/tf4/rds-accounting \
  --secret-string "{\"host\":\"${NEW_HOST}\",\"port\":\"5432\",\"username\":\"techx_app\",\"password\":\"${NEW_APP_PASSWORD}\",\"dbname\":\"otel\",\"connection_string_dotnet\":\"${CONN_STRING}\"}"
unset NEW_APP_PASSWORD CONN_STRING   # xoá khỏi biến shell ngay sau khi dùng xong
```
Không có bước nào ở trên ghi password ra file hay commit vào Git — khớp yêu cầu "không plaintext credential
trong Git/evidence" của Acceptance Criteria Subtask 3.

### 4.3 ExternalSecret mới (PR vào gitops repo — ▶️ CHẠY MỘT LẦN để tạo PR)

Thêm vào `[gitops] platform/secrets/managed-data-secrets.yaml`:
```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: rds-accounting-secret
  namespace: techx-tf4
  labels:
    app.kubernetes.io/part-of: techx-corp
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: ClusterSecretStore
  target:
    name: rds-accounting-secret
    creationPolicy: Owner
  data:
    - secretKey: dotnet-conn-string
      remoteRef:
        key: techx/tf4/rds-accounting
        property: connection_string_dotnet
```

🔍 **QUAN SÁT LIÊN TỤC** — sau khi PR merge và ArgoCD sync xong, đợi tới khi `Ready=True`:
```bash
kubectl -n techx-tf4 get externalsecret rds-accounting-secret -w
```

### 4.4 Sửa chart để `accounting` dùng secret riêng (PR vào app repo)

Trong `techx-corp-chart/templates/_pod.tpl`, đổi để `accounting` không còn dùng chung `$pgKeyMap` với
`catalog`/`reviews` nữa — trỏ thẳng secret/key riêng (`rds-accounting-secret` / `dotnet-conn-string`) khi
`.name == "accounting"`. Cụ thể hoá đoạn code này là việc của PR thực thi thật (ngoài phạm vi kịch bản demo
— tài liệu này chỉ mô tả nội dung cần thay đổi, không viết diff Go-template chi tiết ở đây vì phụ thuộc vào
đúng version `_pod.tpl` tại thời điểm thực thi).

### 4.5 Rollout accounting (▶️ CHẠY MỘT LẦN, sau khi PR ở 4.3+4.4 đã merge và sync)

```bash
kubectl -n techx-tf4 scale deployment/accounting --replicas=1
```

🔍 **QUAN SÁT LIÊN TỤC** — theo dõi pod mới lên khoẻ mạnh:
```bash
kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=accounting -w
```

🔍 **QUAN SÁT LIÊN TỤC** — theo dõi log để bắt sớm lỗi kết nối DB hoặc PK-violation khi consumer replay các
message `orders` dồn lại lúc scale-0 (đúng rủi ro đã nêu ở kế hoạch §7 "Rủi ro redeliver"):
```bash
kubectl -n techx-tf4 logs -f deployment/accounting
```
Để chạy nền song song cửa sổ khác trong lúc làm §4.6, không tắt cho tới khi qua §5.

### 4.6 Theo dõi Kafka consumer lag của `accounting` (🔍 QUAN SÁT LIÊN TỤC)

**Lý do:** đây chính là cách đo "bao lâu thì consume hết order dồn lại trong lúc `accounting` down" — số
liệu thật để đưa vào evidence, không suy đoán.

```bash
watch -n 15 "aws cloudwatch get-metric-statistics \
  --namespace AWS/Kafka --metric-name SumOffsetLag \
  --dimensions Name=\"Consumer Group\",Value=accounting Name=\"Cluster Name\",Value=techx-tf4-orders Name=Topic,Value=orders \
  --start-time \$(date -u -d '-10 minutes' +%Y-%m-%dT%H:%M:%S) --end-time \$(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Maximum --region us-east-1 --query 'Datapoints[-1]'"
```
Để tới khi `SumOffsetLag` về 0 (hoặc gần 0, ổn định) — nghĩa là consumer đã bắt kịp toàn bộ order dồn lại.

---

## §5. Subtask 4 — Validate order processing and stabilize cutover

### 5.1 Tạo test order (▶️ CHẠY MỘT LẦN mỗi lần test — có thể lặp lại nếu cần nhiều order test, nhưng mỗi lần là 1 hành động rõ ràng, không phải "chạy liên tục")

**Lý do:** phải có 1 order thật đi qua đúng luồng checkout để chứng minh `accounting` ghi đúng vào instance
mới — không dùng INSERT tay (không đại diện cho luồng thật).

```bash
kubectl -n techx-tf4 port-forward svc/frontend 8888:80 &
FRONTEND_PID=$!
# Tạo order qua UI thật tại http://localhost:8888, hoặc gọi thẳng checkout API nếu có script test order sẵn
# trong repo (kiểm tra techx-corp-platform/src/load-generator/ hoặc frontend/pages/api/checkout.ts để biết
# đúng payload — không suy đoán payload ở đây, phải đọc code thật tại thời điểm thực thi).
kill $FRONTEND_PID
```

### 5.2 Verify order xuất hiện đúng trên instance mới (✅ KIỂM TRA một lần cho mỗi order test)

```bash
NEW_HOST=$(aws rds describe-db-instances --db-instance-identifier $NEW_RDS_ID --query 'DBInstances[0].Endpoint.Address' --output text)
# dùng lại pod tạm hoặc tạo pod mới trỏ instance mới (xem §3.3), rồi:
psql -h "$NEW_HOST" -U techx_app -d otel -c "SELECT order_id FROM accounting.\"order\" ORDER BY order_id DESC LIMIT 5;"
```
Xác nhận order test vừa tạo xuất hiện, không trùng, không thiếu.

### 5.3 Theo dõi ổn định (🔍 QUAN SÁT LIÊN TỤC trong suốt cửa sổ stabilization, ví dụ 24-48h theo tinh thần bake-time đã dùng ở REL-16)

```bash
watch -n 60 "kubectl -n techx-tf4 get pods -l app.kubernetes.io/component=accounting; \
  echo '---consumer lag---'; \
  aws cloudwatch get-metric-statistics --namespace AWS/Kafka --metric-name SumOffsetLag \
  --dimensions Name='Consumer Group',Value=accounting Name='Cluster Name',Value=techx-tf4-orders Name=Topic,Value=orders \
  --start-time \$(date -u -d '-5 minutes' +%Y-%m-%dT%H:%M:%S) --end-time \$(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Maximum --region us-east-1 --query 'Datapoints[-1].Maximum'"
```

### 5.4 Xác nhận không còn ghi mới vào schema cũ (✅ KIỂM TRA — chạy định kỳ trong lúc stabilization, không cần liên tục)

```bash
OLD_HOST=$(aws rds describe-db-instances --db-instance-identifier $OLD_RDS_ID --query 'DBInstances[0].Endpoint.Address' --output text)
# dùng pod tạm trỏ instance cũ:
psql -h "$OLD_HOST" -U techx_app -d otel -c "SELECT COUNT(*) FROM accounting.\"order\";"
```
Số này phải **đứng yên** (không tăng) so với baseline §3.1 trong suốt thời gian stabilization — nếu tăng
nghĩa là vẫn còn thứ gì đó ghi vào instance cũ, cần điều tra trước khi cleanup.

### 5.5 Cleanup schema cũ (▶️ CHẠY MỘT LẦN — CHỈ sau khi có approval, theo đúng Acceptance Criteria Subtask 4)

```bash
# CHƯA VIẾT LỆNH DROP SCHEMA Ở ĐÂY — theo đúng kế hoạch §6 Bước R.3 và §9 pre-check, việc xoá schema cũ
# phải có approval rõ ràng (ai, ngày nào) trước khi thực hiện, không tự động hoá bước này trong kịch bản demo.
```

