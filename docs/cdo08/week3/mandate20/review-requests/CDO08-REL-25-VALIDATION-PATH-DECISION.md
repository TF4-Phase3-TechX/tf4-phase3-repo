# CDO08 REL-25 - Quyết định validation path cho internal dry run

**Subtask:** Automate shared-RDS PITR and accounting schema recovery workflow
**Owner:** CDO08 Reliability
**Bên review:** Tech Lead / Platform / Cloud Security
**Quyết định:** Temporary private EC2 qua AWS Systems Manager
**Cập nhật:** 2026-07-26

## Vấn đề cần giải quyết

RDS PITR chỉ khôi phục được toàn bộ shared RDS instance:

```text
otel
├── accounting
├── catalog
└── reviews
```

Subtask chỉ cần chứng minh recovery cho `accounting`. Vì vậy cần một validation
client có thể:

- kết nối tới restored RDS;
- dump riêng schema `accounting`;
- import vào database `accounting_drill`;
- chạy reconciliation query;
- không mở network path cho production workloads.

## Guardrail bắt buộc

- Không restore vào production identifier hoặc endpoint.
- Restored RDS phải private.
- Không dùng production security group.
- Chỉ validation client có network path tới restored RDS.
- Không mở public ingress hoặc SSH.
- Secret không nằm trong script, Git hoặc evidence.
- Tài nguyên drill phải có TTL/cost/cleanup tags.
- Sau drill phải cleanup RDS, client, SG và credential access tạm.

## Phương án 1 - EKS Pod với dedicated Pod SG

### Luồng

```text
Validation pod
  -> Pod ENI
  -> validation-client SG
  -> TCP/5432
  -> restore SG
  -> restored RDS
```

### Điểm tốt

- Validation pod có security group riêng.
- Chỉ pod được chọn có network path tới restored RDS.
- Mức cô lập đáp ứng guardrail.

### Vì sao không chọn

EKS hiện dùng:

```text
t3.large
t3a.large
ENABLE_POD_ENI=false
```

Live attempt với `SecurityGroupPolicy` trả:

```text
Insufficient vpc.amazonaws.com/pod-eni
```

Instance family `t3`/`t3a` hiện tại không đáp ứng ENI trunking cần cho Security
Groups for Pods. Chỉ bật `ENABLE_POD_ENI=true` không đủ.

Muốn dùng phương án này phải:

- tạo node group bằng instance family hỗ trợ;
- thay đổi VPC CNI configuration;
- rollout networking trên production EKS;
- vận hành thêm node group chỉ cho một validation pod tạm.

Mức thay đổi production cluster quá lớn so với phạm vi internal restore drill.

### Kết luận

```text
KHÔNG CHỌN
```

## Phương án 2 - Standard EKS Pod dùng EKS Node SG

### Luồng

```text
Validation pod
  -> EKS node network interface
  -> EKS node SG
  -> TCP/5432
  -> restore SG
  -> restored RDS
```

### Điểm tốt

- Không cần Pod ENI.
- Không cần thay node group.
- Thay đổi script ít hơn phương án EC2.

### Vì sao không chọn

Security group được gắn vào node, không gắn riêng cho validation pod.

Nếu restore SG cho phép EKS node SG:

```text
Validation pod          -> có network path
Các pod khác cùng node  -> cũng có network path
```

NetworkPolicy của validation pod không thể ngăn các pod khác trên node kết nối
tới restored RDS.

PITR target kế thừa database users/passwords. Production pod đang có application
credential có thể đăng nhập restored RDS nếu biết endpoint.

Phương án này không đáp ứng đúng acceptance guardrail:

```text
Chỉ validation client được kết nối.
```

### Kết luận

```text
KHÔNG CHỌN
```

Chỉ có thể dùng nếu Tech Lead chính thức chấp nhận reduced isolation và thay đổi
Acceptance Criteria.

## Phương án 3 - Temporary private EC2 qua SSM

### Luồng

```text
Operator
  -> AWS Systems Manager
  -> temporary private EC2
  -> validation SG
  -> TCP/5432
  -> restore SG
  -> restored RDS
```

### Tài nguyên tạm

```text
IAM validation role/profile
Validation SG
Restore SG
Private EC2 validation client
Private RDS PITR target
Database accounting_drill
```

