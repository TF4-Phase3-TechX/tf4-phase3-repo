# CDO07 - Identity Mapping & Change Trace (AUD-17.4)

**Nhóm thực hiện:** CDO07 (Audit)  
**Người thực hiện:** Võ Hồng Đức  
**Ngày thực hiện:** 2026-07-17  
**Trạng thái:** Hoàn thành  

---

## 1. Bối cảnh & Mục tiêu

Theo yêu cầu kiểm toán của **MANDATE-04 (Forensic Audit Trail)**, mọi hành động thay đổi lớn (Infrastructure/Configuration changes) và hoạt động vận hành khẩn cấp (On-call actions) phải được truy vết trực tiếp về **danh tính cá nhân cụ thể (Real Person)**. Không được sử dụng tài khoản dùng chung (shared account) cho con người.

Tài liệu này cung cấp:
1.  **Báo cáo rà soát IAM / SSO**: Chứng minh không có tài khoản dùng chung.
2.  **Bảng ánh xạ định danh (Identity Mapping Table)**: Kết nối Con người -> AWS Identity -> Kubernetes Group.
3.  **Truy vết 3 thay đổi hạ tầng gần nhất** đến người thực hiện.
4.  **Truy vết 3 phiên on-call gần nhất** đến người thực hiện.

---

## 2. Kết quả Rà soát Tài khoản (IAM & SSO Inventory)

Để phục vụ kiểm toán độc lập, chúng tôi đã trích xuất danh sách tài khoản IAM từ AWS API và lưu tại tệp [`docs/evidence/aud-17.4-iam-users-inventory.json`](aud-17.4-iam-users-inventory.json).

### Kết luận rà soát:
*   **Không sử dụng tài khoản dùng chung**: 100% IAM Users tĩnh trong hệ thống đều được gán nhãn theo định danh cá nhân (dạng `cdo04-<tên>` hoặc tên cá nhân cụ thể như `tin`). Không tồn tại tài khoản dạng `shared-*`, `team-admin`, hay `ops-operator`.
*   **Danh sách tài khoản IAM được quét**:
    *   `cdo04-an` (Ngô Nguyễn Trường An)
    *   `cdo04-huy` (Tạ Hoàng Huy)
    *   `cdo04-ninh` (Nguyễn Quách Khang Ninh)
    *   `cdo04-tin` (Văn Phú Tín)
    *   `cdo04-tuan` (Phan Minh Tuấn)
    *   `cdo04-vinh` (Nguyễn Thành Vinh)
    *   `tin` (Văn Phú Tín - Tài khoản định danh cá nhân)

---

## 3. Bảng Ánh xạ Định danh (Identity Mapping Table)

Dưới đây là bảng ánh xạ hoàn chỉnh 100% từ thành viên dự án tới tài khoản AWS (SSO Assumed Role / IAM User) và nhóm tương ứng trên cụm Kubernetes:

### Nhóm CDO04 - Platform & Cost-Performance (Nhóm CD-G04)
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set / IAM User | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Văn Phú Tín** | Lead Platform | `AWSReservedSSO_TF4-DeployOperator_eb819e1d80dc6016` / IAM `cdo04-tin` (`AIDAXOKZSY7W7B3Y6BKGH`), `tin` (`AIDAXOKZSY7WQKJG6AMD6`) | `system:masters` (Admin) | Toàn quyền cụm K8s, GitOps, IaC |
| **Ngô Nguyễn Trường An** | Member | `AWSReservedSSO_TF4-DeployOperator_eb819e1d80dc6016` / IAM `cdo04-an` (`AIDAXOKZSY7WTTLW3YONF`) | `system:masters` (Admin) | Quản trị cụm, Deploy ứng dụng |
| **Nguyễn Thành Vinh** | Member | `AWSReservedSSO_TF4-DeployOperator_eb819e1d80dc6016` / IAM `cdo04-vinh` (`AIDAXOKZSY7W7ULSAQVP5`) | `system:masters` (Admin) | Quản trị cụm, Deploy ứng dụng |
| **Phan Minh Tuấn** | Member | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` (`tuan`) / IAM `cdo04-tuan` (`AIDAXOKZSY7W5QSO4CXVW`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên, Cost/Perf |
| **Tạ Hoàng Huy** | Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`huy`) / IAM `cdo04-huy` (`AIDAXOKZSY7WY23QPXDQ5`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên |
| **Nguyễn Quách Khang Ninh**| Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`ninh`) / IAM `cdo04-ninh` (`AIDAXOKZSY7WVZRWDBRXP`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên |
| **Nguyễn Văn Huy Hoàng** | Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`hoang.nguyenvan`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên |
| **Huỳnh Sỹ Thương** | Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`thuong.huynhsy`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên |
| **Đỗ Khánh Linh** | Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`linh.dokhanh`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên |
| **Nguyễn Quang Thịnh** | Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`thinh.nguyenquang`) | `base-readonly-users` | Đọc cấu hình, check tài nguyên |

### Nhóm CDO07 - Auditability & Compliance (Nhóm CD-G07)
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set (SSO Username) | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Nguyễn Duy Hoàng** | Lead Audit | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`hoang.nguyenduy`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Võ Hồng Đức** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`duc.vo`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Trần Minh Quang** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`quang.tranminh`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Bùi Thành Nghĩa** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`nghia.bui`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Đinh Văn Ty** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`ty.dinhvan`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Nguyễn Thị Huy Hoàng** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`hoang.nguyenthinhuy`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Lê Trung Trực** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`truc.le`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Huỳnh Bá Huân** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`huan.huynh`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Hoàng Kim Hùng** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`hung.hoangkim`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Nguyễn Phú Triệu** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` (`trieu.nguyenphu`) | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |

