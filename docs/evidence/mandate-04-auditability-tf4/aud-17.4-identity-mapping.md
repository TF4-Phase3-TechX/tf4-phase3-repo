# CDO07 - Identity Mapping & Change Trace (AUD-17.4)

**Nhóm thực hiện:** CDO07 (Audit)  
**Người thực hiện:** Võ Hồng Đức  
**Ngày thực hiện:** 2026-07-15  
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
    *   `cdo04-an` (Lê Trung An)
    *   `cdo04-huy` (Nguyễn Huy Hoàng)
    *   `cdo04-ninh` (Bùi Thành Nghĩa)
    *   `cdo04-tin` (Văn Phú Tín)
    *   `cdo04-tuan` (Trần Minh Tuấn)
    *   `cdo04-vinh` (Lê Thế Vinh)
    *   `tin` (Văn Phú Tín - Tài khoản định danh cá nhân)

---

## 3. Bảng Ánh xạ Định danh (Identity Mapping Table)

Dưới đây là bảng ánh xạ hoàn chỉnh 100% từ thành viên dự án tới tài khoản AWS (SSO Assumed Role / IAM User) và nhóm tương ứng trên cụm Kubernetes:

### Nhóm CDO04 - Platform & Cost-Performance
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set / IAM User | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Văn Phú Tín** | Lead Platform | `AWSReservedSSO_TF4-DeployOperator_<ROLE_HASH>` / IAM `cdo04-tin`, `tin` | `system:masters` (Admin) | Toàn quyền cụm K8s, GitOps, IaC |
| **Lê Trung An** | Member | `AWSReservedSSO_TF4-DeployOperator_<ROLE_HASH>` / IAM `cdo04-an` | `system:masters` (Admin) | Quản trị cụm, Deploy ứng dụng |
| **Nguyễn Thanh Vinh** | Member | `AWSReservedSSO_TF4-DeployOperator_<ROLE_HASH>` / IAM `cdo04-vinh` | `system:masters` (Admin) | Quản trị cụm, Deploy ứng dụng |
| **Phan Minh Tuấn** | Member | `AWSReservedSSO_TF4-BaseReadOnly_<ROLE_HASH>` / IAM `cdo04-tuan` | `base-readonly-users` | Đọc cấu hình, check tài nguyên |
| **Nguyễn Huy Hoàng** | Member | `AWSReservedSSO_TF4-BaseReadOnly_<ROLE_HASH>` / IAM `cdo04-huy` | `base-readonly-users` | Đọc cấu hình, check tài nguyên |

### Nhóm CDO07 - Auditability & Compliance
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set / IAM User | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Nguyễn Duy Hoàng** | Lead Audit | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_<ROLE_HASH>` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Võ Hồng Đức** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_<ROLE_HASH>` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Trần Minh Quang** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_<ROLE_HASH>` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Bùi Thành Nghĩa** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_<ROLE_HASH>` / IAM `cdo04-ninh` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Nguyễn Thị Tiểu Phương**| Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_<ROLE_HASH>` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Ty** | Member | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_<ROLE_HASH>` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |

### Nhóm CDO08 - Security & Reliability
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set / IAM User | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Đinh Viết Quyết** | Lead CDO08 | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_<ROLE_HASH>` | `security-reliability-auditors` | Quản lý bảo mật, SLO threshold |
| **Hải** | Member | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_<ROLE_HASH>` | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Từ Phúc Nguyên** | Admin/IAM | `AWSReservedSSO_TF4-SecurityIAMSSOManager_<ROLE_HASH>` / IAM `nguyen` | `system:masters` (Admin/IAM) | Quản trị IAM/SSO, Key management |

