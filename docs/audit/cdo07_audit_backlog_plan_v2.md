# CDO07 Auditability Backlog Plan - Phase 3 v2

Scan nguồn: `docs/audit/cdo07_scan_phase3.md`
Phạm vi: backlog/plan cho các finding thuộc trụ CDO07 Auditability và Evidence.
Ngoài phạm vi: implementation backlog cho Security, Reliability, Cost/Performance, AI. Các cross-pillar observation chỉ được CDO07 track ở mức evidence/status nếu có ảnh hưởng đến audit.

## 1. Nguyên tắc planning

- Backlog phải map về finding trong file scan.
- Mỗi backlog item phải có hiện trạng, lý do, chi phí/impact, plan xử lý, evidence cần thu và acceptance criteria.
- Evidence phải được lưu trong `docs/evidence` hoặc link từ ticket/screenshot/CLI output.
- Nếu cần team khác xử lý, CDO07 chỉ track evidence và dependency, không nhận implementation ngoài trụ audit.
- Chi phí trong file này gồm cả chi phí vận hành AWS, effort thực hiện và rủi ro nếu không làm.
- Nếu một P1 item được defer bằng ADR, ADR phải có owner approve, review date, deadline xử lý lại và compensating controls. Không dùng ADR như trạng thái "done" nếu thiếu các trường này.
- `Assignee đề xuất` là người/team nên nhận việc khi tạo Jira; nếu chưa biết tên cụ thể thì phải xác nhận trước khi đưa vào sprint.

## 2. Quy ước chi phí/impact

| Mức | Ý nghĩa |
| :--- | :--- |
| Low | Chủ yếu là effort tài liệu/CLI; chi phí AWS không đáng kể |
| Medium | Có thay đổi IaC hoặc quyền; có thể phát sinh chi phí log/storage/rule evaluation nhỏ đến vừa |
| High | Có khả năng tăng chi phí vận hành rõ rệt hoặc ảnh hưởng security/compliance nếu cấu hình sai |

## 3. Tổng hợp backlog

| Backlog ID | Source finding | Task | Priority | Owner chính | Assignee đề xuất | Target | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| CDO07-AUD-01 | AUD-01, AUD-02 | Hardening CloudTrail log integrity | P1 | CDO07 + IaC owner | IaC owner TBD + CDO07 evidence collector | Sprint hiện tại | Open |
| CDO07-AUD-02 | AUD-03 | Enable AWS Config recorder/delivery channel | P1 | CDO07 + IaC owner | IaC owner TBD | Sprint hiện tại | Open - runtime gap confirmed |
| CDO07-AUD-03 | AUD-04 | Lưu Access Analyzer evidence và review active findings | P1 | CDO07 | Member 4 Evidence Collector | Sprint hiện tại | Runtime confirmed / evidence file pending |
| CDO07-AUD-04 | AUD-02 | Thu thập CloudTrail và S3 evidence | P1 | CDO07 | Member 4 Evidence Collector | Sprint hiện tại | Partially confirmed / permission blocked |
| CDO07-AUD-05 | AUD-05, AUD-06; related proposal AUDIT-001 | Validate EKS Control Plane Logging và endpoint exposure | P1/P2 | CDO07 + DevOps | DevOps owner TBD + Member 4 | Sprint hiện tại | Runtime confirmed / proposal not implemented / audit profile blocked |
| CDO07-AUD-06 | AUD-08 | Tạo weekly audit report artifact | P2 | Member 4 Evidence Collector | Member 4 Evidence Collector | Hằng tuần | Open |
| CDO07-AUD-08 | AUD-05, AUD-06 | Thêm ADR cho accepted audit trade-offs | P2 | CDO07 + owners | Decision owner TBD | Trước nghiệm thu | Open |
| CDO07-AUD-09 | AUD-10 | Định nghĩa weekly evidence collection runbook | P2 | CDO07 | Member 4 Evidence Collector | Sprint hiện tại | Open |
| CDO07-AUD-11 | Runtime permission blockers | Request missing audit evidence permissions | P1/P2 | CDO07 + IAM owner | IAM/SSO owner TBD | Sprint hiện tại | Open |

## 4. Chi tiết backlog

### CDO07-AUD-01 - Hardening CloudTrail log integrity

Source finding: AUD-01, AUD-02
Priority: P1
Owner chính: CDO07 + IaC owner
Dependency: Terraform/IaC owner
Status: Open

