# CDO08-REL-25 - Yêu cầu điều kiện chạy internal dry run

**Task:** Tự động hóa PITR shared RDS và khôi phục schema accounting  
**Owner:** CDO08 Reliability  
**Mức ưu tiên:** P0  
**Môi trường:** Internal isolated restore drill  
**Thực hiện:** Nhân (CDO08 Reliability)  
**Bên cấp quyền:** Platform / Cloud Security  
**Cập nhật:** 2026-07-24

## Nội dung yêu cầu

Nhờ leader và các bên liên quan cấp hoặc phê duyệt các điều kiện AWS và
Kubernetes bên dưới để CDO08 thực hiện một lần internal dry run RDS PITR.

## Vì sao cần request này

Acceptance Criteria yêu cầu **restore thành công trong internal dry run**.
Kiểm tra cú pháp hoặc chạy `PREFLIGHT_ONLY=true` chỉ chứng minh script và
guardrail hoạt động; chưa chứng minh AWS có thể tạo RDS PITR thật, validation
client kết nối được, schema `accounting` export/import thành công hoặc RTO thực
tế là bao nhiêu.

Internal dry run phải tạo một RDS instance mới từ automated backup. Đây là tài
nguyên AWS có phát sinh chi phí và cần quyền cao hơn các lệnh read-only.
**Nhân sẽ tự tạo toàn bộ resources cần thiết** (security groups, validation pod,
temporary secrets) sau khi được Platform cấp đủ quyền AWS và Kubernetes.
Không assign cho người khác tạo sẵn.

Không thể dùng production SG, production endpoint, production DNS hoặc
production application pod để thay thế. Việc đó có thể làm validation nhầm trên
production hoặc khiến dữ liệu restore bị production truy cập, trái với yêu cầu
restore cô lập và không đụng production.

Các tài nguyên và quyền được yêu cầu bên dưới là mức tối thiểu để:

- tạo RDS PITR mới trong private network;
- chỉ cho validation client kết nối qua TCP/5432;
- dùng temporary credential thay vì ghi secret thật vào script;
- export/import riêng schema `accounting`;
- ghi log start/end và tổng RTO thực tế;
- cleanup RDS, pod và temporary secret sau khi lưu evidence.

## Blocker hiện tại

Kết quả kiểm tra read-only ngày 2026-07-24:

- AWS SSO và Kubernetes context đang truy cập được.
- Source RDS đang ở trạng thái `available`, private và có PITR restore window
  hợp lệ từ automated backup.
- Chưa tìm thấy security group có tag `Environment=RestoreDrill`.
- Chưa có pod đang chạy với label `restore-validation-client=true`.
- SSO role hiện tại từng nhận lỗi `UnauthorizedOperation` khi gọi
  `ec2:CreateSecurityGroup`.
- Operator chưa được cung cấp `ACCOUNTING_TARGET_HOST` cô lập và temporary
  database credential.

Các bước kiểm tra trên không tạo RDS instance, security group, pod, secret, DNS
record hoặc tài nguyên cloud nào.

## Tài nguyên Nhân sẽ tự tạo

Sau khi được cấp đủ quyền AWS và Kubernetes, Nhân sẽ tự tạo toàn bộ
các tài nguyên bên dưới trước khi chạy dry run.

### Validation-client security group

Nhân tự tạo trong cùng VPC với source RDS:

- Không cần database ingress.
- Chỉ gắn vào ENI của validation-client pod.
- Tag `Purpose=RestoreValidationClient`.

### Restore-target security group

Nhân tự tạo trong cùng VPC với source RDS:

- Chỉ có một ingress rule: TCP/5432 từ validation-client security group.
- Không cho phép CIDR, IPv6 CIDR, prefix list, production security group hoặc
  public ingress.
- Tag `Purpose=RestoreTarget`.

Cả hai security group phải có tags:

```text
Owner=CDO08
Environment=RestoreDrill
Mandate=20
Task=CDO08-REL-25
RestoreDrillId=<approved-drill-id>
TTLHours=24
CleanupAfter=<approved-UTC-timestamp>
CostCenter=ReliabilityDrill
Production=false
```

### Accounting drill target database

Nhân tự tạo hoặc provision một database dùng cho `ACCOUNTING_TARGET_HOST`.
Target này phải:

- private và chỉ validation client truy cập được;
- không trùng source RDS endpoint hoặc PITR staging endpoint;
- không dùng production DNS;
- được phép thao tác drop/create schema `accounting`;
- không chứa schema `catalog` hoặc `reviews`.

### Validation pod

Nhân tự tạo pod trong namespace `techx-tf4` với:

- label `restore-validation-client=true`;
- image có `pg_isready`, `pg_dump`, `pg_restore` và `psql`;
- service account riêng cho restore drill;
- không có production application role hoặc production DNS alias;
- credential nhận từ Kubernetes Secret tạm do Nhân tự tạo;
- được xóa cùng temporary secrets sau khi thu evidence.

## Quyền AWS cần Platform cấp cho Nhân