### Nhóm AIO01 - AI Operations
| Thành viên (Real Person) | Vai trò | AWS SSO Permission Set / IAM User | Kubernetes Group (EKS) | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- |
| **Ngo Kim Hoang Nam** | Lead AI | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_<ROLE_HASH>` | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Đinh Danh Nam** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_<ROLE_HASH>` | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Tạ Huy** | Member | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_<ROLE_HASH>` | `ai-readers` | Đọc logs AI, Invoke Bedrock |

---

## 4. Truy vết 3 thay đổi cấu hình hạ tầng gần nhất (Change Trail)

Toàn bộ hạ tầng và cấu hình hệ thống được quản lý dưới dạng mã nguồn (Infrastructure as Code - IaC) trong kho Git. Khi có thay đổi được đẩy lên Git, hệ thống CI/CD (GitHub Actions) sẽ tự động assume role AWS để thực hiện deploy.

Dưới đây là 3 thay đổi IaC gần nhất được truy vết thành công:

### Thay đổi 1: GitOps Hardening (Commit `ca63f7e`)
*   **Thời gian (Timestamp):** Wed Jul 15 13:46:12 2026 +0700
*   **Người thực hiện (Git Author):** Văn Phú Tín (`vanphutin2902@gmail.com`)
*   **Hành động IaC:** Pushed commit `ca63f7e` để làm cứng phân quyền GitOps delivery ownership.
*   **Dấu vết Cloud (CloudTrail):** GitHub Actions Workflow được kích hoạt và assume AWS Role `arn:aws:sts::123456789012:assumed-role/tf4-github-actions-terraform-apply` để cập nhật cụm EKS.

### Thay đổi 2: Karpenter fix & EKS permissions (Commit `b7254b3`)
*   **Thời gian (Timestamp):** Tue Jul 14 23:44:02 2026 +0700
*   **Người thực hiện (Git Author):** Văn Phú Tín (`vanphutin2902@gmail.com`)
*   **Hành động IaC:** Cấu hình `amiSelectorTerms` và cấp quyền EKS view cho role `terraform-plan`.
*   **Dấu vết Cloud (CloudTrail):** Trình tự deploy tự động kích hoạt bởi CI/CD sử dụng role `tf4-github-actions-terraform-apply`.

### Thay đổi 3: Karpenter NodePool / EC2NodeClass to IaC (Commit `d9ee8a2`)
*   **Thời gian (Timestamp):** Tue Jul 14 22:15:32 2026 +0700
*   **Người thực hiện (Git Author):** Văn Phú Tín (`vanphutin2902@gmail.com`)
*   **Hành động IaC:** Đưa cấu hình NodePool và EC2NodeClass của Karpenter vào quản lý trực tiếp bằng Terraform.
*   **Dấu vết Cloud (CloudTrail):** Cập nhật tài nguyên EKS và EC2 thông qua role deploy tự động `tf4-github-actions-terraform-apply`.

*Chi tiết log thô các thay đổi này được lưu tại tệp [`docs/evidence/aud-17.4-infra-changes-7days.json`](aud-17.4-infra-changes-7days.json).*

---

## 5. Truy vết 3 hành động On-Call gần nhất (Bastion SSM Access)

Khi cần thực hiện on-call khẩn cấp để giám sát cổng vận hành nội bộ (như Grafana), các kiểm toán viên phải mở phiên Session Manager (SSM) thông qua tài khoản SSO cá nhân.

Dưới đây là 3 phiên on-call gần nhất được trích xuất từ CloudTrail:

### Phiên 1: On-call truy cập Grafana bởi Võ Hồng Đức
*   **Thời gian (Timestamp):** 2026-07-15T10:57:59Z (17:57:59+07)
*   **Người thực hiện (Username):** `duc.vo`
*   **Tài khoản AWS (Caller ARN):** `arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/duc.vo`
*   **Session ID:** `duc.vo-jxrknnpr75rvx8b3c9k8778tty`
*   **Hành động thực tế:** Mở cổng forward luồng dữ liệu SSM port-forwarding tới Bastion Host `i-072084d1cf0b2f1c9` (Port 13000).

### Phiên 2: On-call truy cập Grafana bởi Trần Minh Quang
*   **Thời gian (Timestamp):** 2026-07-15T10:57:17Z (17:57:17+07)
*   **Người thực hiện (Username):** `quang.tranminh`
*   **Tài khoản AWS (Caller ARN):** `arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882/quang.tranminh`
*   **Session ID:** `quang.tranminh-ozqjhac5hii6p2szs657iz6yly`
*   **Hành động thực tế:** Mở cổng forward luồng dữ liệu SSM port-forwarding tới Bastion Host `i-072084d1cf0b2f1c9` (Port 13000).

### Phiên 3: On-call truy cập hệ thống bởi thành viên CDO08 (Hải)
*   **Thời gian (Timestamp):** 2026-07-15T10:56:18Z (17:56:18+07)
*   **Người thực hiện (Username):** `hai`
*   **Tài khoản AWS (Caller ARN):** `arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155/hai`
*   **Session ID:** `hai-8xypi7vbuis5l8kahlehtx97ui`
*   **Hành động thực tế:** Mở phiên kết nối SSM port-forwarding tới Bastion Host `i-072084d1cf0b2f1c9` (Port 13000).

*Chi tiết log thô các phiên này được lưu tại tệp [`docs/evidence/aud-17.4-bastion-access-7days.json`](aud-17.4-bastion-access-7days.json).*

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
