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

Để phục vụ kiểm toán độc lập, chúng tôi đã trích xuất danh sách tài khoản IAM từ AWS API và lưu tại tệp [`docs/evidence/mandate-04-forensic/aud-17.4-iam-users-inventory.json`](aud-17.4-iam-users-inventory.json).

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

Dưới đây là bảng ánh xạ hoàn chỉnh 100% từ thành viên dự án tới tài khoản AWS SSO (Username & Permission Set), IAM User tĩnh (nếu có) và nhóm tương ứng trên cụm Kubernetes:

### Nhóm CDO04 - Platform & Cost-Performance
| Thành viên (Real Person) | Vai trò | AWS SSO Username | AWS SSO Permission Set | IAM User tĩnh / Arn (nếu có) | Kubernetes Group |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Văn Phú Tín** | Member | `phutin` | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` | `tin` (`AIDAXOKZSY7WQKJG6AMD6`), `cdo04-tin` (`AIDAXOKZSY7W7B3Y6BKGH`) | `base-readonly-users`, `system:masters` (qua IAM) |
| **Ngô Nguyễn Trường An** | Member | `anngo` | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` | `cdo04-an` (`AIDAXOKZSY7WTTLW3YONF`) | `base-readonly-users`, `system:masters` (qua IAM) |
| **Nguyễn Thành Vinh** | Member | `vinhkhuat` | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` | `cdo04-vinh` (`AIDAXOKZSY7W7ULSAQVP5`) | `base-readonly-users`, `system:masters` (qua IAM) |
| **Phan Minh Tuấn** | Member | `tuan` | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` | `cdo04-tuan` (`AIDAXOKZSY7W5QSO4CXVW`) | `base-readonly-users` |
| **Tạ Hoàng Huy** | Member | `huy` | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` | `cdo04-huy` (`AIDAXOKZSY7WY23QPXDQ5`) | `base-readonly-users` |
| **Nguyễn Quách Khang Ninh**| Member | `ninh` | `AWSReservedSSO_TF4-CostPerfReadOnlyAlerting_9122727d2f4b2e86` | `cdo04-ninh` (`AIDAXOKZSY7WVZRWDBRXP`) | `base-readonly-users` |

### Nhóm CDO07 - Auditability & Compliance
| Thành viên (Real Person) | Vai trò | AWS SSO Username | AWS SSO Permission Set | Kubernetes Group | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Bùi Thành Nghĩa** | Tech Lead | `nghia.bui` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS, On-call verification |
| **Đinh Văn Ty** | Project Manager | `ty.dinh` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Nguyễn Thị Huy Hoàng** | Member | `huyhoang.nthi` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Võ Hồng Đức** | Member | `duc.vo` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Lê Trung Trực** | Member | `truc.le` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Nguyễn Duy Hoàng** | Member | `hoang.nguyenduy` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Huỳnh Bá Huân** | Member | `huan.huynh` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Hoàng Kim Hùng** | Member | `hung.hoangkim` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Trần Minh Quang** | Member | `quang.tranminh` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |
| **Nguyễn Phú Triệu** | Member | `trieu.nguyen` | `AWSReservedSSO_TF4-AuditReadOnlyAndAnalyze_2b03e7d876722882` | `audit-readonly-analyzers` | Kiểm toán CloudTrail, log EKS |

### Nhóm CDO08 - Security & Reliability
| Thành viên (Real Person) | Vai trò | AWS SSO Username | AWS SSO Permission Set | Kubernetes Group | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Từ Phúc Nguyên** | Tech Lead | `nguyen` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Hoàng Minh Hải** | Member | `hai` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Nguyễn Thị Tiểu Phương**| Member | `phuong` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Trần Đình Minh Quân** | Member | `quan` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Triển khai policy-as-code |
| **Ngô Kim Hoàng Nam** | Member | `nam` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Cấu hình bảo mật, monitor reliability |
| **Nguyễn Hoàng Nhân** | Member | `nhan` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Hỗ trợ vận hành bảo mật |
| **B'Nướch Thị Thủy** | Member | `thuy` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Đọc logs bảo mật & Audit |
| **Đinh Viết Quyết** | Member | `quyet` | `AWSReservedSSO_TF4-SecReliabilityReadOnlyAudit_e76349e1ba8a6155` | `security-reliability-auditors` | Hỗ trợ vận hành bảo mật |

### Nhóm AIO01 - AI Operations
| Thành viên (Real Person) | Vai trò | AWS SSO Username | AWS SSO Permission Set | Kubernetes Group | Quyền hạn cốt lõi |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Đinh Danh Nam** | Tech Lead | `danhnam` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Định hướng kỹ thuật AI, Bedrock |
| **Trần Đình Thông** | Project Manager | `dinhthong` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Quản lý dự án AI, lập kế hoạch |
| **Nguyễn Trần Huy Vũ** | Member | `huyvu` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Cái Xuân Hoà** | Member | `xuanhoa` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Huỳnh Xuân Hậu** | Member | `xuanhau` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Lê Ngọc Thành Tâm** | Member | `tamhieu` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Đọc logs AI, Invoke Bedrock |
| **Nguyễn Tất Văn** | Member | `tatvan` | `AWSReservedSSO_TF4-AIReadOnlyOrLimitedInvoke_4536cac35e2c79b6` | `ai-readers` | Đọc logs AI, Invoke Bedrock |

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
