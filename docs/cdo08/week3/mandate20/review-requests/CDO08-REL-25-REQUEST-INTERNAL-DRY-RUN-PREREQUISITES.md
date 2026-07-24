# CDO08-REL-25 - Yêu cầu điều kiện chạy internal dry run

**Task:** Tự động hóa PITR shared RDS và khôi phục schema accounting  
**Owner:** CDO08 Reliability  
**Mức ưu tiên:** P0  
**Môi trường:** Internal isolated restore drill  
**Bên cần hỗ trợ:** Platform / Cloud Security / Database owner  
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
nguyên AWS có phát sinh chi phí và cần quyền cao hơn các lệnh read-only. CDO08
hiện chưa có RestoreDrill security group, validation pod, accounting drill
target và đầy đủ quyền AWS, nên cần leader cùng Platform/Cloud Security cấp hoặc
phê duyệt trước khi chạy.

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

## Tài nguyên AWS cần cấp

Cần hai security group trong cùng VPC với source RDS.

### Validation-client security group

- Không cần database ingress.
- Chỉ gắn vào ENI của validation-client pod.
- Có tag `Purpose=RestoreValidationClient`.

### Restore-target security group

- Chỉ có một ingress rule: TCP/5432 từ validation-client security group.
- Không cho phép CIDR, IPv6 CIDR, prefix list, production security group hoặc
  public ingress.
- Có tag `Purpose=RestoreTarget`.

Cả hai security group cần các tag:

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

Đề nghị cung cấp một accounting drill database endpoint dùng cho
`ACCOUNTING_TARGET_HOST`. Target này phải:

- private và chỉ validation client truy cập được;
- không trùng source RDS endpoint hoặc PITR staging endpoint;
- không dùng production DNS;
- được phê duyệt cho thao tác drop/create schema `accounting`;
- không chứa schema `catalog` hoặc `reviews`.

## Quyền AWS cần cấp

Execution role được phê duyệt cần các quyền:

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
```

Nếu Platform không tạo sẵn hai security group, cần cấp thêm các quyền có scope:

```text
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

## Tài nguyên Kubernetes cần cấp

Cần đúng một validation pod đang chạy trong namespace `techx-tf4` với label:

```text
restore-validation-client=true
```

Pod phải:

- nhận validation-client SG qua cơ chế pod ENI được cluster phê duyệt;
- có `pg_isready`, `pg_dump`, `pg_restore` và `psql`;
- sử dụng service account riêng cho restore drill;
- không có production application role hoặc production DNS alias;
- nhận credential của PITR restore và accounting drill từ Kubernetes Secret tạm
  hoặc secret manager đã được phê duyệt;
- cho phép CDO08 chạy `kubectl get` và `kubectl exec`;
- được xóa cùng temporary secrets sau khi thu evidence.

Platform có thể tạo sẵn các tài nguyên trên hoặc cấp cho CDO08 quyền có scope để
tạo/xóa validation pod, temporary Secrets và `SecurityGroupPolicy` tương ứng.

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

- cho phép tạo một private, single-AZ RDS PITR instance để chạy drill;
- TTL và khoảng chi phí tối đa được phép;
- restore timestamp window được chấp thuận;
- bên chịu trách nhiệm tạo SG, validation pod, temporary secrets và accounting
  drill target;
- người phê duyệt và thực hiện cleanup sau khi evidence được lưu.

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