### Cấu hình EC2

```text
Public IP: false
Ingress: none
SSH: disabled
Access: SSM only
EBS: encrypted, DeleteOnTermination=true
IMDSv2: required
TTL/cleanup tags: required
```

### Network isolation

```text
Validation SG:
  gắn trực tiếp vào temporary EC2

Restore SG:
  gắn trực tiếp vào restored RDS
  ingress duy nhất TCP/5432 từ validation SG
```

Restore SG không cho phép:

- public CIDR;
- IPv6 CIDR;
- prefix list;
- production SG;
- EKS node SG;
- port ngoài `5432`.

### Credential isolation

- EC2 role chỉ đọc đúng RDS managed master secret ARN.
- Secret value chỉ được đọc bên trong EC2.
- Secret value không xuất hiện trong source code hoặc SSM output.
- IAM role và policy bị xóa sau drill.

### Điểm tốt

- Validation client có security group riêng.
- Không thay đổi production EKS.
- Không phụ thuộc EKS node instance family.
- Không mở restored RDS cho production pods.
- Không cần public IP hoặc SSH.
- Tài nguyên có thể tạo và cleanup độc lập.
- Đáp ứng guardrail chỉ validation client có network path.

### Điểm đánh đổi

- Phải tạo thêm một EC2 tạm.
- Có chi phí EC2 trong thời gian drill.
- Script cần quản lý IAM, EC2, SSM và cleanup.

EC2 sử dụng `t3.nano` và bị terminate ngay sau drill nên chi phí nhỏ so với RDS
PITR target.

### Kết luận

```text
CHỌN
```

Đây là phương án cân bằng tốt nhất giữa isolation, ảnh hưởng production, chi
phí và khả năng cleanup.

## Workflow sau khi chọn phương án 3

```text
1. Kiểm tra AWS account và PITR window.
2. Chọn restore timestamp.
3. Tạo IAM role/profile tạm.
4. Tạo validation SG và restore SG.
5. Tạo private EC2 và chờ SSM Online.
6. Yêu cầu AWS RDS PITR sang target mới.
7. Chờ target available và kiểm tra private/SG/endpoint.
8. EC2 dump riêng schema accounting từ database otel.
9. Tạo database accounting_drill.
10. Restore accounting vào accounting_drill.
11. So row counts và kiểm tra duplicate/orphan/unexpected schema.
12. Ghi tổng RTO.
13. Cleanup RDS, EC2/EBS, SG và IAM.
14. Kiểm tra AWS độc lập xác nhận không còn tài nguyên drill.
```

## Kết quả chứng minh

Live internal dry run đã PASS:

```text
Drill ID: rel25-20260726-b
Source counts: 205891,205891,377846
Target counts: 205891,205891,377846
Duplicates: 0
Shipping orphans: 0
Orderitem orphans: 0
Unexpected schemas: 0
Initial successful RTO: 1572 seconds
Post-refactor verification RTO: 1867 seconds
Exit code: 0
Cleanup: PASS
```

Production sau run:

```text
Status: available
Public: false
Endpoint: không đổi
Security group: không đổi
```

## Quyết định cuối

```text
REL-25 dùng temporary private EC2 qua SSM làm validation client.
Không dùng dedicated Security Groups for Pods.
Không bật ENABLE_POD_ENI.
Không thay đổi EKS node group.
Không dùng EKS node SG làm source cho restore RDS.
```

## Tài liệu liên quan

Script:

```text
docs/cdo08/week3/mandate20/scripts/postgres/rel25-restore-accounting-pitr.sh
docs/cdo08/week3/mandate20/scripts/postgres/lib/rel25-common.sh
docs/cdo08/week3/mandate20/scripts/postgres/rel25-accounting-recovery-remote.sh
```

Runbook:

```text
docs/cdo08/week3/mandate20/implementation/CDO08-REL-25-EC2-SSM-IMPLEMENTATION-RECORD-20260725.md
```

Giải thích workflow:

```text
docs/cdo08/week3/mandate20/implementation/CDO08-REL-25-HOW-ACCOUNTING-PITR-WORKS.md
```

Evidence:

```text
docs/cdo08/week3/mandate20/evidence/CDO08-REL-25-INTERNAL-DRY-RUN-EVIDENCE.md
```