### Nhóm CDO08 - Security & Reliability (Nhóm CD-G08)
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set (SSO Username) | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Đinh Viết Quyết** | Lead CDO08 | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` (`quyet.dinhviet`) | `security-reliability-auditors` | Quản lý bảo mật, SLO threshold |
| **Từ Phúc Nguyên** | Lead IAM/SSO | `AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10` (`nguyen`) | `system:masters` (Admin/IAM) | Quản trị IAM/SSO, Key management |
| **Ngô Kim Hoàng Nam** | Member/IAM | `AWSReservedSSO_TF4-SecurityIAMSSOManager_7fec96c816beda10` (`nam`) | `system:masters` (Admin/IAM) | Quản trị IAM/SSO, Karpenter/Runtime pin |
| **Hoàng Minh Hải** | Member | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` (`hai`) | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Trần Đình Minh Quân** | Member | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` (`quan`) | `security-reliability-auditors` | Triển khai policy-as-code |
| **Nguyễn Thị Tiểu Phương**| Member | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` (`phuong.nguyenthitieu`) | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Trần Đình Quân** | Member | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` (`quan.trandinh`) | `security-reliability-auditors` | Hỗ trợ cấu hình bảo mật |
| **B'Nướch Thị Thủy** | Member | `AWSReservedSSO_TF4-BaseReadOnly_5e03394d61df47e7` (`thuy`) | `base-readonly-users` | Đọc logs bảo mật & Audit |
| **Nguyễn Hoàng Nhân** | Member | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` (`nhan.nguyenhoang`) | `security-reliability-auditors` | Hỗ trợ vận hành bảo mật |