Hiện trạng:

- Terraform có CloudTrail `tf4-general-cloudtrail`.
- Runtime xác nhận CloudTrail đang logging, multi-region, S3 versioning enabled.
- Runtime xác nhận `LogFileValidationEnabled=false`.
- Static scan thấy CloudTrail log bucket có `force_destroy = true`.
- Event selector hiện chỉ có management events, `DataResources=[]`.

Lý do cần làm:

- Audit evidence cần có tính toàn vẹn và khó bị xóa/sửa.
- Nếu log file validation disabled, việc chứng minh log không bị thay đổi sẽ yếu.
- Nếu bucket vẫn `force_destroy = true`, log bucket có thể bị xóa khi destroy hạ tầng.
- Nếu không có data events, một số hành vi data-plane quan trọng không được ghi nhận.

Chi phí/impact:

- Mức chi phí: Medium.
- Cost drivers: CloudWatch Logs ingestion/storage nếu bật CloudTrail to CloudWatch Logs, KMS request nếu dùng CMK, CloudTrail data events nếu bật cho S3/resource quan trọng.
- Bật log file validation gần như không đáng kể; data events có thể tăng chi phí theo số lượng object/API calls.
- Effort: Medium, cần IaC owner review và apply Terraform.
- Rủi ro nếu không làm: High, audit evidence thiếu tính toàn vẹn và retention yếu.

Plan:

1. Review `infra/terraform/cloudtrail.tf`.
2. Đề xuất thay đổi:
   - `force_destroy = false` cho CloudTrail log bucket.
   - `enable_log_file_validation = true`.
   - KMS CMK cho CloudTrail logs nếu scope cho phép.
   - CloudWatch Logs integration nếu cần alert.
   - Data event selector cho S3 bucket quan trọng nếu được chấp nhận chi phí.
3. Ước lượng thêm chi phí cho CloudWatch Logs/data events trước khi apply.
4. Nếu item nào defer vì cost/lab scope, tạo ADR ghi rõ lý do.
5. Sau thay đổi, chạy lại AWS CLI và lưu evidence.

Evidence cần thu:

```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-event-selectors --trail-name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
```

Acceptance criteria:

- CloudTrail log file validation được bật, hoặc ADR defer có owner approve, review date, deadline và compensating control.
- CloudTrail bucket không còn forced deletion, hoặc ADR defer có owner approve, review date, deadline và compensating control.
- Data event selector được cấu hình cho resource quan trọng, hoặc có cost note + ADR defer đầy đủ owner/review/deadline.
- KMS/CWL decision được ghi rõ: enabled, deferred with ADR, hoặc out-of-scope có lý do.
- Evidence output được lưu dưới `docs/evidence`.

### CDO07-AUD-02 - Enable AWS Config recorder/delivery channel

Source finding: AUD-03
Priority: P1
Owner chính: CDO07 + IaC owner
Dependency: Terraform/IaC owner, AWS permission
Status: Open - runtime gap confirmed

Hiện trạng:

- Static scan chưa thấy Terraform resources cho AWS Config.
- Runtime xác nhận:
  - `ConfigurationRecorders=[]`
  - `ConfigurationRecordersStatus=[]`
  - `DeliveryChannels=[]`

Lý do cần làm:

- AWS Config là control chính để audit drift/change history của tài nguyên AWS.
- Không có recorder thì không có timeline cấu hình tài nguyên để phục vụ compliance evidence.
- Không có delivery channel thì không có nơi lưu configuration snapshots/history.

Chi phí/impact:

- Mức chi phí: Medium/High.
- Cost drivers: số lượng configuration items recorded, số managed/custom rules, số lần rule evaluation, S3 storage cho snapshots/history.
- Cần giới hạn scope resource types/rules ban đầu để tránh bật quá rộng trong môi trường lab.
- Effort: Medium/High, cần IaC owner thêm recorder, bucket/delivery channel, role và baseline rules.
- Rủi ro nếu không làm: High, thiếu evidence về drift và thay đổi cấu hình.

Plan:

1. Xác nhận scope resource types cần record để kiểm soát chi phí.
2. Implement hoặc request Terraform resources:
   - `aws_config_configuration_recorder`
   - `aws_config_delivery_channel`
   - IAM role cho AWS Config
   - selected `aws_config_config_rule`
