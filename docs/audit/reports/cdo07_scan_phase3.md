# CDO07 Static Audit Scan - Phase 3 v2

Phạm vi: scan tĩnh trên repository Phase 3 cho nhóm CDO07 Auditability, có bổ sung runtime verification bằng AWS CLI và `kubectl`.
Chế độ scan: scan toàn bộ repo theo 4 trụ để lấy ngữ cảnh audit, chỉ ghi nhận finding và evidence.
Trạng thái repo: scan trên branch `cdo07/docs/update-phase3-audit-scan-v2`.
Giới hạn: static findings dựa trên source code, IaC và tài liệu trong repo. Runtime findings bên dưới đã được xác nhận bằng AWS CLI hoặc `kubectl` tại thời điểm scan.

## 1. Nguyên tắc phân loại

Nguyên tắc của bản scan v2:

- CDO07 scan toàn bộ 4 trụ để phát hiện rủi ro có liên quan đến audit.
- Finding được ghi theo evidence có trong repo, kèm impact và recommendation.
- Finding thuộc Security, Reliability, Cost/Performance hoặc AI được ghi nhận như cross-pillar observation.
- File này chỉ là static scan report, không phải danh sách task.

## 2. Tổng hợp theo 4 trụ scan

| Trụ scan | Số finding | Priority chính | Ghi chú |
| :--- | :--- | :--- | :--- |
| Auditability / Evidence | 10 | P1/P2 | Trong scope chính của CDO07 scan |
| Security | 6 | P1/P2 | Cross-pillar observation, có thể ảnh hưởng audit/evidence |
| Reliability | 8 | P1/P2 | Cross-pillar observation, dùng làm ngữ cảnh evidence |
| Operational Excellence | 2 | P2 | Cross-pillar observation, liên quan traceability/supply chain |

## 3. Runtime verification đã thực hiện

Runtime profile/context đã dùng:

- AWS profile chính: `TF4-AuditReadOnlyAndAnalyze`
- AWS fallback profile: default `TF4-BaseReadOnly`
- AWS account: `511825856493`
- Kubernetes context: `techx-tf4-base`
- Namespace xác nhận: `techx-tf4`, `techx-observability`

Kết quả runtime chính:

| Hạng mục | Runtime result | Ghi chú |
| :--- | :--- | :--- |
| STS audit profile | PASS | Role `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze`, user session `truc.le` |
| STS default profile | PASS | Role `AWSReservedSSO_TF4-BaseReadOnly`, user session `truc.le` |
| CloudTrail trail | PASS/PARTIAL | `tf4-general-cloudtrail` tồn tại, multi-region, đang logging |
| CloudTrail log validation | FAIL CONFIRMED | `LogFileValidationEnabled=false` |
| CloudTrail event selectors | PARTIAL | Chỉ có management events, `DataResources=[]` |
| CloudTrail S3 versioning | PASS | Bucket `tf4-cloudtrail-logs-bucket-511825856493` có versioning `Enabled` |
| S3 public access/encryption metadata | BLOCKED | Audit profile bị deny `s3:GetBucketPublicAccessBlock` và `s3:GetEncryptionConfiguration` |
| AWS Config | FAIL CONFIRMED | `ConfigurationRecorders=[]`, `DeliveryChannels=[]` |
| IAM Access Analyzer | PASS | Analyzer `tf4-iam-analyzer` status `ACTIVE` |
| Access Analyzer findings | OBSERVED | Có nhiều active findings cho IAM roles, cần review riêng |
| EKS describe cluster bằng audit profile | BLOCKED | Audit profile bị deny `eks:DescribeCluster` |
| EKS describe cluster bằng default profile | PASS | Cluster `techx-tf4-cluster` ACTIVE, version `1.34` |
| EKS endpoint | FAIL/PARTIAL | Public endpoint enabled, CIDR `0.0.0.0/0`; private endpoint enabled |
| EKS control-plane logs | PARTIAL | `api`, `audit`, `authenticator` enabled; `controllerManager`, `scheduler` disabled |
| Kubernetes namespaces | PASS | Thấy `techx-tf4` và `techx-observability` |
| Kubernetes workload runtime | PARTIAL | Workloads mostly Running, nhưng `accounting` restart cao và Grafana có restart/readiness/backoff events |

## 4. Trạng thái control Auditability của CDO07

