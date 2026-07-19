# [AUDIT-015] Yêu cầu áp dụng Service Control Policy (SCP) chống làm mù hệ thống audit

**Trạng thái**: TO DO  
**Người yêu cầu (Reporter)**: Nguyễn Duy Hoàng - Nhóm CDO07 (Audit)  
**Người thực hiện (Assignee)**: Nhóm CDO04 (Platform Admin ở Master Account)  
**Nhóm phối hợp**: Nhóm CDO07 (nghiệm thu evidence), Nhóm CDO08 (Security/SSO/IAM)  
**Độ ưu tiên (Priority)**: P0 (Blocker nghiệm thu Mandate #12 / Task 42)  
**Epic**: Mandate-12 / Targeted Sensitive Data Access Audit

---

## 1. Bối cảnh (Context)

Để thực hiện yêu cầu bảo mật của **Task 42 / MANDATE-12** (Chống làm mù hệ thống audit - Blinding Threat Prevention), hệ thống cần đảm bảo **cấm triệt để** mọi hành vi tắt, sửa đổi hoặc xóa các dịch vụ giám sát/audit cốt lõi (AWS CloudTrail và AWS Config). 

Ràng buộc bảo mật yêu cầu chính sách này phải có hiệu lực với **tất cả mọi IAM User và Role thuộc tài khoản TF4 (bao gồm cả Administrator)**. Do đó, việc cấu hình bắt buộc phải sử dụng **Service Control Policy (SCP)** từ tài khoản Master (Management Account) của AWS Organizations. 

Vì tài khoản/profile hiện tại của team TF4 không có quyền thao tác trên tài khoản Master của AWS Organizations, Nguyễn Duy Hoàng (CDO07) tạo ticket này yêu cầu **Nhóm CDO04** (đơn vị nắm giữ Master Account) hỗ trợ thiết lập và áp dụng SCP này.

---

## 2. Phân tích các hành động cần cấm (Blinding Threat Analysis)

Để bảo vệ toàn diện hệ thống audit khỏi việc bị làm mù, các hành động API sau cần được đưa vào danh sách từ chối (`Deny`):

### 2.1. Đối với AWS CloudTrail (Bảo vệ vết ghi hoạt động Cloud)
* `cloudtrail:StopLogging`: Ngăn chặn việc tắt chức năng ghi log của trail.
* `cloudtrail:DeleteTrail`: Ngăn chặn việc xóa hoàn toàn trail.
* `cloudtrail:UpdateTrail`: Ngăn chặn việc sửa cấu hình (ví dụ: đổi bucket lưu log sang bucket rác, tắt multi-region, tắt encryption).
* `cloudtrail:PutEventSelectors` và `cloudtrail:PutInsightSelectors`: Ngăn chặn việc thay đổi bộ lọc sự kiện (event selectors) để bỏ qua không ghi các hoạt động nhạy cảm.

### 2.2. Đối với AWS Config (Bảo vệ vết ghi cấu hình tài nguyên)
* `config:StopConfigurationRecorder`: Ngăn chặn việc tắt recorder thu thập lịch sử thay đổi cấu hình.
* `config:DeleteConfigurationRecorder`: Ngăn chặn việc xóa hoàn toàn recorder.
* `config:DeleteDeliveryChannel`: Ngăn chặn việc xóa kênh chuyển giao thông tin cấu hình (delivery channel) tới S3/SNS.
* `config:DeleteConfigRule`: Ngăn chặn việc xóa các quy tắc kiểm tra tuân thủ cấu hình.

---

## 3. Yêu cầu từ CDO04 / Platform Admin (The What)

Vui lòng tạo một Service Control Policy (SCP) mới tại AWS Organizations với nội dung JSON dưới đây và gán trực tiếp vào tài khoản thành viên **TF4 (`511825856493`)** hoặc Organizational Unit (OU) tương ứng chứa tài khoản TF4.

### Nội dung Service Control Policy (SCP) đề xuất:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyDisablingAuditingServicesForTF4",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
        "cloudtrail:UpdateTrail",
        "cloudtrail:PutEventSelectors",
        "cloudtrail:PutInsightSelectors",
        "config:StopConfigurationRecorder",
        "config:DeleteConfigurationRecorder",
        "config:DeleteDeliveryChannel",
        "config:DeleteConfigRule"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## 4. Cách thức kiểm tra và nghiệm thu (DoD)

Sau khi SCP được cấu hình và gán thành công bởi Quản trị viên CDO04:

1. Đăng nhập vào tài khoản TF4 (`511825856493`) bằng quyền **Administrator** (hoặc bất kỳ role nào khác).
2. Thử dừng ghi log CloudTrail bằng CLI:
   ```bash
   aws cloudtrail stop-logging --name tf4-general-cloudtrail
   ```
   **Kết quả đạt:** Hệ thống phải trả về lỗi `AccessDeniedException` hoặc `AccessDenied`.
3. Thử dừng AWS Config recorder bằng CLI:
   ```bash
   aws configservice stop-configuration-recorder --configuration-recorder-name <recorder_name>
   ```
   **Kết quả đạt:** Hệ thống phải trả về lỗi `AccessDeniedException` hoặc `AccessDenied`.
