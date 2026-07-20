# [AUDIT-015] Self-service SCP chống làm mù hệ thống audit

**Trạng thái**: IN PROGRESS  
**Reporter**: Nguyễn Duy Hoàng - Nhóm CDO07 (Audit)  
**Assignee**: CDO07 tự triển khai bằng tài khoản AWS Organizations do CDO04 cấp  
**Nhóm phối hợp**: CDO04 (Platform Admin / AWS Organizations), CDO08 (Security / SSO / IAM)  
**Độ ưu tiên**: P0 (Blocker nghiệm thu Mandate #12 / Task 42)  
**Epic**: Mandate-12 / Targeted Sensitive Data Access Audit  
**Account mục tiêu**: TF4 `511825856493`

---

## 1. Bối cảnh

Mandate #12 yêu cầu hệ thống audit của TF4 không có "cửa sổ mù": kể cả Administrator trong account TF4 cũng không được tắt, sửa đổi hoặc xóa các đường ghi log cốt lõi mà không bị chặn hoặc không để lại dấu vết cảnh báo.

Các quyền IAM trong account thành viên không đủ để bảo đảm ràng buộc này, vì Administrator vẫn có thể tự cấp lại quyền. Do đó control bắt buộc phải đặt ở lớp AWS Organizations bằng **Service Control Policy (SCP)** và gắn vào account TF4 `511825856493` hoặc OU chứa account TF4.

Ban đầu ticket này được lập để yêu cầu CDO04 thực hiện trên Management Account. Từ thời điểm CDO04 đã cấp tài khoản Organizations cho CDO07, phạm vi ticket chuyển thành **CDO07 tự triển khai, tự thu evidence và nhờ CDO04 hỗ trợ nếu quyền Organizations bị thiếu hoặc cần rollback ở lớp org**.

---

## 2. Mục tiêu kiểm soát

SCP phải từ chối các hành động có thể làm mù hoặc làm suy yếu audit trail đối với:

- **AWS CloudTrail**: không cho dừng trail, xóa trail, sửa cấu hình trail, hoặc thay đổi event/insight selectors.
- **AWS Config**: không cho dừng/xóa recorder, xóa/sửa delivery channel, xóa config rule, hoặc sửa recorder theo hướng giảm phạm vi ghi nhận.

SCP này áp dụng cho mọi IAM User/Role trong account TF4, bao gồm cả các role Administrator. Việc bảo trì chính sách hoặc tháo policy phải được thực hiện từ tài khoản AWS Organizations theo quy trình CDO04/CDO07.

---

## 3. Service Control Policy đề xuất

Tên đề xuất: `TF4-Deny-Audit-Blinding`

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyCloudTrailBlindingActions",
      "Effect": "Deny",
      "Action": [
        "cloudtrail:StopLogging",
        "cloudtrail:DeleteTrail",
        "cloudtrail:UpdateTrail",
        "cloudtrail:PutEventSelectors",
        "cloudtrail:PutInsightSelectors"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyConfigBlindingActions",
      "Effect": "Deny",
      "Action": [
        "config:StopConfigurationRecorder",
        "config:DeleteConfigurationRecorder",
        "config:PutConfigurationRecorder",
        "config:DeleteDeliveryChannel",
        "config:PutDeliveryChannel",
        "config:DeleteConfigRule"
      ],
      "Resource": "*"
    }
  ]
}
```

Ghi chú vận hành:

- `PutConfigurationRecorder` và `PutDeliveryChannel` được deny vì hai API này có thể thay đổi phạm vi ghi nhận hoặc nơi giao evidence.
- Nếu cần thay đổi hợp lệ cho CloudTrail/AWS Config, thực hiện theo maintenance window: tạm detach SCP từ AWS Organizations, apply thay đổi đã được duyệt, kiểm tra lại logging, rồi attach SCP lại ngay.
- Không đặt exception cho role Administrator trong TF4; exception như vậy sẽ phá mục tiêu của Mandate #12.

---

## 4. Runbook triển khai bằng org account

Biến môi trường mẫu:

```powershell
$OrgProfile = "<org-management-profile>"
$TargetAccountId = "511825856493"
$PolicyName = "TF4-Deny-Audit-Blinding"
$PolicyFile = "tf4-deny-audit-blinding-scp.json"
```

### 4.1. Kiểm tra đang dùng đúng tài khoản Organizations

```powershell
aws sts get-caller-identity --profile $OrgProfile
aws organizations describe-organization --profile $OrgProfile
aws organizations list-roots --profile $OrgProfile
```

Kết quả cần lưu evidence:

- Caller identity thuộc Management Account hoặc delegated admin có quyền quản lý SCP.
- Organization đang bật policy type `SERVICE_CONTROL_POLICY`.
- Account TF4 `511825856493` xuất hiện trong organization:

```powershell
aws organizations describe-account `
  --account-id $TargetAccountId `
  --profile $OrgProfile
```

### 4.2. Tạo file policy cục bộ

Lưu JSON ở mục 3 vào file `$PolicyFile`, sau đó validate JSON trước khi tạo policy:

```powershell
Get-Content $PolicyFile | ConvertFrom-Json | Out-Null
```

### 4.3. Tạo SCP

```powershell
$PolicyContent = Get-Content $PolicyFile -Raw