3. Baseline rules đề xuất:
   - CloudTrail enabled.
   - S3 bucket public access.
   - EBS encryption.
   - IAM policy/access key hygiene nếu phù hợp.
4. Chạy Terraform plan/apply qua owner phù hợp.
5. Chạy lại AWS CLI, lưu evidence.

Evidence cần thu:

```bash
aws configservice describe-configuration-recorders --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-configuration-recorder-status --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-delivery-channels --profile TF4-AuditReadOnlyAndAnalyze
aws configservice describe-config-rules --profile TF4-AuditReadOnlyAndAnalyze
```

Acceptance criteria:

- AWS Config recorder tồn tại và đang recording.
- Delivery channel tồn tại.
- Có baseline config rules cho CloudTrail/S3/EBS/IAM hoặc ADR defer có owner approve, review date, deadline và cost note.
- Cost driver/scope resource types được ghi trong PR, ADR hoặc weekly report.
- Evidence được lưu dưới `docs/evidence`.

### CDO07-AUD-03 - Lưu Access Analyzer evidence và review active findings

Source finding: AUD-04
Priority: P1
Owner chính: CDO07
Dependency: AWS read permissions
Status: Runtime confirmed / evidence file pending

Hiện trạng:

- Terraform có `aws_accessanalyzer_analyzer.main`.
- Runtime xác nhận analyzer `tf4-iam-analyzer` status `ACTIVE`.
- Runtime list findings trả về nhiều active findings cho IAM roles.
- Một số audit ticket vẫn có dấu hiệu stale khi ghi analyzer chưa created.

Lý do cần làm:

- Access Analyzer chỉ có giá trị audit khi findings được review và phân loại.
- Nếu ticket còn stale, báo cáo audit sẽ sai trạng thái.
- Active findings cần phân biệt expected access, needs-action hoặc accepted risk.

Chi phí/impact:

- Chi phí AWS: Access Analyzer account-level thường không phải điểm chi phí lớn cho scope này.
- Effort: Low/Medium, chủ yếu là thu evidence và review findings.
- Rủi ro nếu không làm: Medium/High, có thể bỏ sót external/shared access risk hoặc báo cáo sai trạng thái.

Plan:

1. Lưu analyzer status vào evidence file.
2. Lưu findings summary vào evidence file.
3. Phân loại active findings:
   - expected access
   - needs-action
   - false positive / accepted
4. Cập nhật audit ticket stale.
5. Link evidence từ backlog/weekly report.

Evidence cần thu:

```bash
aws accessanalyzer list-analyzers --profile TF4-AuditReadOnlyAndAnalyze
ANALYZER_ARN=$(aws accessanalyzer list-analyzers --profile TF4-AuditReadOnlyAndAnalyze --query 'analyzers[?name==`tf4-iam-analyzer`].arn | [0]' --output text)
aws accessanalyzer list-findings --analyzer-arn "$ANALYZER_ARN" --profile TF4-AuditReadOnlyAndAnalyze
```

Acceptance criteria:

- Analyzer status `ACTIVE` được lưu vào evidence file.
- Findings summary được lưu và có phân loại sơ bộ.
- Ticket stale về Access Analyzer được cập nhật.
- Findings needs-action có owner hoặc status rõ ràng.

### CDO07-AUD-04 - Thu thập CloudTrail và S3 evidence

Source finding: AUD-02
Priority: P1
Owner chính: CDO07
Dependency: AWS read permissions
Status: Partially confirmed / permission blocked

Hiện trạng:

- Runtime đã xác nhận:
  - CloudTrail `tf4-general-cloudtrail` đang logging.
  - CloudTrail multi-region enabled.
  - S3 bucket `tf4-cloudtrail-logs-bucket-511825856493` versioning `Enabled`.
  - `LogFileValidationEnabled=false`.
  - Event selector chỉ có management events, `DataResources=[]`.
- Audit profile bị deny:
  - `s3:GetBucketPublicAccessBlock`
  - `s3:GetEncryptionConfiguration`

Lý do cần làm:

- Member 4 cần evidence rõ ràng cho weekly report.
- S3 public access block và encryption là bằng chứng quan trọng cho audit log bucket.
- Nếu audit profile không tự đọc được metadata này, quy trình evidence collection không độc lập.

Chi phí/impact:

