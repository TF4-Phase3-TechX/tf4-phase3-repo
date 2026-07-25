# CDO08-REL-25 - Request chốt phương án internal dry run

**Subtask:** Automate shared-RDS PITR and accounting schema recovery workflow
**Owner:** CDO08 Reliability
**Mức ưu tiên:** P0
**Bên cần phê duyệt:** PM / Tech Lead / Platform / Cloud Security
**Cập nhật:** 2026-07-25

## Mục tiêu

Chọn access path phù hợp để chạy internal dry run:

```text
Shared production RDS backup
  -> PITR sang RDS mới
  -> export riêng schema accounting
  -> import vào database accounting_drill
  -> validate dữ liệu và đo RTO
  -> cleanup toàn bộ tài nguyên drill
```

Production RDS chỉ được dùng làm PITR source, không bị modify, đổi SG, đổi DNS
hoặc import dữ liệu.

## Vấn đề cần quyết định

Thiết kế ban đầu dùng validation pod với dedicated Security Group for Pods.
Attempt thực tế xác nhận:

```text
EKS node types: t3.large, t3a.large
ENABLE_POD_ENI=false
Pod status: Pending
Scheduler error: Insufficient vpc.amazonaws.com/pod-eni
```

AWS không hỗ trợ Security Groups for Pods trên instance family `t`. Vì vậy chỉ
bật `ENABLE_POD_ENI=true` không giải quyết được vấn đề trên node hiện tại.

Ba phương án đã được đánh giá dưới đây.

## Phương án 1: Dedicated Security Group for EKS Pod

### Luồng

```text
Validation pod
  -> branch ENI
  -> validation-client SG
  -> TCP/5432
  -> restore-target SG
  -> restored RDS
```

### Điểm tốt

- Mức cô lập tốt.
- Chỉ validation pod có network path tới Restore RDS.
- Khớp thiết kế guardrail ban đầu.

### Vì sao không phù hợp hiện tại

- Node `t3.large` và `t3a.large` không hỗ trợ ENI trunking cần cho Pod SG.
- `ENABLE_POD_ENI=false`.
- Bật cờ trên node family `t` vẫn không tạo được branch ENI.
- Muốn sử dụng phải tạo node group mới bằng instance type hỗ trợ trunking.
- Phải rollout VPC CNI và thay đổi networking của production EKS.
- Mức thay đổi quá lớn chỉ để chạy một validation pod tạm thời.

### Kết luận

```text
KHÔNG CHỌN
```

Không bật `ENABLE_POD_ENI` và không đổi node group production chỉ để phục vụ
REL-25 internal dry run.

## Phương án 2: Standard EKS Pod dùng EKS Node SG

### Luồng

```text
Validation pod
  -> network interface của EKS node
  -> EKS node SG
  -> TCP/5432
  -> restore-target SG
  -> restored RDS
```

### Điểm tốt

- Không cần Pod ENI hoặc `SecurityGroupPolicy`.
- Không cần bật `ENABLE_POD_ENI`.
- Không cần đổi node group.
- Thay đổi script ít hơn phương án EC2/SSM.

### Rủi ro

- Restore RDS phải cho phép TCP/5432 từ EKS node SG.
- Các pod khác dùng cùng node SG cũng có network path tới Restore RDS.
- PITR sao chép database users/passwords; production pod có credential hiện tại
  có thể đăng nhập Restore RDS nếu biết hoặc nhận được endpoint.
- NetworkPolicy chỉ áp dụng cho validation pod không ngăn các pod khác kết nối.
- Không đáp ứng đúng guardrail:

```text
Chỉ validation client được kết nối.
```

- Evidence sẽ phải ghi nhận đây là reduced-isolation mode.

### Khi nào có thể dùng

Chỉ dùng khi PM/Tech Lead chính thức chấp nhận reduced isolation, thay đổi
Acceptance Criteria và áp dụng đầy đủ kiểm soát bù:

- không tạo production DNS;
- Restore RDS tồn tại trong thời gian rất ngắn;
- không công bố endpoint cho application;
- có egress policy được enforce cho các workload khác;
- cleanup ngay sau validation.

### Kết luận

```text
KHÔNG KHUYẾN NGHỊ
```

Phương án chạy được về kỹ thuật nhưng không đạt mức cô lập mong muốn và tạo rủi
ro production pod truy cập nhầm Restore RDS.

## Phương án 3: Temporary private EC2 qua SSM

### Luồng

```text
Operator
  -> AWS Systems Manager
  -> temporary private EC2
  -> validation-client SG
  -> TCP/5432
  -> restore-target SG
  -> restored RDS
```

### Tài nguyên tạm được tạo

1. Một private EC2 validation client.
2. Một validation-client SG gắn trực tiếp vào EC2.
3. Một restore-target SG gắn trực tiếp vào RDS PITR.
4. Một RDS instance mới được tạo bằng PITR.
5. Một database `accounting_drill` trong RDS mới.
6. Một temporary secret/credential phục vụ drill.

EC2 yêu cầu:

```text
Public IP: false
Inbound: không có
SSH port 22: không mở
Access: SSM Session Manager/Run Command
Storage: encrypted, DeleteOnTermination=true
TTL/cleanup tags: bắt buộc
PostgreSQL client version: 17
```

Network rules:

```text
validation-client SG
  -> gắn trực tiếp vào temporary EC2

restore-target SG
  -> gắn trực tiếp vào RDS PITR
  -> ingress TCP/5432 duy nhất từ validation-client SG
```

