# CDO07 Auditability Backlog Plan - Phase 3 v2

Scan nguồn: `docs/audit/cdo07_scan_phase3.md`
Phạm vi: backlog/plan cho các finding thuộc trụ CDO07 Auditability và Evidence.
Ngoài phạm vi: implementation backlog cho Security, Reliability, Cost/Performance, AI. Các cross-pillar observation chỉ được CDO07 track ở mức evidence/status nếu có ảnh hưởng đến audit.

## 1. Nguyên tắc planning

- Backlog phải map về finding trong file scan.
- Mỗi backlog item cần có action plan và acceptance criteria rõ ràng.
- Evidence phải được lưu trong `docs/evidence` hoặc link từ ticket/screenshot/CLI output.
- Nếu cần team khác xử lý, CDO07 chỉ track evidence và dependency, không nhận implementation ngoài trụ audit.

## 2. Tổng hợp backlog

| Backlog ID | Source finding | Task | Priority | Primary owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| CDO07-AUD-01 | AUD-01, AUD-02 | Hardening CloudTrail log integrity | P1 | CDO07 + IaC owner | Open |
| CDO07-AUD-02 | AUD-03 | Enable hoặc evidence AWS Config | P1 | CDO07 + IaC owner | Open |
| CDO07-AUD-03 | AUD-04 | Thu thập IAM Access Analyzer runtime evidence | P1 | CDO07 | Open |
| CDO07-AUD-04 | AUD-02 | Thu thập CloudTrail và S3 evidence | P1 | CDO07 | Open |
| CDO07-AUD-05 | AUD-05, AUD-06 | Validate EKS audit logging và endpoint exposure | P1/P2 | CDO07 + DevOps | Open |
| CDO07-AUD-06 | AUD-08 | Tạo weekly audit report artifact | P2 | Member 4 Evidence Collector | Open |
| CDO07-AUD-07 | AUD-09 | Refresh stale audit tickets | P2 | CDO07 | Open |
| CDO07-AUD-08 | AUD-05, AUD-06 | Thêm ADR cho accepted audit trade-offs | P2 | CDO07 + owners | Open |
| CDO07-AUD-09 | AUD-10 | Định nghĩa weekly evidence collection runbook | P2 | CDO07 | Open |
| CDO07-AUD-10 | Cross-pillar observations | Track cross-pillar evidence dependencies | P2 | CDO07 | Open |

## 3. Detailed plan

### CDO07-AUD-01 - Hardening CloudTrail log integrity

Source finding: AUD-01, AUD-02
Priority: P1
Primary owner: CDO07 + IaC owner
Dependency: Terraform/IaC owner
Status: Open

Plan:

1. Review cấu hình hiện tại trong `infra/terraform/cloudtrail.tf`.
2. Đề xuất các thay đổi hardening cho CloudTrail:
   - `force_destroy = false` cho CloudTrail log bucket.
   - `enable_log_file_validation = true`.
   - KMS CMK cho CloudTrail logs nếu scope cho phép.
   - CloudWatch Logs integration nếu cần alert.
3. Nếu một hardening item bị defer, tạo hoặc cập nhật ADR để ghi rõ lý do.
4. Thu thập post-change evidence bằng AWS CLI.

Acceptance criteria:

- CloudTrail bucket không còn cấu hình forced deletion, hoặc ADR giải thích accepted lab trade-off.
- CloudTrail log file validation được bật, hoặc việc defer được document.
- Output evidence command được lưu dưới `docs/evidence`.
- Finding liên quan trong scan có link evidence mới.

Evidence commands:

```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-<account-id> --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-02 - Enable hoặc evidence AWS Config

Source finding: AUD-03
Priority: P1
Primary owner: CDO07 + IaC owner
Dependency: Terraform/IaC owner, AWS permission
Status: Open

Plan:

1. Verify AWS Config đã được bật ở runtime hay chưa.
2. Nếu chưa bật, request hoặc implement Terraform resources:
   - `aws_config_configuration_recorder`
   - `aws_config_delivery_channel`
   - selected `aws_config_config_rule`
3. Bắt đầu với minimum rules cho CloudTrail, S3 public access, EBS encryption, IAM policy.
4. Lưu CLI output hoặc screenshot làm evidence.

Acceptance criteria:

- AWS Config recorder tồn tại và đang recording, hoặc blocker được document.
- Delivery channel tồn tại.
- Có ít nhất baseline config rules được list, hoặc ADR giải thích defer.
- Evidence được lưu dưới `docs/evidence`.

Evidence commands:

```bash
aws configservice describe-configuration-recorders --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-configuration-recorder-status --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-delivery-channels --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-config-rules --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-03 - Thu thập IAM Access Analyzer runtime evidence