- Mức chi phí: Low.
- Cost drivers: read-only CLI gần như không đáng kể; chi phí đáng kể chỉ xuất hiện nếu remediation bật thêm log/data events/KMS/CWL thuộc CDO07-AUD-01.
- Effort: Low nếu có quyền; Medium nếu phải xin quyền.
- Rủi ro nếu không làm: Medium, thiếu bằng chứng bucket hardening và phải phụ thuộc owner khác.

Plan:

1. Lưu output CloudTrail đã xác nhận vào `docs/evidence`.
2. Lưu S3 versioning evidence vào `docs/evidence`.
3. Ghi rõ permission blocker cho S3 public access block/encryption.
4. Sau khi quyền được cấp, chạy lại lệnh S3 metadata.
5. Update weekly report với status confirmed/blocked.

Evidence cần thu:

```bash
aws cloudtrail describe-trails --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-trail-status --name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws cloudtrail get-event-selectors --trail-name tf4-general-cloudtrail --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-versioning --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-public-access-block --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-encryption --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
```

Acceptance criteria:

- CloudTrail status evidence được lưu.
- S3 versioning evidence được lưu.
- S3 public access block/encryption được capture hoặc blocker được document.
- Weekly report có link đến evidence.

### CDO07-AUD-05 - Validate EKS Control Plane Logging và endpoint exposure

Source finding: AUD-05, AUD-06
Related proposal ticket: `docs/audit/tickets/AUDIT-001-enable-eks-logs.md`
Priority: P1/P2
Owner chính: CDO07 + DevOps
Dependency: EKS/kubectl read permissions
Status: Runtime confirmed / proposal not implemented / audit profile blocked

Hiện trạng:

- Runtime bằng default profile xác nhận:
  - Cluster `techx-tf4-cluster` ACTIVE, version `1.34`.
  - `endpointPublicAccess=true`.
  - `endpointPrivateAccess=true`.
  - `publicAccessCidrs=["0.0.0.0/0"]`.
  - `api`, `audit`, `authenticator` enabled.
  - `controllerManager`, `scheduler` disabled.
- Audit profile `TF4-AuditReadOnlyAndAnalyze` bị deny `eks:DescribeCluster`.
- `kubectl` context hiện tại: `techx-tf4-base`.
- Namespace runtime đúng: `techx-tf4`, `techx-observability`.
- Ticket `AUDIT-001-enable-eks-logs.md` hiện chỉ là ticket đề xuất bật đủ EKS Control Plane Logging, cấu hình retention và long-term storage sang S3. Chưa có evidence cho thấy ticket này đã được triển khai.
- Chưa xác nhận được CloudWatch Log Group retention đang là 14/30 ngày.
- Chưa xác nhận được long-term export/sync sang S3 bucket `tf4-cdo07-audit-log` đã tồn tại hoặc đang chạy.

Lý do cần làm:

- Public endpoint `0.0.0.0/0` là audit risk cần có remediation hoặc ADR.
- EKS Control Plane Logging hiện mới bật 3/5 luồng log; thiếu `controllerManager` và `scheduler` có thể làm thiếu evidence cho controller/scheduler incident.
- CDO07 cần tự verify EKS bằng audit profile, không phụ thuộc fallback default profile.
- `AUDIT-001` là proposal/remediation ticket cần được track riêng; không được tính là control đã pass khi chưa có runtime evidence.

Chi phí/impact:

- Mức chi phí: Medium.
- Hiện trạng đang bật 3/5 log types, nên chi phí hiện tại thấp hơn kịch bản bật đủ 5 log types nhưng chưa có số liệu CloudWatch ingestion thực tế.
- Cost drivers nếu thực hiện proposal: CloudWatch Logs ingestion/storage cho 5 luồng EKS Control Plane Logs, retention policy, số lượng control-plane events, export/long-term storage sang S3.
- Ước tính cho phương án đề xuất trong `AUDIT-001-enable-eks-logs.md`:
  - Idle baseline: khoảng **47 MB/ngày**, ingestion khoảng **$0.023/ngày**, tương đương **~$0.70/tháng**.
  - Dev/config change: khoảng **500 MB/ngày**, ingestion khoảng **$0.25/ngày**, tương đương **~$7.50/tháng**.
  - Load test/peak: khoảng **3-5 GB/ngày**, ingestion khoảng **$1.50-$2.50/ngày**, tương đương **~$45-$75/tháng** nếu kéo dài 30 ngày.