### Nhóm AIO01 - AI Operations (Nhóm AI-G01)
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set (SSO Username) | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Đinh Danh Nam** | Tech Lead AI | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`nam.dinhdanh`) | `ai-readers` | Định hướng kỹ thuật AI, Bedrock |
| **Trần Đình Thông** | PM AI | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`thong.trandinh`) | `ai-readers` | Quản lý dự án AI, lập kế hoạch |
| **Huỳnh Xuân Hậu** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`hau.huynhxuan`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Huỳnh Nguyễn Ngọc Tân**| Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`tan.huynhnguyenngoc`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Cái Xuân Hoà** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`hoa.caixuan`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Nguyễn Trần Huy Vũ** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`vu.nguyentranhuy`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Nguyễn Văn Tuấn Anh** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`anh.nguyenvantuan`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Lê Ngọc Thành Tâm** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`tam.lengocthanh`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Nguyễn Tất Văn** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` (`van.nguyentat`) | `ai-readers` | Đọc logs AI, Invoke Bedrock |

---

## 4. Truy vết 3 thay đổi cấu hình hạ tầng gần nhất (Change Trail)

Toàn bộ hạ tầng và cấu hình hệ thống được quản lý dưới dạng mã nguồn (Infrastructure as Code - IaC) trong kho Git. Khi có thay đổi được đẩy lên Git, hệ thống CI/CD (GitHub Actions) sẽ tự động assume role AWS để thực hiện deploy.

Dưới đây là 3 thay đổi IaC gần nhất được truy vết thành công:

### Thay đổi 1: Runtime hardening policy-as-code (Commit `2e98734`)
*   **Thời gian (Timestamp):** Thu Jul 16 23:30:58 2026 +0700
*   **Người thực hiện (Git Author):** Tran Dinh Minh Quan (`163095752+Remmusss@users.noreply.github.com`)
*   **Hành động IaC:** Merged PR #240 — triển khai admission policy-as-code cho runtime hardening.
*   **Dấu vết Cloud (CloudTrail):** GitHub Actions Workflow được kích hoạt và assume AWS Role `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-ecr-build/GitHubActions` để push container images lên ECR.

### Thay đổi 2: Complete runtime hardening values (Commit `b7887de`)
*   **Thời gian (Timestamp):** Thu Jul 16 16:18:40 2026 +0700
*   **Người thực hiện (Git Author):** haihm191 (`119120119+2hm1901@users.noreply.github.com`)
*   **Hành động IaC:** Merged PR #259 — hoàn thiện cấu hình values cho runtime hardening.
*   **Dấu vết Cloud (CloudTrail):** CI/CD tự động assume role `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-ecr-build/GitHubActions` để cập nhật resources.

### Thay đổi 3: Add detailed cost estimation for security slack alerts (Commit `cf34a33`)
*   **Thời gian (Timestamp):** Thu Jul 16 14:52:22 2026 +0700
*   **Người thực hiện (Git Author):** Bùi Thành Nghĩa (`161110817+BuiThanhNghiaDTU19122004@users.noreply.github.com`)
*   **Hành động IaC:** Merged PR #249 — bổ sung tài liệu chi tiết ước tính chi phí cho cấu hình security Slack alerts.
*   **Dấu vết Cloud (CloudTrail):** Commit merge kích hoạt workflow CI/CD assume role `arn:aws:sts::511825856493:assumed-role/tf4-github-actions-ecr-build/GitHubActions`.

*Chi tiết log thô các thay đổi này được lưu tại tệp [`aud-17.4-infra-changes-7days.json`](aud-17.4-infra-changes-7days.json).*

---

## 5. Truy vết 3 hành động On-Call gần nhất (Bastion SSM Access)

Khi cần thực hiện on-call khẩn cấp để giám sát cổng vận hành nội bộ (như Grafana), các kiểm toán viên phải mở phiên Session Manager (SSM) thông qua tài khoản SSO cá nhân.

Dưới đây là 3 phiên on-call gần nhất được trích xuất từ CloudTrail:

### Phiên 1: On-call truy cập Grafana bởi Bùi Thành Nghĩa (CDO07)
*   **Thời gian (Timestamp):** 2026-07-16T22:55:39+07:00
*   **Người thực hiện (Username):** `nghia.bui`
*   **Tài khoản AWS (Caller ARN):** `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/nghia.bui`
*   **Session ID:** `nghia.bui-yp3dudfzi22aj2qdxhvlggbbjq`
*   **Hành động thực tế:** Mở cổng forward SSM port-forwarding tới Bastion Host `i-072084d1cf0b2f1c9` (Local Port 3000 → Remote Port 13000).

### Phiên 2: On-call truy cập Jaeger bởi thành viên CDO08 (quan)
*   **Thời gian (Timestamp):** 2026-07-16T17:35:15+07:00
*   **Người thực hiện (Username):** `quan`
*   **Tài khoản AWS (Caller ARN):** `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/quan`
*   **Session ID:** `quan-6jojtusct6s2f35488sfppzzh4`
*   **Hành động thực tế:** Mở cổng forward SSM port-forwarding tới Bastion Host `i-072084d1cf0b2f1c9` (Port 16686 — Jaeger UI).

### Phiên 3: On-call truy cập hệ thống bởi thành viên CDO08 (quan)
*   **Thời gian (Timestamp):** 2026-07-16T17:18:08+07:00
*   **Người thực hiện (Username):** `quan`
*   **Tài khoản AWS (Caller ARN):** `arn:aws:sts::511825856493:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/quan`
*   **Session ID:** `quan-xplxgfhc3hbv8jv5lg8bzahqdu`
*   **Hành động thực tế:** Mở cổng forward SSM port-forwarding tới Bastion Host `i-072084d1cf0b2f1c9` (Local Port 8089 → Remote Port 18089).

*Chi tiết log thô các phiên này được lưu tại tệp [`aud-17.4-bastion-access-7days.json`](aud-17.4-bastion-access-7days.json).*

---

## 6. Hướng dẫn Mentor truy vết nhanh bằng AWS CLI (Forensic Runbook Snippet)

Để kiểm chứng tính xác thực của các thông tin trên tại chỗ, mentor có thể chạy các lệnh kiểm tra sau:

### Lệnh 1: Kiểm tra danh sách người dùng IAM (Không có shared account)
```bash
aws iam list-users --query "Users[*].UserName"
```

### Lệnh 2: Kiểm tra phiên SSM StartSession gần nhất
```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=StartSession \
  --query "Events[*].{Time:EventTime, User:Username, Session:Resources[0].ResourceName}" \
  --max-results 5
```

### Lệnh 3: Kiểm tra người thực hiện thay đổi mã nguồn gần nhất
```bash
git log -n 3 --format="%h - %an <%ae> - %ad : %s"
```