Source finding: AUD-04
Priority: P1
Primary owner: CDO07
Dependency: AWS read permissions
Status: Open

Plan:

1. Chạy các command discovery cho Access Analyzer.
2. Lưu analyzer status và findings summary.
3. So sánh runtime evidence với `infra/terraform/iam.tf`.
4. Cập nhật stale ticket nếu ticket vẫn ghi analyzer chưa được tạo.

Acceptance criteria:

- Analyzer status được capture.
- Findings summary được capture.
- Evidence file tồn tại trong `docs/evidence/epic-06-audit`.
- Stale audit ticket được cập nhật hoặc link tới evidence mới.

Evidence commands:

```bash
aws accessanalyzer list-analyzers --profile TF4-AuditReadOnlyAndAnalyze
aws accessanalyzer list-findings --analyzer-arn <analyzer-arn> --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-04 - Thu thập CloudTrail và S3 evidence

Source finding: AUD-02
Priority: P1
Primary owner: CDO07
Dependency: AWS read permissions
Status: Open

Plan:

1. Capture CloudTrail trail status.
2. Capture CloudTrail event selector configuration.
3. Capture S3 bucket versioning và public access block cho log bucket.
4. Capture trạng thái KMS và log validation.
5. Lưu output làm evidence.

Acceptance criteria:

- CloudTrail được xác nhận đang logging.
- Multi-region và global service event settings được capture.
- S3 versioning evidence được capture.
- Các hardening item còn thiếu được document kèm status.

Evidence commands:

```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-event-selectors --trail-name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-<account-id> --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-public-access-block --bucket tf4-cloudtrail-logs-bucket-<account-id> --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-05 - Validate EKS audit logging và endpoint exposure

Source finding: AUD-05, AUD-06
Priority: P1/P2
Primary owner: CDO07 + DevOps
Dependency: EKS/kubectl read permissions
Status: Open

Plan:

1. Confirm EKS control-plane logging setting.
2. Confirm public endpoint CIDR setting.
3. Confirm Kubernetes RBAC capability hiện tại cho audit profile.
4. Capture namespace, pod, service, event và RBAC evidence.
5. Nếu endpoint vẫn public, request ADR hoặc link ADR hiện có.

Acceptance criteria:

- EKS audit logging status được capture.
- Endpoint CIDR evidence được capture.
- RBAC `can-i` output được capture.
- Public endpoint trade-off được document nếu applicable.

Evidence commands:

```bash
aws eks describe-cluster --name techx-tf4-cluster --profile TF4-AuditReadOnlyAndAnalyze
kubectl get ns
kubectl auth can-i --list -n techx
kubectl auth can-i --list -n techx-observability
kubectl -n techx get deploy,pod,svc,pvc,events
kubectl -n techx-observability get deploy,pod,svc,pvc,events
```

### CDO07-AUD-06 - Tạo weekly audit report artifact

Source finding: AUD-08
Priority: P2
Primary owner: Member 4 Evidence Collector
Dependency: Evidence từ các thành viên khác
Status: Open

Plan:

1. Tạo weekly report file dưới `docs/audit/weekly/`.
2. Tóm tắt current audit status từ scan và runtime evidence.
3. Link từng evidence file thay vì copy toàn bộ raw output inline.
4. Đánh dấu missing evidence và blockers.

Acceptance criteria:

- Weekly report file tồn tại.
- Report có scope, summary, evidence collected, missing evidence, owner/status và next actions.
- Report link ngược về các scan findings.

Suggested path:

```text
docs/audit/weekly/weekly-audit-report-YYYY-MM-DD.md
```

### CDO07-AUD-07 - Refresh stale audit tickets

Source finding: AUD-09
Priority: P2
Primary owner: CDO07
Dependency: Runtime evidence
Status: Open

Plan:

1. Review audit tickets dưới `docs/audit/tickets`.
2. Xác định các statement đã stale, đặc biệt là Access Analyzer status.
3. Cập nhật ticket status bằng runtime evidence links.
4. Tách status thành Done, Pending runtime evidence, Still open, Blocked.

