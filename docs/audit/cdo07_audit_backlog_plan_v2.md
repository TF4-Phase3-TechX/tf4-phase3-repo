# CDO07 Auditability Backlog Plan - Phase 3 v2

Source scan: `docs/audit/cdo07_scan_phase3.md`  
Scope: backlog/plan cho cac finding thuoc tru CDO07 Auditability va Evidence.  
Out of scope: implementation backlog cho Security, Reliability, Cost/Performance, AI. Cac cross-pillar observation chi duoc track o muc evidence/status neu anh huong audit.

## 1. Planning principle

- Backlog phai map ve finding trong file scan.
- Moi backlog item can co action plan va acceptance criteria ro rang.
- Evidence phai duoc luu trong `docs/evidence` hoac linked tu ticket/screenshot/CLI output.
- Neu can team khac xu ly, CDO07 chi track evidence va dependency, khong nhan implementation ngoai tru audit.

## 2. Backlog summary

| Backlog ID | Source finding | Task | Priority | Primary owner | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| CDO07-AUD-01 | AUD-01, AUD-02 | Harden CloudTrail log integrity | P1 | CDO07 + IaC owner | Open |
| CDO07-AUD-02 | AUD-03 | Enable or evidence AWS Config | P1 | CDO07 + IaC owner | Open |
| CDO07-AUD-03 | AUD-04 | Collect IAM Access Analyzer runtime evidence | P1 | CDO07 | Open |
| CDO07-AUD-04 | AUD-02 | Collect CloudTrail and S3 evidence | P1 | CDO07 | Open |
| CDO07-AUD-05 | AUD-05, AUD-06 | Validate EKS audit logging and endpoint exposure | P1/P2 | CDO07 + DevOps | Open |
| CDO07-AUD-06 | AUD-08 | Create weekly audit report artifact | P2 | Member 4 Evidence Collector | Open |
| CDO07-AUD-07 | AUD-09 | Refresh stale audit tickets | P2 | CDO07 | Open |
| CDO07-AUD-08 | AUD-05, AUD-06 | Add ADR for accepted audit trade-offs | P2 | CDO07 + owners | Open |
| CDO07-AUD-09 | AUD-10 | Define weekly evidence collection runbook | P2 | CDO07 | Open |
| CDO07-AUD-10 | Cross-pillar observations | Track cross-pillar evidence dependencies | P2 | CDO07 | Open |

## 3. Detailed plan

### CDO07-AUD-01 - Harden CloudTrail log integrity

Source finding: AUD-01, AUD-02  
Priority: P1  
Primary owner: CDO07 + IaC owner  
Dependency: Terraform/IaC owner  
Status: Open

Plan:

1. Review current `infra/terraform/cloudtrail.tf`.
2. Propose CloudTrail hardening changes:
   - `force_destroy = false` for CloudTrail log bucket.
   - `enable_log_file_validation = true`.
   - KMS CMK for CloudTrail logs if allowed by scope.
   - CloudWatch Logs integration if alerting is required.
3. If a hardening item is deferred, create or update ADR to record reason.
4. Collect post-change evidence using AWS CLI.

Acceptance criteria:

- CloudTrail bucket is not configured for forced deletion, or ADR explains accepted lab trade-off.
- CloudTrail log file validation is enabled, or deferral is documented.
- Evidence command output is stored under `docs/evidence`.
- Related scan finding has updated evidence link.

Evidence commands:

```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-<account-id> --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-02 - Enable or evidence AWS Config

Source finding: AUD-03  
Priority: P1  
Primary owner: CDO07 + IaC owner  
Dependency: Terraform/IaC owner, AWS permission  
Status: Open

Plan:

1. Verify whether AWS Config is enabled at runtime.
2. If not enabled, request or implement Terraform resources:
   - `aws_config_configuration_recorder`
   - `aws_config_delivery_channel`
   - selected `aws_config_config_rule`
3. Start with minimum rules for CloudTrail, S3 public access, EBS encryption, IAM policy.
4. Store CLI output or screenshot as evidence.

Acceptance criteria:

- AWS Config recorder exists and is recording, or blocker is documented.
- Delivery channel exists.
- At least baseline config rules are listed, or ADR explains deferral.
- Evidence is saved under `docs/evidence`.

Evidence commands:

```bash
aws configservice describe-configuration-recorders --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-configuration-recorder-status --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-delivery-channels --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-config-rules --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-03 - Collect IAM Access Analyzer runtime evidence

Source finding: AUD-04  
Priority: P1  
Primary owner: CDO07  
Dependency: AWS read permissions  
Status: Open

Plan:

1. Run Access Analyzer discovery commands.
2. Save analyzer status and findings summary.
3. Compare runtime evidence with `infra/terraform/iam.tf`.
4. Update stale ticket text if it still says analyzer is not created.

Acceptance criteria:

- Analyzer status is captured.
- Findings summary is captured.
- Evidence file exists in `docs/evidence/epic-06-audit`.
- Stale audit ticket is updated or linked to new evidence.

Evidence commands:

```bash
aws accessanalyzer list-analyzers --profile TF4-AuditReadOnlyAndAnalyze
aws accessanalyzer list-findings --analyzer-arn <analyzer-arn> --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-04 - Collect CloudTrail and S3 evidence

Source finding: AUD-02  
Priority: P1  
Primary owner: CDO07  
Dependency: AWS read permissions  
Status: Open

Plan:

1. Capture CloudTrail trail status.
2. Capture CloudTrail event selector configuration.
3. Capture S3 bucket versioning and public access block for log bucket.
4. Capture whether KMS and log validation are enabled.
5. Save output as evidence.

Acceptance criteria:

- CloudTrail is confirmed logging.
- Multi-region and global service event settings are captured.
- S3 versioning evidence is captured.
- Missing hardening items are documented with status.

Evidence commands:

```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-event-selectors --trail-name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-<account-id> --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-public-access-block --bucket tf4-cloudtrail-logs-bucket-<account-id> --profile TF4-AuditReadOnlyAndAnalyze
```

### CDO07-AUD-05 - Validate EKS audit logging and endpoint exposure

Source finding: AUD-05, AUD-06  
Priority: P1/P2  
Primary owner: CDO07 + DevOps  
Dependency: EKS/kubectl read permissions  
Status: Open

Plan:

1. Confirm EKS control-plane logging setting.
2. Confirm public endpoint CIDR setting.
3. Confirm current Kubernetes RBAC capability for audit profile.
4. Capture namespace, pod, service, event and RBAC evidence.
5. If endpoint remains public, request ADR or link existing ADR.

Acceptance criteria:

- EKS audit logging status is captured.
- Endpoint CIDR evidence is captured.
- RBAC `can-i` output is captured.
- Public endpoint trade-off is documented if applicable.

Evidence commands:

```bash
aws eks describe-cluster --name techx-tf4-cluster --profile TF4-AuditReadOnlyAndAnalyze
kubectl get ns
kubectl auth can-i --list -n techx
kubectl auth can-i --list -n techx-observability
kubectl -n techx get deploy,pod,svc,pvc,events
kubectl -n techx-observability get deploy,pod,svc,pvc,events
```

### CDO07-AUD-06 - Create weekly audit report artifact

Source finding: AUD-08  
Priority: P2  
Primary owner: Member 4 Evidence Collector  
Dependency: Evidence from other members  
Status: Open

Plan:

1. Create weekly report file under `docs/audit/weekly/`.
2. Summarize current audit status from scan and runtime evidence.
3. Link each evidence file instead of copying raw output inline.
4. Mark missing evidence and blockers.

Acceptance criteria:

- Weekly report file exists.
- Report includes scope, summary, evidence collected, missing evidence, owner/status and next actions.
- Report links back to scan findings.

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

1. Review audit tickets under `docs/audit/tickets`.
2. Identify stale statements, especially Access Analyzer status.
3. Update ticket status using runtime evidence links.
4. Separate status into Done, Pending runtime evidence, Still open, Blocked.

Acceptance criteria:

- Stale Access Analyzer ticket is corrected.
- Permission blocker ticket reflects current missing permissions only.
- Each updated ticket links to evidence or explains blocker.

Files to review:

```text
docs/audit/tickets/AUDIT-005-enable-access-analyzer.md
docs/audit/tickets/AUDIT-006-request-missing-iam-permissions.md
docs/audit/tickets/AUDIT-007-fix-security-findings.md
```

### CDO07-AUD-08 - Add ADR for accepted audit trade-offs

Source finding: AUD-05, AUD-06  
Priority: P2  
Primary owner: CDO07 + owners  
Dependency: Decision from infra/platform owners  
Status: Open

Plan:

1. List accepted audit trade-offs from scan.
2. Check whether ADR already exists.
3. Add or update ADR only for decisions intentionally accepted.
4. Link ADR from scan or weekly report.

Acceptance criteria:

- Public EKS endpoint decision is documented or remediated.
- Partial EKS control-plane log decision is documented or remediated.
- CloudTrail hardening deferral is documented if not fixed.

Candidate ADR topics:

```text
EKS public endpoint CIDR trade-off
Partial EKS control-plane log types
CloudTrail hardening deferral
```

### CDO07-AUD-09 - Define weekly evidence collection runbook

Source finding: AUD-10  
Priority: P2  
Primary owner: CDO07  
Dependency: None  
Status: Open

Plan:

1. Create a runbook under `docs/audit/runbooks`.
2. Define evidence collection steps for AWS and Kubernetes.
3. Include command, expected output, output path and owner.
4. Define cadence for weekly collection.

Acceptance criteria:

- Runbook exists and is reusable.
- Runbook covers CloudTrail, AWS Config, IAM Access Analyzer, EKS audit/RBAC and observability evidence.
- Runbook defines storage location for evidence.

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

1. Keep cross-pillar findings in scan as observations.
2. For each item that affects audit evidence, request owner evidence.
3. Do not duplicate implementation work owned by other pillars.
4. Link external status/evidence in weekly audit report.

Acceptance criteria:

- Cross-pillar items affecting audit evidence have owner/status.
- Evidence links exist for Grafana/OpenSearch exposure and persistence.
- Evidence links exist for secret handling decision or remediation.
- Evidence links exist for supply-chain traceability decision.

Tracked observation groups:

```text
Security: secret handling, Grafana, OpenSearch, NetworkPolicy, gRPC transport
Reliability: observability persistence, alerting, workload resilience
Operational Excellence: Dockerfile artifact pinning, ECR tag mutability
```

## 4. Next action order

Recommended order:

1. CDO07-AUD-03: collect IAM Access Analyzer evidence because IaC already exists.
2. CDO07-AUD-04: collect CloudTrail/S3 evidence because trail already exists.
3. CDO07-AUD-02: verify AWS Config because it is a P1 audit gap.
4. CDO07-AUD-05: collect EKS audit/RBAC evidence.
5. CDO07-AUD-06: create weekly audit report after evidence is collected.
6. CDO07-AUD-07 to CDO07-AUD-10: clean up ticket/runbook/ADR/cross-pillar tracking.

## 5. Definition of done

This backlog plan is considered done when:

- All P1 auditability evidence is collected or blockers are documented.
- Weekly audit report exists and links to evidence.
- CloudTrail, AWS Config, IAM Access Analyzer and EKS audit status are clear.
- Stale tickets are updated.
- Accepted audit trade-offs have ADRs.
- Cross-pillar observations have owner/status references.