- Retention khuyến nghị trong ticket đề xuất: **14 ngày**, tối đa **30 ngày** để tránh CloudWatch Logs `Never Expire`.
- Long-term storage đề xuất: export/sync sang S3 bucket `tf4-cdo07-audit-log`; lifecycle sang Glacier Deep Archive giúp giảm chi phí lưu trữ dài hạn so với giữ toàn bộ trên CloudWatch Logs.
- Effort: Medium, cần DevOps/IaC owner review endpoint CIDR và log types.
- Rủi ro nếu không làm: Medium/High, exposure rộng và thiếu control-plane forensic evidence.

Plan:

1. Ghi evidence runtime hiện tại vào `docs/evidence`.
2. Request quyền `eks:DescribeCluster` cho audit profile hoặc document blocker.
3. Bật EKS Control Plane Logging theo proposal trong `AUDIT-001-enable-eks-logs.md`:
   - Bật đủ 5 log types: `api`, `audit`, `authenticator`, `controllerManager`, `scheduler`.
   - Xác nhận CloudWatch Log Group `/aws/eks/techx-tf4-cluster/cluster`.
   - Cấu hình retention 14 ngày, tối đa 30 ngày.
   - Thiết lập hoặc document plan long-term storage/export sang S3 `tf4-cdo07-audit-log`.
4. Review endpoint CIDR:
   - Nếu có VPN/static IP, đề xuất thu hẹp CIDR.
   - Nếu giữ public vì lab, tạo ADR.
5. Ghi chi phí estimate proposal vào weekly report theo 3 kịch bản trong `AUDIT-001`, kèm ghi chú "chưa triển khai".
6. Lưu `kubectl auth can-i` và workload status theo namespace đúng.

Evidence cần thu:

```bash
aws eks describe-cluster --name techx-tf4-cluster --profile TF4-AuditReadOnlyAndAnalyze
aws logs describe-log-groups --log-group-name-prefix /aws/eks/techx-tf4-cluster/cluster --profile TF4-AuditReadOnlyAndAnalyze
kubectl get ns
kubectl auth can-i --list -n techx-tf4
kubectl auth can-i --list -n techx-observability
kubectl -n techx-tf4 get deploy,pod,svc,pvc,events
kubectl -n techx-observability get deploy,pod,svc,pvc,events
```

Acceptance criteria:

- EKS Control Plane Logging status được lưu vào evidence.
- Current state ghi rõ: runtime mới bật 3/5 log types và `AUDIT-001` chưa triển khai.
- Remediation/proposal state ghi rõ: bật đủ 5 log types `api`, `audit`, `authenticator`, `controllerManager`, `scheduler`, hoặc có ADR defer đầy đủ owner/review/deadline.
- CloudWatch Log Group `/aws/eks/techx-tf4-cluster/cluster` tồn tại và được capture evidence.
- Log group retention được xác nhận; nếu chưa phải 14/30 ngày thì tạo backlog/remediation hoặc ADR defer.
- Long-term storage sang S3 `tf4-cdo07-audit-log` được xác nhận; nếu chưa có thì giữ trạng thái proposal/chưa triển khai.
- Chi phí proposal được ghi vào weekly report theo 3 mức: **~$0.70/tháng**, **~$7.50/tháng**, **~$45-$75/tháng** tùy kịch bản vận hành, kèm ghi chú đây là estimate cho phương án bật đủ logs, không phải chi phí đã phát sinh.
- Audit profile có quyền `eks:DescribeCluster` hoặc blocker được document.
- Public endpoint có remediation plan hoặc ADR defer có owner approve, review date, deadline và compensating control.
- EKS partial logging có remediation plan hoặc ADR/cost note đầy đủ owner/review/deadline.

### CDO07-AUD-06 - Tạo weekly audit report artifact

Source finding: AUD-08
Priority: P2
Owner chính: Member 4 Evidence Collector
Dependency: Evidence từ các thành viên khác
Status: Open

Hiện trạng:

- Có `docs/audit` và `docs/evidence`.
- Chưa thấy weekly audit report riêng.
- Scan hiện đã có runtime evidence đủ để tạo bản weekly đầu tiên.

Lý do cần làm:

- Member 4 có trách nhiệm tổng hợp evidence thành báo cáo hằng tuần.
- Nếu không có weekly report, evidence bị phân tán và khó nghiệm thu.
- Report là nơi thể hiện status, blocker và owner một cách rõ ràng.