Đây là SG thông thường của EC2/RDS, không liên quan Pod SG, Pod ENI,
`SecurityGroupPolicy`, EKS node group hoặc `ENABLE_POD_ENI`.

### Điểm tốt

- Validation client có SG riêng và thực sự được cô lập.
- Không thay đổi production EKS.
- Không phụ thuộc instance type của EKS node.
- Không mở RDS cho EKS node SG hoặc production pods.
- Truy cập EC2 qua SSM, không cần public IP/SSH.
- Đáp ứng guardrail chỉ validation client có network path.
- Tài nguyên có thể tạo và cleanup độc lập theo RestoreDrill tags.

### Điểm cần bổ sung

- Script hiện dùng `kubectl exec`; cần thêm SSM execution backend.
- Cần instance profile tối thiểu cho SSM và quyền đọc đúng temporary secret.
- Cần AMI được duyệt có PostgreSQL 17 client hoặc bootstrap tương đương.
- Có thêm chi phí EC2 trong thời gian drill, nhưng EC2 sẽ bị terminate ngay sau
  khi evidence hoàn tất.

### Kết luận

```text
KHUYẾN NGHỊ CHỌN
```

Đây là phương án cân bằng tốt nhất giữa isolation, mức ảnh hưởng production,
chi phí và khả năng cleanup.

## Thiết kế recovery được đề xuất

Chỉ tạo một RDS PITR mới để giảm chi phí:

```text
Temporary restored RDS
├── otel
│   ├── accounting
│   ├── catalog
│   └── reviews
└── accounting_drill
    └── accounting
```

Workflow:

1. Chọn restore timestamp trong PITR window.
2. Tạo private RDS PITR instance mới.
3. Chờ RDS `available` và verify restore-target SG.
4. Temporary EC2 kết nối tới RDS qua TCP/5432.
5. Tạo database `accounting_drill` trên restored RDS.
6. Chạy `pg_dump --schema=accounting` từ database `otel`.
7. Chạy `pg_restore` vào database `accounting_drill`.
8. Validate orphan, sequence và row counts.
9. Fail nếu `accounting_drill` có schema `catalog` hoặc `reviews`.
10. Ghi UTC start/end/duration từng phase và tổng `rto_seconds`.
11. Lưu evidence.
12. Cleanup RDS, EC2, EBS, SG và temporary secret.

Database `otel` là PITR source bên trong RDS mới. Database
`accounting_drill` là accounting recovery target và chỉ chứa schema
`accounting`.

Nếu yêu cầu là toàn bộ RDS instance cuối tuyệt đối không được chứa
`catalog/reviews`, cần tạo RDS target thứ hai. Phương án đó có chi phí và thời
gian cao hơn; cần PM xác nhận riêng.

## Thay đổi script cần thực hiện

Thêm backend:

```text
VALIDATION_BACKEND=ssm
VALIDATION_INSTANCE_ID=<temporary-ec2-id>
```

Tạo abstraction:

```text
validation_exec
  kubernetes -> kubectl exec
  ssm        -> aws ssm send-command/get-command-invocation
```

Trong SSM mode:

- không yêu cầu validation pod;
- không yêu cầu validation-client pod SG;
- kiểm tra EC2 private, không có public IP;
- kiểm tra EC2 gắn đúng validation-client SG;
- kiểm tra SSM instance ở trạng thái `Online`;
- kiểm tra `pg_isready`, `pg_dump`, `pg_restore`, `psql`;
- không ghi secret hoặc endpoint thật vào log.

Các guardrail vẫn giữ:

- đúng AWS account;
- PITR target khác production;
- target private;
- restore SG khác production SG;
- restore SG chỉ nhận TCP/5432 từ validation-client SG;
- không production DNS;
- không import vào production endpoint/database;
- chỉ dump/restore schema `accounting`;
- integrity validation;
- phase timestamps và tổng RTO;
- fail-safe cleanup và log tài nguyên còn sót.

## Quyết định đề xuất

```text
REL-25 sử dụng temporary private EC2 qua SSM làm validation client.
Không sử dụng dedicated Security Groups for Pods.
Không bật ENABLE_POD_ENI.
Không thay đổi EKS node group.
Không sử dụng EKS node SG làm source cho Restore RDS.
```

## Nội dung cần phê duyệt

Đề nghị PM/Tech Lead/Platform xác nhận:

- chấp thuận phương án temporary private EC2 qua SSM;
- AMI và instance type được phép sử dụng;
- private subnet và SSM access path;
- instance profile tối thiểu;
- TTL/chi phí tối đa;
- cho phép tạo một private RDS PITR instance;
- cho phép tạo database `accounting_drill` trong restored RDS;
- owner thực hiện cleanup và review evidence.

## Trạng thái attempt trước

Attempt dùng Pod SG đã được cleanup hoàn toàn:

- validation pod đã xóa;
- temporary Secret đã xóa;
- `SecurityGroupPolicy` đã xóa;
- validation-client SG đã xóa;
- restore-target SG đã xóa;
- RDS PITR target chưa từng được tạo;
- production RDS không bị thay đổi;
- không còn tài nguyên REL-25 phát sinh chi phí.

## Evidence

```text
docs/cdo08/week3/mandate20/evidence/CDO08-REL-25-INTERNAL-DRY-RUN-VERIFICATION-20260724.md
docs/cdo08/week3/mandate20/implementation/CDO08-REL-25-internal-dry-run-execution-guide.md
```

Subtask chỉ được đánh dấu Done sau khi live PITR trả exit code `0`, có
`rto_seconds`, validation pass và cleanup evidence được review.