| Control | Status | Evidence trong repo | Nhận xét |
| :--- | :--- | :--- | :--- |
| CODEOWNERS | PASS | `.github/CODEOWNERS` | Có owner review cho repo, docs audit/evidence và workflow |
| ADR template | PASS | `docs/audit/templates/ADR_TEMPLATE.md` | Có template, cần dùng cho các trade-off audit |
| Runbook template | PASS | `docs/audit/templates/RUNBOOK_TEMPLATE.md` | Có template, cần bổ sung runbook evidence collection |
| Postmortem template | PASS | `docs/audit/templates/POSTMORTEM_TEMPLATE.md` | Có template phục vụ incident review |
| Evidence folder | PASS | `docs/evidence/*` | Có evidence theo epic |
| CloudTrail basic | PASS RUNTIME | `infra/terraform/cloudtrail.tf`, AWS CLI | Có multi-region trail, đang logging, S3 versioning enabled |
| CloudTrail hardening | FAIL CONFIRMED | `infra/terraform/cloudtrail.tf`, AWS CLI | Log file validation disabled, chưa thấy data events; KMS/CWL vẫn cần xác nhận/cấu hình |
| AWS Config | FAIL CONFIRMED | `infra/terraform/*`, AWS CLI | Runtime không có recorder, delivery channel, config rules |
| IAM Access Analyzer | PASS RUNTIME | `infra/terraform/iam.tf`, AWS CLI | Analyzer `tf4-iam-analyzer` ACTIVE |
| EKS audit logs | PARTIAL RUNTIME | `infra/terraform/eks.tf`, AWS CLI | Có `api`, `audit`, `authenticator`; `controllerManager`, `scheduler` disabled |
| Secret handling evidence | FAIL | `techx-corp-chart/values.yaml` | Có static credential/secret-like values cần được security owner review |
| Weekly audit report | FAIL | Chưa thấy file weekly report riêng | Cần tạo output hằng tuần cho Evidence Collector |

## 5. Auditability findings

### AUD-01 - CloudTrail log bucket cho phép force destroy

Priority: P1
Status: Open - runtime risk confirmed
Evidence:

- `infra/terraform/cloudtrail.tf`
- Resource `aws_s3_bucket.cloudtrail_logs`
- Có `force_destroy = true`
- Runtime đã xác nhận CloudTrail bucket là `tf4-cloudtrail-logs-bucket-511825856493`
- Runtime đã xác nhận S3 versioning `Enabled`

Impact:

- Audit log bucket có thể bị xóa cùng object khi destroy hạ tầng.
- Làm yếu tính bảo toàn evidence.

Recommendation:

- Đổi sang `force_destroy = false`.
- Nếu giữ vì lab/cost, cần ADR ghi rõ lý do và thời hạn chấp nhận rủi ro.
- Cân nhắc S3 Object Lock/retention nếu yêu cầu audit cao.

### AUD-02 - CloudTrail chưa đủ hardening

Priority: P1
Status: Open - runtime gap confirmed
Evidence:

- `infra/terraform/cloudtrail.tf`
- Có `is_multi_region_trail = true`
- Có `include_global_service_events = true`
- Chưa thấy `enable_log_file_validation`
- Chưa thấy `kms_key_id`
- Chưa thấy CloudWatch Logs integration
- Chưa thấy data event selector
- Runtime `describe-trails`: `LogFileValidationEnabled=false`
- Runtime `get-trail-status`: `IsLogging=true`
- Runtime `get-event-selectors`: `IncludeManagementEvents=true`, `DataResources=[]`

Impact:

- Khó chứng minh log integrity.
- Chưa có customer-managed KMS cho audit log.
- Thiếu CloudWatch Logs integration làm giảm khả năng alert gần realtime.
- Nếu chỉ log management events thì một số data-plane actions có thể không được capture.

Recommendation:

- Bật `enable_log_file_validation = true`.
- Thêm KMS CMK cho CloudTrail.
- Tích hợp CloudWatch Logs nếu cần alert.
- Xem xét data events cho S3 bucket quan trọng.

### AUD-03 - AWS Config chưa thấy trong Terraform

Priority: P1
Status: Open - runtime gap confirmed
Evidence:

- Scan static trong `infra/terraform` chưa thấy:
  - `aws_config_configuration_recorder`
  - `aws_config_delivery_channel`
  - `aws_config_config_rule`
- Runtime AWS CLI:
  - `ConfigurationRecorders=[]`
  - `ConfigurationRecordersStatus=[]`
  - `DeliveryChannels=[]`

Impact:

- Thiếu change history và drift evidence cho AWS resources.
- Khó chứng minh compliance tự động theo thời gian.

Recommendation:

- Thêm AWS Config recorder và delivery channel.
- Thêm managed rules tối thiểu cho CloudTrail, S3 public access, EBS encryption, IAM policy.
- Nếu đã bật thủ công trên AWS, cần thêm runtime evidence vào `docs/evidence`.

### AUD-04 - IAM Access Analyzer có IaC nhưng cần runtime evidence

Priority: P1
Status: Runtime confirmed, ticket cleanup pending
Evidence:

- `infra/terraform/iam.tf`
- Resource `aws_accessanalyzer_analyzer.main`
- `docs/audit/tickets/AUDIT-007-fix-security-findings.md` vẫn có dấu hiệu stale khi nói analyzer chưa created
- Runtime `aws accessanalyzer list-analyzers`: analyzer `tf4-iam-analyzer` status `ACTIVE`
- Runtime analyzer type: `ACCOUNT`
- Runtime findings: có nhiều active findings cho IAM roles, cần review riêng

Impact:

- Control đã tồn tại ở runtime, nhưng ticket/evidence chưa đồng bộ có thể gây sai lệch khi nghiệm thu.
- Active findings của Access Analyzer cần được review để biết finding nào là expected access và finding nào cần xử lý.

Recommendation:

- Lưu output Access Analyzer vào `docs/evidence/epic-06-audit`.
- Cập nhật ticket stale theo trạng thái mới.
- Review danh sách active findings và phân loại expected/needs-action.

### AUD-05 - EKS endpoint CIDR mặc định mở rộng

Priority: P1/P2
Status: Runtime confirmed
Evidence:

- `infra/terraform/variables.tf`
- `allowed_cluster_endpoint_cidrs` default là `["0.0.0.0/0"]`
- `infra/terraform/eks.tf` bật public endpoint
- Runtime `aws eks describe-cluster` bằng default profile:
  - `endpointPublicAccess=true`
  - `endpointPrivateAccess=true`
  - `publicAccessCidrs=["0.0.0.0/0"]`
- Audit profile `TF4-AuditReadOnlyAndAnalyze` bị deny `eks:DescribeCluster`

Impact:

- EKS API endpoint có bề mặt truy cập rộng.
- Cần giải thích rõ bằng ADR nếu đây là trade-off cho lab.

Recommendation:

- Thu hẹp CIDR theo IP/VPN thực tế.
- Nếu giữ public, tạo ADR ghi lý do, thời hạn và compensating controls.

### AUD-06 - EKS audit log chưa bật đủ full control-plane logs

Priority: P2
Status: Runtime confirmed
Evidence:

- `infra/terraform/eks.tf`
- `cluster_enabled_log_types = ["api", "audit", "authenticator"]`
- Chưa thấy `controllerManager`, `scheduler`
- Runtime EKS logging:
  - `api`, `audit`, `authenticator` enabled
  - `controllerManager`, `scheduler` disabled

Impact:

- Đã có log quan trọng cho audit, nhưng chưa có full visibility cho control plane.
- Incident liên quan scheduling/controller có thể thiếu evidence.

Recommendation:

- Cân nhắc bật đủ `api`, `audit`, `authenticator`, `controllerManager`, `scheduler`.
- Nếu không bật vì cost/noise, cần ADR.

### AUD-07 - ECR image tag mutable làm giảm deployment traceability

Priority: P2
Status: Observed
Evidence:

- `infra/terraform/ecr.tf`
- `image_tag_mutability = "MUTABLE"`

Impact:

- Một tag image có thể trỏ đến digest khác theo thời gian.
- Khó truy vết artifact nào đã được deploy tại thời điểm incident.

Recommendation:

- Nên chuyển sang `IMMUTABLE`.
- Nên deploy theo version tag hoặc digest để tăng audit traceability.

### AUD-08 - Weekly Audit Report chưa có file riêng

Priority: P2
Status: Static gap, runtime context available
Evidence:

- Có `docs/audit` và `docs/evidence`
- Chưa thấy file weekly audit report riêng
- `docs/audit/TEAM_ASSIGNMENT.md` ghi Member 4 là Evidence Collector
- Runtime evidence hiện đã có thể đưa vào weekly report: CloudTrail, AWS Config, Access Analyzer, EKS, Kubernetes workload status

Impact:

- Evidence bị phân tán.
- Chưa có output đúng vai trò Member 4.

Recommendation:

- Tạo `docs/audit/weekly/weekly-audit-report-YYYY-MM-DD.md`.
- Mỗi finding cần có owner, status, evidence link, priority và next action.

### AUD-09 - Audit tickets cần cập nhật status theo evidence mới

Priority: P2
Status: Open - runtime status changed
Evidence:

- `docs/audit/tickets/AUDIT-007-fix-security-findings.md`
- `docs/audit/tickets/AUDIT-006-request-missing-iam-permissions.md`
- `docs/audit/tickets/AUDIT-005-enable-access-analyzer.md`
- Runtime đã xác nhận Access Analyzer ACTIVE, nên ticket nào ghi analyzer chưa created cần cập nhật
- Runtime cũng xác nhận audit profile vẫn thiếu `eks:DescribeCluster`, `s3:GetBucketPublicAccessBlock`, `s3:GetEncryptionConfiguration`

Impact:

- Ticket stale làm audit report không phản ánh đúng hiện trạng.
- Khó tracking giữa fixed, pending evidence và still open.

Recommendation:

- Cập nhật ticket theo 3 trạng thái: Done, Pending runtime evidence, Still open.
- Gắn link evidence từ AWS CLI/kubectl/screenshot.

### AUD-10 - Evidence collection runbook chưa đủ cụ thể

Priority: P2
Status: Open
Evidence:

- Có `docs/audit/templates/RUNBOOK_TEMPLATE.md`
- Có `docs/audit/runbooks/README.md`
- Chưa thấy runbook cụ thể cho weekly evidence collection

Impact:

- Thành viên khác có thể thu evidence không đồng nhất.
- Weekly report khó lặp lại và khó audit lại.

Recommendation:

- Tạo runbook cho CloudTrail, AWS Config, IAM Access Analyzer, EKS audit/RBAC, Grafana/OpenSearch evidence.
- Định nghĩa command, expected output, nơi lưu file và owner.

## 6. Cross-pillar observations

Những finding dưới đây được scan để lấy tổng quan. Đây là observation ngoài scope chính của CDO07 Auditability, nhưng có thể ảnh hưởng audit evidence hoặc forensic readiness.

### Security observations

| ID | Finding | Evidence | Priority | Audit note |
| :--- | :--- | :--- | :--- | :--- |
| SEC-01 | Hardcoded credentials/API keys/secret material trong Helm values | `techx-corp-chart/values.yaml` có DB password, `OPENAI_API_KEY`, `SECRET_KEY_BASE`, `POSTGRES_PASSWORD` | P1 | Ảnh hưởng secret evidence và audit readiness |
| SEC-02 | Grafana anonymous Admin và admin password mặc định | `auth.anonymous.enabled`, `org_role: Admin`, `adminPassword: admin` | P1/P0 nếu public | Cần runtime exposure evidence |
| SEC-03 | OpenSearch security plugin bị disable | `DISABLE_SECURITY_PLUGIN=true` | P1/P2 | Ảnh hưởng nếu OpenSearch dùng làm evidence store |
| SEC-04 | Default container securityContext rỗng | `default.securityContext: {}` | P2 | Security hardening observation |
| SEC-05 | Chưa thấy NetworkPolicy, OTel CORS wildcard | Không thấy `NetworkPolicy`; CORS `http://*`, `https://*` | P2 | Network isolation observation |
| SEC-06 | Inter-service gRPC dùng insecure transport | `grpc.WithTransportCredentials(insecure.NewCredentials())` | P2 | Service-to-service security observation |

### Reliability observations

| ID | Finding | Evidence | Priority | Audit note |
| :--- | :--- | :--- | :--- | :--- |
| REL-01 | Default app deployment chỉ có 1 replica | `techx-corp-chart/values.yaml`, `_objects.tpl` | P1 | Có thể ảnh hưởng availability của evidence source |
| REL-02 | App pods chưa có readiness/liveness probe mặc định | `values.yaml`, `_objects.tpl` | P1 | Workload reliability observation |
| REL-03 | Chưa thấy HPA/PDB/topology spread | Negative scan in chart/deploy | P1/P2 | Workload resilience observation |
| REL-04 | PostgreSQL/Valkey/Kafka chưa thấy PVC/persistence trong chart | `values.yaml`, `_objects.tpl` | P1 | Persistence observation |
| REL-05 | Observability data/alerting chưa sẵn sàng cho forensic dài hạn | Alertmanager disabled, PV disabled, Jaeger memory, OpenSearch persistence off | P1 | Ảnh hưởng forensic readiness |
| REL-06 | Checkout side effects không atomic | `techx-corp-platform/src/checkout/main.go` | P1 | Application consistency observation |
| REL-07 | Kafka producer không đợi broker ack | `producer.go` dùng `sarama.NoResponse` | P1/P2 | Event reliability observation |
| REL-08 | Nhiều service thiếu CPU/request | `values.yaml`, `deploy/quota.yaml` | P2 | Capacity/scheduling observation |