aws organizations create-policy `
  --name $PolicyName `
  --description "Deny CloudTrail and AWS Config blinding actions for TF4 Mandate-12" `
  --type SERVICE_CONTROL_POLICY `
  --content $PolicyContent `
  --profile $OrgProfile
```

Lưu lại `Policy.Id` trả về, ví dụ `p-xxxxxxxx`.

Nếu policy đã tồn tại, lấy lại ID bằng:

```powershell
aws organizations list-policies `
  --filter SERVICE_CONTROL_POLICY `
  --profile $OrgProfile
```

### 4.4. Gắn SCP vào account TF4

```powershell
$PolicyId = "<policy-id-from-create-or-list>"

aws organizations attach-policy `
  --policy-id $PolicyId `
  --target-id $TargetAccountId `
  --profile $OrgProfile
```

Kiểm tra policy đã gắn:

```powershell
aws organizations list-policies-for-target `
  --target-id $TargetAccountId `
  --filter SERVICE_CONTROL_POLICY `
  --profile $OrgProfile

aws organizations list-targets-for-policy `
  --policy-id $PolicyId `
  --profile $OrgProfile
```

---

## 5. Nghiệm thu kỹ thuật

Thực hiện các lệnh dưới đây bằng profile Administrator hoặc role có quyền cao trong account TF4. Kết quả đạt là `AccessDenied` hoặc `AccessDeniedException` do explicit deny từ Organizations SCP.

### 5.1. CloudTrail StopLogging bị chặn

```powershell
$Tf4AdminProfile = "<tf4-admin-profile>"

aws cloudtrail stop-logging `
  --name tf4-general-cloudtrail `
  --region us-east-1 `
  --profile $Tf4AdminProfile
```

Kết quả đạt:

```text
An error occurred (AccessDeniedException) ... explicitly denied by a service control policy
```

Kiểm tra trail vẫn đang ghi:

```powershell
aws cloudtrail get-trail-status `
  --name tf4-general-cloudtrail `
  --region us-east-1 `
  --profile $Tf4AdminProfile
```

`IsLogging` phải là `true`.

### 5.2. AWS Config StopConfigurationRecorder bị chặn

```powershell
aws configservice describe-configuration-recorders `
  --region us-east-1 `
  --profile $Tf4AdminProfile

aws configservice stop-configuration-recorder `
  --configuration-recorder-name tf4-aws-config-recorder `
  --region us-east-1 `
  --profile $Tf4AdminProfile
```

Kết quả đạt:

```text
An error occurred (AccessDeniedException) ... explicitly denied by a service control policy
```

Kiểm tra recorder vẫn đang ghi:

```powershell
aws configservice describe-configuration-recorder-status `
  --region us-east-1 `
  --profile $Tf4AdminProfile
```

`recording` phải là `true`.

---

## 6. Evidence cần đính kèm khi đóng ticket

Tối thiểu cần lưu các bằng chứng sau:

| Evidence ID | Nội dung | Kết quả đạt |
| --- | --- | --- |
| `AUDIT-015-E01` | `describe-organization`, `describe-account` cho TF4 | Xác nhận đúng org và đúng account `511825856493` |
| `AUDIT-015-E02` | `create-policy` hoặc `describe-policy` cho `TF4-Deny-Audit-Blinding` | SCP tồn tại với đúng JSON |
| `AUDIT-015-E03` | `list-policies-for-target` và `list-targets-for-policy` | SCP đã attach vào account TF4 hoặc OU chứa TF4 |
| `AUDIT-015-E04` | Kết quả `cloudtrail stop-logging` bằng TF4 admin | Bị `AccessDenied` bởi SCP |
| `AUDIT-015-E05` | `cloudtrail get-trail-status` sau test | `IsLogging=true` |
| `AUDIT-015-E06` | Kết quả `configservice stop-configuration-recorder` bằng TF4 admin | Bị `AccessDenied` bởi SCP |
| `AUDIT-015-E07` | `describe-configuration-recorder-status` sau test | `recording=true` |

---

## 7. Rollback có kiểm soát

Chỉ rollback khi có incident vận hành hoặc thay đổi đã được CDO04/CDO07 duyệt:

```powershell
aws organizations detach-policy `
  --policy-id $PolicyId `
  --target-id $TargetAccountId `
  --profile $OrgProfile
```

Sau rollback tạm thời phải:

1. Ghi rõ lý do, người duyệt, thời điểm detach.
2. Thực hiện thay đổi cần thiết.
3. Xác minh CloudTrail và AWS Config vẫn đang logging.
4. Attach lại SCP.
5. Chạy lại nghiệm thu ở mục 5.

---

## 8. Definition of Done

- SCP `TF4-Deny-Audit-Blinding` tồn tại trong AWS Organizations.
- SCP được gắn vào account TF4 `511825856493` hoặc OU chứa account TF4.
- Administrator trong account TF4 không thể chạy thành công `cloudtrail:StopLogging`.
- Administrator trong account TF4 không thể chạy thành công `config:StopConfigurationRecorder`.
- CloudTrail `tf4-general-cloudtrail` vẫn `IsLogging=true` sau test.
- AWS Config recorder `tf4-aws-config-recorder` vẫn `recording=true` sau test.
- Evidence `AUDIT-015-E01` đến `AUDIT-015-E07` được lưu vào PR/Jira/tài liệu nghiệm thu Mandate #12.