Acceptance criteria:

- Stale Access Analyzer ticket được sửa.
- Permission blocker ticket chỉ phản ánh các permission còn thiếu hiện tại.
- Mỗi ticket được cập nhật có link evidence hoặc giải thích blocker.

Files to review:

```text
docs/audit/tickets/AUDIT-005-enable-access-analyzer.md
docs/audit/tickets/AUDIT-006-request-missing-iam-permissions.md
docs/audit/tickets/AUDIT-007-fix-security-findings.md
```

### CDO07-AUD-08 - Thêm ADR cho accepted audit trade-offs

Source finding: AUD-05, AUD-06
Priority: P2
Primary owner: CDO07 + owners
Dependency: Decision từ infra/platform owners
Status: Open

Plan:

1. Liệt kê các accepted audit trade-offs từ scan.
2. Kiểm tra ADR đã tồn tại hay chưa.
3. Chỉ thêm hoặc cập nhật ADR cho các decision được chủ động chấp nhận.
4. Link ADR từ scan hoặc weekly report.

Acceptance criteria:

- Public EKS endpoint decision được document hoặc remediated.
- Partial EKS control-plane log decision được document hoặc remediated.
- CloudTrail hardening deferral được document nếu chưa fix.

Candidate ADR topics:

```text
EKS public endpoint CIDR trade-off
Partial EKS control-plane log types
CloudTrail hardening deferral
```

### CDO07-AUD-09 - Định nghĩa weekly evidence collection runbook

Source finding: AUD-10
Priority: P2
Primary owner: CDO07
Dependency: None
Status: Open

Plan:

1. Tạo runbook dưới `docs/audit/runbooks`.
2. Định nghĩa evidence collection steps cho AWS và Kubernetes.
3. Bao gồm command, expected output, output path và owner.
4. Định nghĩa cadence cho weekly collection.

Acceptance criteria:

- Runbook tồn tại và có thể tái sử dụng.
- Runbook cover CloudTrail, AWS Config, IAM Access Analyzer, EKS audit/RBAC và observability evidence.
- Runbook định nghĩa storage location cho evidence.

Suggested path:

```text
docs/audit/runbooks/weekly-evidence-collection.md
```

### CDO07-AUD-10 - Track cross-pillar evidence dependencies

Source finding: Cross-pillar observations
Priority: P2
Primary owner: CDO07
Dependency: Security/Reliability/Platform owners
Status: Open

Plan:

1. Giữ cross-pillar findings trong scan dưới dạng observations.
2. Với mỗi item ảnh hưởng audit evidence, request owner evidence.
3. Không duplicate implementation work thuộc ownership của pillar khác.
4. Link external status/evidence trong weekly audit report.

Acceptance criteria:

- Cross-pillar items ảnh hưởng audit evidence có owner/status.
- Có evidence links cho Grafana/OpenSearch exposure và persistence.
- Có evidence links cho secret handling decision hoặc remediation.
- Có evidence links cho supply-chain traceability decision.

Tracked observation groups:

```text
Security: secret handling, Grafana, OpenSearch, NetworkPolicy, gRPC transport
Reliability: observability persistence, alerting, workload resilience
Operational Excellence: Dockerfile artifact pinning, ECR tag mutability
```

## 4. Thứ tự next action đề xuất

Recommended order:

1. CDO07-AUD-03: thu thập IAM Access Analyzer evidence vì IaC đã tồn tại.
2. CDO07-AUD-04: thu thập CloudTrail/S3 evidence vì trail đã tồn tại.
3. CDO07-AUD-02: verify AWS Config vì đây là P1 audit gap.
4. CDO07-AUD-05: thu thập EKS audit/RBAC evidence.
5. CDO07-AUD-06: tạo weekly audit report sau khi đã có evidence.
6. CDO07-AUD-07 đến CDO07-AUD-10: cleanup ticket/runbook/ADR/cross-pillar tracking.

## 5. Definition of done

Backlog plan này được xem là done khi:

- Tất cả P1 auditability evidence đã được thu thập hoặc blocker đã được document.
- Weekly audit report tồn tại và link đến evidence.
- CloudTrail, AWS Config, IAM Access Analyzer và EKS audit status đã rõ ràng.
- Stale tickets đã được cập nhật.
- Accepted audit trade-offs có ADR.
- Cross-pillar observations có owner/status references.