### Operational Excellence observations

| ID | Finding | Evidence | Priority | Audit note |
| :--- | :--- | :--- | :--- | :--- |
| OPS-01 | Image `latest` và remote artifact download trong Dockerfile | `frontend-proxy`, `ad`, `fraud-detection`, `kafka` Dockerfile | P2 | Ảnh hưởng supply-chain traceability |
| OPS-02 | ECR mutable tags | `infra/terraform/ecr.tf` | P2 | Ảnh hưởng deployment audit evidence |

Runtime Kubernetes observation bổ sung:

- Namespace `techx-tf4`: tất cả deployments `1/1`, nhưng pod `accounting` có restart cao và event `BackOff`.
- Namespace `techx-observability`: Grafana/Jaeger/Prometheus deployments `1/1`; pod Grafana `4/4 Running` nhưng có restart và event readiness/backoff trước đó.
- Service Grafana/OpenSearch/Prometheus trong `techx-observability` hiện là `ClusterIP`, chưa thấy external service trực tiếp trong output runtime.
- `techx-observability` có `poddisruptionbudget.policy/opensearch-pdb`; `techx-tf4` không thấy HPA/PDB/NetworkPolicy trong command đã chạy.

## 7. Runtime evidence còn cần bổ sung

Đã xác nhận bằng AWS CLI:

- `aws sts get-caller-identity --profile TF4-AuditReadOnlyAndAnalyze`
- `aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze`
- `aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze`
- `aws cloudtrail get-event-selectors --trail-name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze`
- `aws accessanalyzer list-analyzers --profile TF4-AuditReadOnlyAndAnalyze`
- `aws configservice describe-configuration-recorders --profile TF4-AuditReadOnlyAndAnalyze`
- `aws configservice describe-configuration-recorder-status --profile TF4-AuditReadOnlyAndAnalyze`
- `aws configservice describe-delivery-channels --profile TF4-AuditReadOnlyAndAnalyze`
- `aws eks describe-cluster --name techx-tf4-cluster` bằng default profile

Đã xác nhận bằng `kubectl`:

- `kubectl get ns`
- `kubectl -n techx-tf4 get deploy,pod,svc,pvc,events`
- `kubectl -n techx-observability get deploy,pod,svc,pvc,events`
- `kubectl -n techx-tf4 get hpa,pdb,networkpolicy`
- `kubectl -n techx-observability get hpa,pdb,networkpolicy`
- `kubectl auth can-i --list -n techx-tf4`
- `kubectl auth can-i --list -n techx-observability`

Còn cần bổ sung hoặc đang bị blocker:

```bash
aws s3api get-public-access-block --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-encryption --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
aws eks describe-cluster --name techx-tf4-cluster --profile TF4-AuditReadOnlyAndAnalyze
aws budgets describe-budgets --account-id <account-id> --profile TF4-AuditReadOnlyAndAnalyze
```

Các lệnh S3/EKS ở trên đang bị AccessDenied với audit profile và cần bổ sung permission nếu CDO07 phải tự thu evidence bằng profile audit.

## 8. Kết luận

Trạng thái hiện tại của phần CDO07 Auditability: PARTIAL PASS.

Repo đã có nền tảng audit tốt: CODEOWNERS, audit checklist, evidence folder, ADR/runbook/postmortem template, CloudTrail basic và IAM Access Analyzer IaC. Runtime verification xác nhận CloudTrail đang logging, S3 versioning đã bật và Access Analyzer đang ACTIVE.

Các gap P1 vẫn còn rõ sau runtime verification: CloudTrail log validation đang disabled, CloudTrail chưa có data event selector, AWS Config chưa có recorder/delivery channel, EKS API endpoint đang public `0.0.0.0/0`, EKS chưa bật `controllerManager`/`scheduler` logs, và audit profile vẫn thiếu một số quyền đọc evidence quan trọng.

Đây là bản static scan report. Các finding Security/Reliability/Operational Excellence được ghi nhận như observation ngoài scope chính của CDO07 Auditability.