Chi phí/impact:

- Chi phí AWS: không đáng kể.
- Effort: Low/Medium, chủ yếu tổng hợp link evidence và status.
- Rủi ro nếu không làm: Medium, thiếu deliverable đúng role Evidence Collector.

Plan:

1. Tạo weekly report dưới `docs/audit/weekly/`.
2. Tổng hợp runtime evidence mới nhất:
   - CloudTrail logging, S3 versioning enabled.
   - CloudTrail log validation disabled và chưa có data events.
   - AWS Config absent.
   - Access Analyzer ACTIVE nhưng có active findings cần review.
   - EKS endpoint public `0.0.0.0/0`, EKS logs partial.
   - `accounting` restart cao, Grafana có restart/readiness/backoff events.
3. Link từng evidence file thay vì copy toàn bộ raw output inline.
4. Đánh dấu missing evidence và blockers.

Acceptance criteria:

- Weekly report file tồn tại.
- Report có scope, summary, evidence collected, missing evidence, owner/status và next actions.
- Report link ngược về scan findings.
- Report ghi rõ runtime profile/context đã dùng.

Suggested path:

```text
docs/audit/weekly/weekly-audit-report-YYYY-MM-DD.md
```

### CDO07-AUD-08 - Thêm ADR cho accepted audit trade-offs

Source finding: AUD-05, AUD-06
Priority: P2
Owner chính: CDO07 + owners
Dependency: Decision từ infra/platform owners
Status: Open

Hiện trạng:

- Runtime xác nhận một số trade-off/risk:
  - EKS public endpoint `0.0.0.0/0`.
  - EKS chỉ bật `api`, `audit`, `authenticator`.
  - CloudTrail log validation disabled.
  - AWS Config chưa bật.
  - Audit profile thiếu một số quyền đọc evidence.

Lý do cần làm:

- Nếu team quyết định chưa fix ngay, cần ADR để giải thích lý do, thời hạn và compensating controls.
- ADR giúp reviewer phân biệt accepted risk với overlooked gap.

Chi phí/impact:

- Chi phí AWS: không đáng kể nếu chỉ viết ADR.
- Effort: Low/Medium, cần xác nhận decision từ owner liên quan.
- Rủi ro nếu không làm: Medium, audit gap bị xem như thiếu kiểm soát hoặc thiếu ownership.

Plan:

1. Liệt kê accepted audit trade-offs từ scan.
2. Kiểm tra ADR đã tồn tại hay chưa.
3. Chỉ thêm/cập nhật ADR cho decision được chủ động chấp nhận.
4. ADR phải có:
   - context
   - decision
   - consequences
   - owner
   - review date
   - compensating controls
5. Link ADR từ scan hoặc weekly report.

Acceptance criteria:

- Public EKS endpoint decision được document hoặc remediated.
- Partial EKS control-plane log decision được document hoặc remediated.
- CloudTrail hardening deferral được document nếu chưa fix.
- Permission boundary cho audit evidence được document hoặc remediated.

Candidate ADR topics:

```text
EKS public endpoint CIDR trade-off
Partial EKS control-plane log types
CloudTrail hardening deferral
Audit evidence permission boundary
AWS Config enablement deferral
```

### CDO07-AUD-09 - Định nghĩa weekly evidence collection runbook

Source finding: AUD-10
Priority: P2
Owner chính: CDO07
Dependency: None
Status: Open

Hiện trạng:

- Có runbook template và `docs/audit/runbooks/README.md`.
- Chưa thấy runbook cụ thể cho weekly evidence collection.
- Runtime scan đã cho thấy cần thống nhất profile, fallback profile, namespace và output location.

Lý do cần làm:

- Evidence collection phải lặp lại được hằng tuần.
- Nếu mỗi thành viên chạy lệnh khác nhau, output khó so sánh và khó audit lại.
- Runbook giúp Member 4 gom evidence nhanh hơn.

Chi phí/impact:

- Chi phí AWS: không đáng kể.
- Effort: Low/Medium, chủ yếu chuẩn hóa command và nơi lưu output.
- Rủi ro nếu không làm: Medium, evidence thiếu nhất quán và khó nghiệm thu.

Plan:

1. Tạo runbook dưới `docs/audit/runbooks`.
2. Định nghĩa evidence collection steps cho AWS và Kubernetes.
3. Ghi rõ profile/context phải dùng:
   - `TF4-AuditReadOnlyAndAnalyze`
   - default fallback nếu audit profile bị deny
   - `techx-tf4-base`
