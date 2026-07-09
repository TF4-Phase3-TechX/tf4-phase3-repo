# AWS IAM Roles & Permission Sets Documentation

Tài liệu này mô tả chi tiết cấu trúc phân quyền AWS IAM Identity Center (SSO) và các IAM Policies tương ứng cho các nhóm làm việc (Groups) và người dùng cá nhân (Users) trong dự án TF4.

---

## 📌 Tổng quan cấu trúc Thư mục

Tài liệu được phân chia thành hai nhánh chính:
* [Group Directory (Nhóm)](group) - Phân quyền theo vai trò/chức năng dự án.
* [User Directory (Cá nhân)](user) - Quyền hạn đặc thù cho từng cá nhân.

---

## 👥 Bản đồ phân quyền Nhóm (Groups)

Dưới đây là danh sách các nhóm chức năng và các Permission Sets (Policies) được gán tương ứng:

| Nhóm (Group) | Tên nhóm đầy đủ | Danh sách Permission Sets (Policies) | Chi tiết |
| :--- | :--- | :--- | :--- |
| **cdo04** | `TF4-CDO04-CostPerformance` | <ul><li>[TF4-BaseReadOnly](TF4-BaseReadOnly.md)</li><li>[TF4-CostPerfReadOnlyAlerting](group/cdo04/TF4-CostPerfReadOnlyAlerting.md)</li></ul> | [Chi tiết cdo04](group/cdo04/README.md) |
| **cdo07** | `TF4-CDO07-Auditability` | <ul><li>[TF4-BaseReadOnly](TF4-BaseReadOnly.md)</li><li>[TF4-AuditReadOnlyAndAnalyze](group/cdo07/TF4-AuditReadOnlyAndAnalyze.md)</li></ul> | [Chi tiết cdo07](group/cdo07/README.md) |
| **cdo08** | `TF4-CDO08-SecurityReliability` | <ul><li>[TF4-BaseReadOnly](TF4-BaseReadOnly.md)</li><li>[TF4-SecReliabilityReadOnlyAudit](group/cdo08/TF4-SecReliabilityReadOnlyAudit.md)</li></ul> | [Chi tiết cdo08](group/cdo08/README.md) |
| **aio01** | `TF4-AIO01-AI` | <ul><li>[TF4-BaseReadOnly](TF4-BaseReadOnly.md)</li><li>[TF4-AIReadOnlyOrLimitedInvoke](group/aio01/TF4-AIReadOnlyOrLimitedInvoke.md)</li></ul> | [Chi tiết aio01](group/aio01/README.md) |

---

## 👤 Bản đồ phân quyền Người dùng (Users)

Quyền hạn đặc thù cho các cá nhân được cấu hình dựa trên nhu cầu công việc thực tế:

| Người dùng (User) | Danh sách Permission Sets (Policies) | Chi tiết |
| :--- | :--- | :--- |
| **nguyen** | <ul><li>[TF4-SecReliabilityReadOnlyAudit](user/nguyen/TF4-SecReliabilityReadOnlyAudit.md)</li><li>[TF4-SecurityIAMSSOManager](user/nguyen/TF4-SecurityIAMSSOManager.md)</li></ul> | [Chi tiết user nguyen](user/nguyen/README.md) |

---

## 🔐 Nguyên tắc thiết kế phân quyền

1. **Least Privilege (Đặc quyền tối thiểu)**: Đảm bảo chỉ cấp các quyền cần thiết để hoàn thành công việc. Hầu hết các nhóm đều chỉ có quyền ReadOnly đối với hạ tầng cơ bản.
2. **Separation of Duties (Phân tách nhiệm vụ)**:
   * **CDO04** tập trung vào chi phí và hiệu suất (Cost & Performance).
   * **CDO07** tập trung vào kiểm toán và log (Auditability & Trails).
   * **CDO08** tập trung vào bảo mật hạ tầng và độ tin cậy (Security & Reliability).
   * **AIO01** tập trung vào các dịch vụ AI và các mô hình ngôn ngữ lớn (Bedrock & AI Secrets).
   * **nguyen** (User) đóng vai trò Quản trị viên Bảo mật & IAM (IAM SSO Manager).
3. **IAM Identity Center (SSO)**: Mọi quyền hạn được áp dụng dưới dạng Permission Sets thông qua AWS Single Sign-On để quản lý tập trung và an toàn.
