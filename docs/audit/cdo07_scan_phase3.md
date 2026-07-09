# CDO07 Static Audit Scan - Phase 3 v2

Scope: static scan tren repository Phase 3 cho nhom CDO07 Auditability.
Scan mode: scan toan bo repo theo 4 tru de lay context audit, chi ghi nhan finding va evidence.
Repo state: scan tren branch `cdo07/docs/update-phase3-audit-scan-v2`.
Runtime limitation: bao cao nay chi dua tren source code, IaC va tai lieu trong repo. Cac ket luan runtime can xac nhan them bang AWS CLI, AWS Console hoac `kubectl`.

## 1. Nguyen tac phan loai

Nguyen tac cua ban scan v2:

- CDO07 co the scan toan bo 4 tru de phat hien risk lien quan audit.
- Finding duoc ghi theo evidence co trong repo, kem impact va recommendation.
- Finding thuoc Security, Reliability, Cost/Performance hoac AI duoc ghi nhan la cross-pillar observation.
- File nay chi la static scan report, khong phai danh sach task.

## 2. Tong hop theo 4 tru scan

| Tru scan | So finding | Priority chinh | Ghi chu |
| :--- | :--- | :--- | :--- |
| Auditability / Evidence | 10 | P1/P2 | Trong scope chinh cua CDO07 scan |
| Security | 6 | P1/P2 | Cross-pillar observation, anh huong audit/evidence neu lien quan |
| Reliability | 8 | P1/P2 | Cross-pillar observation, dung lam context evidence |
| Operational Excellence | 2 | P2 | Cross-pillar observation, lien quan traceability/supply chain |

## 3. CDO07 Auditability control status

| Control | Status | Evidence trong repo | Nhan xet |
| :--- | :--- | :--- | :--- |
| CODEOWNERS | PASS | `.github/CODEOWNERS` | Co owner review cho repo, docs audit/evidence va workflow |
| ADR template | PASS | `docs/audit/templates/ADR_TEMPLATE.md` | Co template, can dung cho cac trade-off audit |
| Runbook template | PASS | `docs/audit/templates/RUNBOOK_TEMPLATE.md` | Co template, can bo sung runbook evidence collection |
| Postmortem template | PASS | `docs/audit/templates/POSTMORTEM_TEMPLATE.md` | Co template phuc vu incident review |
| Evidence folder | PASS | `docs/evidence/*` | Co evidence theo epic |
| CloudTrail basic | PARTIAL | `infra/terraform/cloudtrail.tf` | Co multi-region trail va S3 versioning |
| CloudTrail hardening | PARTIAL/FAIL | `infra/terraform/cloudtrail.tf` | Thieu log file validation, KMS, CloudWatch Logs integration |
| AWS Config | FAIL | `infra/terraform/*` | Chua thay recorder, delivery channel, config rules |
| IAM Access Analyzer | PASS/PENDING RUNTIME | `infra/terraform/iam.tf` | Co IaC, can runtime evidence de dong ticket stale |
| EKS audit logs | PARTIAL | `infra/terraform/eks.tf` | Co `api`, `audit`, `authenticator`; thieu `controllerManager`, `scheduler` |
| Secret handling evidence | FAIL | `techx-corp-chart/values.yaml` | Co static credential/secret-like values can duoc review boi security owner |
| Weekly audit report | FAIL | Chua thay file weekly report rieng | Can tao output hang tuan cho Evidence Collector |

## 4. Auditability findings

### AUD-01 - CloudTrail log bucket cho phep force destroy

Priority: P1
Status: Open
Evidence:

- `infra/terraform/cloudtrail.tf`
- Resource `aws_s3_bucket.cloudtrail_logs`
- Co `force_destroy = true`

Impact:

- Audit log bucket co the bi xoa cung object khi destroy ha tang.
- Lam yeu tinh bao toan evidence.

Recommendation:

- Doi sang `force_destroy = false`.
- Neu giu vi lab/cost, can ADR ghi ro ly do va thoi han chap nhan rui ro.
- Can nhac S3 Object Lock/retention neu yeu cau audit cao.

### AUD-02 - CloudTrail chua du hardening

Priority: P1
Status: Open
Evidence:

- `infra/terraform/cloudtrail.tf`
- Co `is_multi_region_trail = true`
- Co `include_global_service_events = true`
- Chua thay `enable_log_file_validation`
- Chua thay `kms_key_id`
- Chua thay CloudWatch Logs integration
- Chua thay data event selector

Impact:

- Kho chung minh log integrity.
- Chua co customer-managed KMS cho audit log.
- Thieu CloudWatch Logs integration lam giam kha nang alert gan realtime.
- Neu chi log management events thi mot so data-plane actions co the khong duoc capture.

Recommendation:

- Bat `enable_log_file_validation = true`.
- Them KMS CMK cho CloudTrail.
- Tich hop CloudWatch Logs neu can alert.
- Xem xet data events cho S3 bucket quan trong.