4. Ghi rõ namespace đúng:
   - `techx-tf4`
   - `techx-observability`
5. Định nghĩa output path, naming convention và cadence weekly.

Acceptance criteria:

- Runbook tồn tại và có thể tái sử dụng.
- Runbook cover CloudTrail, AWS Config, IAM Access Analyzer, EKS audit/RBAC và observability evidence.
- Runbook định nghĩa storage location cho evidence.
- Runbook ghi rõ blocker handling khi gặp AccessDenied.

Suggested path:

```text
docs/audit/runbooks/weekly-evidence-collection.md
```

### CDO07-AUD-11 - Request missing audit evidence permissions

Source finding: Runtime permission blockers
Priority: P1/P2
Owner chính: CDO07 + IAM owner
Dependency: IAM/SSO permission set owner
Status: Open

Hiện trạng:

- Profile chính `TF4-AuditReadOnlyAndAnalyze` đủ quyền hơn `TF4-BaseReadOnly` cho nhiều audit commands.
- Tuy nhiên runtime xác nhận audit profile vẫn bị deny:
  - `eks:DescribeCluster`
  - `s3:GetBucketPublicAccessBlock`
  - `s3:GetEncryptionConfiguration`
- Default profile được dùng fallback cho EKS describe cluster, nhưng đây không nên là quy trình chính của Evidence Collector.

Lý do cần làm:

- Evidence Collector cần tự thu evidence bằng audit profile.
- Nếu phải fallback sang profile khác, audit process kém nhất quán và khó phân quyền đúng.
- Các quyền cần thêm đều là read-only evidence permissions.

Chi phí/impact:

- Chi phí AWS: không đáng kể.
- Effort: Low/Medium, cần IAM/SSO owner cập nhật permission set.
- Rủi ro nếu không làm: Medium/High, CDO07 bị block khi tự xác nhận runtime evidence.

Plan:

1. Ghi nhận các lệnh runtime bị deny với profile `TF4-AuditReadOnlyAndAnalyze`.
2. Request bổ sung quyền read-only:
   - `eks:DescribeCluster`
   - `s3:GetBucketPublicAccessBlock`
   - `s3:GetEncryptionConfiguration`
3. Sau khi permission được cập nhật, chạy lại các lệnh bị deny.
4. Lưu output mới vào `docs/evidence`.
5. Cập nhật permission blocker ticket.

Evidence cần thu:

```bash
aws eks describe-cluster --name techx-tf4-cluster --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-public-access-block --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
aws s3api get-bucket-encryption --bucket tf4-cloudtrail-logs-bucket-511825856493 --profile TF4-AuditReadOnlyAndAnalyze
```

Acceptance criteria:

- Audit profile tự chạy được `eks:DescribeCluster`.
- Audit profile tự đọc được S3 public access block và encryption configuration của CloudTrail log bucket.
- Permission blocker ticket được cập nhật với evidence mới hoặc lý do từ chối.

## 5. Thứ tự next action đề xuất

Recommended order:

1. CDO07-AUD-03: lưu Access Analyzer evidence và phân loại active findings vì runtime đã xác nhận `ACTIVE`.
2. CDO07-AUD-04: lưu CloudTrail/S3 evidence đã xác nhận và ghi blocker S3 metadata permissions.
3. CDO07-AUD-02: xử lý AWS Config vì runtime đã xác nhận recorder/delivery channel chưa tồn tại.
4. CDO07-AUD-11: request missing audit evidence permissions.
5. CDO07-AUD-05: cập nhật EKS audit/RBAC evidence với namespace `techx-tf4` và blocker `eks:DescribeCluster`.
6. CDO07-AUD-06: tạo weekly audit report sau khi evidence chính đã có.
7. CDO07-AUD-08 đến CDO07-AUD-09: hoàn thiện ADR và runbook evidence collection.

## 6. Definition of done

Backlog plan này được xem là done khi:

- Tất cả P1 auditability evidence đã được thu thập hoặc blocker đã được document.
- Weekly audit report tồn tại và link đến evidence.
- CloudTrail, AWS Config, IAM Access Analyzer và EKS audit status đã rõ ràng.
- Permission blockers của audit profile đã được giải quyết hoặc document.
- Accepted audit trade-offs có ADR.