Nhân cần được cấp các quyền sau vào SSO role để tự tạo và vận hành
toàn bộ resources drill:

```text
sts:GetCallerIdentity
rds:DescribeDBInstances
rds:DescribeDBInstanceAutomatedBackups
rds:DescribeDBSubnetGroups
rds:ListTagsForResource
rds:RestoreDBInstanceToPointInTime
rds:ModifyDBInstance
rds:DeleteDBInstance
ec2:DescribeSecurityGroups
ec2:DescribeNetworkInterfaces
ec2:CreateSecurityGroup
ec2:CreateTags
ec2:AuthorizeSecurityGroupIngress
ec2:RevokeSecurityGroupIngress
ec2:DeleteSecurityGroup
```

Trong phạm vi AWS condition hỗ trợ, giới hạn quyền tạo, gắn tag và xóa vào tài
nguyên có:

```text
Environment=RestoreDrill
Task=CDO08-REL-25
Production=false
```

Quyền `rds:DeleteDBInstance` chỉ dùng cho cleanup đã được review sau khi lưu
evidence.

## Quyền Kubernetes cần Platform cấp cho Nhân

Nhân cần được cấp quyền trong namespace `techx-tf4` để tự tạo và
xóa các tài nguyên Kubernetes của drill:

```text
pods: create, get, list, delete, exec
secrets: create, get, delete
serviceaccounts: create, delete
SecurityGroupPolicy (VPC CNI CRD): create, delete
```

Nhân sẽ tự tạo validation pod, service account, temporary Secrets và
`SecurityGroupPolicy` theo spec. Platform không cần tạo sẵn.

## Giá trị runtime cần chuyển qua kênh bảo mật

Đề nghị cung cấp các giá trị sau ngoài Git và ticket:

```text
EXPECTED_AWS_ACCOUNT_ID
EXPECTED_KUBE_CONTEXT
RESTORE_SECURITY_GROUP_ID
VALIDATION_CLIENT_SECURITY_GROUP_ID
ACCOUNTING_TARGET_HOST
temporary PostgreSQL authentication material
```

CDO08 sẽ chọn restore timestamp và target identifier sau khi PITR window và
naming guardrail pass.

## Nội dung cần leader phê duyệt

Đề nghị xác nhận:

- cho phép Nhân tạo một private, single-AZ RDS PITR instance để chạy drill;
- TTL tối đa 24 giờ và khoảng chi phí tối đa được phép;
- restore timestamp window được chấp thuận;
- Platform cấp đủ quyền AWS và Kubernetes cho Nhân để tự tạo resources;
- Nhân chịu trách nhiệm tạo, vận hành và cleanup toàn bộ drill resources;
- PM review evidence trước khi Nhân thực hiện cleanup và đóng subtask.

## Evidence CDO08 sẽ cung cấp

Sau khi được cấp đủ điều kiện, CDO08 sẽ cung cấp:

- preflight log có `preflight_only_passed no_rds_instance_created`;
- live log thể hiện restore request, instance `available`, network validation,
  accounting export/import và duration của từng phase;
- kết quả integrity có số orphan của shipping/order-item bằng `0`, đồng thời
  không có schema `catalog` hoặc `reviews`;
- tổng `rto_seconds`;
- cleanup evidence xác nhận RDS drill target, temporary pod và secrets đã được
  xóa.

Subtask chỉ hoàn thành khi lệnh internal dry run trả exit code `0` và toàn bộ
evidence trên được review.

---

## PM Approval

**Người phê duyệt:** Hải (PM)  
**Ngày:** 2026-07-24  
**Trạng thái:** ✅ APPROVED

### Nội dung phê duyệt

Tôi xác nhận đã đọc toàn bộ request này và phê duyệt các điều kiện sau:

- Cho phép **Nhân** tạo **một** private, single-AZ RDS PITR instance trong môi
  trường isolated để chạy internal dry run. Instance phải được cleanup sau khi
  lưu evidence, không để lại resource mồ côi.
- TTL tối đa **24 giờ** kể từ khi RDS PITR target được tạo.
- Restore timestamp phải nằm trong PITR window hiện có của source RDS; không
  yêu cầu backup bổ sung.
- **Nhân tự tạo toàn bộ resources cần thiết** (security groups, validation pod,
  temporary secrets, accounting drill target) — không assign cho người khác.
- Yêu cầu Platform/Cloud Security **cấp quyền AWS và Kubernetes** cho Nhân theo
  danh sách trong request. Platform không cần tạo sẵn resource.
- Nhân **không được** dùng production SG, production endpoint, production DNS
  hoặc production application pod để thay thế bất kỳ prerequisite nào.
- PM sẽ review evidence trước khi Nhân cleanup và đóng subtask REL25-2.

### Ghi chú

Request được đánh giá hợp lý, tối thiểu quyền và không tạo rủi ro cho
production. Các guardrail trong script `rel25-restore-accounting-pitr.sh` đã
được review và đủ để ngăn restore nhầm production.
Nhân là người duy nhất chịu trách nhiệm end-to-end cho dry run này.