### AUD-03 - AWS Config chua thay trong Terraform

Priority: P1
Status: Open
Evidence:

- Scan static trong `infra/terraform` chua thay:
  - `aws_config_configuration_recorder`
  - `aws_config_delivery_channel`
  - `aws_config_config_rule`

Impact:

- Thieu change history va drift evidence cho AWS resources.
- Kho chung minh compliance tu dong theo thoi gian.

Recommendation:

- Them AWS Config recorder va delivery channel.
- Them managed rules toi thieu cho CloudTrail, S3 public access, EBS encryption, IAM policy.
- Neu da bat thu cong tren AWS, can them runtime evidence vao `docs/evidence`.

### AUD-04 - IAM Access Analyzer co IaC nhung can runtime evidence

Priority: P1
Status: Pending runtime evidence
Evidence:

- `infra/terraform/iam.tf`
- Resource `aws_accessanalyzer_analyzer.main`
- `docs/audit/tickets/AUDIT-007-fix-security-findings.md` van co dau hieu stale khi noi analyzer chua created

Impact:

- IaC da co control, nhung ticket/evidence chua dong bo co the gay sai lech khi nghiem thu.

Recommendation:

- Chay `aws accessanalyzer list-analyzers`.
- Luu output vao `docs/evidence/epic-06-audit`.
- Cap nhat ticket stale theo trang thai moi.

### AUD-05 - EKS endpoint CIDR mac dinh mo rong

Priority: P1/P2
Status: Open
Evidence:

- `infra/terraform/variables.tf`
- `allowed_cluster_endpoint_cidrs` default la `["0.0.0.0/0"]`
- `infra/terraform/eks.tf` bat public endpoint

Impact:

- EKS API endpoint co be mat truy cap rong.
- Can giai thich ro bang ADR neu day la trade-off cho lab.

Recommendation:

- Thu hep CIDR theo IP/VPN thuc te.
- Neu giu public, tao ADR ghi ly do, thoi han va compensating controls.

### AUD-06 - EKS audit log chua bat du full control-plane logs

Priority: P2
Status: Open
Evidence:

- `infra/terraform/eks.tf`
- `cluster_enabled_log_types = ["api", "audit", "authenticator"]`
- Chua thay `controllerManager`, `scheduler`

Impact:

- Da co log quan trong cho audit, nhung chua co full visibility cho control plane.
- Incident lien quan scheduling/controller co the thieu evidence.

Recommendation:

- Can nhac bat du `api`, `audit`, `authenticator`, `controllerManager`, `scheduler`.
- Neu khong bat vi cost/noise, can ADR.

### AUD-07 - ECR image tag mutable lam giam deployment traceability

Priority: P2
Status: Observed
Evidence:

- `infra/terraform/ecr.tf`
- `image_tag_mutability = "MUTABLE"`

Impact:

- Mot tag image co the tro den digest khac theo thoi gian.
- Kho truy vet artifact nao da duoc deploy tai thoi diem incident.

Recommendation:

- Nen chuyen sang `IMMUTABLE`.
- Nen deploy theo version tag hoac digest de tang audit traceability.

### AUD-08 - Weekly Audit Report chua co file rieng

Priority: P2
Status: Open
Evidence:

- Co `docs/audit` va `docs/evidence`
- Chua thay file weekly audit report rieng
- `docs/audit/TEAM_ASSIGNMENT.md` ghi Member 4 la Evidence Collector

Impact:

- Evidence bi phan tan.
- Chua co output dung vai tro Member 4.

Recommendation:

- Tao `docs/audit/weekly/weekly-audit-report-YYYY-MM-DD.md`.
- Moi finding can co owner, status, evidence link, priority va next action.

### AUD-09 - Audit tickets can update status theo evidence moi

Priority: P2
Status: Open
Evidence:

- `docs/audit/tickets/AUDIT-007-fix-security-findings.md`
- `docs/audit/tickets/AUDIT-006-request-missing-iam-permissions.md`
- `docs/audit/tickets/AUDIT-005-enable-access-analyzer.md`

Impact:

- Ticket stale lam audit report khong phan anh dung hien trang.
- Kho tracking giua fixed, pending evidence va still open.

Recommendation:

- Cap nhat ticket theo 3 trang thai: Done, Pending runtime evidence, Still open.
- Gan link evidence tu AWS CLI/kubectl/screenshot.

### AUD-10 - Evidence collection runbook chua du cu the

Priority: P2
Status: Open
Evidence:

- Co `docs/audit/templates/RUNBOOK_TEMPLATE.md`
- Co `docs/audit/runbooks/README.md`
- Chua thay runbook cu the cho weekly evidence collection

Impact:

- Member khac co the thu evidence khong dong nhat.
- Weekly report kho lap lai va kho audit lai.

Recommendation:

- Tao runbook cho CloudTrail, AWS Config, IAM Access Analyzer, EKS audit/RBAC, Grafana/OpenSearch evidence.
- Dinh nghia command, expected output, noi luu file va owner.

## 5. Cross-pillar observations

Nhung finding duoi day duoc scan de lay tong quan. Day la observation ngoai scope chinh cua CDO07 Auditability, nhung co the anh huong audit evidence hoac forensic readiness.

### Security observations

| ID | Finding | Evidence | Priority | Audit note |
| :--- | :--- | :--- | :--- | :--- |
| SEC-01 | Hardcoded credentials/API keys/secret material trong Helm values | `techx-corp-chart/values.yaml` co DB password, `OPENAI_API_KEY`, `SECRET_KEY_BASE`, `POSTGRES_PASSWORD` | P1 | Anh huong secret evidence va audit readiness |
| SEC-02 | Grafana anonymous Admin va admin password mac dinh | `auth.anonymous.enabled`, `org_role: Admin`, `adminPassword: admin` | P1/P0 neu public | Can runtime exposure evidence |
| SEC-03 | OpenSearch security plugin bi disable | `DISABLE_SECURITY_PLUGIN=true` | P1/P2 | Anh huong neu OpenSearch dung lam evidence store |
| SEC-04 | Default container securityContext rong | `default.securityContext: {}` | P2 | Security hardening observation |
| SEC-05 | Chua thay NetworkPolicy, OTel CORS wildcard | Khong thay `NetworkPolicy`; CORS `http://*`, `https://*` | P2 | Network isolation observation |
| SEC-06 | Inter-service gRPC dung insecure transport | `grpc.WithTransportCredentials(insecure.NewCredentials())` | P2 | Service-to-service security observation |

### Reliability observations

| ID | Finding | Evidence | Priority | Audit note |
| :--- | :--- | :--- | :--- | :--- |
| REL-01 | Default app deployment chi co 1 replica | `techx-corp-chart/values.yaml`, `_objects.tpl` | P1 | Co the anh huong availability cua evidence source |
| REL-02 | App pods chua co readiness/liveness probe mac dinh | `values.yaml`, `_objects.tpl` | P1 | Workload reliability observation |
| REL-03 | Chua thay HPA/PDB/topology spread | Negative scan in chart/deploy | P1/P2 | Workload resilience observation |
| REL-04 | PostgreSQL/Valkey/Kafka chua thay PVC/persistence trong chart | `values.yaml`, `_objects.tpl` | P1 | Persistence observation |
| REL-05 | Observability data/alerting chua san sang forensic dai han | Alertmanager disabled, PV disabled, Jaeger memory, OpenSearch persistence off | P1 | Anh huong forensic readiness |
| REL-06 | Checkout side effects khong atomic | `techx-corp-platform/src/checkout/main.go` | P1 | Application consistency observation |
| REL-07 | Kafka producer khong doi broker ack | `producer.go` dung `sarama.NoResponse` | P1/P2 | Event reliability observation |
| REL-08 | Nhieu service thieu CPU/request | `values.yaml`, `deploy/quota.yaml` | P2 | Capacity/scheduling observation |

### Operational Excellence observations

| ID | Finding | Evidence | Priority | Audit note |
| :--- | :--- | :--- | :--- | :--- |
| OPS-01 | Image `latest` va remote artifact download trong Dockerfile | `frontend-proxy`, `ad`, `fraud-detection`, `kafka` Dockerfile | P2 | Anh huong supply-chain traceability |
| OPS-02 | ECR mutable tags | `infra/terraform/ecr.tf` | P2 | Anh huong deployment audit evidence |

## 6. Runtime evidence can bo sung

AWS:

```bash
aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws accessanalyzer list-analyzers --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-configuration-recorders --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-delivery-channels --profile TF4-AuditReadOnlyAndAnalyze
aws budgets describe-budgets --account-id <account-id> --profile TF4-AuditReadOnlyAndAnalyze
```

Kubernetes:

```bash
kubectl get ns
kubectl -n techx get deploy,pod,svc,pvc,events
kubectl -n techx-observability get deploy,pod,svc,pvc,events
kubectl -n techx-observability get hpa,pdb,networkpolicy
kubectl auth can-i --list -n techx
kubectl auth can-i --list -n techx-observability
```

## 7. Ket luan

Trang thai hien tai cua phan CDO07 Auditability: PARTIAL PASS.

Repo da co nen tang audit tot: CODEOWNERS, audit checklist, evidence folder, ADR/runbook/postmortem template, CloudTrail basic va IAM Access Analyzer IaC. Tuy nhien, cac control chua du de nghiem thu hoan chinh vi con thieu CloudTrail hardening, AWS Config, runtime evidence, weekly audit report va runbook evidence collection.

Day la ban static scan report. Cac finding Security/Reliability/Operational Excellence duoc ghi nhan nhu observation ngoai scope chinh cua CDO07 Auditability.
